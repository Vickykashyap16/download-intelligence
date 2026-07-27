import SwiftUI
import EngineBridge

/// Scan Complete (`High-Fidelity UI Specification.md` §4): header, tier-
/// count rows in fixed order with zero-row omission, a category breakdown,
/// and the "File the N now" Primary Button when there's anything auto-tier
/// to file. Execute itself (what "File the N now" leads to) and Review
/// Queue's real content are both out of WP-GUI-04's scope — `onFileNow`/
/// `onReview` are supplied by the caller (`AppShell`), exactly like
/// `HomeView`'s own `onScanRequested`/`onFileThemNow`/`onGoToReviewQueue`
/// stub-navigation callbacks already work.
public struct ScanCompleteView: View {
    private let projection: ScanCompleteProjection
    private let onReview: () -> Void
    private let onFileNow: () -> Void
    private let extraSecondaryActionTitle: String?
    private let extraSecondaryAction: (() -> Void)?

    /// - Parameters:
    ///   - extraSecondaryActionTitle/extraSecondaryAction: an additional,
    ///     caller-supplied action beyond the two the spec names — used only
    ///     by the First Run Experience entry point, which has no Sidebar to
    ///     navigate away through, to bridge back into `.displayingHome`
    ///     once the very first scan's result has been shown (see
    ///     `AppShell`'s own documentation for why this one entry point
    ///     needs it and the Home entry point does not).
    public init(
        projection: ScanCompleteProjection,
        onReview: @escaping () -> Void,
        onFileNow: @escaping () -> Void,
        extraSecondaryActionTitle: String? = nil,
        extraSecondaryAction: (() -> Void)? = nil
    ) {
        self.projection = projection
        self.onReview = onReview
        self.onFileNow = onFileNow
        self.extraSecondaryActionTitle = extraSecondaryActionTitle
        self.extraSecondaryAction = extraSecondaryAction
    }

    public var body: some View {
        if projection.isEmpty {
            EmptyStateView(
                systemImageName: "tray",
                heading: "No files found to sort",
                explanation: "Nothing new was found to check this time.",
                secondaryActionTitle: extraSecondaryActionTitle,
                secondaryAction: extraSecondaryAction
            )
        } else {
            content
        }
    }

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text("Scan complete — \(projection.totalFilesLookedAt) files looked at")
                    .font(.title.weight(.semibold))
                    .accessibilityAddTraits(.isHeader)

                VStack(alignment: .leading, spacing: 12) {
                    ForEach(projection.tierRows, id: \.tier) { row in
                        tierRow(row)
                    }
                }
                .padding(.top, 24)

                if !projection.categoryBreakdown.isEmpty {
                    Divider().padding(.vertical, 24)
                    Text("By type")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(projection.categoryBreakdown, id: \.category) { row in
                            HStack {
                                Text(row.category.rawValue)
                                Spacer()
                                Text("\(row.count)").monospacedDigit()
                            }
                        }
                    }
                    .padding(.top, 8)
                }

                if let autoCount = projection.primaryActionAutoCount {
                    PrimaryButton("File the \(autoCount) now", action: onFileNow)
                        .fixedSize()
                        .padding(.top, 32)
                }

                if let extraSecondaryActionTitle, let extraSecondaryAction {
                    SecondaryButton(extraSecondaryActionTitle, action: extraSecondaryAction)
                        .fixedSize()
                        .padding(.top, 16)
                }
            }
            .padding(32)
            .frame(maxWidth: 560, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// Every tier row's icon is paired with its label and count — never
    /// icon-only (§4, Accessibility) — reusing `ConfidenceChipModel`'s
    /// label/icon mapping rather than re-deriving tier vocabulary a second
    /// time, the same reuse `HomeView`'s own `TierCountRow` already
    /// establishes for tier rows.
    @ViewBuilder
    private func tierRow(_ row: ScanCompleteProjection.TierRow) -> some View {
        let model = ConfidenceChipModel(tier: row.tier)
        HStack(spacing: 8) {
            Image(systemName: model.iconSystemName)
                .accessibilityHidden(true)
            Text(model.label)
            Spacer()
            Text("\(row.count)")
                .monospacedDigit()
                .accessibilityLabel("\(row.count) files")
            // Deliberately left un-combined with the rest of this row (unlike
            // `HomeView`'s `TierCountRow`, which has no interactive content):
            // combining would swallow this button's own accessibility
            // element, making "Review" unreachable as a distinct action for
            // VoiceOver users.
            if row.tier != .auto {
                Button("Review", action: onReview)
                    .buttonStyle(.plain)
                    .foregroundStyle(Color.accentColor)
            }
        }
    }
}
