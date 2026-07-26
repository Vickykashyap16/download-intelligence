import Foundation
import EngineBridge

/// The read-through projection Home renders — a pure, deterministic
/// computation over the engine's own metadata records, entirely
/// independent of any other screen's state (`Desktop Implementation
/// Blueprint.md` §3: "Home never assumes what its own counts should be
/// based on what just happened elsewhere; it always re-derives them
/// independently"). Kept separate from `HomeViewModel` so this logic is
/// unit-testable without an `EngineBridge`, a live window, or any
/// asynchronous code at all.
public struct HomeProjection: Equatable, Sendable {
    /// The three named Home states from `GUI Engineering Work Packages.md`
    /// WP-GUI-03 ("Home's steady state, first-run empty state, and
    /// fully-caught-up empty state"), with steady state split into its two
    /// documented variants (`High-Fidelity UI Specification.md` §2, Edge
    /// Cases: "the primary message reflects this honestly" for pending
    /// review vs. "if a batch is scanned but not yet executed, the message
    /// reflects '41 ready to file'"). This split is presentation detail
    /// within steady state, not a fourth top-level Home state.
    public enum Kind: Equatable, Sendable {
        case firstRun
        case needsReview(count: Int)
        case readyToFile(count: Int)
        case caughtUp
    }

    public struct BatchSummary: Equatable, Sendable {
        public let fileCount: Int
        public let date: Date?

        public init(fileCount: Int, date: Date?) {
            self.fileCount = fileCount
            self.date = date
        }
    }

    public let kind: Kind
    public let primaryMessage: String
    public let primaryActionTitle: String?
    public let secondaryActionTitle: String?
    public let lastScanDate: Date?
    public let lastBatch: BatchSummary?
    /// Per-tier counts for records discovered within the rolling window
    /// ending at the `now` the projection was computed with (`06 Visual
    /// Design System.md` §6, dashboard rhythm's "trend summary"). A tier
    /// with no matching records simply has no entry here — that *is* the
    /// "omitted entirely (not shown at zero)" rule from the Figma
    /// Production Guide's Home annotation notes, satisfied by construction
    /// rather than by a separate filtering step at render time.
    public let weeklyTierCounts: [Tier: Int]

    public init(
        kind: Kind,
        primaryMessage: String,
        primaryActionTitle: String?,
        secondaryActionTitle: String?,
        lastScanDate: Date?,
        lastBatch: BatchSummary?,
        weeklyTierCounts: [Tier: Int]
    ) {
        self.kind = kind
        self.primaryMessage = primaryMessage
        self.primaryActionTitle = primaryActionTitle
        self.secondaryActionTitle = secondaryActionTitle
        self.lastScanDate = lastScanDate
        self.lastBatch = lastBatch
        self.weeklyTierCounts = weeklyTierCounts
    }

    private static let dateFormatter = ISO8601DateFormatter()

    /// Computes the projection from the engine's own records — no other
    /// input is needed or consulted, per Home's own re-derive-independently
    /// principle above.
    ///
    /// - Parameters:
    ///   - records: every `FileRecordSnapshot` currently in the metadata
    ///     store, exactly as `MetadataStoreReadResult.records` returns them.
    ///   - now: the reference instant "This week" and recency are computed
    ///     relative to. Defaults to the real current time; tests pass a
    ///     fixed value so the 7-day window and recency text are
    ///     deterministic against fixture timestamps.
    public static func compute(records: [FileRecordSnapshot], now: Date = Date()) -> HomeProjection {
        // "No data exists: first-run empty state" (`High-Fidelity UI
        // Specification.md` §2, Edge Cases) — an empty metadata store
        // means no scan has ever completed, full stop; every other
        // computation below assumes at least one record exists.
        guard !records.isEmpty else {
            return HomeProjection(
                kind: .firstRun,
                primaryMessage: "Nothing scanned yet",
                primaryActionTitle: "Scan now",
                secondaryActionTitle: nil,
                lastScanDate: nil,
                lastBatch: nil,
                weeklyTierCounts: [:]
            )
        }

        let lastScanDate = records
            .compactMap { dateFormatter.date(from: $0.discoveredAt) }
            .max()

        let lastBatch = Self.mostRecentBatch(in: records)

        // Non-auto tiers (`review_required`, `approval_required`) both
        // route to Review Queue from Scan Complete (`Desktop
        // Implementation Blueprint.md` §4: "via either non-auto tier's
        // 'Review' link") — Home's single primary status sentence
        // combines them into one "needs your review" count rather than
        // two separate messages, matching "exactly one primary action is
        // ever presented at a time" (`High-Fidelity UI Specification.md`
        // §2, UX Acceptance Criteria). `review_required` files are never
        // executed at all (left in place and flagged, per `Rules/
        // Confidence Rules.md`), so every such record counts;
        // `approval_required` files stop counting once a human has acted
        // and the engine has filed them (`status == "executed"`).
        let reviewRequiredCount = records.filter { $0.tier == .reviewRequired }.count
        let approvalRequiredPendingCount = records.filter {
            $0.tier == .approvalRequired && $0.status != "executed"
        }.count
        let needsReviewCount = reviewRequiredCount + approvalRequiredPendingCount

        // Auto-tier files that have been scored but not yet filed —
        // `High-Fidelity UI Specification.md` §2, Edge Cases: "if a batch
        // is scanned but not yet executed, the message reflects '41 ready
        // to file'."
        let readyToFileCount = records.filter { $0.tier == .auto && $0.status != "executed" }.count

        let weeklyTierCounts = Self.weeklyTierCounts(in: records, now: now)

        if needsReviewCount > 0 {
            return HomeProjection(
                kind: .needsReview(count: needsReviewCount),
                primaryMessage: Self.countSentence(needsReviewCount, singular: "file needs", plural: "files need") + " your review",
                primaryActionTitle: "Go to Review Queue",
                secondaryActionTitle: "Scan again",
                lastScanDate: lastScanDate,
                lastBatch: lastBatch,
                weeklyTierCounts: weeklyTierCounts
            )
        }

        if readyToFileCount > 0 {
            return HomeProjection(
                kind: .readyToFile(count: readyToFileCount),
                primaryMessage: Self.countSentence(readyToFileCount, singular: "file ready", plural: "files ready") + " to file",
                primaryActionTitle: "File them now",
                secondaryActionTitle: "Scan again",
                lastScanDate: lastScanDate,
                lastBatch: lastBatch,
                weeklyTierCounts: weeklyTierCounts
            )
        }

        // Nothing pending: caught up. Per `High-Fidelity UI
        // Specification.md` §15 (Empty States), the caught-up instance's
        // action is a Secondary Button, not Primary — the only available
        // action here is optional, not the screen's one demanded action,
        // which is exactly what Secondary emphasis communicates.
        return HomeProjection(
            kind: .caughtUp,
            primaryMessage: "You're all caught up",
            primaryActionTitle: nil,
            secondaryActionTitle: "Scan again",
            lastScanDate: lastScanDate,
            lastBatch: lastBatch,
            weeklyTierCounts: weeklyTierCounts
        )
    }

    private static func countSentence(_ count: Int, singular: String, plural: String) -> String {
        count == 1 ? "1 \(singular)" : "\(count) \(plural)"
    }

    /// The most recently processed batch — the record set sharing the
    /// `batchID` whose `processedAt` is latest — and how many records
    /// belong to it. Records with no `batchID` (never reached execution)
    /// are not eligible to be "the last batch."
    private static func mostRecentBatch(in records: [FileRecordSnapshot]) -> BatchSummary? {
        let processed = records.compactMap { record -> (batchID: String, date: Date)? in
            guard let batchID = record.batchID,
                  let processedAtString = record.processedAt,
                  let date = dateFormatter.date(from: processedAtString)
            else { return nil }
            return (batchID, date)
        }
        guard let latest = processed.max(by: { $0.date < $1.date }) else { return nil }
        let fileCount = records.filter { $0.batchID == latest.batchID }.count
        return BatchSummary(fileCount: fileCount, date: latest.date)
    }

    /// Per-tier counts among records discovered within
    /// `HomeConfiguration.weeklyTrendWindowInDays` of `now` — see that
    /// property's documentation for why a rolling window was chosen.
    /// Untiered records (still mid-pipeline, never reached confidence
    /// scoring) are excluded, since the trend summary reports the *tier*
    /// distribution specifically.
    private static func weeklyTierCounts(in records: [FileRecordSnapshot], now: Date) -> [Tier: Int] {
        guard let windowStart = Calendar(identifier: .gregorian).date(
            byAdding: .day, value: -HomeConfiguration.weeklyTrendWindowInDays, to: now
        ) else { return [:] }

        let recentTiers = records.compactMap { record -> Tier? in
            guard let tier = record.tier,
                  let discoveredAt = dateFormatter.date(from: record.discoveredAt),
                  discoveredAt >= windowStart, discoveredAt <= now
            else { return nil }
            return tier
        }
        return Dictionary(grouping: recentTiers, by: { $0 }).mapValues(\.count)
    }
}
