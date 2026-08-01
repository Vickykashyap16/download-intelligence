import SwiftUI
import EngineBridge
import enum EngineBridge.Category

/// The identity/confidence-chip/breakdown layout `ReviewDetailView` (needs-
/// input) and `FlaggedDetailView` (the flagged "why" view) both share
/// verbatim (`High-Fidelity UI Specification.md` §6: the flagged why-view
/// "shares this screen's identity-and-breakdown layout, but omits the
/// decision actions"). Purely presentational — no buttons, no actions —
/// each caller supplies its own distinct action row below this.
struct ReviewDetailIdentityView: View {
    let originalName: String
    let suggestedName: String?
    let suggestedDestination: String?
    let category: Category?
    let tier: Tier
    let confidenceScore: Int?
    let isDuplicate: Bool
    let flagReason: String?
    let breakdown: [ConfidenceDeductionFormatter.DeductionLine]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 8) {
                ConfidenceChip(tier: tier, score: confidenceScore)
                if isDuplicate {
                    StatusBadge(.duplicate)
                }
                Spacer()
            }

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(originalName)
                        .foregroundStyle(suggestedName != nil ? .secondary : .primary)
                    if let suggestedName {
                        Image(systemName: "arrow.right")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .accessibilityHidden(true)
                        Text(suggestedName)
                    }
                }
                .font(.title2.weight(.semibold))
                .accessibilityAddTraits(.isHeader)
                .accessibilityElement(children: .combine)

                if let category {
                    Text(category.rawValue)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                if let suggestedDestination {
                    Text(suggestedDestination)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .truncationMode(.middle)
                }
            }

            if let flagReason {
                Text(flagReason)
                    .font(.callout.weight(.medium))
            }

            if !breakdown.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Confidence breakdown")
                        .font(.headline)
                    ForEach(Array(breakdown.enumerated()), id: \.offset) { _, line in
                        HStack {
                            Text(line.text)
                            Spacer()
                            Text("\(line.points)")
                                .monospacedDigit()
                                .foregroundStyle(.secondary)
                        }
                        .font(.callout)
                    }
                }
                .padding(.top, 8)
            }
        }
    }
}
