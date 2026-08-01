import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `ExecuteViewModel` against a real `EngineBridge`
/// and a real `python3 -m src.cli execute -y` subprocess
/// (`Fixtures/ExecutingEngineProject`) — proving the actual end-to-end
/// wiring this work package depends on: a real fresh-read-before-commit
/// cycle, a real non-interactive `execute` invocation under the existing
/// mutation guard, and a result derived exclusively from a real,
/// post-invocation action-log re-read (including real per-file isolation
/// against a genuinely locked/unmoved fixture file) — rather than only the
/// pure-model simulation `ExecuteResultProjectionTests` already covers.
@MainActor
final class ExecuteViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("ExecuteViewModelTests-\(UUID().uuidString)")
    }

    /// Copies the checked-in fixture to an isolated temp directory rather
    /// than reading/writing it in place — `execute` genuinely mutates this
    /// fixture's metadata store and appends to its action log, so reusing
    /// the checked-in copy directly would leave it contaminated with one
    /// test's own output for every subsequent test, exactly the class of
    /// test-isolation defect already found and fixed for Module 07 and
    /// guarded against identically in `ScanViewModelTests`.
    private func makeIsolatedBridge(project: String) throws -> EngineBridge {
        let root = try fixtureURL(project)
        let tempRoot = makeTempDirectory()
        try FileManager.default.copyItem(at: root, to: tempRoot)
        addTeardownBlock { try? FileManager.default.removeItem(at: tempRoot) }
        // `copyItem` preserves the source's permission bits, and the
        // test-resource-bundle copy `Bundle.module` resolves to is
        // non-writable — without this, the fixture's own `save_store()`/
        // `append_action_log()` (plain `open(path, "w"/"a")` calls) fail on
        // their first write, exactly the same defect already documented and
        // guarded against in `ScanViewModelTests`.
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o644],
            ofItemAtPath: tempRoot.appendingPathComponent("Database/Metadata/metadata_store.json").path
        )
        return EngineBridge(configuration: .init(
            projectRootURL: tempRoot,
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
    }

    // MARK: - loadConfirmation(): correct batch, correct exclusions

    func test_loadConfirmation_includesOnlyAutoTierNotYetExecutedRecords() async throws {
        let bridge = try makeIsolatedBridge(project: "ExecutingEngineProject")
        let viewModel = ExecuteViewModel(bridge: bridge)

        await viewModel.loadConfirmation()

        guard case .confirming(let projection) = viewModel.phase else {
            return XCTFail("expected .confirming, got \(viewModel.phase)")
        }
        // auto-1, auto-2, auto-locked — never already-executed (wrong
        // status) or needs-approval (wrong tier).
        XCTAssertEqual(Set(projection.fileRows.map(\.fileID)), ["auto-1", "auto-2", "auto-locked"])
        XCTAssertEqual(projection.totalCount, 3)
    }

    // MARK: - confirmAndExecute(): real invocation, real per-file isolation

    func test_confirmAndExecute_realInvocation_filesEligibleRecords_isolatesLockedFile() async throws {
        let bridge = try makeIsolatedBridge(project: "ExecutingEngineProject")
        let viewModel = ExecuteViewModel(bridge: bridge)

        await viewModel.loadConfirmation()
        await viewModel.confirmAndExecute()

        guard case .result(let result) = viewModel.phase else {
            return XCTFail("expected .result, got \(viewModel.phase)")
        }
        XCTAssertEqual(result.totalAttempted, 3)
        XCTAssertEqual(result.filedCount, 2)
        XCTAssertFalse(result.isFullSuccess)
        XCTAssertEqual(Set(result.filedRows.map(\.fileID)), ["auto-1", "auto-2"])
        XCTAssertEqual(result.problemRows.map(\.fileID), ["auto-locked"])
        XCTAssertEqual(result.problemRows.first?.reason, "Permission denied")
    }

    func test_confirmAndExecute_destinationBreakdown_reflectsRealWrittenPaths() async throws {
        let bridge = try makeIsolatedBridge(project: "ExecutingEngineProject")
        let viewModel = ExecuteViewModel(bridge: bridge)

        await viewModel.loadConfirmation()
        await viewModel.confirmAndExecute()

        guard case .result(let result) = viewModel.phase else {
            return XCTFail("expected .result, got \(viewModel.phase)")
        }
        XCTAssertEqual(Set(result.destinationBreakdown.map(\.destinationFolder)), ["Finance", "Images"])
        XCTAssertEqual(result.destinationBreakdown.map(\.count).reduce(0, +), 2)
    }

    func test_confirmAndExecute_alreadyExecutedAndApprovalRequiredRecords_neverAppearInResult() async throws {
        let bridge = try makeIsolatedBridge(project: "ExecutingEngineProject")
        let viewModel = ExecuteViewModel(bridge: bridge)

        await viewModel.loadConfirmation()
        await viewModel.confirmAndExecute()

        guard case .result(let result) = viewModel.phase else {
            return XCTFail("expected .result, got \(viewModel.phase)")
        }
        let allFileIDs = Set(result.filedRows.map(\.fileID) + result.problemRows.map(\.fileID))
        XCTAssertFalse(allFileIDs.contains("already-executed"))
        XCTAssertFalse(allFileIDs.contains("needs-approval"))
    }

    // MARK: - Real second fresh read before commit: a batch that empties out between load and confirm is caught

    func test_confirmAndExecute_batchBecomesEmptyBeforeCommit_reportsNothingToFile() async throws {
        let bridge = try makeIsolatedBridge(project: "ExecutingEngineProject")
        let viewModel = ExecuteViewModel(bridge: bridge)

        await viewModel.loadConfirmation()
        guard case .confirming = viewModel.phase else {
            return XCTFail("expected .confirming before simulating an out-of-band change")
        }

        // Simulate the batch becoming empty between load and commit (e.g.
        // another process already executed everything) by invoking execute
        // twice in a row — the second invocation's own fresh pre-commit
        // read must see nothing left to file.
        await viewModel.confirmAndExecute()
        await viewModel.confirmAndExecute()

        XCTAssertEqual(viewModel.phase, .nothingToFile)
    }

    // MARK: - Failure path (reuses the existing IncompatibleEngineProject fixture)

    func test_loadConfirmation_incompatibleEngineVersion_failsWithoutEverInvokingExecute() async throws {
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: try fixtureURL("IncompatibleEngineProject"),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = ExecuteViewModel(bridge: bridge)

        await viewModel.loadConfirmation()

        guard case .failed(let presentation) = viewModel.phase else {
            return XCTFail("expected .failed, got \(viewModel.phase)")
        }
        XCTAssertEqual(presentation.heading, "Update needed")
    }
}
