import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `SettingsViewModel` (WP-GUI-11) against a real
/// `EngineBridge` — mirroring `FirstRunExperienceViewModelTests`' own
/// isolated-copy discipline: every test that performs a real config write
/// copies its fixture project into a fresh temporary directory first
/// (`makeIsolatedProjectCopy`), so a write-performing test never mutates a
/// fixture shared with other tests or other runs (the exact defect class
/// this project's own engineering history already caught once — Module 07's
/// real-Database test-isolation defect, Task #322).
///
/// Reuses `FirstRunEngineProject`/`FirstRunMissingConfigEngineProject`
/// (already built for WP-GUI-02) rather than building new fixtures: Settings
/// performs the exact same `config` write/read round trip Onboarding does,
/// against the exact same fake CLI behavior, so a second, parallel fixture
/// would only duplicate this one. This also directly enables WP-GUI-11's own
/// Test Plan requirement — "a side-by-side test confirming a folder change
/// via Settings and the equivalent change via Onboarding produce identical
/// configuration file results" — which requires both view models to start
/// from the same fixture in the first place.
@MainActor
final class SettingsViewModelTests: XCTestCase {

    private let minimumSupportedVersion = SemanticVersion(major: 0, minor: 1, patch: 0)
    private let maximumSupportedVersion = SemanticVersion(major: 0, minor: 9, patch: 0)

    private func fixtureURL(_ project: String) throws -> URL {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return fixturesRoot.appendingPathComponent(project)
    }

    private func makeIsolatedProjectCopy(of project: String) throws -> URL {
        let source = try fixtureURL(project)
        let destination = FileManager.default.temporaryDirectory
            .appendingPathComponent("SettingsViewModelTests-\(project)-\(UUID().uuidString)")
        try FileManager.default.copyItem(at: source, to: destination)
        addTeardownBlock {
            try? FileManager.default.removeItem(at: destination)
        }
        return destination
    }

    private func makeTempLogDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("SettingsViewModelTests-log-\(UUID().uuidString)")
    }

    private func makeBridge(projectRoot: URL) -> EngineBridge {
        EngineBridge(configuration: .init(
            projectRootURL: projectRoot,
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempLogDirectory()
        ))
    }

    private func makeTempFolder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        addTeardownBlock {
            try? FileManager.default.removeItem(at: url)
        }
        return url
    }

    /// Overwrites an isolated fixture copy's `sources.yaml` so a test can
    /// exercise `load()` against a real, currently-valid folder rather than
    /// the fixture's own hardcoded `/Users/fixture/...` placeholder paths
    /// (which don't exist on the machine running the test).
    private func writeSourcesYAML(projectRoot: URL, sourcePath: String, destinationPath: String?) throws {
        let configURL = projectRoot.appendingPathComponent("src/config/sources.yaml")
        let destinationLine = destinationPath.map { "destination_root: \($0)" } ?? "destination_root: null"
        let contents = """
        sources:
          - source_id: downloads
            path: \(sourcePath)
            type: local_folder
            enabled: true
            recursive: false
        execution_mode: manual
        \(destinationLine)
        classification_provider: null
        extraction_provider: null
        ai_provider_consent: false
        """
        try contents.write(to: configURL, atomically: true, encoding: .utf8)
    }

    // MARK: - Loading

    func test_load_readsExistingSourceAndDestination_andValidatesBoth() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let projectRoot = try makeIsolatedProjectCopy(of: "FirstRunEngineProject")
        try writeSourcesYAML(projectRoot: projectRoot, sourcePath: source.path, destinationPath: destination.path)
        let viewModel = SettingsViewModel(bridge: makeBridge(projectRoot: projectRoot))

        await viewModel.load()

        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.configurationError)
        XCTAssertEqual(viewModel.sourceURL?.path, source.path)
        XCTAssertEqual(viewModel.sourceValidation, .valid)
        XCTAssertEqual(viewModel.destinationURL?.path, destination.path)
        XCTAssertEqual(viewModel.destinationValidation, .valid)
        XCTAssertEqual(viewModel.engineVersion, SemanticVersion(major: 0, minor: 8, patch: 0))
        XCTAssertNil(viewModel.engineVersionError)
        XCTAssertEqual(viewModel.appVersion, AppVersion.current)
    }

    func test_load_noDestinationConfiguredYet_leavesDestinationNil() async throws {
        // FirstRunEngineProject's own shipped sources.yaml has
        // `destination_root: null` and a source path that doesn't exist on
        // this machine (`/Users/fixture/Downloads`), unmodified.
        let projectRoot = try makeIsolatedProjectCopy(of: "FirstRunEngineProject")
        let viewModel = SettingsViewModel(bridge: makeBridge(projectRoot: projectRoot))

        await viewModel.load()

        XCTAssertNil(viewModel.configurationError)
        XCTAssertNil(viewModel.destinationURL)
        XCTAssertNil(viewModel.destinationValidation)
        XCTAssertEqual(viewModel.sourceURL?.path, "/Users/fixture/Downloads")
        XCTAssertEqual(viewModel.sourceValidation, .doesNotExist)
    }

    func test_load_missingConfiguration_surfacesConfigurationErrorWithoutAffectingEngineVersion() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "FirstRunMissingConfigEngineProject")
        let viewModel = SettingsViewModel(bridge: makeBridge(projectRoot: projectRoot))

        await viewModel.load()

        XCTAssertNotNil(viewModel.configurationError)
        XCTAssertNil(viewModel.sourceURL)
        XCTAssertNil(viewModel.destinationURL)
        // The engine version file is a separate, independent artifact from
        // the (here, missing) configuration file — isolated exactly like
        // `ReportsViewModel` (WP-GUI-10) isolates each of its four artifacts
        // from one another.
        XCTAssertNil(viewModel.engineVersionError)
        XCTAssertEqual(viewModel.engineVersion, SemanticVersion(major: 0, minor: 8, patch: 0))
    }

    /// `EngineBridge.currentEngineVersion()` is deliberately *ungated* — it
    /// reads `Release/VERSIONS.md` directly, without checking it against the
    /// supported range, specifically so a caller can still display which
    /// version is actually installed even when it's incompatible (see that
    /// method's own documentation). `readConfiguration()`, by contrast, *is*
    /// gated. So an incompatible engine is expected to still successfully
    /// report its real version in the About section, while the folder
    /// configuration read fails — these are two independently-behaving
    /// artifacts, not a single whole-screen failure.
    func test_load_incompatibleEngineVersion_stillReportsRealEngineVersion_whileConfigurationFails() async throws {
        // Read-only fixture — no write performed, so no isolated copy is
        // needed (mirrors `ReportsViewModelTests`' own use of this fixture).
        let projectRoot = try fixtureURL("IncompatibleEngineProject")
        let viewModel = SettingsViewModel(bridge: makeBridge(projectRoot: projectRoot))

        await viewModel.load()

        XCTAssertEqual(viewModel.configurationError?.heading, "Update needed")
        XCTAssertNil(viewModel.engineVersionError)
        XCTAssertEqual(viewModel.engineVersion, SemanticVersion(major: 9, minor: 9, patch: 9))
        XCTAssertNil(viewModel.sourceURL)
    }

    // MARK: - Choosing folders: validate, then write, then re-read and verify

    func test_chooseSourceFolder_validFolder_writesAndConfirms() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "FirstRunEngineProject")
        let bridge = makeBridge(projectRoot: projectRoot)
        let viewModel = SettingsViewModel(bridge: bridge)
        let newSource = try makeTempFolder()

        await viewModel.chooseSourceFolder(newSource)

        XCTAssertNil(viewModel.configurationError)
        XCTAssertEqual(viewModel.sourceValidation, .valid)
        XCTAssertFalse(viewModel.isSavingSource)
        XCTAssertEqual(viewModel.sourceURL?.path, newSource.path)

        // Independently confirm the real configuration file was actually
        // rewritten — not just that the ViewModel believes it was.
        let configuration = try await bridge.readConfiguration()
        XCTAssertEqual(configuration.sources.first?.path, newSource.path)
    }

    func test_chooseDestinationFolder_validFolder_writesAndConfirms() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "FirstRunEngineProject")
        let bridge = makeBridge(projectRoot: projectRoot)
        let viewModel = SettingsViewModel(bridge: bridge)
        let newDestination = try makeTempFolder()

        await viewModel.chooseDestinationFolder(newDestination)

        XCTAssertNil(viewModel.configurationError)
        XCTAssertEqual(viewModel.destinationValidation, .valid)
        XCTAssertFalse(viewModel.isSavingDestination)
        XCTAssertEqual(viewModel.destinationURL?.path, newDestination.path)

        let configuration = try await bridge.readConfiguration()
        XCTAssertEqual(configuration.destinationRoot, newDestination.path)
    }

    func test_chooseSourceFolder_nonexistentPath_doesNotAttemptWrite() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "FirstRunEngineProject")
        let bridge = makeBridge(projectRoot: projectRoot)
        let viewModel = SettingsViewModel(bridge: bridge)
        let missingFolder = FileManager.default.temporaryDirectory
            .appendingPathComponent("does-not-exist-\(UUID().uuidString)")

        await viewModel.chooseSourceFolder(missingFolder)

        XCTAssertEqual(viewModel.sourceValidation, .doesNotExist)
        XCTAssertNil(viewModel.configurationError, "nothing was even attempted, so there is nothing to report as failed")
        XCTAssertNil(viewModel.sourceURL, "an invalid choice must not be reflected as the current, saved value")

        // The real configuration file must be untouched.
        let configuration = try await bridge.readConfiguration()
        XCTAssertEqual(configuration.sources.first?.path, "/Users/fixture/Downloads")
    }

    /// Proves the same "Config Corrupted" verification-failure path
    /// `FirstRunExperienceViewModel` already guards: this fixture has no
    /// `src/config/sources.yaml` at all, so the real CLI's own existence
    /// guard causes `config` to exit 0 while writing nothing — the re-read-
    /// and-compare step, not the exit code alone, is what catches this.
    func test_chooseSourceFolder_configWriteSilentlyNoOps_surfacesErrorState() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "FirstRunMissingConfigEngineProject")
        let bridge = makeBridge(projectRoot: projectRoot)
        let viewModel = SettingsViewModel(bridge: bridge)
        let newSource = try makeTempFolder()

        await viewModel.chooseSourceFolder(newSource)

        XCTAssertNotNil(viewModel.configurationError)
        XCTAssertNil(viewModel.sourceURL, "must not advance on an unverified write")
        XCTAssertFalse(viewModel.isSavingSource)
    }

    func test_dismissConfigurationError_clearsError() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "FirstRunMissingConfigEngineProject")
        let bridge = makeBridge(projectRoot: projectRoot)
        let viewModel = SettingsViewModel(bridge: bridge)
        await viewModel.chooseSourceFolder(try makeTempFolder())
        XCTAssertNotNil(viewModel.configurationError)

        viewModel.dismissConfigurationError()

        XCTAssertNil(viewModel.configurationError)
    }

    // MARK: - Acceptance Criteria: parity with Onboarding

    /// WP-GUI-11's own Test Plan: "a side-by-side test confirming a folder
    /// change via Settings and the equivalent change via Onboarding produce
    /// identical configuration file results." Each view model is driven
    /// against its own isolated copy of the exact same starting fixture,
    /// given the exact same new source folder, and the resulting
    /// configuration files are compared field-by-field.
    func test_chooseSourceFolder_producesIdenticalConfigurationResult_asOnboardingContinueFromSource() async throws {
        let newSource = try makeTempFolder()

        let settingsProjectRoot = try makeIsolatedProjectCopy(of: "FirstRunEngineProject")
        let settingsBridge = makeBridge(projectRoot: settingsProjectRoot)
        let settingsViewModel = SettingsViewModel(bridge: settingsBridge)
        await settingsViewModel.chooseSourceFolder(newSource)

        let onboardingProjectRoot = try makeIsolatedProjectCopy(of: "FirstRunEngineProject")
        let onboardingBridge = makeBridge(projectRoot: onboardingProjectRoot)
        let onboardingViewModel = FirstRunExperienceViewModel(
            bridge: onboardingBridge,
            defaultSourceURL: newSource,
            defaultDestinationURL: try makeTempFolder(),
            onScanRequested: {}
        )
        await onboardingViewModel.start()
        await onboardingViewModel.continueFromSource()

        let settingsConfiguration = try await settingsBridge.readConfiguration()
        let onboardingConfiguration = try await onboardingBridge.readConfiguration()
        XCTAssertEqual(settingsConfiguration.sources, onboardingConfiguration.sources)
    }
}
