import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `ReviewQueueViewModel` against a real
/// `EngineBridge` — proving the real read-from-disk-through-EngineBridge
/// path works, and — the type's own central architectural guarantee — that
/// Approve/Reject decisions are purely session-local state that never
/// triggers a second engine invocation. `ReviewQueueProjectionTests`
/// already covers the state-selection/grouping logic itself, independent
/// of any `EngineBridge`, mirroring the established
/// `*ProjectionTests`/`*ViewModelTests` split.
@MainActor
final class ReviewQueueViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("ReviewQueueViewModelTests-\(UUID().uuidString)")
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

    // MARK: - Real read-through

    func test_refreshNow_populatesProjectionFromRealRead() async throws {
        let json = "[\(recordJSON(fileID: "1", tier: "approval_required"))]"
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewQueueViewModel(bridge: makeBridge(projectRoot: root))

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.projection?.needsInputItems.map(\.fileID), ["1"])
        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertFalse(viewModel.isLoading)
    }

    func test_refreshNow_incompatibleEngine_surfacesErrorState() async throws {
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: try fixtureURL("IncompatibleEngineProject"),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = ReviewQueueViewModel(bridge: bridge)

        await viewModel.refreshNow()

        XCTAssertNil(viewModel.projection)
        XCTAssertNotNil(viewModel.errorPresentation)
    }

    // MARK: - Decisions are session-local: visible lists update, underlying projection does not

    func test_decide_approve_removesItemFromVisibleList_butNotFromProjection() async throws {
        let json = "[\(recordJSON(fileID: "1", tier: "approval_required"))]"
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewQueueViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        viewModel.decide(.approved, for: "1")

        XCTAssertTrue(viewModel.visibleNeedsInputItems.isEmpty)
        XCTAssertEqual(viewModel.projection?.needsInputItems.map(\.fileID), ["1"], "the fresh-read snapshot itself must never be mutated in place")
        XCTAssertEqual(viewModel.decisions["1"], .approved)
    }

    func test_decide_reject_alsoRemovesItemFromVisibleList() async throws {
        let json = "[\(recordJSON(fileID: "1", tier: "approval_required"))]"
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewQueueViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        viewModel.decide(.rejected, for: "1")

        XCTAssertTrue(viewModel.visibleNeedsInputItems.isEmpty)
        XCTAssertEqual(viewModel.decisions["1"], .rejected)
    }

    // MARK: - Focus management: next remaining card in the same group

    func test_decide_middleItem_focusMovesToNextRemainingItem() async throws {
        let json = """
        [\(recordJSON(fileID: "a", tier: "approval_required")),
         \(recordJSON(fileID: "b", tier: "approval_required")),
         \(recordJSON(fileID: "c", tier: "approval_required"))]
        """
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewQueueViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()
        // Sanity: fixed discoveredAt/fileID ordering yields a, b, c.
        XCTAssertEqual(viewModel.visibleNeedsInputItems.map(\.fileID), ["a", "b", "c"])

        let nextFocus = viewModel.decide(.approved, for: "b")

        XCTAssertEqual(nextFocus, "c", "focus should move to the next remaining card, not the first or a lost focus")
        XCTAssertEqual(viewModel.visibleNeedsInputItems.map(\.fileID), ["a", "c"])
    }

    func test_decide_lastItem_focusMovesToNewLastItem() async throws {
        let json = """
        [\(recordJSON(fileID: "a", tier: "approval_required")),
         \(recordJSON(fileID: "b", tier: "approval_required"))]
        """
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewQueueViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        let nextFocus = viewModel.decide(.approved, for: "b")

        XCTAssertEqual(nextFocus, "a")
    }

    func test_decide_onlyRemainingItem_returnsNilFocus() async throws {
        let json = "[\(recordJSON(fileID: "a", tier: "approval_required"))]"
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewQueueViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        let nextFocus = viewModel.decide(.approved, for: "a")

        XCTAssertNil(nextFocus, "no remaining card exists to move focus to")
    }

    func test_decide_alreadyDecidedFileID_isNoOp() async throws {
        let json = "[\(recordJSON(fileID: "a", tier: "approval_required"))]"
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewQueueViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        viewModel.decide(.approved, for: "a")
        let secondCallResult = viewModel.decide(.rejected, for: "a")

        XCTAssertNil(secondCallResult)
        XCTAssertEqual(viewModel.decisions["a"], .approved, "the first decision must not be overwritten by a stale second call")
    }

    // MARK: - Needs-input and Flagged groups are decided independently

    func test_decide_needsInputItem_doesNotAffectFlaggedGroup() async throws {
        let json = """
        [\(recordJSON(fileID: "approval-item", tier: "approval_required")),
         \(recordJSON(fileID: "flagged-item", tier: "review_required"))]
        """
        let root = try makeMutableProject(initialRecordsJSON: json)
        defer { try? FileManager.default.removeItem(at: root) }
        let viewModel = ReviewQueueViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        viewModel.decide(.approved, for: "approval-item")

        XCTAssertEqual(viewModel.visibleFlaggedItems.map(\.fileID), ["flagged-item"])
    }
}
