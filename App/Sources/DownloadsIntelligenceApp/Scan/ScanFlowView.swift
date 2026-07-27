import SwiftUI

/// Wires one `ScanViewModel` to the three real screens its `phase` maps to.
/// The single shared container both of WP-GUI-04's entry points (Home's
/// "Scan now"/"Scan again," and First Run Experience's "Scan now") render —
/// exactly the same "one implementation, reused by every call site that can
/// reach it" pattern `AppShell`'s previous placeholder (`scanProgressStub`)
/// already established for this same pair of entry points.
struct ScanFlowView: View {
    @ObservedObject private var viewModel: ScanViewModel
    private let onReview: () -> Void
    private let onFileNow: () -> Void
    private let extraCompletionActionTitle: String?
    private let extraCompletionAction: (() -> Void)?

    init(
        viewModel: ScanViewModel,
        onReview: @escaping () -> Void,
        onFileNow: @escaping () -> Void,
        extraCompletionActionTitle: String? = nil,
        extraCompletionAction: (() -> Void)? = nil
    ) {
        self.viewModel = viewModel
        self.onReview = onReview
        self.onFileNow = onFileNow
        self.extraCompletionActionTitle = extraCompletionActionTitle
        self.extraCompletionAction = extraCompletionAction
    }

    var body: some View {
        Group {
            switch viewModel.phase {
            case .running(let progressPhase):
                ScanProgressView(phase: progressPhase)
            case .complete(let projection):
                ScanCompleteView(
                    projection: projection,
                    onReview: onReview,
                    onFileNow: onFileNow,
                    extraSecondaryActionTitle: extraCompletionActionTitle,
                    extraSecondaryAction: extraCompletionAction
                )
            case .failed(let presentation):
                ErrorStateView(presentation)
            }
        }
        .task {
            await viewModel.start()
        }
    }
}
