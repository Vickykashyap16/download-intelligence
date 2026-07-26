import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Verifies `ConfidenceChipModel`'s tier→label/icon/accessibility mapping
/// for all three known tiers plus the forward-compatible `.other` case,
/// and both the "With Score" and "Without Score" variants named in the
/// Figma Production Guide §2.
final class ConfidenceChipModelTests: XCTestCase {

    func test_autoTier_label() {
        XCTAssertEqual(ConfidenceChipModel(tier: .auto).label, "Auto")
    }

    func test_approvalRequiredTier_label() {
        XCTAssertEqual(ConfidenceChipModel(tier: .approvalRequired).label, "Approval Required")
    }

    func test_reviewRequiredTier_label() {
        XCTAssertEqual(ConfidenceChipModel(tier: .reviewRequired).label, "Review Required")
    }

    func test_unrecognizedTier_rendersHonestlyRatherThanGuessing() {
        // `.other` — an engine tier value this GUI version doesn't
        // recognize — must never be silently mapped onto one of the three
        // known tiers (`ConfidenceChipModel`'s own documentation).
        let model = ConfidenceChipModel(tier: .other("some_future_tier"))
        XCTAssertEqual(model.label, "Unrecognized")
        XCTAssertNotEqual(model.label, "Auto")
        XCTAssertNotEqual(model.label, "Approval Required")
        XCTAssertNotEqual(model.label, "Review Required")
    }

    func test_everyKnownTierHasADistinctIcon() {
        let icons = [
            ConfidenceChipModel(tier: .auto).iconSystemName,
            ConfidenceChipModel(tier: .approvalRequired).iconSystemName,
            ConfidenceChipModel(tier: .reviewRequired).iconSystemName
        ]
        XCTAssertEqual(Set(icons).count, icons.count, "the three tier icons must never be redrawn/varied or reused across tiers")
    }

    func test_withScore_accessibilityLabelIncludesScore() {
        let model = ConfidenceChipModel(tier: .auto, score: 97)
        XCTAssertEqual(model.accessibilityLabel, "Auto, confidence score 97")
    }

    func test_withoutScore_accessibilityLabelOmitsScore() {
        let model = ConfidenceChipModel(tier: .auto, score: nil)
        XCTAssertEqual(model.accessibilityLabel, "Auto")
    }

    func test_scoreDefaultsToNil() {
        XCTAssertNil(ConfidenceChipModel(tier: .reviewRequired).score)
    }
}
