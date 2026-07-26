import XCTest
@testable import EngineBridge

/// Verifies `EngineArtifactLocations` constructs exactly the real, expected
/// relative paths — the single source of truth every artifact reader's
/// tests implicitly rely on being correct.
final class EngineArtifactLocationsTests: XCTestCase {

    private let root = URL(fileURLWithPath: "/fixture/project/root")
    private var locations: EngineArtifactLocations { EngineArtifactLocations(projectRootURL: root) }

    func test_configurationFileURL() {
        XCTAssertEqual(locations.configurationFileURL.path, "/fixture/project/root/src/config/sources.yaml")
    }

    func test_actionLogURL() {
        XCTAssertEqual(locations.actionLogURL.path, "/fixture/project/root/Runtime/Logs/action_log.jsonl")
    }

    func test_metadataStoreURL() {
        XCTAssertEqual(locations.metadataStoreURL.path, "/fixture/project/root/Database/Metadata/metadata_store.json")
    }

    func test_dailySummaryDirectoryURL() {
        XCTAssertEqual(
            locations.dailySummaryDirectoryURL.path,
            "/fixture/project/root/Runtime/Reports/Daily Summary"
        )
    }

    func test_weeklySummaryDirectoryURL() {
        XCTAssertEqual(
            locations.weeklySummaryDirectoryURL.path,
            "/fixture/project/root/Runtime/Reports/Weekly Summary"
        )
    }

    func test_duplicateReportURL() {
        XCTAssertEqual(
            locations.duplicateReportURL.path,
            "/fixture/project/root/Runtime/Reports/Duplicate Report/duplicate_report.md"
        )
    }

    func test_storageReportURL() {
        XCTAssertEqual(
            locations.storageReportURL.path,
            "/fixture/project/root/Runtime/Reports/Storage Report/storage_report.md"
        )
    }

    func test_versionsFileURL() {
        XCTAssertEqual(locations.versionsFileURL.path, "/fixture/project/root/Release/VERSIONS.md")
    }
}
