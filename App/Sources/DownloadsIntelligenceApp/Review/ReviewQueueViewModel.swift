import Foundation
import EngineBridge

/// Loads Review Queue's projection from a real `EngineBridge` and manages
/// every decision (Approve/Reject) as **session-local, in-memory state
/// only** — this type never calls `bridge.run(...)` for a decision, and
/// never will, per the confirmed architecture: `Desktop Implementation
/// Blueprint.md` §5's own Execute request flow describes confirming Execute
/// as invoking the engine "for the already-determined batch (the auto-tier
/// batch, plus any items freshly approved through Review Queue/Review
/// Detail **in the same session**)" — "in the same session" is explicit
/// that these decisions live only in the GUI's memory until Execute
/// (WP-GUI-07, out of scope here) actually runs. There is no `approve`,
/// `reject`, or `reclassify` verb anywhere in `EngineCommand` to invoke even
/// if this type wanted to.
///
/// A decision never mutates `metadata_store.json`, so there is no partial-
/// write hazard an app-quit-mid-decision could ever produce (`High-Fidelity
/// UI Specification.md` §5's own "unexpected interruption mid-decision"
/// edge case resolves trivially this way: nothing was ever written, so a
/// relaunch always shows the record exactly as it was).
///
/// `decisions` is exposed (read-only) specifically so a future WP-GUI-07
/// can consume "items freshly approved... in the same session" without this
/// type needing to build that hand-off itself — WP-GUI-06's own scope ends
/// at "collect the decision," not "act on it."
@MainActor
public final class ReviewQueueViewModel: ObservableObject {
    public enum Decision: Equatable, Sendable {
        case approved
        case rejected
    }

    @Published public private(set) var projection: ReviewQueueProjection?
    @Published public private(set) var errorPresentation: ErrorPresentation?
    @Published public private(set) var isLoading = true
    @Published public private(set) var decisions: [String: Decision] = [:]

    private let bridge: EngineBridge

    public init(bridge: EngineBridge) {
        self.bridge = bridge
    }

    /// Performs one fresh read-and-compute cycle. Deliberately does **not**
    /// reset `decisions` — a manual "try again" after a transient read
    /// failure must not silently discard decisions the user already made
    /// this session.
    public func refreshNow() async {
        do {
            let result = try await bridge.readMetadataStore()
            projection = ReviewQueueProjection.compute(records: result.records)
            errorPresentation = nil
        } catch let error as EngineBridgeError {
            errorPresentation = .forEngineBridgeFailure(error)
        } catch {
            errorPresentation = ErrorPresentation(
                heading: "Something went wrong",
                explanation: "Review Queue couldn't load its current items.",
                resolutionActionTitle: "Try again",
                technicalDetail: String(describing: error)
            )
        }
        isLoading = false
    }

    /// The "Needs your input" items still awaiting a decision this session
    /// — every item from the last fresh read minus whatever already
    /// received a local decision. `projection` itself is never mutated in
    /// place, so a future `refreshNow()` can always recompute cleanly from
    /// a genuinely fresh read.
    public var visibleNeedsInputItems: [ReviewQueueProjection.NeedsInputItem] {
        (projection?.needsInputItems ?? []).filter { decisions[$0.fileID] == nil }
    }

    /// "Flagged for you" items — Reclassify does not remove a card from
    /// this list (see `ReviewCardView`'s own documentation for why: it has
    /// no real backing engine capability yet and is an inert stub), so this
    /// list is unaffected by `decisions` in practice today, but is filtered
    /// identically to `visibleNeedsInputItems` for forward consistency if a
    /// future work package ever makes Reclassify a real, list-clearing
    /// decision.
    public var visibleFlaggedItems: [ReviewQueueProjection.FlaggedItem] {
        (projection?.flaggedItems ?? []).filter { decisions[$0.fileID] == nil }
    }

    /// Records `decision` for `fileID` and returns the file ID focus should
    /// move to next: the next remaining item in the same group `fileID`
    /// belonged to, or `nil` if none remains (`High-Fidelity UI
    /// Specification.md` §5 Accessibility: "focus moves to the next
    /// remaining card... never being lost or reset to the top of the
    /// list"). A no-op (returns `nil`) for a `fileID` not currently visible
    /// — already decided, or never part of either group — the same
    /// idempotent-call safety `ScanViewModel.start()` already establishes
    /// for its own single-invocation guarantee.
    @discardableResult
    public func decide(_ decision: Decision, for fileID: String) -> String? {
        for ids in [visibleNeedsInputItems.map(\.fileID), visibleFlaggedItems.map(\.fileID)] {
            guard let index = ids.firstIndex(of: fileID) else { continue }
            decisions[fileID] = decision
            let remaining = ids.filter { $0 != fileID }
            guard !remaining.isEmpty else { return nil }
            return index < remaining.count ? remaining[index] : remaining[remaining.count - 1]
        }
        return nil
    }
}
