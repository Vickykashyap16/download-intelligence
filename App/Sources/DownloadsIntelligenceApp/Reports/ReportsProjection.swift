import Foundation
import EngineBridge

/// The read-through projection Reports renders — a pure, deterministic,
/// I/O-free computation over the four `ReportContent?` values the Engine
/// Bridge already reads verbatim from `Runtime/Reports/*` (`ReportsReader`,
/// WP-GUI-00). No filesystem I/O of its own, mirroring `HistoryProjection`/
/// `ExecuteResultProjection`'s own established "pure model over already-read
/// data" pattern rather than inventing a new one.
///
/// **What this projection deliberately does not do.** It never recalculates,
/// reinterprets, or regenerates a single figure the engine already rendered
/// (`Desktop Implementation Blueprint.md` §6's "GUI is a presentation layer
/// only," restated in `GUI Engineering Work Packages.md`'s WP-GUI-10
/// Technical Notes: "no figure shown in any report sub-view may be
/// recalculated or reformatted differently than what the CLI's own `report`
/// command produces"). This type's only job is **structural** extraction —
/// splitting one Markdown document into the ordered sequence of bullet-list
/// and pipe-table sections it already contains — never touching a cell's
/// own text. Every one of `src/pipeline/reporting.py`'s four
/// `generate_*()`/`_render_*()` functions renders the same three-part shape
/// confirmed by direct reading of that file: a `# Title` line, a leading
/// run of `- bullet` summary lines, then one or more `## Section` headings
/// each immediately followed by a real Markdown pipe table (header row,
/// `|---|...` separator row, zero or more data rows) — this parser
/// recognizes exactly that shape and nothing more.
///
/// **Fails safely, never drops content (WP-GUI-00's own defensive-parsing
/// precedent, `GUI Engineering Work Packages.md` WP-GUI-10 Markdown
/// handling: "on unexpected Markdown, fall back to rendering the raw text
/// rather than failing").** Any content that doesn't match the expected
/// shape — including the WP-GUI-00 `ReportsReader` fixture's own
/// placeholder prose, which is deliberately not real report content —
/// produces `.rawText(_)` holding the complete, untouched original
/// `markdownText`, never a partial or best-guess structured parse.
public struct ReportsProjection: Equatable, Sendable {
    /// One structurally-recognized section of a report's body, in the order
    /// it appeared in the source document.
    public enum Block: Equatable, Sendable {
        /// A run of consecutive `- ` lines, each with that prefix already
        /// stripped — rendered as plain typographic content (`06 Visual
        /// Design System.md` §4/§8; Hi-Fi §11 Component Usage: "plain
        /// typographic content blocks for narrative summary sections").
        case bullets([String])
        /// One `## Heading` followed by a real Markdown table — `columns`
        /// is the header row's own cell text, `rows` each data row's cell
        /// text, both exactly as written by the engine, never reordered,
        /// recomputed, or re-typed (`06 Visual Design System.md` §4/§8;
        /// Hi-Fi §11 Component Usage: "Table... for structured report
        /// content").
        case table(heading: String, columns: [String], rows: [[String]])
    }

    /// One report type's fully-parsed (or safely-unparsed) content.
    public struct Report: Equatable, Sendable {
        public enum Content: Equatable, Sendable {
            case structured(title: String, blocks: [Block])
            /// The complete, untouched source text — used whenever the
            /// document didn't match the expected heading/bullet/table
            /// shape.
            case rawText(String)
        }

        public let kind: ReportKind
        public let fileURL: URL
        public let content: Content

        public init(kind: ReportKind, fileURL: URL, content: Content) {
            self.kind = kind
            self.fileURL = fileURL
            self.content = content
        }
    }

    public let dailySummary: Report?
    public let weeklySummary: Report?
    public let duplicateReport: Report?
    public let storageReport: Report?

    /// Hi-Fi §11 Empty state: "'No reports generated yet' if `report` has
    /// never been run" — true only when all four artifacts are absent, as
    /// opposed to one specific report type being structurally present but
    /// carrying zero data rows (e.g. "No duplicates found this period"),
    /// which is a per-report, per-view concern this type does not decide on
    /// behalf of its caller.
    public var isEmpty: Bool {
        dailySummary == nil && weeklySummary == nil && duplicateReport == nil && storageReport == nil
    }

    public init(dailySummary: Report?, weeklySummary: Report?, duplicateReport: Report?, storageReport: Report?) {
        self.dailySummary = dailySummary
        self.weeklySummary = weeklySummary
        self.duplicateReport = duplicateReport
        self.storageReport = storageReport
    }

    public static func compute(
        dailySummary: ReportContent?,
        weeklySummary: ReportContent?,
        duplicateReport: ReportContent?,
        storageReport: ReportContent?
    ) -> ReportsProjection {
        ReportsProjection(
            dailySummary: dailySummary.map(parse),
            weeklySummary: weeklySummary.map(parse),
            duplicateReport: duplicateReport.map(parse),
            storageReport: storageReport.map(parse)
        )
    }

    // MARK: - Parsing (structural only — see type-level documentation)

    private static func parse(_ content: ReportContent) -> Report {
        let lines = content.markdownText.components(separatedBy: "\n")
        if let (title, rest) = parseTitle(lines), let blocks = parseBlocks(rest) {
            return Report(kind: content.kind, fileURL: content.fileURL, content: .structured(title: title, blocks: blocks))
        }
        return Report(kind: content.kind, fileURL: content.fileURL, content: .rawText(content.markdownText))
    }

    /// The first non-blank line must be a top-level `# Title` heading — true
    /// of every real `generate_*()` output. Returns `nil` (triggering the
    /// whole-report raw-text fallback) if not, rather than guessing at a
    /// title.
    private static func parseTitle(_ lines: [String]) -> (title: String, rest: ArraySlice<String>)? {
        var index = 0
        while index < lines.count, isBlank(lines[index]) {
            index += 1
        }
        guard index < lines.count, lines[index].hasPrefix("# ") else { return nil }
        let title = String(lines[index].dropFirst(2))
        return (title, lines[(index + 1)...])
    }

    /// Scans the remainder of the document into an ordered `[Block]`:
    /// blank lines are skipped between blocks; a run of consecutive `- `
    /// lines becomes one `.bullets` block; a `## Heading` line must be
    /// immediately followed (after only blank lines) by a real pipe-table
    /// header row and a separator row, after which consecutive data rows
    /// (matching the header's own column count) become that block's `rows`.
    /// Any line that matches none of these shapes — or a table row whose
    /// cell count doesn't match its own header — aborts the whole parse
    /// (returns `nil`), never producing a partial or best-guess result.
    private static func parseBlocks(_ lines: ArraySlice<String>) -> [Block]? {
        var blocks: [Block] = []
        var index = lines.startIndex
        let end = lines.endIndex

        while index < end {
            if isBlank(lines[index]) {
                index += 1
                continue
            }

            if lines[index].hasPrefix("- ") {
                var bullets: [String] = []
                while index < end, lines[index].hasPrefix("- ") {
                    bullets.append(String(lines[index].dropFirst(2)))
                    index += 1
                }
                blocks.append(.bullets(bullets))
                continue
            }

            if lines[index].hasPrefix("## ") {
                let heading = String(lines[index].dropFirst(3))
                index += 1
                while index < end, isBlank(lines[index]) {
                    index += 1
                }
                guard index < end, let columns = parseTableRow(lines[index]) else { return nil }
                index += 1
                guard index < end, isSeparatorRow(lines[index]) else { return nil }
                index += 1

                var rows: [[String]] = []
                while index < end, !isBlank(lines[index]) {
                    guard let cells = parseTableRow(lines[index]), cells.count == columns.count else { return nil }
                    rows.append(cells)
                    index += 1
                }
                blocks.append(.table(heading: heading, columns: columns, rows: rows))
                continue
            }

            // Unrecognized line shape at the top level — fail safely; the
            // caller falls back to the untouched raw text rather than
            // producing a partial structured result.
            return nil
        }

        return blocks
    }

    /// Splits one `| a | b | c |` line into `["a", "b", "c"]`, trimming
    /// surrounding whitespace from each cell. Returns `nil` for any line
    /// that isn't a pipe-delimited row at all.
    private static func parseTableRow(_ line: String) -> [String]? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("|"), trimmed.hasSuffix("|"), trimmed.count >= 2 else { return nil }
        let inner = trimmed.dropFirst().dropLast()
        return inner.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
    }

    /// A Markdown table separator row: every cell non-empty and composed
    /// solely of `-` characters (e.g. `|---|---|---|`).
    private static func isSeparatorRow(_ line: String) -> Bool {
        guard let cells = parseTableRow(line), !cells.isEmpty else { return false }
        return cells.allSatisfy { cell in !cell.isEmpty && cell.allSatisfy { $0 == "-" } }
    }

    private static func isBlank(_ line: String) -> Bool {
        line.trimmingCharacters(in: .whitespaces).isEmpty
    }
}
