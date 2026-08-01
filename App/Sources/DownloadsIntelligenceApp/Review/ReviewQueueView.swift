import SwiftUI
import EngineBridge

/// Review Queue's content screen (`High-Fidelity UI Specification.md` §5):
/// "Needs your input" then "Flagged for you," in that fixed order, each
/// with a sticky group header and its own Review Cards — a group with no
/// items is omitted entirely (`ReviewQueueProjection`'s own zero-group
/// omission).
///
/// Renders directly from `viewModel.visibleNeedsInputItems`/
/// `visibleFlaggedItems` — decided-this-session items simply disappear from
/// both lists (`ReviewQueueViewModel`'s own session-local decision model) —
/// never from `viewModel.projection` directly, so a genuine "queue cleared
/// entirely this session" state can be told apart from "nothing was ever
/// here" (which `ReviewQueueFlowView` handles one level up, by redirecting
/// to Home instead of ever rendering this view at all).
public struct ReviewQueueView: View {
    @ObservedObject private var viewModel: ReviewQueueViewModel
    private let onOpenDetail: (String) -> Void
    private let onOpenWhy: (String) -> Void

    @FocusState private var focusedFileID: String?

    public init(
        viewModel: ReviewQueueViewModel,
        onOpenDetail: @escaping (String) -> Void,
        onOpenWhy: @escaping (String) -> Void
    ) {
        self.viewModel = viewModel
        self.onOpenDetail = onOpenDetail
        self.onOpenWhy = onOpenWhy
    }

    public var body: some View {
        if viewModel.visibleNeedsInputItems.isEmpty && viewModel.visibleFlaggedItems.isEmpty {
            // Everything that existed at the last fresh read has been
            // decided this session — distinct from "nothing was ever here"
            // (`ReviewQueueFlowView` handles that case by redirecting to
            // Home instead of reaching this view at all). Revisiting later
            // triggers a genuinely fresh read, which will show Home's own
            // caught-up state if the queue really is empty by then.
            EmptyStateView(
                systemImageName: "checkmark.circle",
                heading: "You've cleared the queue",
                explanation: "Nice work. Revisiting Review Queue later will show its current state."
            )
        } else {
            content
        }
    }

    private var content: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                if !viewModel.visibleNeedsInputItems.isEmpty {
                    Section(header: groupHeader("Needs your input", count: viewModel.visibleNeedsInputItems.count)) {
                        ForEach(viewModel.visibleNeedsInputItems, id: \.fileID) { item in
                            NeedsInputCardView(
                                item: item,
                                focusedFileID: $focusedFileID,
                                onOpenDetail: { onOpenDetail(item.fileID) },
                                onApprove: { decide(.approved, for: item.fileID) },
                                onEdit: { onOpenDetail(item.fileID) },
                                onReject: { decide(.rejected, for: item.fileID) }
                            )
                            .padding(.vertical, 6)
                        }
                    }
                }
                if !viewModel.visibleFlaggedItems.isEmpty {
                    Section(header: groupHeader("Flagged for you", count: viewModel.visibleFlaggedItems.count)) {
                        ForEach(viewModel.visibleFlaggedItems, id: \.fileID) { item in
                            FlaggedCardView(
                                item: item,
                                focusedFileID: $focusedFileID,
                                onOpenWhy: { onOpenWhy(item.fileID) }
                            )
                            .padding(.vertical, 6)
                        }
                    }
                }
            }
            .padding(32)
            .frame(maxWidth: 640, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// A sticky, opaque-background group header (`06 Visual Design
    /// System.md` §6, Layout System) — count included, matching every other
    /// screen's own tier/group header convention (`PreviewView.tierSection`,
    /// `ScanCompleteView.tierRow`).
    private func groupHeader(_ title: String, count: Int) -> some View {
        HStack {
            Text("\(title) (\(count))")
                .font(.title3.weight(.semibold))
                .accessibilityAddTraits(.isHeader)
            Spacer()
        }
        .padding(.vertical, 12)
        .background(.background)
    }

    /// Records the decision, then moves keyboard focus to whichever card
    /// `ReviewQueueViewModel.decide(_:for:)` reports as the next remaining
    /// one in the same group (`High-Fidelity UI Specification.md` §5
    /// Accessibility: "focus moves to the next remaining card... never
    /// being lost or reset to the top of the list").
    private func decide(_ decision: ReviewQueueViewModel.Decision, for fileID: String) {
        focusedFileID = viewModel.decide(decision, for: fileID)
    }
}
