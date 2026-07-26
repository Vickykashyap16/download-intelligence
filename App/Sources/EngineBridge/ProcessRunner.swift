import Foundation

/// Invokes the real, frozen CLI (`python3 -m src.cli <args>`) as an external
/// process and returns its complete result. This is the *only* type in this
/// package that ever spawns a process — every other Engine Bridge component
/// either calls through this one or reads on-disk artifacts directly.
///
/// This is an `actor` (not a plain struct/class) so that concurrent callers
/// serialize on the Swift-level bookkeeping automatically; the actual
/// single-mutation-slot business rule, however, lives in
/// `EngineMutationGuard`, not here — `ProcessRunner` only knows how to run
/// one process safely and correctly, and deliberately does not decide
/// whether it *should* be allowed to run right now. Keeping those concerns
/// separate is what §"No duplicated logic" / SOLID single-responsibility
/// means concretely for this work package.
///
/// Safety rules this type enforces unconditionally, matching
/// `GUI Architecture Specification.md` §8 and §9:
///
/// 1. A command whose `requiresInteractiveInput` is `true` is refused before
///    any subprocess is spawned, unless the caller explicitly opts in via
///    `allowInteractive: true`. The GUI itself is expected to never need
///    that opt-in in normal operation — every real screen collects its
///    decision first and calls the corresponding non-interactive form
///    (e.g. `execute(yes: true, debug:)`). The opt-in exists only so this
///    fact is asserted in code, not merely in documentation, and so a test
///    can exercise the refusal path deterministically.
/// 2. Standard input is always a pipe whose write end this runner closes
///    itself immediately after the process launches — never the terminal's
///    own stdin, and never left open. For the rare, explicitly-opted-in
///    interactive invocation this means the child's first read of stdin
///    receives immediate end-of-file rather than hanging or reading
///    unrelated data; for every ordinary, non-interactive invocation it
///    guarantees the process can never block waiting on input that this
///    package has no way to provide.
/// 3. Standard output and standard error are captured completely and
///    returned as part of `CommandResult` — never streamed to the GUI
///    process's own stdout/stderr, and never discarded.
public actor ProcessRunner {
    /// Where to find the engine checkout and how to invoke Python.
    public struct Configuration: Sendable {
        /// The directory containing `src/` — i.e. the real
        /// `Download Intelligence` project root, invoked as
        /// `python3 -m src.cli` from this working directory (matching how
        /// `src/cli.py` is actually run today; it is a package module, not a
        /// standalone script).
        public let projectRootURL: URL

        /// The argv prefix that resolves to a working Python 3 interpreter
        /// on the user's machine, resolved through `/usr/bin/env` so this
        /// works regardless of whether Python is a `pyenv` shim, a
        /// Homebrew install, or the system interpreter. Defaults to
        /// `["python3"]`; overridable for a machine where the working
        /// interpreter is named differently or lives in a virtual
        /// environment that must be activated via an explicit path.
        public let pythonInvocation: [String]

        public init(
            projectRootURL: URL,
            pythonInvocation: [String] = ["python3"]
        ) {
            self.projectRootURL = projectRootURL
            self.pythonInvocation = pythonInvocation
        }
    }

    private let configuration: Configuration
    private let logger: GUILogger?

    public init(configuration: Configuration, logger: GUILogger? = nil) {
        self.configuration = configuration
        self.logger = logger
    }

    /// Runs `command` to completion and returns its full result.
    ///
    /// - Parameter allowInteractive: Must be `true` to run a command for
    ///   which `command.requiresInteractiveInput` is `true`. Defaults to
    ///   `false`. This package provides no mechanism to actually *supply*
    ///   interactive input even when this is `true` — stdin is always
    ///   closed immediately after launch (see type documentation) — so
    ///   setting this to `true` only changes whether the refusal in rule 1
    ///   above happens; it does not make an interactive command behave
    ///   differently once it starts.
    /// - Throws: `EngineBridgeError.commandRequiresInteractiveInput` if
    ///   refused per rule 1; `EngineBridgeError.projectRootNotFound` if the
    ///   configured project root does not exist;
    ///   `EngineBridgeError.failedToLaunchProcess` if the OS could not spawn
    ///   the process at all (as opposed to the process launching and then
    ///   exiting non-zero, which is not an error at this layer — see
    ///   `CommandResult.outcome`).
    public func run(
        _ command: EngineCommand,
        allowInteractive: Bool = false
    ) async throws -> CommandResult {
        if command.requiresInteractiveInput && !allowInteractive {
            throw EngineBridgeError.commandRequiresInteractiveInput(command)
        }
        guard FileManager.default.fileExists(atPath: configuration.projectRootURL.path) else {
            throw EngineBridgeError.projectRootNotFound(configuration.projectRootURL.path)
        }

        let process = Process()
        process.currentDirectoryURL = configuration.projectRootURL
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = configuration.pythonInvocation + ["-m", "src.cli"] + command.argv

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        // Started before the process is even launched: reading a pipe's
        // read end blocks (on a background thread, not this actor) until
        // data arrives or every write-end reference is closed — it does not
        // require the writer to already exist. Starting these concurrently
        // with the launch, rather than after waiting for exit, is what
        // avoids the classic Process+Pipe deadlock: if the child ever
        // writes enough output to fill the OS pipe buffer before anyone
        // reads it, and nothing is reading yet, the child blocks on its own
        // write() call and never reaches exit.
        async let stdoutData = Self.readAll(stdoutPipe.fileHandleForReading)
        async let stderrData = Self.readAll(stderrPipe.fileHandleForReading)

        let exitCode: Int32
        do {
            exitCode = try await Self.launchAndAwaitExit(
                process,
                closingAfterLaunch: [
                    // Closed immediately after a successful launch, not
                    // after exit: this is what delivers end-of-file to the
                    // child's stdin right away (see rule 2 above), and what
                    // guarantees the parent's own reference to the
                    // stdout/stderr write ends is gone so that, once the
                    // child's copy of those descriptors closes at exit, the
                    // reads above actually observe end-of-file instead of
                    // blocking forever waiting for a write end that will
                    // never come (the parent process, having created the
                    // Pipe, holds its own duplicate of the write end in
                    // addition to the child's).
                    stdinPipe.fileHandleForWriting,
                    stdoutPipe.fileHandleForWriting,
                    stderrPipe.fileHandleForWriting
                ]
            )
        } catch {
            throw EngineBridgeError.failedToLaunchProcess(String(describing: error))
        }

        let standardOutput = String(data: await stdoutData, encoding: .utf8) ?? ""
        let standardError = String(data: await stderrData, encoding: .utf8) ?? ""

        let result = CommandResult(
            command: command,
            exitCode: exitCode,
            standardOutput: standardOutput,
            standardError: standardError
        )
        await logger?.log(result: result)
        return result
    }

    /// Launches `process` and suspends until it exits, returning its
    /// termination status. Uses `Process.terminationHandler` rather than
    /// the synchronous, blocking `Process.waitUntilExit()` so that no
    /// thread in the cooperative Swift Concurrency thread pool is ever tied
    /// up sleeping for the duration of an engine run (which, for `scan` or
    /// `run` over a large Downloads folder, could be a non-trivial amount
    /// of wall-clock time).
    private static func launchAndAwaitExit(
        _ process: Process,
        closingAfterLaunch handlesToClose: [FileHandle]
    ) async throws -> Int32 {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Int32, Error>) in
            process.terminationHandler = { finishedProcess in
                continuation.resume(returning: finishedProcess.terminationStatus)
            }
            do {
                try process.run()
                for handle in handlesToClose {
                    handle.closeFile()
                }
            } catch {
                process.terminationHandler = nil
                for handle in handlesToClose {
                    handle.closeFile()
                }
                continuation.resume(throwing: error)
            }
        }
    }

    /// Reads a pipe end to completion on a background thread, off the
    /// actor's own executor, so a large volume of engine output never
    /// blocks Swift Concurrency's cooperative thread pool.
    private static func readAll(_ handle: FileHandle) async -> Data {
        await withCheckedContinuation { (continuation: CheckedContinuation<Data, Never>) in
            DispatchQueue.global(qos: .utility).async {
                let data = handle.readDataToEndOfFile()
                continuation.resume(returning: data)
            }
        }
    }
}
