import EngineBridge

/// The GUI application's own version — distinct from, and always displayed
/// alongside, the engine's own version (`EngineBridge.currentEngineVersion()`).
/// WP-GUI-11's own Acceptance Criteria requires the About section to report
/// "the current, real application and engine version," but no such concept
/// existed anywhere in this codebase before this work package (confirmed:
/// no `Info.plist`, no `Package.swift` version field, no prior app-version
/// constant) — this is the single GUI-only source of truth that value comes
/// from, kept at the top level alongside `AppSection.swift` since it is an
/// application-wide fact, not something scoped to the Settings screen alone.
///
/// Deliberately a plain, hardcoded constant rather than anything read from
/// real packaging metadata: this project has no distribution
/// packaging/bundle-versioning pipeline yet (out of this work package's
/// small scope, and out of any GUI work package's scope to date), so
/// inventing one here would be exactly the kind of unauthorized new
/// capability this project's engineering discipline avoids. When real
/// packaging exists, this is the one place that would change.
///
/// Reuses `EngineBridge.SemanticVersion` — a small, dependency-free value
/// type with no knowledge of any specific artifact or file — for the same
/// `MAJOR.MINOR.PATCH` shape and `description` rendering the engine version
/// already uses, so both versions in the About section render identically
/// via the same, single formatting implementation. This is ordinary reuse
/// of an existing public type, not a change to `EngineBridge` itself.
///
/// **This is the single GUI-only source of truth for the application
/// version.** No other file in this target should hardcode the app version
/// as a literal string or number — `SettingsViewModel` reads it only from
/// `AppVersion.current`, and `SettingsView` only ever displays that same
/// value, never a value it computes or stores itself. If the version
/// changes in the future, updating `current` below is the one and only
/// change needed to update the entire Settings/About screen.
public enum AppVersion {
    public static let current = SemanticVersion(major: 0, minor: 1, patch: 0)
}
