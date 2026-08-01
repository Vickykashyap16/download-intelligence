import Foundation
import EngineBridge

/// Loads Reports' projection from a real `EngineBridge`. Diverges from
/// `HistoryViewModel`/`ReviewQueueViewModel`'s own `isLoading`/
/// `errorPresentation`/`projection` shape in one deliberate, disclosed way:
/// **there is no whole-screen `errorPresentation` here.** Hi-Fi §11 States
/// specifies Reports' only error behavior as "if a specific report fails to
/// generate/load, this is shown as a plain message within that sub-view
/// only, without affecting the other three" — no full-screen Reports error
/// state exists anywhere in the source documents (unlike History/Review
/// Queue, whose whole screen replaces itself with `ErrorStateView` on
/// failure). Reports' four artifacts are read independently for exactly
/// this reason, each with its own captured outcome in its own named
/// `*Error` property below — a failure reading one never prevents the
/// other three from rendering. Four explicit named properties, not a
/// `[ReportKind: ErrorPresentation]` dictionary, deliberately: `ReportKind`
/// (`EngineBridge`'s own type, frozen, WP-GUI-00) is `Equatable` but not
/// `Hashable`, and this package never modifies `EngineBridge` to add a
/// conformance it doesn't already have — `ReportsProjection` itself already
/// establishes the same four-named-properties shape over a dictionary for
/// its own four report slots, so this mirrors that precedent rather than
/// introducing a second one.
///
/// **Report-generation trigger (WP-GUI-10, verified against `Desktop
/// Implementation Blueprint.md` §7's "Report Generation runs as a
/// low-priority background operation... the Reports screen simply shows a
/// brief loading state while it completes," and `src/main.py`'s own
/// `report()` docstring confirming nothing else in the engine ever
/// regenerates reports automatically): `refreshNow()` invokes the engine's
/// real `report` command exactly once per call** — regenerating all four
/// report types in the single existing CLI invocation (there is no CLI
/// capability to regenerate just one type) — **never per sub-view
/// selection.** Switching which of the four reports is currently displayed
/// is `ReportsView`'s own local, synchronous selection state; it never
/// triggers another read or another `report` invocation.
///
/// **No optimistic success (`UndoViewModel`/`HistoryViewModel`'s own
/// established discipline, applied here too):** `bridge.run(.report)`'s own
/// thrown error, if any — including a clean refusal via
/// `EngineBridgeError.anotherMutatingOperationInProgress` when Scan/
/// Execute/Undo already holds the single mutation slot — is deliberately
/// **not** surfaced as an error at all. Per `Desktop Implementation
/// Blueprint.md` §9 Edge Cases (Reports), "a report generation interrupted
/// mid-write should never leave a corrupted or half-written report visible
/// — the prior valid report remains shown until a new one successfully
/// completes," so whether generation itself succeeded is never the
/// question; the four artifact re-reads that always follow are the sole
/// source of truth for what Reports actually shows, exactly as Execute,
/// Undo, and History already establish.
@MainActor
public final class ReportsViewModel: ObservableObject {
    @Published public private(set) var projection: ReportsProjection?
    @Published public private(set) var dailySummaryError: ErrorPresentation?
    @Published public private(set) var weeklySummaryError: ErrorPresentation?
    @Published public private(set) var duplicateReportError: ErrorPresentation?
    @Published public private(set) var storageReportError: ErrorPresentation?
    @Published public private(set) var isLoading = true

    private let bridge: EngineBridge

    public init(bridge: EngineBridge) {
        self.bridge = bridge
    }

    /// Performs one fresh generate-then-read cycle: a real, tolerated-if-it-
    /// fails `report` invocation, followed by four independent, always-
    /// attempted artifact re-reads — never assumed unchanged from a
    /// previous call, never gated on the invocation's own success.
    public func refreshNow() async {
        _ = try? await bridge.run(.report)

        let dailySummaryResult = await readReport { try await self.bridge.readLatestDailySummary() }
        dailySummaryError = dailySummaryResult.error

        let weeklySummaryResult = await readReport { try await self.bridge.readLatestWeeklySummary() }
        weeklySummaryError = weeklySummaryResult.error

        let duplicateReportResult = await readReport { try await self.bridge.readDuplicateReport() }
        duplicateReportError = duplicateReportResult.error

        let storageReportResult = await readReport { try await self.bridge.readStorageReport() }
        storageReportError = storageReportResult.error

        projection = ReportsProjection.compute(
            dailySummary: dailySummaryResult.content,
            weeklySummary: weeklySummaryResult.content,
            duplicateReport: duplicateReportResult.content,
            storageReport: storageReportResult.content
        )
        isLoading = false
    }

    /// Runs one artifact read in isolation — a thrown error here never
    /// propagates to the other three reads, and never clears a different
    /// report type's already-good content.
    private func readReport(_ body: () async throws -> ReportContent?) async -> (content: ReportContent?, error: ErrorPresentation?) {
        do {
            let content = try await body()
            return (content, nil)
        } catch let error as EngineBridgeError {
            return (nil, .forEngineBridgeFailure(error, layout: .inline))
        } catch {
            let presentation = ErrorPresentation(
                heading: "Something went wrong",
                explanation: "This report couldn't load.",
                resolutionActionTitle: "Try again",
                technicalDetail: String(describing: error),
                layout: .inline
            )
            return (nil, presentation)
        }
    }
}
