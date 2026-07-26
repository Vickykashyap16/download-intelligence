import XCTest
@testable import EngineBridge

final class FileGUILoggerTests: XCTestCase {

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("FileGUILoggerTests-\(UUID().uuidString)")
    }

    // MARK: - Creation

    func test_firstLogCall_createsLogDirectoryAndFile() async throws {
        let directory = makeTempDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let logger = FileGUILogger(configuration: .init(logDirectoryURL: directory))
        await logger.log("first message", level: .info)

        let logFileURL = directory.appendingPathComponent("gui.log")
        XCTAssertTrue(FileManager.default.fileExists(atPath: logFileURL.path))

        let contents = try String(contentsOf: logFileURL, encoding: .utf8)
        XCTAssertTrue(contents.contains("[INFO]"))
        XCTAssertTrue(contents.contains("first message"))
        let failureReason = await logger.lastFailureReason
        XCTAssertNil(failureReason)
    }

    func test_customFilename_isRespected() async throws {
        let directory = makeTempDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let logger = FileGUILogger(configuration: .init(logDirectoryURL: directory, currentLogFilename: "diagnostics.log"))
        await logger.log("hello", level: .debug)

        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent("diagnostics.log").path))
    }

    // MARK: - Appending

    func test_multipleLogCalls_appendInOrderToTheSameFile() async throws {
        let directory = makeTempDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let logger = FileGUILogger(configuration: .init(logDirectoryURL: directory))
        await logger.log("first", level: .info)
        await logger.log("second", level: .warning)
        await logger.log("third", level: .error)

        let contents = try String(contentsOf: directory.appendingPathComponent("gui.log"), encoding: .utf8)
        let lines = contents.split(separator: "\n")
        XCTAssertEqual(lines.count, 3)
        XCTAssertTrue(lines[0].contains("first"))
        XCTAssertTrue(lines[1].contains("second"))
        XCTAssertTrue(lines[2].contains("third"))
    }

    // MARK: - GUILogger protocol conformance (CommandResult logging)

    func test_logResult_viaGUILoggerProtocol_writesASummaryLine() async throws {
        let directory = makeTempDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let logger: GUILogger = FileGUILogger(configuration: .init(logDirectoryURL: directory))
        let result = CommandResult(command: .status, exitCode: 0, standardOutput: "ok", standardError: "")
        await logger.log(result: result)

        let contents = try String(contentsOf: directory.appendingPathComponent("gui.log"), encoding: .utf8)
        XCTAssertTrue(contents.contains("status"))
        XCTAssertTrue(contents.contains("exitCode=0"))
        XCTAssertTrue(contents.contains("[INFO]")) // succeeded => info, not warning
    }

    func test_logFailedResult_isLoggedAtWarningLevel() async throws {
        let directory = makeTempDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let logger = FileGUILogger(configuration: .init(logDirectoryURL: directory))
        let result = CommandResult(command: .report, exitCode: 1, standardOutput: "", standardError: "boom")
        await logger.log(result: result)

        let contents = try String(contentsOf: directory.appendingPathComponent("gui.log"), encoding: .utf8)
        XCTAssertTrue(contents.contains("[WARNING]"))
    }

    // MARK: - Rotation

    func test_rotation_movesOverflowIntoNumberedBackupsAndTrimsOldest() async throws {
        let directory = makeTempDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        // A tiny size threshold and small backup count so a handful of
        // ordinary log lines is enough to force several rotations without
        // writing megabytes of fixture data.
        let logger = FileGUILogger(configuration: .init(
            logDirectoryURL: directory,
            maximumLogFileSizeBytes: 40,
            maximumRotatedFileCount: 2
        ))

        for index in 1...6 {
            await logger.log("line number \(index) of the rotation test", level: .info)
        }

        let currentLogURL = directory.appendingPathComponent("gui.log")
        let backup1URL = directory.appendingPathComponent("gui.log.1")
        let backup2URL = directory.appendingPathComponent("gui.log.2")
        let backup3URL = directory.appendingPathComponent("gui.log.3")

        XCTAssertTrue(FileManager.default.fileExists(atPath: currentLogURL.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: backup1URL.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: backup2URL.path))
        XCTAssertFalse(
            FileManager.default.fileExists(atPath: backup3URL.path),
            "maximumRotatedFileCount is 2 — a third backup file must never accumulate"
        )
    }

    // MARK: - Failure handling: never throws, never crashes, remains inert

    func test_whenLogDirectoryPathIsBlockedByARegularFile_logDoesNotThrowAndRecordsFailure() async throws {
        let directory = makeTempDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        // Create the parent, then put an ordinary *file* exactly where the
        // logger wants to create its *directory* — createDirectory(at:)
        // must fail for a path already occupied by a non-directory file.
        try FileManager.default.createDirectory(
            at: directory.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data("not a directory".utf8).write(to: directory)

        let logger = FileGUILogger(configuration: .init(logDirectoryURL: directory))

        // The call itself must complete normally — no throw is possible
        // here by the GUILogger protocol's own (non-throwing) signature,
        // so this is really asserting "does not crash / does not hang."
        await logger.log("this cannot possibly be written", level: .error)

        let failureReason = await logger.lastFailureReason
        XCTAssertNotNil(failureReason, "a write into a blocked directory must be recorded as a failure, not silently treated as success")
    }

    func test_afterAFailure_aSubsequentSuccessfulWriteClearsTheFailureReason() async throws {
        let blockedPath = makeTempDirectory()
        defer { try? FileManager.default.removeItem(at: blockedPath) }
        try FileManager.default.createDirectory(
            at: blockedPath.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data("not a directory".utf8).write(to: blockedPath)

        let logger = FileGUILogger(configuration: .init(logDirectoryURL: blockedPath))
        await logger.log("first attempt fails", level: .error)
        let firstFailureReason = await logger.lastFailureReason
        XCTAssertNotNil(firstFailureReason)

        // Clear the obstruction and confirm recovery — a transient failure
        // must not permanently disable the logger.
        try FileManager.default.removeItem(at: blockedPath)
        await logger.log("second attempt should succeed", level: .info)
        let secondFailureReason = await logger.lastFailureReason
        XCTAssertNil(secondFailureReason)
    }

    // MARK: - Integration: using the logger alongside ProcessRunner never touches the real action log

    func test_loggingRealCommandResults_neverModifiesTheEngineActionLog() async throws {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        let projectRoot = fixturesRoot.appendingPathComponent("FakeEngineProject")
        let actionLogURL = EngineArtifactLocations(projectRootURL: projectRoot).actionLogURL
        let actionLogContentsBefore = try Data(contentsOf: actionLogURL)

        let guiLogDirectory = makeTempDirectory()
        defer { try? FileManager.default.removeItem(at: guiLogDirectory) }

        let logger = FileGUILogger(configuration: .init(logDirectoryURL: guiLogDirectory))
        let runner = ProcessRunner(configuration: .init(projectRootURL: projectRoot), logger: logger)

        _ = try await runner.run(.version)
        _ = try await runner.run(.status)

        let actionLogContentsAfter = try Data(contentsOf: actionLogURL)
        XCTAssertEqual(
            actionLogContentsBefore,
            actionLogContentsAfter,
            "using the GUI logger must never alter the engine's own action log"
        )

        // And the GUI's own log, entirely separate, did receive the entries.
        let guiLogContents = try String(contentsOf: guiLogDirectory.appendingPathComponent("gui.log"), encoding: .utf8)
        XCTAssertTrue(guiLogContents.contains("version"))
        XCTAssertTrue(guiLogContents.contains("status"))
    }
}
