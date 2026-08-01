import Foundation
import EngineBridge

/// Drives Undo end-to-end: invokes the engine's real `undo --last` command
/// under the existing single-mutation-slot guard, and derives the result
/// exclusively from a post-invocation re-read of the action log — the same
/// "always re-read, never infer from the invocation's own outcome"
/// discipline `ExecuteViewModel.confirmAndExecute()` already establishes
/// (`WP-GUI-08` Technical Notes: "use action-log re-reading as the sole
/// source of truth after undo; never infer success from the command
/// result").
///
/// Undo's batch is not independently re-derived from a fresh engine query
/// the way Execute's confirmation batch is — the batch being undone *is*
/// the batch Execute just reported as filed (`ExecuteResultProjection`'s
/// own `filedRows`), so it is seeded once, at construction, from that
/// already-verified in-memory result. `undo --last` (`EngineCommand
/// .undo(.last)`) targets the most recent batch across the entire action
/// log by timestamp (`src/cli.py`'s `_most_recent_batch_id_from_entries()`)
/// — since this view model is only ever constructed immediately after an
/// Execute result is on screen, with no other mutating engine call able to
/// occur in between (`EngineMutationGuard`'s single-slot rule), "most
/// recent batch" and "the batch just filed" are the same batch.
///
/// `target` (added by WP-GUI-09) generalizes this to History's second
/// entry point, which can trigger Undo against *any* past batch, not only
/// the most recent one — `EngineCommand.undo(.batchID(String))` already
/// maps to the CLI's own `undo <batch_id>` positional argument (no engine
/// change needed; see `Open Dependencies.md` OD-GUI-4 for the one Undo
/// capability that genuinely doesn't exist yet — per-file undo, which
/// remains out of scope here). Defaults to `.last`, preserving WP-GUI-08's
/// original, tested behavior exactly for the Execute-result entry point,
/// which never passes this parameter explicitly.
///
/// Owned by `AppShell` as `@State`, created fresh at the moment "Undo this
/// batch" is pressed — the same per-visit ownership pattern
/// `ExecuteViewModel` already establishes.
@MainActor
public final class UndoViewModel: ObservableObject {
    public enum Phase: Equatable {
        case confirming
        case undoing
        case result(UndoResultProjection)
        case failed(ErrorPresentation)
    }

    @Published public private(set) var phase: Phase = .confirming

    private let bridge: EngineBridge
    private let confirmedRows: [ExecuteResultProjection.FiledRow]
    private let target: EngineCommand.UndoTarget

    /// The count shown on the confirmation dialog ("This will move N files
    /// back...") — exposed directly so the view never has to reach into a
    /// non-`.confirming` phase to render its own confirmation copy.
    public var totalToUndo: Int { confirmedRows.count }

    public init(
        bridge: EngineBridge,
        confirmedRows: [ExecuteResultProjection.FiledRow],
        target: EngineCommand.UndoTarget = .last
    ) {
        self.bridge = bridge
        self.confirmedRows = confirmedRows
        self.target = target
    }

    /// "Undo this batch": invokes the engine's real `undo` command (`--last`
    /// or a specific `batch_id`, per `target`) under the mutation guard,
    /// then derives the result exclusively from a fresh action-log re-read.
    ///
    /// Regardless of whether the invocation itself throws — a clean
    /// CLI-level refusal, a subprocess launch failure, or an abnormal
    /// mid-undo termination — this method always proceeds to re-read the
    /// action log and compute the verified result from it, mirroring
    /// `ExecuteViewModel.confirmAndExecute()`'s identical handling for
    /// Execute's own equivalent interruption cases. Only if the action-log
    /// re-read *itself* fails — the one case where no verified outcome can
    /// be determined at all — does this route to `.failed`.
    ///
    /// For `.batchID(id)` specifically, the re-read entries are filtered to
    /// that `batchID` before being handed to `UndoResultProjection.compute
    /// (confirmedRows:actionLogEntries:)`, which otherwise reconciles by
    /// `fileID` alone — correct for `.last`, where the batch just executed
    /// is definitionally the only recent activity for those exact
    /// `fileID`s, but not provably safe in general for an arbitrary
    /// historical batch a `fileID` could in principle have participated in
    /// more than once across the product's lifetime. Filtering here keeps
    /// that guarantee correct for History's own entry point without
    /// touching `UndoResultProjection` itself, and without changing
    /// `.last`'s own computation in any way — the exact same entries this
    /// method has always handed to `compute(_:_:)` reach it unfiltered
    /// whenever `target == .last`.
    public func confirmAndUndo() async {
        guard !confirmedRows.isEmpty else {
            phase = .result(UndoResultProjection(totalAttempted: 0, restoredRows: [], problemRows: []))
            return
        }

        phase = .undoing

        _ = try? await bridge.run(.undo(target))

        do {
            let logResult = try await bridge.readActionLog()
            let relevantEntries: [ActionLogEntry]
            if case .batchID(let id) = target {
                relevantEntries = logResult.entries.filter { $0.batchID == id }
            } else {
                relevantEntries = logResult.entries
            }
            let result = UndoResultProjection.compute(confirmedRows: confirmedRows, actionLogEntries: relevantEntries)
            phase = .result(result)
        } catch let error as EngineBridgeError {
            phase = .failed(.forEngineBridgeFailure(error))
        } catch {
            phase = .failed(Self.genericFailure(error))
        }
    }

    private static func genericFailure(_ error: Error) -> ErrorPresentation {
        ErrorPresentation(
            heading: "Something went wrong",
            explanation: "Undo couldn't finish.",
            resolutionActionTitle: nil,
            technicalDetail: String(describing: error)
        )
    }
}
