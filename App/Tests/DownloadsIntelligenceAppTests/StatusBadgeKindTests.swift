import XCTest
@testable import DownloadsIntelligenceApp

/// Verifies the three Status Badge variants named in the Figma Production
/// Guide §2: Duplicate / Archived / Unknown-category tag.
final class StatusBadgeKindTests: XCTestCase {

    func test_exactlyThreeKinds() {
        XCTAssertEqual(StatusBadgeKind.allCases.count, 3)
    }

    func test_labels() {
        XCTAssertEqual(StatusBadgeKind.duplicate.label, "Duplicate")
        XCTAssertEqual(StatusBadgeKind.archived.label, "Archived")
        XCTAssertEqual(StatusBadgeKind.unknownCategory.label, "Unknown")
    }

    func test_archivedIconIsNeverATrashOrDeletionMark() {
        // "deliberately never resembling a trash or deletion icon in any
        // way, reinforcing the non-deletion guarantee" (`06 Visual Design
        // System.md` §5).
        let forbiddenIconNames = ["trash", "trash.fill", "delete.left", "minus.circle"]
        XCTAssertFalse(forbiddenIconNames.contains(StatusBadgeKind.archived.iconSystemName))
    }

    func test_everyKindHasADistinctIcon() {
        let icons = StatusBadgeKind.allCases.map(\.iconSystemName)
        XCTAssertEqual(Set(icons).count, icons.count)
    }
}
