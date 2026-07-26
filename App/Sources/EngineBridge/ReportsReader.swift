import Foundation

/// Identifies which of the four real report types
/// (`src/storage/runtime_io.py`'s `write_daily_summary()`,
/// `write_weekly_summary()`, `write_duplicate_report()`,
/// `write_storage_report()`) a given `ReportContent` came from.
public enum ReportKind: Equatable, Sendable {
    case dailySummary
    case weeklySummary
    case duplicateReport
    case storageReport
}

/// The raw content of one report file, read exactly as written by the
/// engine. `markdownText` is never parsed, reformatted, or summarized by
/// this package — reports are Markdown intended for direct display, and
/// `GUI Architecture Specification.md` §15's "never paraphrase engine
/// output" principle applies here just as it does to error text and log
/// content: the Reports screen shows what the engine actually wrote.
public struct ReportContent: Equatable, Sendable {
    public let kind: ReportKind
    public let fileURL: URL
    public let markdownText: String

    public init(kind: ReportKind, fileURL: URL, markdownText: String) {
        self.kind = kind
        self.fileURL = fileURL
        self.markdownText = markdownText
    }
}

/// Reads the four real report files under `Runtime/Reports/`, exactly as
/// they exist on disk today. Every report type is optional at the file
/// level — a fresh installation, or one that has never run `report`, has
/// none of these yet, and that is the Reports screen's own documented
/// Empty State (`High-Fidelity UI Specification.md` §11), not an error —
/// so every read method here returns `nil` for "not generated yet" rather
/// than throwing.
public struct ReportsReader: Sendable {
    private let locations: EngineArtifactLocations

    public init(locations: EngineArtifactLocations) {
        self.locations = locations
    }

    /// `Runtime/Reports/Duplicate Report/duplicate_report.md` — a single,
    /// overwritten file, not dated.
    public func readDuplicateReport() throws -> ReportContent? {
        try readSingleFileReport(kind: .duplicateReport, url: locations.duplicateReportURL)
    }

    /// `Runtime/Reports/Storage Report/storage_report.md` — a single,
    /// overwritten file, not dated.
    public func readStorageReport() throws -> ReportContent? {
        try readSingleFileReport(kind: .storageReport, url: locations.storageReportURL)
    }

    /// The most recently generated Daily Summary
    /// (`summary_YYYY-MM-DD.md`), if any have ever been generated.
    public func readLatestDailySummary() throws -> ReportContent? {
        try readLatestDatedReport(
            kind: .dailySummary,
            directory: locations.dailySummaryDirectoryURL,
            filenamePrefix: "summary_"
        )
    }

    /// The most recently generated Weekly Summary
    /// (`summary_YYYY-Www.md`, ISO week numbering), if any have ever been
    /// generated.
    public func readLatestWeeklySummary() throws -> ReportContent? {
        try readLatestDatedReport(
            kind: .weeklySummary,
            directory: locations.weeklySummaryDirectoryURL,
            filenamePrefix: "summary_"
        )
    }

    // MARK: - Shared helpers (no duplicated parsing/lookup logic between report kinds)

    private func readSingleFileReport(kind: ReportKind, url: URL) throws -> ReportContent? {
        guard FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }
        do {
            let text = try String(contentsOf: url, encoding: .utf8)
            return ReportContent(kind: kind, fileURL: url, markdownText: text)
        } catch {
            throw EngineBridgeError.artifactUnreadable(path: url.path, reason: String(describing: error))
        }
    }

    /// Finds and reads the most recent report in a directory of dated
    /// report files. Real filenames (`summary_YYYY-MM-DD.md`,
    /// `summary_YYYY-Www.md`) are constructed so that plain lexicographic
    /// string sorting already matches chronological order — zero-padded
    /// year/month/day and ISO week numbering both sort correctly as
    /// strings — so finding "the latest" never requires parsing a date out
    /// of the filename, only sorting the filenames themselves.
    private func readLatestDatedReport(
        kind: ReportKind,
        directory: URL,
        filenamePrefix: String
    ) throws -> ReportContent? {
        guard FileManager.default.fileExists(atPath: directory.path) else {
            return nil
        }

        let entries: [URL]
        do {
            entries = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        } catch {
            throw EngineBridgeError.artifactUnreadable(path: directory.path, reason: String(describing: error))
        }

        guard let latestURL = entries
            .filter({ $0.lastPathComponent.hasPrefix(filenamePrefix) && $0.pathExtension == "md" })
            .sorted(by: { $0.lastPathComponent < $1.lastPathComponent })
            .last
        else {
            return nil
        }

        do {
            let text = try String(contentsOf: latestURL, encoding: .utf8)
            return ReportContent(kind: kind, fileURL: latestURL, markdownText: text)
        } catch {
            throw EngineBridgeError.artifactUnreadable(path: latestURL.path, reason: String(describing: error))
        }
    }
}
