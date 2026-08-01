import XCTest
@testable import DownloadsIntelligenceApp

/// Verifies `AIProviderSettingsProjection`'s pure derivation against
/// High-Fidelity UI Specification §13's Content Specification and UX
/// Acceptance Criteria — not against this package's own restatement of
/// that spec.
final class AIProviderSettingsProjectionTests: XCTestCase {

    // MARK: - Off state

    func test_off_withDisclosureNotYetShown_reportsOffAndEnableNotReachable() {
        let projection = AIProviderSettingsProjection.compute(isEnabled: false, hasShownDisclosure: false)

        XCTAssertEqual(projection.status, .off)
        XCTAssertEqual(projection.title, "AI-assisted classification")
        XCTAssertEqual(projection.statusLabel, "Status: Off")
        XCTAssertFalse(
            projection.isEnableReachable,
            "§13 UX Acceptance Criteria: 'No path exists to enable this mode without seeing the full disclosure first.'"
        )
    }

    func test_off_withDisclosureShown_reportsEnableReachable() {
        let projection = AIProviderSettingsProjection.compute(isEnabled: false, hasShownDisclosure: true)

        XCTAssertEqual(projection.status, .off)
        XCTAssertTrue(projection.isEnableReachable)
    }

    // MARK: - On state

    func test_on_reportsOnRegardlessOfDisclosureFlag() {
        // Disable carries no disclosure gate (§13 Content Specification lists
        // only "Enable" as disclosure-gated) — the on state must never be
        // blocked by a stale/unset `hasShownDisclosure` value.
        for hasShownDisclosure in [true, false] {
            let projection = AIProviderSettingsProjection.compute(isEnabled: true, hasShownDisclosure: hasShownDisclosure)

            XCTAssertEqual(projection.status, .on)
            XCTAssertEqual(projection.title, "AI-assisted classification is on")
            XCTAssertEqual(projection.statusLabel, "Status: On")
        }
    }

    // MARK: - Success message (§13 States: quiet, non-celebratory confirmation)

    func test_successMessage_forOn() {
        XCTAssertEqual(
            AIProviderSettingsProjection.successMessage(forNewStatus: .on),
            "AI-assisted classification is now on."
        )
    }

    func test_successMessage_forOff() {
        XCTAssertEqual(
            AIProviderSettingsProjection.successMessage(forNewStatus: .off),
            "AI-assisted classification is now off."
        )
    }

    // MARK: - Equatable (used directly by SwiftUI diffing / view-model tests)

    func test_equatable_sameInputsProduceEqualProjections() {
        let a = AIProviderSettingsProjection.compute(isEnabled: false, hasShownDisclosure: true)
        let b = AIProviderSettingsProjection.compute(isEnabled: false, hasShownDisclosure: true)
        XCTAssertEqual(a, b)
    }
}
