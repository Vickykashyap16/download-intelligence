import SwiftUI
import EngineBridge

/// The "Needs your input" Review Card variant (`High-Fidelity UI
/// Specification.md` §5): inline Approve/Edit/Reject, in that fixed
/// keyboard order (Figma Production Guide, Frame 06 accessibility notes).
/// Kept as its own distinct type — not a single `ReviewCardView` gated by a
/// runtime "is this flagged" flag — so a Flagged card's own type
/// (`FlaggedCardView`) can never, even accidentally, grow an Approve
/// affordance; see that type's own documentation for why this split is a
/// structural safety requirement, not just a style preference.
public struct NeedsInputCardView: View {
    private let item: ReviewQueueProjection.NeedsInputItem
    private let focusedFileID: FocusState<String?>.Binding
    private let onOpenDetail: () -> Void
    private let onApprove: () -> Void
    private let onEdit: () -> Void
    private let onReject: () -> Void

    /// - Parameters:
    ///   - onOpenDetail: opens Review Detail — reachable by clicking the
    ///     card body itself (a mouse convenience only; the spec's own fixed
    ///     keyboard order for this card lists Approve/Edit/Reject alone, so
    ///     keyboard-only users reach Detail via Edit, which routes to the
    ///     same place).
    ///   - onEdit: also routes to Review Detail — the actual edit affordance
    ///     lives there, not inline on the list card.
    public init(
        item: ReviewQueueProjection.NeedsInputItem,
        focusedFileID: FocusState<String?>.Binding,
        onOpenDetail: @escaping () -> Void,
        onApprove: @escaping () -> Void,
        onEdit: @escaping () -> Void,
        onReject: @escaping () -> Void
    ) {
        self.item = item
        self.focusedFileID = focusedFileID
        self.onOpenDetail = onOpenDetail
        self.onApprove = onApprove
        self.onEdit = onEdit
        self.onReject = onReject
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                ConfidenceChip(tier: .approvalRequired, score: item.confidenceScore)
                if item.isDuplicate {
                    StatusBadge(.duplicate)
                }
                Spacer()
            }

            Text(item.originalName)
                .font(.body.weight(.medium))

            HStack(spacing: 6) {
                if let category = item.category {
                    Text(category.rawValue)
                }
                if let destination = item.suggestedDestination {
                    Text("→ \(destination)")
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)

            HStack(spacing: 12) {
                Button("Approve", action: onApprove)
                    .focused(focusedFileID, equals: item.fileID)
                Button("Edit", action: onEdit)
                Button("Reject", action: onReject)
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color.accentColor)
        }
        .padding(20)
        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
        .contentShape(Rectangle())
        .onTapGesture(perform: onOpenDetail)
        .accessibilityElement(children: .contain)
        .accessibilityAction(named: Text("Open detail"), onOpenDetail)
    }
}
