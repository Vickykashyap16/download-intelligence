import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `ReviewDetailViewModel` against a real
/// `EngineBridge` — the real read-from-disk-through-EngineBridge path,
/// plus the "record not found" race this type must handle honestly.
/// `ReviewDetailProjectionTests` already covers the selection/kind logic
/// itself, independent of any `EngineBridge`.
@MainActor
final class ReviewDetailViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("ReviewDetailViewModelTests-\(UUID().uuidString)")
    }

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

    private func recordJSON(fileID: String, tier: String, status: String = "scored") -> String {
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

    func test_refreshNow_populatesProjectionFromRealRead() async throws {
        let json = "[\(recordJSON(fileID: "1", tier: "approval_required"))]"
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewDetailViewModel(bridge: makeBridge(projectRoot: root), fileID: "1")

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.projection?.fileID, "1")
        XCTAssertEqual(viewModel.projection?.kind, .needsInput)
        XCTAssertFalse(viewModel.recordNotFound)
        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertFalse(viewModel.isLoading)
    }

    func test_refreshNow_fileIDNotInStore_setsRecordNotFound() async throws {
        let json = "[\(recordJSON(fileID: "other", tier: "approval_required"))]"
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewDetailViewModel(bridge: makeBridge(projectRoot: root), fileID: "missing")

        await viewModel.refreshNow()

        XCTAssertNil(viewModel.projection)
        XCTAssertTrue(viewModel.recordNotFound)
        XCTAssertNil(viewModel.errorPresentation, "not-found is not a read error")
    }

    func test_refreshNow_incompatibleEngine_surfacesErrorState() async throws {
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: try fixtureURL("IncompatibleEngineProject"),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = ReviewDetailViewModel(bridge: bridge, fileID: "1")

        await viewModel.refreshNow()

        XCTAssertNil(viewModel.projection)
        XCTAssertNotNil(viewModel.errorPresentation)
        XCTAssertFalse(viewModel.recordNotFound, "an engine-level error is not the same as a not-found record")
    }
}
