import Foundation
import EngineBridge

/// Drives the Settings screen (WP-GUI-11) against a real `EngineBridge` —
/// "Expose the existing configuration-management capability through a
/// dedicated Settings screen, reusing the exact logic already proven in
/// Onboarding" (`GUI Engineering Work Packages.md`, WP-GUI-11 Objective).
///
/// **Reused, not reinvented.** Every Engine Bridge capability this type
/// calls — `readConfiguration()`, `run(.config(setSource:setDestination:))`,
/// `validateFolder(at:requireWritable:)`, `currentEngineVersion()` — already
/// exists and is already proven working end-to-end by
/// `FirstRunExperienceViewModel` (WP-GUI-02) and `ReportsViewModel`
/// (WP-GUI-10). This type adds no new Engine Bridge capability.
///
/// **Write verification.** `chooseSourceFolder(_:)`/`chooseDestinationFolder(_:)`
/// reuse exactly the same write-then-re-read-and-compare pattern as
/// `FirstRunExperienceViewModel.continueFromSource()`/`continueFromDestination()`:
/// validate first, then write, then check the `CommandResult`'s own
/// `succeeded` flag, then re-read `EngineConfiguration` and compare the
/// written field — never inferring success from the command result alone
/// (`GUI Engineering Work Packages.md`, WP-GUI-11 Technical Notes: "a folder
/// setting change must be confirmed via re-read before being reflected as
/// saved, per the no-optimistic-success rule already applied throughout the
/// roadmap"). Unlike Onboarding's stepped wizard, Settings has no "Continue"
/// step to gate this behind — this screen is revisited and edited directly,
/// so each folder choice validates and (if valid) saves in one action,
/// matching how a settings pane, not a wizard, is normally used.
///
/// **Error isolation.** Loading the folder configuration and loading the
/// engine version read two independent artifacts (`src/config/sources.yaml`
/// vs. `Release/VERSIONS.md`) — a corrupt/missing version file must not
/// block the folder settings from working, and vice versa. `configurationError`
/// and `engineVersionError` are therefore separate, independently-cleared
/// properties, the same "one artifact's failure never affects the other"
/// principle `ReportsViewModel` (WP-GUI-10) already established, scoped here
/// to Settings' own two genuinely independent reads.
///
/// A folder change never retroactively alters already-filed files
/// (WP-GUI-11 Technical Notes) — this is real, existing engine-side
/// behavior (the same `config` subprocess Onboarding already invokes,
/// which only ever rewrites `sources.yaml`), not something this type needs
/// to implement.
///
/// `@MainActor` because every published property drives SwiftUI view state
/// directly, matching every other ViewModel in this project.
@MainActor
public final class SettingsViewModel: ObservableObject {

    // MARK: - Folder configuration (Source & Destination)

    @Published public private(set) var isLoading = false
    @Published public private(set) var configurationError: ErrorPresentation?

    @Published public private(set) var sourceURL: URL?
    @Published public private(set) var sourceValidation: FolderValidationOutcome?
    @Published public private(set) var isValidatingSource = false
    @Published public private(set) var isSavingSource = false

    @Published public private(set) var destinationURL: URL?
    @Published public private(set) var destinationValidation: FolderValidationOutcome?
    @Published public private(set) var isValidatingDestination = false
    @Published public private(set) var isSavingDestination = false

    // MARK: - About

    /// The real, current application version — `AppVersion.current`, this
    /// work package's own single GUI-only source of truth. Never `nil`:
    /// unlike the engine version, this never depends on reading anything
    /// from disk or the subprocess, so it has nothing to fail.
    public let appVersion: SemanticVersion = AppVersion.current

    @Published public private(set) var engineVersion: SemanticVersion?
    @Published public private(set) var engineVersionError: ErrorPresentation?

    private let bridge: EngineBridge

    public init(bridge: EngineBridge) {
        self.bridge = bridge
    }

    // MARK: - Loading

    /// Loads the current folder configuration and the current engine
    /// version. Safe to call again on every screen entry (mirrors
    /// `ReportsSectionView`'s own "re-created fresh every time the section
    /// is (re-)selected" precedent) — always re-reads rather than trusting
    /// stale state, consistent with this project's "the artifact re-read is
    /// the source of truth" principle applied to a load, not just a write.
    public func load() async {
        isLoading = true
        defer { isLoading = false }

        configurationError = nil
        do {
            let configuration = try await bridge.readConfiguration()
            let source = configuration.sources.first.map { URL(fileURLWithPath: $0.path) }
            let destination = configuration.destinationRoot.map { URL(fileURLWithPath: $0) }
            sourceURL = source
            destinationURL = destination
            if let source {
                await validateSource(source)
            } else {
                sourceValidation = nil
            }
            if let destination {
                await validateDestination(destination)
            } else {
                destinationValidation = nil
            }
        } catch let error as EngineBridgeError {
            configurationError = .forEngineBridgeFailure(error)
        } catch {
            configurationError = Self.unexpectedFailurePresentation(
                explanation: "The app couldn't load your current folder settings.",
                detail: String(describing: error)
            )
        }

        engineVersionError = nil
        do {
            engineVersion = try await bridge.currentEngineVersion()
        } catch let error as EngineBridgeError {
            engineVersion = nil
            engineVersionError = .forEngineBridgeFailure(error, layout: .inline)
        } catch {
            engineVersion = nil
            engineVersionError = Self.unexpectedFailurePresentation(
                explanation: "The app couldn't read the engine's version.",
                detail: String(describing: error),
                layout: .inline
            )
        }
    }

    // MARK: - Source

    private func validateSource(_ url: URL) async {
        isValidatingSource = true
        sourceValidation = await bridge.validateFolder(at: url, requireWritable: true)
        isValidatingSource = false
    }

    /// Validates `url`, then — only if valid — writes it as the Source
    /// folder and confirms the write via re-read, exactly as
    /// `FirstRunExperienceViewModel.continueFromSource()` does. `sourceURL`
    /// only ever advances to `url` once that confirmation succeeds; an
    /// invalid or unconfirmed choice leaves the previously-saved value in
    /// place, with the failure surfaced via `sourceValidation`/
    /// `configurationError`.
    public func chooseSourceFolder(_ url: URL) async {
        configurationError = nil
        await validateSource(url)
        guard sourceValidation?.isValid ?? false else { return }

        isSavingSource = true
        defer { isSavingSource = false }
        do {
            let result = try await bridge.run(.config(setSource: url.path))
            guard result.succeeded else {
                configurationError = Self.configWriteFailedPresentation(detail: Self.commandFailureDetail(result))
                return
            }
            let configuration = try await bridge.readConfiguration()
            guard configuration.sources.first?.path == url.path else {
                configurationError = Self.configWriteFailedPresentation(
                    detail: "Wrote source path \(url.path), but re-reading the configuration did not confirm it."
                )
                return
            }
            sourceURL = url
        } catch let error as EngineBridgeError {
            configurationError = .forEngineBridgeFailure(error)
        } catch {
            configurationError = Self.configWriteFailedPresentation(detail: String(describing: error))
        }
    }

    // MARK: - Destination

    private func validateDestination(_ url: URL) async {
        isValidatingDestination = true
        destinationValidation = await bridge.validateFolder(at: url, requireWritable: true)
        isValidatingDestination = false
    }

    /// The Destination counterpart of `chooseSourceFolder(_:)` — same
    /// validate-then-write-then-verify pattern, mirroring
    /// `FirstRunExperienceViewModel.continueFromDestination()`.
    public func chooseDestinationFolder(_ url: URL) async {
        configurationError = nil
        await validateDestination(url)
        guard destinationValidation?.isValid ?? false else { return }

        isSavingDestination = true
        defer { isSavingDestination = false }
        do {
            let result = try await bridge.run(.config(setDestination: url.path))
            guard result.succeeded else {
                configurationError = Self.configWriteFailedPresentation(detail: Self.commandFailureDetail(result))
                return
            }
            let configuration = try await bridge.readConfiguration()
            guard configuration.destinationRoot == url.path else {
                configurationError = Self.configWriteFailedPresentation(
                    detail: "Wrote destination path \(url.path), but re-reading the configuration did not confirm it."
                )
                return
            }
            destinationURL = url
        } catch let error as EngineBridgeError {
            configurationError = .forEngineBridgeFailure(error)
        } catch {
            configurationError = Self.configWriteFailedPresentation(detail: String(describing: error))
        }
    }

    // MARK: - Error recovery

    public func dismissConfigurationError() {
        configurationError = nil
    }

    // MARK: - Presentation helpers

    private static func configWriteFailedPresentation(detail: String) -> ErrorPresentation {
        ErrorPresentation(
            heading: "Couldn't save your settings",
            explanation: "The app tried to save this folder choice, but couldn't confirm it took effect. Nothing has changed yet — you can try again.",
            resolutionActionTitle: "Try again",
            technicalDetail: detail,
            layout: .fullScreen
        )
    }

    private static func unexpectedFailurePresentation(
        explanation: String,
        detail: String,
        layout: ErrorStateLayout = .fullScreen
    ) -> ErrorPresentation {
        ErrorPresentation(
            heading: "Something went wrong",
            explanation: explanation,
            resolutionActionTitle: "Try again",
            technicalDetail: detail,
            layout: layout
        )
    }

    private static func commandFailureDetail(_ result: CommandResult) -> String {
        let errorOutput = result.standardError.trimmingCharacters(in: .whitespacesAndNewlines)
        let output = result.standardOutput.trimmingCharacters(in: .whitespacesAndNewlines)
        let detail = !errorOutput.isEmpty ? errorOutput : output
        return "\(result.command) exited with code \(result.exitCode)\(detail.isEmpty ? "" : ": \(detail)")"
    }
}
