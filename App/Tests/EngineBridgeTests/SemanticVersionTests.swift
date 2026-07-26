import XCTest
@testable import EngineBridge

final class SemanticVersionTests: XCTestCase {

    // MARK: - Parsing

    func test_parsesWellFormedTriple() throws {
        let version = try SemanticVersion(parsing: "0.8.0")
        XCTAssertEqual(version, SemanticVersion(major: 0, minor: 8, patch: 0))
    }

    func test_parsesMultiDigitComponents() throws {
        let version = try SemanticVersion(parsing: "12.34.567")
        XCTAssertEqual(version, SemanticVersion(major: 12, minor: 34, patch: 567))
    }

    func test_description_roundTripsBackToTheSameString() throws {
        let version = try SemanticVersion(parsing: "1.2.3")
        XCTAssertEqual(version.description, "1.2.3")
    }

    // MARK: - Malformed input

    func test_wrongComponentCount_tooFew_throws() {
        XCTAssertThrowsError(try SemanticVersion(parsing: "0.8")) { error in
            XCTAssertEqual(error as? SemanticVersion.ParseError, .wrongComponentCount(rawValue: "0.8"))
        }
    }

    func test_wrongComponentCount_tooMany_throws() {
        XCTAssertThrowsError(try SemanticVersion(parsing: "0.8.0.1")) { error in
            XCTAssertEqual(error as? SemanticVersion.ParseError, .wrongComponentCount(rawValue: "0.8.0.1"))
        }
    }

    func test_nonNumericComponent_throws() {
        XCTAssertThrowsError(try SemanticVersion(parsing: "0.8.beta")) { error in
            XCTAssertEqual(error as? SemanticVersion.ParseError, .nonNumericComponent(rawValue: "0.8.beta"))
        }
    }

    func test_negativeComponent_throws() {
        XCTAssertThrowsError(try SemanticVersion(parsing: "0.-1.0")) { error in
            XCTAssertEqual(error as? SemanticVersion.ParseError, .nonNumericComponent(rawValue: "0.-1.0"))
        }
    }

    func test_emptyString_throws() {
        XCTAssertThrowsError(try SemanticVersion(parsing: ""))
    }

    func test_prereleaseSuffix_isRejectedRatherThanSilentlyTruncated() {
        // Deliberately strict: "0.8.0-beta" is not the real, current
        // VERSIONS.md format, and this type does not guess how to handle a
        // format it has never seen.
        XCTAssertThrowsError(try SemanticVersion(parsing: "0.8.0-beta"))
    }

    // MARK: - Ordering

    func test_ordering_comparesMajorFirst() {
        XCTAssertLessThan(SemanticVersion(major: 0, minor: 9, patch: 9), SemanticVersion(major: 1, minor: 0, patch: 0))
    }

    func test_ordering_comparesMinorWhenMajorEqual() {
        XCTAssertLessThan(SemanticVersion(major: 1, minor: 2, patch: 9), SemanticVersion(major: 1, minor: 3, patch: 0))
    }

    func test_ordering_comparesPatchWhenMajorAndMinorEqual() {
        XCTAssertLessThan(SemanticVersion(major: 1, minor: 2, patch: 3), SemanticVersion(major: 1, minor: 2, patch: 4))
    }

    func test_ordering_equalVersionsAreNeitherLessThanEachOther() {
        let a = SemanticVersion(major: 1, minor: 2, patch: 3)
        let b = SemanticVersion(major: 1, minor: 2, patch: 3)
        XCTAssertFalse(a < b)
        XCTAssertFalse(b < a)
        XCTAssertEqual(a, b)
    }
}
