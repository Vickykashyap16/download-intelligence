import SwiftUI
import EngineBridge

/// Reports' top-level screen (`High-Fidelity UI Specification.md` §11;
/// `Downloads Intelligence — Figma Design Production Guide.md` frame
/// `12 — Reports`): a fixed, always-visible four-way selector row at the
/// top, with the selected report's content scrolling independently
/// beneath it (§11 Layout Specification). Mirrors `HistoryView`'s own
/// `isLoading`/content branching, adapted for Reports' own per-sub-view
/// error handling (see `ReportsViewModel`'s documentation for why there is
/// no single whole-screen error state here).
public struct ReportsView: View {
    @ObservedObject private var viewModel: ReportsViewModel
    @State private var selectedKind: ReportKind = .dailySummary
    @AccessibilityFocusState private var isContentFocused: Bool

    public init(viewModel: ReportsViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if viewModel.projection?.isEmpty ?? true {
                // "No reports generated yet" (§11 Empty state) — one of the
                // seven named `EmptyStateView` configurations WP-GUI-01
                // already anticipated for this exact screen ("Reports —
                // Empty").
                EmptyStateView(
                    systemImageName: AppSection.reports.outlineSymbolName,
                    heading: "No reports generated yet",
                    explanation: "Reports summarize what's been filed. Once files have been filed, reports will appear here."
                )
            } else {
                VStack(alignment: .leading, spacing: 24) {
                    selectorRow
                    ScrollView {
                        selectedContent
                            .accessibilityFocused($isContentFocused)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .padding()
            }
        }
        .task {
            // Report generation is triggered exactly once, here, on entry
            // to this screen — never per sub-view selection (`Desktop
            // Implementation Blueprint.md` §7; `ReportsViewModel`'s own
            // documentation). Switching `selectedKind` below is purely
            // local, synchronous state — it never calls back into
            // `viewModel`.
            await viewModel.refreshNow()
        }
    }

    @ViewBuilder
    private var selectorRow: some View {
        // "A simple label-based selector/switcher (four items, no icons
        // required at MVP scope)" (Figma frame `12`) — the four-report
        // selector lives within Reports itself, not as separate Sidebar
        // entries (Hi-Fi §11 Layout Specification).
        HStack(spacing: 20) {
            selectorButton(title: "Daily Summary", kind: .dailySummary)
            selectorButton(title: "Weekly Summary", kind: .weeklySummary)
            selectorButton(title: "Duplicate Report", kind: .duplicateReport)
            selectorButton(title: "Storage Report", kind: .storageReport)
        }
    }

    private func selectorButton(title: String, kind: ReportKind) -> some View {
        let isSelected = selectedKind == kind
        return Button {
            selectedKind = kind
            // "Switching sub-views moves focus to the newly active
            // report's heading" (Hi-Fi §11 Accessibility).
            isContentFocused = true
        } label: {
            Text(title)
                .font(.callout.weight(isSelected ? .semibold : .regular))
                .foregroundStyle(isSelected ? Color.primary : Color.secondary)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
    }

    @ViewBuilder
    private var selectedContent: some View {
        switch selectedKind {
        case .dailySummary:
            reportOrError(report: viewModel.projection?.dailySummary, error: viewModel.dailySummaryError)
        case .weeklySummary:
            reportOrError(report: viewModel.projection?.weeklySummary, error: viewModel.weeklySummaryError)
        case .duplicateReport:
            reportOrError(report: viewModel.projection?.duplicateReport, error: viewModel.duplicateReportError)
        case .storageReport:
            reportOrError(report: viewModel.projection?.storageReport, error: viewModel.storageReportError)
        }
    }

    /// A report-specific load failure never affects the other three
    /// sub-views (Hi-Fi §11 States) — rendered inline, within this one
    /// sub-view's own content area only.
    @ViewBuilder
    private func reportOrError(report: ReportsProjection.Report?, error: ErrorPresentation?) -> some View {
        if let error {
            ErrorStateView(error) {
                Task { await viewModel.refreshNow() }
            }
        } else if let report {
            ReportSectionView(report: report)
        } else {
            // This specific report type hasn't been generated, even though
            // at least one of the other three has (§11 Empty state: "an
            // individual report type may also be empty... without implying
            // the others are also empty").
            Text("Nothing here yet.")
                .font(.body)
                .foregroundStyle(.secondary)
        }
    }
}
