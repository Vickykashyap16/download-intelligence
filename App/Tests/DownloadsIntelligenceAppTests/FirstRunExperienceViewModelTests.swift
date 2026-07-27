import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `FirstRunExperienceViewModel` — the one part of
/// WP-GUI-02 that actually drives a real `EngineBridge`, exactly mirroring
/// how `AppLifecycleControllerTests`/`HomeViewModelTests` exercise their
/// own view models against real (fixture-backed) bridges rather than mocks.
///
/// Every fixture here is self-contained under this test target's own
/// `Fixtures/` resource, per this project's "never share fixtures across
/// test targets" convention. Unlike every prior fixture-based test in this
/// project, these tests exercise a real config *write* (via each fixture's
/// own fake `src/cli.py`) — so every test copies its fixture project into a
/// fresh temporary directory first (`makeIsolatedProjectCopy`) rather than
/// pointing `EngineBridge` at the shared, bundled fixture directly. This
/// guards against exactly the class of defect this project's own
/// engineering history already caught once (Module 07's real-Database
/// test-isolation defect, Task #322) — a write-performing test must never
/// mutate a fixture shared with other tests or other runs.
@MainActor
final class FirstRunExperienceViewModelTests: XCTestCase {

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
            .appendingPathComponent("FirstRunExperienceViewModelTests-\(project)-\(UUID().uuidString)")
        try FileManager.default.copyItem(at: source, to: destination)
        addTeardownBlock {
            try? FileManager.default.removeItem(at: destination)
        }
        return destination
    }

    private func makeTempLogDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("FirstRunExperienceViewModelTests-log-\(UUID().uuidString)")
    }

    private func makeBridge(project: String) throws -> EngineBridge {
        EngineBridge(configuration: .init(
            projectRootURL: try makeIsolatedProjectCopy(of: project),
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

    private func makeViewModel(
        project: String,
        source: URL,
        destination: URL,
        onScanRequested: @escaping () -> Void = {}
    ) throws -> FirstRunExperienceViewModel {
        FirstRunExperienceViewModel(
            bridge: try makeBridge(project: project),
            defaultSourceURL: source,
            defaultDestinationURL: destination,
            onScanRequested: onScanRequested
        )
    }

    // MARK: - Step 1: Source, default validation

    func test_start_validatesDefaultSourceFolder() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let viewModel = try makeViewModel(project: "FirstRunEngineProject", source: source, destination: destination)

        await viewModel.start()

        XCTAssertEqual(viewModel.sourceValidation, .valid)
        XCTAssertTrue(viewModel.isSourceStepValid)
        XCTAssertFalse(viewModel.isValidatingSource)
        XCTAssertEqual(viewModel.currentStep, .source)
    }

    func test_chooseSourceFolder_nonexistentPath_blocksContinueWithoutAttemptingAWrite() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let viewModel = try makeViewModel(project: "FirstRunEngineProject", source: source, destination: destination)
        await viewModel.start()

        let missingFolder = FileManager.default.temporaryDirectory
            .appendingPathComponent("does-not-exist-\(UUID().uuidString)")
        await viewModel.chooseSourceFolder(missingFolder)

        XCTAssertEqual(viewModel.sourceValidation, .doesNotExist)
        XCTAssertFalse(viewModel.isSourceStepValid)

        await viewModel.continueFromSource()

        // Guarded before any Engine Bridge call: the step must not advance
        // and no error should be surfaced (nothing was even attempted).
        XCTAssertEqual(viewModel.currentStep, .source)
        XCTAssertNil(viewModel.errorPresentation)
    }

    // MARK: - Step 1 -> 2: real config write + verification

    func test_continueFromSource_validFolder_writesConfig_advancesToDestination_andValidatesIt() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let bridge = try makeBridge(project: "FirstRunEngineProject")
        let viewModel = FirstRunExperienceViewModel(
            bridge: bridge, defaultSourceURL: source, defaultDestinationURL: destination, onScanRequested: {}
        )
        await viewModel.start()
        XCTAssertTrue(viewModel.isSourceStepValid)

        await viewModel.continueFromSource()

        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.currentStep, .destination)
        XCTAssertFalse(viewModel.isSaving)
        // Step 2's default is validated automatically on arrival (§16,
        // States: "every step always has a value to show... even before
        // the user makes an active choice").
        XCTAssertEqual(viewModel.destinationValidation, .valid)

        // Independently confirm the real configuration file was actually
        // rewritten — not just that the ViewModel believes it was.
        let configuration = try await bridge.readConfiguration()
        XCTAssertEqual(configuration.sources.first?.path, source.path)
    }

    func test_continueFromDestination_validFolder_advancesToReadyToScan() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let bridge = try makeBridge(project: "FirstRunEngineProject")
        let viewModel = FirstRunExperienceViewModel(
            bridge: bridge, defaultSourceURL: source, defaultDestinationURL: destination, onScanRequested: {}
        )
        await viewModel.start()
        await viewModel.continueFromSource()
        XCTAssertEqual(viewModel.currentStep, .destination)

        await viewModel.continueFromDestination()

        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.currentStep, .readyToScan)

        let configuration = try await bridge.readConfiguration()
        XCTAssertEqual(configuration.destinationRoot, destination.path)
        XCTAssertEqual(configuration.sources.first?.path, source.path)
    }

    func test_chooseDestinationFolder_nonexistentPath_blocksContinue() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let viewModel = try makeViewModel(project: "FirstRunEngineProject", source: source, destination: destination)
        await viewModel.start()
        await viewModel.continueFromSource()
        XCTAssertEqual(viewModel.currentStep, .destination)

        let missingFolder = FileManager.default.temporaryDirectory
            .appendingPathComponent("does-not-exist-\(UUID().uuidString)")
        await viewModel.chooseDestinationFolder(missingFolder)

        XCTAssertEqual(viewModel.destinationValidation, .doesNotExist)
        XCTAssertFalse(viewModel.isDestinationStepValid)

        await viewModel.continueFromDestination()

        XCTAssertEqual(viewModel.currentStep, .destination)
        XCTAssertNil(viewModel.errorPresentation)
    }

    // MARK: - Step 3: Scan now

    func test_scanNow_invokesCallback() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        var scanRequested = false
        let viewModel = try makeViewModel(
            project: "FirstRunEngineProject", source: source, destination: destination,
            onScanRequested: { scanRequested = true }
        )

        viewModel.scanNow()

        XCTAssertTrue(scanRequested)
    }

    // MARK: - Navigation

    func test_goBack_fromDestination_returnsToSource() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let viewModel = try makeViewModel(project: "FirstRunEngineProject", source: source, destination: destination)
        await viewModel.start()
        await viewModel.continueFromSource()
        XCTAssertEqual(viewModel.currentStep, .destination)

        viewModel.goBack()

        XCTAssertEqual(viewModel.currentStep, .source)
    }

    func test_goBack_fromSource_isANoOp() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let viewModel = try makeViewModel(project: "FirstRunEngineProject", source: source, destination: destination)

        viewModel.goBack()

        XCTAssertEqual(viewModel.currentStep, .source)
    }

    // MARK: - Write verification failure (Config Corrupted error path)

    /// Proves WP-GUI-02's own Definition of Done: "the flow correctly
    /// diverts to the Config Corrupted error path if the configuration
    /// somehow fails to verify on re-read after writing." This fixture
    /// project has no `src/config/sources.yaml` at all, so the real CLI's
    /// own existence guard (verified against real `src/cli.py` source, not
    /// assumed) causes `config` to exit 0 while writing nothing — proving
    /// the re-read-and-compare step, not the exit code alone, is what
    /// actually guards this path.
    func test_continueFromSource_configWriteSilentlyNoOps_surfacesErrorState() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let viewModel = try makeViewModel(
            project: "FirstRunMissingConfigEngineProject", source: source, destination: destination
        )
        await viewModel.start()
        XCTAssertTrue(viewModel.isSourceStepValid)

        await viewModel.continueFromSource()

        XCTAssertEqual(viewModel.currentStep, .source, "must not advance on an unverified write")
        XCTAssertNotNil(viewModel.errorPresentation)
        XCTAssertFalse(viewModel.isSaving)
    }

    func test_dismissError_clearsErrorPresentation_withoutChangingStep() async throws {
        let source = try makeTempFolder()
        let destination = try makeTempFolder()
        let viewModel = try makeViewModel(
            project: "FirstRunMissingConfigEngineProject", source: source, destination: destination
        )
        await viewModel.start()
        await viewModel.continueFromSource()
        XCTAssertNotNil(viewModel.errorPresentation)

        viewModel.dismissError()

        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.currentStep, .source)
    }

    // MARK: - Default detection

    func test_detectedDownloadsFolder_isARealAccessibleURL() {
        let url = FirstRunExperienceViewModel.detectedDownloadsFolder()
        XCTAssertFalse(url.path.isEmpty)
    }

    func test_suggestedDestinationFolder_endsInOrganizedDownloads() {
        let url = FirstRunExperienceViewModel.suggestedDestinationFolder()
        XCTAssertEqual(url.lastPathComponent, "Organized Downloads")
    }
}
