import XCTest
@testable import EngineBridge

final class EngineVersionReaderTests: XCTestCase {

    private func fixtureLocations(project: String) throws -> EngineArtifactLocations {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return EngineArtifactLocations(projectRootURL: fixturesRoot.appendingPathComponent(project))
    }

    // MARK: - Happy path, against the real VERSIONS.md shape

    func test_readsRealShapedVersionLineCorrectly() throws {
        let reader = EngineVersionReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let version = try reader.read()

        XCTAssertEqual(version, SemanticVersion(major: 0, minor: 8, patch: 0))
    }

    // MARK: - Missing version information

    func test_missingVersionsFile_throwsArtifactNotFound() throws {
        let reader = EngineVersionReader(locations: try fixtureLocations(project: "EmptyEngineProject"))

        do {
            _ = try reader.read()
            XCTFail("expected artifactNotFound to be thrown")
        } catch EngineBridgeError.artifactNotFound(let path) {
            XCTAssertTrue(path.hasSuffix("VERSIONS.md"))
        }
    }

    // MARK: - Malformed version information

    func test_fileWithNoVersionLine_throwsArtifactUnreadable() throws {
        let tempDirectory = try makeTempProject(versionsFileContent: "# Version History\n\nNothing useful here.\n")
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let reader = EngineVersionReader(locations: EngineArtifactLocations(projectRootURL: tempDirectory))

        do {
            _ = try reader.read()
            XCTFail("expected artifactUnreadable to be thrown")
        } catch EngineBridgeError.artifactUnreadable(let path, let reason) {
            XCTAssertTrue(path.hasSuffix("VERSIONS.md"))
            XCTAssertTrue(reason.contains("Pipeline Version"))
        }
    }

    func test_versionLineWithMalformedTriple_throwsArtifactUnreadable() throws {
        let tempDirectory = try makeTempProject(versionsFileContent: "**Pipeline Version: not-a-version**\n")
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let reader = EngineVersionReader(locations: EngineArtifactLocations(projectRootURL: tempDirectory))

        do {
            _ = try reader.read()
            XCTFail("expected artifactUnreadable to be thrown")
        } catch EngineBridgeError.artifactUnreadable(let path, let reason) {
            XCTAssertTrue(path.hasSuffix("VERSIONS.md"))
            XCTAssertTrue(reason.contains("not-a-version"))
        }
    }

    func test_versionLineWithTwoComponentsOnly_throwsArtifactUnreadable() throws {
        let tempDirectory = try makeTempProject(versionsFileContent: "**Pipeline Version: 0.8**\n")
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let reader = EngineVersionReader(locations: EngineArtifactLocations(projectRootURL: tempDirectory))

        XCTAssertThrowsError(try reader.read()) { error in
            guard case EngineBridgeError.artifactUnreadable = error else {
                return XCTFail("expected .artifactUnreadable, got \(error)")
            }
        }
    }

    // MARK: - Helpers

    private func makeTempProject(versionsFileContent: String) throws -> URL {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("EngineVersionReaderTests-\(UUID().uuidString)")
        let releaseDirectory = tempDirectory.appendingPathComponent("Release")
        try FileManager.default.createDirectory(at: releaseDirectory, withIntermediateDirectories: true)
        try versionsFileContent.write(
            to: releaseDirectory.appendingPathComponent("VERSIONS.md"),
            atomically: true,
            encoding: .utf8
        )
        return tempDirectory
    }
}
