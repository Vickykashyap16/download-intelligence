import Foundation
import EngineBridge

/// Loads Preview's projection from a real `EngineBridge` — mirroring how
/// `HomeViewModel` is the one piece of WP-GUI-03 that talks to the Engine
/// Bridge for Home, applied here to Preview. Unlike `HomeViewModel`, this
/// type has no periodic refresh loop: Preview is not a persistent
/// background landing page the way Home is, it is a screen the user
/// navigates to and away from, and `GUI Architecture Specification.md` §7's
/// "always re-read, never trust a cache across an engine-changing action"
/// requirement is satisfied here by performing one fresh read every time
/// the screen is (re-)entered — a fresh `PreviewViewModel` instance is
/// constructed per visit (`AppShell`'s own responsibility, mirroring how it
/// already constructs a fresh `ScanViewModel` per scan), and `refreshNow()`
/// is called once from that instance's own `.task`, so revisiting Preview
/// always means a brand new read, never a value carried over from a
/// previous visit.
///
/// `@MainActor` because `projection`/`errorPresentation`/`isLoading` drive
/// SwiftUI view state directly, the same reason `HomeViewModel` is
/// `@MainActor`.
@MainActor
public final class PreviewViewModel: ObservableObject {
    @Published public private(set) var projection: PreviewProjection?
    @Published public private(set) var errorPresentation: ErrorPresentation?
    @Published public private(set) var isLoading = true

    private let bridge: EngineBridge

    public init(bridge: EngineBridge) {
        self.bridge = bridge
    }

    /// Performs one fresh read-and-compute cycle against the engine's
    /// current metadata store. There is exactly one code path for "get the
    /// current projection" — the same "no separate code path" principle
    /// `HomeViewModel.refreshNow()` already follows — so a caller
    /// requesting a manual refresh (e.g. after fixing an Error State) uses
    /// this identical method, never a bespoke variant.
    public func refreshNow() async {
        do {
            let result = try await bridge.readMetadataStore()
            projection = PreviewProjection.compute(records: result.records)
            errorPresentation = nil
        } catch let error as EngineBridgeError {
            errorPresentation = .forEngineBridgeFailure(error)
        } catch {
            errorPresentation = ErrorPresentation(
                heading: "Something went wrong",
                explanation: "Preview couldn't load the current plan.",
                resolutionActionTitle: "Try again",
                technicalDetail: String(describing: error)
            )
        }
        isLoading = false
    }
}
