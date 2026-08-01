import SwiftUI
import EngineBridge

/// The flagged "why" view (`High-Fidelity UI Specification.md` §6):
/// shares `ReviewDetailView`'s identity-and-breakdown layout verbatim via
/// `ReviewDetailIdentityView`, but Open/Reclassify only — **neither of the
/// two decision controls the needs-input detail screen offers may ever
/// appear anywhere in this file**, the same structural (not stylistic)
/// requirement `FlaggedCardView` documents for the list card, for the
/// identical reason: a `review_required` item can never be accepted, full
/// stop, and that guarantee has to live in a dedicated type whose own
/// source a reviewer (or `FlaggedViewsStructuralTests`' mechanical check)
/// can verify in isolation, not a runtime branch inside a shared type.
public struct FlaggedDetailView: View {
    private let projection: ReviewDetailProjection
    private let onBackToQueue: () -> Void

    @State private var showsOpenStubNotice = false
    @State private var showsReclassifyStubNotice = false

    public init(
        projection: ReviewDetailProjection,
        onBackToQueue: @escaping () -> Void
    ) {
        self.projection = projection
        self.onBackToQueue = onBackToQueue
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Button("← Back to queue", action: onBackToQueue)
                    .buttonStyle(.plain)
                    .foregroundStyle(Color.accentColor)

                ReviewDetailIdentityView(
                    originalName: projection.originalName,
                    suggestedName: projection.suggestedName,
                    suggestedDestination: projection.suggestedDestination,
                    category: projection.category,
                    tier: .reviewRequired,
                    confidenceScore: nil,
                    isDuplicate: projection.isDuplicate,
                    flagReason: projection.flagReason,
                    breakdown: projection.breakdown
                )

                HStack(spacing: 12) {
                    Button("Open") { showsOpenStubNotice = true }
                    Button("Reclassify") { showsReclassifyStubNotice = true }
                }
                .buttonStyle(.plain)
                .foregroundStyle(Color.accentColor)

                if showsOpenStubNotice {
                    Text("Opening in Finder isn't built yet — that's a future work package.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if showsReclassifyStubNotice {
                    Text("Reclassifying isn't built yet — that's a future work package.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(32)
            .frame(maxWidth: 560, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
