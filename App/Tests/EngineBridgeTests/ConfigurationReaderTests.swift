import XCTest
@testable import EngineBridge

final class ConfigurationReaderTests: XCTestCase {

    private func fixtureLocations(project: String) throws -> EngineArtifactLocations {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return EngineArtifactLocations(projectRootURL: fixturesRoot.appendingPathComponent(project))
    }

    // MARK: - Happy path, against the real, current sources.yaml shape

    func test_readsRealShapedConfigurationCorrectly() throws {
        let reader = ConfigurationReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let configuration = try reader.read()

        XCTAssertEqual(configuration.sources.count, 1)
        let source = try XCTUnwrap(configuration.sources.first)
        XCTAssertEqual(source.sourceID, "downloads")
        XCTAssertEqual(source.path, "/Users/fixture/Downloads")
        XCTAssertEqual(source.type, "local_folder")
        XCTAssertTrue(source.enabled)
        XCTAssertFalse(source.recursive)

        XCTAssertEqual(configuration.executionMode, "manual")
        XCTAssertEqual(configuration.destinationRoot, "/Users/fixture/Organized Downloads")
        XCTAssertNil(configuration.classificationProvider)
        XCTAssertNil(configuration.extractionProvider)
        XCTAssertFalse(configuration.aiProviderConsent)
    }

    // MARK: - Missing file: a distinct, meaningful "not configured yet" state

    func test_missingConfigurationFile_throwsArtifactNotFound() throws {
        let reader = ConfigurationReader(locations: try fixtureLocations(project: "EmptyEngineProject"))

        do {
            _ = try reader.read()
            XCTFail("expected artifactNotFound to be thrown")
        } catch EngineBridgeError.artifactNotFound(let path) {
            XCTAssertTrue(path.hasSuffix("sources.yaml"))
        }
    }

    // MARK: - Malformed file: the whole file is untrustworthy, not partially usable

    func test_malformedYAML_throwsArtifactUnreadable() throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("ConfigurationReaderTests-\(UUID().uuidString)")
        let configDirectory = tempDirectory.appendingPathComponent("src/config")
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let configURL = configDirectory.appendingPathComponent("sources.yaml")
        // Deliberately invalid YAML syntax (unterminated flow sequence).
        try "sources: [unterminated".write(to: configURL, atomically: true, encoding: .utf8)

        let reader = ConfigurationReader(locations: EngineArtifactLocations(projectRootURL: tempDirectory))

        do {
            _ = try reader.read()
            XCTFail("expected artifactUnreadable to be thrown")
        } catch EngineBridgeError.artifactUnreadable(let path, _) {
            XCTAssertTrue(path.hasSuffix("sources.yaml"))
        }
    }

    func test_wellFormedYAMLWithWrongShape_throwsArtifactUnreadable() throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("ConfigurationReaderTests-\(UUID().uuidString)")
        let configDirectory = tempDirectory.appendingPathComponent("src/config")
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let configURL = configDirectory.appendingPathComponent("sources.yaml")
        // Valid YAML, but "sources" is a string, not a list — a real shape
        // mismatch, not a syntax error.
        try "sources: \"not a list\"\n".write(to: configURL, atomically: true, encoding: .utf8)

        let reader = ConfigurationReader(locations: EngineArtifactLocations(projectRootURL: tempDirectory))

        do {
            _ = try reader.read()
            XCTFail("expected artifactUnreadable to be thrown")
        } catch EngineBridgeError.artifactUnreadable {
            // expected
        }
    }
}
