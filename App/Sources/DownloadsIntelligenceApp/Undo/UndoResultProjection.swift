import Foundation
import EngineBridge

/// The read-through projection Undo's result state renders — computed
/// exclusively from a post-invocation re-read of the action log, mirroring
/// `ExecuteResultProjection`'s own proven shape and reasoning (`WP-GUI-08`
/// Technical Notes: "as with Execute, the result must be populated only
/// from a post-invocation re-read of the action log, never assumed from
/// the button press").
///
/// Per-file outcome is determined independently for every file in the
/// confirmed batch (`Architecture Specification.md` §12's per-file error
/// isolation principle, reapplied here exactly as it was for Execute), so a
/// genuine restoration conflict — something now occupying a file's
/// original path — isolates to that file's row without failing the whole
/// undo (`WP-GUI-08` Acceptance Criteria). A file with no matching
/// action-log entry at all is treated as not restored, never assumed
/// complete — the same honest handling `ExecuteResultProjection` already
/// establishes for an interrupted mid-operation kill.
///
/// Kept separate from any view model so this arithmetic is unit-testable
/// without an `EngineBridge`, a live window, or any asynchronous code at
/// all — the same separation every other projection in this package
/// already establishes.
public struct UndoResultProjection: Equatable, Sendable {
    /// One successfully restored file.
    public struct RestoredRow: Equatable, Sendable {
        public let fileID: String
        public let originalName: String

        public init(fileID: String, originalName: String) {
            self.fileID = fileID
            self.originalName = originalName
        }
    }

    /// One file that did not end up restored — named and isolated, per §9
    /// States: "if a file can't be restored... this is surfaced
    /// specifically for that file within the result state."
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

    /// The exact count promised on the confirmation dialog ("This will move
    /// N files back...") — the size of the batch undo was attempted
    /// against.
    public let totalAttempted: Int
    public let restoredRows: [RestoredRow]
    public let problemRows: [ProblemRow]

    public var restoredCount: Int { restoredRows.count }

    /// "N files are back in Downloads, exactly as they were" (full success)
    /// vs. "N of M restored... see details" (partial) — §9 States.
    public var isFullSuccess: Bool { problemRows.isEmpty }

    public init(totalAttempted: Int, restoredRows: [RestoredRow], problemRows: [ProblemRow]) {
        self.totalAttempted = totalAttempted
        self.restoredRows = restoredRows
        self.problemRows = problemRows
    }

    /// The real action-log vocabulary this projection recognizes as a
    /// terminal outcome for one file's undo attempt
    /// (`src/pipeline/execution.py`'s `undo_single_action()`/`log_undo()`/
    /// `log_error()`): `undo` for a confirmed restoration, `error` for
    /// every one of `undo_single_action()`'s own failure branches
    /// (`SKIPPED_COLLISION`, `SKIPPED_MISSING`, `FAILED`, `SKIPPED_NO_RECORD`
    /// all route through `log_error()`).
    private static let successActions: Set<String> = ["undo"]
    private static let failureActions: Set<String> = ["error"]

    /// Computes the projection from the confirmed batch (the exact files
    /// `ExecuteResultProjection` reported as filed, captured before
    /// invoking the engine's `undo` command) and a fresh, post-invocation
    /// action-log read.
    ///
    /// For each confirmed file, every action-log entry matching its
    /// `fileID` and one of `successActions`/`failureActions` is
    /// considered, and the **last** such entry is taken as that file's
    /// outcome — the exact same "log is append-only, oldest-first, last
    /// match wins" reconciliation `ExecuteResultProjection.compute(_:_:)`
    /// already establishes and `src/main.py`'s own
    /// `_read_execution_log_actions()` independently confirms as the
    /// engine's own convention.
    public static func compute(
        confirmedRows: [ExecuteResultProjection.FiledRow],
        actionLogEntries: [ActionLogEntry]
    ) -> UndoResultProjection {
        let confirmedFileIDs = Set(confirmedRows.map(\.fileID))
        let relevantActions = successActions.union(failureActions)

        var lastRelevantEntryByFileID: [String: ActionLogEntry] = [:]
        for entry in actionLogEntries where confirmedFileIDs.contains(entry.fileID) && relevantActions.contains(entry.action) {
            lastRelevantEntryByFileID[entry.fileID] = entry
        }

        var restoredRows: [RestoredRow] = []
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
                restoredRows.append(RestoredRow(fileID: row.fileID, originalName: row.originalName))
            } else {
                problemRows.append(ProblemRow(fileID: row.fileID, originalName: row.originalName, reason: reason(for: entry)))
            }
        }

        return UndoResultProjection(totalAttempted: confirmedRows.count, restoredRows: restoredRows, problemRows: problemRows)
    }

    /// Extracts a plain-language reason from a failing entry's own
    /// `details`. Every `error` entry `undo_single_action()` can write
    /// carries `error_detail` (`log_error()`'s own required parameter,
    /// reused unmodified from Module 07 WP-6) — the same field
    /// `ExecuteResultProjection.reason(for:)` already reads for Execute's
    /// own `error` entries. Falls back to a generic, honest label rather
    /// than guessing when it's absent.
    private static func reason(for entry: ActionLogEntry) -> String {
        if let detail = entry.details?["error_detail"]?.stringValue, !detail.isEmpty {
            return detail
        }
        return "Didn't restore — the engine reported an error."
    }
}
