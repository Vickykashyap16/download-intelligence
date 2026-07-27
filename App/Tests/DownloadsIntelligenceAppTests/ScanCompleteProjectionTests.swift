import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

final class ScanCompleteProjectionTests: XCTestCase {

    private func makeRecord(
        fileID: String,
        category: EngineBridge.Category? = nil,
        tier: Tier? = nil
    ) -> FileRecordSnapshot {
        FileRecordSnapshot(
            fileID: fileID,
            sourceID: "downloads",
            originalName: "\(fileID).pdf",
            originalPath: "/Users/fixture/Downloads/\(fileID).pdf",
            currentPath: "/Users/fixture/Downloads/\(fileID).pdf",
            fileExtension: ".pdf",
            mimeType: "application/pdf",
            sizeBytes: 1024,
            createdAt: "2026-07-26T10:00:00Z",
            modifiedAt: "2026-07-26T10:00:00Z",
            contentHash: "hash-\(fileID)",
            discoveredAt: "2026-07-26T10:00:00Z",
            category: category,
            tier: tier
        )
    }

    // MARK: - Scope restriction

    func test_compute_onlyCountsRecordsWithinScope() {
        let records = [
            makeRecord(fileID: "in-scope", category: .invoice, tier: .auto),
            makeRecord(fileID: "out-of-scope-from-a-previous-scan", category: .resume, tier: .auto),
        ]
        let projection = ScanCompleteProjection.compute(records: records, scope: ["in-scope"])

        XCTAssertEqual(projection.totalFilesLookedAt, 1)
        XCTAssertEqual(projection.tierRows, [.init(tier: .auto, count: 1)])
    }

    // MARK: - Empty state

    func test_compute_zeroFilesInScope_isEmpty() {
        let projection = ScanCompleteProjection.compute(records: [], scope: [])
        XCTAssertTrue(projection.isEmpty)
        XCTAssertEqual(projection.totalFilesLookedAt, 0)
        XCTAssertTrue(projection.tierRows.isEmpty)
        XCTAssertNil(projection.primaryActionAutoCount)
    }

    // MARK: - Zero-row omission (§4's explicit rule)

    func test_compute_everythingReviewRequired_omitsAutoAndApprovalRows_andPrimaryAction() {
        let records = [
            makeRecord(fileID: "1", category: .invoice, tier: .reviewRequired),
            makeRecord(fileID: "2", category: .resume, tier: .reviewRequired),
        ]
        let projection = ScanCompleteProjection.compute(records: records, scope: ["1", "2"])

        XCTAssertEqual(projection.tierRows, [.init(tier: .reviewRequired, count: 2)])
        XCTAssertNil(projection.primaryActionAutoCount, "nothing to file — the Primary Button must be omitted entirely")
    }

    func test_compute_everythingAuto_omitsApprovalAndReviewRows_andShowsPrimaryAction() {
        let records = [
            makeRecord(fileID: "1", category: .invoice, tier: .auto),
            makeRecord(fileID: "2", category: .resume, tier: .auto),
            makeRecord(fileID: "3", category: .invoice, tier: .auto),
        ]
        let projection = ScanCompleteProjection.compute(records: records, scope: ["1", "2", "3"])

        XCTAssertEqual(projection.tierRows, [.init(tier: .auto, count: 3)])
        XCTAssertEqual(projection.primaryActionAutoCount, 3)
    }

    // MARK: - Fixed tier order regardless of input order

    func test_compute_tierRows_areAlwaysInFixedOrder() {
        let records = [
            makeRecord(fileID: "1", category: .invoice, tier: .reviewRequired),
            makeRecord(fileID: "2", category: .resume, tier: .auto),
            makeRecord(fileID: "3", category: .document, tier: .approvalRequired),
        ]
        let projection = ScanCompleteProjection.compute(records: records, scope: ["1", "2", "3"])

        XCTAssertEqual(projection.tierRows.map(\.tier), [.auto, .approvalRequired, .reviewRequired])
    }

    // MARK: - Category breakdown ordering

    func test_compute_categoryBreakdown_isSortedByDescendingCount_thenRawValue() {
        let records = [
            makeRecord(fileID: "1", category: .resume, tier: .auto),
            makeRecord(fileID: "2", category: .invoice, tier: .auto),
            makeRecord(fileID: "3", category: .invoice, tier: .auto),
            makeRecord(fileID: "4", category: .document, tier: .auto),
            makeRecord(fileID: "5", category: .document, tier: .auto),
        ]
        let projection = ScanCompleteProjection.compute(records: records, scope: ["1", "2", "3", "4", "5"])

        // Invoice(2) and Document(2) tie on count — "Document" < "Invoice"
        // lexicographically breaks the tie deterministically.
        XCTAssertEqual(
            projection.categoryBreakdown,
            [
                .init(category: .document, count: 2),
                .init(category: .invoice, count: 2),
                .init(category: .resume, count: 1),
            ]
        )
    }

    func test_compute_recordsWithNoCategory_areExcludedFromBreakdown_butStillCounted() {
        let records = [
            makeRecord(fileID: "1", category: nil, tier: .reviewRequired),
            makeRecord(fileID: "2", category: .invoice, tier: .auto),
        ]
        let projection = ScanCompleteProjection.compute(records: records, scope: ["1", "2"])

        XCTAssertEqual(projection.totalFilesLookedAt, 2)
        XCTAssertEqual(projection.categoryBreakdown, [.init(category: .invoice, count: 1)])
    }

    // MARK: - Duplicates receive a normal tier row, not a fourth tier (§4 Edge Cases)

    func test_compute_duplicatesOnly_stillRepresentedWithinNormalTierRows() {
        let records = [
            makeRecord(fileID: "1", category: .image, tier: .auto),
            makeRecord(fileID: "2", category: .image, tier: .auto),
        ]
        let projection = ScanCompleteProjection.compute(records: records, scope: ["1", "2"])

        XCTAssertEqual(projection.tierRows, [.init(tier: .auto, count: 2)])
    }
}
