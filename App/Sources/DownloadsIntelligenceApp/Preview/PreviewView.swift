import SwiftUI
import EngineBridge

/// Preview (`High-Fidelity UI Specification.md` §7): a persistent,
/// revisitable, read-only view of the complete current plan across all
/// three tiers at once — distinct from Scan Complete, which is the
/// transient moment right after one specific scan finishes. Every
/// affordance on this screen is either purely informational or a
/// navigation link elsewhere (`Downloads Intelligence — Figma Design
/// Production Guide.md`, Frame 08 annotation: "this frame must never
/// trigger any file operation") — `onExecuteNow`/`onReview` hand off to
/// whichever screen actually performs an action, exactly like
/// `ScanCompleteView`'s own `onFileNow`/`onReview` stub-navigation
/// callbacks.
public struct PreviewView: View {
    private let projection: PreviewProjection
    private let onExecuteNow: () -> Void
    private let onReview: () -> Void
    private let onScanNow: () -> Void
    private let onBackToHome: () -> Void

    /// - Parameters:
    ///   - onExecuteNow: "Execute now" (§7's Primary Action) — proceeds to
    ///     Execute (§8) for the auto-tier batch. Execute itself remains out
    ///     of scope (WP-GUI-07), so the caller (`AppShell`) routes this to
    ///     the same "not built yet" filing stub Scan Complete's "File the N
    ///     now" already uses.
    ///   - onReview: "Review" links into Review Queue for the two non-auto
    ///     tier sections (§7's Secondary Action) — the same single
    ///     destination regardless of which section's link was used,
    ///     matching `ScanCompleteView`'s own single `onReview` closure.
    ///   - onScanNow: the "Nothing to preview yet" empty state's one action
    ///     (§15).
    ///   - onBackToHome: the "Everything's already filed" empty state's one
    ///     action (§15).
    public init(
        projection: PreviewProjection,
        onExecuteNow: @escaping () -> Void,
        onReview: @escaping () -> Void,
        onScanNow: @escaping () -> Void,
        onBackToHome: @escaping () -> Void
    ) {
        self.projection = projection
        self.onExecuteNow = onExecuteNow
        self.onReview = onReview
        self.onScanNow = onScanNow
        self.onBackToHome = onBackToHome
    }

    public var body: some View {
        switch projection.kind {
        case .nothingScannedYet:
            EmptyStateView(
                systemImageName: "eye",
                heading: "Nothing to preview yet",
                explanation: "Run a scan first to see what would happen if you filed everything now.",
                primaryActionTitle: "Scan now",
                primaryAction: onScanNow
            )
        case .allFiled:
            EmptyStateView(
                systemImageName: "checkmark.circle",
                heading: "Everything's already filed",
                explanation: "The last plan has already been fully executed. Scan again to build a new one.",
                secondaryActionTitle: "Back to Home",
                secondaryAction: onBackToHome
            )
        case .hasPlan:
            content
        }
    }

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                // "First attention: the explicit 'this is read-only'
                // framing, stated once at the top" (§7, Screen Hierarchy).
                Text("Preview — nothing has moved yet.")
                    .font(.title.weight(.semibold))
                    .accessibilityAddTraits(.isHeader)

                Text("You can reopen this anytime — looking here never changes anything until you execute.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .padding(.top, 4)

                // Three tier sections in fixed order, always expanded
                // ("defaults to expanded so nothing is hidden by default,"
                // §7 Layout Specification) — zero-count tiers never produce
                // a section at all (`PreviewProjection`'s own zero-row
                // omission).
                VStack(alignment: .leading, spacing: 24) {
                    ForEach(projection.tierSections, id: \.tier) { section in
                        tierSection(section)
                    }
                }
                .padding(.top, 24)

                if let autoCount = projection.primaryActionAutoCount {
                    PrimaryButton("Execute now", action: onExecuteNow)
                        .fixedSize()
                        .padding(.top, 32)
                        .accessibilityLabel(Text("Execute now, \(autoCount) files"))
                }
            }
            .padding(32)
            .frame(maxWidth: 560, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// One tier's section header (icon, label matching Scan Complete's
    /// exact wording via the shared `ConfidenceChipModel`, and count) plus
    /// its full list of File Rows. The "Review" link lives once per
    /// non-auto section header, not once per row — §7's Content
    /// Specification: "'Review' links into Review Queue for the two
    /// non-auto tiers, matching Scan Complete's pattern," i.e. one link per
    /// tier, the same granularity `ScanCompleteView.tierRow(_:)` already
    /// uses.
    @ViewBuilder
    private func tierSection(_ section: PreviewProjection.TierSection) -> some View {
        let model = ConfidenceChipModel(tier: section.tier)
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: model.iconSystemName)
                    .accessibilityHidden(true)
                Text(model.label)
                    .font(.headline)
                Text("\(section.count)")
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                    .accessibilityLabel("\(section.count) files")
                Spacer()
                if section.tier != .auto {
                    Button("Review", action: onReview)
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.accentColor)
                }
            }
            VStack(alignment: .leading, spacing: 8) {
                ForEach(section.rows, id: \.fileID) { row in
                    fileRow(row)
                    if row.fileID != section.rows.last?.fileID {
                        Divider()
                    }
                }
            }
        }
    }

    /// One File Row: full before → after filename/destination, plus a
    /// compact Confidence Chip (§7 Content/Component Specification). No
    /// per-row action beyond the section-level "Review" link — this is
    /// inspection only, never a Review Card (§7 Component Usage: "File
    /// Row/List (not Review Card — no per-row actions exist here beyond a
    /// link into Review Queue)").
    @ViewBuilder
    private func fileRow(_ row: PreviewProjection.FileRow) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(row.originalName)
                        .foregroundStyle(row.suggestedName != nil ? .secondary : .primary)
                    if let suggestedName = row.suggestedName {
                        Image(systemName: "arrow.right")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .accessibilityHidden(true)
                        Text(suggestedName)
                    }
                }
                .font(.body)
                .accessibilityElement(children: .combine)
                if let destination = row.suggestedDestination {
                    Text(destination)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            Spacer()
            ConfidenceChip(tier: row.tier, score: row.confidenceScore)
        }
        .padding(.vertical, 4)
    }
}
