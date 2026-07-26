import XCTest
@testable import DownloadsIntelligenceApp

/// Verifies the five-item Information Architecture (`GUI Architecture
/// Specification.md` §6) is exactly what's implemented: five sections, no
/// more, no fewer, each with a unique title and a unique icon, and the
/// filled/outline icon-naming convention (`06 Visual Design System.md` §5)
/// holds for every case.
final class AppSectionTests: XCTestCase {

    func test_exactlyFiveSections() {
        XCTAssertEqual(AppSection.allCases.count, 5)
    }

    func test_everySectionHasAUniqueTitle() {
        let titles = AppSection.allCases.map(\.title)
        XCTAssertEqual(Set(titles).count, titles.count, "no two sections should share a title")
    }

    func test_everySectionHasAUniqueOutlineIcon() {
        // "one fixed icon in the Sidebar, used only there and in no other
        // context" (`06 Visual Design System.md` §5).
        let icons = AppSection.allCases.map(\.outlineSymbolName)
        XCTAssertEqual(Set(icons).count, icons.count, "no two sections should share an icon")
    }

    func test_filledSymbolIsAlwaysTheOutlineSymbolPlusFillSuffix() {
        for section in AppSection.allCases {
            XCTAssertEqual(section.filledSymbolName, section.outlineSymbolName + ".fill")
        }
    }

    func test_expectedFiveDestinations() {
        XCTAssertEqual(
            Set(AppSection.allCases),
            [.home, .reviewQueue, .history, .reports, .settings]
        )
    }

    func test_rawValueRoundTrips() {
        for section in AppSection.allCases {
            XCTAssertEqual(AppSection(rawValue: section.rawValue), section)
        }
    }
}
