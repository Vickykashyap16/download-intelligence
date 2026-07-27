import Foundation

/// Scan's tunable, non-business-rule configuration values, gathered into a
/// single named location — the same pattern `HomeConfiguration` already
/// establishes for Home's own tunables.
public enum ScanConfiguration {
    /// How often `ScanViewModel` polls `readMetadataStore()` while a scan is
    /// in flight. Scan is described throughout the UX documents as a
    /// "short, bounded" operation (`High-Fidelity UI Specification.md` §3),
    /// so a much shorter interval than Home's 30-second idle refresh
    /// (`HomeConfiguration.defaultRefreshInterval`) is appropriate here.
    /// Neither the Architecture Specification nor the High-Fidelity UI
    /// Specification fixes an exact polling cadence — this is a small,
    /// easily-revised implementation default, in the same spirit as that
    /// existing value.
    public static let progressPollInterval: TimeInterval = 0.5
}
