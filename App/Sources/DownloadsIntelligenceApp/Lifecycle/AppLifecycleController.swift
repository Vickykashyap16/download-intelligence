import Foundation
import EngineBridge

/// Drives the application through `Desktop Implementation Blueprint.md`
/// §2's fixed lifecycle sequence, using a real `EngineBridge` for the Load
/// Configuration and Engine Bridge readiness phases. This is the one part
/// of WP-GUI-01 that actually talks to the Engine Bridge — every shared
/// component (buttons, chips, badges, dialogs, empty/error states) remains
/// entirely independent of it, per the work package's own scope boundary
/// ("out of scope: any screen's real content" beyond wiring the Error
/// State to a real failure).
///
/// `@MainActor` because `phase` drives SwiftUI view state directly
/// (`AppShell` observes this controller) — every phase transition is
/// therefore published on the main actor, and every `EngineBridge` call
/// below is `await`ed across that actor boundary, exactly as `EngineBridge`
/// itself requires of any caller.
@MainActor
public final class AppLifecycleController: ObservableObject {
    @Published public private(set) var phase: AppLifecyclePhase = .launching

    private let bridge: EngineBridge

    public init(bridge: EngineBridge) {
        self.bridge = bridge
    }

    /// Runs the fixed phase sequence once, in order, exactly as `Desktop
    /// Implementation Blueprint.md` §2 describes it: Launch (already
    /// implicit — this method being called at all is the app having
    /// launched) → Initialize → Load Configuration → Engine Bridge
    /// (readiness check) → Read Metadata → Restore Window State → Display
    /// Home. Every transition is driven by a real (or, in tests,
    /// fixture-backed) `EngineBridge` call — nothing here is simulated or
    /// faked once this method is actually invoked.
    public func start() async {
        phase = .initializing
        phase = .loadingConfiguration

        do {
            _ = try await bridge.readConfiguration()
        } catch EngineBridgeError.artifactNotFound {
            // "the configuration is entirely absent... this is a
            // first-time setup" (`Desktop Implementation Blueprint.md`
            // §2). This is the *only* file `readConfiguration()` reads,
            // so an `.artifactNotFound` at this exact phase unambiguously
            // means "no configuration yet," not some other missing
            // artifact.
            phase = .firstRunNeeded
            return
        } catch let error as EngineBridgeError {
            // "present but unreadable/malformed... routes immediately to
            // the Config Corrupted error path" (ibid.).
            phase = .error(.forEngineBridgeFailure(error))
            return
        } catch {
            phase = .error(ErrorPresentation(
                heading: "Something went wrong",
                explanation: "The app couldn't read its configuration.",
                resolutionActionTitle: "Check folder settings",
                technicalDetail: String(describing: error)
            ))
            return
        }

        phase = .checkingEngineReadiness
        do {
            try await bridge.verifyEngineIsCompatible()
        } catch let error as EngineBridgeError {
            // "If this check fails, the lifecycle diverts to the Python
            // Missing or Engine Unavailable error path... before any
            // further phase is attempted" (ibid.).
            phase = .error(.forEngineBridgeFailure(error))
            return
        } catch {
            phase = .error(ErrorPresentation(
                heading: "Couldn't reach the engine",
                explanation: "The app couldn't confirm the engine is installed and reachable.",
                resolutionActionTitle: "Try again",
                technicalDetail: String(describing: error)
            ))
            return
        }

        phase = .readingMetadata
        // Best-effort: a missing or unreadable metadata store/action log
        // at this stage is not itself fatal to reaching Home (Home's own
        // real content, including what to show for each of these cases,
        // is a future work package's concern) — WP-GUI-01 only needs this
        // phase to genuinely run against the real Engine Bridge, not to
        // render its result anywhere yet.
        _ = try? await bridge.readMetadataStore()
        _ = try? await bridge.readActionLog()

        phase = .restoringWindowState
        phase = .displayingHome
    }
}
