import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `PreviewViewModel` against a real `EngineBridge` —
/// proving the real read-from-disk-through-EngineBridge-into-
/// PreviewViewModel path works, and — the WP-GUI-05 Test Plan's own
/// requirement — that Preview never shows a stale result: a change made to
/// the underlying plan via direct engine-state manipulation (no scan, no
/// GUI action) must be reflected the next time `refreshNow()` runs.
///
/// The state-selection logic itself (`.nothingScannedYet` /
/// `.allFiled` / `.hasPlan`, tier/category arithmetic) is already covered
/// exhaustively, independent of any `EngineBridge`, by
/// `PreviewProjectionTests`. What's specific to this file is the real
/// engine-bridge round trip and the no-stale-cache guarantee, mirroring the
/// split `HomeProjectionTests`/`HomeViewModelTests` already establish.
@MainActor
final class PreviewViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("PreviewViewModelTests-\(UUID().uuidString)")
    }

    /// Builds a minimal, real, mutable engine project on disk — identical
    /// shape to `HomeViewModelTests`' own `makeMutableProject`, duplicated
    /// here rather than shared, matching this codebase's existing
    /// per-test-file helper convention (`ScanViewModelTests` and
    /// `HomeViewModelTests` each define their own copies rather than a
    /// shared test-utility type).
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

    private func recordJSON(fileID: String, tier: String, status: String, category: String = "Invoice") -> String {
        """
        {
          "file_id": "\(fileID)", "source_id": "downloads", "original_name": "\(fileID).pdf",
          "original_path": "/Users/fixture/Downloads/\(fileID).pdf",
          "current_path": "/Users/fixture/Downloads/\(fileID).pdf",
          "extension": ".pdf", "mime_type": "application/pdf", "size_bytes": 1024,
          "created_at": "2026-07-27T10:00:00Z", "modified_at": "2026-07-27T10:00:00Z",
          "content_hash": "hash-\(fileID)", "discovered_at": "2026-07-27T10:00:00Z",
          "status": "\(status)", "category": "\(category)", "tier": "\(tier)"
        }
        """
    }

    // MARK: - Real read-through: the three Preview states

    func test_refreshNow_emptyMetadataStore_yieldsNothingScannedYet() async throws {
        let root = try makeMutableProject(initialRecordsJSON: "[]")
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = PreviewViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.projection?.kind, .nothingScannedYet)
        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertFalse(viewModel.isLoading)
    }

    func test_refreshNow_allExecutedRecords_yieldsAllFiled() async throws {
        let json = "[\(recordJSON(fileID: "1", tier: "auto", status: "executed"))]"
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = PreviewViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.projection?.kind, .allFiled)
    }

    func test_refreshNow_pendingRecords_yieldsHasPlanWithCorrectTierRows() async throws {
        let json = """
        [\(recordJSON(fileID: "1", tier: "auto", status: "scored")),
         \(recordJSON(fileID: "2", tier: "review_required", status: "scored", category: "Resume"))]
        """
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = PreviewViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.projection?.kind, .hasPlan)
        XCTAssertEqual(viewModel.projection?.totalFilesPending, 2)
        XCTAssertEqual(viewModel.projection?.tierSections.map(\.tier), [.auto, .reviewRequired])
        XCTAssertEqual(viewModel.projection?.tierSections.map(\.count), [1, 1])
    }

    // MARK: - Error routing

    func test_refreshNow_incompatibleEngine_surfacesErrorState_withNoProjectionYet() async throws {
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: try fixtureURL("IncompatibleEngineProject"),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = PreviewViewModel(bridge: bridge)

        await viewModel.refreshNow()

        XCTAssertNil(viewModel.projection)
        XCTAssertNotNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.errorPresentation?.heading, "Update needed")
    }

    // MARK: - No-stale-cache: the WP-GUI-05 Test Plan's own core requirement

    /// Mutates the underlying plan via direct engine-state manipulation —
    /// exactly as if the engine itself had changed the store between two
    /// separate visits to Preview, with no scan and no GUI action involved
    /// — then confirms a second, independent `refreshNow()` call reflects
    /// the change. This is the direct proof that `GUI Architecture
    /// Specification.md` §7's "always re-read, never trust a cache across
    /// an engine-changing action" principle actually holds for Preview:
    /// there is no cached value anywhere in `PreviewViewModel` that could
    /// cause this second call to repeat the first call's answer.
    func test_refreshNow_calledAgainAfterDirectStoreMutation_reflectsChangeNotStaleValue() async throws {
        let initialJSON = "[\(recordJSON(fileID: "1", tier: "auto", status: "scored"))]"
        let root = try makeMutableProject(initialRecordsJSON: initialJSON)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = PreviewViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()
        XCTAssertEqual(viewModel.projection?.kind, .hasPlan, "sanity check on the pre-mutation state")
        XCTAssertEqual(viewModel.projection?.totalFilesPending, 1)

        // No scan, no execute — just the underlying file changing, as if
        // some other process (or a future Execute work package) had filed
        // this record and appended a new, unrelated pending one.
        let mutatedJSON = """
        [\(recordJSON(fileID: "1", tier: "auto", status: "executed")),
         \(recordJSON(fileID: "2", tier: "review_required", status: "scored", category: "Resume"))]
        """
        try writeMetadataStore(mutatedJSON, to: root)

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.projection?.kind, .hasPlan)
        XCTAssertEqual(viewModel.projection?.totalFilesPending, 1, "record 1 is now executed and must no longer count")
        XCTAssertEqual(viewModel.projection?.tierSections.map(\.tier), [.reviewRequired])
        XCTAssertEqual(viewModel.projection?.tierSections.first?.rows.map(\.fileID), ["2"])
    }
}
