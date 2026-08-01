import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

final class HistoryProjectionTests: XCTestCase {

    private func makeRecord(
        fileID: String,
        originalName: String? = nil,
        tier: Tier? = .auto,
        confidenceScore: Int? = 97,
        status: String = "executed"
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
            confidenceScore: confidenceScore,
            tier: tier
        )
    }

    private func makeEntry(
        batchID: String,
        fileID: String,
        action: String,
        from: String? = nil,
        to: String? = nil,
        details: JSONValue? = nil,
        timestamp: String = "2026-08-01T10:00:00Z"
    ) -> ActionLogEntry {
        ActionLogEntry(
            batchID: batchID,
            fileID: fileID,
            action: action,
            from: from ?? "/Users/fixture/Downloads/\(fileID).pdf",
            to: to,
            timestamp: timestamp,
            approvedBy: "auto",
            details: details
        )
    }

    // MARK: - Basic grouping and full success

    func test_compute_singleBatchFullSuccess_producesOneBatchWithFiledRows() {
        let entries = [
            makeEntry(batchID: "batch-1", fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf"),
            makeEntry(batchID: "batch-1", fileID: "2", action: "move_rename", to: "/dest/Images/2.pdf"),
        ]
        let records = [makeRecord(fileID: "1"), makeRecord(fileID: "2")]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: records)

        XCTAssertEqual(projection.batches.count, 1)
        let batch = projection.batches[0]
        XCTAssertEqual(batch.batchID, "batch-1")
        XCTAssertEqual(batch.filedCount, 2)
        XCTAssertTrue(batch.problemRows.isEmpty)
        XCTAssertFalse(batch.isFullyUndone)
        XCTAssertFalse(batch.isPartiallyUndone)
    }

    // MARK: - Pipeline-stage entries sharing a batch_id are excluded

    func test_compute_batchWithOnlyPipelineStageEntries_excludedEntirely() {
        // A scan session that discovered/classified/scored files but never
        // reached execute — batch_id is real and shared, but there's
        // nothing to show in History yet.
        let entries = [
            makeEntry(batchID: "batch-scan-1", fileID: "1", action: "discover"),
            makeEntry(batchID: "batch-scan-1", fileID: "1", action: "classify"),
            makeEntry(batchID: "batch-scan-1", fileID: "1", action: "score_confidence"),
        ]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: [makeRecord(fileID: "1")])

        XCTAssertTrue(projection.isEmpty)
    }

    func test_compute_batchWithMixedPipelineAndFilingEntries_onlyFilingEntriesCounted() {
        // Same batch_id spans this file's whole journey (real engine
        // behavior — batch_id is assigned once at discovery) — only the
        // execute/undo-relevant entries should ever surface in a batch.
        let entries = [
            makeEntry(batchID: "batch-1", fileID: "1", action: "discover"),
            makeEntry(batchID: "batch-1", fileID: "1", action: "classify"),
            makeEntry(batchID: "batch-1", fileID: "1", action: "score_confidence"),
            makeEntry(batchID: "batch-1", fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf"),
        ]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: [makeRecord(fileID: "1")])

        XCTAssertEqual(projection.batches.count, 1)
        XCTAssertEqual(projection.batches[0].filedCount, 1)
        XCTAssertEqual(projection.batches[0].filedRows.first?.finalLocation, "/dest/Finance/1.pdf")
    }

    // MARK: - Partial failure

    func test_compute_partialFailureBatch_reportsFiledAndProblemRows() {
        let entries = [
            makeEntry(batchID: "batch-1", fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf"),
            makeEntry(batchID: "batch-1", fileID: "2", action: "error", details: .object(["error_detail": .string("Permission denied")])),
        ]
        let records = [makeRecord(fileID: "1"), makeRecord(fileID: "2")]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: records)

        let batch = projection.batches[0]
        XCTAssertEqual(batch.filedCount, 1)
        XCTAssertEqual(batch.totalAttempted, 2)
        XCTAssertEqual(batch.problemRows.count, 1)
        XCTAssertEqual(batch.problemRows.first?.reason, "Permission denied")
    }

    // MARK: - Undo status reflected accurately

    func test_compute_fullyUndoneBatch_marksAllRowsWasUndoneAndIsFullyUndone() {
        let entries = [
            makeEntry(batchID: "batch-1", fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf", timestamp: "2026-08-01T10:00:00Z"),
            makeEntry(batchID: "batch-1", fileID: "2", action: "move_rename", to: "/dest/Images/2.pdf", timestamp: "2026-08-01T10:00:01Z"),
            makeEntry(batchID: "batch-1", fileID: "1", action: "undo", to: "/Users/fixture/Downloads/1.pdf", timestamp: "2026-08-01T11:00:00Z"),
            makeEntry(batchID: "batch-1", fileID: "2", action: "undo", to: "/Users/fixture/Downloads/2.pdf", timestamp: "2026-08-01T11:00:01Z"),
        ]
        let records = [makeRecord(fileID: "1", status: "scored"), makeRecord(fileID: "2", status: "scored")]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: records)

        let batch = projection.batches[0]
        XCTAssertEqual(batch.filedCount, 2)
        XCTAssertTrue(batch.filedRows.allSatisfy(\.wasUndone))
        XCTAssertTrue(batch.isFullyUndone)
        XCTAssertFalse(batch.isPartiallyUndone)
        // Historically accurate: still reports where it *was* filed, even
        // though it's since been restored.
        XCTAssertEqual(batch.filedRows.first { $0.fileID == "1" }?.finalLocation, "/dest/Finance/1.pdf")
    }

    func test_compute_partiallyUndoneBatch_marksOnlyUndoneRowsAndIsPartiallyUndone() {
        let entries = [
            makeEntry(batchID: "batch-1", fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf", timestamp: "2026-08-01T10:00:00Z"),
            makeEntry(batchID: "batch-1", fileID: "2", action: "move_rename", to: "/dest/Images/2.pdf", timestamp: "2026-08-01T10:00:01Z"),
            makeEntry(batchID: "batch-1", fileID: "1", action: "undo", to: "/Users/fixture/Downloads/1.pdf", timestamp: "2026-08-01T11:00:00Z"),
        ]
        let records = [makeRecord(fileID: "1", status: "scored"), makeRecord(fileID: "2")]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: records)

        let batch = projection.batches[0]
        XCTAssertFalse(batch.isFullyUndone)
        XCTAssertTrue(batch.isPartiallyUndone)
        XCTAssertEqual(batch.filedRows.first { $0.fileID == "1" }?.wasUndone, true)
        XCTAssertEqual(batch.filedRows.first { $0.fileID == "2" }?.wasUndone, false)
    }

    // MARK: - Batch timestamp: earliest filing entry, not a later undo

    func test_compute_batchTimestamp_isEarliestFilingEntryNotLaterUndo() {
        let entries = [
            makeEntry(batchID: "batch-1", fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf", timestamp: "2026-08-01T10:00:00Z"),
            makeEntry(batchID: "batch-1", fileID: "1", action: "undo", to: "/Users/fixture/Downloads/1.pdf", timestamp: "2026-08-01T15:00:00Z"),
        ]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: [makeRecord(fileID: "1")])

        XCTAssertEqual(projection.batches[0].timestamp, "2026-08-01T10:00:00Z")
    }

    // MARK: - Tier breakdown

    func test_compute_tierBreakdown_groupsAndSortsByDescendingCountThenTier() {
        let entries = [
            makeEntry(batchID: "batch-1", fileID: "1", action: "move_rename", to: "/dest/A/1.pdf"),
            makeEntry(batchID: "batch-1", fileID: "2", action: "move_rename", to: "/dest/B/2.pdf"),
            makeEntry(batchID: "batch-1", fileID: "3", action: "move_rename", to: "/dest/C/3.pdf"),
        ]
        let records = [
            makeRecord(fileID: "1", tier: .auto),
            makeRecord(fileID: "2", tier: .auto),
            makeRecord(fileID: "3", tier: .approvalRequired),
        ]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: records)

        let breakdown = projection.batches[0].tierBreakdown
        XCTAssertEqual(breakdown.map(\.tier), [.auto, .approvalRequired])
        XCTAssertEqual(breakdown.map(\.count), [2, 1])
    }

    // MARK: - Multiple batches, most recent first

    func test_compute_multipleBatches_sortedMostRecentFirst() {
        let entries = [
            makeEntry(batchID: "batch-old", fileID: "1", action: "move_rename", to: "/dest/A/1.pdf", timestamp: "2026-07-01T10:00:00Z"),
            makeEntry(batchID: "batch-new", fileID: "2", action: "move_rename", to: "/dest/B/2.pdf", timestamp: "2026-08-01T10:00:00Z"),
        ]
        let records = [makeRecord(fileID: "1"), makeRecord(fileID: "2")]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: records)

        XCTAssertEqual(projection.batches.map(\.batchID), ["batch-new", "batch-old"])
    }

    // MARK: - Empty

    func test_compute_noEntriesAtAll_producesEmptyProjection() {
        let projection = HistoryProjection.compute(actionLogEntries: [], records: [])
        XCTAssertTrue(projection.isEmpty)
    }

    // MARK: - Missing metadata record falls back to a path-derived name

    func test_compute_fileWithNoMetadataRecord_fallsBackToPathDerivedName() {
        let entries = [
            makeEntry(batchID: "batch-1", fileID: "orphan", action: "move_rename", from: "/Users/fixture/Downloads/orphan_file.pdf", to: "/dest/A/orphan_file.pdf"),
        ]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: [])

        XCTAssertEqual(projection.batches[0].filedRows.first?.originalName, "orphan_file.pdf")
    }

    // MARK: - Same file_id appearing in two different batches never cross-contaminates

    func test_compute_sameFileIDAcrossTwoBatches_eachBatchReflectsItsOwnEntry() {
        let entries = [
            makeEntry(batchID: "batch-1", fileID: "1", action: "move_rename", to: "/dest/A/1.pdf", timestamp: "2026-07-01T10:00:00Z"),
            makeEntry(batchID: "batch-1", fileID: "1", action: "undo", to: "/Users/fixture/Downloads/1.pdf", timestamp: "2026-07-01T11:00:00Z"),
            makeEntry(batchID: "batch-2", fileID: "1", action: "move_rename", to: "/dest/B/1.pdf", timestamp: "2026-08-01T10:00:00Z"),
        ]
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: [makeRecord(fileID: "1")])

        XCTAssertEqual(projection.batches.count, 2)
        let newBatch = projection.batches.first { $0.batchID == "batch-2" }
        let oldBatch = projection.batches.first { $0.batchID == "batch-1" }
        XCTAssertEqual(newBatch?.filedRows.first?.wasUndone, false)
        XCTAssertEqual(oldBatch?.filedRows.first?.wasUndone, true)
    }
}
