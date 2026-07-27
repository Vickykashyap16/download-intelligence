import SwiftUI
import EngineBridge

/// The `.firstRunNeeded` phase's real content: Welcome, then First Run
/// Experience once "Get started" is pressed (`High-Fidelity UI
/// Specification.md` §1: "Primary Action: 'Get started' — proceeds to
/// First Run Experience"). Replaces WP-GUI-01's routing-only placeholder in
/// `AppShell` (an `EmptyStateView` explicitly documented there as "a
/// routing placeholder only, per WP-GUI-01's own 'out of scope: any
/// screen's real content'" — WP-GUI-02 is the work package that owns this
/// phase's real content).
///
/// `hasStarted` is disposable, session-local UI state — which of these two
/// screens is currently showing carries no business meaning of its own
/// (`GUI Architecture Specification.md` §7); the only state with real
/// consequence in this whole flow is the configuration this leads to
/// writing, which is verified and re-read from the engine itself, never
/// held only here.
public struct OnboardingFlowView: View {
    private let bridge: EngineBridge
    private let onScanRequested: () -> Void
    @State private var hasStarted = false

    public init(bridge: EngineBridge, onScanRequested: @escaping () -> Void) {
        self.bridge = bridge
        self.onScanRequested = onScanRequested
    }

    public var body: some View {
        if hasStarted {
            FirstRunExperienceView(bridge: bridge, onScanRequested: onScanRequested)
        } else {
            WelcomeView { hasStarted = true }
        }
    }
}
