import SwiftUI
import EngineBridge

/// History's top-level screen (`High-Fidelity UI Specification.md` §10;
/// `Wireframes — MVP.md` screens 15–16): a single scrolling batch list,
/// most recent first, each batch expanding in place rather than
/// navigating to a separate detail screen (§10 Layout Specification —
/// "expand-in-place rather than a separate detail screen"). Mirrors
/// `ReviewQueueFlowView`'s own loading/error/content branching over
/// `isLoading`/`errorPresentation`/`projection`, since `HistoryViewModel`
/// deliberately reuses that same shape rather than `ExecuteViewModel`'s
/// `Phase` enum (see `HistoryViewModel`'s own documentation for why).
public struct HistoryView: View {
    @ObservedObject private var viewModel: HistoryViewModel
    private let onUndoBatch: (String, [ExecuteResultProjection.FiledRow]) -> Void

    public init(viewModel: HistoryViewModel, onUndoBatch: @escaping (String, [ExecuteResultProjection.FiledRow]) -> Void) {
        self.viewModel = viewModel
        self.onUndoBatch = onUndoBatch
    }

    public var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let errorPresentation = viewModel.errorPresentation, viewModel.projection == nil {
                ErrorStateView(errorPresentation) {
                    Task { await viewModel.refreshNow() }
                }
            } else if let projection = viewModel.projection, !projection.isEmpty {
                // SwiftUI's `List` is already row-virtualized — only
                // visible rows are actually materialized, regardless of
                // how many hundreds of batches `projection.batches`
                // contains (see `HistoryViewModelTests`'
                // `test_compute_largeSyntheticHistory_...` for the
                // measured grouping/summarizing cost this relies on being
                // small).
                List(projection.batches, id: \.batchID) { batch in
                    HistoryBatchRow(batch: batch, onUndoBatch: { rows in onUndoBatch(batch.batchID, rows) })
                }
                .listStyle(.plain)
            } else {
                // "Nothing filed yet" — one of the seven named
                // configurations `EmptyStateView`'s own WP-GUI-01
                // documentation already anticipated for this exact screen.
                EmptyStateView(
                    systemImageName: "clock",
                    heading: "Nothing filed yet",
                    explanation: "Files you file will show up here, along with anything you've undone."
                )
            }
        }
        .task {
            // "History must always re-read fresh — never cache a stale
            // list" (WP-GUI-09 Technical Notes) — a fresh read every time
            // this view appears, the same discipline `ReviewQueueFlowView`
            // already establishes for its own `.task`.
            await viewModel.refreshNow()
        }
    }
}

/// One batch's row: collapsed summary, expanding in place to show
/// per-file detail (§10 Content Specification). Local `@State` for
/// expand/collapse — this is purely this row's own presentation state,
/// never shared with any other row or persisted.
struct HistoryBatchRow: View {
    let batch: HistoryProjection.Batch
    let onUndoBatch: ([ExecuteResultProjection.FiledRow]) -> Void

    @State private var isExpanded = false
    @AccessibilityFocusState private var isDetailFocused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(reduceMotion ? nil : .default) {
                    isExpanded.toggle()
                }
                if isExpanded { isDetailFocused = true }
            } label: {
                summaryRow
            }
            .buttonStyle(.plain)

            if isExpanded {
                detailSection
                    .accessibilityFocused($isDetailFocused)
            }
        }
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var summaryRow: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(formattedTimestamp)
                    .font(.headline)
                Spacer()
                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
            }

            Text(summaryLine)
                .font(.callout)
                .foregroundStyle(.secondary)

            if batch.isFullyUndone || batch.isPartiallyUndone {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.uturn.backward.circle")
                        .accessibilityHidden(true)
                    Text(batch.isFullyUndone ? "Reversed" : "Partially reversed")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
            }

            if !batch.tierBreakdown.isEmpty {
                HStack(spacing: 8) {
                    ForEach(batch.tierBreakdown, id: \.tier) { tierCount in
                        ConfidenceChip(tier: tierCount.tier)
                            .overlay(alignment: .topTrailing) {
                                Text("\(tierCount.count)")
                                    .font(.caption2.weight(.bold))
                                    .foregroundStyle(.secondary)
                                    .offset(x: 4, y: -4)
                            }
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text("\(formattedTimestamp). \(summaryLine)"))
        .accessibilityAddTraits(.isButton)
        .accessibilityHint(Text(isExpanded ? "Collapses this batch." : "Expands this batch to show individual files."))
        .contentShape(Rectangle())
    }

    @ViewBuilder
    private var detailSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(batch.filedRows, id: \.fileID) { row in
                fileDetailRow(row)
                if row.fileID != batch.filedRows.last?.fileID || !batch.problemRows.isEmpty {
                    Divider()
                }
            }
            ForEach(batch.problemRows, id: \.fileID) { row in
                problemDetailRow(row)
                if row.fileID != batch.problemRows.last?.fileID {
                    Divider()
                }
            }

            if !batch.isFullyUndone && !batch.filedRows.isEmpty {
                SecondaryButton("Undo this batch") {
                    let rows = batch.filedRows.map { filedRow in
                        // `destinationFolder` is never read by
                        // `UndoResultProjection.compute(_:_:)` — only
                        // `fileID`/`originalName` are — so it's passed as
                        // `nil` here rather than re-deriving a value
                        // nothing downstream consumes.
                        ExecuteResultProjection.FiledRow(fileID: filedRow.fileID, originalName: filedRow.originalName, destinationFolder: nil)
                    }
                    onUndoBatch(rows)
                }
                .fixedSize()
                .padding(.top, 4)
                .accessibilityLabel(Text("Undo this batch"))
            }
        }
        .padding(.top, 12)
        .padding(.leading, 8)
    }

    @ViewBuilder
    private func fileDetailRow(_ row: HistoryProjection.FiledFileRow) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text(row.originalName)
                if row.wasUndone {
                    Text("(restored)")
                        .foregroundStyle(.secondary)
                }
            }
            .font(.body)

            if let finalLocation = row.finalLocation {
                Text(finalLocation)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            if let tier = row.tier {
                ConfidenceChip(tier: tier, score: row.confidenceScore)
            }
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func problemDetailRow(_ row: HistoryProjection.ProblemFileRow) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(row.originalName)
            Text(row.reason)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }

    private var formattedTimestamp: String {
        guard let date = ISO8601DateFormatter().date(from: batch.timestamp) else { return batch.timestamp }
        return Self.dateFormatter.string(from: date)
    }

    private var summaryLine: String {
        batch.problemRows.isEmpty
            ? "\(batch.filedCount) file\(batch.filedCount == 1 ? "" : "s") filed"
            : "\(batch.filedCount) of \(batch.totalAttempted) filed"
    }
}
