import Foundation

/// Reads `Runtime/Logs/action_log.jsonl` — the sole, authoritative record
/// of business actions (`src/storage/runtime_io.py`'s
/// `read_action_log_entries()`) — exactly as it exists on disk today: one
/// JSON object per line, newline-delimited, oldest entries first.
///
/// Not an actor, for the same reason as `MetadataStoreReader`: no mutable
/// state, a single synchronous file read per call.
public struct ActionLogReader: Sendable {
    private let locations: EngineArtifactLocations

    public init(locations: EngineArtifactLocations) {
        self.locations = locations
    }

    /// Reads and parses the action log.
    ///
    /// A missing file returns an empty result — `entries: []`,
    /// `issues: []` — exactly matching the real engine's own
    /// `read_action_log_entries()`, which is explicitly documented to
    /// return an empty list rather than raise when the log doesn't exist
    /// yet (a fresh installation that has never executed a batch). This
    /// reader mirrors that real behavior rather than inventing a stricter
    /// one of its own.
    ///
    /// A line that isn't valid JSON, or that's valid JSON but missing a
    /// required field, is recorded in `issues` and skipped — it does not
    /// fail the whole read. This matters concretely for a real, append-only
    /// log: if the engine process were ever interrupted mid-write, the
    /// last line could in principle be truncated, and that must never make
    /// every earlier, complete entry unreadable.
    public func read() throws -> ActionLogReadResult {
        let url = locations.actionLogURL

        guard FileManager.default.fileExists(atPath: url.path) else {
            return ActionLogReadResult(entries: [], issues: [])
        }

        let contents: String
        do {
            contents = try String(contentsOf: url, encoding: .utf8)
        } catch {
            throw EngineBridgeError.artifactUnreadable(path: url.path, reason: String(describing: error))
        }

        var entries: [ActionLogEntry] = []
        var issues: [ArtifactParseIssue] = []
        let decoder = JSONDecoder()

        let lines = contents.split(separator: "\n", omittingEmptySubsequences: false)
        for (zeroBasedIndex, rawLine) in lines.enumerated() {
            let lineNumber = zeroBasedIndex + 1
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            // Blank lines (including a trailing newline's empty final
            // "line") are not evidence of anything and are silently
            // skipped — they are not a parse issue, just normal file
            // formatting.
            guard !line.isEmpty else { continue }

            guard let lineData = line.data(using: .utf8) else {
                issues.append(
                    ArtifactParseIssue(index: lineNumber, rawContent: line, reason: "line is not valid UTF-8")
                )
                continue
            }

            do {
                let entry = try decoder.decode(ActionLogEntry.self, from: lineData)
                entries.append(entry)
            } catch {
                issues.append(
                    ArtifactParseIssue(index: lineNumber, rawContent: line, reason: String(describing: error))
                )
            }
        }

        return ActionLogReadResult(entries: entries, issues: issues)
    }
}

/// The result of one `ActionLogReader.read()` call: every successfully
/// parsed entry, in file order, plus every individually-unparseable line
/// encountered along the way.
public struct ActionLogReadResult: Equatable, Sendable {
    public let entries: [ActionLogEntry]
    public let issues: [ArtifactParseIssue]

    public init(entries: [ActionLogEntry], issues: [ArtifactParseIssue]) {
        self.entries = entries
        self.issues = issues
    }
}
