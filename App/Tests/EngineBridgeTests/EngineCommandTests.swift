import XCTest
@testable import EngineBridge

/// Verifies `EngineCommand`'s three computed properties against the exact,
/// real behavior documented in `src/cli.py` — not against this package's
/// own restatement of that behavior. Each assertion below traces back to a
/// specific fact recorded in `EngineCommand.swift`'s doc comments.
final class EngineCommandTests: XCTestCase {

    // MARK: - argv

    func test_scan_argv() {
        XCTAssertEqual(EngineCommand.scan.argv, ["scan"])
    }

    func test_run_argv() {
        XCTAssertEqual(EngineCommand.run.argv, ["run"])
    }

    func test_preview_argv() {
        XCTAssertEqual(EngineCommand.preview.argv, ["preview"])
    }

    func test_execute_argv_withNeitherFlag() {
        XCTAssertEqual(EngineCommand.execute(yes: false, debug: false).argv, ["execute"])
    }

    func test_execute_argv_withYesOnly() {
        XCTAssertEqual(EngineCommand.execute(yes: true, debug: false).argv, ["execute", "-y"])
    }

    func test_execute_argv_withDebugOnly() {
        XCTAssertEqual(EngineCommand.execute(yes: false, debug: true).argv, ["execute", "--debug"])
    }

    func test_execute_argv_withBothFlags() {
        XCTAssertEqual(EngineCommand.execute(yes: true, debug: true).argv, ["execute", "-y", "--debug"])
    }

    func test_undo_argv_last() {
        XCTAssertEqual(EngineCommand.undo(.last).argv, ["undo", "--last"])
    }

    func test_undo_argv_batchID() {
        XCTAssertEqual(
            EngineCommand.undo(.batchID("batch-123")).argv,
            ["undo", "batch-123"]
        )
    }

    func test_report_argv() {
        XCTAssertEqual(EngineCommand.report.argv, ["report"])
    }

    func test_status_argv() {
        XCTAssertEqual(EngineCommand.status.argv, ["status"])
    }

    func test_version_argv() {
        XCTAssertEqual(EngineCommand.version.argv, ["version"])
    }

    func test_config_argv_noOptions() {
        XCTAssertEqual(EngineCommand.config().argv, ["config"])
    }

    func test_config_argv_setSourceOnly() {
        XCTAssertEqual(
            EngineCommand.config(setSource: "/a/b").argv,
            ["config", "--set-source", "/a/b"]
        )
    }

    func test_config_argv_setDestinationOnly() {
        XCTAssertEqual(
            EngineCommand.config(setDestination: "/c/d").argv,
            ["config", "--set-destination", "/c/d"]
        )
    }

    func test_config_argv_bothOptions() {
        XCTAssertEqual(
            EngineCommand.config(setSource: "/a/b", setDestination: "/c/d").argv,
            ["config", "--set-source", "/a/b", "--set-destination", "/c/d"]
        )
    }

    func test_initialSetup_argv_mapsToInit() {
        XCTAssertEqual(EngineCommand.initialSetup.argv, ["init"])
    }

    func test_provider_argv_enable() {
        XCTAssertEqual(EngineCommand.provider(.enable).argv, ["provider", "enable"])
    }

    func test_provider_argv_disable() {
        XCTAssertEqual(EngineCommand.provider(.disable).argv, ["provider", "disable"])
    }

    func test_provider_argv_status() {
        XCTAssertEqual(EngineCommand.provider(.status).argv, ["provider", "status"])
    }

    // MARK: - requiresInteractiveInput

    func test_requiresInteractiveInput_trueOnlyForTheThreeDocumentedPaths() {
        XCTAssertTrue(EngineCommand.initialSetup.requiresInteractiveInput)
        XCTAssertTrue(EngineCommand.execute(yes: false, debug: false).requiresInteractiveInput)
        XCTAssertTrue(EngineCommand.provider(.enable).requiresInteractiveInput)
    }

    func test_requiresInteractiveInput_falseForExecuteWithYes() {
        XCTAssertFalse(EngineCommand.execute(yes: true, debug: false).requiresInteractiveInput)
    }

    func test_requiresInteractiveInput_falseForEverythingElse() {
        let nonInteractiveCommands: [EngineCommand] = [
            .scan, .run, .preview, .report, .status, .version,
            .config(), .undo(.last), .undo(.batchID("x")),
            .provider(.disable), .provider(.status)
        ]
        for command in nonInteractiveCommands {
            XCTAssertFalse(
                command.requiresInteractiveInput,
                "\(command) should not require interactive input"
            )
        }
    }

    // MARK: - isMutating

    func test_isMutating_falseForDocumentedReadOnlyCommands() {
        XCTAssertFalse(EngineCommand.preview.isMutating)
        XCTAssertFalse(EngineCommand.status.isMutating)
        XCTAssertFalse(EngineCommand.version.isMutating)
        XCTAssertFalse(EngineCommand.provider(.status).isMutating)
    }

    func test_isMutating_trueForReport() {
        // report is classified as mutating because it writes new files to
        // Runtime/Reports/, even though it never touches the metadata store
        // or action log — see EngineCommand.isMutating's doc comment.
        XCTAssertTrue(EngineCommand.report.isMutating)
    }

    func test_isMutating_trueForEverythingElse() {
        let mutatingCommands: [EngineCommand] = [
            .scan, .run,
            .execute(yes: true, debug: false),
            .undo(.last),
            .config(setSource: "/x"),
            .initialSetup,
            .provider(.enable),
            .provider(.disable)
        ]
        for command in mutatingCommands {
            XCTAssertTrue(command.isMutating, "\(command) should be classified as mutating")
        }
    }
}
