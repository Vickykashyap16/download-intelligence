import Foundation

/// The two Dialog variants relevant to a reusable, generic sheet component
/// (Figma Production Guide §2: "Confirmation (two-button) / Result
/// (single-button)"). "Disclosure" is deliberately *not* a third case
/// here: the Guide states it is "used structurally within AI Provider
/// Settings' frame content, not as a separate Dialog component" — adding
/// a third case for it here would misrepresent a screen-specific decision
/// as a general-purpose Dialog variant, which is exactly the kind of new
/// UX decision WP-GUI-01 is not authorized to introduce.
public enum DialogKind: Equatable, Sendable {
    /// Two-button: a non-destructive way out (Cancel/Escape) plus the
    /// action being confirmed.
    case confirmation(confirmTitle: String, cancelTitle: String)
    /// Single-button: acknowledges a completed operation's outcome.
    case result(dismissTitle: String)
}
