import SwiftUI
import EngineBridge

/// Review Detail (`High-Fidelity UI Specification.md` §6) — the
/// `approval_required` variant: full identity, confidence chip, complete
/// breakdown, an Edit affordance, and equal-weight Reject/Approve. Reached
/// only as state nested under Review Queue, never a separate `AppSection`
/// (`GUI Architecture Specification.md` line 99); "Back to queue" is a
/// local state transition (line 102), not a fresh navigation.
///
/// Edit has no real backing capability yet — no inline rename/destination
/// editor component exists anywhere in this codebase — so, like
/// `FlaggedCardView`'s own Reclassify, it is a disclosed, honest stub
/// rather than invented machinery outside this work package's scope.
public struct ReviewDetailView: View {
    private let projection: ReviewDetailProjection
    private let onApprove: () -> Void
    private let onReject: () -> Void
    private let onBackToQueue: () -> Void

    @State private var showsEditStubNotice = false

    public init(
        projection: ReviewDetailProjection,
        onApprove: @escaping () -> Void,
        onReject: @escaping () -> Void,
        onBackToQueue: @escaping () -> Void
    ) {
        self.projection = projection
        self.onApprove = onApprove
        self.onReject = onReject
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
                    tier: .approvalRequired,
                    confidenceScore: projection.confidenceScore,
                    isDuplicate: projection.isDuplicate,
                    flagReason: nil,
                    breakdown: projection.breakdown
                )

                VStack(alignment: .leading, spacing: 8) {
                    Button("Edit") { showsEditStubNotice = true }
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.accentColor)
                    if showsEditStubNotice {
                        Text("Editing isn't built yet — that's a future work package.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                // Equal-weight Reject/Approve (§6: neither reads as the
                // default path) — both `SecondaryButton`, unlike Preview/
                // Scan Complete's single dominant `PrimaryButton`.
                HStack(spacing: 12) {
                    SecondaryButton("Reject", action: onReject)
                    SecondaryButton("Approve", action: onApprove)
                }
            }
            .padding(32)
            .frame(maxWidth: 560, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
