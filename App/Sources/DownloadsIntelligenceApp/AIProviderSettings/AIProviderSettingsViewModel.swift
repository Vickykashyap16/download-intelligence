import Foundation
import EngineBridge

/// Drives the AI Provider Settings screen (WP-GUI-12) against a real
/// `EngineBridge` and a `CredentialStore` (production: `KeychainCredentialStore`).
///
/// **Scope, per the approved WP-GUI-12 plan.** "GUI is responsible only
/// for: disclosure, credential collection, secure Keychain storage,
/// invoking the existing engine command, displaying the verified result" —
/// never an independent network-validation call of its own. Option A
/// (a GUI-owned connectivity check before enabling) was explicitly
/// rejected: network communication with AI providers belongs to the
/// engine/provider layer, and a GUI-owned HTTP client would duplicate
/// provider logic and create a second source of truth. See
/// `AIProviderSettingsProjection`'s own documentation for the full
/// reasoning behind that decision and what it means for this type's error
/// handling below.
///
/// **`enable(credential:)` does exactly four things, in order:** store the
/// credential via `credentialStore`, invoke `provider enable -y` with the
/// credential supplied through `additionalEnvironment` (never written to
/// `sources.yaml`, never logged — INFRA-01 / OD-GUI-6's own structural
/// leak-safety guarantee), re-read `EngineConfiguration` to confirm
/// `aiProviderConsent` actually flipped, and update `projection` from that
/// re-read. `disable()` mirrors this for the reverse direction, minus the
/// credential step. Both follow the exact "engine is sole source of truth,
/// no optimistic success" discipline `SettingsViewModel.chooseSourceFolder`/
/// `UndoViewModel.confirmAndUndo` already establish elsewhere in this app:
/// neither method ever treats a successful `CommandResult` alone as proof
/// the change took effect.
///
/// **Disclosure gating.** `markDisclosureShown()` is the one call site
/// that ever sets the projection's `hasShownDisclosure` input to `true`;
/// `AIProviderSettingsView`'s off-state body calls it once its disclosure
/// text has actually rendered — before ever constructing the Enable
/// button — per High-Fidelity UI Specification §13's "no path exists to
/// enable this mode without seeing the full disclosure first." `enable(
/// credential:)` itself also refuses to proceed if `projection.
/// isEnableReachable` is `false`, as a second, structural guard against
/// this same rule, not merely a UI-level one.
///
/// `@MainActor` because every published property drives SwiftUI view state
/// directly, matching every other ViewModel in this project.
@MainActor
public final class AIProviderSettingsViewModel: ObservableObject {
    @Published public private(set) var isLoading = true
    @Published public private(set) var projection: AIProviderSettingsProjection = .compute(isEnabled: false, hasShownDisclosure: false)
    @Published public private(set) var isSubmitting = false
    @Published public private(set) var successMessage: String?

    /// Set only by `load()` — a failure to even determine the current
    /// on/off status, screen-level per `AIProviderSettingsView` (full
    /// Error State, replacing the screen). Kept as its own property, never
    /// sharing storage with `errorPresentation` below, mirroring
    /// `SettingsViewModel`'s own `configurationError`/`engineVersionError`
    /// isolation: a load failure and an Enable/Disable failure are
    /// genuinely different situations (§13 States distinguishes them too —
    /// a load failure has no known status to fall back to display, whereas
    /// an Enable/Disable failure explicitly "remains off [or on]," a known,
    /// still-displayable status), and collapsing them into one property
    /// would force the view to guess which situation it's in rather than
    /// being told directly.
    @Published public private(set) var loadErrorPresentation: ErrorPresentation?

    /// Set only by `enable(credential:)`/`disable()` — shown inline,
    /// alongside the still-visible current status, never replacing the
    /// whole screen the way `loadErrorPresentation` does.
    @Published public private(set) var errorPresentation: ErrorPresentation?

    /// Backing state `projection` is recomputed from — kept private so
    /// `projection` (the `Equatable`, view-facing snapshot) is the only
    /// thing any caller outside this type ever reads.
    private var isEnabled = false
    private var hasShownDisclosure = false

    private let bridge: EngineBridge
    private let credentialStore: CredentialStore

    public init(bridge: EngineBridge, credentialStore: CredentialStore = KeychainCredentialStore()) {
        self.bridge = bridge
        self.credentialStore = credentialStore
    }

    // MARK: - Loading

    /// Loads the current on/off status. Safe to call again on every screen
    /// entry, mirroring `SettingsViewModel.load()`'s own "always re-read
    /// rather than trusting stale state" precedent. Does not reset
    /// `hasShownDisclosure` — once the disclosure has rendered during this
    /// screen's lifetime, re-loading the status alone should not re-hide
    /// the Enable action behind it again.
    public func load() async {
        isLoading = true
        defer { isLoading = false }

        loadErrorPresentation = nil
        do {
            let configuration = try await bridge.readConfiguration()
            isEnabled = configuration.aiProviderConsent
            refreshProjection()
        } catch let error as EngineBridgeError {
            loadErrorPresentation = .forEngineBridgeFailure(error)
        } catch {
            loadErrorPresentation = Self.unexpectedFailurePresentation(detail: String(describing: error))
        }
    }

    // MARK: - Disclosure gating

    public func markDisclosureShown() {
        guard !hasShownDisclosure else { return }
        hasShownDisclosure = true
        refreshProjection()
    }

    // MARK: - Enable

    /// Stores `credential` via `credentialStore`, then invokes
    /// `provider enable -y` with it delivered through
    /// `additionalEnvironment`. No-ops if `projection.isEnableReachable`
    /// is `false` (disclosure not yet shown) — a structural guard mirroring
    /// the one `AIProviderSettingsView` already applies at the UI level.
    public func enable(credential: String) async {
        guard projection.isEnableReachable else { return }

        errorPresentation = nil
        successMessage = nil
        isSubmitting = true
        defer { isSubmitting = false }

        do {
            try credentialStore.store(credential)
        } catch {
            errorPresentation = Self.credentialStoreFailedPresentation(detail: String(describing: error))
            return
        }

        do {
            let result = try await bridge.run(
                .provider(.enable(yes: true)),
                additionalEnvironment: ["ANTHROPIC_API_KEY": credential]
            )
            guard result.succeeded else {
                errorPresentation = Self.enableFailedPresentation(detail: Self.commandFailureDetail(result))
                return
            }
            let configuration = try await bridge.readConfiguration()
            guard configuration.aiProviderConsent else {
                errorPresentation = Self.enableFailedPresentation(
                    detail: "The engine reported success, but re-reading the configuration did not confirm AI-assisted classification is on."
                )
                return
            }
            isEnabled = true
            refreshProjection()
            successMessage = AIProviderSettingsProjection.successMessage(forNewStatus: .on)
        } catch let error as EngineBridgeError {
            errorPresentation = .forEngineBridgeFailure(error, layout: .inline)
        } catch {
            errorPresentation = Self.enableFailedPresentation(detail: String(describing: error))
        }
    }

    // MARK: - Disable

    /// Invokes `provider disable`, then re-reads to confirm — no
    /// disclosure gate (§13 Content Specification lists only "Enable" as
    /// disclosure-gated; Disable is "exactly as easy as turning it on,"
    /// per §10's own Acceptance Criteria, not gated behind anything
    /// additional). Does not delete the stored credential: leaving it in
    /// the Keychain lets a later re-enable skip re-entering it, and the
    /// credential is never read except at the moment of an explicit Enable
    /// action, so retaining it while disabled carries no additional
    /// exposure beyond what Enable already accepted.
    public func disable() async {
        errorPresentation = nil
        successMessage = nil
        isSubmitting = true
        defer { isSubmitting = false }

        do {
            let result = try await bridge.run(.provider(.disable))
            guard result.succeeded else {
                errorPresentation = Self.disableFailedPresentation(detail: Self.commandFailureDetail(result))
                return
            }
            let configuration = try await bridge.readConfiguration()
            guard !configuration.aiProviderConsent else {
                errorPresentation = Self.disableFailedPresentation(
                    detail: "The engine reported success, but re-reading the configuration did not confirm AI-assisted classification is off."
                )
                return
            }
            isEnabled = false
            refreshProjection()
            successMessage = AIProviderSettingsProjection.successMessage(forNewStatus: .off)
        } catch let error as EngineBridgeError {
            errorPresentation = .forEngineBridgeFailure(error, layout: .inline)
        } catch {
            errorPresentation = Self.disableFailedPresentation(detail: String(describing: error))
        }
    }

    // MARK: - Dismissal

    public func dismissError() {
        errorPresentation = nil
    }

    public func dismissLoadError() {
        loadErrorPresentation = nil
    }

    public func dismissSuccessMessage() {
        successMessage = nil
    }

    // MARK: - Presentation helpers

    private func refreshProjection() {
        projection = AIProviderSettingsProjection.compute(isEnabled: isEnabled, hasShownDisclosure: hasShownDisclosure)
    }

    /// §13 States: "if enabling fails... a plain, actionable message
    /// appears, and the mode remains off until it can be confirmed." This
    /// is deliberately one generic failure presentation, not an
    /// Offline-specific one — the engine's `provider enable` makes no
    /// network call today (see `AIProviderSettingsProjection`'s own
    /// documentation), so this GUI cannot honestly distinguish "offline"
    /// from any other failure without adding its own independent network
    /// check, which the approved WP-GUI-12 plan explicitly rules out. This
    /// is a disclosed, documented limitation, not a silently dropped
    /// requirement.
    // `layout: .inline` for all three below — `AIProviderSettingsView`
    // renders each of these alongside the still-visible status statement
    // and screen content, never replacing the whole screen the way
    // `loadErrorPresentation`'s `.fullScreen` presentation does (see that
    // property's own documentation for why the two are kept separate).

    private static func enableFailedPresentation(detail: String) -> ErrorPresentation {
        ErrorPresentation(
            heading: "Couldn't turn this on",
            explanation: "The app tried to enable AI-assisted classification, but couldn't confirm it took effect. Nothing has changed — the mode remains off, and you can try again.",
            resolutionActionTitle: "Try again",
            technicalDetail: detail,
            layout: .inline
        )
    }

    private static func disableFailedPresentation(detail: String) -> ErrorPresentation {
        ErrorPresentation(
            heading: "Couldn't turn this off",
            explanation: "The app tried to disable AI-assisted classification, but couldn't confirm it took effect. You can try again.",
            resolutionActionTitle: "Try again",
            technicalDetail: detail,
            layout: .inline
        )
    }

    private static func credentialStoreFailedPresentation(detail: String) -> ErrorPresentation {
        ErrorPresentation(
            heading: "Couldn't save your API key",
            explanation: "The app couldn't securely store your API key, so AI-assisted classification was not enabled. Nothing has changed.",
            resolutionActionTitle: "Try again",
            technicalDetail: detail,
            layout: .inline
        )
    }

    private static func unexpectedFailurePresentation(detail: String) -> ErrorPresentation {
        ErrorPresentation(
            heading: "Something went wrong",
            explanation: "The app couldn't load the current AI provider status.",
            resolutionActionTitle: "Try again",
            technicalDetail: detail,
            layout: .fullScreen
        )
    }

    private static func commandFailureDetail(_ result: CommandResult) -> String {
        let errorOutput = result.standardError.trimmingCharacters(in: .whitespacesAndNewlines)
        let output = result.standardOutput.trimmingCharacters(in: .whitespacesAndNewlines)
        let detail = !errorOutput.isEmpty ? errorOutput : output
        return "\(result.command) exited with code \(result.exitCode)\(detail.isEmpty ? "" : ": \(detail)")"
    }
}
