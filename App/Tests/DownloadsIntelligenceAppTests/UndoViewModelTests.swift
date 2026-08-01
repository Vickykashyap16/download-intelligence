import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `UndoViewModel` against a real `EngineBridge` and
/// a real `python3 -m src.cli undo --last` subprocess
/// (`Fixtures/UndoingEngineProject`) — proving the actual end-to-end
/// wiring this work package depends on: a real non-interactive `undo
/// --last` invocation under the existing mutation guard, targeting only
/// the most recent batch, and a result derived exclusively from a real,
/// post-invocation action-log re-read (including real per-file isolation
/// against a genuine restoration conflict) — rather than only the
/// pure-model simulation `UndoResultProjectionTests` already covers.
@MainActor
final class UndoViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("UndoViewModelTests-\(UUID().uuidString)")
    }

    /// Copies the checked-in fixture to an isolated temp directory rather
    /// than reading/writing it in place — `undo` genuinely mutates this
    /// fixture's metadata store and appends to its action log, so reusing
    /// the checked-in copy directly would leave it contaminated with one
    /// test's own output for every subsequent test, the same test-isolation
    /// discipline `ExecuteViewModelTests.makeIsolatedBridge(project:)`
    /// already establishes.
    private func makeIsolatedBridge(project: String) throws -> EngineBridge {
        let root = try fixtureURL(project)
        let tempRoot = makeTempDirectory()
        try FileManager.default.copyItem(at: root, to: tempRoot)
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

    private func makeConfirmedRow(fileID: String) -> ExecuteResultProjection.FiledRow {
        ExecuteResultProjection.FiledRow(fileID: fileID, originalName: "\(fileID).pdf", destinationFolder: "Finance")
    }

    // MARK: - confirmAndUndo(): real invocation, real per-file isolation

    func test_confirmAndUndo_realInvocation_restoresEligibleRecords_isolatesConflictFile() async throws {
        let bridge = try makeIsolatedBridge(project: "UndoingEngineProject")
        let confirmedRows = [makeConfirmedRow(fileID: "filed-1"), makeConfirmedRow(fileID: "filed-2"), makeConfirmedRow(fileID: "restore-conflict")]
        let viewModel = UndoViewModel(bridge: bridge, confirmedRows: confirmedRows)

        XCTAssertEqual(viewModel.totalToUndo, 3)
        await viewModel.confirmAndUndo()

        guard case .result(let result) = viewModel.phase else {
            return XCTFail("expected .result, got \(viewModel.phase)")
        }
        XCTAssertEqual(result.totalAttempted, 3)
        XCTAssertEqual(result.restoredCount, 2)
        XCTAssertFalse(result.isFullSuccess)
        XCTAssertEqual(Set(result.restoredRows.map(\.fileID)), ["filed-1", "filed-2"])
        XCTAssertEqual(result.problemRows.map(\.fileID), ["restore-conflict"])
        XCTAssertEqual(result.problemRows.first?.reason, "Something already exists at the original location")
    }

    // MARK: - "--last" targets only the most recent batch — an older batch's record is left untouched

    func test_confirmAndUndo_targetsOnlyMostRecentBatch_olderBatchRecordUntouched() async throws {
        let bridge = try makeIsolatedBridge(project: "UndoingEngineProject")
        let confirmedRows = [makeConfirmedRow(fileID: "filed-1"), makeConfirmedRow(fileID: "filed-2"), makeConfirmedRow(fileID: "restore-conflict")]
        let viewModel = UndoViewModel(bridge: bridge, confirmedRows: confirmedRows)

        await viewModel.confirmAndUndo()

        guard case .result = viewModel.phase else {
            return XCTFail("expected .result, got \(viewModel.phase)")
        }
        // "old-file" belongs to an earlier batch ("fixture-batch-0") and was
        // never part of the confirmed batch passed to this view model —
        // `undo --last` must never touch it.
        let records = try await bridge.readMetadataStore().records
        let oldFile = records.first { $0.fileID == "old-file" }
        XCTAssertEqual(oldFile?.status, "executed")
    }

    // MARK: - Empty confirmed batch: reports nothing to undo without invoking the engine

    func test_confirmAndUndo_emptyConfirmedRows_reportsNothingToUndo() async throws {
        let bridge = try makeIsolatedBridge(project: "UndoingEngineProject")
        let viewModel = UndoViewModel(bridge: bridge, confirmedRows: [])

        XCTAssertEqual(viewModel.totalToUndo, 0)
        await viewModel.confirmAndUndo()

        guard case .result(let result) = viewModel.phase else {
            return XCTFail("expected .result, got \(viewModel.phase)")
        }
        XCTAssertEqual(result.totalAttempted, 0)
        XCTAssertTrue(result.isFullSuccess)

        // The engine was never invoked — the action log is untouched beyond
        // its four seeded entries.
        let entries = try await bridge.readActionLog().entries
        XCTAssertEqual(entries.count, 4)
    }

    // MARK: - Failure path (reuses the existing IncompatibleEngineProject fixture)

    func test_confirmAndUndo_incompatibleEngineVersion_reportsFailed() async throws {
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: try fixtureURL("IncompatibleEngineProject"),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = UndoViewModel(bridge: bridge, confirmedRows: [makeConfirmedRow(fileID: "filed-1")])

        await viewModel.confirmAndUndo()

        guard case .failed(let presentation) = viewModel.phase else {
            return XCTFail("expected .failed, got \(viewModel.phase)")
        }
        XCTAssertEqual(presentation.heading, "Update needed")
    }
}
