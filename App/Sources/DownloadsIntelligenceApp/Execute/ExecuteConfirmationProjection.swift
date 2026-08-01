import EngineBridge

/// The read-through projection Execute's confirmation state renders — a
/// pure, deterministic computation over the engine's own metadata records,
/// restricted to exactly the auto-tier, not-yet-filed batch (`WP-GUI-07`
/// Technical Notes: "the confirmation screen must perform one more fresh
/// read before allowing 'File them'"; Scope: "In scope: Execute's
/// confirmation and result states"; `High-Fidelity UI Specification.md`
/// §8 Edge Cases: "Review required / Approval required: not applicable to
/// this screen — by definition, only auto-tier items reach Execute
/// directly").
///
/// Deliberately restricted to `tier == .auto` only — never mixing in
/// freshly-approved `approval_required` items from Review Queue, per
/// `Downloads Intelligence — UX Design/Open Dependencies.md` OD-GUI-3: the
/// engine's non-interactive `execute -y` invocation has no channel to
/// receive GUI-collected approval decisions today, so this package's own
/// scope is the engine's actual auto-tier execution set, exactly as
/// `execute -y` alone can honor it. OD-GUI-3 is a documented future engine
/// capability, not something this projection attempts to work around.
///
/// The "unfiled" predicate (`tier != nil && status != "executed"`) is the
/// exact same one `PreviewProjection.compute(records:)` already applies —
/// this projection's `.auto`-tier subset is precisely the same file set
/// `PreviewProjection.primaryActionAutoCount` counts and
/// `ScanCompleteProjection.primaryActionAutoCount` counts for a single
/// scan's scope, so the count shown here can never disagree with what
/// either of those screens already promised the user (`High-Fidelity UI
/// Specification.md` §4's own UX Acceptance Criterion, reapplied here).
///
/// Kept separate from any view model so this arithmetic is unit-testable
/// without an `EngineBridge`, a live window, or any asynchronous code at
/// all — the same separation `PreviewProjection`/`ScanCompleteProjection`
/// already establish.
public struct ExecuteConfirmationProjection: Equatable, Sendable {
    /// One pending file's full before/after detail, per `High-Fidelity UI
    /// Specification.md` §8 Content Specification ("full before → after
    /// filename/destination per row"). Deliberately carries no `tier` or
    /// `confidenceScore` — §8 Content Specification is explicit that
    /// "Confidence chips: not shown per-row in the confirmation list at
    /// MVP scope... this list is specifically the already-auto-tier
    /// batch, so tier is already implied and would be redundant per row."
    public struct FileRow: Equatable, Sendable {
        public let fileID: String
        public let originalName: String
        public let suggestedName: String?
        public let suggestedDestination: String?

        public init(
            fileID: String,
            originalName: String,
            suggestedName: String?,
            suggestedDestination: String?
        ) {
            self.fileID = fileID
            self.originalName = originalName
            self.suggestedName = suggestedName
            self.suggestedDestination = suggestedDestination
        }
    }

    /// In a stable, deterministic order (by `originalName`, `fileID` as the
    /// tie-break) — the same ordering rule `PreviewProjection.TierSection`
    /// already applies to its own rows, so re-rendering the same data never
    /// visibly reshuffles.
    public let fileRows: [FileRow]

    public var totalCount: Int { fileRows.count }

    public init(fileRows: [FileRow]) {
        self.fileRows = fileRows
    }

    /// Computes the projection from the engine's own records. Callers
    /// (`ExecuteViewModel`) are expected to pass `MetadataStoreReadResult
    /// .records` taken from a read no older than the current screen visit
    /// — per `GUI Architecture Specification.md` §7's "always re-read,
    /// never trust a cache," and per this work package's own requirement
    /// that "File them" itself re-runs this computation against one more
    /// fresh read immediately before invoking the engine.
    public static func compute(records: [FileRecordSnapshot]) -> ExecuteConfirmationProjection {
        let eligible = records.filter { $0.tier == .auto && $0.status != "executed" }
        let rows = eligible
            .map { record in
                FileRow(
                    fileID: record.fileID,
                    originalName: record.originalName,
                    suggestedName: record.suggestedName,
                    suggestedDestination: record.suggestedDestination
                )
            }
            .sorted { lhs, rhs in
                lhs.originalName != rhs.originalName
                    ? lhs.originalName.localizedStandardCompare(rhs.originalName) == .orderedAscending
                    : lhs.fileID < rhs.fileID
            }
        return ExecuteConfirmationProjection(fileRows: rows)
    }
}
