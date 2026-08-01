import XCTest
import EngineBridge
import enum EngineBridge.Category
@testable import DownloadsIntelligenceApp

final class ReviewDetailProjectionTests: XCTestCase {

    private func makeRecord(
        fileID: String = "1",
        originalName: String? = nil,
        category: Category? = nil,
        tier: Tier? = nil,
        status: String = "scored",
        suggestedName: String? = nil,
        suggestedDestination: String? = nil,
        confidenceScore: Int? = nil,
        confidenceBreakdown: [String: JSONValue] = [:],
        duplicateOf: String? = nil
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
            duplicateOf: duplicateOf,
            confidenceScore: confidenceScore,
            confidenceBreakdown: confidenceBreakdown,
            tier: tier
        )
    }

    // MARK: - Not found at all

    func test_compute_fileIDNotFound_returnsNil() {
        let projection = ReviewDetailProjection.compute(records: [], fileID: "missing")
        XCTAssertNil(projection)
    }

    // MARK: - Kind detection

    func test_compute_approvalRequiredNotExecuted_kindIsNeedsInput() {
        let records = [makeRecord(tier: .approvalRequired, status: "scored")]
        let projection = ReviewDetailProjection.compute(records: records, fileID: "1")
        XCTAssertEqual(projection?.kind, .needsInput)
    }

    func test_compute_approvalRequiredExecuted_kindIsNil() {
        let records = [makeRecord(tier: .approvalRequired, status: "executed")]
        let projection = ReviewDetailProjection.compute(records: records, fileID: "1")
        XCTAssertNil(projection?.kind)
    }

    func test_compute_reviewRequired_kindIsFlagged_regardlessOfStatus() {
        let records = [makeRecord(tier: .reviewRequired, status: "executed")]
        let projection = ReviewDetailProjection.compute(records: records, fileID: "1")
        XCTAssertEqual(projection?.kind, .flagged)
    }

    func test_compute_autoTier_kindIsNil() {
        let records = [makeRecord(tier: .auto)]
        let projection = ReviewDetailProjection.compute(records: records, fileID: "1")
        XCTAssertNil(projection?.kind)
    }

    func test_compute_untiered_kindIsNil() {
        let records = [makeRecord(tier: nil)]
        let projection = ReviewDetailProjection.compute(records: records, fileID: "1")
        XCTAssertNil(projection?.kind)
    }

    // MARK: - Content fidelity

    func test_compute_needsInput_carriesFullContentAndBreakdown() {
        let records = [
            makeRecord(
                originalName: "IMG_4821.pdf",
                category: .invoice,
                tier: .approvalRequired,
                suggestedName: "invoice_acme.pdf",
                suggestedDestination: "/Users/fixture/Organized Downloads/Invoices/invoice_acme.pdf",
                confidenceScore: 87,
                confidenceBreakdown: ["non_english_content": .number(-10)],
                duplicateOf: "some-other-file-id"
            ),
        ]
        let projection = ReviewDetailProjection.compute(records: records, fileID: "1")

        XCTAssertEqual(projection?.originalName, "IMG_4821.pdf")
        XCTAssertEqual(projection?.category, .invoice)
        XCTAssertEqual(projection?.suggestedName, "invoice_acme.pdf")
        XCTAssertEqual(projection?.suggestedDestination, "/Users/fixture/Organized Downloads/Invoices/invoice_acme.pdf")
        XCTAssertEqual(projection?.confidenceScore, 87)
        XCTAssertTrue(projection?.isDuplicate ?? false)
        XCTAssertEqual(projection?.breakdown, [.init(text: "Non-English content detected", points: -10)])
        XCTAssertNil(projection?.flagReason, "flagReason is scoped to .flagged only")
    }

    // MARK: - Flag reason integration (flagged only)

    func test_compute_flagged_carriesFlagReasonFromResolver() {
        let records = [makeRecord(category: .unknown, tier: .reviewRequired)]
        let projection = ReviewDetailProjection.compute(records: records, fileID: "1")

        XCTAssertEqual(projection?.flagReason, "This file's category couldn't be determined")
    }

    // MARK: - Correct record picked out of several

    func test_compute_picksMatchingRecordAmongMany() {
        let records = [
            makeRecord(fileID: "a", tier: .approvalRequired),
            makeRecord(fileID: "b", tier: .reviewRequired),
            makeRecord(fileID: "c", tier: .auto),
        ]
        let projection = ReviewDetailProjection.compute(records: records, fileID: "b")

        XCTAssertEqual(projection?.fileID, "b")
        XCTAssertEqual(projection?.kind, .flagged)
    }
}
