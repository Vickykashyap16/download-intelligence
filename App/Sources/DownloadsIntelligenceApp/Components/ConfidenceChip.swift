import SwiftUI
import EngineBridge

/// The single most reused component in the product (`06 Visual Design
/// System.md` §7): tier + optional numeric score, rendered as one of the
/// three fixed tier treatments — never a continuous gradient or dial
/// (`06 Visual Design System.md` §8). All content logic lives in
/// `ConfidenceChipModel`; this view only adds presentation (color, layout)
/// on top of it.
public struct ConfidenceChip: View {
    private let model: ConfidenceChipModel

    public init(tier: Tier, score: Int? = nil) {
        self.model = ConfidenceChipModel(tier: tier, score: score)
    }

    public var body: some View {
        HStack(spacing: 6) {
            Image(systemName: model.iconSystemName)
            Text(model.label)
                .font(.callout.weight(.medium))
            if let score = model.score {
                // Confidence score emphasis (`06 Visual Design System.md`
                // §4): always visually subordinate to the tier label —
                // smaller and lighter, never larger or bolder.
                Text("\(score)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 10)
        .background(backgroundColor, in: Capsule())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.accessibilityLabel)
    }

    // Review Required is a "neutral-but-noticeable, cool-leaning tone,"
    // Approval Required is "a warm, mid-weight tone," and Auto is "the
    // quietest and most settled-feeling of the three, distinct from
    // Success" (`06 Visual Design System.md` §3) — Auto is therefore kept
    // out of the green/Success family deliberately here, using a calmer
    // teal instead, so a future Success treatment never collides with it.
    private var backgroundColor: Color {
        switch model.tier {
        case .auto: return .teal.opacity(0.15)
        case .approvalRequired: return .orange.opacity(0.15)
        case .reviewRequired: return .blue.opacity(0.15)
        case .other: return .gray.opacity(0.15)
        }
    }
}
