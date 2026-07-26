import XCTest
@testable import EngineBridge

/// Verifies `CommandResult.Outcome`'s classification against the exact
/// exit-code table documented in `src/cli.py`'s own module docstring:
/// 0 = success/expected, 1 = unexpected internal error, 2 = usage error,
/// 3 = aborted (Ctrl-C). Anything outside that table is preserved, not
/// coerced into one of the four known buckets.
final class CommandResultTests: XCTestCase {

    private func makeResult(exitCode: Int32) -> CommandResult {
        CommandResult(
            command: .status,
            exitCode: exitCode,
            standardOutput: "",
            standardError: ""
        )
    }

    func test_exitCode0_isCompleted() {
        XCTAssertEqual(makeResult(exitCode: 0).outcome, .completed)
    }

    func test_exitCode1_isUnexpectedError() {
        XCTAssertEqual(makeResult(exitCode: 1).outcome, .unexpectedError)
    }

    func test_exitCode2_isUsageError() {
        XCTAssertEqual(makeResult(exitCode: 2).outcome, .usageError)
    }

    func test_exitCode3_isAborted() {
        XCTAssertEqual(makeResult(exitCode: 3).outcome, .aborted)
    }

    func test_unrecognizedExitCode_isPreservedVerbatim() {
        XCTAssertEqual(makeResult(exitCode: 42).outcome, .unrecognizedExitCode(42))
        XCTAssertEqual(makeResult(exitCode: -1).outcome, .unrecognizedExitCode(-1))
    }

    func test_succeeded_isTrueOnlyForExitCode0() {
        XCTAssertTrue(makeResult(exitCode: 0).succeeded)
        XCTAssertFalse(makeResult(exitCode: 1).succeeded)
        XCTAssertFalse(makeResult(exitCode: 2).succeeded)
        XCTAssertFalse(makeResult(exitCode: 3).succeeded)
        XCTAssertFalse(makeResult(exitCode: 99).succeeded)
    }

    func test_preservesCommandAndCapturedStreams() {
        let result = CommandResult(
            command: .version,
            exitCode: 0,
            standardOutput: "Pipeline Version: 9.9.9-fixture\n",
            standardError: ""
        )
        XCTAssertEqual(result.command, .version)
        XCTAssertEqual(result.standardOutput, "Pipeline Version: 9.9.9-fixture\n")
        XCTAssertEqual(result.standardError, "")
    }
}
