import XCTest
@testable import EngineBridge

/// End-to-end integration tests for the `EngineBridge` facade — the final
/// WP-GUI-00 deliverable. Every test here goes through the public facade
/// API only (`EngineBridge.run`, `.readConfiguration`, etc.), never
/// reaching into `ProcessRunner`/`EngineMutationGuard`/the readers
/// directly, since proving the facade's own wiring is exactly what
/// distinguishes this suite from `ProcessRunnerTests`,
/// `EngineMutationGuardTests`, and the per-reader test files.
final class EngineBridgeTests: XCTestCase {

    /// The example supported range used throughout this suite. Per
    /// `VersionCompatibilityChecker`'s own documentation, WP-GUI-00 does
    /// not fix real supported-version numbers — these are test fixture
    /// values only, chosen so the fixture engine's `0.8.0` falls inside
    /// the range and `IncompatibleEngineProject`'s `9.9.9` falls outside
    /// it.
    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeTempLogDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("EngineBridgeTests-\(UUID().uuidString)")
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

    // MARK: - End-to-end smoke test

    func test_endToEnd_versionCheckThenReadOnlyCommand_succeeds() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        let version = try await bridge.verifyEngineIsCompatible()
        XCTAssertEqual(version, SemanticVersion(major: 0, minor: 8, patch: 0))

        let result = try await bridge.run(.version)
        XCTAssertTrue(result.succeeded)
    }

    // MARK: - Read-only command flow

    func test_readOnlyCommand_doesNotRequireMutationSlot() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        // Many concurrent read-only calls through the facade must all
        // succeed — proving isMutating: false commands are never
        // serialized against each other by the guard the facade wires in.
        try await withThrowingTaskGroup(of: Bool.self) { group in
            for _ in 0..<10 {
                group.addTask {
                    let result = try await bridge.run(.status)
                    return result.succeeded
                }
            }
            for try await succeeded in group {
                XCTAssertTrue(succeeded)
            }
        }
    }

    // MARK: - Mutating command flow

    func test_mutatingCommand_succeedsThroughTheGuard() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        let result = try await bridge.run(.provider(.disable))
        XCTAssertTrue(result.succeeded)
    }

    // MARK: - Concurrency guard integration (through the facade, not the guard directly)

    func test_secondConcurrentMutatingCommand_isRefusedThroughTheFacade() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        // .config sleeps ~0.3s in the fixture engine before succeeding.
        async let first = bridge.run(.config(setSource: "/tmp/fixture"))

        // Give the first call a real chance to acquire the slot before
        // firing the second. A short, generous sleep is acceptable here
        // (unlike EngineMutationGuardTests's polling approach) because
        // this test's purpose is to prove the facade's wiring reaches the
        // same guard, not to re-verify the guard's own race-freedom, which
        // is already covered exhaustively in EngineMutationGuardTests.
        try await Task.sleep(nanoseconds: 100_000_000) // 100ms

        do {
            _ = try await bridge.run(.provider(.disable))
            XCTFail("expected the second, concurrent mutating call to be refused")
        } catch EngineBridgeError.anotherMutatingOperationInProgress {
            // expected
        }

        let firstResult = try await first
        XCTAssertTrue(firstResult.succeeded)
    }

    // MARK: - Failure propagation (interactive-command refusal, unwrapped)

    func test_interactiveCommandRefusal_propagatesUnwrapped() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        do {
            _ = try await bridge.run(.initialSetup)
            XCTFail("expected commandRequiresInteractiveInput to be thrown")
        } catch EngineBridgeError.commandRequiresInteractiveInput(let command) {
            XCTAssertEqual(command, .initialSetup)
        }
    }

    // MARK: - Artifact read flow

    func test_readConfiguration_returnsRealShapedData() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        let configuration = try await bridge.readConfiguration()
        XCTAssertEqual(configuration.sources.first?.sourceID, "downloads")
    }

    func test_readMetadataStore_returnsRecordsAndSummary() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        let result = try await bridge.readMetadataStore()
        XCTAssertEqual(result.records.count, 2)
        XCTAssertEqual(result.summary.totalRecordCount, 2)
    }

    func test_readActionLog_returnsEntriesAndIssues() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        let result = try await bridge.readActionLog()
        XCTAssertEqual(result.entries.count, 2)
        XCTAssertEqual(result.issues.count, 2)
    }

    func test_readReports_returnsExpectedContent() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        let duplicate = try await bridge.readDuplicateReport()
        XCTAssertTrue(duplicate?.markdownText.contains("Duplicate Report") ?? false)

        let storage = try await bridge.readStorageReport()
        XCTAssertTrue(storage?.markdownText.contains("Storage Report") ?? false)

        let daily = try await bridge.readLatestDailySummary()
        XCTAssertEqual(daily?.fileURL.lastPathComponent, "summary_2026-07-26.md")

        let weekly = try await bridge.readLatestWeeklySummary()
        XCTAssertEqual(weekly?.fileURL.lastPathComponent, "summary_2026-W30.md")
    }

    // MARK: - Missing artifact handling (configured + compatible, but never scanned)

    func test_configuredButNeverScannedProject_returnsEmptyOrNilRatherThanThrowing() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "ConfiguredButFreshEngineProject", guiLogDirectory: logDirectory)

        // Configuration exists and is readable.
        let configuration = try await bridge.readConfiguration()
        XCTAssertEqual(configuration.sources.first?.sourceID, "downloads")

        // Database/ and Runtime/ do not exist at all in this fixture.
        let metadata = try await bridge.readMetadataStore()
        XCTAssertTrue(metadata.records.isEmpty)

        let actionLog = try await bridge.readActionLog()
        XCTAssertTrue(actionLog.entries.isEmpty)

        let duplicate = try await bridge.readDuplicateReport()
        XCTAssertNil(duplicate)

        let storage = try await bridge.readStorageReport()
        XCTAssertNil(storage)

        let daily = try await bridge.readLatestDailySummary()
        XCTAssertNil(daily)

        // And a real command still runs successfully — "never scanned" is
        // about the artifacts, not about whether the engine executable
        // itself is reachable.
        let result = try await bridge.run(.status)
        XCTAssertTrue(result.succeeded)
    }

    // MARK: - Version failure: refused before any command execution or artifact read

    func test_incompatibleEngineVersion_refusesCommandExecution() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "IncompatibleEngineProject", guiLogDirectory: logDirectory)

        do {
            _ = try await bridge.run(.status)
            XCTFail("expected engineVersionTooNew to be thrown")
        } catch EngineBridgeError.engineVersionTooNew(let engineVersion, let maximumSupportedVersion) {
            XCTAssertEqual(engineVersion, SemanticVersion(major: 9, minor: 9, patch: 9))
            XCTAssertEqual(maximumSupportedVersion, self.maximumSupportedVersion)
        }
    }

    func test_incompatibleEngineVersion_refusesArtifactReadsBeforeTouchingTheReader() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "IncompatibleEngineProject", guiLogDirectory: logDirectory)

        // IncompatibleEngineProject's sources.yaml is real and perfectly
        // readable — if the version gate did not run first, this call
        // would succeed. It must not.
        do {
            _ = try await bridge.readConfiguration()
            XCTFail("expected engineVersionTooNew to be thrown before the configuration was ever read")
        } catch EngineBridgeError.engineVersionTooNew {
            // expected
        }

        do {
            _ = try await bridge.readMetadataStore()
            XCTFail("expected engineVersionTooNew to be thrown before the metadata store was ever read")
        } catch EngineBridgeError.engineVersionTooNew {
            // expected
        }
    }

    func test_missingVersionInformation_refusesEverything() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "EmptyEngineProject", guiLogDirectory: logDirectory)

        do {
            _ = try await bridge.run(.status)
            XCTFail("expected artifactNotFound to be thrown")
        } catch EngineBridgeError.artifactNotFound(let path) {
            XCTAssertTrue(path.hasSuffix("VERSIONS.md"))
        }
    }

    func test_currentEngineVersion_isStillReadableAfterAnIncompatibilityFailure() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "IncompatibleEngineProject", guiLogDirectory: logDirectory)

        do {
            _ = try await bridge.run(.status)
            XCTFail("expected engineVersionTooNew to be thrown")
        } catch {
            // expected — asserted in detail elsewhere; this test cares
            // about what happens next.
        }

        // Even though the gated methods refuse to proceed, the raw version
        // must still be readable, since the Error State needs to display
        // exactly which version is installed.
        let rawVersion = try await bridge.currentEngineVersion()
        XCTAssertEqual(rawVersion, SemanticVersion(major: 9, minor: 9, patch: 9))
    }

    // MARK: - Logger integration

    func test_loggerIntegration_recordsCommandResultsAndVersionFailures() async throws {
        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        _ = try await bridge.run(.version)

        let incompatibleBridge = try makeBridge(project: "IncompatibleEngineProject", guiLogDirectory: logDirectory)
        _ = try? await incompatibleBridge.run(.status)

        let logContents = try String(contentsOf: logDirectory.appendingPathComponent("gui.log"), encoding: .utf8)

        // The successful command result, logged by ProcessRunner itself
        // through the shared logger the facade wired in.
        XCTAssertTrue(logContents.contains("command=version"))
        XCTAssertTrue(logContents.contains("exitCode=0"))

        // The version-incompatibility failure, logged by the facade's own
        // verifyEngineIsCompatible().
        XCTAssertTrue(logContents.contains("not compatible"))
    }

    // MARK: - The real action log is never touched by any of the above

    func test_noneOfTheAboveOperationsEverModifyTheRealActionLog() async throws {
        let projectRoot = try fixtureURL("FakeEngineProject")
        let actionLogURL = EngineArtifactLocations(projectRootURL: projectRoot).actionLogURL
        let before = try Data(contentsOf: actionLogURL)

        let logDirectory = makeTempLogDirectory()
        defer { try? FileManager.default.removeItem(at: logDirectory) }
        let bridge = try makeBridge(project: "FakeEngineProject", guiLogDirectory: logDirectory)

        _ = try await bridge.run(.version)
        _ = try await bridge.readActionLog()
        _ = try await bridge.readMetadataStore()

        let after = try Data(contentsOf: actionLogURL)
        XCTAssertEqual(before, after)
    }
}
