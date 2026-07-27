import SwiftUI
import EngineBridge

/// The three-step guided setup itself (`High-Fidelity UI Specification.md`
/// §16). "no Sidebar Navigation during this flow... a focused, linear
/// sequence with its own back/step-indicator chrome instead" (§16, Layout
/// Specification) — this view renders standalone, with no
/// `NavigationSplitView`/Sidebar, matching Welcome's own exception to the
/// otherwise-universal Sidebar pattern.
public struct FirstRunExperienceView: View {
    @StateObject private var viewModel: FirstRunExperienceViewModel

    public init(bridge: EngineBridge, onScanRequested: @escaping () -> Void) {
        _viewModel = StateObject(wrappedValue: FirstRunExperienceViewModel(
            bridge: bridge,
            onScanRequested: onScanRequested
        ))
    }

    public var body: some View {
        Group {
            if let errorPresentation = viewModel.errorPresentation {
                // "Config corrupted... routes to an Error State" (`Desktop
                // Implementation Blueprint.md` §8) — the same shared
                // component every other screen's failure uses, never a
                // bespoke per-screen treatment (§8: "implemented via the
                // same shared Error State component, never a bespoke
                // per-screen treatment").
                ErrorStateView(errorPresentation) {
                    viewModel.dismissError()
                }
            } else {
                stepContent
            }
        }
        .task {
            await viewModel.start()
        }
    }

    @ViewBuilder
    private var stepContent: some View {
        VStack(alignment: .leading, spacing: 24) {
            HStack {
                if viewModel.currentStep.canGoBack {
                    SecondaryButton("Back") { viewModel.goBack() }
                }
                Spacer()
                Text(viewModel.currentStep.indicatorText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            switch viewModel.currentStep {
            case .source:
                sourceStep
            case .destination:
                destinationStep
            case .readyToScan:
                readyToScanStep
            }

            Spacer(minLength: 0)
        }
        .frame(maxWidth: 480)
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var sourceStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Where should we watch for downloads?")
                .font(.title2.weight(.semibold))
                .accessibilityAddTraits(.isHeader)

            FolderPathView(
                path: viewModel.sourceURL.path,
                validationMessage: viewModel.sourceValidation.flatMap(FolderValidationMessage.inline(for:)),
                isValidating: viewModel.isValidatingSource
            )

            SecondaryButton("Choose a different folder") {
                if let url = FolderPicker.chooseFolder(startingAt: viewModel.sourceURL) {
                    Task { await viewModel.chooseSourceFolder(url) }
                }
            }

            Text("We only read files here. Nothing moves until you say so.")
                .font(.callout)
                .foregroundStyle(.secondary)

            PrimaryButton(
                viewModel.isSaving ? "Saving…" : "Continue",
                isDisabled: !viewModel.isSourceStepValid || viewModel.isSaving
            ) {
                Task { await viewModel.continueFromSource() }
            }
        }
    }

    private var destinationStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Where should sorted files go?")
                .font(.title2.weight(.semibold))
                .accessibilityAddTraits(.isHeader)

            FolderPathView(
                path: viewModel.destinationURL.path,
                validationMessage: viewModel.destinationValidation.flatMap(FolderValidationMessage.inline(for:)),
                isValidating: viewModel.isValidatingDestination
            )

            SecondaryButton("Choose a different folder") {
                if let url = FolderPicker.chooseFolder(startingAt: viewModel.destinationURL) {
                    Task { await viewModel.chooseDestinationFolder(url) }
                }
            }

            Text("Files are organized into a few plain folders here — Documents, Finance, Images, Videos, and so on.")
                .font(.callout)
                .foregroundStyle(.secondary)

            PrimaryButton(
                viewModel.isSaving ? "Saving…" : "Continue",
                isDisabled: !viewModel.isDestinationStepValid || viewModel.isSaving
            ) {
                Task { await viewModel.continueFromDestination() }
            }
        }
    }

    private var readyToScanStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("You're set up.")
                .font(.title2.weight(.semibold))
                .accessibilityAddTraits(.isHeader)

            // "a recap card showing both chosen paths" (§16, Step 3
            // content spec) — already-confirmed-valid at this point (both
            // writes were verified before this step was ever reached), so
            // no validation message/spinner is shown here, only the
            // checkmark state each `FolderPathView` already renders for
            // `validationMessage: nil`.
            VStack(alignment: .leading, spacing: 12) {
                FolderPathView(path: viewModel.sourceURL.path, validationMessage: nil, isValidating: false)
                FolderPathView(path: viewModel.destinationURL.path, validationMessage: nil, isValidating: false)
            }

            Text("Next, we'll look at what's in your Downloads folder — just look. Nothing will move yet.")
                .font(.callout)
                .foregroundStyle(.secondary)

            PrimaryButton("Scan now") {
                viewModel.scanNow()
            }
        }
    }
}
