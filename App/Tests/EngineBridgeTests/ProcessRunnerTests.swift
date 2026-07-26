import XCTest
@testable import EngineBridge

/// Integration tests: these spawn a *real* subprocess (`python3 -m src.cli`)
/// against a fixture project that stands in for the real engine — see
/// `Fixtures/FakeEngineProject/src/cli.py` for exactly what each fixture
/// command does and why. Deliberately never points at the real
/// `Download Intelligence` checkout: these tests must be safe to run
/// repeatedly with no risk of ever touching real `Database/`/`Runtime/`
/// data, per this project's non-negotiable "every action must be
/// reversible" / never-mutate-real-data-in-tests rule.
///
/// Requires a working `python3` on the machine running the tests (the
/// project already depends on Python 3 for the real engine, so any machine
/// set up to run this project at all should already have it).
final class ProcessRunnerTests: XCTestCase {

    private func makeRunner(logger: GUILogger? = nil) throws -> ProcessRunner {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        let projectRoot = fixturesRoot.appendingPathComponent("FakeEngineProject")
        return ProcessRunner(
            configuration: .init(projectRootURL: projectRoot),
            logger: logger
        )
    }

    // MARK: - Successful invocation

    func test_version_succeedsAndCapturesStdout() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.version)

        XCTAssertTrue(result.succeeded)
        XCTAssertEqual(result.outcome, .completed)
        XCTAssertTrue(
            result.standardOutput.contains("Pipeline Version: 9.9.9-fixture"),
            "unexpected stdout: \(result.standardOutput)"
        )
        XCTAssertEqual(result.standardError, "")
    }

    // MARK: - Large output does not deadlock

    func test_status_capturesLargeOutputWithoutDeadlocking() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.status)

        XCTAssertTrue(result.succeeded)
        // 100_000 "x" characters plus the trailing newline from `print`.
        XCTAssertEqual(result.standardOutput.count, 100_001)
    }

    // MARK: - Exit-code classification, per src/cli.py's documented table

    func test_report_exitCode1_isClassifiedAsUnexpectedError() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.report)

        XCTAssertEqual(result.exitCode, 1)
        XCTAssertEqual(result.outcome, .unexpectedError)
        XCTAssertFalse(result.succeeded)
        XCTAssertTrue(result.standardError.contains("simulated internal failure"))
    }

    func test_scan_exitCode2_isClassifiedAsUsageError() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.scan)

        XCTAssertEqual(result.exitCode, 2)
        XCTAssertEqual(result.outcome, .usageError)
    }

    func test_run_exitCode3_isClassifiedAsAborted() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.run)

        XCTAssertEqual(result.exitCode, 3)
        XCTAssertEqual(result.outcome, .aborted)
    }

    func test_undoLast_exitCode42_isPreservedAsUnrecognized() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.undo(.last))

        XCTAssertEqual(result.exitCode, 42)
        XCTAssertEqual(result.outcome, .unrecognizedExitCode(42))
    }

    // MARK: - Interactive-command refusal (fails fast, no subprocess spawned)

    func test_initialSetup_isRefusedWithoutExplicitOptIn() async throws {
        let runner = try makeRunner()
        do {
            _ = try await runner.run(.initialSetup)
            XCTFail("Expected commandRequiresInteractiveInput to be thrown")
        } catch EngineBridgeError.commandRequiresInteractiveInput(let command) {
            XCTAssertEqual(command, .initialSetup)
        }
    }

    func test_executeWithoutYes_isRefusedWithoutExplicitOptIn() async throws {
        let runner = try makeRunner()
        do {
            _ = try await runner.run(.execute(yes: false, debug: false))
            XCTFail("Expected commandRequiresInteractiveInput to be thrown")
        } catch EngineBridgeError.commandRequiresInteractiveInput {
            // expected
        }
    }

    // MARK: - Closed stdin delivers immediate EOF, never a hang

    func test_initialSetup_withExplicitOptIn_receivesImmediateEOFRatherThanHanging() async throws {
        let runner = try makeRunner()

        let result = try await runner.run(.initialSetup, allowInteractive: true)

        // The fixture's `init` branch calls input(), which — because
        // ProcessRunner always closes its own copy of the stdin pipe's
        // write end immediately after launch — raises EOFError right away.
        // The fixture mirrors the real CLI's own outermost handler by
        // reporting that as exit code 1, not by hanging.
        XCTAssertEqual(result.exitCode, 1)
        XCTAssertEqual(result.outcome, .unexpectedError)
        XCTAssertTrue(result.standardError.contains("EOF"))
    }

    // MARK: - Non-interactive command with no special behavior

    func test_preview_echoesArgumentsAndSucceeds() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.preview)

        XCTAssertTrue(result.succeeded)
        XCTAssertTrue(result.standardOutput.contains("fixture preview ok:"))
    }

    // MARK: - config and provider (added for EngineMutationGuard coverage)

    func test_config_succeeds() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.config(setSource: "/tmp/fixture"))

        XCTAssertTrue(result.succeeded)
        XCTAssertTrue(result.standardOutput.contains("config updated"))
    }

    func test_providerDisable_succeeds() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.provider(.disable))

        XCTAssertTrue(result.succeeded)
        XCTAssertTrue(result.standardOutput.contains("provider disabled"))
    }

    func test_providerStatus_succeeds() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.provider(.status))

        XCTAssertTrue(result.succeeded)
        XCTAssertTrue(result.standardOutput.contains("provider: disabled"))
    }

    func test_providerEnable_isRefusedWithoutExplicitOptIn() async throws {
        let runner = try makeRunner()
        do {
            _ = try await runner.run(.provider(.enable))
            XCTFail("Expected commandRequiresInteractiveInput to be thrown")
        } catch EngineBridgeError.commandRequiresInteractiveInput {
            // expected
        }
    }

    func test_providerEnable_withExplicitOptIn_receivesImmediateEOFRatherThanHanging() async throws {
        let runner = try makeRunner()
        let result = try await runner.run(.provider(.enable), allowInteractive: true)

        XCTAssertEqual(result.exitCode, 1)
        XCTAssertTrue(result.standardError.contains("EOF"))
    }

    // MARK: - Missing project root

    func test_missingProjectRoot_throwsProjectRootNotFound() async throws {
        let bogusRoot = URL(fileURLWithPath: "/nonexistent/path/that/should/never/exist-\(UUID().uuidString)")
        let runner = ProcessRunner(configuration: .init(projectRootURL: bogusRoot))

        do {
            _ = try await runner.run(.version)
            XCTFail("Expected projectRootNotFound to be thrown")
        } catch EngineBridgeError.projectRootNotFound(let path) {
            XCTAssertEqual(path, bogusRoot.path)
        }
    }

    // MARK: - Logger integration

    func test_successfulRun_isReportedToTheInjectedLogger() async throws {
        let recorder = RecordingLogger()
        let runner = try makeRunner(logger: recorder)

        _ = try await runner.run(.version)

        let logged = await recorder.results
        XCTAssertEqual(logged.count, 1)
        XCTAssertEqual(logged.first?.command, .version)
    }

    func test_refusedInteractiveCommand_isNeverReportedToTheLogger() async throws {
        let recorder = RecordingLogger()
        let runner = try makeRunner(logger: recorder)

        _ = try? await runner.run(.initialSetup)

        let logged = await recorder.results
        XCTAssertTrue(logged.isEmpty, "A refused, never-spawned command should not be logged as a result")
    }
}

/// A trivial in-memory `GUILogger` used only to assert that `ProcessRunner`
/// calls through to whatever logger it was configured with, exactly once
/// per completed invocation. Not a stand-in for the real, file-backed
/// implementation this work package still owes separately.
private actor RecordingLogger: GUILogger {
    private(set) var results: [CommandResult] = []

    func log(result: CommandResult) async {
        results.append(result)
    }
}
