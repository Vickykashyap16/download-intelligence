import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `HomeViewModel` against a real `EngineBridge` —
/// the tests behind WP-GUI-03's own Test Plan: "three fixture datasets,
/// one per Home state, each loaded independently and verified; a timed
/// test confirming the periodic refresh interval fires and updates
/// displayed data when the underlying fixture is changed mid-session."
///
/// The three-fixture-dataset requirement for the *state selection logic
/// itself* is already covered exhaustively, and independent of any
/// `EngineBridge`, by `HomeProjectionTests`. What's specific to this file
/// is proving the real read-from-disk-through-EngineBridge-into-
/// HomeViewModel path actually works, and that periodic refresh really
/// re-polls rather than rendering once at load — hence the one
/// on-disk-mutating fixture built directly in this file (a self-contained
/// temp project root, not `Fixtures/`, since periodic-refresh proof
/// requires writing to the metadata store file *during* the test).
@MainActor
final class HomeViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("HomeViewModelTests-\(UUID().uuidString)")
    }

    /// Builds a minimal, real, mutable engine project on disk: a
    /// compatible `Release/VERSIONS.md`, a valid `src/config/sources.yaml`,
    /// and a `Database/Metadata/metadata_store.json` seeded with
    /// `initialRecordsJSON`. Returns the project root, for use both as
    /// `EngineBridge.Configuration.projectRootURL` and as the base for
    /// later overwriting the metadata store file mid-test.
    private func makeMutableProject(initialRecordsJSON: String) throws -> URL {
        let root = makeTempDirectory()
        let fm = FileManager.default
        try fm.createDirectory(at: root.appendingPathComponent("Release"), withIntermediateDirectories: true)
        try fm.createDirectory(at: root.appendingPathComponent("src/config"), withIntermediateDirectories: true)
        try fm.createDirectory(at: root.appendingPathComponent("Database/Metadata"), withIntermediateDirectories: true)

        try "**Pipeline Version: 0.8.0**\n".write(
            to: root.appendingPathComponent("Release/VERSIONS.md"), atomically: true, encoding: .utf8
        )
        try """
        sources:
          - source_id: downloads
            path: /Users/fixture/Downloads
            type: local_folder
            enabled: true
            recursive: false
        execution_mode: manual
        destination_root: /Users/fixture/Organized Downloads
        classification_provider: null
        extraction_provider: null
        ai_provider_consent: false
        """.write(to: root.appendingPathComponent("src/config/sources.yaml"), atomically: true, encoding: .utf8)

        try writeMetadataStore(initialRecordsJSON, to: root)
        return root
    }

    private func writeMetadataStore(_ json: String, to root: URL) throws {
        try json.write(
            to: root.appendingPathComponent("Database/Metadata/metadata_store.json"),
            atomically: true,
            encoding: .utf8
        )
    }

    private func makeBridge(projectRoot: URL) -> EngineBridge {
        EngineBridge(configuration: .init(
            projectRootURL: projectRoot,
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
    }

    private func recordJSON(fileID: String, tier: String, status: String, discoveredAt: String) -> String {
        """
        {
          "file_id": "\(fileID)", "source_id": "downloads", "original_name": "\(fileID).pdf",
          "original_path": "/Users/fixture/Downloads/\(fileID).pdf",
          "current_path": "/Users/fixture/Downloads/\(fileID).pdf",
          "extension": ".pdf", "mime_type": "application/pdf", "size_bytes": 1024,
          "created_at": "\(discoveredAt)", "modified_at": "\(discoveredAt)",
          "content_hash": "hash-\(fileID)", "discovered_at": "\(discoveredAt)",
          "status": "\(status)", "tier": "\(tier)"
        }
        """
    }

    // MARK: - Real read-through: three states, using the app's own
    // Fixtures/CompatibleEngineProject and two ad hoc mutable projects.

    func test_refreshNow_emptyMetadataStore_yieldsFirstRun() async throws {
        let root = try makeMutableProject(initialRecordsJSON: "[]")
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = HomeViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.projection?.kind, .firstRun)
        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertFalse(viewModel.isLoading)
    }

    func test_refreshNow_pendingReviewRecord_yieldsNeedsReview() async throws {
        let json = "[\(recordJSON(fileID: "1", tier: "review_required", status: "scored", discoveredAt: "2026-07-26T10:00:00Z"))]"
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = HomeViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.projection?.kind, .needsReview(count: 1))
    }

    func test_refreshNow_allExecutedRecords_yieldsCaughtUp() async throws {
        let json = """
        [{
          "file_id": "1", "source_id": "downloads", "original_name": "1.pdf",
          "original_path": "/Users/fixture/Downloads/1.pdf",
          "current_path": "/Users/fixture/Organized Downloads/1.pdf",
          "extension": ".pdf", "mime_type": "application/pdf", "size_bytes": 1024,
          "created_at": "2026-07-25T10:00:00Z", "modified_at": "2026-07-25T10:00:00Z",
          "content_hash": "hash-1", "discovered_at": "2026-07-25T10:00:00Z",
          "status": "executed", "tier": "auto", "batch_id": "batch-1",
          "processed_at": "2026-07-25T10:05:00Z"
        }]
        """
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = HomeViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.projection?.kind, .caughtUp)
    }

    // MARK: - Error routing on initial load

    func test_refreshNow_incompatibleEngine_surfacesErrorState_withNoProjectionYet() async throws {
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: try fixtureURL("IncompatibleEngineProject"),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = HomeViewModel(bridge: bridge)

        await viewModel.refreshNow()

        XCTAssertNil(viewModel.projection)
        XCTAssertNotNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.errorPresentation?.heading, "Update needed")
    }

    // MARK: - Periodic refresh actually re-polls

    func test_periodicRefresh_reReadsOnInterval_andReflectsAChangedFixture() async throws {
        let root = try makeMutableProject(initialRecordsJSON: "[]")
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = HomeViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()
        XCTAssertEqual(viewModel.projection?.kind, .firstRun, "sanity check on the pre-mutation state")

        // Mutate the underlying fixture mid-session, exactly as WP-GUI-03's
        // Test Plan requires, then start a fast periodic refresh loop and
        // confirm it picks the change up on its own — never a second
        // manual `refreshNow()` call standing in for the loop itself.
        let updatedJSON = "[\(recordJSON(fileID: "1", tier: "review_required", status: "scored", discoveredAt: "2026-07-26T10:00:00Z"))]"
        try writeMetadataStore(updatedJSON, to: root)

        viewModel.startPeriodicRefresh(interval: 0.05)
        defer { viewModel.stopPeriodicRefresh() }

        let deadline = Date().addingTimeInterval(2)
        while viewModel.projection?.kind == .firstRun, Date() < deadline {
            try await Task.sleep(nanoseconds: 20_000_000)
        }

        XCTAssertEqual(viewModel.projection?.kind, .needsReview(count: 1), "the periodic loop must have re-read the mutated file on its own")
    }

    func test_stopPeriodicRefresh_haltsFurtherPolling() async throws {
        let root = try makeMutableProject(initialRecordsJSON: "[]")
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = HomeViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()
        viewModel.startPeriodicRefresh(interval: 0.05)
        viewModel.stopPeriodicRefresh()

        // Mutate after stopping — if the loop were still running, this
        // would eventually be picked up; asserting it is *not* picked up
        // is what proves `stopPeriodicRefresh()` genuinely halts polling
        // rather than merely being a no-op.
        let updatedJSON = "[\(recordJSON(fileID: "1", tier: "review_required", status: "scored", discoveredAt: "2026-07-26T10:00:00Z"))]"
        try writeMetadataStore(updatedJSON, to: root)

        try await Task.sleep(nanoseconds: 300_000_000)

        XCTAssertEqual(viewModel.projection?.kind, .firstRun, "polling should have stopped, so the mutation must not have been observed")
    }
}
