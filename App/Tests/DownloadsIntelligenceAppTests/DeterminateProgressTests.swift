import XCTest
@testable import DownloadsIntelligenceApp

/// Verifies `DeterminateProgress`'s fraction-clamping and plain-language
/// label formatting — `06 Visual Design System.md` §7: "always paired
/// with a plain-language count in text, never a bar shown alone."
final class DeterminateProgressTests: XCTestCase {

    func test_fraction_normalCase() {
        let progress = DeterminateProgress(completed: 12, total: 41)
        XCTAssertEqual(progress.fraction, 12.0 / 41.0, accuracy: 0.0001)
    }

    func test_fraction_zeroTotal_doesNotDivideByZero() {
        let progress = DeterminateProgress(completed: 0, total: 0)
        XCTAssertEqual(progress.fraction, 0)
    }

    func test_fraction_completedExceedingTotal_clampsToOne() {
        let progress = DeterminateProgress(completed: 50, total: 41)
        XCTAssertEqual(progress.fraction, 1)
    }

    func test_negativeInputs_clampToZero() {
        let progress = DeterminateProgress(completed: -5, total: -10)
        XCTAssertEqual(progress.completed, 0)
        XCTAssertEqual(progress.total, 0)
    }

    func test_label_isPlainLanguageCount() {
        let progress = DeterminateProgress(completed: 12, total: 41)
        XCTAssertEqual(progress.label, "12 of 41 files")
    }

    func test_label_completedExceedingTotal_showsTotalNotOvercount() {
        let progress = DeterminateProgress(completed: 50, total: 41)
        XCTAssertEqual(progress.label, "41 of 41 files")
    }

    func test_label_zeroTotal() {
        let progress = DeterminateProgress(completed: 0, total: 0)
        XCTAssertEqual(progress.label, "0 of 0 files")
    }
}
