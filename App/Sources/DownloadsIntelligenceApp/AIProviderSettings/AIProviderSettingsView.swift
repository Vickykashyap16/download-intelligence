import SwiftUI
import EngineBridge

/// AI Provider Settings (WP-GUI-12), per `High-Fidelity UI Specification.md`
/// §13: "the dedicated, appropriately weighted home for the optional,
/// off-by-default AI-assisted classification mode." Content grouping
/// follows §13's Layout Specification exactly, top to bottom: status
/// statement → plain-language explanation → disclosure (what's sent, that
/// it costs money) → the single relevant action (Enable, or Disable) —
/// "mirroring the CLI's own disclosure-then-confirm sequence."
///
/// **The structural disclosure guarantee.** `AIProviderSettingsProjection.
/// isEnableReachable` starts `false` and only ever becomes `true` after
/// `viewModel.markDisclosureShown()` has been called — and this view's
/// off-state body calls it from `.task` attached to the disclosure text
/// itself, so by construction the disclosure has already rendered by the
/// time that call fires. The Enable button/credential field below are
/// still only ever constructed once `viewModel.projection.isEnableReachable`
/// is `true`, so there is no code path — not merely a UI convention — that
/// reaches Enable without the disclosure having rendered first, per §13's
/// UX Acceptance Criteria ("No path exists to enable this mode without
/// seeing the full disclosure first").
public struct AIProviderSettingsView: View {
    @ObservedObject private var viewModel: AIProviderSettingsViewModel
    /// Reached as a nested screen within Settings, not a Sidebar
    /// destination of its own (§13 Layout Specification) — `SettingsSectionView`
    /// owns the local, `NavigationLink`-free toggle between this screen and
    /// the rest of Settings (this app's established "local state-driven
    /// conditional view switching, never push navigation" idiom), so this
    /// closure is how that screen actually reaches this one's own way back.
    private let onBack: () -> Void
    @State private var enteredCredential = ""
    @AccessibilityFocusState private var isStatusStatementFocused: Bool

    public init(viewModel: AIProviderSettingsViewModel, onBack: @escaping () -> Void) {
        self.viewModel = viewModel
        self.onBack = onBack
    }

    public var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let loadErrorPresentation = viewModel.loadErrorPresentation {
                // A load failure (status could not even be determined) is
                // screen-level, the same shared Error State every other
                // screen-level failure in this project uses. An Enable/
                // Disable failure, by contrast (`viewModel.errorPresentation`,
                // below), is shown inline, alongside the still-visible
                // status — §13 States: "the mode remains off [or on] until
                // it can be confirmed," not replaced by an error screen.
                // The two are tracked as separate ViewModel properties
                // specifically so this view never has to guess which
                // situation it's in.
                ErrorStateView(loadErrorPresentation) {
                    Task { await viewModel.load() }
                }
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        SecondaryButton("Back to Settings", action: onBack)
                            .fixedSize()
                        statusStatement
                        if let successMessage = viewModel.successMessage {
                            Text(successMessage)
                                .font(.body)
                                .foregroundStyle(.secondary)
                        }
                        switch viewModel.projection.status {
                        case .off:
                            offStateContent
                        case .on:
                            onStateContent
                        }
                        if let errorPresentation = viewModel.errorPresentation {
                            ErrorStateView(errorPresentation) {
                                viewModel.dismissError()
                            }
                        }
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
        .onChange(of: viewModel.projection.status) { _ in
            // §13 Accessibility: "on toggling state, focus moves to the
            // updated status statement so the change is clearly announced."
            isStatusStatementFocused = true
        }
    }

    // MARK: - Status statement (§13 Content Specification: "Status: Off" / "Status: On")

    @ViewBuilder
    private var statusStatement: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(viewModel.projection.title)
                .font(.title2.weight(.semibold))
                .accessibilityAddTraits(.isHeader)

            HStack(spacing: 8) {
                // A plain, neutral status icon only — no excitement-oriented
                // iconography (§13 Content Specification).
                Image(systemName: viewModel.projection.status == .on ? "checkmark.circle" : "circle")
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
                Text(viewModel.projection.statusLabel)
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityFocused($isStatusStatementFocused)
    }

    // MARK: - Off state

    @ViewBuilder
    private var offStateContent: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("AI-assisted classification is optional and off by default. When it's on, it's used only for the harder judgment calls this app's own deterministic rules can't confidently resolve — it never runs silently, and it's never required to use this app.")
                .font(.body)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            // The disclosure itself — never smaller or less prominent than
            // body content (§13 Accessibility: "meets the same contrast
            // standard as primary body content, never de-emphasized as
            // fine print"). `.task` fires once this text has actually
            // rendered, which is what unlocks Enable below — see this
            // view's own top-level documentation.
            Text("Turning this on sends limited file metadata (never full file contents) to Anthropic's Claude API for classification, and costs real money based on your own Anthropic account's usage. See the full privacy and data-handling explanation in the app's documentation for exactly what is and isn't sent.")
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
                .task {
                    viewModel.markDisclosureShown()
                }

            if viewModel.projection.isEnableReachable {
                VStack(alignment: .leading, spacing: 12) {
                    SecureField("Anthropic API key", text: $enteredCredential)
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 320)

                    PrimaryButton(
                        viewModel.isSubmitting ? "Enabling…" : "Enable",
                        isDisabled: viewModel.isSubmitting || enteredCredential.isEmpty
                    ) {
                        let credential = enteredCredential
                        Task {
                            await viewModel.enable(credential: credential)
                        }
                    }
                }
            }
        }
    }

    // MARK: - On state

    @ViewBuilder
    private var onStateContent: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("AI-assisted classification is currently on. It's used only for the harder judgment calls this app's own deterministic rules can't confidently resolve, and every AI-assisted result stays visible per-file in its own confidence breakdown, the same as any other result.")
                .font(.body)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            SecondaryButton(
                viewModel.isSubmitting ? "Disabling…" : "Disable",
                isDisabled: viewModel.isSubmitting
            ) {
                Task {
                    await viewModel.disable()
                }
            }
        }
    }
}
