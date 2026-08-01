import SwiftUI

/// Execute's confirmation state (`High-Fidelity UI Specification.md` §8;
/// `Wireframes — MVP.md` screen 12). Single content column: count/heading →
/// explanatory line → full itemized list → undo-guarantee reassurance line
/// → Cancel/Confirm action pair — the exact content grouping §8's Layout
/// Specification names. The itemized list scrolls independently while the
/// heading, reassurance line, and action buttons remain anchored (§8: "so
/// the commit decision is never accidentally made without having had the
/// chance to scroll and inspect the list").
///
/// No Confidence Chip per row and no empty state of its own — both by §8's
/// own content spec ("tier is already implied... redundant per row") and
/// States spec ("this screen is only reached when there is a non-zero
/// auto-tier batch to confirm"); `ExecuteFlowView` handles the
/// `.nothingToFile` case with a distinct, dedicated presentation rather
/// than routing it through this view.
public struct ExecuteConfirmationView: View {
    private let projection: ExecuteConfirmationProjection
    private let onFileThem: () -> Void
    private let onCancel: () -> Void
    @AccessibilityFocusState private var isHeadingFocused: Bool

    public init(
        projection: ExecuteConfirmationProjection,
        onFileThem: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) {
        self.projection = projection
        self.onFileThem = onFileThem
        self.onCancel = onCancel
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Heading + explanatory line + reassurance line + buttons stay
            // anchored; only the itemized list below scrolls independently
            // (§8 Layout Specification).
            Text("About to file \(projection.totalCount) item\(projection.totalCount == 1 ? "" : "s").")
                .font(.title.weight(.semibold))
                .accessibilityAddTraits(.isHeader)
                .accessibilityFocused($isHeadingFocused)

            Text("\(projection.totalCount) auto-approved file\(projection.totalCount == 1 ? "" : "s"), based on your confidence settings — see the full list below.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .padding(.top, 8)

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(projection.fileRows, id: \.fileID) { row in
                        fileRow(row)
                        if row.fileID != projection.fileRows.last?.fileID {
                            Divider()
                        }
                    }
                }
            }
            .frame(maxHeight: 360)
            .padding(.top, 24)
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(Color.secondary.opacity(0.2), lineWidth: 1)
            )

            Text("This can be undone afterward, in full or file by file.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .padding(.top, 16)

            HStack(spacing: 12) {
                SecondaryButton("Cancel", action: onCancel)
                PrimaryButton("File them", action: onFileThem)
            }
            .padding(.top, 24)
        }
        .padding(32)
        .frame(maxWidth: 560, alignment: .leading)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onAppear { isHeadingFocused = true }
    }

    /// Full before → after filename/destination per row (§8 Content
    /// Specification), no per-row action beyond inspection — this is the
    /// same "no per-row interaction" restriction `PreviewView.fileRow`
    /// already applies, minus the Confidence Chip §8 explicitly omits here.
    @ViewBuilder
    private func fileRow(_ row: ExecuteConfirmationProjection.FileRow) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Text(row.originalName)
                    .foregroundStyle(row.suggestedName != nil ? .secondary : .primary)
                if let suggestedName = row.suggestedName {
                    Image(systemName: "arrow.right")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                    Text(suggestedName)
                }
            }
            .font(.body)
            .accessibilityElement(children: .combine)
            if let destination = row.suggestedDestination {
                Text(destination)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
