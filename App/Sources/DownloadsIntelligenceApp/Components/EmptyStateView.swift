import SwiftUI

/// A single calm illustration style, a plain-language heading, a brief
/// explanation, and at most one relevant action (`06 Visual Design
/// System.md` §12, `High-Fidelity UI Specification.md` §15). This is the
/// generic, reusable component itself — the seven concrete named
/// instances (Home — First Run, Home — Caught Up, Scan Complete — No
/// Files, Preview — Nothing Yet, Preview — Already Filed, History —
/// Empty, Reports — Empty; Figma Production Guide §2) are each a specific
/// configuration of this one component, to be wired up by whichever
/// future work package builds that screen's real content — none of those
/// seven instances is itself in scope for WP-GUI-01.
public struct EmptyStateView: View {
    private let systemImageName: String
    private let heading: String
    private let explanation: String
    private let primaryActionTitle: String?
    private let primaryAction: (() -> Void)?
    private let secondaryActionTitle: String?
    private let secondaryAction: (() -> Void)?

    /// At most one primary and one secondary action — never more than one
    /// competing primary action (`High-Fidelity UI Specification.md` §15:
    /// "always exactly one relevant next step"), enforced here by the API
    /// shape itself rather than by a runtime check.
    public init(
        systemImageName: String,
        heading: String,
        explanation: String,
        primaryActionTitle: String? = nil,
        primaryAction: (() -> Void)? = nil,
        secondaryActionTitle: String? = nil,
        secondaryAction: (() -> Void)? = nil
    ) {
        self.systemImageName = systemImageName
        self.heading = heading
        self.explanation = explanation
        self.primaryActionTitle = primaryActionTitle
        self.primaryAction = primaryAction
        self.secondaryActionTitle = secondaryActionTitle
        self.secondaryAction = secondaryAction
    }

    public var body: some View {
        VStack(spacing: 16) {
            Image(systemName: systemImageName)
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
                // Decorative only — the heading/explanation text below
                // fully carries the meaning on its own (`High-Fidelity UI
                // Specification.md` §15's accessibility guidance).
                .accessibilityHidden(true)
            Text(heading)
                .font(.title2.weight(.semibold))
                .accessibilityAddTraits(.isHeader)
            Text(explanation)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            if let primaryActionTitle, let primaryAction {
                PrimaryButton(primaryActionTitle, action: primaryAction)
                    .fixedSize()
            }
            if let secondaryActionTitle, let secondaryAction {
                SecondaryButton(secondaryActionTitle, action: secondaryAction)
                    .fixedSize()
            }
        }
        .frame(maxWidth: 360)
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
