import XCTest
@testable import EngineBridge

/// Exercises `VersionCompatibilityChecker` against an example configured
/// range (1.0.0 ... 1.5.0). The specific numbers here are test fixtures
/// only, not a claim about any real, shipped compatibility policy — per
/// `VersionCompatibilityChecker`'s own documentation, WP-GUI-00 does not
/// fix real version numbers; this suite verifies the general comparison
/// mechanism is correct for whatever range a caller configures.
final class VersionCompatibilityCheckerTests: XCTestCase {

    private let minimum = SemanticVersion(major: 1, minor: 0, patch: 0)
    private let maximum = SemanticVersion(major: 1, minor: 5, patch: 0)

    private var checker: VersionCompatibilityChecker {
        VersionCompatibilityChecker(minimumSupportedVersion: minimum, maximumSupportedVersion: maximum)
    }

    // MARK: - Compatible

    func test_versionEqualToMaximum_isCompatible() {
        XCTAssertEqual(checker.evaluate(maximum), .compatible)
    }

    func test_versionEqualToMinimum_isCompatible() {
        XCTAssertEqual(checker.evaluate(minimum), .compatible)
    }

    func test_versionStrictlyBetweenBounds_isCompatible() {
        // "Older supported version accepted": older than the GUI's own
        // built-against ceiling (1.5.0), but still within the supported
        // range — must be accepted, not rejected just for not being the
        // newest supported version.
        let olderSupported = SemanticVersion(major: 1, minor: 2, patch: 3)
        XCTAssertEqual(checker.evaluate(olderSupported), .compatible)
    }

    func test_check_doesNotThrowForCompatibleVersion() {
        XCTAssertNoThrow(try checker.check(maximum))
    }

    // MARK: - Too old

    func test_versionBelowMinimum_isTooOld() {
        let tooOld = SemanticVersion(major: 0, minor: 9, patch: 0)
        XCTAssertEqual(checker.evaluate(tooOld), .tooOld)
    }

    func test_check_throwsEngineVersionTooOld_withCorrectPayload() {
        let tooOld = SemanticVersion(major: 0, minor: 9, patch: 0)
        XCTAssertThrowsError(try checker.check(tooOld)) { error in
            guard case EngineBridgeError.engineVersionTooOld(let engineVersion, let minimumSupportedVersion) = error else {
                return XCTFail("expected .engineVersionTooOld, got \(error)")
            }
            XCTAssertEqual(engineVersion, tooOld)
            XCTAssertEqual(minimumSupportedVersion, minimum)
        }
    }

    // MARK: - Too new

    func test_versionAboveMaximum_isTooNew() {
        let tooNew = SemanticVersion(major: 1, minor: 6, patch: 0)
        XCTAssertEqual(checker.evaluate(tooNew), .tooNew)
    }

    func test_check_throwsEngineVersionTooNew_withCorrectPayload() {
        let tooNew = SemanticVersion(major: 2, minor: 0, patch: 0)
        XCTAssertThrowsError(try checker.check(tooNew)) { error in
            guard case EngineBridgeError.engineVersionTooNew(let engineVersion, let maximumSupportedVersion) = error else {
                return XCTFail("expected .engineVersionTooNew, got \(error)")
            }
            XCTAssertEqual(engineVersion, tooNew)
            XCTAssertEqual(maximumSupportedVersion, maximum)
        }
    }

    // MARK: - Degenerate range (minimum == maximum) — exactly one accepted version

    func test_singleVersionRange_acceptsOnlyThatExactVersion() {
        let exact = SemanticVersion(major: 0, minor: 8, patch: 0)
        let singleVersionChecker = VersionCompatibilityChecker(
            minimumSupportedVersion: exact,
            maximumSupportedVersion: exact
        )
        XCTAssertEqual(singleVersionChecker.evaluate(exact), .compatible)
        XCTAssertEqual(
            singleVersionChecker.evaluate(SemanticVersion(major: 0, minor: 7, patch: 9)),
            .tooOld
        )
        XCTAssertEqual(
            singleVersionChecker.evaluate(SemanticVersion(major: 0, minor: 8, patch: 1)),
            .tooNew
        )
    }
}
