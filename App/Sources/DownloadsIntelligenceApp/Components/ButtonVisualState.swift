import Foundation

/// The five button states named explicitly in the Figma Production Guide's
/// Variant Inventory (§2): "Primary / Secondary × Default / Hover / Pressed
/// / Focused / Disabled." This type and `resolve(...)` exist so the
/// precedence between simultaneously-true inputs (e.g. a button can be
/// both hovered and focused at once) is expressed exactly once, as a
/// single pure function, and is unit-testable independent of any actual
/// SwiftUI view hierarchy or live window.
public enum ButtonVisualState: Equatable, Sendable {
    case normal
    case hovered
    case focused
    case pressed
    case disabled

    /// Precedence, highest first: Disabled overrides every other input,
    /// since an unavailable control must never appear interactively
    /// engaged regardless of transient pointer/focus state (`06 Visual
    /// Design System.md` §3's Disabled treatment must "remain
    /// distinguishable" from every other state). Pressed outranks Focused
    /// and Hovered because it reflects the most immediate, active user
    /// input in progress. Focused outranks Hovered because keyboard focus
    /// is a more durable, intentional state than a transient pointer
    /// position.
    public static func resolve(isEnabled: Bool, isPressed: Bool, isFocused: Bool, isHovered: Bool) -> ButtonVisualState {
        if !isEnabled { return .disabled }
        if isPressed { return .pressed }
        if isFocused { return .focused }
        if isHovered { return .hovered }
        return .normal
    }
}
