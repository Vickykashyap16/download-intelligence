import SwiftUI

/// "a folder-path display treatment (icon + path + validation checkmark)
/// reused identically across steps 1 and 2 and recapped in step 3"
/// (`High-Fidelity UI Specification.md` §16, Component Usage) — built once,
/// here, as a shared component rather than per-step markup, per `GUI
/// Architecture Specification.md` §4's "one implementation per component,
/// reused everywhere" rule. Settings' own future folder fields are
/// documented to reuse this same presentation ("Icons: a folder icon
/// accompanying each path field, consistent with First Run Experience's
/// presentation" — §16-adjacent Settings content spec), so this lives
/// alongside the other shared components rather than inside `Onboarding/`.
public struct FolderPathView: View {
    private let path: String
    private let validationMessage: String?
    private let isValidating: Bool

    /// - Parameters:
    ///   - path: the literal folder path to display (§16, Content
    ///     Specification: "Metadata: the literal folder paths shown at each
    ///     step").
    ///   - validationMessage: `nil` shows the checkmark (valid, or not yet
    ///     known/recap context); non-`nil` replaces it with that
    ///     plain-language message (§16, States: "the checkmark becomes a
    ///     plain-language inline message").
    ///   - isValidating: shows a brief loading indicator instead of either
    ///     (§16, States: "Loading: brief, if folder validation takes a
    ///     perceptible moment").
    public init(path: String, validationMessage: String?, isValidating: Bool) {
        self.path = path
        self.validationMessage = validationMessage
        self.isValidating = isValidating
    }

    public var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "folder")
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(path)
                .font(.body)
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
            Spacer(minLength: 12)
            trailingIndicator
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Color.secondary.opacity(0.08))
        )
        // "the folder icon and validation checkmark are always paired with
        // the plain-language path text, never icon-only" (§16,
        // Accessibility) — the path text above already carries the
        // meaning; this container-level label adds only the validation
        // state, never duplicating icon-only meaning.
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityDescription)
    }

    @ViewBuilder
    private var trailingIndicator: some View {
        if isValidating {
            ProgressView()
                .controlSize(.small)
        } else if let validationMessage {
            Label(validationMessage, systemImage: "exclamationmark.circle")
                .font(.caption)
                .foregroundStyle(.secondary)
                .labelStyle(.titleAndIcon)
        } else {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
        }
    }

    private var accessibilityDescription: String {
        if isValidating {
            return "\(path), checking"
        } else if let validationMessage {
            return "\(path), \(validationMessage)"
        } else {
            return "\(path), valid"
        }
    }
}
