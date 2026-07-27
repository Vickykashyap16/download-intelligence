import AppKit
import Foundation

/// Thin AppKit glue for "Choose a different folder" (§16, User Actions) —
/// the one piece of real macOS system interaction in this work package
/// (§16, Risks: "platform folder-permission dialogs — a real macOS system
/// interaction — can interrupt the flow in ways that are easy to
/// under-test"). Deliberately synchronous and minimal: presents the panel
/// modally and returns the chosen folder, or `nil` if the user cancelled.
///
/// Kept out of `FirstRunExperienceViewModel` entirely and marked `internal`
/// (not `public`) — this is view-layer AppKit glue, not business logic; the
/// ViewModel only ever receives an already-chosen `URL` (via
/// `chooseSourceFolder(_:)`/`chooseDestinationFolder(_:)`), so it remains
/// fully testable without a real window server, exactly as
/// `AppLifecycleController`/`HomeViewModel` remain testable without any
/// other AppKit dependency.
enum FolderPicker {
    static func chooseFolder(startingAt url: URL) -> URL? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.directoryURL = url
        panel.prompt = "Choose"
        return panel.runModal() == .OK ? panel.url : nil
    }
}
