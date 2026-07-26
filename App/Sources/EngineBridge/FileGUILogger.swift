import Foundation

/// The severity of one GUI-side diagnostic log line. Distinct from
/// anything in the engine's `action` vocabulary — this is a shell-level
/// concept (per `Desktop Implementation Blueprint.md` §13: "UI-level
/// errors, Engine Bridge invocation failures, unexpected internal GUI
/// conditions"), not a business event.
public enum GUILogLevel: String, Sendable {
    case debug = "DEBUG"
    case info = "INFO"
    case warning = "WARNING"
    case error = "ERROR"
}

/// A file-backed, rotating implementation of `GUILogger`.
///
/// Three requirements from `Desktop Implementation Blueprint.md` §13 and
/// `GUI Architecture Specification.md` §15 govern this type's entire
/// design, and each maps to a specific, deliberate choice below:
///
/// 1. **"Never merged with the engine's action log."** This type never
///    reads, writes, or even knows the path of `action_log.jsonl`. It is
///    constructed with its own, independent `logDirectoryURL` — a
///    directory the caller chooses, entirely separate from anything
///    `EngineArtifactLocations` points at. Nothing in this file imports or
///    references `ActionLogReader`, `ActionLogEntry`, or any engine
///    artifact path.
/// 2. **"Must never become a source of truth" / a logging failure must
///    never disrupt the application.** `GUILogger.log(result:)` is
///    non-throwing by protocol design (see `GUILogger.swift`) precisely so
///    a concrete implementation cannot force callers to handle "the
///    diagnostic log couldn't be written" as if it were a real failure.
///    This type honors that at the implementation level too: every
///    filesystem operation inside `write(line:)` is wrapped in its own
///    `do`/`catch`, and a failure is recorded only in `lastFailureReason`
///    (inspectable for diagnostics and tests) — never thrown, never
///    logged by crashing, never retried in a way that could cascade.
/// 3. **"Local rotation, a reasonable retention window"**
///    (`GUI Architecture Specification.md` §15). Standard, unremarkable
///    numbered-backup rotation: once the current log file would exceed
///    `maximumLogFileSizeBytes`, it is renamed to `<name>.1`, any existing
///    `<name>.1..N-1` shift up by one, anything beyond
///    `maximumRotatedFileCount` is deleted, and a fresh, empty current log
///    file is started. Both thresholds are configuration, not hardcoded
///    constants — this design phase's documents describe the requirement
///    ("a reasonable retention window") without naming specific numbers,
///    so the specific figures are a tunable default here, not a
///    rediscovered architectural decision.
///
/// An `actor`, unlike the four read-only artifact readers: this type has
/// real mutable state (`lastFailureReason`) and performs writes that must
/// be serialized against each other — two concurrent log calls must not
/// interleave their rotation checks and produce a corrupted rotation.
public actor FileGUILogger: GUILogger {
    public struct Configuration: Sendable {
        public let logDirectoryURL: URL
        public let currentLogFilename: String
        public let maximumLogFileSizeBytes: Int
        public let maximumRotatedFileCount: Int

        public init(
            logDirectoryURL: URL,
            currentLogFilename: String = "gui.log",
            maximumLogFileSizeBytes: Int = 5 * 1024 * 1024,
            maximumRotatedFileCount: Int = 5
        ) {
            self.logDirectoryURL = logDirectoryURL
            self.currentLogFilename = currentLogFilename
            self.maximumLogFileSizeBytes = maximumLogFileSizeBytes
            self.maximumRotatedFileCount = maximumRotatedFileCount
        }
    }

    private let configuration: Configuration
    private let dateFormatter: ISO8601DateFormatter

    /// The reason the most recent write attempt failed, if it did. `nil`
    /// after any successful write. Exists purely for diagnostics and
    /// tests — no part of this package's own behavior branches on it.
    public private(set) var lastFailureReason: String?

    public init(configuration: Configuration) {
        self.configuration = configuration
        self.dateFormatter = ISO8601DateFormatter()
    }

    private var currentLogFileURL: URL {
        configuration.logDirectoryURL.appendingPathComponent(configuration.currentLogFilename)
    }

    private func rotatedLogFileURL(index: Int) -> URL {
        configuration.logDirectoryURL
            .appendingPathComponent("\(configuration.currentLogFilename).\(index)")
    }

    // MARK: - GUILogger

    public func log(result: CommandResult) async {
        let summary = "command=\(result.command) exitCode=\(result.exitCode) outcome=\(result.outcome) " +
            "stdoutBytes=\(result.standardOutput.utf8.count) stderrBytes=\(result.standardError.utf8.count)"
        let level: GUILogLevel = result.succeeded ? .info : .warning
        write(level: level, message: summary)
    }

    // MARK: - General-purpose GUI diagnostic logging

    /// Records a shell-side diagnostic event that has nothing to do with a
    /// specific engine invocation — a UI-level error, an unexpected
    /// internal condition — per `Desktop Implementation Blueprint.md`
    /// §13's description of what the GUI log is for beyond just Engine
    /// Bridge results.
    public func log(_ message: String, level: GUILogLevel = .info) async {
        write(level: level, message: message)
    }

    // MARK: - Writing and rotation

    private func write(level: GUILogLevel, message: String) {
        let line = "[\(dateFormatter.string(from: Date()))] [\(level.rawValue)] \(message)\n"
        do {
            try ensureLogDirectoryExists()
            try rotateIfNeeded(forIncomingLine: line)
            try append(line: line)
            lastFailureReason = nil
        } catch {
            // Deliberately swallowed beyond this point: see the type-level
            // documentation above. A diagnostic log that can't be written
            // must never become a reason a real feature fails.
            lastFailureReason = String(describing: error)
        }
    }

    private func ensureLogDirectoryExists() throws {
        var isDirectory: ObjCBool = false
        let exists = FileManager.default.fileExists(
            atPath: configuration.logDirectoryURL.path,
            isDirectory: &isDirectory
        )
        if exists && !isDirectory.boolValue {
            throw GUILoggerError.logDirectoryPathIsNotADirectory(path: configuration.logDirectoryURL.path)
        }
        if !exists {
            try FileManager.default.createDirectory(
                at: configuration.logDirectoryURL,
                withIntermediateDirectories: true
            )
        }
    }

    private func append(line: String) throws {
        let data = Data(line.utf8)
        if FileManager.default.fileExists(atPath: currentLogFileURL.path) {
            let handle = try FileHandle(forWritingTo: currentLogFileURL)
            defer { try? handle.close() }
            try handle.seekToEnd()
            try handle.write(contentsOf: data)
        } else {
            try data.write(to: currentLogFileURL, options: .atomic)
        }
    }

    private func rotateIfNeeded(forIncomingLine line: String) throws {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: currentLogFileURL.path),
              let currentSize = attributes[.size] as? Int
        else {
            return // no current log file yet — nothing to rotate
        }

        guard currentSize + line.utf8.count > configuration.maximumLogFileSizeBytes else {
            return
        }

        let fileManager = FileManager.default

        if configuration.maximumRotatedFileCount < 1 {
            try fileManager.removeItem(at: currentLogFileURL)
            return
        }

        let oldestURL = rotatedLogFileURL(index: configuration.maximumRotatedFileCount)
        if fileManager.fileExists(atPath: oldestURL.path) {
            try fileManager.removeItem(at: oldestURL)
        }

        var index = configuration.maximumRotatedFileCount - 1
        while index >= 1 {
            let source = rotatedLogFileURL(index: index)
            let destination = rotatedLogFileURL(index: index + 1)
            if fileManager.fileExists(atPath: source.path) {
                try fileManager.moveItem(at: source, to: destination)
            }
            index -= 1
        }

        try fileManager.moveItem(at: currentLogFileURL, to: rotatedLogFileURL(index: 1))
    }
}

/// Errors specific to `FileGUILogger`'s own operation. Kept separate from
/// `EngineBridgeError` deliberately: this is a GUI-shell-only concern with
/// no relationship to engine artifacts, and per this type's own "never
/// becomes a source of truth" requirement, callers of `GUILogger.log`
/// never actually receive this type — it is only ever captured internally
/// into `lastFailureReason`, never thrown outward.
public enum GUILoggerError: Error, Equatable, Sendable {
    case logDirectoryPathIsNotADirectory(path: String)
}
