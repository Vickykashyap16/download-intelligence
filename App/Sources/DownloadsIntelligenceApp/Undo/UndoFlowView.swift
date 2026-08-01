import SwiftUI

/// Wires one `UndoViewModel` to the real screens its `phase` maps to — the
/// sheet content `AppShell` presents over Execute's result screen,
/// mirroring `ExecuteFlowView`'s own "one implementation per view model"
/// pattern.
///
/// Unlike `ExecuteFlowView`, this view has no `.task` performing an
/// initial fresh read: `UndoViewModel.phase` starts at `.confirming`
/// directly, seeded at construction from the already-verified,
/// already-in-memory `ExecuteResultProjection.filedRows` — there is
/// nothing to re-read from disk before the confirmation dialog can be
/// shown (see `UndoViewModel`'s own documentation for why).
struct UndoFlowView: View {
    @ObservedObject private var viewModel: UndoViewModel
    private let onBackToHome: () -> Void

    init(viewModel: UndoViewModel, onBackToHome: @escaping () -> Void) {
        self.viewModel = viewModel
        self.onBackToHome = onBackToHome
    }

    var body: some View {
        Group {
            switch viewModel.phase {
            case .confirming:
                UndoConfirmationView(
                    totalToUndo: viewModel.totalToUndo,
                    onUndo: { Task { await viewModel.confirmAndUndo() } },
                    onCancel: onBackToHome
                )
            case .undoing:
                ProgressIndicatorView(.indeterminate)
                    .padding(32)
                    .frame(minWidth: 360, maxWidth: 480)
                    .accessibilityLabel("Undoing")
            case .result(let result):
                UndoResultView(result: result, onBackToHome: onBackToHome)
            case .failed(let presentation):
                // Mirrors `ExecuteFlowView`'s own identical handling: no
                // `onResolutionAction` wired here either, the same
                // proven precedent this work package reuses rather than
                // inventing new behavior for. The sheet remains dismissible
                // via the platform's own swipe/Escape gesture even when a
                // presentation's `resolutionActionTitle` button has nowhere
                // meaningful to route to inside a Dialog context.
                ErrorStateView(presentation)
            }
        }
    }
}
