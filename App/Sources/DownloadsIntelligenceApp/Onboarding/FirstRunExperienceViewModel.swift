import Foundation
import EngineBridge

/// Drives the three-step First Run Experience flow end-to-end against a
/// real `EngineBridge` — the one part of WP-GUI-02 that actually talks to
/// the Engine Bridge, exactly mirroring how `HomeViewModel` was the one
/// part of WP-GUI-03 that did so and `AppLifecycleController` the one part
/// of WP-GUI-01.
///
/// **Validation.** Each folder step's "Continue" is gated on a real,
/// syscall-backed check via `EngineBridge.validateFolder(at:requireWritable:)`
/// (WP-GUI-00A) — never assumed valid client-side (`GUI Engineering Work
/// Packages.md`, WP-GUI-02 Technical Notes). Both Source and Destination are
/// checked with `requireWritable: true`: the Technical Notes require "the
/// current step's folder is verified readable/writable" for either step
/// alike (no per-step asymmetry is specified), and Source specifically will
/// need write access later regardless — Execute (a future work package)
/// removes/moves files out of Source once they're filed, even though this
/// flow's own copy ("we only read files here") describes only what *this
/// screen* does to it.
///
/// **Write verification.** Per `Desktop Implementation Blueprint.md` §5
/// (Settings/config request-response flow): "on success, the Engine Bridge
/// re-reads the configuration file to confirm the new value took effect...
/// never optimistically assuming the write succeeded." Two independent
/// signals are checked after every config write, not one: the
/// `CommandResult`'s own exit-code-derived `succeeded` flag, and a fresh
/// `readConfiguration()` re-read compared field-by-field against what was
/// just written. The second check exists because real CLI source
/// (`src/cli.py`'s `_cmd_config()`) can report a clean, successful exit
/// (`return 0`) while writing nothing at all — if `src/config/sources.yaml`
/// doesn't exist yet, `_cmd_config()`'s own existence guard prints a message
/// and returns `0` without ever calling `_write_config_value()`. A
/// exit-code check alone would miss this; the re-read comparison catches it
/// every time. If either signal disagrees, the flow does not proceed and
/// instead surfaces the shared Error State (`Desktop Implementation
/// Blueprint.md` §8, Config Corrupted: "routes to an Error State... rather
/// than silently fabricating a value that was never actually confirmed by
/// the user"), satisfying WP-GUI-02's own Definition of Done ("the flow
/// correctly diverts to the Config Corrupted error path if the
/// configuration somehow fails to verify on re-read after writing").
///
/// **Incremental writes.** Source is written and confirmed at the end of
/// Step 1, Destination at the end of Step 2 — not both batched at Step 3.
/// This is the reading that makes §16's own interruption edge case
/// coherent: "if the app closes between steps, relaunching should resume at
/// Welcome or at the first incomplete step (whichever the underlying `init`
/// state indicates)" only has real content to resume *from* if a
/// completed step's choice was actually persisted. (Note: `AppLifecycleController`
/// itself, per WP-GUI-01A, only distinguishes "configured" from
/// "unconfigured" as a whole — it does not resume mid-flow at a specific
/// step. A user who quits after Step 1 relaunches to Welcome again, not
/// directly to Step 2; the engine-side persistence this flow performs is
/// still real and still exactly what makes that future refinement possible
/// without any further Engine Bridge change.)
///
/// `@MainActor` because every published property drives SwiftUI view state
/// directly.
@MainActor
public final class FirstRunExperienceViewModel: ObservableObject {
    @Published public private(set) var currentStep: FirstRunStep = .source

    @Published public private(set) var sourceURL: URL
    @Published public private(set) var sourceValidation: FolderValidationOutcome?
    @Published public private(set) var isValidatingSource = false

    @Published public private(set) var destinationURL: URL
    @Published public private(set) var destinationValidation: FolderValidationOutcome?
    @Published public private(set) var isValidatingDestination = false

    /// True while a config write + re-read-verify round trip is in flight
    /// (Step 1's and Step 2's "Continue"). Drives the "brief... loading"
    /// state §16 allows for ("Loading: brief, if folder validation takes a
    /// perceptible moment... otherwise not applicable" — the same brief-
    /// loading allowance applied here to the write/verify round trip, the
    /// only other real latency this flow has).
    @Published public private(set) var isSaving = false

    @Published public private(set) var errorPresentation: ErrorPresentation?

    private let bridge: EngineBridge
    private let onScanRequested: () -> Void

    /// - Parameters:
    ///   - defaultSourceURL/defaultDestinationURL: injectable so tests get
    ///     deterministic paths rather than depending on the real machine's
    ///     actual Downloads/Desktop folders, mirroring `HomeViewModel`'s own
    ///     injectable `now: () -> Date` pattern (WP-GUI-03).
    ///   - onScanRequested: the existing WP-GUI-03 stub navigation target
    ///     ("Scan Progress isn't built yet" — `AppShell`'s
    ///     `isScanStubShowing`) — Step 3's "Scan now" reuses it rather than
    ///     inventing a new one, since Scan Progress itself remains out of
    ///     this work package's scope.
    public init(
        bridge: EngineBridge,
        defaultSourceURL: URL = FirstRunExperienceViewModel.detectedDownloadsFolder(),
        defaultDestinationURL: URL = FirstRunExperienceViewModel.suggestedDestinationFolder(),
        onScanRequested: @escaping () -> Void
    ) {
        self.bridge = bridge
        self.sourceURL = defaultSourceURL
        self.destinationURL = defaultDestinationURL
        self.onScanRequested = onScanRequested
    }

    // MARK: - Default detection

    /// The real, current user's Downloads folder — "pre-filled real
    /// Downloads folder path" (§16, Step 1 content spec).
    ///
    /// `nonisolated`: this is used as a default initializer argument, which
    /// Swift evaluates in a nonisolated context even though `init` itself
    /// is `@MainActor`-isolated (default-argument expressions are part of
    /// the caller-side expression, not the initializer body). Safe here
    /// because this function only calls `FileManager` APIs — it never
    /// touches `self` or any other actor-isolated state.
    public nonisolated static func detectedDownloadsFolder() -> URL {
        FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Downloads")
    }

    /// "pre-filled suggested subfolder path" (§16, Step 2 content spec).
    /// `~/Desktop/Organized Downloads` is not an invented guess: it is the
    /// real, current sample destination already used elsewhere in this
    /// project's own `sources.yaml` convention.
    ///
    /// `nonisolated` for the same reason as `detectedDownloadsFolder()`
    /// above — used as a default initializer argument, and touches only
    /// `FileManager`, never actor-isolated state.
    public nonisolated static func suggestedDestinationFolder() -> URL {
        FileManager.default.urls(for: .desktopDirectory, in: .userDomainMask).first?
            .appendingPathComponent("Organized Downloads")
            ?? FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Desktop/Organized Downloads")
    }

    // MARK: - Step 1: Source

    /// Validates the pre-filled default the moment Step 1 becomes visible —
    /// "every step always has a value to show (a detected default), even
    /// before the user makes an active choice" (§16, States: Empty) means
    /// that default must already carry a real validation result, not an
    /// assumed one.
    public func start() async {
        await validateSource()
    }

    public func validateSource() async {
        isValidatingSource = true
        sourceValidation = await bridge.validateFolder(at: sourceURL, requireWritable: true)
        isValidatingSource = false
    }

    public func chooseSourceFolder(_ url: URL) async {
        sourceURL = url
        await validateSource()
    }

    public var isSourceStepValid: Bool {
        sourceValidation?.isValid ?? false
    }

    public func continueFromSource() async {
        guard isSourceStepValid else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            let result = try await bridge.run(.config(setSource: sourceURL.path))
            guard result.succeeded else {
                errorPresentation = Self.configWriteFailedPresentation(detail: Self.commandFailureDetail(result))
                return
            }
            let configuration = try await bridge.readConfiguration()
            guard configuration.sources.first?.path == sourceURL.path else {
                errorPresentation = Self.configWriteFailedPresentation(
                    detail: "Wrote source path \(sourceURL.path), but re-reading the configuration did not confirm it."
                )
                return
            }
            currentStep = .destination
            await validateDestination()
        } catch let error as EngineBridgeError {
            errorPresentation = .forEngineBridgeFailure(error)
        } catch {
            errorPresentation = Self.configWriteFailedPresentation(detail: String(describing: error))
        }
    }

    // MARK: - Step 2: Destination

    public func validateDestination() async {
        isValidatingDestination = true
        destinationValidation = await bridge.validateFolder(at: destinationURL, requireWritable: true)
        isValidatingDestination = false
    }

    public func chooseDestinationFolder(_ url: URL) async {
        destinationURL = url
        await validateDestination()
    }

    public var isDestinationStepValid: Bool {
        destinationValidation?.isValid ?? false
    }

    public func continueFromDestination() async {
        guard isDestinationStepValid else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            let result = try await bridge.run(.config(setDestination: destinationURL.path))
            guard result.succeeded else {
                errorPresentation = Self.configWriteFailedPresentation(detail: Self.commandFailureDetail(result))
                return
            }
            let configuration = try await bridge.readConfiguration()
            guard configuration.destinationRoot == destinationURL.path else {
                errorPresentation = Self.configWriteFailedPresentation(
                    detail: "Wrote destination path \(destinationURL.path), but re-reading the configuration did not confirm it."
                )
                return
            }
            currentStep = .readyToScan
        } catch let error as EngineBridgeError {
            errorPresentation = .forEngineBridgeFailure(error)
        } catch {
            errorPresentation = Self.configWriteFailedPresentation(detail: String(describing: error))
        }
    }

    // MARK: - Step 3: Ready to scan

    /// "this final step's button leads directly into Scan Progress" (§16,
    /// Step 3 content spec) — both Source and Destination are already
    /// written and confirmed by the time this step is reached, so there is
    /// nothing further to save here; this only hands off to the existing
    /// stub navigation target.
    public func scanNow() {
        onScanRequested()
    }

    // MARK: - Navigation

    public func goBack() {
        guard let previous = currentStep.previous else { return }
        currentStep = previous
    }

    // MARK: - Error recovery

    /// "Try again" on the resulting Error State dismisses it and returns
    /// control to whichever step was in progress (untouched by the failed
    /// attempt, since `currentStep` only advances after a write is
    /// confirmed) — this already *is* "re-run configuration... via First
    /// Run Experience's exact flow" (`Desktop Implementation Blueprint.md`
    /// §8, Config corrupted), since the flow never left.
    public func dismissError() {
        errorPresentation = nil
    }

    private static func configWriteFailedPresentation(detail: String) -> ErrorPresentation {
        ErrorPresentation(
            heading: "Couldn't save your settings",
            explanation: "The app tried to save this folder choice, but couldn't confirm it took effect. Nothing has changed yet — you can try again.",
            resolutionActionTitle: "Try again",
            technicalDetail: detail,
            layout: .fullScreen
        )
    }

    private static func commandFailureDetail(_ result: CommandResult) -> String {
        let errorOutput = result.standardError.trimmingCharacters(in: .whitespacesAndNewlines)
        let output = result.standardOutput.trimmingCharacters(in: .whitespacesAndNewlines)
        let detail = !errorOutput.isEmpty ? errorOutput : output
        return "\(result.command) exited with code \(result.exitCode)\(detail.isEmpty ? "" : ": \(detail)")"
    }
}
