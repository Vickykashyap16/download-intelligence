import SwiftUI

/// The two variants named in the Figma Production Guide §2: Determinate /
/// Indeterminate. Determinate is used "when a real count is known" (`06
/// Visual Design System.md` §7); Indeterminate is the "quiet, non-
/// determinate treatment" for brief, uncountable loading moments (`06
/// Visual Design System.md` §9's Motion System — "no elaborate flourish").
public enum ProgressIndicatorStyle: Equatable, Sendable {
    case determinate(DeterminateProgress)
    case indeterminate
}

public struct ProgressIndicatorView: View {
    private let style: ProgressIndicatorStyle

    public init(_ style: ProgressIndicatorStyle) {
        self.style = style
    }

    public var body: some View {
        switch style {
        case .determinate(let progress):
            VStack(alignment: .leading, spacing: 6) {
                ProgressView(value: progress.fraction)
                Text(progress.label)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .combine)
        case .indeterminate:
            ProgressView()
                .progressViewStyle(.circular)
                .accessibilityLabel("Working")
        }
    }
}
