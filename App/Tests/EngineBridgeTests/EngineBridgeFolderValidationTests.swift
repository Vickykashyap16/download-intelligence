import XCTest
@testable import EngineBridge

/// Integration tests proving `EngineBridge.validateFolder(at:requireWritable:)`
/// (WP-GUI-00A) is wired correctly through the public facade — a thin
/// delegation test, exactly matching how `EngineBridgeTests.swift` itself
/// proves the facade's other methods delegate correctly, kept in its own
/// file rather than added to that one so WP-GUI-00's existing, frozen test
/// file is never touched by this addition.
///
/// The one behavior specific to this method that no other `EngineBridge`
/// method exhibits — succeeding even when the engine itself is
/// incompatible — gets its own dedicated test below, since that's the
/// entire reason `validateFolder` was deliberately written to skip the
/// version-compatibility gate every other method runs first.
final class EngineBridgeFolderValidationTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempLogDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("EngineBridgeFolderValidationTests-\(UUID().uuidString)")
    }

    private func makeBridge(
        project: String,
        guiLogDirectory: URL,
        minimum: SemanticVersion? = nil,
        maximum: SemanticVersion? = nil
    ) throws -> EngineBridge {
        EngineBridge(configuration: .init(
            projectRootURL: try fixtureURL(project),
            minimumSupportedEngineVersion: minimum ?? minimumSupportedVersion,
            maximumSupportedEngineVersion: maximum ?? maximumSupportedVersion,
            guiLogDirectoryURL: guiLogDirectory
        ))
    }

    // MARK: - Facade delegation

    func test_validateFolder_realExistingDirectory_returnsValid() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        let candidateDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("EngineBridgeFolderValidationTests-dir-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: candidateDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: candidateDirectory) }

        let outcome = await bridge.validateFolder(at: candidateDirectory, requireWritable: true)

        XCTAssertEqual(outcome, .valid)
    }

    func test_validateFolder_missingPath_returnsDoesNotExist() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        let missingURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("EngineBridgeFolderValidationTests-missing-\(UUID().uuidString)")

        let outcome = await bridge.validateFolder(at: missingURL, requireWritable: false)

        XCTAssertEqual(outcome, .doesNotExist)
    }

    func test_validateFolder_regularFile_returnsNotADirectory() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        let fileURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("EngineBridgeFolderValidationTests-file-\(UUID().uuidString).txt")
        try "not a folder".write(to: fileURL, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: fileURL) }

        let outcome = await bridge.validateFolder(at: fileURL, requireWritable: false)

        XCTAssertEqual(outcome, .notADirectory)
    }

    // MARK: - Deliberately not gated behind engine-version compatibility

    /// `IncompatibleEngineProject`'s reported engine version falls outside
    /// this suite's configured supported range (see
    /// `EngineBridgeTests.swift`'s own use of the same fixture) — every
    /// other read/command method on `EngineBridge` refuses to proceed
    /// against it, throwing `.engineVersionTooOld`/`.engineVersionTooNew`.
    /// `validateFolder` must behave differently: it still succeeds,
    /// because it never touches the engine subprocess or its reported
    /// version at all.
    func test_validateFolder_succeedsEvenWhenEngineIsIncompatible() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "IncompatibleEngineProject", guiLogDirectory: logDirectory)

        // Sanity check: this fixture really is treated as incompatible by
        // every gated method, so the contrast below is meaningful.
        do {
            _ = try await bridge.verifyEngineIsCompatible()
            XCTFail("expected IncompatibleEngineProject to fail the version gate")
        } catch {
            // expected
        }

        let candidateDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("EngineBridgeFolderValidationTests-dir-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: candidateDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: candidateDirectory) }

        let outcome = await bridge.validateFolder(at: candidateDirectory, requireWritable: false)

        XCTAssertEqual(outcome, .valid, "validateFolder must not be blocked by engine incompatibility")
    }
}
