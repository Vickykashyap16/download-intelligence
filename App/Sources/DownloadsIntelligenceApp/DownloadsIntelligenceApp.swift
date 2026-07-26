import SwiftUI
import EngineBridge
import Foundation

/// The application's entry point (`Desktop Implementation Blueprint.md`
/// §2's "Launch" phase: "the operating system starts the application
/// process... its main window is instantiated"). This is the release-
/// configuration assembly point `EngineBridge.Configuration`'s own
/// documentation (WP-GUI-00) defers to "whoever assembles the running
/// application" — the project root, supported engine version range, and
/// GUI log location chosen below are placeholders suitable for local
/// development, expected to be replaced by real packaging/release
/// configuration before distribution; that packaging decision is out of
/// WP-GUI-01's scope.
@main
struct DownloadsIntelligenceApp: App {
    private let bridge: EngineBridge

    init() {
        let projectRoot = ProcessInfo.processInfo.environment["DOWNLOADS_INTELLIGENCE_PROJECT_ROOT"]
            .map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Desktop/Download Intelligence", isDirectory: true)
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let guiLogDirectory = appSupport.appendingPathComponent("DownloadsIntelligence/Logs", isDirectory: true)

        self.bridge = EngineBridge(configuration: .init(
            projectRootURL: projectRoot,
            minimumSupportedEngineVersion: SemanticVersion(major: 0, minor: 8, patch: 0),
            maximumSupportedEngineVersion: SemanticVersion(major: 0, minor: 99, patch: 0),
            guiLogDirectoryURL: guiLogDirectory
        ))
    }

    var body: some Scene {
        WindowGroup {
            AppShell(bridge: bridge)
                .frame(minWidth: 800, minHeight: 500)
        }
    }
}
