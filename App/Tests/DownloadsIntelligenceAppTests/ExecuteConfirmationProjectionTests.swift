import XCTest
import EngineBridge
// Scoped import: resolves EngineBridge.Category by its exact module path,
// disambiguating it from XCTest's own colliding top-level `Category`
// symbol — the same precedent already established in
// PreviewProjectionTests/ScanCompleteProjectionTests.
import enum EngineBridge.Category
@testable import DownloadsIntelligenceApp

final class ExecuteConfirmationProjectionTests: XCTestCase {

    private func makeRecord(
        fileID: String,
        originalName: String? = nil,
        suggestedName: String? = nil,
        suggestedDestination: String? = nil,
        category: Category? = nil,
        tier: Tier? = nil,
        status: String = "discovered"
    ) -> FileRecordSnapshot {
        FileRecordSnapshot(
            fileID: fileID,
            sourceID: "downloads",
            originalName: originalName ?? "\(fileID).pdf",
            originalPath: "/Users/fixture/Downloads/\(fileID).pdf",
            currentPath: "/Users/fixture/Downloads/\(fileID).pdf",
            fileExtension: ".pdf",
            mimeType: "application/pdf",
            sizeBytes: 1024,
            createdAt: "2026-07-27T10:00:00Z",
            modifiedAt: "2026-07-27T10:00:00Z",
            contentHash: "hash-\(fileID)",
            discoveredAt: "2026-07-27T10:00:00Z",
            status: status,
            category: category,
            suggestedName: suggestedName,
            suggestedDestination: suggestedDestination,
            tier: tier
        )
    }

    // MARK: - Only auto-tier, not-yet-filed records are included

    func test_compute_noRecords_isEmpty() {
        let projection = ExecuteConfirmationProjection.compute(records: [])
        XCTAssertEqual(projection.totalCount, 0)
        XCTAssertTrue(projection.fileRows.isEmpty)
    }

    func test_compute_onlyAutoTierRecordsIncluded_approvalRequiredAndReviewRequiredExcluded() {
        let records = [
            makeRecord(fileID: "1", category: .invoice, tier: .auto, status: "scored"),
            makeRecord(fileID: "2", category: .resume, tier: .approvalRequired, status: "scored"),
            makeRecord(fileID: "3", category: .document, tier: .reviewRequired, status: "scored"),
        ]
        let projection = ExecuteConfirmationProjection.compute(records: records)

        XCTAssertEqual(projection.fileRows.map(\.fileID), ["1"])
    }

    func test_compute_recordWithNoTier_excluded() {
        let records = [makeRecord(fileID: "1", tier: nil, status: "discovered")]
        let projection = ExecuteConfirmationProjection.compute(records: records)
        XCTAssertTrue(projection.fileRows.isEmpty)
    }

    func test_compute_alreadyExecutedAutoRecord_excluded() {
        let records = [makeRecord(fileID: "1", category: .invoice, tier: .auto, status: "executed")]
        let projection = ExecuteConfirmationProjection.compute(records: records)
        XCTAssertTrue(projection.fileRows.isEmpty, "an already-filed record must never reappear in a fresh confirmation batch")
    }

    func test_compute_mixOfPendingAndExecutedAuto_onlyPendingIncluded() {
        let records = [
            makeRecord(fileID: "already-filed", category: .invoice, tier: .auto, status: "executed"),
            makeRecord(fileID: "still-pending", category: .resume, tier: .auto, status: "scored"),
        ]
        let projection = ExecuteConfirmationProjection.compute(records: records)
        XCTAssertEqual(projection.fileRows.map(\.fileID), ["still-pending"])
    }

    // MARK: - Row content: full before -> after detail, no tier/confidence carried

    func test_compute_fileRow_carriesBeforeAfterDetail() {
        let records = [
            makeRecord(
                fileID: "1",
                originalName: "2026-07-19_acme.pdf",
                suggestedName: "2026-07-19_Acme_Invoice.pdf",
                suggestedDestination: "Finance/",
                category: .invoice,
                tier: .auto,
                status: "scored"
            ),
        ]
        let projection = ExecuteConfirmationProjection.compute(records: records)

        let row = try? XCTUnwrap(projection.fileRows.first)
        XCTAssertEqual(row?.fileID, "1")
        XCTAssertEqual(row?.originalName, "2026-07-19_acme.pdf")
        XCTAssertEqual(row?.suggestedName, "2026-07-19_Acme_Invoice.pdf")
        XCTAssertEqual(row?.suggestedDestination, "Finance/")
    }

    // MARK: - Deterministic ordering

    func test_compute_rows_areOrderedByOriginalNameThenFileID() {
        let records = [
            makeRecord(fileID: "b", originalName: "banana.pdf", category: .document, tier: .auto, status: "scored"),
            makeRecord(fileID: "a", originalName: "apple.pdf", category: .document, tier: .auto, status: "scored"),
            makeRecord(fileID: "c", originalName: "apple.pdf", category: .document, tier: .auto, status: "scored"),
        ]
        let projection = ExecuteConfirmationProjection.compute(records: records)
        XCTAssertEqual(projection.fileRows.map(\.fileID), ["a", "c", "b"])
    }

    func test_totalCount_matchesRowCount() {
        let records = [
            makeRecord(fileID: "1", category: .invoice, tier: .auto, status: "scored"),
            makeRecord(fileID: "2", category: .resume, tier: .auto, status: "scored"),
        ]
        let projection = ExecuteConfirmationProjection.compute(records: records)
        XCTAssertEqual(projection.totalCount, 2)
    }
}
