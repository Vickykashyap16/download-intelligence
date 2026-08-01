import EngineBridge

/// The read-through projection Review Queue renders — a pure, deterministic
/// computation over the engine's own metadata records, grouped into the two
/// tiers that ever appear here (`High-Fidelity UI Specification.md` §5):
/// "Needs your input" (`approval_required`, not yet executed) and "Flagged
/// for you" (`review_required`, which is never executed at all — left in
/// place and flagged, per `Rules/Confidence Rules.md`).
///
/// The `approval_required`/`status != "executed"` predicate is the same one
/// `HomeProjection.approvalRequiredPendingCount` and
/// `PreviewProjection.compute(records:)` already apply — this is not a new
/// rule invented here. `review_required` records are never filtered by
/// `status` at all, matching `HomeProjection.reviewRequiredCount`'s own
/// documented reasoning: such records are never executed, so every one of
/// them is always still pending review.
///
/// Kept separate from any view model so grouping/ordering/flag-reason
/// logic is unit-testable without an `EngineBridge`, a live window, or any
/// asynchronous code at all — the same separation every other screen's
/// projection type already establishes.
public struct ReviewQueueProjection: Equatable, Sendable {
    /// One "Needs your input" card's content (§5 Content Specification:
    /// filename, category, suggested destination, confidence chip, plus a
    /// Duplicate Status Badge alongside the tier chip when applicable — "not
    /// replacing it," §5 Edge Cases).
    public struct NeedsInputItem: Equatable, Sendable {
        public let fileID: String
        public let originalName: String
        public let suggestedName: String?
        public let suggestedDestination: String?
        public let category: Category?
        public let confidenceScore: Int?
        public let isDuplicate: Bool

        public init(
            fileID: String,
            originalName: String,
            suggestedName: String?,
            suggestedDestination: String?,
            category: Category?,
            confidenceScore: Int?,
            isDuplicate: Bool
        ) {
            self.fileID = fileID
            self.originalName = originalName
            self.suggestedName = suggestedName
            self.suggestedDestination = suggestedDestination
            self.category = category
            self.confidenceScore = confidenceScore
            self.isDuplicate = isDuplicate
        }
    }

    /// One "Flagged for you" card's content — no confidence score shown
    /// (Review Queue's tier chip for this group communicates tier alone;
    /// the flag reason is the substantive content), plus the same Duplicate
    /// Status Badge treatment as a Needs-input card.
    public struct FlaggedItem: Equatable, Sendable {
        public let fileID: String
        public let originalName: String
        public let category: Category?
        public let flagReason: String
        public let isDuplicate: Bool

        public init(
            fileID: String,
            originalName: String,
            category: Category?,
            flagReason: String,
            isDuplicate: Bool
        ) {
            self.fileID = fileID
            self.originalName = originalName
            self.category = category
            self.flagReason = flagReason
            self.isDuplicate = isDuplicate
        }
    }

    /// "Needs your input" first, "Flagged for you" second — the fixed
    /// order Wireframe screen 10 and §5's own "First attention" both
    /// specify. A group with no items is omitted entirely — never shown
    /// with a header and no cards (§5 Edge Cases: "Everything is
    /// review_required: the 'Needs your input' group is entirely absent").
    public let needsInputItems: [NeedsInputItem]
    public let flaggedItems: [FlaggedItem]

    /// Both groups empty — Review Queue itself routes to Home's caught-up
    /// state rather than rendering here at all (§5 States/Edge Cases), but
    /// this is still exposed so a view model can make that routing decision
    /// without re-deriving the same emptiness check.
    public var isEmpty: Bool { needsInputItems.isEmpty && flaggedItems.isEmpty }

    public init(needsInputItems: [NeedsInputItem], flaggedItems: [FlaggedItem]) {
        self.needsInputItems = needsInputItems
        self.flaggedItems = flaggedItems
    }

    /// Computes the projection from the engine's own records — no scope
    /// parameter, unlike `ScanCompleteProjection`: Review Queue is not tied
    /// to any one scan's baseline, the same reasoning `PreviewProjection`
    /// already establishes for Preview.
    public static func compute(records: [FileRecordSnapshot]) -> ReviewQueueProjection {
        let needsInputRecords = records.filter { $0.tier == .approvalRequired && $0.status != "executed" }
        let flaggedRecords = records.filter { $0.tier == .reviewRequired }

        let needsInputItems = Self.ordered(needsInputRecords).map { record in
            NeedsInputItem(
                fileID: record.fileID,
                originalName: record.originalName,
                suggestedName: record.suggestedName,
                suggestedDestination: record.suggestedDestination,
                category: record.category,
                confidenceScore: record.confidenceScore,
                isDuplicate: record.duplicateOf != nil
            )
        }

        let flaggedItems = Self.ordered(flaggedRecords).map { record in
            FlaggedItem(
                fileID: record.fileID,
                originalName: record.originalName,
                category: record.category,
                flagReason: FlagReasonResolver.resolve(for: record),
                isDuplicate: record.duplicateOf != nil
            )
        }

        return ReviewQueueProjection(needsInputItems: needsInputItems, flaggedItems: flaggedItems)
    }

    /// `discovered_at` ascending, `file_id` lexicographic as the final
    /// tie-break — the exact same deterministic order
    /// `score_confidence_batch()` itself already processes records in
    /// (`src/pipeline/confidence.py`), reused here rather than inventing a
    /// separate display order. `discoveredAt` is a real ISO 8601 string
    /// (`FileRecordSnapshot`'s own field type), which sorts correctly as a
    /// plain string comparison without needing to parse it into a `Date`
    /// first.
    private static func ordered(_ records: [FileRecordSnapshot]) -> [FileRecordSnapshot] {
        records.sorted { lhs, rhs in
            if lhs.discoveredAt != rhs.discoveredAt {
                return lhs.discoveredAt < rhs.discoveredAt
            }
            return lhs.fileID < rhs.fileID
        }
    }
}
