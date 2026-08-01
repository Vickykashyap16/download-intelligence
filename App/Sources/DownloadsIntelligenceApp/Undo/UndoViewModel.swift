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

    /// The count shown on the confirmation dialog ("This will move N files
    /// back...") — exposed directly so the view never has to reach into a
    /// non-`.confirming` phase to render its own confirmation copy.
    public var totalToUndo: Int { confirmedRows.count }

    public init(bridge: EngineBridge, confirmedRows: [ExecuteResultProjection.FiledRow]) {
        self.bridge = bridge
        self.confirmedRows = confirmedRows
    }

    /// "Undo this batch": invokes the engine's real `undo --last` under the
    /// mutation guard, then derives the result exclusively from a fresh
    /// action-log re-read.
    ///
    /// Regardless of whether the invocation itself throws — a clean
    /// CLI-level refusal, a subprocess launch failure, or an abnormal
    /// mid-undo termination — this method always proceeds to re-read the
    /// action log and compute the verified result from it, mirroring
    /// `ExecuteViewModel.confirmAndExecute()`'s identical handling for
    /// Execute's own equivalent interruption cases. Only if the action-log
    /// re-read *itself* fails — the one case where no verified outcome can
    /// be determined at all — does this route to `.failed`.
    public func confirmAndUndo() async {
        guard !confirmedRows.isEmpty else {
            phase = .result(UndoResultProjection(totalAttempted: 0, restoredRows: [], problemRows: []))
            return
        }

        phase = .undoing

        _ = try? await bridge.run(.undo(.last))

        do {
            let logResult = try await bridge.readActionLog()
            let result = UndoResultProjection.compute(confirmedRows: confirmedRows, actionLogEntries: logResult.entries)
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
