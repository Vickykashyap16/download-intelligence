import XCTest
@testable import EngineBridge

final class ReportsReaderTests: XCTestCase {

    private func fixtureLocations(project: String) throws -> EngineArtifactLocations {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return EngineArtifactLocations(projectRootURL: fixturesRoot.appendingPathComponent(project))
    }

    // MARK: - Single-file reports (Duplicate Report, Storage Report)

    func test_readDuplicateReport_returnsRawMarkdownUnmodified() throws {
        let reader = ReportsReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let report = try XCTUnwrap(try reader.readDuplicateReport())

        XCTAssertEqual(report.kind, .duplicateReport)
        XCTAssertTrue(report.markdownText.contains("# Duplicate Report"))
        XCTAssertTrue(report.markdownText.contains("No duplicate groups"))
    }

    func test_readStorageReport_returnsRawMarkdownUnmodified() throws {
        let reader = ReportsReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let report = try XCTUnwrap(try reader.readStorageReport())

        XCTAssertEqual(report.kind, .storageReport)
        XCTAssertTrue(report.markdownText.contains("Total tracked size"))
    }

    // MARK: - Dated reports: "latest" selection

    func test_readLatestDailySummary_picksNewestDatedFile() throws {
        let reader = ReportsReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let report = try XCTUnwrap(try reader.readLatestDailySummary())

        XCTAssertEqual(report.kind, .dailySummary)
        XCTAssertEqual(report.fileURL.lastPathComponent, "summary_2026-07-26.md")
        XCTAssertTrue(report.markdownText.contains("2026-07-26"))
        XCTAssertFalse(report.markdownText.contains("older fixture"))
    }

    func test_readLatestWeeklySummary_picksNewestDatedFile() throws {
        let reader = ReportsReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let report = try XCTUnwrap(try reader.readLatestWeeklySummary())

        XCTAssertEqual(report.kind, .weeklySummary)
        XCTAssertEqual(report.fileURL.lastPathComponent, "summary_2026-W30.md")
    }

    // MARK: - Nothing generated yet: the Reports screen's own documented Empty State

    func test_noReportsGeneratedYet_returnsNilForEveryKindRatherThanThrowing() throws {
        let reader = ReportsReader(locations: try fixtureLocations(project: "EmptyEngineProject"))

        XCTAssertNil(try reader.readDuplicateReport())
        XCTAssertNil(try reader.readStorageReport())
        XCTAssertNil(try reader.readLatestDailySummary())
        XCTAssertNil(try reader.readLatestWeeklySummary())
    }
}
