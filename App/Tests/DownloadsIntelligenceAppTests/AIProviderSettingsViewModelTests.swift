import XCTest
import Foundation
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Integration tests for `AIProviderSettingsViewModel` (WP-GUI-12) against a
/// real `EngineBridge` and a real `python3` subprocess — mirroring
/// `SettingsViewModelTests`/`HistoryViewModelTests`' own isolated-copy
/// discipline: every test that performs a real config write copies its
/// fixture project into a fresh temporary directory first
/// (`makeIsolatedProjectCopy`), so a write-performing test never mutates a
/// fixture shared with other tests or other runs.
///
/// Uses a new fixture, `ProviderSettingsEngineProject` — no existing
/// fixture supports the `provider enable`/`provider disable` subprocess
/// path (`FirstRunEngineProject`'s fixture `src/cli.py` only implements
/// `version`/`config`) — plus an in-memory `FakeCredentialStore` so these
/// tests never touch the real OS Keychain (`KeychainCredentialStoreTests`
/// is the one place that exercises the real Keychain-backed implementation
/// directly).
@MainActor
final class AIProviderSettingsViewModelTests: XCTestCase {

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
            .appendingPathComponent("AIProviderSettingsViewModelTests-\(project)-\(UUID().uuidString)")
        try FileManager.default.copyItem(at: source, to: destination)
        addTeardownBlock {
            try? FileManager.default.removeItem(at: destination)
        }
        return destination
    }

    private func makeTempLogDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("AIProviderSettingsViewModelTests-log-\(UUID().uuidString)")
    }

    private func makeBridge(projectRoot: URL) -> EngineBridge {
        EngineBridge(configuration: .init(
            projectRootURL: projectRoot,
            minimumSupportedEngineVersion: minimumSupportedVersion,
            maximumSupportedEngineVersion: maximumSupportedVersion,
            guiLogDirectoryURL: makeTempLogDirectory()
        ))
    }

    /// Overwrites an isolated fixture copy's `sources.yaml` `ai_provider_
    /// consent` line, so a test can start from either the off (fixture
    /// default) or on state before calling `load()`.
    private func writeConsent(projectRoot: URL, enabled: Bool) throws {
        let configURL = projectRoot.appendingPathComponent("src/config/sources.yaml")
        let contents = """
        sources:
          - source_id: downloads
            path: /Users/fixture/Downloads
            type: local_folder
            enabled: true
            recursive: false
        execution_mode: manual
        destination_root: null
        classification_provider: null
        extraction_provider: null
        ai_provider_consent: \(enabled ? "true" : "false")
        """
        try contents.write(to: configURL, atomically: true, encoding: .utf8)
    }

    private func makeViewModel(projectRoot: URL, credentialStore: CredentialStore = FakeCredentialStore()) -> AIProviderSettingsViewModel {
        AIProviderSettingsViewModel(bridge: makeBridge(projectRoot: projectRoot), credentialStore: credentialStore)
    }

    // MARK: - Loading

    func test_load_reportsOff_whenAiProviderConsentIsFalse() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        let viewModel = makeViewModel(projectRoot: projectRoot)

        await viewModel.load()

        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.projection.status, .off)
        XCTAssertEqual(viewModel.projection.statusLabel, "Status: Off")
    }

    func test_load_reportsOn_whenAiProviderConsentIsTrue() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        try writeConsent(projectRoot: projectRoot, enabled: true)
        let viewModel = makeViewModel(projectRoot: projectRoot)

        await viewModel.load()

        XCTAssertEqual(viewModel.projection.status, .on)
        XCTAssertEqual(viewModel.projection.statusLabel, "Status: On")
    }

    // MARK: - Disclosure gating

    func test_beforeMarkDisclosureShown_enableIsNotReachable() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        let viewModel = makeViewModel(projectRoot: projectRoot)

        await viewModel.load()

        XCTAssertFalse(viewModel.projection.isEnableReachable)
    }

    func test_markDisclosureShown_makesEnableReachable() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        let viewModel = makeViewModel(projectRoot: projectRoot)

        await viewModel.load()
        viewModel.markDisclosureShown()

        XCTAssertTrue(viewModel.projection.isEnableReachable)
    }

    func test_enable_withoutDisclosureShown_isNoOp() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        let credentialStore = FakeCredentialStore()
        let viewModel = makeViewModel(projectRoot: projectRoot, credentialStore: credentialStore)

        await viewModel.load()
        // Deliberately never calls markDisclosureShown().
        await viewModel.enable(credential: "sk-ant-should-not-be-stored")

        XCTAssertEqual(viewModel.projection.status, .off)
        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertNil(credentialStore.storedCredential, "enable() must not store a credential when the disclosure gate refuses it")
    }

    // MARK: - Enable (success)

    func test_enable_succeeds_storesCredentialFlipsStatusAndSetsSuccessMessage() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        let credentialStore = FakeCredentialStore()
        let viewModel = makeViewModel(projectRoot: projectRoot, credentialStore: credentialStore)

        await viewModel.load()
        viewModel.markDisclosureShown()
        await viewModel.enable(credential: "sk-ant-test-credential")

        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.projection.status, .on)
        XCTAssertEqual(viewModel.projection.statusLabel, "Status: On")
        XCTAssertEqual(viewModel.successMessage, "AI-assisted classification is now on.")
        XCTAssertEqual(credentialStore.storedCredential, "sk-ant-test-credential")
        XCTAssertFalse(viewModel.isSubmitting)

        // Re-reading independently confirms the real on-disk effect, not
        // just the ViewModel's own in-memory state.
        let configuration = try await makeBridge(projectRoot: projectRoot).readConfiguration()
        XCTAssertTrue(configuration.aiProviderConsent)
    }

    // MARK: - Enable (credential store failure)

    func test_enable_whenCredentialStoreFails_showsErrorAndRemainsOff() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        let credentialStore = FakeCredentialStore()
        credentialStore.storeError = NSError(domain: "test", code: 1)
        let viewModel = makeViewModel(projectRoot: projectRoot, credentialStore: credentialStore)

        await viewModel.load()
        viewModel.markDisclosureShown()
        await viewModel.enable(credential: "sk-ant-test-credential")

        XCTAssertNotNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.errorPresentation?.heading, "Couldn't save your API key")
        XCTAssertEqual(viewModel.projection.status, .off)
        XCTAssertNil(viewModel.successMessage)
    }

    // MARK: - Enable (engine invocation failure)

    func test_enable_whenEngineInvocationFails_showsErrorAndRemainsOff() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        let viewModel = makeViewModel(projectRoot: projectRoot)

        setenv("DI_TEST_FORCE_PROVIDER_FAILURE", "1", 1)
        defer { unsetenv("DI_TEST_FORCE_PROVIDER_FAILURE") }

        await viewModel.load()
        viewModel.markDisclosureShown()
        await viewModel.enable(credential: "sk-ant-test-credential")

        XCTAssertNotNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.errorPresentation?.heading, "Couldn't turn this on")
        XCTAssertEqual(viewModel.projection.status, .off)
        XCTAssertNil(viewModel.successMessage)

        let configuration = try await makeBridge(projectRoot: projectRoot).readConfiguration()
        XCTAssertFalse(configuration.aiProviderConsent, "a failed engine invocation must never be reflected as enabled")
    }

    // MARK: - Disable (success)

    func test_disable_succeeds_flipsStatusAndSetsSuccessMessage() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        try writeConsent(projectRoot: projectRoot, enabled: true)
        let viewModel = makeViewModel(projectRoot: projectRoot)

        await viewModel.load()
        XCTAssertEqual(viewModel.projection.status, .on)

        await viewModel.disable()

        XCTAssertNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.projection.status, .off)
        XCTAssertEqual(viewModel.successMessage, "AI-assisted classification is now off.")

        let configuration = try await makeBridge(projectRoot: projectRoot).readConfiguration()
        XCTAssertFalse(configuration.aiProviderConsent)
    }

    // MARK: - Disable (engine invocation failure)

    func test_disable_whenEngineInvocationFails_showsErrorAndRemainsOn() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        try writeConsent(projectRoot: projectRoot, enabled: true)
        let viewModel = makeViewModel(projectRoot: projectRoot)

        await viewModel.load()

        setenv("DI_TEST_FORCE_PROVIDER_FAILURE", "1", 1)
        defer { unsetenv("DI_TEST_FORCE_PROVIDER_FAILURE") }

        await viewModel.disable()

        XCTAssertNotNil(viewModel.errorPresentation)
        XCTAssertEqual(viewModel.errorPresentation?.heading, "Couldn't turn this off")
        XCTAssertEqual(viewModel.projection.status, .on)
        XCTAssertNil(viewModel.successMessage)
    }

    // MARK: - Dismissal

    func test_dismissError_clearsErrorPresentation() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        let viewModel = makeViewModel(projectRoot: projectRoot)

        setenv("DI_TEST_FORCE_PROVIDER_FAILURE", "1", 1)
        defer { unsetenv("DI_TEST_FORCE_PROVIDER_FAILURE") }

        await viewModel.load()
        viewModel.markDisclosureShown()
        await viewModel.enable(credential: "sk-ant-test-credential")
        XCTAssertNotNil(viewModel.errorPresentation)

        viewModel.dismissError()
        XCTAssertNil(viewModel.errorPresentation)
    }

    func test_dismissSuccessMessage_clearsSuccessMessage() async throws {
        let projectRoot = try makeIsolatedProjectCopy(of: "ProviderSettingsEngineProject")
        let viewModel = makeViewModel(projectRoot: projectRoot)

        await viewModel.load()
        viewModel.markDisclosureShown()
        await viewModel.enable(credential: "sk-ant-test-credential")
        XCTAssertNotNil(viewModel.successMessage)

        viewModel.dismissSuccessMessage()
        XCTAssertNil(viewModel.successMessage)
    }
}

/// An in-memory `CredentialStore` test double — so
/// `AIProviderSettingsViewModelTests` never touches the real OS Keychain.
/// `@unchecked Sendable`: this type is only ever constructed and read from
/// the main actor within these tests (mirroring
/// `AIProviderSettingsViewModel`'s own `@MainActor` isolation of its
/// `credentialStore` property), never accessed concurrently.
private final class FakeCredentialStore: CredentialStore, @unchecked Sendable {
    private(set) var storedCredential: String?
    var storeError: Error?

    func store(_ credential: String) throws {
        if let storeError {
            throw storeError
        }
        storedCredential = credential
    }

    func read() throws -> String? {
        storedCredential
    }

    func delete() throws {
        storedCredential = nil
    }
}
