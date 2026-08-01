import SwiftUI

/// Undo's confirmation state (`High-Fidelity UI Specification.md` §9;
/// `Wireframes — MVP.md` screen 14). Rendered as a `DialogSheet`
/// (WP-GUI-01, frozen) — Undo is explicitly a Dialog overlaid on the
/// context it was triggered from, "not as a standalone full
/// Sidebar-navigable screen" (§9 Layout Specification), the same
/// two-button `.confirmation` kind `DialogSheet` already models exactly.
///
/// Content grouping matches §9's Content Specification precisely: title
/// "Undo this batch?", supporting sentence naming the real, exact count,
/// "Cancel"/"Undo" as a deliberately equal-weight button pair (Wireframe
/// screen 14, annotation 3: "the one dialog in the whole product allowed
/// to feel this simple, because there's genuinely nothing risky about
/// it").
///
/// Known, disclosed gap: §9 Content Specification also calls for "the
/// dedicated undo icon... accompanies the heading in both states."
/// `DialogSheet` (frozen under WP-GUI-01) has no icon slot in its title —
/// only "Confirmation (two-button) / Result (single-button)" per the Figma
/// Production Guide §2's own scope for that component. Adding one would
/// mean modifying a frozen module, which is outside WP-GUI-08's authorized
/// scope ("the one additive AppShell integration" only). This is a
/// pre-existing content-spec/component gap inherited from WP-GUI-01, not
/// something introduced here — disclosed rather than silently worked
/// around.
public struct UndoConfirmationView: View {
    private let totalToUndo: Int
    private let onUndo: () -> Void
    private let onCancel: () -> Void

    public init(totalToUndo: Int, onUndo: @escaping () -> Void, onCancel: @escaping () -> Void) {
        self.totalToUndo = totalToUndo
        self.onUndo = onUndo
        self.onCancel = onCancel
    }

    public var body: some View {
        DialogSheet(
            title: "Undo this batch?",
            message: "This will move \(totalToUndo) file\(totalToUndo == 1 ? "" : "s") back to their original names and locations in Downloads.",
            kind: .confirmation(confirmTitle: "Undo", cancelTitle: "Cancel"),
            onPrimary: onUndo,
            onCancel: onCancel
        )
    }
}
