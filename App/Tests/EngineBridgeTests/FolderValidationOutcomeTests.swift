import XCTest
@testable import EngineBridge

/// Pure-value tests for `FolderValidationOutcome` — no filesystem, no
/// `EngineBridge`, exactly mirroring the "test the pure model directly"
/// pattern already used for `Tier`/`Category`-style value types in this
/// package (WP-GUI-00A).
final class FolderValidationOutcomeTests: XCTestCase {

    func test_isValid_trueOnlyForValidCase() {
        XCTAssertTrue(FolderValidationOutcome.valid.isValid)
        XCTAssertFalse(FolderValidationOutcome.doesNotExist.isValid)
        XCTAssertFalse(FolderValidationOutcome.notADirectory.isValid)
        XCTAssertFalse(FolderValidationOutcome.notReadable.isValid)
        XCTAssertFalse(FolderValidationOutcome.notWritable.isValid)
    }

    func test_equatable_matchingCasesAreEqual() {
        XCTAssertEqual(FolderValidationOutcome.valid, FolderValidationOutcome.valid)
        XCTAssertEqual(FolderValidationOutcome.doesNotExist, FolderValidationOutcome.doesNotExist)
        XCTAssertEqual(FolderValidationOutcome.notADirectory, FolderValidationOutcome.notADirectory)
        XCTAssertEqual(FolderValidationOutcome.notReadable, FolderValidationOutcome.notReadable)
        XCTAssertEqual(FolderValidationOutcome.notWritable, FolderValidationOutcome.notWritable)
    }

    func test_equatable_differentCasesAreNotEqual() {
        let allCases: [FolderValidationOutcome] = [
            .valid, .doesNotExist, .notADirectory, .notReadable, .notWritable
        ]
        for (i, lhs) in allCases.enumerated() {
            for (j, rhs) in allCases.enumerated() where i != j {
                XCTAssertNotEqual(lhs, rhs, "\(lhs) unexpectedly equal to \(rhs)")
            }
        }
    }
}
