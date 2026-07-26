import XCTest
@testable import DownloadsIntelligenceApp

/// Verifies the two Dialog variants named in the Figma Production Guide
/// §2 carry exactly the button configuration their name implies —
/// Confirmation is two-button, Result is single-button — and that
/// equality behaves as expected for use in view state/tests elsewhere.
final class DialogKindTests: XCTestCase {

    func test_confirmation_carriesBothTitles() {
        let kind = DialogKind.confirmation(confirmTitle: "Undo this batch", cancelTitle: "Cancel")
        guard case .confirmation(let confirmTitle, let cancelTitle) = kind else {
            return XCTFail("expected .confirmation")
        }
        XCTAssertEqual(confirmTitle, "Undo this batch")
        XCTAssertEqual(cancelTitle, "Cancel")
    }

    func test_result_carriesOnlyDismissTitle() {
        let kind = DialogKind.result(dismissTitle: "Back to Home")
        guard case .result(let dismissTitle) = kind else {
            return XCTFail("expected .result")
        }
        XCTAssertEqual(dismissTitle, "Back to Home")
    }

    func test_confirmationAndResultAreNeverEqual() {
        let confirmation = DialogKind.confirmation(confirmTitle: "Undo", cancelTitle: "Cancel")
        let result = DialogKind.result(dismissTitle: "Undo")
        XCTAssertNotEqual(confirmation, result)
    }

    func test_equalityIsValueBased() {
        let a = DialogKind.confirmation(confirmTitle: "Undo", cancelTitle: "Cancel")
        let b = DialogKind.confirmation(confirmTitle: "Undo", cancelTitle: "Cancel")
        XCTAssertEqual(a, b)
    }
}
