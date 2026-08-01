import SwiftUI
import EngineBridge

/// A plain, typeset table for structured report content (Hi-Fi §11
/// Component Usage: "Table — for structured report content like the
/// Duplicate or Storage Report"; `06 Visual Design System.md` §8: "Reports
/// lead with plain typographic content and simple tables... never a pie or
/// donut chart"). Named `ReportTable`, not `Table`, to avoid colliding with
/// SwiftUI's own built-in `Table` view.
///
/// Deliberately minimal — WP-GUI-10 is this component's only consumer today
/// (`GUI Engineering Work Packages.md` WP-GUI-10's own Table component
/// note: "implement only the functionality required by WP-GUI-10... do not
/// generalize or expand it beyond the current milestone"): no sorting, no
/// column resizing, no row selection, no pagination. `columns`/`rows` are
/// rendered exactly as `ReportsProjection` already parsed them — structural
/// presentation only, never reinterpreting a cell's own text — with one
/// disclosed exception: a column literally titled "Tier" renders via the
/// shared `ConfidenceChip` component instead of plain text, per Hi-Fi §11's
/// own "Confidence chip placement: used only if a specific report
/// specifically enumerates individual files with their tier... using the
/// same reusable Confidence Chip component for consistency, not a bespoke
/// report-specific badge." `Tier(rawValue:)` already round-trips the exact
/// raw string the engine wrote into that cell (`auto`/`approval_required`/
/// `review_required`), so this is presentation only, not recalculation.
struct ReportTable: View {
    let columns: [String]
    let rows: [[String]]

    private var tierColumnIndex: Int? {
        columns.firstIndex(of: "Tier")
    }

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
            GridRow {
                ForEach(Array(columns.enumerated()), id: \.offset) { _, column in
                    Text(column)
                        .font(.callout.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }
            Divider()
                .gridCellColumns(max(columns.count, 1))
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                GridRow {
                    ForEach(Array(row.enumerated()), id: \.offset) { columnIndex, value in
                        cell(columnIndex: columnIndex, value: value)
                    }
                }
            }
        }
        // Table text register (`06 Visual Design System.md` §4: "Reports
        // content reads closer to Body for sustained reading") — every
        // cell in the same column already uses the same register
        // consistently by construction, since every cell shares this one
        // `.font(.body)` default.
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder
    private func cell(columnIndex: Int, value: String) -> some View {
        if columnIndex == tierColumnIndex {
            ConfidenceChip(tier: Tier(rawValue: value))
        } else {
            Text(value)
                .font(.body)
                .monospacedDigit()
                .lineLimit(1)
                .truncationMode(.middle)
        }
    }
}
