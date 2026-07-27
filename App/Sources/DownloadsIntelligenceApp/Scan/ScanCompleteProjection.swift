import EngineBridge

/// The read-through projection Scan Complete renders — a pure, deterministic
/// computation over the engine's own metadata records, restricted to
/// exactly the file set this scan was responsible for (`ScanProgress.scope`,
/// never the whole, cumulative, all-time metadata store — a re-scan must
/// never re-report files a previous scan already showed). Kept separate
/// from any view model so the tier/category arithmetic is unit-testable
/// without an `EngineBridge`, a live window, or any asynchronous code at
/// all, the same separation `HomeProjection` already establishes for Home.
public struct ScanCompleteProjection: Equatable, Sendable {
    public struct TierRow: Equatable, Sendable {
        public let tier: Tier
        public let count: Int
    }

    public struct CategoryRow: Equatable, Sendable {
        public let category: Category
        public let count: Int
    }

    /// "Scan complete — N files looked at" (`High-Fidelity UI
    /// Specification.md` §4, Content Specification) — the count of files
    /// *this* scan was responsible for, not the cumulative store size.
    public let totalFilesLookedAt: Int

    /// Fixed order — auto, approval required, review required
    /// (`High-Fidelity UI Specification.md` §4: "in that fixed order") —
    /// with zero-count tiers omitted entirely, never shown as a zero row
    /// (§4's explicit "zero-row-omission rule").
    public let tierRows: [TierRow]

    /// Deterministic order (descending count, category raw value as the
    /// tie-break) so re-rendering the same data never visibly reshuffles.
    public let categoryBreakdown: [CategoryRow]

    /// The auto-tier count to substitute into "File the N now" — `nil`
    /// (button omitted entirely, not shown disabled or at zero) when there
    /// is nothing to file, per §4's "Everything is review_required... the
    /// Primary Button... is omitted entirely since there is nothing to
    /// file."
    public let primaryActionAutoCount: Int?

    /// "No files found to sort" — the zero-files-looked-at Empty state
    /// (§4, States: "a distinct message state... replacing the tier-group
    /// content entirely").
    public var isEmpty: Bool { totalFilesLookedAt == 0 }

    public init(
        totalFilesLookedAt: Int,
        tierRows: [TierRow],
        categoryBreakdown: [CategoryRow],
        primaryActionAutoCount: Int?
    ) {
        self.totalFilesLookedAt = totalFilesLookedAt
        self.tierRows = tierRows
        self.categoryBreakdown = categoryBreakdown
        self.primaryActionAutoCount = primaryActionAutoCount
    }

    private static let orderedTiers: [Tier] = [.auto, .approvalRequired, .reviewRequired]

    /// Computes the projection from the engine's own records, restricted to
    /// `scope` — the exact same file-ID set `ScanProgress` tracked
    /// throughout this scan (`ScanProgress.scope(baselineFileIDs:baselinePendingFileIDs:currentRecords:)`),
    /// so Scan Progress's "checked N of M" and Scan Complete's own totals
    /// can never disagree about which files this scan covered
    /// (`High-Fidelity UI Specification.md` §4's own UX Acceptance
    /// Criterion: "No number shown here can be inconsistent with what
    /// Review Queue or Execute subsequently shows for the same batch").
    public static func compute(records: [FileRecordSnapshot], scope: Set<String>) -> ScanCompleteProjection {
        let scoped = records.filter { scope.contains($0.fileID) }

        let tierCounts = Dictionary(grouping: scoped.compactMap(\.tier), by: { $0 }).mapValues(\.count)
        let tierRows = orderedTiers.compactMap { tier -> TierRow? in
            guard let count = tierCounts[tier], count > 0 else { return nil }
            return TierRow(tier: tier, count: count)
        }

        let categoryCounts = Dictionary(grouping: scoped.compactMap(\.category), by: { $0 }).mapValues(\.count)
        let categoryBreakdown = categoryCounts
            .map { CategoryRow(category: $0.key, count: $0.value) }
            .sorted { lhs, rhs in
                lhs.count != rhs.count ? lhs.count > rhs.count : lhs.category.rawValue < rhs.category.rawValue
            }

        let autoCount = tierCounts[.auto] ?? 0

        return ScanCompleteProjection(
            totalFilesLookedAt: scoped.count,
            tierRows: tierRows,
            categoryBreakdown: categoryBreakdown,
            primaryActionAutoCount: autoCount > 0 ? autoCount : nil
        )
    }
}
