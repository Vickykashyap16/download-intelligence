import XCTest
@testable import DownloadsIntelligenceApp

/// Pure, synchronous tests for `FirstRunStep` — no `EngineBridge`, no
/// SwiftUI, no asynchronous code, mirroring `HomeProjectionTests`'
/// precedent for testing a pure model in isolation.
final class FirstRunStepTests: XCTestCase {
    func test_indicatorText_matchesStepNumberOfThree() {
        XCTAssertEqual(FirstRunStep.source.indicatorText, "1 of 3")
        XCTAssertEqual(FirstRunStep.destination.indicatorText, "2 of 3")
        XCTAssertEqual(FirstRunStep.readyToScan.indicatorText, "3 of 3")
    }

    func test_canGoBack_falseOnlyForSource() {
        XCTAssertFalse(FirstRunStep.source.canGoBack)
        XCTAssertTrue(FirstRunStep.destination.canGoBack)
        XCTAssertTrue(FirstRunStep.readyToScan.canGoBack)
    }

    func test_previous_stepsBackwardCorrectly() {
        XCTAssertNil(FirstRunStep.source.previous)
        XCTAssertEqual(FirstRunStep.destination.previous, .source)
        XCTAssertEqual(FirstRunStep.readyToScan.previous, .destination)
    }

    func test_allCases_isExactlyThreeStepsInOrder() {
        XCTAssertEqual(FirstRunStep.allCases, [.source, .destination, .readyToScan])
    }
}
