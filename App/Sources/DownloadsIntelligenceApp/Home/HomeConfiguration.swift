import Foundation

/// Home's tunable, non-business-rule configuration values, gathered into a
/// single named location. Previously these lived in two different places —
/// `HomeProjection.weeklyWindowInDays` and a bare `30` literal default in
/// `HomeViewModel.startPeriodicRefresh(interval:)` — with no shared home.
/// Neither `Desktop Implementation Blueprint.md` nor `High-Fidelity UI
/// Specification.md` fixes exact values for either of these; both are
/// small, implementation-time defaults in the same spirit as
/// `Package.swift`'s macOS-13 and SwiftUI choices. Values are unchanged
/// from their prior defaults (7 days, 30 seconds) — this type only
/// relocates them.
public enum HomeConfiguration {
    /// How many days back "This week" (`High-Fidelity UI Specification.md`
    /// §2, "the trend summary") looks from `now`. A rolling window is the
    /// simplest honest reading of "this week" that requires no assumption
    /// about the user's locale-specific week start day. See
    /// `HomeProjection.compute(records:now:)`.
    public static let weeklyTrendWindowInDays = 7

    /// The default interval, in seconds, at which `HomeViewModel` re-reads
    /// the Engine Bridge while Home is on screen (`Desktop Implementation
    /// Blueprint.md` §2, Idle phase: "refreshing Home's status on a modest
    /// periodic interval"). Callers — tests, in particular — may pass a
    /// much shorter interval to `startPeriodicRefresh(interval:)` to
    /// observe re-polling without a real 30-second wait.
    public static let defaultRefreshInterval: TimeInterval = 30
}
