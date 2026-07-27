import XCTest
import EngineBridge
// Scoped import: resolves this one declaration by its exact module path,
// disambiguating it from XCTest's own colliding top-level `Category` symbol
// (only a problem in files that import both XCTest and EngineBridge —
// `EngineBridge.Category` is used bare, without conflict, everywhere else
// in this codebase). This is a different resolution mechanism from ordinary
// qualified-name lookup, so it isn't affected by `EngineBridge` also being
// the name of a type (the `EngineBridge` actor) declared inside this same
// module.
import enum EngineBridge.Category
@testable import DownloadsIntelligenceApp

final class ScanProgressTests: XCTestCase {

    // MARK: - Fixture helpers

    private func makeRecord(
        fileID: String,
        category: Category? = nil,
        suggestedName: String? = nil,
        tier: Tier? = nil
    ) -> FileRecordSnapshot {
        FileRecordSnapshot(
            fileID: fileID,
            sourceID: "downloads",
            originalName: "\(fileID).pdf",
            originalPath: "/Users/fixture/Downloads/\(fileID).pdf",
            currentPath: "/Users/fixture/Downloads/\(fileID).pdf",
            fileExtension: ".pdf",
            mimeType: "application/pdf",
            sizeBytes: 1024,
            createdAt: "2026-07-26T10:00:00Z",
            modifiedAt: "2026-07-26T10:00:00Z",
            contentHash: "hash-\(fileID)",
            discoveredAt: "2026-07-26T10:00:00Z",
            category: category,
            suggestedName: suggestedName,
            tier: tier
        )
    }

    // MARK: - Starting state

    func test_starting_isAlwaysIndeterminate_regardlessOfBaselineContent() {
        XCTAssertEqual(ScanProgress.starting(baseline: []).phase, .indeterminate)
        XCTAssertEqual(
            ScanProgress.starting(baseline: [makeRecord(fileID: "1", tier: .auto)]).phase,
            .indeterminate
        )
    }

    // MARK: - Staying indeterminate until a real signal exists

    func test_next_scanStillWalking_noNewRecordsYet_staysIndeterminate() {
        let progress = ScanProgress.starting(baseline: [])
        let next = progress.next(records: [])
        XCTAssertEqual(next.phase, .indeterminate)
    }

    func test_next_newRecordsDiscoveredButNotYetClassified_staysIndeterminate() {
        // scan()'s append burst has landed (new file_ids exist) but
        // classify() hasn't started yet — no marker has moved, so this must
        // still read as indeterminate, not a premature "0 of 3."
        let progress = ScanProgress.starting(baseline: [])
        let next = progress.next(records: [makeRecord(fileID: "1"), makeRecord(fileID: "2"), makeRecord(fileID: "3")])
        XCTAssertEqual(next.phase, .indeterminate)
    }

    // MARK: - Transitioning to determinate on the first real signal

    func test_next_firstCategoryAssigned_transitionsToDeterminate_withCorrectScope() {
        let progress = ScanProgress.starting(baseline: [])
        let next = progress.next(records: [
            makeRecord(fileID: "1", category: .invoice),
            makeRecord(fileID: "2"),
            makeRecord(fileID: "3"),
        ])
        XCTAssertEqual(next.phase, .determinate(DeterminateProgress(completed: 0, total: 3)))
    }

    func test_next_someRecordsAlreadyTiered_progressReflectsCompletedCount() {
        let progress = ScanProgress.starting(baseline: [])
        let next = progress.next(records: [
            makeRecord(fileID: "1", category: .invoice, suggestedName: "a.pdf", tier: .auto),
            makeRecord(fileID: "2", category: .invoice),
            makeRecord(fileID: "3"),
        ])
        XCTAssertEqual(next.phase, .determinate(DeterminateProgress(completed: 1, total: 3)))
    }

    func test_next_allRecordsTiered_reportsFullCompletion() {
        let progress = ScanProgress.starting(baseline: [])
        let next = progress.next(records: [
            makeRecord(fileID: "1", category: .invoice, suggestedName: "a.pdf", tier: .auto),
            makeRecord(fileID: "2", category: .resume, suggestedName: "b.pdf", tier: .reviewRequired),
        ])
        XCTAssertEqual(next.phase, .determinate(DeterminateProgress(completed: 2, total: 2)))
    }

    // MARK: - Scope stays fixed once known, even as later polls advance

    func test_scope_remainsFixed_asSubsequentPollsAdvanceCompletion() {
        var progress = ScanProgress.starting(baseline: [])
        progress = progress.next(records: [makeRecord(fileID: "1", category: .invoice), makeRecord(fileID: "2")])
        XCTAssertEqual(progress.phase, .determinate(DeterminateProgress(completed: 0, total: 2)))

        progress = progress.next(records: [
            makeRecord(fileID: "1", category: .invoice, suggestedName: "a.pdf", tier: .auto),
            makeRecord(fileID: "2", category: .document, suggestedName: "b.pdf", tier: .approvalRequired),
        ])
        XCTAssertEqual(progress.phase, .determinate(DeterminateProgress(completed: 2, total: 2)))
    }

    // MARK: - Each of the three markers independently triggers the transition

    func test_next_suggestedNameAloneAdvancing_stillTriggersTransition() {
        // Simulates a record already classified in a prior, interrupted
        // run (category already set at baseline) where only naming moves
        // in this run.
        let baseline = [makeRecord(fileID: "1", category: .invoice)]
        let progress = ScanProgress.starting(baseline: baseline)
        let next = progress.next(records: [makeRecord(fileID: "1", category: .invoice, suggestedName: "a.pdf")])
        XCTAssertEqual(next.phase, .determinate(DeterminateProgress(completed: 0, total: 1)))
    }

    func test_next_tierAloneAdvancing_stillTriggersTransition() {
        let baseline = [makeRecord(fileID: "1", category: .invoice, suggestedName: "a.pdf")]
        let progress = ScanProgress.starting(baseline: baseline)
        let next = progress.next(records: [makeRecord(fileID: "1", category: .invoice, suggestedName: "a.pdf", tier: .auto)])
        XCTAssertEqual(next.phase, .determinate(DeterminateProgress(completed: 1, total: 1)))
    }

    // MARK: - Baseline-pending (stale, previously interrupted) records are in scope

    func test_scope_includesBaselinePendingRecords_evenWithNoNewDiscoveries() {
        // A record left over, untiered, from a previously interrupted run;
        // this scan discovers nothing new in the source folder, but the
        // leftover record still legitimately advances during this run.
        let baseline = [makeRecord(fileID: "stale", category: .invoice)]
        let progress = ScanProgress.starting(baseline: baseline)
        let next = progress.next(records: [makeRecord(fileID: "stale", category: .invoice, suggestedName: "a.pdf")])
        XCTAssertEqual(next.phase, .determinate(DeterminateProgress(completed: 0, total: 1)))
    }

    // MARK: - Already-completed baseline records are excluded from scope

    func test_scope_excludesRecordsAlreadyTieredAtBaseline() {
        // A record fully processed by a previous scan must not inflate this
        // scan's own denominator, and must not be double-counted as newly
        // "completed" by this run.
        let baseline = [
            makeRecord(fileID: "old", category: .invoice, suggestedName: "old.pdf", tier: .auto),
        ]
        let progress = ScanProgress.starting(baseline: baseline)
        let next = progress.next(records: [
            makeRecord(fileID: "old", category: .invoice, suggestedName: "old.pdf", tier: .auto),
            makeRecord(fileID: "new", category: .resume),
        ])
        XCTAssertEqual(next.phase, .determinate(DeterminateProgress(completed: 0, total: 1)))
    }

    // MARK: - Empty scope (idempotent re-run, nothing pending, nothing new)

    func test_scope_canBeEmpty_whenEverythingWasAlreadyDone() {
        // markerCount cannot advance beyond baseline if nothing changes —
        // this exercises that a completely idempotent re-run simply never
        // leaves .indeterminate, which is the correct, honest outcome
        // (the run subprocess will exit almost immediately in this case).
        let baseline = [makeRecord(fileID: "old", category: .invoice, suggestedName: "old.pdf", tier: .auto)]
        let progress = ScanProgress.starting(baseline: baseline)
        let next = progress.next(records: baseline)
        XCTAssertEqual(next.phase, .indeterminate)
    }
}
