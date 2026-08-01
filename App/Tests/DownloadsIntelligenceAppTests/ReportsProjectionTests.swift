import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Fixture Markdown strings below are hand-copied to match the exact
/// rendering shape of `src/pipeline/reporting.py`'s real
/// `_render_daily_summary()`/`_render_weekly_summary()`/
/// `_render_duplicate_report()`/`_render_storage_report()` functions
/// (confirmed by direct reading during WP-GUI-10 dependency verification),
/// not invented — this is what makes these tests a meaningful check of
/// `ReportsProjection`'s parsing against real engine output shape, not just
/// against whatever the parser happens to expect.
final class ReportsProjectionTests: XCTestCase {

    private func makeContent(kind: ReportKind, markdownText: String) -> ReportContent {
        ReportContent(kind: kind, fileURL: URL(fileURLWithPath: "/fixture/\(kind).md"), markdownText: markdownText)
    }

    // MARK: - All four absent

    func test_compute_allFourAbsent_isEmpty() {
        let projection = ReportsProjection.compute(dailySummary: nil, weeklySummary: nil, duplicateReport: nil, storageReport: nil)

        XCTAssertTrue(projection.isEmpty)
        XCTAssertNil(projection.dailySummary)
        XCTAssertNil(projection.weeklySummary)
        XCTAssertNil(projection.duplicateReport)
        XCTAssertNil(projection.storageReport)
    }

    func test_compute_oneReportPresent_isNotEmpty() {
        let content = makeContent(kind: .storageReport, markdownText: Self.storageReportMarkdown)
        let projection = ReportsProjection.compute(dailySummary: nil, weeklySummary: nil, duplicateReport: nil, storageReport: content)

        XCTAssertFalse(projection.isEmpty)
        XCTAssertNil(projection.dailySummary)
        XCTAssertNotNil(projection.storageReport)
    }

    // MARK: - Daily Summary (one table)

    func test_compute_dailySummary_parsesTitleBulletsAndFilesTable() {
        let content = makeContent(kind: .dailySummary, markdownText: Self.dailySummaryMarkdown)
        let projection = ReportsProjection.compute(dailySummary: content, weeklySummary: nil, duplicateReport: nil, storageReport: nil)

        guard case .structured(let title, let blocks) = projection.dailySummary?.content else {
            return XCTFail("Expected structured content")
        }
        XCTAssertEqual(title, "Daily Summary — 2026-08-01")
        XCTAssertEqual(blocks.count, 2)

        guard case .bullets(let bullets) = blocks[0] else { return XCTFail("Expected leading bullets block") }
        XCTAssertEqual(bullets, [
            "Files scanned: 12",
            "Auto-filed: 8",
            "Approval required: 2",
            "Review required: 2",
            "Duplicates found: 1 (archived)",
            "Versions archived: 0",
            "Errors: 0",
        ])

        guard case .table(let heading, let columns, let rows) = blocks[1] else { return XCTFail("Expected Files table block") }
        XCTAssertEqual(heading, "Files")
        XCTAssertEqual(columns, ["Original", "New Name", "Destination", "Category", "Confidence", "Tier"])
        XCTAssertEqual(rows, [
            ["invoice.pdf", "Invoice_2026-08-01.pdf", "Finance/Invoices/", "invoice", "97", "auto"],
        ])
    }

    /// The real `Tier` raw strings (`"auto"`/`"approval_required"`/
    /// `"review_required"`) survive the parse completely unaltered — this
    /// is what lets a later view layer round-trip a cell's text through
    /// `Tier(rawValue:)` without this pure model needing to know anything
    /// about the `Tier` type itself.
    func test_compute_dailySummary_tierColumnCellTextIsUntouched() {
        let content = makeContent(kind: .dailySummary, markdownText: Self.dailySummaryMarkdown)
        let projection = ReportsProjection.compute(dailySummary: content, weeklySummary: nil, duplicateReport: nil, storageReport: nil)

        guard case .structured(_, let blocks) = projection.dailySummary?.content,
              case .table(_, let columns, let rows) = blocks.last else {
            return XCTFail("Expected Files table block")
        }
        let tierColumnIndex = columns.firstIndex(of: "Tier")
        XCTAssertEqual(tierColumnIndex, 5)
        XCTAssertEqual(rows[0][tierColumnIndex!], Tier.auto.rawValue)
    }

    // MARK: - Weekly Summary (day rows include "-" placeholders)

    func test_compute_weeklySummary_parsesNotYetClosedPlaceholderRow() {
        let content = makeContent(kind: .weeklySummary, markdownText: Self.weeklySummaryMarkdown)
        let projection = ReportsProjection.compute(dailySummary: nil, weeklySummary: content, duplicateReport: nil, storageReport: nil)

        guard case .structured(let title, let blocks) = projection.weeklySummary?.content else {
            return XCTFail("Expected structured content")
        }
        XCTAssertEqual(title, "Weekly Summary — 2026-W31")
        guard case .table(let heading, let columns, let rows) = blocks.last else { return XCTFail("Expected Days table block") }
        XCTAssertEqual(heading, "Days")
        XCTAssertEqual(columns.count, 9)
        XCTAssertEqual(rows.count, 2)
        // "Not yet closed" row's placeholder cells are preserved verbatim,
        // never recomputed into a zero or omitted.
        XCTAssertEqual(rows[1], ["2026-08-03", "Not yet closed", "-", "-", "-", "-", "-", "-", "-"])
    }

    // MARK: - Duplicate Report (zero-row table — "no duplicates found this period")

    func test_compute_duplicateReport_zeroRowTableParsesWithEmptyRows() {
        let content = makeContent(kind: .duplicateReport, markdownText: Self.duplicateReportZeroRowsMarkdown)
        let projection = ReportsProjection.compute(dailySummary: nil, weeklySummary: nil, duplicateReport: content, storageReport: nil)

        guard case .structured(let title, let blocks) = projection.duplicateReport?.content else {
            return XCTFail("Expected structured content")
        }
        XCTAssertEqual(title, "Duplicate Report")
        guard case .table(let heading, let columns, let rows) = blocks.last else { return XCTFail("Expected Records table block") }
        XCTAssertEqual(heading, "Records")
        XCTAssertEqual(columns, ["Original", "Type", "Related To", "Disposition"])
        XCTAssertEqual(rows, [])
    }

    // MARK: - Storage Report (two tables in one document)

    func test_compute_storageReport_parsesBothByDestinationAndByCategoryTables() {
        let content = makeContent(kind: .storageReport, markdownText: Self.storageReportMarkdown)
        let projection = ReportsProjection.compute(dailySummary: nil, weeklySummary: nil, duplicateReport: nil, storageReport: content)

        guard case .structured(let title, let blocks) = projection.storageReport?.content else {
            return XCTFail("Expected structured content")
        }
        XCTAssertEqual(title, "Storage Report")
        XCTAssertEqual(blocks.count, 3) // leading bullets + two tables

        guard case .table(let firstHeading, _, let firstRows) = blocks[1] else { return XCTFail("Expected By Destination table") }
        XCTAssertEqual(firstHeading, "By Destination")
        XCTAssertEqual(firstRows, [["Finance/Invoices/", "12.0 KB"]])

        guard case .table(let secondHeading, _, let secondRows) = blocks[2] else { return XCTFail("Expected By Category table") }
        XCTAssertEqual(secondHeading, "By Category")
        XCTAssertEqual(secondRows, [["invoice", "12.0 KB"]])
    }

    // MARK: - Fallback: unexpected Markdown never fails, never drops content

    /// Mirrors the real, checked-in WP-GUI-00 `ReportsReader` test fixture
    /// content (`Tests/EngineBridgeTests/Fixtures/FakeEngineProject/Runtime/
    /// Reports/Storage Report/storage_report.md`) — deliberately plain
    /// placeholder prose, not real report shape, confirming this parser
    /// degrades to the raw-text fallback rather than mis-parsing it.
    func test_compute_nonStructuredPlaceholderContent_fallsBackToRawText() {
        let markdown = "# Storage Report\n\nFixture Storage Report content, exercised by `ReportsReader.readStorageReport()`.\n\nTotal tracked size: 256000 bytes.\n"
        let content = makeContent(kind: .storageReport, markdownText: markdown)
        let projection = ReportsProjection.compute(dailySummary: nil, weeklySummary: nil, duplicateReport: nil, storageReport: content)

        guard case .rawText(let text) = projection.storageReport?.content else {
            return XCTFail("Expected raw-text fallback")
        }
        XCTAssertEqual(text, markdown)
    }

    func test_compute_missingTitleLine_fallsBackToRawText() {
        let markdown = "Just some text with no heading at all.\n"
        let content = makeContent(kind: .dailySummary, markdownText: markdown)
        let projection = ReportsProjection.compute(dailySummary: content, weeklySummary: nil, duplicateReport: nil, storageReport: nil)

        guard case .rawText(let text) = projection.dailySummary?.content else {
            return XCTFail("Expected raw-text fallback")
        }
        XCTAssertEqual(text, markdown)
    }

    func test_compute_tableRowCellCountMismatch_fallsBackToRawText() {
        let markdown = """
        # Daily Summary — 2026-08-01

        - Files scanned: 1

        ## Files
        | Original | New Name | Destination | Category | Confidence | Tier |
        |---|---|---|---|---|---|
        | invoice.pdf | Invoice.pdf | Finance/ |

        """
        let content = makeContent(kind: .dailySummary, markdownText: markdown)
        let projection = ReportsProjection.compute(dailySummary: content, weeklySummary: nil, duplicateReport: nil, storageReport: nil)

        guard case .rawText(let text) = projection.dailySummary?.content else {
            return XCTFail("Expected raw-text fallback for a malformed table row")
        }
        XCTAssertEqual(text, markdown)
    }

    func test_compute_missingSeparatorRow_fallsBackToRawText() {
        let markdown = """
        # Duplicate Report

        - As of: no activity recorded yet

        ## Records
        | Original | Type | Related To | Disposition |
        | invoice.pdf | Duplicate | other.pdf | Archived |

        """
        let content = makeContent(kind: .duplicateReport, markdownText: markdown)
        let projection = ReportsProjection.compute(dailySummary: nil, weeklySummary: nil, duplicateReport: content, storageReport: nil)

        guard case .rawText(let text) = projection.duplicateReport?.content else {
            return XCTFail("Expected raw-text fallback for a missing separator row")
        }
        XCTAssertEqual(text, markdown)
    }

    // MARK: - Fixture Markdown (matching src/pipeline/reporting.py's real rendering shape)

    private static let dailySummaryMarkdown = """
    # Daily Summary — 2026-08-01

    - Files scanned: 12
    - Auto-filed: 8
    - Approval required: 2
    - Review required: 2
    - Duplicates found: 1 (archived)
    - Versions archived: 0
    - Errors: 0

    ## Files
    | Original | New Name | Destination | Category | Confidence | Tier |
    |---|---|---|---|---|---|
    | invoice.pdf | Invoice_2026-08-01.pdf | Finance/Invoices/ | invoice | 97 | auto |

    """

    private static let weeklySummaryMarkdown = """
    # Weekly Summary — 2026-W31

    - Week range: 2026-07-28 to 2026-08-03
    - Files scanned: 12
    - Auto-filed: 8
    - Approval required: 2
    - Review required: 2
    - Duplicates found: 1
    - Versions archived: 0
    - Errors: 0

    ## Days
    | Date | Status | Files scanned | Auto-filed | Approval required | Review required | Duplicates found | Versions archived | Errors |
    |---|---|---|---|---|---|---|---|---|
    | 2026-07-28 | Reported | 12 | 8 | 2 | 2 | 1 | 0 | 0 |
    | 2026-08-03 | Not yet closed | - | - | - | - | - | - | - |

    """

    private static let duplicateReportZeroRowsMarkdown = """
    # Duplicate Report

    - As of: no activity recorded yet
    - Records tracked: 0 (0 duplicates, 0 superseded versions)
    - Archived: 0
    - Kept: 0
    - Overridden by user: 0

    ## Records
    | Original | Type | Related To | Disposition |
    |---|---|---|---|

    """

    private static let storageReportMarkdown = """
    # Storage Report

    - As of: 2026-08-01T10:00:00Z
    - Filed records: 1
    - Total space used: 12.0 KB

    ## By Destination
    | Destination | Size |
    |---|---|
    | Finance/Invoices/ | 12.0 KB |

    ## By Category
    | Category | Size |
    |---|---|
    | invoice | 12.0 KB |

    """
}
