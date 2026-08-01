import Foundation
import EngineBridge

/// Drives Execute end-to-end: loads the confirmation batch from a fresh
/// metadata-store read, performs one more fresh read immediately before
/// invoking the engine (`WP-GUI-07` Technical Notes: "the confirmation
/// screen must perform one more fresh read before allowing 'File them'",
/// `Desktop Implementation Blueprint.md` §3), invokes the engine's real,
/// non-interactive `execute -y` command under the existing single-mutation-
/// slot guard, and derives the result exclusively from a post-invocation
/// re-read of the action log.
///
/// Scoped to the engine's actual auto-tier execution set only — the
/// confirmation batch is never mixed with freshly-approved
/// `approval_required` items from Review Queue, and this type never
/// attempts to supply approval decisions to `execute` in any way. That
/// capability does not exist in the engine today (`Downloads Intelligence —
/// UX Design/Open Dependencies.md`, OD-GUI-3) — it is a documented future
/// engine capability, not something this work package works around.
///
/// Must be owned at a level that survives Sidebar navigation away from
/// whichever screen is currently rendering it, exactly like `ScanViewModel`
/// — Execute is a real, physical file operation running as a background
/// subprocess, and `Desktop Implementation Blueprint.md` §7 is explicit
/// that navigating away is discouraged but never technically blocked, so
/// the in-flight invocation must not be silently abandoned by a Sidebar
/// click. `AppShell` owns this as a `@State`, created fresh per Execute
/// visit — the same ownership pattern `ScanViewModel` already establishes.
///
/// Deliberately holds no extra concurrency bookkeeping of its own: the
/// single-mutation-slot rule is already fully enforced by
/// `EngineMutationGuard` inside `EngineBridge.run(_:)` (WP-GUI-00) — this
/// type only needs to avoid starting a second engine-mutating call
/// concurrently with its own, which its single, sequential `await` chain in
/// `confirmAndExecute()` already guarantees.
@MainActor
public final class ExecuteViewModel: ObservableObject {
    public enum Phase: Equatable {
        case loadingConfirmation
        case confirming(ExecuteConfirmationProjection)
        /// The fresh, pre-commit re-read (or the very first load) found no
        /// eligible auto-tier batch — `High-Fidelity UI Specification.md`
        /// §8 States: "Empty: not applicable — this screen is only reached
        /// when there is a non-zero auto-tier batch to confirm," honored
        /// here defensively for the one case that statement doesn't quite
        /// rule out on its own: the batch changing out from under a
        /// confirmation screen already on display.
        case nothingToFile
        case executing
        case result(ExecuteResultProjection)
        case failed(ErrorPresentation)
    }

    @Published public private(set) var phase: Phase = .loadingConfirmation

    private let bridge: EngineBridge

    public init(bridge: EngineBridge) {
        self.bridge = bridge
    }

    /// Performs the initial fresh read that populates the confirmation
    /// screen. Callers (`ExecuteFlowView`) invoke this once, from their own
    /// `.task`, mirroring `PreviewViewModel.refreshNow()`'s "one fresh read
    /// per visit" discipline.
    public func loadConfirmation() async {
        do {
            let records = try await bridge.readMetadataStore().records
            let projection = ExecuteConfirmationProjection.compute(records: records)
            phase = projection.fileRows.isEmpty ? .nothingToFile : .confirming(projection)
        } catch let error as EngineBridgeError {
            phase = .failed(.forEngineBridgeFailure(error))
        } catch {
            phase = .failed(Self.genericFailure(error))
        }
    }

    /// "File them": performs one more fresh read to re-verify the batch
    /// (per `Desktop Implementation Blueprint.md` §3), then invokes the
    /// engine's real `execute -y` under the mutation guard, then derives
    /// the result exclusively from a fresh action-log re-read.
    ///
    /// Regardless of whether the invocation itself throws — a clean
    /// CLI-level refusal, a subprocess launch failure, or an abnormal
    /// mid-execute termination — this method always proceeds to re-read the
    /// action log and compute the verified result from it, never routing
    /// straight to a generic failure screen on the invocation's own outcome
    /// alone. This is the concrete mechanism behind `Desktop Implementation
    /// Blueprint.md` §8's "Unexpected crash"/"Interrupted execute"
    /// handling: "the GUI never infers success from this — it immediately
    /// re-reads the action log... to determine the true, verified outcome,"
    /// which may honestly turn out to be full success, partial success, or
    /// nothing filed at all, exactly as the log itself shows. Only if the
    /// action-log re-read *itself* fails — the one case where no verified
    /// outcome can be determined at all — does this route to `.failed`.
    public func confirmAndExecute() async {
        let freshRecords: [FileRecordSnapshot]
        do {
            freshRecords = try await bridge.readMetadataStore().records
        } catch let error as EngineBridgeError {
            phase = .failed(.forEngineBridgeFailure(error))
            return
        } catch {
            phase = .failed(Self.genericFailure(error))
            return
        }

        let freshProjection = ExecuteConfirmationProjection.compute(records: freshRecords)
        guard !freshProjection.fileRows.isEmpty else {
            phase = .nothingToFile
            return
        }

        let confirmedRows = freshProjection.fileRows
        phase = .executing

        _ = try? await bridge.run(.execute(yes: true, debug: false))

        do {
            let logResult = try await bridge.readActionLog()
            let result = ExecuteResultProjection.compute(confirmedRows: confirmedRows, actionLogEntries: logResult.entries)
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
            explanation: "Execute couldn't finish.",
            resolutionActionTitle: nil,
            technicalDetail: String(describing: error)
        )
    }
}
