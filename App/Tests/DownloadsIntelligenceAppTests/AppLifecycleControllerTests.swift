import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `AppLifecycleController` — the one part of
/// WP-GUI-01 that actually drives a real `EngineBridge` through `Desktop
/// Implementation Blueprint.md` §2's lifecycle phases. These are the tests
/// behind WP-GUI-01's own Acceptance Criteria: "the application launches...
/// and navigates between placeholder sections" (exercised by reaching
/// `.displayingHome`) and "the Error State correctly displays a real
/// failure surfaced by the Engine Bridge (e.g., a deliberately-
/// misconfigured test installation)" (exercised by the incompatible- and
/// corrupt-config fixtures below).
///
/// Every fixture here is self-contained under this test target's own
/// `Fixtures/` resource — none of WP-GUI-00's `EngineBridgeTests/Fixtures`
/// is read, reused, or modified, per the standing "never modify a frozen
/// module's own artifacts" constraint applied here to its test resources.
@MainActor
final class AppLifecycleControllerTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempLogDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("AppLifecycleControllerTests-\(UUID().uuidString)")
    }

    private func makeBridge(project: String) throws -> EngineBridge {
        EngineBridge(configuration: .init(
            projectRootURL: try fixtureURL(project),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempLogDirectory()
        ))
    }

    // MARK: - Success path

    func test_compatibleEngine_reachesDisplayingHome() async throws {
        let bridge = try makeBridge(project: "CompatibleEngineProject")
        let controller = AppLifecycleController(bridge: bridge)

        XCTAssertEqual(controller.phase, .launching)
        await controller.start()

        XCTAssertEqual(controller.phase, .displayingHome)
    }

    // MARK: - First-run routing

    func test_missingConfiguration_routesToFirstRunNeeded_notToAnErrorState() async throws {
        let bridge = try makeBridge(project: "MissingConfigEngineProject")
        let controller = AppLifecycleController(bridge: bridge)

        await controller.start()

        XCTAssertEqual(controller.phase, .firstRunNeeded)
    }

    // MARK: - Error State wiring (WP-GUI-01's Acceptance Criteria)

    func test_incompatibleEngineVersion_routesToErrorState_withPlainLanguageContent() async throws {
        let bridge = try makeBridge(project: "IncompatibleEngineProject")
        let controller = AppLifecycleController(bridge: bridge)

        await controller.start()

        guard case .error(let presentation) = controller.phase else {
            return XCTFail("expected .error, got \(controller.phase)")
        }
        XCTAssertEqual(presentation.heading, "Update needed")
        XCTAssertTrue(presentation.explanation.contains("9.9.9"), "should name the actual installed version")
        XCTAssertFalse(presentation.technicalDetail.isEmpty, "technical detail must still be available")
    }

    func test_corruptConfiguration_routesToErrorState_notToFirstRun() async throws {
        let bridge = try makeBridge(project: "CorruptConfigEngineProject")
        let controller = AppLifecycleController(bridge: bridge)

        await controller.start()

        guard case .error = controller.phase else {
            return XCTFail("a malformed (present-but-unreadable) configuration must route to the Error State, per Desktop Implementation Blueprint.md §2 — got \(controller.phase)")
        }
    }

    // MARK: - Phase ordering

    func test_loadConfigurationHappensBeforeEngineReadinessCheck() async throws {
        // A missing-config project has no Release/VERSIONS.md either — if
        // the readiness check ran first, this would fail with a version
        // error instead of routing to firstRunNeeded. Confirming
        // `.firstRunNeeded` (rather than `.error`) proves Load
        // Configuration is checked first, exactly as `Desktop
        // Implementation Blueprint.md` §2 orders these phases.
        let bridge = try makeBridge(project: "MissingConfigEngineProject")
        let controller = AppLifecycleController(bridge: bridge)

        await controller.start()

        XCTAssertEqual(controller.phase, .firstRunNeeded)
    }
}
