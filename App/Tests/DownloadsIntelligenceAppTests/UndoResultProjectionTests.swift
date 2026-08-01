import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

final class UndoResultProjectionTests: XCTestCase {

    private func makeRow(fileID: String, originalName: String? = nil) -> ExecuteResultProjection.FiledRow {
        ExecuteResultProjection.FiledRow(
            fileID: fileID,
            originalName: originalName ?? "\(fileID).pdf",
            destinationFolder: "Finance"
        )
    }

    private func makeEntry(
        fileID: String,
        action: String,
        from: String? = nil,
        details: JSONValue? = nil,
        timestamp: String = "2026-08-01T10:00:00Z"
    ) -> ActionLogEntry {
        ActionLogEntry(
            batchID: "batch-1",
            fileID: fileID,
            action: action,
            from: from ?? "/dest/Finance/\(fileID).pdf",
            to: "/Users/fixture/Downloads/\(fileID).pdf",
            timestamp: timestamp,
            approvedBy: "user",
            details: details
        )
    }

    // MARK: - Full success

    func test_compute_allRestoredSuccessfully_isFullSuccess() {
        let rows = [makeRow(fileID: "1"), makeRow(fileID: "2")]
        let entries = [
            makeEntry(fileID: "1", action: "undo"),
            makeEntry(fileID: "2", action: "undo"),
        ]
        let result = UndoResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertTrue(result.isFullSuccess)
        XCTAssertEqual(result.totalAttempted, 2)
        XCTAssertEqual(result.restoredCount, 2)
        XCTAssertTrue(result.problemRows.isEmpty)
    }

    // MARK: - Partial failure, per-file isolation (e.g. a restoration conflict)

    func test_compute_oneFileErrors_isolatedFromRestOfBatch() {
        let rows = [makeRow(fileID: "1"), makeRow(fileID: "2")]
        let entries = [
            makeEntry(fileID: "1", action: "undo"),
            makeEntry(fileID: "2", action: "error", details: .object(["error_detail": .string("Something now occupies the original path")])),
        ]
        let result = UndoResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertFalse(result.isFullSuccess)
        XCTAssertEqual(result.totalAttempted, 2)
        XCTAssertEqual(result.restoredCount, 1)
        XCTAssertEqual(result.problemRows.count, 1)
        XCTAssertEqual(result.problemRows.first?.fileID, "2")
        XCTAssertEqual(result.problemRows.first?.reason, "Something now occupies the original path")
    }

    func test_compute_errorEntryWithoutDetail_fallsBackToGenericReason() {
        let rows = [makeRow(fileID: "1")]
        let entries = [makeEntry(fileID: "1", action: "error")]
        let result = UndoResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertEqual(result.problemRows.first?.reason, "Didn't restore — the engine reported an error.")
    }

    // MARK: - Missing entry entirely (interrupted undo)

    func test_compute_fileWithNoActionLogEntryAtAll_treatedAsNotRestored_neverAssumedComplete() {
        let rows = [makeRow(fileID: "1"), makeRow(fileID: "2")]
        let entries = [makeEntry(fileID: "1", action: "undo")]
        // File "2" has no matching entry at all — e.g. undo was interrupted
        // before it was ever reached.
        let result = UndoResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertEqual(result.restoredCount, 1)
        XCTAssertEqual(result.problemRows.count, 1)
        XCTAssertEqual(result.problemRows.first?.fileID, "2")
        XCTAssertFalse(result.isFullSuccess)
    }

    // MARK: - Last-entry-wins semantics

    func test_compute_multipleEntriesForSameFile_lastOneWins() {
        let rows = [makeRow(fileID: "1")]
        let entries = [
            makeEntry(fileID: "1", action: "error", details: .object(["error_detail": .string("collision")]), timestamp: "2026-08-01T10:00:00Z"),
            makeEntry(fileID: "1", action: "undo", timestamp: "2026-08-01T10:05:00Z"),
        ]
        let result = UndoResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertTrue(result.isFullSuccess)
        XCTAssertEqual(result.restoredRows.first?.fileID, "1")
    }

    // MARK: - Entries for files outside the confirmed batch are ignored

    func test_compute_actionLogEntriesForOtherFiles_ignored() {
        let rows = [makeRow(fileID: "1")]
        let entries = [
            makeEntry(fileID: "1", action: "undo"),
            makeEntry(fileID: "unrelated", action: "error", details: .object(["error_detail": .string("noise")])),
        ]
        let result = UndoResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertEqual(result.totalAttempted, 1)
        XCTAssertTrue(result.isFullSuccess)
    }

    // MARK: - Empty batch

    func test_compute_emptyConfirmedRows_producesEmptyResult() {
        let result = UndoResultProjection.compute(confirmedRows: [], actionLogEntries: [])
        XCTAssertEqual(result.totalAttempted, 0)
        XCTAssertTrue(result.restoredRows.isEmpty)
        XCTAssertTrue(result.problemRows.isEmpty)
        XCTAssertTrue(result.isFullSuccess)
    }
}
