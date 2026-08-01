import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `HistoryViewModel` against a real `EngineBridge`.
///
/// Unlike `ExecuteViewModelTests`/`UndoViewModelTests`, `HistoryViewModel`
/// never calls `bridge.run(...)` — it only ever calls `readActionLog()`/
/// `readMetadataStore()`, neither of which invokes a subprocess at all
/// (`EngineBridge.readActionLog()`/`readMetadataStore()` both go through
/// `withVersionGate(...)`, a local `Release/VERSIONS.md` read plus a local
/// `ActionLogReader`/`MetadataStoreReader` file read — no `python3`
/// process is ever launched). So, mirroring `ReviewQueueViewModelTests`'
/// own precedent (the other purely-read-only view model in this package),
/// these tests build minimal fixture projects inline with plain file
/// writes rather than needing a checked-in `Fixtures/HistoryEngineProject/`
/// directory with its own fake `src/cli.py` — there's no command for a
/// fake CLI to ever handle.
///
/// The one exception is the cross-entry-point consistency test at the
/// bottom, which genuinely does invoke `undo` as a real subprocess (via
/// `UndoViewModel`) — that test reuses WP-GUI-08's existing, checked-in,
/// unmodified `UndoingEngineProject` fixture read-only (two separate
/// isolated copies, one per entry point), rather than inventing a second
/// undo-capable fixture or touching that already-frozen one.
@MainActor
final class HistoryViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("HistoryViewModelTests-\(UUID().uuidString)")
    }

    private func makeProject(recordsJSON: String, actionLogLines: [String]) throws -> URL {
        let root = makeTempDirectory()
        let fm = FileManager.default
        try fm.createDirectory(at: root.appendingPathComponent("Release"), withIntermediateDirectories: true)
        try fm.createDirectory(at: root.appendingPathComponent("Database/Metadata"), withIntermediateDirectories: true)
        try fm.createDirectory(at: root.appendingPathComponent("Runtime/Logs"), withIntermediateDirectories: true)

        try "**Pipeline Version: 0.8.0**\n".write(
            to: root.appendingPathComponent("Release/VERSIONS.md"), atomically: true, encoding: .utf8
        )
        try recordsJSON.write(
            to: root.appendingPathComponent("Database/Metadata/metadata_store.json"), atomically: true, encoding: .utf8
        )
        try (actionLogLines.joined(separator: "\n") + "\n").write(
            to: root.appendingPathComponent("Runtime/Logs/action_log.jsonl"), atomically: true, encoding: .utf8
        )
        return root
    }

    private func makeBridge(projectRoot: URL) -> EngineBridge {
        EngineBridge(configuration: .init(
            projectRootURL: projectRoot,
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
    }

    private func recordJSON(fileID: String, tier: String = "auto", status: String = "executed") -> String {
        """
        {
          "file_id": "\(fileID)", "source_id": "downloads", "original_name": "\(fileID).pdf",
          "original_path": "/Users/fixture/Downloads/\(fileID).pdf",
          "current_path": "/Users/fixture/Downloads/\(fileID).pdf",
          "extension": ".pdf", "mime_type": "application/pdf", "size_bytes": 1024,
          "created_at": "2026-07-27T10:00:00Z", "modified_at": "2026-07-27T10:00:00Z",
          "content_hash": "hash-\(fileID)", "discovered_at": "2026-07-27T10:00:00Z",
          "status": "\(status)", "category": "Invoice", "tier": "\(tier)"
        }
        """
    }

    private func logLine(batchID: String, fileID: String, action: String, timestamp: String, to: String? = nil) -> String {
        let toField = to.map { "\"\($0)\"" } ?? "null"
        return """
        {"batch_id": "\(batchID)", "file_id": "\(fileID)", "action": "\(action)", "from": "/Users/fixture/Downloads/\(fileID).pdf", "to": \(toField), "timestamp": "\(timestamp)", "approved_by": "auto", "details": {}}
        """
    }

    // MARK: - Real read-through, fresh every call

    func test_refreshNow_populatesProjectionFromRealRead() async throws {
        let records = "[\(recordJSON(fileID: "1"))]"
        let entries = [logLine(batchID: "batch-1", fileID: "1", action: "move_rename", timestamp: "2026-08-01T10:00:00Z", to: "/dest/Finance/1.pdf")]
        let root = try makeProject(recordsJSON: records, actionLogLines: entries)
        defer { try? FileManager.default.removeItem(at: root) }

        let viewModel = HistoryViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.projection?.batches.map(\.batchID), ["batch-1"])
    }

    func test_refreshNow_calledTwiceAfterExternalChange_reflectsTheChange() async throws {
        // "History must always re-read fresh — never cache a stale list"
        // (WP-GUI-09 Technical Notes) — simulated here by mutating the
        // action log directly between two `refreshNow()` calls, standing
        // in for a change made via direct CLI use.
        let records = "[\(recordJSON(fileID: "1")), \(recordJSON(fileID: "2"))]"
        let root = try makeProject(
            recordsJSON: records,
            actionLogLines: [logLine(batchID: "batch-1", fileID: "1", action: "move_rename", timestamp: "2026-08-01T10:00:00Z", to: "/dest/Finance/1.pdf")]
        )
        defer { try? FileManager.default.removeItem(at: root) }

        let viewModel = HistoryViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()
        XCTAssertEqual(viewModel.projection?.batches.count, 1)

        let secondLine = logLine(batchID: "batch-2", fileID: "2", action: "move_rename", timestamp: "2026-08-01T11:00:00Z", to: "/dest/Images/2.pdf")
        let logURL = root.appendingPathComponent("Runtime/Logs/action_log.jsonl")
        let existing = try String(contentsOf: logURL, encoding: .utf8)
        try (existing + secondLine + "\n").write(to: logURL, atomically: true, encoding: .utf8)

        await viewModel.refreshNow()
        XCTAssertEqual(viewModel.projection?.batches.count, 2)
    }

    // MARK: - Failure path (reuses the existing IncompatibleEngineProject fixture, read-only)

    func test_refreshNow_incompatibleEngineVersion_setsErrorPresentation() async throws {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: fixturesRoot.appendingPathComponent("IncompatibleEngineProject"),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = HistoryViewModel(bridge: bridge)

        await viewModel.refreshNow()

        XCTAssertNil(viewModel.projection)
        XCTAssertEqual(viewModel.errorPresentation?.heading, "Update needed")
    }

    // MARK: - Large synthetic history: grouping/summarizing performance

    /// WP-GUI-09's own Risk: "progressive loading for a long history is
    /// the main technical risk at scale." `ActionLogReader`/
    /// `MetadataStoreReader` have no pagination API to read incrementally
    /// from, so the read is necessarily a single full read regardless —
    /// this measures whether the one remaining variable this package
    /// controls, `HistoryProjection.compute()`'s own grouping/summarizing
    /// pass, is fast enough that no custom chunked-computation logic is
    /// actually needed, rather than assuming either way.
    func test_compute_largeSyntheticHistory_groupsAndSummarizesQuickly() {
        var entries: [ActionLogEntry] = []
        var records: [FileRecordSnapshot] = []
        let batchCount = 300
        let filesPerBatch = 3

        for batchIndex in 0..<batchCount {
            let batchID = "batch-\(batchIndex)"
            let timestamp = String(format: "2026-01-01T%02d:%02d:00Z", batchIndex / 60 % 24, batchIndex % 60)
            for fileIndex in 0..<filesPerBatch {
                let fileID = "\(batchID)-file-\(fileIndex)"
                entries.append(
                    ActionLogEntry(
                        batchID: batchID, fileID: fileID, action: "move_rename",
                        from: "/Users/fixture/Downloads/\(fileID).pdf",
                        to: "/dest/Finance/\(fileID).pdf",
                        timestamp: timestamp, approvedBy: "auto", details: nil
                    )
                )
                records.append(
                    FileRecordSnapshot(
                        fileID: fileID, sourceID: "downloads", originalName: "\(fileID).pdf",
                        originalPath: "/Users/fixture/Downloads/\(fileID).pdf",
                        currentPath: "/dest/Finance/\(fileID).pdf",
                        fileExtension: ".pdf", mimeType: "application/pdf", sizeBytes: 1024,
                        createdAt: timestamp, modifiedAt: timestamp, contentHash: "hash-\(fileID)",
                        discoveredAt: timestamp, status: "executed", tier: .auto
                    )
                )
            }
        }

        let start = Date()
        let projection = HistoryProjection.compute(actionLogEntries: entries, records: records)
        let elapsed = Date().timeIntervalSince(start)

        XCTAssertEqual(projection.batches.count, batchCount)
        // A generous ceiling, not a tight benchmark — this is a
        // measure-first sanity check (per this work package's own plan:
        // "only invest in true chunked/incremental computation if this
        // measurement shows a real problem"), not a performance contract.
        XCTAssertLessThan(elapsed, 2.0, "HistoryProjection.compute() took \(elapsed)s for \(batchCount) batches — investigate before relying on plain List virtualization alone.")
    }

    // MARK: - Cross-entry-point consistency: History's `.batchID` path vs. Execute's `.last` path

    /// WP-GUI-09's own Test Plan: "a side-by-side test confirming both
    /// Undo entry points produce identical results for the same batch."
    /// Reuses WP-GUI-08's checked-in `UndoingEngineProject` fixture
    /// read-only, via two separate isolated copies (one per entry point) —
    /// never modifying the fixture itself.
    func test_undoViaExplicitBatchID_and_undoViaLast_produceIdenticalResults_forSameBatch() async throws {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        let source = fixturesRoot.appendingPathComponent("UndoingEngineProject")

        func makeIsolatedBridge() throws -> EngineBridge {
            let tempRoot = makeTempDirectory()
            try FileManager.default.copyItem(at: source, to: tempRoot)
            addTeardownBlock { try? FileManager.default.removeItem(at: tempRoot) }
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o644],
                ofItemAtPath: tempRoot.appendingPathComponent("Database/Metadata/metadata_store.json").path
            )
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o644],
                ofItemAtPath: tempRoot.appendingPathComponent("Runtime/Logs/action_log.jsonl").path
            )
            return EngineBridge(configuration: .init(
                projectRootURL: tempRoot,
                minimumSupportedEngineVersion: minimumSupportedVersion,
                maximumSupportedEngineVersion: maximumSupportedVersion,
                guiLogDirectoryURL: makeTempDirectory()
            ))
        }

        // The fixture's own seeded batch — "fixture-batch-1" — is both the
        // most recent batch in the log (`--last` resolves to it) and the
        // batch History's row for it would pass explicitly as `.batchID`.
        let confirmedRows = [
            ExecuteResultProjection.FiledRow(fileID: "filed-1", originalName: "2026-07-19_acme.pdf", destinationFolder: "Finance"),
            ExecuteResultProjection.FiledRow(fileID: "filed-2", originalName: "IMG_4821.jpg", destinationFolder: "Images"),
            ExecuteResultProjection.FiledRow(fileID: "restore-conflict", originalName: "locked_file.pdf", destinationFolder: "Documents"),
        ]

        let lastViewModel = UndoViewModel(bridge: try makeIsolatedBridge(), confirmedRows: confirmedRows, target: .last)
        await lastViewModel.confirmAndUndo()

        let batchIDViewModel = UndoViewModel(bridge: try makeIsolatedBridge(), confirmedRows: confirmedRows, target: .batchID("fixture-batch-1"))
        await batchIDViewModel.confirmAndUndo()

        guard case .result(let lastResult) = lastViewModel.phase, case .result(let batchIDResult) = batchIDViewModel.phase else {
            return XCTFail("expected .result from both entry points, got \(lastViewModel.phase) and \(batchIDViewModel.phase)")
        }

        XCTAssertEqual(lastResult, batchIDResult)
    }
}
