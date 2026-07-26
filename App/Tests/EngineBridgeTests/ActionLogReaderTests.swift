import XCTest
@testable import EngineBridge

final class ActionLogReaderTests: XCTestCase {

    private func fixtureLocations(project: String) throws -> EngineArtifactLocations {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return EngineArtifactLocations(projectRootURL: fixturesRoot.appendingPathComponent(project))
    }

    // MARK: - Mixed well-formed / malformed / blank lines

    func test_readsValidEntriesAndCapturesMalformedLinesAsIssues() throws {
        let reader = ActionLogReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let result = try reader.read()

        // Fixture file: line 1 (valid discover), line 2 (valid move_rename
        // with details), line 3 (invalid JSON), line 4 (blank — silently
        // skipped, not an issue), line 5 (valid JSON missing "action").
        XCTAssertEqual(result.entries.count, 2)
        XCTAssertEqual(result.issues.count, 2)
        XCTAssertEqual(Set(result.issues.map(\.index)), [3, 5])

        let discover = result.entries[0]
        XCTAssertEqual(discover.batchID, "batch-001")
        XCTAssertEqual(discover.fileID, "file-001")
        XCTAssertEqual(discover.action, "discover")
        XCTAssertNil(discover.from)
        XCTAssertNil(discover.to)
        XCTAssertNil(discover.details)

        let moveRename = result.entries[1]
        XCTAssertEqual(moveRename.action, "move_rename")
        XCTAssertEqual(moveRename.from, "/Users/fixture/Downloads/invoice.pdf")
        XCTAssertEqual(moveRename.to, "/Users/fixture/Organized Downloads/Invoices/2026-07-25_Acme_Invoice.pdf")
        XCTAssertEqual(moveRename.details?["confidence_score"]?.doubleValue, 97)
        XCTAssertEqual(moveRename.details?["tier"]?.stringValue, "auto")
    }

    func test_timestampDate_parsesValidISO8601Timestamp() throws {
        let reader = ActionLogReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let result = try reader.read()

        let discover = try XCTUnwrap(result.entries.first)
        XCTAssertNotNil(discover.timestampDate)
    }

    // MARK: - Missing file: normal empty state, per real read_action_log_entries() behavior

    func test_missingActionLog_returnsEmptyResultRatherThanThrowing() throws {
        let reader = ActionLogReader(locations: try fixtureLocations(project: "EmptyEngineProject"))
        let result = try reader.read()

        XCTAssertTrue(result.entries.isEmpty)
        XCTAssertTrue(result.issues.isEmpty)
    }

    // MARK: - Issue content is preserved, not just counted

    func test_parseIssue_preservesOriginalLineContentForDiagnostics() throws {
        let reader = ActionLogReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let result = try reader.read()

        let malformedLineIssue = try XCTUnwrap(result.issues.first(where: { $0.index == 3 }))
        XCTAssertTrue(malformedLineIssue.rawContent.contains("batch-002"))
    }
}
