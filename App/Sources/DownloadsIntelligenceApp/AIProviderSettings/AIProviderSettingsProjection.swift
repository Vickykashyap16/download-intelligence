import Foundation

/// The read-through projection AI Provider Settings renders — a pure,
/// deterministic computation over the engine's current on/off status
/// (`EngineConfiguration.aiProviderConsent`, read via
/// `EngineBridge.readConfiguration()`) plus one piece of local GUI-only
/// state, `hasShownDisclosure`, with no filesystem or network I/O of its
/// own (`ReportsProjection`/`HistoryProjection`'s own established "pure,
/// deterministic, I/O-free computation" pattern, reused here rather than
/// inventing a new one). Deliberately kept thin — this screen has exactly
/// one status field and one gated action, not a multi-entity domain model.
///
/// **Why `hasShownDisclosure` is a projection input, not something this
/// type infers.** High-Fidelity UI Specification §13's Content
/// Specification is explicit that "Enable" is "off state, only reachable
/// after the disclosure has been shown — not a simple toggle," and §13's
/// UX Acceptance Criteria states "No path exists to enable this mode
/// without seeing the full disclosure first." A pure model has no way to
/// observe what the view has actually rendered on screen; it can only
/// combine a caller-supplied fact (has the disclosure been shown this
/// session) with the engine's own current status to decide whether Enable
/// is reachable. `AIProviderSettingsViewModel`/`AIProviderSettingsView` are
/// the actual place that sets this flag to `true` — the moment the
/// disclosure text has rendered, never before — so the structural
/// guarantee comes from that wiring, not from this type alone; this type
/// only refuses to report "reachable" until told to.
///
/// **What this projection deliberately does not do.** It does not attempt
/// to classify a failed Enable attempt as "offline" versus any other kind
/// of failure. §13's own States section names an Offline state ("We
/// couldn't reach the AI service — check your connection and try again"),
/// but the engine's own `provider enable` (`src/cli.py`'s
/// `_provider_enable()`) makes no network call at all today — it only
/// checks that `ANTHROPIC_API_KEY` is set locally (`WP-GUI-12 Dependency
/// Re-Verification and Implementation Plan.md` §2, finding 2). Per the
/// approved WP-GUI-12 plan, the GUI does not add its own independent
/// network-validation call to paper over that gap: network communication
/// with AI providers belongs to the engine/provider layer, and a
/// GUI-owned HTTP client would duplicate provider logic and create a
/// second source of truth. This projection and `AIProviderSettingsViewModel`
/// therefore report only a single, generic failure presentation for a
/// failed Enable/Disable — sourced from the real `CommandResult`/
/// `EngineBridgeError` the failing invocation actually produced, the same
/// "engine is sole source of truth" discipline every other mutating
/// ViewModel in this app already follows — rather than fabricating an
/// Offline-specific message the engine cannot today support. This is a
/// disclosed, documented limitation, not a silently dropped requirement:
/// if live connectivity verification is ever added, it belongs in the
/// engine, exposed through `EngineCommand`/`EngineBridge`, at which point
/// this projection can gain a real Offline case.
public struct AIProviderSettingsProjection: Equatable, Sendable {
    public enum Status: Equatable, Sendable {
        case off
        case on
    }

    public let status: Status
    /// §13 Content Specification: "AI-assisted classification" (off state)
    /// or "AI-assisted classification is on" (on state).
    public let title: String
    /// §13 Content Specification: "Status: Off" / "Status: On."
    public let statusLabel: String
    /// §13 Content Specification: "'Enable' (off state, only reachable
    /// after the disclosure has been shown — not a simple toggle)." Only
    /// meaningful in the `.off` state — the on state's own action is
    /// "Disable," which carries no disclosure gate.
    public let isEnableReachable: Bool

    public init(status: Status, title: String, statusLabel: String, isEnableReachable: Bool) {
        self.status = status
        self.title = title
        self.statusLabel = statusLabel
        self.isEnableReachable = isEnableReachable
    }

    public static func compute(isEnabled: Bool, hasShownDisclosure: Bool) -> AIProviderSettingsProjection {
        let status: Status = isEnabled ? .on : .off
        return AIProviderSettingsProjection(
            status: status,
            title: isEnabled ? "AI-assisted classification is on" : "AI-assisted classification",
            statusLabel: isEnabled ? "Status: On" : "Status: Off",
            isEnableReachable: hasShownDisclosure
        )
    }

    /// §13 States: "a quiet confirmation after enabling or disabling
    /// ('AI-assisted classification is now on/off'), non-celebratory."
    public static func successMessage(forNewStatus status: Status) -> String {
        switch status {
        case .on:
            return "AI-assisted classification is now on."
        case .off:
            return "AI-assisted classification is now off."
        }
    }
}
