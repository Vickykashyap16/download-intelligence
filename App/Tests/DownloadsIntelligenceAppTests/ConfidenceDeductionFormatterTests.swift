import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

final class ConfidenceDeductionFormatterTests: XCTestCase {

    private typealias DeductionLine = ConfidenceDeductionFormatter.DeductionLine

    // MARK: - Empty

    func test_lines_emptyBreakdown_isEmpty() {
        XCTAssertEqual(ConfidenceDeductionFormatter.lines(from: [:]), [])
    }

    // MARK: - Each of the six fixed-key deductions

    func test_lines_ambiguousClassification() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["ambiguous_classification": .number(-15)])
        XCTAssertEqual(lines, [DeductionLine(text: "Classification was ambiguous between two plausible categories", points: -15)])
    }

    func test_lines_noExtractableText() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["no_extractable_text": .number(-30)])
        XCTAssertEqual(lines, [DeductionLine(text: "No extractable text or content — classified from filename only", points: -30)])
    }

    func test_lines_fuzzyDuplicate() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["fuzzy_duplicate": .number(-20)])
        XCTAssertEqual(lines, [DeductionLine(text: "Near-duplicate or fuzzy image match found", points: -20)])
    }

    func test_lines_versionConflict() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["version_conflict": .number(-25)])
        XCTAssertEqual(lines, [DeductionLine(text: "Version chain where filename version number and file date disagree", points: -25)])
    }

    func test_lines_nonEnglishContent() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["non_english_content": .number(-10)])
        XCTAssertEqual(lines, [DeductionLine(text: "Non-English content detected", points: -10)])
    }

    func test_lines_lockedFile() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["locked_file": .number(-40)])
        XCTAssertEqual(lines, [DeductionLine(text: "Locked or password-protected file", points: -40)])
    }

    // MARK: - Parameterized keys (matching Confidence Rules.md's worked example)

    func test_lines_missingRequiredField() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["missing_required_field:invoice_number": .number(-8)])
        XCTAssertEqual(lines, [DeductionLine(text: "Missing required field: invoice_number", points: -8)])
    }

    func test_lines_missingOptionalField() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["missing_optional_field:currency": .number(-2)])
        XCTAssertEqual(lines, [DeductionLine(text: "Missing optional field: currency", points: -2)])
    }

    func test_lines_namingFallback() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["naming_fallback:vendor": .number(-10)])
        XCTAssertEqual(lines, [DeductionLine(text: "Naming fallback used: vendor", points: -10)])
    }

    /// The exact worked example from `Rules/Confidence Rules.md`: "Stored
    /// breakdown: `{"missing_required_field:invoice_number": -8,
    /// "naming_fallback:vendor": -10}` → total 82."
    func test_lines_confidenceRulesWorkedExample() {
        let breakdown: [String: JSONValue] = [
            "missing_required_field:invoice_number": .number(-8),
            "naming_fallback:vendor": .number(-10),
        ]
        let lines = ConfidenceDeductionFormatter.lines(from: breakdown)
        XCTAssertEqual(
            lines,
            [
                DeductionLine(text: "Missing required field: invoice_number", points: -8),
                DeductionLine(text: "Naming fallback used: vendor", points: -10),
            ]
        )
    }

    // MARK: - A capped field deduction, stored as exactly 0, is still rendered

    func test_lines_zeroValueDeduction_isStillRendered_neverOmitted() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["missing_required_field:extra_field": .number(0)])
        XCTAssertEqual(lines, [DeductionLine(text: "Missing required field: extra_field", points: 0)])
    }

    // MARK: - Fixed order regardless of input/dictionary iteration order

    func test_lines_areAlwaysInFixedOrder() {
        let breakdown: [String: JSONValue] = [
            "locked_file": .number(-40),
            "non_english_content": .number(-10),
            "version_conflict": .number(-25),
            "fuzzy_duplicate": .number(-20),
            "naming_fallback:vendor": .number(-10),
            "missing_optional_field:currency": .number(-2),
            "missing_required_field:invoice_number": .number(-8),
            "no_extractable_text": .number(-30),
            "ambiguous_classification": .number(-15),
        ]
        let lines = ConfidenceDeductionFormatter.lines(from: breakdown)
        XCTAssertEqual(
            lines.map(\.text),
            [
                "Classification was ambiguous between two plausible categories",
                "No extractable text or content — classified from filename only",
                "Missing required field: invoice_number",
                "Missing optional field: currency",
                "Naming fallback used: vendor",
                "Near-duplicate or fuzzy image match found",
                "Version chain where filename version number and file date disagree",
                "Non-English content detected",
                "Locked or password-protected file",
            ]
        )
    }

    // MARK: - Multiple entries within one parameterized group are sub-ordered alphabetically

    func test_lines_multipleMissingRequiredFields_areSortedAlphabetically() {
        let breakdown: [String: JSONValue] = [
            "missing_required_field:vendor": .number(-8),
            "missing_required_field:invoice_date": .number(-8),
        ]
        let lines = ConfidenceDeductionFormatter.lines(from: breakdown)
        XCTAssertEqual(
            lines.map(\.text),
            [
                "Missing required field: invoice_date",
                "Missing required field: vendor",
            ]
        )
    }

    // MARK: - An unrecognized key is never dropped

    func test_lines_unrecognizedKey_isRenderedRatherThanDropped() {
        let lines = ConfidenceDeductionFormatter.lines(from: ["some_future_deduction": .number(-5)])
        XCTAssertEqual(lines, [DeductionLine(text: "some_future_deduction", points: -5)])
    }

    func test_lines_unrecognizedKey_sortsAfterAllKnownDeductions() {
        let breakdown: [String: JSONValue] = [
            "some_future_deduction": .number(-5),
            "locked_file": .number(-40),
        ]
        let lines = ConfidenceDeductionFormatter.lines(from: breakdown)
        XCTAssertEqual(lines.map(\.text), ["Locked or password-protected file", "some_future_deduction"])
    }
}
