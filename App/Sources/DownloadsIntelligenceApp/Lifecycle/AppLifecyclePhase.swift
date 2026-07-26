import Foundation

/// The fixed sequence of phases the application moves through on every
/// launch (`Desktop Implementation Blueprint.md` §2). WP-GUI-01 implements
/// this sequence through "Display Home" with Home itself as a placeholder,
/// per WP-GUI-01's own Definition of Done ("the application's launch-to-
/// shell sequence matches the lifecycle phases... through 'Display Home'
/// (even though Home itself is a placeholder at this stage)"). The phases
/// after Display Home (Idle, Shutdown) and the real content behind each
/// Sidebar section are out of this work package's scope.
public enum AppLifecyclePhase: Equatable, Sendable {
    case launching
    case initializing
    case loadingConfiguration
    case checkingEngineReadiness
    case readingMetadata
    case restoringWindowState

    /// The lifecycle's terminal success state for WP-GUI-01's scope —
    /// Home's real content is a future work package's deliverable.
    case displayingHome

    /// "The configuration is entirely absent... this is a first-time
    /// setup and the lifecycle diverts to First Run Experience instead of
    /// continuing toward Home" (`Desktop Implementation Blueprint.md` §2).
    /// Represented here only as a named routing destination so the branch
    /// itself is exercised and tested now, even though First Run
    /// Experience's real screen content is WP-GUI-02's scope, not
    /// WP-GUI-01's.
    case firstRunNeeded

    /// "The configuration is present but unreadable/malformed, which
    /// routes immediately to the Config Corrupted error path" or the
    /// Engine Bridge readiness check failed and "diverts to the Python
    /// Missing or Engine Unavailable error path" (`Desktop Implementation
    /// Blueprint.md` §2) — both route to the shared Error State.
    case error(ErrorPresentation)
}
