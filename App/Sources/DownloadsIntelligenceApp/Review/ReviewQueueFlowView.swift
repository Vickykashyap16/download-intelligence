import SwiftUI
import EngineBridge

/// Wires one `ReviewQueueViewModel` to Review Queue's loading/error/content
/// states, the same branching every other screen's flow wrapper already
/// establishes (`PreviewFlowView`, `HomeView`).
///
/// Unlike `PreviewFlowView` (which owns its view model entirely internally,
/// since Preview has no drill-down state to share), this type's
/// `ReviewQueueViewModel` must be reachable by Review Detail too — Approve/
/// Reject made from Detail has to land in the exact same session-local
/// `decisions` dictionary the list itself reads from, so a decision made on
/// one screen is immediately reflected on the other
/// (`GUI Architecture Specification.md` line 99: Review Detail is state
/// nested *under* Review Queue, not a separate destination). `AppShell`
/// therefore hoists this type's own `ReviewQueueViewModel` at the same
/// level it hoists `ScanViewModel` — high enough to outlive the Detail
/// drill-down, for the same "must survive a nested navigation" reason.
struct ReviewQueueFlowView: View {
    @ObservedObject var viewModel: ReviewQueueViewModel
    let onOpenDetail: (String) -> Void
    let onOpenWhy: (String) -> Void

    /// Called at most once, immediately after the first fresh read, only
    /// when that read shows genuinely nothing to review at all (§5 States/
    /// Edge Cases: "routes to Home's fully caught up empty state rather
    /// than a bespoke empty Review Queue screen"). Deliberately keyed off
    /// `viewModel.projection` — the untouched fresh-read snapshot — rather
    /// than the decision-filtered `visible...Items`, so clearing every card
    /// *during* this session (a different, already-handled case; see
    /// `ReviewQueueView`'s own "You've cleared the queue" state) never
    /// triggers this redirect.
    let onQueueEmpty: () -> Void

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let errorPresentation = viewModel.errorPresentation, viewModel.projection == nil {
                ErrorStateView(errorPresentation) {
                    Task { await viewModel.refreshNow() }
                }
            } else if let projection = viewModel.projection, !projection.isEmpty {
                ReviewQueueView(
                    viewModel: viewModel,
                    onOpenDetail: onOpenDetail,
                    onOpenWhy: onOpenWhy
                )
            } else {
                // Nothing to review at all — `onQueueEmpty()` (below) is
                // about to redirect away from this section entirely; this
                // is only ever a one-frame transient, never a resting state
                // a user actually sees.
                Color.clear
            }
        }
        .task {
            await viewModel.refreshNow()
            if let projection = viewModel.projection, projection.isEmpty {
                onQueueEmpty()
            }
        }
    }
}
