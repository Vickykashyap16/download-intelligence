import XCTest
import EngineBridge
// Scoped import: see the identical note in ScanCompleteProjectionTests —
// resolves EngineBridge.Category by its exact module path, disambiguating
// it from XCTest's own colliding top-level `Category` symbol.
import enum EngineBridge.Category
@testable import DownloadsIntelligenceApp

final class PreviewProjectionTests: XCTestCase {

    private func makeRecord(
        fileID: String,
        originalName: String? = nil,
        suggestedName: String? = nil,
        suggestedDestination: String? = nil,
        category: Category? = nil,
        tier: Tier? = nil,
        confidenceScore: Int? = nil,
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
            confidenceScore: confidenceScore,
            tier: tier
        )
    }

    // MARK: - Empty state: nothing scanned yet

    func test_compute_noRecordsAtAll_isNothingScannedYet() {
        let projection = PreviewProjection.compute(records: [])

        XCTAssertEqual(projection.kind, .nothingScannedYet)
        XCTAssertEqual(projection.totalFilesPending, 0)
        XCTAssertTrue(projection.tierSections.isEmpty)
        XCTAssertNil(projection.primaryActionAutoCount)
    }

    func test_compute_recordsExistButNoneClassifiedYet_isNothingScannedYet() {
        // Discovered, but never reached confidence scoring — no tier at all.
        let records = [makeRecord(fileID: "1", tier: nil)]
        let projection = PreviewProjection.compute(records: records)

        XCTAssertEqual(projection.kind, .nothingScannedYet)
    }

    // MARK: - Empty state: already filed

    func test_compute_allClassifiedRecordsExecuted_isAllFiled() {
        let records = [
            makeRecord(fileID: "1", category: .invoice, tier: .auto, status: "executed"),
            makeRecord(fileID: "2", category: .resume, tier: .reviewRequired, status: "executed"),
        ]
        let projection = PreviewProjection.compute(records: records)

        XCTAssertEqual(projection.kind, .allFiled)
        XCTAssertEqual(projection.totalFilesPending, 0)
        XCTAssertTrue(projection.tierSections.isEmpty)
        XCTAssertNil(projection.primaryActionAutoCount)
    }

    // MARK: - Populated plan: executed records excluded, pending records counted

    func test_compute_mixOfExecutedAndPending_onlyPendingCounted() {
        let records = [
            makeRecord(fileID: "already-filed", category: .invoice, tier: .auto, status: "executed"),
            makeRecord(fileID: "still-pending", category: .resume, tier: .auto, status: "scored"),
        ]
        let projection = PreviewProjection.compute(records: records)

        XCTAssertEqual(projection.kind, .hasPlan)
        XCTAssertEqual(projection.totalFilesPending, 1)
        XCTAssertEqual(projection.tierSections.map(\.tier), [.auto])
        XCTAssertEqual(projection.tierSections.first?.rows.map(\.fileID), ["still-pending"])
    }

    func test_compute_recordWithNoTier_excludedFromPendingCount() {
        let records = [
            makeRecord(fileID: "still-mid-pipeline", tier: nil, status: "discovered"),
            makeRecord(fileID: "classified", category: .invoice, tier: .auto, status: "scored"),
        ]
        let projection = PreviewProjection.compute(records: records)

        XCTAssertEqual(projection.totalFilesPending, 1)
    }

    // MARK: - Zero-row omission (matching ScanCompleteProjection's own rule)

    func test_compute_everythingReviewRequired_omitsAutoAndApprovalSections_andPrimaryAction() {
        let records = [
            makeRecord(fileID: "1", category: .invoice, tier: .reviewRequired, status: "scored"),
            makeRecord(fileID: "2", category: .resume, tier: .reviewRequired, status: "scored"),
        ]
        let projection = PreviewProjection.compute(records: records)

        XCTAssertEqual(projection.tierSections.map(\.tier), [.reviewRequired])
        XCTAssertEqual(projection.tierSections.first?.count, 2)
        XCTAssertNil(projection.primaryActionAutoCount, "nothing to file — 'Execute now' must be omitted entirely")
    }

    func test_compute_everythingAuto_showsPrimaryAction() {
        let records = [
            makeRecord(fileID: "1", category: .invoice, tier: .auto, status: "scored"),
            makeRecord(fileID: "2", category: .resume, tier: .auto, status: "scored"),
        ]
        let projection = PreviewProjection.compute(records: records)

        XCTAssertEqual(projection.primaryActionAutoCount, 2)
    }

    // MARK: - Fixed tier order regardless of input order

    func test_compute_tierSections_areAlwaysInFixedOrder() {
        let records = [
            makeRecord(fileID: "1", category: .invoice, tier: .reviewRequired, status: "scored"),
            makeRecord(fileID: "2", category: .resume, tier: .auto, status: "scored"),
            makeRecord(fileID: "3", category: .document, tier: .approvalRequired, status: "scored"),
        ]
        let projection = PreviewProjection.compute(records: records)

        XCTAssertEqual(projection.tierSections.map(\.tier), [.auto, .approvalRequired, .reviewRequired])
    }

    // MARK: - Per-file row content: full before -> after detail (§7's own requirement)

    func test_compute_fileRow_carriesFullBeforeAfterDetailAndConfidence() {
        let records = [
            makeRecord(
                fileID: "1",
                originalName: "IMG_4821.pdf",
                suggestedName: "invoice_acme_2026-07.pdf",
                suggestedDestination: "/Users/fixture/Organized Downloads/Invoices/invoice_acme_2026-07.pdf",
                category: .invoice,
                tier: .auto,
                confidenceScore: 97,
                status: "scored"
            ),
        ]
        let projection = PreviewProjection.compute(records: records)

        let row = try? XCTUnwrap(projection.tierSections.first?.rows.first)
        XCTAssertEqual(row?.originalName, "IMG_4821.pdf")
        XCTAssertEqual(row?.suggestedName, "invoice_acme_2026-07.pdf")
        XCTAssertEqual(row?.suggestedDestination, "/Users/fixture/Organized Downloads/Invoices/invoice_acme_2026-07.pdf")
        XCTAssertEqual(row?.tier, .auto)
        XCTAssertEqual(row?.confidenceScore, 97)
    }

    // MARK: - Row ordering within a section is stable and deterministic

    func test_compute_rowsWithinASection_areOrderedByOriginalNameThenFileID() {
        let records = [
            makeRecord(fileID: "b", originalName: "banana.pdf", tier: .auto, status: "scored"),
            makeRecord(fileID: "a", originalName: "apple.pdf", tier: .auto, status: "scored"),
            makeRecord(fileID: "c", originalName: "apple.pdf", tier: .auto, status: "scored"),
        ]
        let projection = PreviewProjection.compute(records: records)

        XCTAssertEqual(projection.tierSections.first?.rows.map(\.fileID), ["a", "c", "b"])
    }
}
