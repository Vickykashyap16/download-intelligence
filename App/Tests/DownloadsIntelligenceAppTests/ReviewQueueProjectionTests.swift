import XCTest
import EngineBridge
import enum EngineBridge.Category
@testable import DownloadsIntelligenceApp

final class ReviewQueueProjectionTests: XCTestCase {

    private func makeRecord(
        fileID: String,
        originalName: String? = nil,
        category: Category? = nil,
        tier: Tier? = nil,
        status: String = "scored",
        suggestedName: String? = nil,
        suggestedDestination: String? = nil,
        confidenceScore: Int? = nil,
        duplicateOf: String? = nil,
        discoveredAt: String = "2026-07-27T10:00:00Z"
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
            createdAt: discoveredAt,
            modifiedAt: discoveredAt,
            contentHash: "hash-\(fileID)",
            discoveredAt: discoveredAt,
            status: status,
            category: category,
            suggestedName: suggestedName,
            suggestedDestination: suggestedDestination,
            duplicateOf: duplicateOf,
            confidenceScore: confidenceScore,
            tier: tier
        )
    }

    // MARK: - Zero-group-omission, both directions

    func test_compute_everythingApprovalRequired_omitsFlaggedGroup() {
        let records = [makeRecord(fileID: "1", tier: .approvalRequired)]
        let projection = ReviewQueueProjection.compute(records: records)

        XCTAssertEqual(projection.needsInputItems.count, 1)
        XCTAssertTrue(projection.flaggedItems.isEmpty)
    }

    func test_compute_everythingReviewRequired_omitsNeedsInputGroup() {
        let records = [makeRecord(fileID: "1", tier: .reviewRequired)]
        let projection = ReviewQueueProjection.compute(records: records)

        XCTAssertTrue(projection.needsInputItems.isEmpty)
        XCTAssertEqual(projection.flaggedItems.count, 1)
    }

    func test_compute_noRecords_isEmpty() {
        XCTAssertTrue(ReviewQueueProjection.compute(records: []).isEmpty)
    }

    // MARK: - Executed approval_required records are excluded; review_required is not status-filtered

    func test_compute_executedApprovalRequiredRecord_excludedFromNeedsInput() {
        let records = [
            makeRecord(fileID: "1", tier: .approvalRequired, status: "executed"),
            makeRecord(fileID: "2", tier: .approvalRequired, status: "scored"),
        ]
        let projection = ReviewQueueProjection.compute(records: records)

        XCTAssertEqual(projection.needsInputItems.map(\.fileID), ["2"])
    }

    func test_compute_reviewRequiredRecord_neverExcludedByStatus() {
        // review_required files are never executed at all (Rules/Confidence
        // Rules.md), so — matching HomeProjection.reviewRequiredCount's own
        // precedent — every such record counts regardless of `status`.
        let records = [makeRecord(fileID: "1", tier: .reviewRequired, status: "executed")]
        let projection = ReviewQueueProjection.compute(records: records)

        XCTAssertEqual(projection.flaggedItems.map(\.fileID), ["1"])
    }

    // MARK: - Records with no tier, or auto tier, never appear here

    func test_compute_untieredAndAutoRecords_excludedEntirely() {
        let records = [
            makeRecord(fileID: "1", tier: nil),
            makeRecord(fileID: "2", tier: .auto),
        ]
        let projection = ReviewQueueProjection.compute(records: records)

        XCTAssertTrue(projection.isEmpty)
    }

    // MARK: - Ordering: discoveredAt ascending, fileID tie-break

    func test_compute_ordersByDiscoveredAtThenFileID() {
        let records = [
            makeRecord(fileID: "later", tier: .approvalRequired, discoveredAt: "2026-07-27T12:00:00Z"),
            makeRecord(fileID: "earlier", tier: .approvalRequired, discoveredAt: "2026-07-27T09:00:00Z"),
            makeRecord(fileID: "also-earlier-b", tier: .approvalRequired, discoveredAt: "2026-07-27T09:00:00Z"),
            makeRecord(fileID: "also-earlier-a", tier: .approvalRequired, discoveredAt: "2026-07-27T09:00:00Z"),
        ]
        let projection = ReviewQueueProjection.compute(records: records)

        XCTAssertEqual(
            projection.needsInputItems.map(\.fileID),
            ["also-earlier-a", "also-earlier-b", "earlier", "later"]
        )
    }

    // MARK: - Needs-input item content

    func test_compute_needsInputItem_carriesFullCardContent() {
        let records = [
            makeRecord(
                fileID: "1",
                originalName: "IMG_4821.pdf",
                category: .invoice,
                tier: .approvalRequired,
                suggestedName: "invoice_acme.pdf",
                suggestedDestination: "/Users/fixture/Organized Downloads/Invoices/invoice_acme.pdf",
                confidenceScore: 87,
                duplicateOf: "some-other-file-id"
            ),
        ]
        let item = ReviewQueueProjection.compute(records: records).needsInputItems.first

        XCTAssertEqual(item?.originalName, "IMG_4821.pdf")
        XCTAssertEqual(item?.category, .invoice)
        XCTAssertEqual(item?.suggestedName, "invoice_acme.pdf")
        XCTAssertEqual(item?.suggestedDestination, "/Users/fixture/Organized Downloads/Invoices/invoice_acme.pdf")
        XCTAssertEqual(item?.confidenceScore, 87)
        XCTAssertTrue(item?.isDuplicate ?? false)
    }

    func test_compute_needsInputItem_notDuplicate_whenDuplicateOfIsNil() {
        let records = [makeRecord(fileID: "1", tier: .approvalRequired, duplicateOf: nil)]
        let item = ReviewQueueProjection.compute(records: records).needsInputItems.first

        XCTAssertFalse(item?.isDuplicate ?? true)
    }

    // MARK: - Flagged item content, including flag reason integration

    func test_compute_flaggedItem_carriesFlagReasonFromResolver() {
        let records = [makeRecord(fileID: "1", category: .unknown, tier: .reviewRequired)]
        let item = ReviewQueueProjection.compute(records: records).flaggedItems.first

        XCTAssertEqual(item?.flagReason, "This file's category couldn't be determined")
    }
}
