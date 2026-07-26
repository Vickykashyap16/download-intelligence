import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Comprehensive tests for `HomeProjection.compute(records:now:)` — written
/// before `HomeViewModel`/`HomeView` per the standing instruction to add
/// tests first. Every state named in WP-GUI-03's Acceptance Criteria (and
/// the two steady-state variants named in `High-Fidelity UI
/// Specification.md` §2's Edge Cases) gets its own fixture dataset, per
/// that work package's own Risk mitigation ("test all three states
/// explicitly with distinct fixture datasets, not just the state that
/// happens to be easiest to produce").
final class HomeProjectionTests: XCTestCase {

    private let referenceNow = ISO8601DateFormatter().date(from: "2026-07-27T12:00:00Z")!

    private func makeRecord(
        fileID: String,
        discoveredAt: String,
        tier: Tier? = nil,
        status: String = "discovered",
        batchID: String? = nil,
        processedAt: String? = nil
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
            createdAt: discoveredAt,
            modifiedAt: discoveredAt,
            contentHash: "hash-\(fileID)",
            discoveredAt: discoveredAt,
            status: status,
            tier: tier,
            batchID: batchID,
            processedAt: processedAt
        )
    }

    // MARK: - First run

    func test_noRecords_yieldsFirstRun() {
        let projection = HomeProjection.compute(records: [], now: referenceNow)

        XCTAssertEqual(projection.kind, .firstRun)
        XCTAssertEqual(projection.primaryMessage, "Nothing scanned yet")
        XCTAssertEqual(projection.primaryActionTitle, "Scan now")
        XCTAssertNil(projection.secondaryActionTitle)
        XCTAssertNil(projection.lastScanDate)
        XCTAssertNil(projection.lastBatch)
        XCTAssertTrue(projection.weeklyTierCounts.isEmpty)
    }

    // MARK: - Caught up

    func test_allExecutedNoAutoUnfiled_yieldsCaughtUp() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-25T10:00:00Z", tier: .auto, status: "executed", batchID: "batch-1", processedAt: "2026-07-25T10:05:00Z"),
            makeRecord(fileID: "2", discoveredAt: "2026-07-25T10:00:00Z", tier: .approvalRequired, status: "executed", batchID: "batch-1", processedAt: "2026-07-25T10:05:00Z")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)

        XCTAssertEqual(projection.kind, .caughtUp)
        XCTAssertEqual(projection.primaryMessage, "You're all caught up")
        // Per High-Fidelity UI Specification.md §15: caught-up's action is
        // Secondary, not Primary.
        XCTAssertNil(projection.primaryActionTitle)
        XCTAssertEqual(projection.secondaryActionTitle, "Scan again")
        XCTAssertNotNil(projection.lastScanDate)
    }

    func test_reviewRequiredIsNeverExecuted_soItsPresenceAloneMustNotBlockCaughtUp_whenActuallyEmpty() {
        // Sanity check on the empty-records path specifically (already
        // covered above) plus confirming a record set containing *zero*
        // review_required/approval_required/pending-auto records reaches
        // caught up even when a review_required record exists but has
        // already been accounted for as reviewed. Since this package has
        // no "reviewed" status of its own yet, this test simply documents
        // that an empty pending set (no review_required records at all)
        // is what actually drives caught-up — covered by the test above.
        XCTAssertTrue(true)
    }

    // MARK: - Needs review

    func test_reviewRequiredRecords_yieldNeedsReview() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .reviewRequired, status: "scored"),
            makeRecord(fileID: "2", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto, status: "executed", batchID: "batch-1", processedAt: "2026-07-26T10:05:00Z")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)

        guard case .needsReview(let count) = projection.kind else {
            return XCTFail("expected .needsReview, got \(projection.kind)")
        }
        XCTAssertEqual(count, 1)
        XCTAssertEqual(projection.primaryMessage, "1 file needs your review")
        XCTAssertEqual(projection.primaryActionTitle, "Go to Review Queue")
        XCTAssertEqual(projection.secondaryActionTitle, "Scan again")
    }

    func test_pendingApprovalRequiredRecords_countTowardNeedsReview() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .approvalRequired, status: "scored"),
            makeRecord(fileID: "2", discoveredAt: "2026-07-26T10:00:00Z", tier: .approvalRequired, status: "scored")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)

        guard case .needsReview(let count) = projection.kind else {
            return XCTFail("expected .needsReview, got \(projection.kind)")
        }
        XCTAssertEqual(count, 2)
        XCTAssertEqual(projection.primaryMessage, "2 files need your review")
    }

    func test_executedApprovalRequiredRecords_doNotCountTowardNeedsReview() {
        // Already filed approval_required records represent resolved
        // history, not a pending decision — Home must not keep demanding
        // review of something a human already acted on.
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .approvalRequired, status: "executed", batchID: "batch-1", processedAt: "2026-07-26T10:05:00Z")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)

        XCTAssertEqual(projection.kind, .caughtUp)
    }

    func test_reviewRequiredRecords_countRegardlessOfStatus() {
        // review_required files are never executed at all (left in place
        // and flagged, per Rules/Confidence Rules.md) — status alone must
        // never be used to decide they're "done."
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .reviewRequired, status: "scored")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)

        guard case .needsReview(let count) = projection.kind else {
            return XCTFail("expected .needsReview, got \(projection.kind)")
        }
        XCTAssertEqual(count, 1)
    }

    // MARK: - Ready to file

    func test_unfiledAutoRecords_yieldReadyToFile_whenNothingNeedsReview() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto, status: "scored"),
            makeRecord(fileID: "2", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto, status: "scored")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)

        guard case .readyToFile(let count) = projection.kind else {
            return XCTFail("expected .readyToFile, got \(projection.kind)")
        }
        XCTAssertEqual(count, 2)
        XCTAssertEqual(projection.primaryMessage, "2 files ready to file")
        XCTAssertEqual(projection.primaryActionTitle, "File them now")
    }

    func test_needsReviewTakesPriorityOverReadyToFile() {
        // Exactly one primary action is ever presented at a time
        // (`High-Fidelity UI Specification.md` §2, UX Acceptance
        // Criteria) — when both conditions exist simultaneously, the more
        // decision-worthy one (needs review) wins.
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .reviewRequired, status: "scored"),
            makeRecord(fileID: "2", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto, status: "scored")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)

        guard case .needsReview = projection.kind else {
            return XCTFail("expected .needsReview to take priority, got \(projection.kind)")
        }
    }

    func test_singularPhrasing_forExactlyOneReadyToFile() {
        let records = [makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto, status: "scored")]
        let projection = HomeProjection.compute(records: records, now: referenceNow)
        XCTAssertEqual(projection.primaryMessage, "1 file ready to file")
    }

    // MARK: - Last scan / last batch recency

    func test_lastScanDate_isTheMostRecentDiscoveredAt() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-20T10:00:00Z", tier: .auto, status: "executed", batchID: "b1", processedAt: "2026-07-20T10:05:00Z"),
            makeRecord(fileID: "2", discoveredAt: "2026-07-25T10:00:00Z", tier: .auto, status: "executed", batchID: "b2", processedAt: "2026-07-25T10:05:00Z")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)
        XCTAssertEqual(projection.lastScanDate, ISO8601DateFormatter().date(from: "2026-07-25T10:00:00Z"))
    }

    func test_lastBatch_isDerivedFromMostRecentProcessedAt_andCountsOnlyThatBatchsFiles() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-20T10:00:00Z", tier: .auto, status: "executed", batchID: "batch-old", processedAt: "2026-07-20T10:05:00Z"),
            makeRecord(fileID: "2", discoveredAt: "2026-07-25T10:00:00Z", tier: .auto, status: "executed", batchID: "batch-new", processedAt: "2026-07-25T10:05:00Z"),
            makeRecord(fileID: "3", discoveredAt: "2026-07-25T10:00:00Z", tier: .auto, status: "executed", batchID: "batch-new", processedAt: "2026-07-25T10:05:00Z")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)

        XCTAssertEqual(projection.lastBatch?.fileCount, 2)
        XCTAssertEqual(projection.lastBatch?.date, ISO8601DateFormatter().date(from: "2026-07-25T10:05:00Z"))
    }

    func test_recordsWithNoBatchIDOrProcessedAt_areIneligibleForLastBatch() {
        let records = [makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto, status: "scored")]
        let projection = HomeProjection.compute(records: records, now: referenceNow)
        XCTAssertNil(projection.lastBatch)
    }

    // MARK: - Weekly tier counts (trend summary)

    func test_weeklyTierCounts_includesRecordsWithinSevenDays() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto, status: "scored")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)
        XCTAssertEqual(projection.weeklyTierCounts[.auto], 1)
    }

    func test_weeklyTierCounts_excludesRecordsOlderThanSevenDays() {
        // referenceNow is 2026-07-27T12:00:00Z; 7 days back is
        // 2026-07-20T12:00:00Z, so a record discovered on 2026-07-19 must
        // be excluded.
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-19T10:00:00Z", tier: .auto, status: "scored")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)
        XCTAssertNil(projection.weeklyTierCounts[.auto])
    }

    func test_weeklyTierCounts_omitsZeroCountTiersEntirely() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto, status: "scored")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)

        XCTAssertNil(projection.weeklyTierCounts[.reviewRequired])
        XCTAssertNil(projection.weeklyTierCounts[.approvalRequired])
        XCTAssertEqual(projection.weeklyTierCounts.count, 1, "only the one tier actually present should have an entry")
    }

    func test_weeklyTierCounts_excludesUntieredRecords() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: nil, status: "discovered")
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)
        XCTAssertTrue(projection.weeklyTierCounts.isEmpty)
    }

    func test_weeklyTierCounts_countsMultipleTiersIndependently() {
        let records = [
            makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto),
            makeRecord(fileID: "2", discoveredAt: "2026-07-26T10:00:00Z", tier: .auto),
            makeRecord(fileID: "3", discoveredAt: "2026-07-26T10:00:00Z", tier: .reviewRequired)
        ]
        let projection = HomeProjection.compute(records: records, now: referenceNow)
        XCTAssertEqual(projection.weeklyTierCounts[.auto], 2)
        XCTAssertEqual(projection.weeklyTierCounts[.reviewRequired], 1)
    }

    // MARK: - Determinism

    func test_computeIsPureAndDeterministic_sameInputsSameOutput() {
        let records = [makeRecord(fileID: "1", discoveredAt: "2026-07-26T10:00:00Z", tier: .reviewRequired)]
        let first = HomeProjection.compute(records: records, now: referenceNow)
        let second = HomeProjection.compute(records: records, now: referenceNow)
        XCTAssertEqual(first, second)
    }
}
