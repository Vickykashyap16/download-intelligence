import SwiftUI
import AppKit

/// Restores the native window's size and position across launches via
/// AppKit's own frame-autosave mechanism (`GUI Architecture Specification.md`
/// §5: "The window remembers its size and position across launches"). This
/// is standard, expected native behavior, not custom logic — `NSWindow`
/// already does this for any window given a stable autosave name; this
/// view exists only to reach the underlying `NSWindow` that SwiftUI's
/// `WindowGroup` doesn't otherwise expose a handle to.
struct WindowAccessor: NSViewRepresentable {
    let autosaveName: String

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            view.window?.setFrameAutosaveName(autosaveName)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}
