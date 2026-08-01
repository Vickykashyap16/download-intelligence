import SwiftUI
import EngineBridge

/// Settings' top-level screen (`High-Fidelity UI Specification.md` §12;
/// `Downloads Intelligence — Figma Design Production Guide.md` frame `13`):
/// Source & Destination folder settings, reusing exactly the same
/// `FolderPathView`/`FolderPicker`/`FolderValidationMessage` presentation
/// Onboarding already established, plus an About section reporting both the
/// real application and engine version (WP-GUI-11 Acceptance Criteria).
///
/// AI Provider Settings (the disclosure-gated provider entry Hi-Fi §12
/// mentions) and the undocumented "Documentation" label item are both out
/// of this work package's scope (WP-GUI-11's own Scope: "Out of scope: AI
/// Provider Settings, next milestone"; "Documentation" has no defined
/// destination anywhere in this project's design documents and is not
/// listed in WP-GUI-11's own Deliverables/Acceptance Criteria) — this
/// screen is deliberately just the two sections WP-GUI-11 actually commits
/// to, laid out so a future work package can add a third selector entry
/// additively, the same way `AppShell`'s own switch already extends
/// additively per section.
public struct SettingsView: View {
    @ObservedObject private var viewModel: SettingsViewModel

    public init(viewModel: SettingsViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let configurationError = viewModel.configurationError {
                // A configuration-load failure is screen-level here (unlike
                // Reports' four independently-isolated artifacts, Settings'
                // folder fields come from one single configuration read) —
                // the same shared Error State component every other
                // screen-level failure in this project uses.
                ErrorStateView(configurationError) {
                    Task { await viewModel.load() }
                }
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 32) {
                        sourceSection
                        destinationSection
                        aboutSection
                    }
                    .frame(maxWidth: 480, alignment: .leading)
                    .padding()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task {
            await viewModel.load()
        }
    }

    // MARK: - Source

    @ViewBuilder
    private var sourceSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Watching")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)

            if let sourceURL = viewModel.sourceURL {
                FolderPathView(
                    path: sourceURL.path,
                    validationMessage: viewModel.sourceValidation.flatMap(FolderValidationMessage.inline(for:)),
                    isValidating: viewModel.isValidatingSource
                )
            } else {
                Text("No folder configured yet.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }

            SecondaryButton(
                viewModel.isSavingSource ? "Saving…" : "Choose a different folder",
                isDisabled: viewModel.isSavingSource
            ) {
                let startingURL = viewModel.sourceURL ?? FirstRunExperienceViewModel.detectedDownloadsFolder()
                if let url = FolderPicker.chooseFolder(startingAt: startingURL) {
                    Task { await viewModel.chooseSourceFolder(url) }
                }
            }
        }
    }

    // MARK: - Destination

    @ViewBuilder
    private var destinationSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Sorting into")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)

            if let destinationURL = viewModel.destinationURL {
                FolderPathView(
                    path: destinationURL.path,
                    validationMessage: viewModel.destinationValidation.flatMap(FolderValidationMessage.inline(for:)),
                    isValidating: viewModel.isValidatingDestination
                )
            } else {
                Text("No folder configured yet.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }

            SecondaryButton(
                viewModel.isSavingDestination ? "Saving…" : "Choose a different folder",
                isDisabled: viewModel.isSavingDestination
            ) {
                let startingURL = viewModel.destinationURL ?? FirstRunExperienceViewModel.suggestedDestinationFolder()
                if let url = FolderPicker.chooseFolder(startingAt: startingURL) {
                    Task { await viewModel.chooseDestinationFolder(url) }
                }
            }
        }
    }

    // MARK: - About

    @ViewBuilder
    private var aboutSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("About")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)

            // Hi-Fi §12's own "Metadata: current app version, in the About
            // section" plus WP-GUI-11's own Acceptance Criteria ("the About
            // section correctly reports the current, real application and
            // engine version") — both are shown, each labeled unambiguously
            // rather than sharing one generic "Version" line.
            Text("App version \(viewModel.appVersion.description)")
                .font(.body)
                .foregroundStyle(.secondary)

            if let engineVersion = viewModel.engineVersion {
                Text("Engine version \(engineVersion.description)")
                    .font(.body)
                    .foregroundStyle(.secondary)
            } else if let engineVersionError = viewModel.engineVersionError {
                // Isolated, inline — a failure here never affects the
                // folder settings above (`SettingsViewModel`'s own
                // documentation).
                ErrorStateView(engineVersionError) {
                    Task { await viewModel.load() }
                }
            }
        }
    }
}
