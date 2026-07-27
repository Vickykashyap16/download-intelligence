import Foundation
import EngineBridge

/// Drives one full `run` invocation end-to-end: reads a baseline, invokes
/// the engine's `run` command in the background, concurrently polls
/// `readMetadataStore()` to derive live progress via the pure
/// `ScanProgress` reducer, and — once `run` completes — computes the final
/// `ScanCompleteProjection` from a fresh read restricted to this scan's own
/// scope.
///
/// Must be owned at a level that survives Sidebar navigation away from
/// whichever screen is currently rendering it — Scan Progress's own layout
/// spec is explicit that "navigating away does not cancel the scan"
/// (`High-Fidelity UI Specification.md` §3) and that "the Sidebar and all
/// other screens remain fully usable while a scan is in progress"
/// (`Desktop Implementation Blueprint.md` §7). `AppShell` owns this as a
/// `@State`, created fresh per scan — mirroring the precedent
/// `AppLifecycleController` already sets as a `@StateObject` living above
/// any individual screen.
///
/// Concurrency: polling `readMetadataStore()` while `run` is still in
/// flight relies on `EngineBridge` being an actor and therefore reentrant
/// at its own `await` suspension points — the same fact
/// `EngineMutationGuard`'s own documentation already establishes ("read-
/// only commands are never serialized against each other or against a
/// running mutation"). This is Finding 4's own conclusion: no
/// `ProcessRunner` or `EngineBridge` change was needed to support live
/// polling during a run.
@MainActor
public final class ScanViewModel: ObservableObject {
    public enum Phase: Equatable {
        case running(ScanProgress.Phase)
        case complete(ScanCompleteProjection)
        case failed(ErrorPresentation)
    }

    @Published public private(set) var phase: Phase = .running(.indeterminate)

    private let bridge: EngineBridge
    private let pollInterval: TimeInterval
    private var pollTask: Task<Void, Never>?
    private var progress: ScanProgress?
    private var hasStarted = false

    /// - Parameter pollInterval: how often to poll `readMetadataStore()`
    ///   while `run` is in flight. Defaults to
    ///   `ScanConfiguration.progressPollInterval`; tests pass a much
    ///   shorter interval against a fixture engine whose own simulated
    ///   stages run in well under a second, the same overridable-interval
    ///   pattern `HomeViewModel.startPeriodicRefresh(interval:)` already
    ///   establishes for Home's periodic refresh.
    public init(bridge: EngineBridge, pollInterval: TimeInterval = ScanConfiguration.progressPollInterval) {
        self.bridge = bridge
        self.pollInterval = pollInterval
    }

    deinit {
        pollTask?.cancel()
    }

    /// Runs the scan exactly once per `ScanViewModel` instance. A second
    /// call — e.g. from a SwiftUI `.task` re-invoking after a view identity
    /// change — is a no-op rather than starting a second, concurrent `run`
    /// (which the single-mutation-slot rule would refuse anyway); callers
    /// that want to run a further scan construct a fresh `ScanViewModel`,
    /// exactly as `AppShell` does for "Scan again."
    public func start() async {
        guard !hasStarted else { return }
        hasStarted = true

        let baselineRecords: [FileRecordSnapshot]
        do {
            baselineRecords = try await bridge.readMetadataStore().records
        } catch {
            phase = .failed(Self.failurePresentation(error))
            return
        }

        let startingProgress = ScanProgress.starting(baseline: baselineRecords)
        progress = startingProgress
        phase = .running(startingProgress.phase)

        pollTask = Task { [weak self, pollInterval] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(pollInterval * 1_000_000_000))
                guard !Task.isCancelled else { return }
                await self?.pollOnce()
            }
        }

        do {
            _ = try await bridge.run(.run)
            pollTask?.cancel()
            pollTask = nil
            await finish(baselineRecords: baselineRecords)
        } catch {
            pollTask?.cancel()
            pollTask = nil
            phase = .failed(Self.failurePresentation(error))
        }
    }

    private func pollOnce() async {
        guard let records = try? await bridge.readMetadataStore().records else { return }
        let updated = progress?.next(records: records)
        progress = updated
        if let updated {
            phase = .running(updated.phase)
        }
    }

    /// Computes the final Scan Complete projection from a fresh read taken
    /// once `run` has genuinely finished — independent of whatever the live
    /// polling loop happened to last observe, so a poll landing at an
    /// unlucky moment can never leave Scan Complete showing a stale result.
    private func finish(baselineRecords: [FileRecordSnapshot]) async {
        let finalRecords: [FileRecordSnapshot]
        do {
            finalRecords = try await bridge.readMetadataStore().records
        } catch {
            phase = .failed(Self.failurePresentation(error))
            return
        }

        let baselineFileIDs = Set(baselineRecords.map(\.fileID))
        let baselinePendingFileIDs = Set(baselineRecords.filter { $0.tier == nil }.map(\.fileID))
        let scope = ScanProgress.scope(
            baselineFileIDs: baselineFileIDs,
            baselinePendingFileIDs: baselinePendingFileIDs,
            currentRecords: finalRecords
        )
        phase = .complete(.compute(records: finalRecords, scope: scope))
    }

    private static func failurePresentation(_ error: Error) -> ErrorPresentation {
        if let bridgeError = error as? EngineBridgeError {
            return .forEngineBridgeFailure(bridgeError)
        }
        return ErrorPresentation(
            heading: "Something went wrong",
            explanation: "The scan couldn't finish.",
            resolutionActionTitle: nil,
            technicalDetail: String(describing: error)
        )
    }
}
