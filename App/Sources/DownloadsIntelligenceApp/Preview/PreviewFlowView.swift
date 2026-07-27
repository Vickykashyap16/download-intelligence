import SwiftUI
import EngineBridge

/// Wires one `PreviewViewModel` to Preview's loading/error/content states —
/// the same loading/error/content branching `HomeView` already establishes
/// for its own `HomeViewModel`, applied here to Preview.
///
/// Unlike `ScanFlowView` (which wraps an externally-owned `ScanViewModel`
/// because a running scan must survive Sidebar navigation away from it),
/// `PreviewFlowView` owns its `PreviewViewModel` itself, exactly as
/// `HomeView` owns its own `HomeViewModel` — Preview has nothing in flight
/// to preserve across a navigation round-trip, so there is no reason to
/// hoist its view model up to `AppShell`. This is what makes "always a
/// fresh read on every visit" (`GUI Architecture Specification.md` §7)
/// fall out of ordinary SwiftUI view identity for free: `AppShell` renders
/// this view fresh each time Preview is (re-)entered (see `AppShell`'s own
/// `isPreviewShowing` documentation), so a fresh `@StateObject` — and
/// therefore a fresh `.task` call to `refreshNow()` — is created every
/// single time, never carried over from a previous visit.
struct PreviewFlowView: View {
    @StateObject private var viewModel: PreviewViewModel
    private let onExecuteNow: () -> Void
    private let onReview: () -> Void
    private let onScanNow: () -> Void
    private let onBackToHome: () -> Void

    init(
        bridge: EngineBridge,
        onExecuteNow: @escaping () -> Void,
        onReview: @escaping () -> Void,
        onScanNow: @escaping () -> Void,
        onBackToHome: @escaping () -> Void
    ) {
        _viewModel = StateObject(wrappedValue: PreviewViewModel(bridge: bridge))
        self.onExecuteNow = onExecuteNow
        self.onReview = onReview
        self.onScanNow = onScanNow
        self.onBackToHome = onBackToHome
    }

    var body: some View {
        Group {
            if viewModel.isLoading {
                // "Loading: brief, while the current plan is retrieved;
                // non-determinate given short expected duration" (§7,
                // States).
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let errorPresentation = viewModel.errorPresentation, viewModel.projection == nil {
                ErrorStateView(errorPresentation) {
                    Task { await viewModel.refreshNow() }
                }
            } else if let projection = viewModel.projection {
                PreviewView(
                    projection: projection,
                    onExecuteNow: onExecuteNow,
                    onReview: onReview,
                    onScanNow: onScanNow,
                    onBackToHome: onBackToHome
                )
            }
        }
        .task {
            await viewModel.refreshNow()
        }
    }
}
