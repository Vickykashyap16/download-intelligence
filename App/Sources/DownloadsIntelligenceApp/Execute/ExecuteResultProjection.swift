import Foundation
import EngineBridge

/// The read-through projection Execute's result state renders — computed
/// exclusively from a post-invocation re-read of the action log, never from
/// the subprocess exit code or the confirmation list alone (`WP-GUI-07`
/// Technical Notes: "The result must be populated only from a post-
/// invocation re-read of the action log — never from the subprocess exit
/// code alone"; `Desktop Implementation Blueprint.md` §5's Execute Response
/// flow: "a partial result... is only ever reported as partial if the
/// action log itself confirms that split").
///
/// Per-file outcome is determined independently for every file in the
/// confirmed batch, satisfying `Architecture Specification.md` §12's
/// per-file error isolation principle and this work package's own
/// Acceptance Criteria ("a fixture file deliberately deleted between scan
/// and execute is reported as a skipped, per-file failure without
/// affecting the rest of the batch"). A file with no matching action-log
/// entry at all — the honest, unresolved case a mid-execute interruption
/// can leave behind (`Desktop Implementation Blueprint.md` §8,
/// "Interrupted execute") — is treated as not filed, never assumed
/// complete.
///
/// Kept separate from any view model so this arithmetic is unit-testable
/// without an `EngineBridge`, a live window, or any asynchronous code at
/// all — the same separation every other projection in this package
/// already establishes.
public struct ExecuteResultProjection: Equatable, Sendable {
    /// One successfully filed file — its real, verified destination, taken
    /// from the action log entry's own `to` field wherever present (the
    /// authoritative, post-write path the engine itself recorded), falling
    /// back to the pre-execute `suggestedDestination` only when `to` is
    /// missing from an otherwise-successful entry.
    public struct FiledRow: Equatable, Sendable {
        public let fileID: String
        public let originalName: String
        public let destinationFolder: String?

        public init(fileID: String, originalName: String, destinationFolder: String?) {
            self.fileID = fileID
            self.originalName = originalName
            self.destinationFolder = destinationFolder
        }
    }

    /// One file that did not end up filed — named and isolated, per §8's
    /// "Error: partial failure... represented as 'N of M filed' with the
    /// specific failed files named."
    public struct ProblemRow: Equatable, Sendable {
        public let fileID: String
        public let originalName: String
        public let reason: String

        public init(fileID: String, originalName: String, reason: String) {
            self.fileID = fileID
            self.originalName = originalName
            self.reason = reason
        }
    }

    /// One destination folder's filed-file count, for the result screen's
    /// per-destination-folder breakdown (§8 Content Specification:
    /// "Supporting text (result): per-destination-folder counts"). Sorted
    /// by descending count, folder name as the tie-break — the same
    /// determinism rule `ScanCompleteProjection.categoryBreakdown` already
    /// applies to its own breakdown.
    public struct DestinationBreakdown: Equatable, Sendable {
        public let destinationFolder: String
        public let count: Int

        public init(destinationFolder: String, count: Int) {
            self.destinationFolder = destinationFolder
            self.count = count
        }
    }

    /// The exact count promised on the confirmation screen — "the count
    /// should visibly match, closing the loop" (`Wireframes — MVP.md`
    /// screen 13, annotation 1).
    public let totalAttempted: Int
    public let filedRows: [FiledRow]
    public let problemRows: [ProblemRow]
    public let destinationBreakdown: [DestinationBreakdown]

    public var filedCount: Int { filedRows.count }

    /// "N files filed" (full success) vs. "N of M filed" (partial failure)
    /// — §8 States: "Error: partial failure... represented as 'N of M
    /// filed.'"
    public var isFullSuccess: Bool { problemRows.isEmpty }

    public init(
        totalAttempted: Int,
        filedRows: [FiledRow],
        problemRows: [ProblemRow],
        destinationBreakdown: [DestinationBreakdown]
    ) {
        self.totalAttempted = totalAttempted
        self.filedRows = filedRows
        self.problemRows = problemRows
        self.destinationBreakdown = destinationBreakdown
    }

    /// The real action-log vocabulary this projection recognizes as a
    /// terminal outcome for one file's execute attempt
    /// (`ActionLogEntry.action`'s documented open-ended values,
    /// `src/pipeline/execution.py`): the three successful-filing actions,
    /// plus `error` (the real action `_log_error()` writes, `details:
    /// {"error_detail": ...}`) and `skip` (recognized defensively, for
    /// forward compatibility, even though a record that already reached
    /// `tier == .auto` would not normally carry a Module 01-era `skip`
    /// entry from this batch).
    private static let successActions: Set<String> = ["move_rename", "archive_duplicate", "archive_superseded_version"]
    private static let failureActions: Set<String> = ["error", "skip"]

    /// Computes the projection from the confirmed batch (the exact rows
    /// shown on the confirmation screen, captured immediately before
    /// invoking the engine) and a fresh, post-invocation action-log read.
    ///
    /// For each confirmed file, every action-log entry matching its
    /// `fileID` and one of `successActions`/`failureActions` is
    /// considered, and the **last** such entry (the log is append-only,
    /// oldest-first, so the last matching entry is the most recent) is
    /// taken as that file's outcome — mirroring `src/main.py`'s own
    /// `_read_execution_log_actions()` "last action wins" semantics for
    /// exactly this same reconciliation problem. A confirmed file with no
    /// matching entry at all is treated as not filed, its reason recorded
    /// honestly as unresolved rather than guessed.
    public static func compute(
        confirmedRows: [ExecuteConfirmationProjection.FileRow],
        actionLogEntries: [ActionLogEntry]
    ) -> ExecuteResultProjection {
        let confirmedFileIDs = Set(confirmedRows.map(\.fileID))
        let relevantActions = successActions.union(failureActions)

        var lastRelevantEntryByFileID: [String: ActionLogEntry] = [:]
        for entry in actionLogEntries where confirmedFileIDs.contains(entry.fileID) && relevantActions.contains(entry.action) {
            // Overwriting on every matching iteration, in log order, means
            // the final value left in the dictionary is the last (most
            // recent) matching entry for that file — no separate sort step
            // needed, since `entries` is already oldest-first.
            lastRelevantEntryByFileID[entry.fileID] = entry
        }

        var filedRows: [FiledRow] = []
        var problemRows: [ProblemRow] = []

        for row in confirmedRows {
            guard let entry = lastRelevantEntryByFileID[row.fileID] else {
                problemRows.append(
                    ProblemRow(
                        fileID: row.fileID,
                        originalName: row.originalName,
                        reason: "Didn't complete — check History for the current status."
                    )
                )
                continue
            }

            if successActions.contains(entry.action) {
                let destination = folderDisplayName(fromPath: entry.to) ?? folderDisplayName(fromPath: row.suggestedDestination)
                filedRows.append(FiledRow(fileID: row.fileID, originalName: row.originalName, destinationFolder: destination))
            } else {
                problemRows.append(
                    ProblemRow(fileID: row.fileID, originalName: row.originalName, reason: reason(for: entry))
                )
            }
        }

        let breakdownCounts = Dictionary(grouping: filedRows.compactMap(\.destinationFolder), by: { $0 })
            .mapValues(\.count)
        let destinationBreakdown = breakdownCounts
            .map { DestinationBreakdown(destinationFolder: $0.key, count: $0.value) }
            .sorted { lhs, rhs in
                lhs.count != rhs.count ? lhs.count > rhs.count : lhs.destinationFolder < rhs.destinationFolder
            }

        return ExecuteResultProjection(
            totalAttempted: confirmedRows.count,
            filedRows: filedRows,
            problemRows: problemRows,
            destinationBreakdown: destinationBreakdown
        )
    }

    /// Extracts a plain-language reason from a failing entry's own
    /// `details`. `error` entries carry `error_detail`
    /// (`src/pipeline/execution.py`'s `_log_error()`); `skip` entries, if
    /// ever encountered here, carry `reason`
    /// (`src/pipeline/watch_ingest.py`'s own `skip` logging shape, reused
    /// defensively). Falls back to a generic, honest label rather than
    /// guessing when neither key is present.
    private static func reason(for entry: ActionLogEntry) -> String {
        if let detail = entry.details?["error_detail"]?.stringValue, !detail.isEmpty {
            return detail
        }
        if let detail = entry.details?["reason"]?.stringValue, !detail.isEmpty {
            return detail
        }
        return entry.action == "skip" ? "Skipped." : "Didn't file — the engine reported an error."
    }

    /// Derives a display-ready folder name from either shape this package
    /// encounters: a real written path (`entry.to`, e.g.
    /// `".../Finance/2026-07-19_Acme_Invoice.pdf"`) or the pre-execute
    /// `suggested_destination` folder path (`src/pipeline/naming.py`'s
    /// `resolve_destination()`, e.g. `"Finance/"` or
    /// `"Archive/Duplicates/"`). Both are handled by the same trailing-
    /// component extraction — never a category→folder mapping invented at
    /// this layer, only mechanical parsing of a path the engine itself
    /// already produced.
    private static func folderDisplayName(fromPath path: String?) -> String? {
        guard let path, !path.isEmpty else { return nil }
        let trimmed = path.hasSuffix("/") ? String(path.dropLast()) : path
        guard !trimmed.isEmpty else { return nil }

        // A written file path (`entry.to`) names the file itself, so the
        // folder is one path component up; a destination-folder path
        // (`suggestedDestination`) already names the folder directly. To
        // handle both without knowing which shape was passed, the
        // heuristic is: if the last path component looks like a filename
        // (contains a `.` after the first character, ruling out dotfiles),
        // treat it as a written file path and step up one component;
        // otherwise the last component is already the folder name.
        let lastComponent = (trimmed as NSString).lastPathComponent
        let looksLikeFilename = lastComponent.dropFirst().contains(".")
        let folderPath = looksLikeFilename ? (trimmed as NSString).deletingLastPathComponent : trimmed
        let folderName = (folderPath as NSString).lastPathComponent
        return folderName.isEmpty ? nil : folderName
    }
}
