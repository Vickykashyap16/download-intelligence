import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `ScanViewModel` against a real `EngineBridge` and a
/// real `python3 -m src.cli run` subprocess (`Fixtures/ScanningEngineProject`)
/// — proving the actual end-to-end wiring this work package depends on:
/// live polling of `readMetadataStore()` while `run` is still in flight
/// (the actor-reentrancy fact Finding 4 relies on), the indeterminate→
/// determinate transition actually happening against a real subprocess
/// rather than only in `ScanProgressTests`' pure-model simulation, and the
/// final `ScanCompleteProjection` being computed correctly once `run`
/// genuinely exits.
///
/// Deliberately does not reuse `EngineBridgeTests`' `FakeEngineProject`
/// fixture, whose own `run` branch already has a different, frozen job
/// (`ProcessRunnerTests.test_run_exitCode3_isClassifiedAsAborted`) that
/// must not be disturbed.
@MainActor
final class ScanViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("ScanViewModelTests-\(UUID().uuidString)")
    }

    private func makeBridge(project: String) throws -> EngineBridge {
        EngineBridge(configuration: .init(
            projectRootURL: try fixtureURL(project),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
    }

    // MARK: - End-to-end: indeterminate → determinate → complete

    func test_start_observesIndeterminateThenDeterminate_thenCompletesWithCorrectProjection() async throws {
        // Copied to an isolated temp directory, not read/written in place —
        // `run` genuinely mutates this fixture's metadata store, so reusing
        // the checked-in copy directly would leave it contaminated with
        // this test's own output for every subsequent run (the same class
        // of test-isolation defect already found and fixed for Module 07).
        let root = try fixtureURL("ScanningEngineProject")
        let tempRoot = makeTempDirectory()
        try FileManager.default.copyItem(at: root, to: tempRoot)
        defer { try? FileManager.default.removeItem(at: tempRoot) }
        // `copyItem` preserves the source file's permission bits, and the
        // test-resource-bundle copy of this fixture that `Bundle.module`
        // resolves to is non-writable — so without this, the fixture's own
        // `save_store()` (a plain `open(path, "w")`) fails with a
        // permission error on its very first write, the subprocess exits
        // non-zero, and — since `ScanViewModel.start()` never inspects
        // `run`'s exit code — the metadata store silently stays empty for
        // the rest of this test.
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o644],
            ofItemAtPath: tempRoot.appendingPathComponent("Database/Metadata/metadata_store.json").path
        )
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: tempRoot,
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = ScanViewModel(bridge: bridge, pollInterval: 0.05)

        var observedIndeterminate = false
        var observedDeterminateProgress: [DeterminateProgress] = []

        let observer = Task { @MainActor in
            while true {
                switch viewModel.phase {
                case .running(.indeterminate):
                    observedIndeterminate = true
                case .running(.determinate(let progress)):
                    observedDeterminateProgress.append(progress)
                case .complete, .failed:
                    return
                }
                try? await Task.sleep(nanoseconds: 10_000_000)
            }
        }

        await viewModel.start()
        _ = await observer.value

        XCTAssertTrue(observedIndeterminate, "should have observed indeterminate before scan's append burst landed")
        XCTAssertFalse(observedDeterminateProgress.isEmpty, "should have observed at least one live determinate update")
        XCTAssertEqual(
            observedDeterminateProgress.last,
            DeterminateProgress(completed: 3, total: 3),
            "the last live update before completion should already reflect full completion"
        )

        guard case .complete(let projection) = viewModel.phase else {
            return XCTFail("expected .complete, got \(viewModel.phase)")
        }
        XCTAssertEqual(projection.totalFilesLookedAt, 3)
        XCTAssertEqual(
            projection.tierRows,
            [
                ScanCompleteProjection.TierRow(tier: .auto, count: 2),
                ScanCompleteProjection.TierRow(tier: .reviewRequired, count: 1),
            ]
        )
        XCTAssertEqual(projection.primaryActionAutoCount, 2)
    }

    // MARK: - A pre-existing, already-processed record is excluded from this scan's scope

    func test_start_scopeExcludesRecordsAlreadyPresentAndTieredBeforeThisScan() async throws {
        // Build a fresh copy of the fixture project (so mutating its
        // metadata store here never affects other tests) seeded with one
        // already-tiered record whose file_id the fixture's own `run`
        // never touches.
        let root = try fixtureURL("ScanningEngineProject")
        let tempRoot = makeTempDirectory()
        try FileManager.default.copyItem(at: root, to: tempRoot)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        let preExisting = """
        [{
          "file_id": "already-done", "source_id": "downloads", "original_name": "old.pdf",
          "original_path": "/Users/fixture/Downloads/old.pdf",
          "current_path": "/Users/fixture/Organized Downloads/old.pdf",
          "extension": ".pdf", "mime_type": "application/pdf", "size_bytes": 1024,
          "created_at": "2026-07-20T10:00:00Z", "modified_at": "2026-07-20T10:00:00Z",
          "content_hash": "hash-old", "discovered_at": "2026-07-20T10:00:00Z",
          "status": "executed", "category": "Invoice", "suggested_name": "old.pdf", "tier": "auto"
        }]
        """
        try preExisting.write(
            to: tempRoot.appendingPathComponent("Database/Metadata/metadata_store.json"),
            atomically: true,
            encoding: .utf8
        )

        let bridge = EngineBridge(configuration: .init(
            projectRootURL: tempRoot,
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = ScanViewModel(bridge: bridge, pollInterval: 0.05)

        await viewModel.start()

        guard case .complete(let projection) = viewModel.phase else {
            return XCTFail("expected .complete, got \(viewModel.phase)")
        }
        // 3 from the fixture's own run, not 4 — the pre-existing, already-
        // tiered record must not be recounted as part of this scan.
        XCTAssertEqual(projection.totalFilesLookedAt, 3)
        XCTAssertEqual(projection.primaryActionAutoCount, 2)
    }

    // MARK: - Idempotent start()

    func test_start_calledTwice_secondCallIsNoOp() async throws {
        // Isolated temp copy — see the identical note in
        // test_start_observesIndeterminateThenDeterminate_thenCompletesWithCorrectProjection.
        let root = try fixtureURL("ScanningEngineProject")
        let tempRoot = makeTempDirectory()
        try FileManager.default.copyItem(at: root, to: tempRoot)
        defer { try? FileManager.default.removeItem(at: tempRoot) }
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: tempRoot,
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = ScanViewModel(bridge: bridge, pollInterval: 0.05)

        await viewModel.start()
        guard case .complete(let firstProjection) = viewModel.phase else {
            return XCTFail("expected .complete after the first start()")
        }

        await viewModel.start()
        guard case .complete(let secondProjection) = viewModel.phase else {
            return XCTFail("expected .complete to remain unchanged after a second start() call")
        }
        XCTAssertEqual(firstProjection, secondProjection)
    }

    // MARK: - Failure path (reuses the existing IncompatibleEngineProject fixture)

    func test_start_incompatibleEngineVersion_failsWithoutEverInvokingRun() async throws {
        let bridge = try makeBridge(project: "IncompatibleEngineProject")
        let viewModel = ScanViewModel(bridge: bridge, pollInterval: 0.05)

        await viewModel.start()

        guard case .failed(let presentation) = viewModel.phase else {
            return XCTFail("expected .failed, got \(viewModel.phase)")
        }
        XCTAssertEqual(presentation.heading, "Update needed")
    }
}
