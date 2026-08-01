import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

final class ExecuteResultProjectionTests: XCTestCase {

    private func makeRow(fileID: String, originalName: String? = nil, suggestedDestination: String? = nil) -> ExecuteConfirmationProjection.FileRow {
        ExecuteConfirmationProjection.FileRow(
            fileID: fileID,
            originalName: originalName ?? "\(fileID).pdf",
            suggestedName: nil,
            suggestedDestination: suggestedDestination
        )
    }

    private func makeEntry(
        fileID: String,
        action: String,
        to: String? = nil,
        details: JSONValue? = nil,
        timestamp: String = "2026-08-01T10:00:00Z"
    ) -> ActionLogEntry {
        ActionLogEntry(
            batchID: "batch-1",
            fileID: fileID,
            action: action,
            from: "/Users/fixture/Downloads/\(fileID).pdf",
            to: to,
            timestamp: timestamp,
            approvedBy: "auto",
            details: details
        )
    }

    // MARK: - Full success

    func test_compute_allFiledSuccessfully_isFullSuccess() {
        let rows = [makeRow(fileID: "1", suggestedDestination: "Finance/"), makeRow(fileID: "2", suggestedDestination: "Image/")]
        let entries = [
            makeEntry(fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf"),
            makeEntry(fileID: "2", action: "move_rename", to: "/dest/Image/2.pdf"),
        ]
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertTrue(result.isFullSuccess)
        XCTAssertEqual(result.totalAttempted, 2)
        XCTAssertEqual(result.filedCount, 2)
        XCTAssertTrue(result.problemRows.isEmpty)
    }

    func test_compute_archiveDuplicateAndSupersededActions_alsoCountAsFiled() {
        let rows = [makeRow(fileID: "1"), makeRow(fileID: "2")]
        let entries = [
            makeEntry(fileID: "1", action: "archive_duplicate", to: "/dest/~ARCHIVE~/Duplicates/1.pdf"),
            makeEntry(fileID: "2", action: "archive_superseded_version", to: "/dest/~ARCHIVE~/Old Versions/2.pdf"),
        ]
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertTrue(result.isFullSuccess)
        XCTAssertEqual(result.filedRows.map(\.destinationFolder), ["Duplicates", "Old Versions"])
    }

    // MARK: - Partial failure, per-file isolation

    func test_compute_oneFileErrors_isolatedFromRestOfBatch() {
        let rows = [makeRow(fileID: "1"), makeRow(fileID: "2")]
        let entries = [
            makeEntry(fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf"),
            makeEntry(fileID: "2", action: "error", details: .object(["error_detail": .string("Permission denied")])),
        ]
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertFalse(result.isFullSuccess)
        XCTAssertEqual(result.totalAttempted, 2)
        XCTAssertEqual(result.filedCount, 1)
        XCTAssertEqual(result.problemRows.count, 1)
        XCTAssertEqual(result.problemRows.first?.fileID, "2")
        XCTAssertEqual(result.problemRows.first?.reason, "Permission denied")
    }

    func test_compute_errorEntryWithoutDetail_fallsBackToGenericReason() {
        let rows = [makeRow(fileID: "1")]
        let entries = [makeEntry(fileID: "1", action: "error")]
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertEqual(result.problemRows.first?.reason, "Didn't file — the engine reported an error.")
    }

    // MARK: - Missing entry entirely (interrupted execute)

    func test_compute_fileWithNoActionLogEntryAtAll_treatedAsNotFiled_neverAssumedComplete() {
        let rows = [makeRow(fileID: "1"), makeRow(fileID: "2")]
        let entries = [makeEntry(fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf")]
        // File "2" has no matching entry at all — e.g. execution was
        // interrupted before it was ever reached.
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertEqual(result.filedCount, 1)
        XCTAssertEqual(result.problemRows.count, 1)
        XCTAssertEqual(result.problemRows.first?.fileID, "2")
        XCTAssertFalse(result.isFullSuccess)
    }

    // MARK: - Last-entry-wins semantics (mirrors src/main.py's own reconciliation)

    func test_compute_multipleEntriesForSameFile_lastOneWins() {
        let rows = [makeRow(fileID: "1")]
        // An earlier attempt errored, a later one (after some retry/rerun
        // mechanism at the engine level) succeeded — the log is
        // oldest-first, so the later entry must win.
        let entries = [
            makeEntry(fileID: "1", action: "error", details: .object(["error_detail": .string("locked")]), timestamp: "2026-08-01T10:00:00Z"),
            makeEntry(fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf", timestamp: "2026-08-01T10:05:00Z"),
        ]
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertTrue(result.isFullSuccess)
        XCTAssertEqual(result.filedRows.first?.destinationFolder, "Finance")
    }

    // MARK: - Entries for files outside the confirmed batch are ignored

    func test_compute_actionLogEntriesForOtherFiles_ignored() {
        let rows = [makeRow(fileID: "1")]
        let entries = [
            makeEntry(fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf"),
            makeEntry(fileID: "unrelated", action: "error", details: .object(["error_detail": .string("noise")])),
        ]
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertEqual(result.totalAttempted, 1)
        XCTAssertTrue(result.isFullSuccess)
    }

    // MARK: - Destination fallback when `to` is absent on a successful entry

    func test_compute_successfulEntryWithoutTo_fallsBackToSuggestedDestination() {
        let rows = [makeRow(fileID: "1", suggestedDestination: "Finance/")]
        let entries = [makeEntry(fileID: "1", action: "move_rename", to: nil)]
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertEqual(result.filedRows.first?.destinationFolder, "Finance")
    }

    // MARK: - Destination breakdown: grouping and deterministic order

    func test_compute_destinationBreakdown_groupsAndSortsByDescendingCountThenName() {
        let rows = [makeRow(fileID: "1"), makeRow(fileID: "2"), makeRow(fileID: "3"), makeRow(fileID: "4")]
        let entries = [
            makeEntry(fileID: "1", action: "move_rename", to: "/dest/Images/1.jpg"),
            makeEntry(fileID: "2", action: "move_rename", to: "/dest/Finance/2.pdf"),
            makeEntry(fileID: "3", action: "move_rename", to: "/dest/Finance/3.pdf"),
            makeEntry(fileID: "4", action: "move_rename", to: "/dest/Finance/4.pdf"),
        ]
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertEqual(result.destinationBreakdown.map(\.destinationFolder), ["Finance", "Images"])
        XCTAssertEqual(result.destinationBreakdown.map(\.count), [3, 1])
    }

    func test_compute_destinationBreakdown_excludesProblemRows() {
        let rows = [makeRow(fileID: "1"), makeRow(fileID: "2")]
        let entries = [
            makeEntry(fileID: "1", action: "move_rename", to: "/dest/Finance/1.pdf"),
            makeEntry(fileID: "2", action: "error", details: .object(["error_detail": .string("locked")])),
        ]
        let result = ExecuteResultProjection.compute(confirmedRows: rows, actionLogEntries: entries)

        XCTAssertEqual(result.destinationBreakdown.map(\.destinationFolder), ["Finance"])
        XCTAssertEqual(result.destinationBreakdown.map(\.count), [1])
    }

    // MARK: - Empty batch

    func test_compute_emptyConfirmedRows_producesEmptyResult() {
        let result = ExecuteResultProjection.compute(confirmedRows: [], actionLogEntries: [])
        XCTAssertEqual(result.totalAttempted, 0)
        XCTAssertTrue(result.filedRows.isEmpty)
        XCTAssertTrue(result.problemRows.isEmpty)
        XCTAssertTrue(result.isFullSuccess)
    }
}
