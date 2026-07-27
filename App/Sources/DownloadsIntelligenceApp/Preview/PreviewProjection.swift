import EngineBridge

/// The read-through projection Preview renders — a pure, deterministic
/// computation over the engine's own metadata records, restricted to every
/// record the engine has ever classified but not yet filed (`tier != nil`
/// and `status != "executed"`), never a single scan's own scope.
///
/// This is the key difference from `ScanCompleteProjection`, whose `scope`
/// parameter restricts counting to exactly the file set one particular scan
/// was responsible for (`GUI Engineering Work Packages.md`, WP-GUI-05
/// Technical Notes: Preview "reuses Scan Complete's proven data model" for
/// the tier-grouping and zero-row-omission arithmetic itself, but is not
/// tied to any one scan's baseline the way Scan Progress/Scan Complete are
/// — a plan persists and remains reviewable across any number of visits,
/// regardless of which scan produced each individual record). The
/// "unfiled" predicate this type applies (`tier != nil && status !=
/// "executed"`) is not a new rule invented here — it is the exact same
/// predicate `HomeProjection` already uses twice (`needsReviewCount`,
/// `readyToFileCount`) to decide which records still need action.
///
/// Unlike `ScanCompleteProjection`, this type carries individual files, not
/// just per-tier counts: `High-Fidelity UI Specification.md` §7 is explicit
/// that Preview's content is "compact File Rows... full before → after
/// filename/destination per row, since this is explicitly the 'show
/// everything' screen" — Scan Complete's aggregate-counts-only model is
/// deliberately not sufficient here.
///
/// Kept separate from any view model so this arithmetic is unit-testable
/// without an `EngineBridge`, a live window, or any asynchronous code at
/// all — the same separation `ScanCompleteProjection` and `HomeProjection`
/// already establish.
public struct PreviewProjection: Equatable, Sendable {
    /// One pending file's full before/after detail, per `High-Fidelity UI
    /// Specification.md` §7 Content Specification ("full before → after
    /// filename/destination per row") and Component Usage ("Confidence
    /// Chip... one per File Row, in compact form (tier + score)").
    public struct FileRow: Equatable, Sendable {
        public let fileID: String
        public let originalName: String
        public let suggestedName: String?
        public let suggestedDestination: String?
        public let tier: Tier
        public let confidenceScore: Int?

        public init(
            fileID: String,
            originalName: String,
            suggestedName: String?,
            suggestedDestination: String?,
            tier: Tier,
            confidenceScore: Int?
        ) {
            self.fileID = fileID
            self.originalName = originalName
            self.suggestedName = suggestedName
            self.suggestedDestination = suggestedDestination
            self.tier = tier
            self.confidenceScore = confidenceScore
        }
    }

    /// One tier's full section: its rows, in a stable, deterministic order
    /// (by `originalName`, `fileID` as the tie-break, so re-rendering the
    /// same data never visibly reshuffles — the same determinism guarantee
    /// `ScanCompleteProjection.categoryBreakdown`'s own sort provides).
    /// Per §7's zero-row-omission rule, a tier with no pending records
    /// never produces a `TierSection` at all — never an empty section.
    public struct TierSection: Equatable, Sendable {
        public let tier: Tier
        public let rows: [FileRow]

        public var count: Int { rows.count }

        public init(tier: Tier, rows: [FileRow]) {
            self.tier = tier
            self.rows = rows
        }
    }

    /// The two distinct empty variants Preview must distinguish
    /// (`High-Fidelity UI Specification.md` §15: "Preview — Nothing Yet"
    /// vs. "Preview — Already Filed" — two different messages, not one
    /// generic "nothing to show"), plus the populated state.
    ///
    /// `.nothingScannedYet`: no record has ever been classified at all — no
    /// scan has produced a plan yet.
    /// `.allFiled`: classified records exist, but every one has already
    /// been executed — there was a plan once, and it's now fully filed.
    /// `.hasPlan`: at least one classified, not-yet-executed record exists.
    public enum Kind: Equatable, Sendable {
        case nothingScannedYet
        case allFiled
        case hasPlan
    }

    public let kind: Kind

    /// The count of records currently pending — classified but not yet
    /// filed. Zero in both empty-state variants.
    public let totalFilesPending: Int

    /// Fixed order — auto, approval required, review required, matching
    /// `ScanCompleteProjection`'s own fixed order — with zero-row tiers
    /// omitted entirely, never shown as an empty section.
    public let tierSections: [TierSection]

    /// The auto-tier pending count to substitute into "Execute now" —
    /// `nil` (button omitted entirely, not shown disabled or at zero) when
    /// there is nothing to file, per §7 Edge Cases: "Everything is
    /// review_required... the 'Execute now' Primary Button is omitted
    /// since there is nothing to file." Mirrors
    /// `ScanCompleteProjection.primaryActionAutoCount` exactly.
    public let primaryActionAutoCount: Int?

    public init(
        kind: Kind,
        totalFilesPending: Int,
        tierSections: [TierSection],
        primaryActionAutoCount: Int?
    ) {
        self.kind = kind
        self.totalFilesPending = totalFilesPending
        self.tierSections = tierSections
        self.primaryActionAutoCount = primaryActionAutoCount
    }

    private static let orderedTiers: [Tier] = [.auto, .approvalRequired, .reviewRequired]

    /// Computes the projection from the engine's own records. Unlike
    /// `ScanCompleteProjection.compute(records:scope:)`, this takes no
    /// `scope` parameter — Preview derives its own scope internally, as
    /// "every currently unfiled, classified record," from a fresh read of
    /// the whole metadata store. Callers (`PreviewViewModel`) are expected
    /// to pass `MetadataStoreReadResult.records` taken from a read no older
    /// than the current screen visit — never a value carried over from a
    /// previous visit or another screen — per `GUI Architecture
    /// Specification.md` §7's "always re-read, never trust a cache."
    ///
    /// Deliberately out of scope for this pass, per §7's own "if the list
    /// is long" framing (a tertiary refinement, not the core content
    /// requirement): per-tier category sub-grouping, and section
    /// collapse/expand (§7 States: "defaults to expanded so nothing is
    /// hidden by default" — always-expanded already satisfies that
    /// acceptance criterion without needing collapse/expand interaction at
    /// all).
    public static func compute(records: [FileRecordSnapshot]) -> PreviewProjection {
        let classified = records.filter { $0.tier != nil }
        guard !classified.isEmpty else {
            return PreviewProjection(kind: .nothingScannedYet, totalFilesPending: 0, tierSections: [], primaryActionAutoCount: nil)
        }

        let pending = classified.filter { $0.status != "executed" }
        guard !pending.isEmpty else {
            return PreviewProjection(kind: .allFiled, totalFilesPending: 0, tierSections: [], primaryActionAutoCount: nil)
        }

        let byTier = Dictionary(grouping: pending, by: { $0.tier! })

        let tierSections = orderedTiers.compactMap { tier -> TierSection? in
            guard let recordsForTier = byTier[tier], !recordsForTier.isEmpty else { return nil }
            let rows = recordsForTier
                .map { record in
                    FileRow(
                        fileID: record.fileID,
                        originalName: record.originalName,
                        suggestedName: record.suggestedName,
                        suggestedDestination: record.suggestedDestination,
                        tier: tier,
                        confidenceScore: record.confidenceScore
                    )
                }
                .sorted { lhs, rhs in
                    lhs.originalName != rhs.originalName
                        ? lhs.originalName.localizedStandardCompare(rhs.originalName) == .orderedAscending
                        : lhs.fileID < rhs.fileID
                }
            return TierSection(tier: tier, rows: rows)
        }

        let autoCount = byTier[.auto]?.count ?? 0

        return PreviewProjection(
            kind: .hasPlan,
            totalFilesPending: pending.count,
            tierSections: tierSections,
            primaryActionAutoCount: autoCount > 0 ? autoCount : nil
        )
    }
}
