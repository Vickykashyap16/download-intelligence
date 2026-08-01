import SwiftUI

/// Renders one already-parsed `ReportsProjection.Report`'s content — the
/// structured title/bullets/table sequence, or (for the rare unexpected-
/// Markdown case) the complete raw text, verbatim (`GUI Engineering Work
/// Packages.md` WP-GUI-10 Markdown handling: "on unexpected Markdown, fall
/// back to rendering the raw text rather than failing").
struct ReportSectionView: View {
    let report: ReportsProjection.Report

    var body: some View {
        switch report.content {
        case .rawText(let text):
            Text(text)
                .font(.body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        case .structured(let title, let blocks):
            VStack(alignment: .leading, spacing: 20) {
                // Section register (`06 Visual Design System.md` §4): "the
                // active report's name and period" — Hi-Fi §11 Typography
                // Hierarchy.
                Text(title)
                    .font(.title3.weight(.semibold))
                    .accessibilityAddTraits(.isHeader)
                ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                    blockView(block)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func blockView(_ block: ReportsProjection.Block) -> some View {
        switch block {
        case .bullets(let items):
            // Plain typographic content blocks (Hi-Fi §11 Component Usage)
            // for the narrative summary lines every report type leads with.
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    Text(item)
                        .font(.body)
                }
            }
        case .table(let heading, let columns, let rows):
            VStack(alignment: .leading, spacing: 8) {
                Text(heading)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(.secondary)
                if rows.isEmpty {
                    // Hi-Fi §11 Empty state: "an individual report type
                    // may also show its own lighter empty note... without
                    // implying the others are also empty" — this is that
                    // note, scoped to just this one table section.
                    Text("Nothing here yet.")
                        .font(.body)
                        .foregroundStyle(.secondary)
                } else {
                    ReportTable(columns: columns, rows: rows)
                }
            }
        }
    }
}
