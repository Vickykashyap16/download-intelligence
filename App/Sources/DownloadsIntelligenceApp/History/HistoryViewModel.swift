import Foundation
import EngineBridge

/// Loads History's projection from a real `EngineBridge`. Mirrors
/// `ReviewQueueViewModel`'s own shape (`isLoading`/`errorPresentation`/
/// `projection` as separate `@Published` properties, not a `Phase` enum) —
/// History is architecturally a "load and browse a list" screen like
/// Review Queue, not a multi-step transactional flow like Execute/Undo, so
/// it reuses that closer sibling's pattern rather than the `Phase`-enum
/// pattern those two establish.
///
/// Always performs a fresh read on every call to `refreshNow()` — never
/// caches a stale list across visits (`GUI Engineering Work Packages.md`,
/// WP-GUI-09 Technical Notes: "History must always re-read fresh... since
/// the underlying data may change via direct CLI use as well as GUI use").
/// `AppShell`/`HistoryView` re-create this view model fresh every time
/// `.history` is (re-)selected (`ReviewQueueSectionView`'s own precedent
/// for "always fresh on revisit," `GUI Architecture Specification.md` §7),
/// so a stored view model never goes stale between visits either.
///
/// Undo is deliberately not driven from here — "Undo this batch" from
/// History routes back up to `AppShell`'s own existing `UndoViewModel`/
/// `.sheet` machinery (WP-GUI-08), exactly as it does from Execute's
/// result screen, via a callback this type has no need to own or know
/// about.
@MainActor
public final class HistoryViewModel: ObservableObject {
    @Published public private(set) var projection: HistoryProjection?
    @Published public private(set) var errorPresentation: ErrorPresentation?
    @Published public private(set) var isLoading = true

    private let bridge: EngineBridge

    public init(bridge: EngineBridge) {
        self.bridge = bridge
    }

    /// Performs one fresh read-and-compute cycle: a real `readActionLog()`
    /// and a real `readMetadataStore()`, both re-read every time this is
    /// called — never assumed unchanged from a previous call.
    public func refreshNow() async {
        do {
            let logResult = try await bridge.readActionLog()
            let storeResult = try await bridge.readMetadataStore()
            projection = HistoryProjection.compute(actionLogEntries: logResult.entries, records: storeResult.records)
            errorPresentation = nil
        } catch let error as EngineBridgeError {
            errorPresentation = .forEngineBridgeFailure(error)
        } catch {
            errorPresentation = ErrorPresentation(
                heading: "Something went wrong",
                explanation: "History couldn't load.",
                resolutionActionTitle: "Try again",
                technicalDetail: String(describing: error)
            )
        }
        isLoading = false
    }
}
