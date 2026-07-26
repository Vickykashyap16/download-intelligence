import Foundation

/// The complete, raw result of one `ProcessRunner.run(_:)` invocation:
/// exactly what the engine's own process reported, with no interpretation
/// of *meaning* layered on top (that belongs to the artifact readers and,
/// later, to the GUI's own screen logic — `GUI Architecture Specification.md`
/// §12: error propagation is the engine's own, unmodified signal, carried
/// through, not re-authored).
///
/// `outcome` classifies only the exit code itself, per the exact table
/// documented in `src/cli.py`'s own module docstring:
/// 0 = success or an intentionally-reported "nothing to do" state,
/// 1 = an unanticipated internal error (the outermost `try/except` in
/// `main()`), 2 = a usage error (raised by `argparse` itself), 3 = the
/// process was aborted via Ctrl-C (`KeyboardInterrupt`). Any other exit code
/// is not part of that documented table and is preserved rather than
/// force-fit into one of the four known buckets.
public struct CommandResult: Equatable, Sendable {
    public let command: EngineCommand
    public let exitCode: Int32
    public let standardOutput: String
    public let standardError: String
    public let outcome: Outcome

    public init(
        command: EngineCommand,
        exitCode: Int32,
        standardOutput: String,
        standardError: String
    ) {
        self.command = command
        self.exitCode = exitCode
        self.standardOutput = standardOutput
        self.standardError = standardError
        self.outcome = Outcome(exitCode: exitCode)
    }

    /// True only for the one exit code (`0`) `src/cli.py` documents as
    /// success. A caller that only cares about "did this work" can check
    /// this without switching on `outcome` themselves.
    public var succeeded: Bool {
        exitCode == 0
    }

    public enum Outcome: Equatable, Sendable {
        case completed
        case unexpectedError
        case usageError
        case aborted
        case unrecognizedExitCode(Int32)

        init(exitCode: Int32) {
            switch exitCode {
            case 0: self = .completed
            case 1: self = .unexpectedError
            case 2: self = .usageError
            case 3: self = .aborted
            default: self = .unrecognizedExitCode(exitCode)
            }
        }
    }
}
