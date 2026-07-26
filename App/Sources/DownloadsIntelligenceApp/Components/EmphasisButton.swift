import SwiftUI

/// Shared rendering engine for `PrimaryButton` and `SecondaryButton`. The
/// Design System documents these as two distinct components (`06 Visual
/// Design System.md` §7: "Buttons — Primary" / "Buttons — Secondary"),
/// each with its own Figma component name, but their five-state behavior
/// (`Downloads Intelligence — Figma Design Production Guide.md` §2:
/// "Default / Hover / Pressed / Focused / Disabled") is identical
/// mechanics with a different emphasis look — built once, here, and never
/// re-implemented per call site, per `GUI Architecture Specification.md`
/// §4's "one implementation per component, reused everywhere" rule.
struct EmphasisButton: View {
    enum Emphasis {
        case primary
        case secondary
    }

    let title: String
    let emphasis: Emphasis
    let isDisabled: Bool
    let action: () -> Void

    @State private var isHovered = false
    @State private var isPressed = false
    @FocusState private var isFocused: Bool

    private var visualState: ButtonVisualState {
        ButtonVisualState.resolve(
            isEnabled: !isDisabled,
            isPressed: isPressed,
            isFocused: isFocused,
            isHovered: isHovered
        )
    }

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.body.weight(emphasis == .primary ? .semibold : .regular))
                .padding(.vertical, 12)
                .padding(.horizontal, 20)
        }
        .buttonStyle(.plain)
        .background(backgroundColor)
        .foregroundColor(foregroundColor)
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .strokeBorder(borderColor, lineWidth: emphasis == .secondary || visualState == .focused ? 1 : 0)
        )
        .disabled(isDisabled)
        .focusable(true)
        .focused($isFocused)
        .onHover { hovering in isHovered = hovering }
        .simultaneousGesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in isPressed = true }
                .onEnded { _ in isPressed = false }
        )
        .accessibilityAddTraits(.isButton)
        .accessibilityLabel(Text(title))
    }

    // Every branch below reads directly from `06 Visual Design System.md`
    // §3's purpose/rarity rules (Primary used once per screen for the main
    // action; Secondary always visibly less prominent than Primary without
    // reading as disabled; Disabled distinguishable from ordinary
    // secondary-emphasis content) — no hex values are introduced, only the
    // system's own semantic `Color.accentColor`/`Color.secondary`, per that
    // section's explicit "no hex values are specified anywhere" instruction
    // deferring exact values to a real visual-design pass.
    private var backgroundColor: Color {
        switch emphasis {
        case .primary:
            switch visualState {
            case .disabled: return Color.accentColor.opacity(0.35)
            case .pressed: return Color.accentColor.opacity(0.75)
            case .hovered, .focused: return Color.accentColor.opacity(0.9)
            case .normal: return Color.accentColor
            }
        case .secondary:
            switch visualState {
            case .disabled: return Color.secondary.opacity(0.08)
            case .pressed: return Color.secondary.opacity(0.24)
            case .hovered, .focused: return Color.secondary.opacity(0.16)
            case .normal: return Color.secondary.opacity(0.1)
            }
        }
    }

    private var foregroundColor: Color {
        switch emphasis {
        case .primary: return .white
        case .secondary: return isDisabled ? Color.primary.opacity(0.35) : Color.primary
        }
    }

    private var borderColor: Color {
        visualState == .focused ? Color.accentColor : Color.secondary.opacity(0.3)
    }
}

/// The single most visually confident interactive element on any screen it
/// appears on — used once per screen for that screen's one primary action
/// (`06 Visual Design System.md` §7).
public struct PrimaryButton: View {
    private let title: String
    private let isDisabled: Bool
    private let action: () -> Void

    public init(_ title: String, isDisabled: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.isDisabled = isDisabled
        self.action = action
    }

    public var body: some View {
        EmphasisButton(title: title, emphasis: .primary, isDisabled: isDisabled, action: action)
    }
}

/// Visually quieter than `PrimaryButton` but still clearly interactive —
/// never so muted it reads as disabled (`06 Visual Design System.md` §7) —
/// used for "Cancel," "Back," and similar non-primary actions.
public struct SecondaryButton: View {
    private let title: String
    private let isDisabled: Bool
    private let action: () -> Void

    public init(_ title: String, isDisabled: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.isDisabled = isDisabled
        self.action = action
    }

    public var body: some View {
        EmphasisButton(title: title, emphasis: .secondary, isDisabled: isDisabled, action: action)
    }
}
