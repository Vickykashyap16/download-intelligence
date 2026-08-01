import Foundation
import EngineBridge

/// Loads Review Detail's projection for one specific `fileID` from a real
/// `EngineBridge` — its own independent fresh read, exactly like every
/// other screen's own view model (`GUI Architecture Specification.md` §7),
/// rather than reusing whatever `ReviewQueueProjection` the list already
/// has in memory. Review Detail's content needs (the full
/// `confidenceBreakdown`) go beyond what `ReviewQueueProjection.NeedsInputItem`/
/// `FlaggedItem` carry, so a separate read-and-compute step is required
/// regardless.
///
/// Approve/Reject decisions made from Detail are **not** recorded here —
/// this type has no `decide` method of its own. Because Detail is state
/// nested *under* Review Queue (`GUI Architecture Specification.md` line
/// 99), a decision made here must land in the exact same session-local
/// `decisions` dictionary the list itself reads from, so the two screens
/// never disagree about what's already been decided this session. The
/// owning view therefore calls back into the same, already-hoisted
/// `ReviewQueueViewModel.decide(_:for:)` the list uses, then dismisses this
/// screen ("Back to queue" is a local state transition, `GUI Architecture
/// Specification.md` line 102) — this type exists purely to load and
/// display one file's detail, not to own any decision state.
@MainActor
public final class ReviewDetailViewModel: ObservableObject {
    @Published public private(set) var projection: ReviewDetailProjection?
    @Published public private(set) var errorPresentation: ErrorPresentation?
    @Published public private(set) var isLoading = true
    /// `true` once a fresh read completed successfully but found no record
    /// at all for `fileID` — a genuine, if rare, race (e.g. a re-scan
    /// removed it) distinct from a transient read failure.
    @Published public private(set) var recordNotFound = false

    private let bridge: EngineBridge
    public let fileID: String

    public init(bridge: EngineBridge, fileID: String) {
        self.bridge = bridge
        self.fileID = fileID
    }

    public func refreshNow() async {
        do {
            let result = try await bridge.readMetadataStore()
            if let computed = ReviewDetailProjection.compute(records: result.records, fileID: fileID) {
                projection = computed
                recordNotFound = false
            } else {
                projection = nil
                recordNotFound = true
            }
            errorPresentation = nil
        } catch let error as EngineBridgeError {
            errorPresentation = .forEngineBridgeFailure(error)
        } catch {
            errorPresentation = ErrorPresentation(
                heading: "Something went wrong",
                explanation: "This item's details couldn't load.",
                resolutionActionTitle: "Try again",
                technicalDetail: String(describing: error)
            )
        }
        isLoading = false
    }
}
