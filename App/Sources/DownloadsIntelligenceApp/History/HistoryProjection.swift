import Foundation
import EngineBridge

/// The read-through projection History renders — a pure, deterministic
/// computation over the engine's own action log and metadata store, with
/// no filesystem I/O of its own (`ExecuteResultProjection`/
/// `UndoResultProjection`'s own established pattern, reused here rather
/// than inventing a new one).
///
/// **What counts as "a batch" here.** `batch_id` (`src/pipeline/
/// watch_ingest.py`'s `make_batch_id()`) is assigned once, at discovery
/// time, and every subsequent action-log entry for that file — `discover`,
/// `classify`, `extract_metadata`, `detect_duplicates_and_versions`,
/// `suggest_naming_and_destination`, `score_confidence`, and eventually
/// `move_rename`/`archive_*`/`error`/`undo` — reuses that same `batch_id`
/// (confirmed directly: `execute_batch()`'s own docstring, "every record in
/// one `execute_batch()` call shares the same `batch_id`"; `undo_single_
/// action()`'s `log_undo()` call reuses `log_entry["batch_id"]`, the
/// *original* filing entry's own value). Grouping the action log by raw
/// `batchID` alone would therefore lump a file's entire pipeline journey —
/// scan through classification through scoring — into the same group as
/// its eventual filing, which is not what "batch" means anywhere else in
/// this product (Execute/Undo's own `batch` is specifically the set of
/// files filed together in one `execute` invocation).
///
/// This projection filters to the same execute/undo-relevant action
/// vocabulary `ExecuteResultProjection`/`UndoResultProjection` already
/// recognize (`move_rename`/`archive_duplicate`/`archive_superseded_
/// version`/`error`/`skip`/`undo`) *before* grouping by `batchID` — a
/// `batchID` with none of these (a scan session never yet executed) is
/// correctly excluded from History entirely, matching §10's own Empty
/// state ("Nothing filed yet") and Screen Purpose ("the record of
/// everything the product has ever done" — done, not merely scanned).
///
/// **What this projection deliberately does not do.** No filesystem
/// existence check for whether a historically-filed file is still where
/// the metadata store says it is (§10's "if a specific historical file's
/// current status can't be determined... noted plainly on that row") — an
/// I/O-free pure model has no way to perform that check itself without
/// breaking the same purity every other projection in this package relies
/// on for synchronous, fixture-free unit testing. Deliberately out of
/// scope for this pass; not silently dropped, disclosed here.
public struct HistoryProjection: Equatable, Sendable {
    /// One successfully filed file within a batch, as it was actually
    /// filed — `finalLocation` is the *original* filing entry's own `to`
    /// path, kept historically accurate even if the file was later undone
    /// or moved again (§10 Content Specification: "this is the one screen
    /// where full raw metadata is appropriate and expected, given its
    /// audit purpose"). `tier`/`confidenceScore` are read from the
    /// *current* metadata store record for this `fileID` — the same
    /// "current state, not a frozen historical snapshot" characteristic
    /// `UndoViewModel`'s own documentation already establishes as an
    /// accepted property of this architecture, not a defect.
    public struct FiledFileRow: Equatable, Sendable {
        public let fileID: String
        public let originalName: String
        public let finalLocation: String?
        public let tier: Tier?
        public let confidenceScore: Int?
        /// This file's own most recent status within *this batch* is an
        /// `undo` entry — reflected per §10 States: "Undo completed:
        /// reflected in the batch/file's history entry... so the record
        /// remains accurate and complete even after a reversal."
        public let wasUndone: Bool

        public init(fileID: String, originalName: String, finalLocation: String?, tier: Tier?, confidenceScore: Int?, wasUndone: Bool) {
            self.fileID = fileID
            self.originalName = originalName
            self.finalLocation = finalLocation
            self.tier = tier
            self.confidenceScore = confidenceScore
            self.wasUndone = wasUndone
        }
    }

    /// One file this batch attempted to file but couldn't — same shape and
    /// reasoning as `ExecuteResultProjection.ProblemRow`, surfaced here so
    /// a batch's own summary can honestly represent "N of M filed" rather
    /// than only ever showing successes (§10 Edge Cases: "a partially-
    /// completed batch is shown honestly as partial, never rounded up to
    /// 'complete'").
    public struct ProblemFileRow: Equatable, Sendable {
        public let fileID: String
        public let originalName: String
        public let reason: String

        public init(fileID: String, originalName: String, reason: String) {
            self.fileID = fileID
            self.originalName = originalName
            self.reason = reason
        }
    }

    /// One tier's count within a batch's summary (§10 Content
    /// Specification: "Labels: batch date/time, batch ID, per-tier counts
    /// within each batch summary"). Sorted by descending count, tier raw
    /// value as the tie-break — the same determinism rule every other
    /// breakdown in this package already applies.
    public struct TierCount: Equatable, Sendable {
        public let tier: Tier
        public let count: Int

        public init(tier: Tier, count: Int) {
            self.tier = tier
            self.count = count
        }
    }

    public struct Batch: Equatable, Sendable {
        public let batchID: String
        /// The batch's own display timestamp — the earliest filing-type
        /// entry's timestamp (when this batch was actually executed), not
        /// any later `undo` entry's timestamp, and not the file's original
        /// discovery time.
        public let timestamp: String
        public let filedRows: [FiledFileRow]
        public let problemRows: [ProblemFileRow]
        public let tierBreakdown: [TierCount]

        public var filedCount: Int { filedRows.count }
        public var totalAttempted: Int { filedRows.count + problemRows.count }

        /// §10 States' "already undone" marker — every filed file in this
        /// batch has since been undone.
        public var isFullyUndone: Bool { !filedRows.isEmpty && filedRows.allSatisfy(\.wasUndone) }
        /// Some, but not all, filed files in this batch have since been
        /// undone (e.g. a per-file restoration conflict left some files
        /// filed while the rest were successfully reversed).
        public var isPartiallyUndone: Bool { !isFullyUndone && filedRows.contains(where: \.wasUndone) }

        public init(batchID: String, timestamp: String, filedRows: [FiledFileRow], problemRows: [ProblemFileRow], tierBreakdown: [TierCount]) {
            self.batchID = batchID
            self.timestamp = timestamp
            self.filedRows = filedRows
            self.problemRows = problemRows
            self.tierBreakdown = tierBreakdown
        }
    }

    /// Most recent first (§10 Screen Hierarchy: "the list of past batches,
    /// most recent first").
    public let batches: [Batch]

    /// "Nothing filed yet" (§10 Empty state) — no batch has ever contained
    /// even one execute/undo-relevant action-log entry.
    public var isEmpty: Bool { batches.isEmpty }

    public init(batches: [Batch]) {
        self.batches = batches
    }

    /// The execute/undo-relevant action vocabulary this projection
    /// recognizes — identical to `ExecuteResultProjection`'s own
    /// `successActions`/`failureActions`, plus `"undo"` (which neither of
    /// those two projections needs to recognize, since Execute's own
    /// result never contains an `undo` entry and Undo's own result is
    /// already scoped to a single invocation's outcome rather than a
    /// batch's full history).
    private static let successActions: Set<String> = ["move_rename", "archive_duplicate", "archive_superseded_version"]
    private static let problemActions: Set<String> = ["error", "skip"]
    private static let undoAction = "undo"

    public static func compute(actionLogEntries: [ActionLogEntry], records: [FileRecordSnapshot]) -> HistoryProjection {
        let relevantActions = successActions.union(problemActions).union([undoAction])
        // Overwrite-based construction, not `Dictionary(uniqueKeysWithValues:)`
        // — a malformed metadata store with a duplicate `fileID` must never
        // crash this projection; it's tolerated the same way every other
        // "records by ID" lookup elsewhere in this package already is.
        var recordsByID: [String: FileRecordSnapshot] = [:]
        for record in records {
            recordsByID[record.fileID] = record
        }

        let relevantEntries = actionLogEntries.filter { relevantActions.contains($0.action) }
        let entriesByBatchID = Dictionary(grouping: relevantEntries, by: \.batchID)

        let batches: [Batch] = entriesByBatchID.compactMap { batchID, entries in
            Self.buildBatch(batchID: batchID, entries: entries, recordsByID: recordsByID)
        }

        let ordered = batches.sorted { lhs, rhs in
            lhs.timestamp != rhs.timestamp ? lhs.timestamp > rhs.timestamp : lhs.batchID > rhs.batchID
        }

        return HistoryProjection(batches: ordered)
    }

    private static func buildBatch(batchID: String, entries: [ActionLogEntry], recordsByID: [String: FileRecordSnapshot]) -> Batch? {
        // Last-matching-entry-wins per fileID, within this one batch —
        // the same append-only, oldest-first reconciliation
        // `ExecuteResultProjection`/`UndoResultProjection` already
        // establish, applied here per (batch, file) instead of globally
        // per file.
        var lastEntryByFileID: [String: ActionLogEntry] = [:]
        var earliestFilingTimestamp: String?
        for entry in entries {
            lastEntryByFileID[entry.fileID] = entry
            if successActions.contains(entry.action) {
                if earliestFilingTimestamp == nil || entry.timestamp < earliestFilingTimestamp! {
                    earliestFilingTimestamp = entry.timestamp
                }
            }
        }

        guard !lastEntryByFileID.isEmpty else { return nil }

        var filedRows: [FiledFileRow] = []
        var problemRows: [ProblemFileRow] = []

        for (fileID, entry) in lastEntryByFileID {
            let record = recordsByID[fileID]
            let originalName = record?.originalName ?? Self.fallbackName(fromPath: entry.from)

            if entry.action == undoAction {
                // Reconstruct this file's own filing entry (the one this
                // `undo` entry reversed) to still report where it was
                // filed to, per this type's own "historically accurate,
                // never silently dropped" documentation.
                let filingEntry = entries.first { $0.fileID == fileID && successActions.contains($0.action) }
                filedRows.append(
                    FiledFileRow(
                        fileID: fileID,
                        originalName: originalName,
                        finalLocation: filingEntry?.to,
                        tier: record?.tier,
                        confidenceScore: record?.confidenceScore,
                        wasUndone: true
                    )
                )
            } else if successActions.contains(entry.action) {
                filedRows.append(
                    FiledFileRow(
                        fileID: fileID,
                        originalName: originalName,
                        finalLocation: entry.to,
                        tier: record?.tier,
                        confidenceScore: record?.confidenceScore,
                        wasUndone: false
                    )
                )
            } else {
                problemRows.append(ProblemFileRow(fileID: fileID, originalName: originalName, reason: reason(for: entry)))
            }
        }

        filedRows.sort { $0.originalName != $1.originalName ? $0.originalName < $1.originalName : $0.fileID < $1.fileID }
        problemRows.sort { $0.originalName != $1.originalName ? $0.originalName < $1.originalName : $0.fileID < $1.fileID }

        let breakdownCounts = Dictionary(grouping: filedRows.compactMap(\.tier), by: { $0 }).mapValues(\.count)
        let tierBreakdown = breakdownCounts
            .map { TierCount(tier: $0.key, count: $0.value) }
            .sorted { lhs, rhs in
                lhs.count != rhs.count ? lhs.count > rhs.count : lhs.tier.rawValue < rhs.tier.rawValue
            }

        // A batch with only `undo`/`error` entries and no filing entry at
        // all (anomalous — every `undo` entry implies an earlier filing
        // entry existed in the same batch, and every real execute attempt
        // logs at least one entry) falls back to the earliest entry of any
        // kind, so a timestamp is always produced rather than the batch
        // being silently dropped.
        let timestamp = earliestFilingTimestamp ?? entries.map(\.timestamp).min() ?? ""

        return Batch(batchID: batchID, timestamp: timestamp, filedRows: filedRows, problemRows: problemRows, tierBreakdown: tierBreakdown)
    }

    /// Extracts a plain-language reason from a failing entry's own
    /// `details` — identical extraction logic to `ExecuteResultProjection.
    /// reason(for:)`, reused rather than re-derived.
    private static func reason(for entry: ActionLogEntry) -> String {
        if let detail = entry.details?["error_detail"]?.stringValue, !detail.isEmpty {
            return detail
        }
        if let detail = entry.details?["reason"]?.stringValue, !detail.isEmpty {
            return detail
        }
        return entry.action == "skip" ? "Skipped." : "Didn't file — the engine reported an error."
    }

    /// A display-ready name derived from a raw path, used only when no
    /// metadata store record exists for this `fileID` — an anomalous,
    /// defensive fallback (mirrors `ExecuteResultProjection`'s own
    /// "always show something honest, never omit the row" precedent).
    private static func fallbackName(fromPath path: String?) -> String {
        guard let path, !path.isEmpty else { return "Unknown file" }
        return (path as NSString).lastPathComponent
    }
}
