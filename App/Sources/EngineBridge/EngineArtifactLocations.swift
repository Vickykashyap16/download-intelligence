import Foundation

/// The single, shared source of truth for where every on-disk artifact this
/// package reads actually lives, relative to the engine project root. Every
/// artifact reader (`ConfigurationReader`, `ActionLogReader`,
/// `MetadataStoreReader`, `ReportsReader`) is initialized with one of these
/// rather than independently constructing paths — the exact "do not
/// duplicate parsing logic" requirement for WP-GUI-00's artifact readers,
/// applied one level below parsing, to path construction itself: if the
/// real engine ever moves where a file lives, exactly one type needs to
/// change.
///
/// Every path here mirrors a real, already-confirmed location in the real,
/// frozen engine — none is invented or guessed:
/// `src/storage/database.py`'s `metadata_store_path()`,
/// `src/storage/runtime_io.py`'s `action_log_path()`,
/// `write_daily_summary()`/`write_weekly_summary()`/
/// `write_duplicate_report()`/`write_storage_report()`, and the real,
/// observed location of the sources configuration file
/// (`src/config/sources.yaml`).
public struct EngineArtifactLocations: Sendable {
    public let projectRootURL: URL

    public init(projectRootURL: URL) {
        self.projectRootURL = projectRootURL
    }

    /// `src/config/sources.yaml` — the engine's own configuration file
    /// (sources, execution mode, destination root, provider selection,
    /// AI-provider consent).
    public var configurationFileURL: URL {
        projectRootURL
            .appendingPathComponent("src")
            .appendingPathComponent("config")
            .appendingPathComponent("sources.yaml")
    }

    /// `Runtime/Logs/action_log.jsonl` — the sole, authoritative,
    /// append-only record of business actions. Per
    /// `GUI Architecture Specification.md` §15, this is never merged with
    /// the GUI's own separate application log.
    public var actionLogURL: URL {
        projectRootURL
            .appendingPathComponent("Runtime")
            .appendingPathComponent("Logs")
            .appendingPathComponent("action_log.jsonl")
    }

    /// `Database/Metadata/metadata_store.json` — the cumulative JSON array
    /// of `FileRecord` objects the engine maintains across every run.
    public var metadataStoreURL: URL {
        projectRootURL
            .appendingPathComponent("Database")
            .appendingPathComponent("Metadata")
            .appendingPathComponent("metadata_store.json")
    }

    /// The directory containing dated Daily Summary reports
    /// (`summary_YYYY-MM-DD.md`, one file per day generated).
    public var dailySummaryDirectoryURL: URL {
        projectRootURL
            .appendingPathComponent("Runtime")
            .appendingPathComponent("Reports")
            .appendingPathComponent("Daily Summary")
    }

    /// The directory containing dated Weekly Summary reports
    /// (`summary_YYYY-Www.md`, ISO week numbering, one file per week
    /// generated).
    public var weeklySummaryDirectoryURL: URL {
        projectRootURL
            .appendingPathComponent("Runtime")
            .appendingPathComponent("Reports")
            .appendingPathComponent("Weekly Summary")
    }

    /// `Runtime/Reports/Duplicate Report/duplicate_report.md` — a single
    /// file, overwritten on each `report` invocation, not dated.
    public var duplicateReportURL: URL {
        projectRootURL
            .appendingPathComponent("Runtime")
            .appendingPathComponent("Reports")
            .appendingPathComponent("Duplicate Report")
            .appendingPathComponent("duplicate_report.md")
    }

    /// `Runtime/Reports/Storage Report/storage_report.md` — a single file,
    /// overwritten on each `report` invocation, not dated.
    public var storageReportURL: URL {
        projectRootURL
            .appendingPathComponent("Runtime")
            .appendingPathComponent("Reports")
            .appendingPathComponent("Storage Report")
            .appendingPathComponent("storage_report.md")
    }

    /// `Release/VERSIONS.md` — the file `src/cli.py`'s own `_cmd_version()`
    /// reads to answer the real `version` command, containing a line of the
    /// exact form `**Pipeline Version: X.Y.Z**`. `EngineVersionReader`
    /// reads this same file directly rather than invoking the CLI's
    /// `version` subcommand and parsing its printed stdout, per WP-GUI-00's
    /// own Technical Notes preference for re-reading a stable on-disk
    /// artifact over parsing free-text process output wherever structured
    /// detail is needed — and a version string used to gate every other
    /// engine invocation is exactly that kind of structured detail.
    public var versionsFileURL: URL {
        projectRootURL
            .appendingPathComponent("Release")
            .appendingPathComponent("VERSIONS.md")
    }
}
