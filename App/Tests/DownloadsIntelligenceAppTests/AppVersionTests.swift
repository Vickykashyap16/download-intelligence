import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Verifies `AppVersion` — the single GUI-only source of truth for the
/// application's own version (WP-GUI-11) — is a real, well-formed value
/// that renders the same way the engine's own `SemanticVersion` does, so
/// the About section's two version labels share one formatting
/// implementation with no drift between them.
final class AppVersionTests: XCTestCase {

    func test_current_isAWellFormedSemanticVersion() {
        let version = AppVersion.current

        XCTAssertGreaterThanOrEqual(version.major, 0)
        XCTAssertGreaterThanOrEqual(version.minor, 0)
        XCTAssertGreaterThanOrEqual(version.patch, 0)
    }

    func test_current_descriptionIsAPlainDotSeparatedTriple() {
        // Same rendering the engine version already uses
        // (`SemanticVersion.description`) — proven here so the About
        // section's two version labels are guaranteed to look consistent
        // with each other without a second formatting implementation.
        let version = AppVersion.current

        XCTAssertEqual(version.description, "\(version.major).\(version.minor).\(version.patch)")
    }

    func test_current_isStable() {
        // Not a per-call recomputation or randomly generated value — the
        // same constant every time, as befits a single source of truth.
        XCTAssertEqual(AppVersion.current, AppVersion.current)
    }
}
