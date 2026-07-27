import SwiftUI
import EngineBridge

/// Home in all three of its states (`GUI Engineering Work Packages.md`
/// WP-GUI-03), rendered from a real `HomeViewModel`/`HomeProjection` —
/// never from data owned by another screen. Layout follows `Downloads
/// Intelligence — Figma Design Production Guide.md`'s Home frame spec
/// (`03`/`03a`/`03b`): steady state is a left-aligned content column
/// (status sentence → 24px → Primary Button → 32px → recency block → 32px
/// → trend-summary card); both empty variants reuse the shared
/// `EmptyStateView` component, centered, per that same spec.
public struct HomeView: View {
    @StateObject private var viewModel: HomeViewModel

    /// "Go to Review Queue" is a real navigation target — Review Queue's
    /// placeholder already exists from WP-GUI-01's Sidebar. "Scan now" /
    /// "Scan again" / "File them now" are stub targets per WP-GUI-03's own
    /// scope ("Out of scope: the screens Home's actions navigate to...
    /// beyond stub navigation targets") — the caller (`AppShell`) decides
    /// what a stub actually shows.
    private let onGoToReviewQueue: () -> Void
    private let onScanRequested: () -> Void
    private let onFileThemNow: () -> Void
    private let onGoToPreview: (() -> Void)?

    /// - Parameter onGoToPreview: WP-GUI-05's Home entry point into Preview
    ///   (`High-Fidelity UI Specification.md` §7: "Preview is reachable
    ///   from Scan Complete ('Review full plan') and, once a plan exists,
    ///   from Home"). Optional and additive, `nil` by default — shown only
    ///   in the `.needsReview`/`.readyToFile` steady states, since those
    ///   are exactly the states in which a plan exists at all.
    public init(
        bridge: EngineBridge,
        onGoToReviewQueue: @escaping () -> Void,
        onScanRequested: @escaping () -> Void,
        onFileThemNow: @escaping () -> Void,
        onGoToPreview: (() -> Void)? = nil
    ) {
        _viewModel = StateObject(wrappedValue: HomeViewModel(bridge: bridge))
        self.onGoToReviewQueue = onGoToReviewQueue
        self.onScanRequested = onScanRequested
        self.onFileThemNow = onFileThemNow
        self.onGoToPreview = onGoToPreview
    }

    public var body: some View {
        Group {
            if viewModel.isLoading {
                // "Loading: brief, only while the current status is being
                // computed on screen open... a lightweight, non-
                // determinate treatment" (`High-Fidelity UI
                // Specification.md` §2).
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let errorPresentation = viewModel.errorPresentation, viewModel.projection == nil {
                // Only a failed *initial* load replaces the whole screen
                // with the Error State — a transient failure during
                // periodic refresh keeps showing the last-known-good
                // projection instead (`HomeViewModel.refreshNow()`).
                ErrorStateView(errorPresentation) {
                    Task { await viewModel.refreshNow() }
                }
            } else if let projection = viewModel.projection {
                content(for: projection)
            }
        }
        .task {
            await viewModel.refreshNow()
            viewModel.startPeriodicRefresh()
        }
    }

    @ViewBuilder
    private func content(for projection: HomeProjection) -> some View {
        switch projection.kind {
        case .firstRun:
            EmptyStateView(
                systemImageName: "folder",
                heading: "Nothing scanned yet",
                explanation: "Run your first scan to see what's in your Downloads folder.",
                primaryActionTitle: "Scan now",
                primaryAction: onScanRequested
            )
        case .caughtUp:
            EmptyStateView(
                systemImageName: "checkmark.circle",
                heading: "You're all caught up",
                explanation: caughtUpExplanation(projection),
                secondaryActionTitle: "Scan again",
                secondaryAction: onScanRequested
            )
        case .needsReview, .readyToFile:
            steadyState(projection)
        }
    }

    private func steadyState(_ projection: HomeProjection) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text(projection.primaryMessage)
                    .font(.title.weight(.semibold))
                    .accessibilityAddTraits(.isHeader)

                if let primaryActionTitle = projection.primaryActionTitle {
                    PrimaryButton(primaryActionTitle, action: primaryAction(for: projection.kind))
                        .fixedSize()
                        .padding(.top, 24)
                }

                recencyBlock(projection)
                    .padding(.top, 32)

                trendSummaryCard(projection)
                    .padding(.top, 32)

                if let secondaryActionTitle = projection.secondaryActionTitle {
                    SecondaryButton(secondaryActionTitle, action: onScanRequested)
                        .fixedSize()
                        .padding(.top, 32)
                }

                if let onGoToPreview {
                    Button("Review the full plan", action: onGoToPreview)
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.accentColor)
                        .padding(.top, 16)
                }
            }
            .padding(32)
            .frame(maxWidth: 560, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func recencyBlock(_ projection: HomeProjection) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let lastScanDate = projection.lastScanDate {
                HStack(spacing: 6) {
                    Text("Last scan").font(.subheadline).foregroundStyle(.secondary)
                    Text(Self.dateFormatter.string(from: lastScanDate)).font(.body)
                }
            }
            if let lastBatch = projection.lastBatch {
                HStack(spacing: 6) {
                    Text("Last batch").font(.subheadline).foregroundStyle(.secondary)
                    Text(lastBatchDescription(lastBatch)).font(.body)
                }
            }
        }
    }

    private func lastBatchDescription(_ batch: HomeProjection.BatchSummary) -> String {
        let fileCountText = batch.fileCount == 1 ? "1 file" : "\(batch.fileCount) files"
        guard let date = batch.date else { return fileCountText }
        return "\(fileCountText) · \(Self.dateFormatter.string(from: date))"
    }

    @ViewBuilder
    private func trendSummaryCard(_ projection: HomeProjection) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("This week").font(.subheadline).foregroundStyle(.secondary)
            if projection.weeklyTierCounts.isEmpty {
                Text("No activity this week").font(.body).foregroundStyle(.secondary)
            } else {
                // Fixed display order regardless of dictionary iteration
                // order, and rows for zero-count tiers are never
                // constructed in the first place (`HomeProjection`'s own
                // "omitted entirely" guarantee).
                ForEach(Self.orderedTiers.filter { projection.weeklyTierCounts[$0] != nil }, id: \.self) { tier in
                    TierCountRow(tier: tier, count: projection.weeklyTierCounts[tier] ?? 0)
                }
            }
        }
        .padding(16)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private func primaryAction(for kind: HomeProjection.Kind) -> () -> Void {
        switch kind {
        case .needsReview: return onGoToReviewQueue
        case .readyToFile: return onFileThemNow
        case .firstRun, .caughtUp: return {}
        }
    }

    private func caughtUpExplanation(_ projection: HomeProjection) -> String {
        guard let lastScanDate = projection.lastScanDate else {
            return "Everything's filed."
        }
        return "Everything's filed. Last scan: \(Self.dateFormatter.string(from: lastScanDate))."
    }

    private static let orderedTiers: [Tier] = [.auto, .approvalRequired, .reviewRequired]

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()
}

/// A compact tier + count row for the trend-summary card — visually a
/// small badge/pill, matching the Figma Production Guide's Home
/// annotation ("Status Badges with tier icons inline within the
/// trend-summary card's per-tier rows"), but not the shared `StatusBadge`
/// component itself: `StatusBadge` closes over Duplicate/Archived/
/// Unknown-category specifically, a different vocabulary than tiers.
/// Reuses `ConfidenceChipModel`'s label/icon mapping rather than
/// re-deriving tier vocabulary a second time — Confidence Chips
/// themselves are explicitly "not used on Home directly" (Figma
/// Production Guide, Home annotation notes), so this is a distinct,
/// Home-specific row, not a `ConfidenceChip` in disguise.
private struct TierCountRow: View {
    let tier: Tier
    let count: Int

    private var model: ConfidenceChipModel { ConfidenceChipModel(tier: tier) }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: model.iconSystemName)
                .font(.caption)
            Text(model.label)
                .font(.caption)
            Spacer()
            Text("\(count)")
                .font(.caption.monospacedDigit())
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 10)
        .background(Color.secondary.opacity(0.1), in: Capsule())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(model.label): \(count)")
    }
}
