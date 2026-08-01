import SwiftUI

/// Wires one `ExecuteViewModel` to the real screens its `phase` maps to —
/// the single shared container both of Execute's entry points (Preview's
/// "Execute now," Scan Complete's "File the N now") render, mirroring
/// `ScanFlowView`'s own "one implementation, reused by every call site that
/// can reach it" pattern.
struct ExecuteFlowView: View {
    @ObservedObject private var viewModel: ExecuteViewModel
    private let onCancel: () -> Void
    private let onUndo: () -> Void
    private let onBackToHome: () -> Void

    init(
        viewModel: ExecuteViewModel,
        onCancel: @escaping () -> Void,
        onUndo: @escaping () -> Void,
        onBackToHome: @escaping () -> Void
    ) {
        self.viewModel = viewModel
        self.onCancel = onCancel
        self.onUndo = onUndo
        self.onBackToHome = onBackToHome
    }

    var body: some View {
        Group {
            switch viewModel.phase {
            case .loadingConfirmation:
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .confirming(let projection):
                ExecuteConfirmationView(
                    projection: projection,
                    onFileThem: { Task { await viewModel.confirmAndExecute() } },
                    onCancel: onCancel
                )
            case .nothingToFile:
                // A fresh re-read found nothing eligible left to file — the
                // batch changed out from under an already-displayed
                // confirmation screen (§8 States: this screen is only
                // reached with a non-zero batch; this is the defensive
                // fallback for that assumption no longer holding by the
                // time "File them" is actually pressed).
                EmptyStateView(
                    systemImageName: "checkmark.circle",
                    heading: "Nothing left to file",
                    explanation: "The plan changed since you opened this screen — there's nothing eligible to file right now.",
                    secondaryActionTitle: "Back to Home",
                    secondaryAction: onCancel
                )
            case .executing:
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityLabel("Filing")
            case .result(let result):
                ExecuteResultView(result: result, onUndo: onUndo, onBackToHome: onBackToHome)
            case .failed(let presentation):
                ErrorStateView(presentation)
            }
        }
        .task {
            await viewModel.loadConfirmation()
        }
    }
}
