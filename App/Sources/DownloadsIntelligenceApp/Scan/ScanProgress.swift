import EngineBridge

/// The pure state machine behind Scan Progress's own progress signal — kept
/// separate from `ScanViewModel` so its indeterminate→determinate
/// transition and "checked N of M" arithmetic are unit-testable without an
/// `EngineBridge`, a live subprocess, or any asynchronous code at all, the
/// same separation `HomeProjection` already establishes for Home.
///
/// This type resolves Finding 4 (WP-GUI-04's pre-implementation analysis,
/// confirmed by direct reading of `classify_batch()`, `extract_metadata_batch()`,
/// `detect_duplicates_batch()`, `suggest_naming_and_destination_batch()`, and
/// `score_confidence_batch()`):
///
/// - `scan()` appends every newly discovered record in a single burst, only
///   *after* its whole-directory walk finishes — there is no signal to
///   observe while that walk is in progress. This type stays
///   `.indeterminate` for exactly as long as that is true.
/// - No stage after `scan()` ever introduces a new `file_id` — every later
///   stage only mutates fields on records that already exist
///   (`save_file_record`'s upsert-by-`file_id` contract). That fact is what
///   makes it safe to treat "the total record set is definitely final" as
///   knowable from a real signal (see `next(records:)` below) rather than a
///   guess about timing.
/// - `tier` is the one field only the pipeline's *last* stage
///   (`score_confidence`) ever sets, and it is always a real, non-`nil`
///   value once set — unlike `extractedMetadata` (legitimately empty even
///   after successful extraction) or `duplicateOf`/`versionGroupID`
///   (legitimately `nil` forever for a non-duplicate file). That makes
///   `tier != nil` the one unambiguous "this record is fully through the
///   run pipeline" marker.
///
/// No timer, no fixed delay, no simulated percentage is used anywhere in
/// this type — every transition is a direct, provable consequence of an
/// actual `readMetadataStore()` poll, per the Work Packages' explicit ban
/// on inventing progress before a real signal exists.
public struct ScanProgress: Equatable, Sendable {
    public enum Phase: Equatable, Sendable {
        case indeterminate
        case determinate(DeterminateProgress)
    }

    /// What the Scan Progress screen should render right now.
    public let phase: Phase

    // Internal bookkeeping, carried from one `next(records:)` call to the
    // next so this type never needs a clock, an actor, or any state outside
    // its own value — a pure fold over successive `readMetadataStore()`
    // results, exactly like `HomeProjection.compute(records:now:)`'s single-
    // snapshot computation, generalized to a sequence of snapshots.
    private let scopeIsKnown: Bool
    private let scopeFileIDs: Set<String>
    private let baselineFileIDs: Set<String>
    private let baselinePendingFileIDs: Set<String>
    private let baselineMarkerCount: Int

    private init(
        phase: Phase,
        scopeIsKnown: Bool,
        scopeFileIDs: Set<String>,
        baselineFileIDs: Set<String>,
        baselinePendingFileIDs: Set<String>,
        baselineMarkerCount: Int
    ) {
        self.phase = phase
        self.scopeIsKnown = scopeIsKnown
        self.scopeFileIDs = scopeFileIDs
        self.baselineFileIDs = baselineFileIDs
        self.baselinePendingFileIDs = baselinePendingFileIDs
        self.baselineMarkerCount = baselineMarkerCount
    }

    /// The starting state for a fresh scan. `baseline` must be a
    /// `readMetadataStore()` result taken immediately *before* invoking the
    /// `run` command, so records already fully processed by an earlier scan
    /// are never mistaken for this scan's own work, and so a record left
    /// pending by a previously interrupted run (crash-safety, `Desktop
    /// Implementation Blueprint.md` §9) is still correctly counted as part
    /// of this scan's scope.
    public static func starting(baseline: [FileRecordSnapshot]) -> ScanProgress {
        ScanProgress(
            phase: .indeterminate,
            scopeIsKnown: false,
            scopeFileIDs: [],
            baselineFileIDs: Set(baseline.map(\.fileID)),
            baselinePendingFileIDs: Set(baseline.filter { $0.tier == nil }.map(\.fileID)),
            baselineMarkerCount: Self.markerCount(baseline)
        )
    }

    /// Folds one fresh metadata-store poll into the previous state.
    ///
    /// The scope (the fixed denominator, `M`) becomes known the instant any
    /// record shows real forward movement on one of three fields that are
    /// each, on their own stage, always set to a real value on success and
    /// never legitimately cleared: `category` (Module 02), `suggestedName`
    /// (Module 05 — "always a real, non-empty string afterward... no
    /// legitimately stays null forever case exists here," per that module's
    /// own implementation), and `tier` (Module 06). Because `run`'s six
    /// stages execute strictly sequentially within one subprocess
    /// (`src/cli.py`'s `_cmd_run`), *any* one of those three fields
    /// advancing beyond its count at baseline is proof — not a guess —
    /// that `scan()` has already fully completed and appended its entire
    /// burst, since none of those three stages can run before `scan()`
    /// returns. At that exact moment, the current total record set is
    /// final, so scope can be fixed once and never revisited.
    ///
    /// `N` (completed) is the count of in-scope records that currently have
    /// `tier != nil`.
    public func next(records: [FileRecordSnapshot]) -> ScanProgress {
        guard !scopeIsKnown else {
            return ScanProgress(
                phase: Self.derivePhase(scope: scopeFileIDs, records: records),
                scopeIsKnown: true,
                scopeFileIDs: scopeFileIDs,
                baselineFileIDs: baselineFileIDs,
                baselinePendingFileIDs: baselinePendingFileIDs,
                baselineMarkerCount: baselineMarkerCount
            )
        }

        guard Self.markerCount(records) > baselineMarkerCount else {
            return ScanProgress(
                phase: .indeterminate,
                scopeIsKnown: false,
                scopeFileIDs: [],
                baselineFileIDs: baselineFileIDs,
                baselinePendingFileIDs: baselinePendingFileIDs,
                baselineMarkerCount: baselineMarkerCount
            )
        }

        let scope = Self.scope(baselineFileIDs: baselineFileIDs, baselinePendingFileIDs: baselinePendingFileIDs, currentRecords: records)
        return ScanProgress(
            phase: Self.derivePhase(scope: scope, records: records),
            scopeIsKnown: true,
            scopeFileIDs: scope,
            baselineFileIDs: baselineFileIDs,
            baselinePendingFileIDs: baselinePendingFileIDs,
            baselineMarkerCount: baselineMarkerCount
        )
    }

    /// The set of `file_id`s this scan is responsible for: every record
    /// already pending (untiered) at baseline, plus every record discovered
    /// for the first time since baseline. Shared with `ScanCompleteProjection`
    /// so Scan Complete's own "N files looked at" figure and tier breakdown
    /// are computed from the exact same scope, never a second, independently
    /// derived one.
    public static func scope(
        baselineFileIDs: Set<String>,
        baselinePendingFileIDs: Set<String>,
        currentRecords: [FileRecordSnapshot]
    ) -> Set<String> {
        let currentFileIDs = Set(currentRecords.map(\.fileID))
        let newlyDiscovered = currentFileIDs.subtracting(baselineFileIDs)
        return baselinePendingFileIDs.union(newlyDiscovered)
    }

    private static func markerCount(_ records: [FileRecordSnapshot]) -> Int {
        records.reduce(into: 0) { count, record in
            if record.category != nil { count += 1 }
            if record.suggestedName != nil { count += 1 }
            if record.tier != nil { count += 1 }
        }
    }

    private static func derivePhase(scope: Set<String>, records: [FileRecordSnapshot]) -> Phase {
        let completed = records.filter { scope.contains($0.fileID) && $0.tier != nil }.count
        return .determinate(DeterminateProgress(completed: completed, total: scope.count))
    }
}
