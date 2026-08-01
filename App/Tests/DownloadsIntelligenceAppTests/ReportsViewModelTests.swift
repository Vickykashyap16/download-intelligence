import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `ReportsViewModel` against a real `EngineBridge`.
///
/// Most tests here deliberately omit `src/cli.py` from their fixture
/// project entirely — `refreshNow()`'s own `_ = try? await
/// bridge.run(.report)` call is designed to tolerate that invocation
/// failing for any reason whatsoever (per WP-GUI-10's own verified design:
/// "never infer success from the command result alone... the artifact
/// re-read is the source of truth"), so a fixture with no working `report`
/// command at all is a meaningful, deliberate way to prove the read path
/// truly does not depend on the invocation having succeeded. The one
/// exception is `test_refreshNow_realReportSubprocess...` below, which
/// exercises the real subprocess path end-to-end via the new, isolated
/// `ReportingEngineProject` fixture (this work package's own — it does not
/// touch `UndoingEngineProject`/`ExecutingEngineProject`, which belong to
/// other, already-frozen work packages).
@MainActor
final class ReportsViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func makeTempDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("ReportsViewModelTests-\(UUID().uuidString)")
    }

    /// Builds a minimal fixture project with only `Release/VERSIONS.md` and
    /// (optionally) pre-seeded `Runtime/Reports/*` content — deliberately no
    /// `src/` at all, so `bridge.run(.report)` cannot possibly succeed,
    /// proving these tests exercise the read path alone.
    private func makeProject() throws -> URL {
        let root = makeTempDirectory()
        try FileManager.default.createDirectory(at: root.appendingPathComponent("Release"), withIntermediateDirectories: true)
        try "**Pipeline Version: 0.8.0**\n".write(
            to: root.appendingPathComponent("Release/VERSIONS.md"), atomically: true, encoding: .utf8
        )
        return root
    }

    private func makeBridge(projectRoot: URL) -> EngineBridge {
        EngineBridge(configuration: .init(
            projectRootURL: projectRoot,
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
    }

    private func writeReportFile(root: URL, relativePath: String, content: String) throws {
        let url = root.appendingPathComponent("Runtime/Reports").appendingPathComponent(relativePath)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try content.write(to: url, atomically: true, encoding: .utf8)
    }

    // MARK: - Success: all four artifacts already on disk, no working `report` command needed

    func test_refreshNow_allFourReportsExist_populatesProjectionWithNoErrors() async throws {
        let root = try makeProject()
        defer { try? FileManager.default.removeItem(at: root) }

        try writeReportFile(
            root: root, relativePath: "Daily Summary/summary_2026-08-01.md",
            content: "# Daily Summary — 2026-08-01\n\n- Files scanned: 1\n\n## Files\n| Original | New Name | Destination | Category | Confidence | Tier |\n|---|---|---|---|---|---|\n| a.pdf | A.pdf | Finance/ | invoice | 97 | auto |\n"
        )
        try writeReportFile(
            root: root, relativePath: "Weekly Summary/summary_2026-W31.md",
            content: "# Weekly Summary — 2026-W31\n\n- Week range: 2026-07-28 to 2026-08-03\n\n## Days\n| Date | Status |\n|---|---|\n| 2026-08-01 | Reported |\n"
        )
        try writeReportFile(
            root: root, relativePath: "Duplicate Report/duplicate_report.md",
            content: "# Duplicate Report\n\n- As of: no activity recorded yet\n\n## Records\n| Original | Type | Related To | Disposition |\n|---|---|---|---|\n"
        )
        try writeReportFile(
            root: root, relativePath: "Storage Report/storage_report.md",
            content: "# Storage Report\n\n- Filed records: 1\n\n## By Destination\n| Destination | Size |\n|---|---|\n| Finance/ | 12.0 KB |\n"
        )

        let viewModel = ReportsViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.dailySummaryError)
        XCTAssertNil(viewModel.weeklySummaryError)
        XCTAssertNil(viewModel.duplicateReportError)
        XCTAssertNil(viewModel.storageReportError)

        XCTAssertFalse(viewModel.projection?.isEmpty ?? true)
        guard case .structured(let title, _) = viewModel.projection?.dailySummary?.content else {
            return XCTFail("Expected Daily Summary to parse as structured content")
        }
        XCTAssertEqual(title, "Daily Summary — 2026-08-01")
        XCTAssertNotNil(viewModel.projection?.weeklySummary)
        XCTAssertNotNil(viewModel.projection?.duplicateReport)
        XCTAssertNotNil(viewModel.projection?.storageReport)
    }

    // MARK: - Never generated: Hi-Fi §11's "No reports generated yet"

    func test_refreshNow_noReportsGeneratedYet_projectionIsEmptyWithNoErrors() async throws {
        let root = try makeProject()
        defer { try? FileManager.default.removeItem(at: root) }

        let viewModel = ReportsViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        XCTAssertFalse(viewModel.isLoading)
        XCTAssertTrue(viewModel.projection?.isEmpty ?? false)
        XCTAssertNil(viewModel.dailySummaryError)
        XCTAssertNil(viewModel.weeklySummaryError)
        XCTAssertNil(viewModel.duplicateReportError)
        XCTAssertNil(viewModel.storageReportError)
    }

    // MARK: - Per-report isolation: one unreadable artifact never affects the other three

    /// Hi-Fi §11 States: "if a specific report fails to generate/load, this
    /// is shown as a plain message within that sub-view only, without
    /// affecting the other three." Simulated here by making the Duplicate
    /// Report's own expected file path a directory instead of a file —
    /// `ReportsReader.readDuplicateReport()`'s `String(contentsOf:)` call
    /// throws for a directory, surfacing `EngineBridgeError
    /// .artifactUnreadable` for that report alone.
    func test_refreshNow_oneReportUnreadable_isolatedToThatReportOnly() async throws {
        let root = try makeProject()
        defer { try? FileManager.default.removeItem(at: root) }

        try writeReportFile(
            root: root, relativePath: "Storage Report/storage_report.md",
            content: "# Storage Report\n\n- Filed records: 0\n\n## By Destination\n| Destination | Size |\n|---|---|\n"
        )
        // A directory where the Duplicate Report file is expected.
        try FileManager.default.createDirectory(
            at: root.appendingPathComponent("Runtime/Reports/Duplicate Report/duplicate_report.md"),
            withIntermediateDirectories: true
        )

        let viewModel = ReportsViewModel(bridge: makeBridge(projectRoot: root))
        await viewModel.refreshNow()

        XCTAssertNil(viewModel.dailySummaryError)
        XCTAssertNil(viewModel.weeklySummaryError)
        XCTAssertNil(viewModel.storageReportError)
        XCTAssertEqual(viewModel.duplicateReportError?.heading, "Something went wrong")

        // The other three report slots are entirely unaffected.
        XCTAssertNil(viewModel.projection?.dailySummary)
        XCTAssertNil(viewModel.projection?.weeklySummary)
        XCTAssertNil(viewModel.projection?.duplicateReport)
        XCTAssertNotNil(viewModel.projection?.storageReport)
    }

    // MARK: - Whole-engine failure: incompatible version affects all four uniformly

    func test_refreshNow_incompatibleEngineVersion_allFourReportsShowError() async throws {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        let bridge = EngineBridge(configuration: .init(
            projectRootURL: fixturesRoot.appendingPathComponent("IncompatibleEngineProject"),
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempDirectory()
        ))
        let viewModel = ReportsViewModel(bridge: bridge)

        await viewModel.refreshNow()

        XCTAssertEqual(viewModel.dailySummaryError?.heading, "Update needed")
        XCTAssertEqual(viewModel.weeklySummaryError?.heading, "Update needed")
        XCTAssertEqual(viewModel.duplicateReportError?.heading, "Update needed")
        XCTAssertEqual(viewModel.storageReportError?.heading, "Update needed")
        XCTAssertNil(viewModel.projection?.dailySummary)
        XCTAssertNil(viewModel.projection?.weeklySummary)
        XCTAssertNil(viewModel.projection?.duplicateReport)
        XCTAssertNil(viewModel.projection?.storageReport)
    }

    // MARK: - Real end-to-end: the subprocess actually runs and writes the files this reads back

    /// WP-GUI-10's own Test Plan: exercise `bridge.run(.report)` as a real
    /// subprocess at least once, proving the invocation is wired correctly
    /// and that the always-following re-read reflects exactly what that
    /// process wrote — not a fixture standing in for both halves at once.
    /// Uses an isolated copy of the checked-in `ReportingEngineProject`
    /// fixture (mirrors `HistoryViewModelTests`' own isolated-copy
    /// precedent) so repeated test runs never accumulate written report
    /// files in the checked-in fixture itself.
    func test_refreshNow_realReportSubprocess_generatesAndReadsBackContent() async throws {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        let source = fixturesRoot.appendingPathComponent("ReportingEngineProject")
        let tempRoot = makeTempDirectory()
        try FileManager.default.copyItem(at: source, to: tempRoot)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        // Nothing generated yet — the fixture ships with no pre-existing
        // Runtime/Reports content, so any content found after refreshNow()
        // can only have come from the real subprocess this call performs.
        let viewModel = ReportsViewModel(bridge: makeBridge(projectRoot: tempRoot))
        await viewModel.refreshNow()

        XCTAssertNil(viewModel.dailySummaryError)
        XCTAssertNil(viewModel.weeklySummaryError)
        XCTAssertNil(viewModel.duplicateReportError)
        XCTAssertNil(viewModel.storageReportError)

        guard case .structured(let title, let blocks) = viewModel.projection?.dailySummary?.content else {
            return XCTFail("Expected the real subprocess to have written a parseable Daily Summary")
        }
        XCTAssertEqual(title, "Daily Summary — 2026-08-01")
        guard case .table(_, let columns, let rows) = blocks.last else { return XCTFail("Expected a Files table") }
        XCTAssertEqual(columns, ["Original", "New Name", "Destination", "Category", "Confidence", "Tier"])
        XCTAssertEqual(rows, [["invoice.pdf", "Invoice_2026-08-01.pdf", "Finance/Invoices/", "invoice", "97", "auto"]])

        XCTAssertNotNil(viewModel.projection?.weeklySummary)
        XCTAssertNotNil(viewModel.projection?.duplicateReport)
        XCTAssertNotNil(viewModel.projection?.storageReport)
    }
}
