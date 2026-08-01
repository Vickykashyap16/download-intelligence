import SwiftUI
import EngineBridge

/// Wires one `ReviewDetailViewModel` (its own independent fresh read) to
/// whichever of `ReviewDetailView`/`FlaggedDetailView` its freshly-read
/// `kind` calls for — decided from real, current data rather than trusting
/// which card the user clicked from the list, since Detail's own read can
/// race the list's (`ReviewDetailProjection.Kind`'s own documentation).
///
/// Approve/Reject is recorded into `reviewQueueViewModel` — the same,
/// already-hoisted view model the list itself reads from — never into any
/// state local to this type, so the list and this screen can never
/// disagree about what has already been decided this session.
struct ReviewDetailFlowView: View {
    @StateObject private var viewModel: ReviewDetailViewModel
    @ObservedObject var reviewQueueViewModel: ReviewQueueViewModel
    let onBackToQueue: () -> Void

    init(
        bridge: EngineBridge,
        fileID: String,
        reviewQueueViewModel: ReviewQueueViewModel,
        onBackToQueue: @escaping () -> Void
    ) {
        _viewModel = StateObject(wrappedValue: ReviewDetailViewModel(bridge: bridge, fileID: fileID))
        self.reviewQueueViewModel = reviewQueueViewModel
        self.onBackToQueue = onBackToQueue
    }

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let errorPresentation = viewModel.errorPresentation, viewModel.projection == nil {
                ErrorStateView(errorPresentation) {
                    Task { await viewModel.refreshNow() }
                }
            } else if let projection = viewModel.projection, projection.kind == .needsInput {
                ReviewDetailView(
                    projection: projection,
                    onApprove: {
                        reviewQueueViewModel.decide(.approved, for: projection.fileID)
                        onBackToQueue()
                    },
                    onReject: {
                        reviewQueueViewModel.decide(.rejected, for: projection.fileID)
                        onBackToQueue()
                    },
                    onBackToQueue: onBackToQueue
                )
            } else if let projection = viewModel.projection, projection.kind == .flagged {
                FlaggedDetailView(
                    projection: projection,
                    onBackToQueue: onBackToQueue
                )
            } else {
                // Either genuinely not found, or found but no longer
                // belongs to either group (e.g. executed or re-scored to
                // auto since the list's own last read) — an honest,
                // disclosed race rather than a silently stale screen.
                EmptyStateView(
                    systemImageName: "checkmark.circle",
                    heading: "This item no longer needs review",
                    explanation: "It's already been handled, or the plan changed since you opened it.",
                    secondaryActionTitle: "Back to queue",
                    secondaryAction: onBackToQueue
                )
            }
        }
        .task {
            await viewModel.refreshNow()
        }
    }
}
