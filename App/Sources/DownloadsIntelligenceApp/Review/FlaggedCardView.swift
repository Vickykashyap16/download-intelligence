import SwiftUI
import EngineBridge

/// The "Flagged for you" Review Card variant (`High-Fidelity UI
/// Specification.md` §5): Open/Reclassify only — **no code path in this
/// file may ever construct the file-acceptance or file-rejection controls
/// the needs-input card offers**. That is a structural requirement, not a
/// stylistic one (Figma Production Guide, Frame 06: no control anywhere on
/// a "Flagged for you" card may accept it), which is exactly why this is
/// its own dedicated type rather than a second branch inside
/// `NeedsInputCardView` gated by a tier check — a runtime conditional in a
/// shared type still has that control's code present, merely hidden; a
/// separate type does not. `FlaggedViewsStructuralTests` mechanically
/// verifies this file's own source never contains that verb at all.
///
/// Neither Reclassify nor Open has a real backing capability yet: no
/// `reclassify` verb exists in `EngineCommand`, and revealing the file in
/// Finder would need a real file path this card's own projection
/// deliberately doesn't carry (see `ReviewQueueProjection.FlaggedItem`).
/// Both are disclosed, honest stubs here — the same treatment
/// `ReviewQueueViewModel`'s own documentation already establishes for
/// Reclassify, extended to Open for the identical reason rather than
/// silently wiring a callback that would do nothing with no feedback.
public struct FlaggedCardView: View {
    private let item: ReviewQueueProjection.FlaggedItem
    private let focusedFileID: FocusState<String?>.Binding
    private let onOpenWhy: () -> Void

    @State private var showsOpenStubNotice = false
    @State private var showsReclassifyStubNotice = false

    public init(
        item: ReviewQueueProjection.FlaggedItem,
        focusedFileID: FocusState<String?>.Binding,
        onOpenWhy: @escaping () -> Void
    ) {
        self.item = item
        self.focusedFileID = focusedFileID
        self.onOpenWhy = onOpenWhy
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                ConfidenceChip(tier: .reviewRequired)
                if item.isDuplicate {
                    StatusBadge(.duplicate)
                }
                Spacer()
            }

            Text(item.originalName)
                .font(.body.weight(.medium))

            if let category = item.category {
                Text(category.rawValue)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Text(item.flagReason)
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack(spacing: 12) {
                Button("Open") {
                    showsOpenStubNotice = true
                }
                .focused(focusedFileID, equals: item.fileID)
                Button("Reclassify") {
                    showsReclassifyStubNotice = true
                }
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color.accentColor)

            if showsOpenStubNotice {
                Text("Opening in Finder isn't built yet — that's a future work package.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if showsReclassifyStubNotice {
                Text("Reclassifying isn't built yet — that's a future work package.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(20)
        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
        .contentShape(Rectangle())
        .onTapGesture(perform: onOpenWhy)
        .accessibilityElement(children: .contain)
        .accessibilityAction(named: Text("Open detail"), onOpenWhy)
    }
}
