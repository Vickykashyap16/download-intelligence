import SwiftUI

/// The shared Error State component. Full-Screen and Inline share this one
/// implementation (`High-Fidelity UI Specification.md` §14: "the same
/// template scales to both contexts") — `presentation.layout` only affects
/// outer framing, never the underlying content structure or behavior.
public struct ErrorStateView: View {
    private let presentation: ErrorPresentation
    private let onResolutionAction: (() -> Void)?
    @State private var isTechnicalDetailExpanded = false

    public init(_ presentation: ErrorPresentation, onResolutionAction: (() -> Void)? = nil) {
        self.presentation = presentation
        self.onResolutionAction = onResolutionAction
    }

    public var body: some View {
        VStack(alignment: presentation.layout == .fullScreen ? .center : .leading, spacing: 16) {
            // A calm, non-alarmist icon — never a red warning triangle by
            // default (`High-Fidelity UI Specification.md` §14's content
            // spec, `06 Visual Design System.md` §3's color-reservation
            // principle extended to iconography).
            Image(systemName: "exclamationmark.circle")
                .font(.system(size: presentation.layout == .fullScreen ? 36 : 20))
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(presentation.heading)
                .font(presentation.layout == .fullScreen ? .title2.weight(.semibold) : .headline)
                .accessibilityAddTraits(.isHeader)
            Text(presentation.explanation)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(presentation.layout == .fullScreen ? .center : .leading)
            if let resolutionActionTitle = presentation.resolutionActionTitle {
                PrimaryButton(resolutionActionTitle) { onResolutionAction?() }
                    .fixedSize()
            }
            DisclosureGroup(isExpanded: $isTechnicalDetailExpanded) {
                Text(presentation.technicalDetail)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Text("Show technical details")
                    .font(.caption)
            }
        }
        .frame(maxWidth: presentation.layout == .fullScreen ? 420 : .infinity)
        .padding(presentation.layout == .fullScreen ? 32 : 16)
        .frame(maxWidth: .infinity, maxHeight: presentation.layout == .fullScreen ? .infinity : nil)
    }
}
