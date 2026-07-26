import Foundation
import EngineBridge

/// Loads and periodically refreshes Home's projection from a real
/// `EngineBridge` — the one piece of WP-GUI-03 that actually talks to the
/// Engine Bridge, exactly mirroring how `AppLifecycleController` was the
/// one piece of WP-GUI-01 that did so. Home reads independently of the
/// lifecycle controller's own best-effort metadata read (`Desktop
/// Implementation Blueprint.md` §3's "every projection re-read rather than
/// carried forward"), never reusing whatever the lifecycle controller
/// happened to read at startup.
///
/// `@MainActor` because `projection`/`errorPresentation`/`isLoading` drive
/// SwiftUI view state directly.
@MainActor
public final class HomeViewModel: ObservableObject {
    @Published public private(set) var projection: HomeProjection?
    @Published public private(set) var errorPresentation: ErrorPresentation?
    @Published public private(set) var isLoading = true

    private let bridge: EngineBridge
    private let now: () -> Date
    private var refreshTask: Task<Void, Never>?

    /// - Parameters:
    ///   - bridge: the real (or fixture-backed) Engine Bridge to read from.
    ///   - now: how the current instant is obtained, injected so tests can
    ///     supply a fixed clock and get deterministic weekly-window/recency
    ///     results against fixture timestamps, exactly as
    ///     `HomeProjection.compute(records:now:)` itself is tested.
    public init(bridge: EngineBridge, now: @escaping () -> Date = Date.init) {
        self.bridge = bridge
        self.now = now
    }

    deinit {
        refreshTask?.cancel()
    }

    /// Performs one fresh read-and-compute cycle. Called both for the
    /// initial load (on Home's arrival) and by the periodic refresh loop
    /// below — there is exactly one code path for "get the current
    /// projection," matching `Desktop Implementation Blueprint.md` §3's
    /// "no separate code path" principle.
    public func refreshNow() async {
        do {
            let result = try await bridge.readMetadataStore()
            projection = HomeProjection.compute(records: result.records, now: now())
            errorPresentation = nil
        } catch let error as EngineBridgeError {
            // "Error: source or destination folder unreachable — routes to
            // the Error Screen pattern" (`High-Fidelity UI Specification.md`
            // §2). Home keeps whatever projection it last had rather than
            // discarding it — a transient read failure during periodic
            // refresh must not blank out a screen that was showing
            // perfectly good data a moment ago; only the initial load (
            // where `projection` is still `nil`) actually surfaces as a
            // full Error State to the view.
            errorPresentation = .forEngineBridgeFailure(error)
        } catch {
            errorPresentation = ErrorPresentation(
                heading: "Something went wrong",
                explanation: "Home couldn't load its current status.",
                resolutionActionTitle: "Try again",
                technicalDetail: String(describing: error)
            )
        }
        isLoading = false
    }

    /// Starts the periodic status refresh Home's steady state requires
    /// (`Desktop Implementation Blueprint.md` §2, Idle phase: "refreshing
    /// Home's status on a modest periodic interval"). The default interval
    /// is `HomeConfiguration.defaultRefreshInterval`; callers (tests, in
    /// particular) may pass a much shorter interval to observe re-polling
    /// without a real 30-second wait.
    ///
    /// Calling this again while already running restarts the loop rather
    /// than stacking a second one, so a view's `.task` re-invocation (e.g.
    /// after a SwiftUI view identity change) can never leave two refresh
    /// loops running concurrently against the same view model.
    public func startPeriodicRefresh(interval: TimeInterval = HomeConfiguration.defaultRefreshInterval) {
        refreshTask?.cancel()
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
                guard !Task.isCancelled else { return }
                await self?.refreshNow()
            }
        }
    }

    public func stopPeriodicRefresh() {
        refreshTask?.cancel()
        refreshTask = nil
    }
}
