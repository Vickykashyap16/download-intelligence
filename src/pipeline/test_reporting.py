"""
Unit tests for pipeline/reporting.py — Module 08 (Logging & Reporting).

Module 08 Implementation Plan.md WP-1 scope: the shared aggregation primitives
`read_action_log_entries_safe()`, `compute_as_of_marker()`, `filter_entries_by_day()`,
and `filter_entries_by_action()` (Module 08 Design.md §7, §12 Layer 1).

WP-2 scope: `generate_daily_summary()` — the real aggregation/rendering logic,
tested below against `Metadata & Log Schema.md`'s own worked example.

WP-3 scope: `generate_duplicate_report()` — a single, continuously-updated
current-state file over every duplicate/superseded-version record (decision 25),
categorized into archived/kept/overridden-by-user.

WP-4 scope: `generate_weekly_summary()` — rolls up already-written Daily Summary
files (never the metadata store) for the requested ISO week, with a narrow
action-log exception solely to disambiguate a missing day (§12 Layer 1's L1
fix). Inherits closed-period (G6/I6) protection transitively from Daily
Summary's own per-day guarantee — no independent week-boundary mechanism.
`generate_storage_report()` remains a NotImplementedError stub, WP-5's own
scope, and is not tested here — the same convention `pipeline/test_execution.py`
already established for its own untouched pre-existing stubs.

Isolated from the project's real `Runtime/Logs/action_log.jsonl` via the same
`monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / ...)`
convention `pipeline/test_execution.py`/`pipeline/test_naming.py` already
established, from the real `Runtime/Reports/` via the equivalent
`monkeypatch.setattr(runtime_io_module, "_RUNTIME_REPORTS_PATH", ...)` convention
`storage/test_runtime_io.py` already established, and from the real
`Database/Metadata/metadata_store.json` via the equivalent
`monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", ...)` convention
`pipeline/test_naming.py`/`pipeline/test_execution.py` already established.

Run with: pytest src/pipeline/test_reporting.py -v
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.classification import Category
from src.models.file_record import FileRecord
from src.pipeline.reporting import (
    compute_as_of_marker,
    filter_entries_by_action,
    filter_entries_by_day,
    generate_daily_summary,
    generate_duplicate_report,
    generate_storage_report,
    generate_weekly_summary,
    read_action_log_entries_safe,
)


def _isolate_action_log(tmp_path, monkeypatch):
    """Same isolation convention pipeline/test_execution.py already established —
    redirect action_log_path()'s target file to a sandboxed tmp_path, never the
    project's real Runtime/Logs/action_log.jsonl."""
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


def _isolate_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_io_module, "_RUNTIME_REPORTS_PATH", tmp_path / "Reports")


def _isolate_metadata_store(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")


def _isolate_all(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_reports(tmp_path, monkeypatch)
    _isolate_metadata_store(tmp_path, monkeypatch)


def _write_raw_lines(tmp_path, lines):
    log_path = tmp_path / "action_log.jsonl"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _entry(batch_id="batch-1", file_id="f1", action="discover",
           timestamp="2026-07-14T10:00:00+00:00", **kwargs):
    entry = {
        "batch_id": batch_id, "file_id": file_id, "action": action,
        "from": None, "to": None, "timestamp": timestamp, "approved_by": "auto",
    }
    entry.update(kwargs)
    return entry


def _record(file_id, name, category=None, tier=None, confidence_score=None,
            suggested_name=None, suggested_destination=None,
            version_group_id=None, version_rank=None, **kwargs):
    """Mirrors pipeline/test_naming.py's own `_record()` helper pattern."""
    return FileRecord(
        file_id=file_id, source_id="downloads", original_name=name,
        original_path=f"/tmp/{name}", current_path=f"/tmp/{name}",
        status="discovered", category=category, tier=tier,
        confidence_score=confidence_score, suggested_name=suggested_name,
        suggested_destination=suggested_destination,
        version_group_id=version_group_id, version_rank=version_rank,
        batch_id="batch-1", **kwargs,
    )


# --- read_action_log_entries_safe() — malformed-line-wrapper ---

class TestReadActionLogEntriesSafe:
    def test_returns_empty_and_zero_when_log_does_not_exist(self, tmp_path, monkeypatch):
        _isolate_action_log(tmp_path, monkeypatch)
        entries, malformed_count = read_action_log_entries_safe()
        assert entries == []
        assert malformed_count == 0

    def test_returns_empty_and_zero_for_an_empty_log_file(self, tmp_path, monkeypatch):
        _isolate_action_log(tmp_path, monkeypatch)
        (tmp_path / "action_log.jsonl").write_text("", encoding="utf-8")
        entries, malformed_count = read_action_log_entries_safe()
        assert entries == []
        assert malformed_count == 0

    def test_reads_every_well_formed_line(self, tmp_path, monkeypatch):
        _isolate_action_log(tmp_path, monkeypatch)
        lines = [json.dumps(_entry(file_id=f"f{i}")) for i in range(3)]
        _write_raw_lines(tmp_path, lines)
        entries, malformed_count = read_action_log_entries_safe()
        assert len(entries) == 3
        assert malformed_count == 0
        assert [e["file_id"] for e in entries] == ["f0", "f1", "f2"]

    def test_skips_a_malformed_line_without_raising(self, tmp_path, monkeypatch):
        _isolate_action_log(tmp_path, monkeypatch)
        lines = [
            json.dumps(_entry(file_id="f1")),
            "{not valid json at all",
            json.dumps(_entry(file_id="f2")),
        ]
        _write_raw_lines(tmp_path, lines)
        entries, malformed_count = read_action_log_entries_safe()
        assert malformed_count == 1
        assert [e["file_id"] for e in entries] == ["f1", "f2"]

    def test_counts_every_malformed_line_independently(self, tmp_path, monkeypatch):
        _isolate_action_log(tmp_path, monkeypatch)
        lines = [
            "not json",
            json.dumps(_entry(file_id="f1")),
            "also not json",
            "{broken",
        ]
        _write_raw_lines(tmp_path, lines)
        entries, malformed_count = read_action_log_entries_safe()
        assert malformed_count == 3
        assert [e["file_id"] for e in entries] == ["f1"]

    def test_all_malformed_returns_empty_entries_and_full_count(self, tmp_path, monkeypatch):
        _isolate_action_log(tmp_path, monkeypatch)
        _write_raw_lines(tmp_path, ["nope", "still nope"])
        entries, malformed_count = read_action_log_entries_safe()
        assert entries == []
        assert malformed_count == 2


# --- compute_as_of_marker() — distinct / tie / empty cases ---

class TestComputeAsOfMarker:
    def test_empty_entries_returns_none(self):
        assert compute_as_of_marker([]) is None

    def test_single_entry_returns_its_own_timestamp(self):
        entries = [_entry(timestamp="2026-07-14T09:00:00+00:00")]
        assert compute_as_of_marker(entries) == "2026-07-14T09:00:00+00:00"

    def test_distinct_timestamps_returns_the_latest(self):
        entries = [
            _entry(file_id="f1", timestamp="2026-07-14T08:00:00+00:00"),
            _entry(file_id="f2", timestamp="2026-07-14T11:30:00+00:00"),
            _entry(file_id="f3", timestamp="2026-07-14T09:15:00+00:00"),
        ]
        assert compute_as_of_marker(entries) == "2026-07-14T11:30:00+00:00"

    def test_tie_at_the_latest_timestamp_returns_that_value(self):
        entries = [
            _entry(file_id="f1", timestamp="2026-07-14T08:00:00+00:00"),
            _entry(file_id="f2", timestamp="2026-07-14T11:30:00+00:00"),
            _entry(file_id="f3", timestamp="2026-07-14T11:30:00+00:00"),
        ]
        assert compute_as_of_marker(entries) == "2026-07-14T11:30:00+00:00"

    def test_order_of_entries_does_not_affect_the_result(self):
        entries = [
            _entry(file_id="f1", timestamp="2026-07-14T11:30:00+00:00"),
            _entry(file_id="f2", timestamp="2026-07-14T08:00:00+00:00"),
        ]
        assert compute_as_of_marker(entries) == "2026-07-14T11:30:00+00:00"


# --- filter_entries_by_day() ---

class TestFilterEntriesByDay:
    def test_keeps_only_entries_on_the_requested_utc_day(self):
        entries = [
            _entry(file_id="f1", timestamp="2026-07-14T08:00:00+00:00"),
            _entry(file_id="f2", timestamp="2026-07-13T23:59:59+00:00"),
            _entry(file_id="f3", timestamp="2026-07-14T23:59:59+00:00"),
            _entry(file_id="f4", timestamp="2026-07-15T00:00:00+00:00"),
        ]
        result = filter_entries_by_day(entries, date(2026, 7, 14))
        assert [e["file_id"] for e in result] == ["f1", "f3"]

    def test_empty_entries_returns_empty(self):
        assert filter_entries_by_day([], date(2026, 7, 14)) == []

    def test_no_matching_day_returns_empty(self):
        entries = [_entry(timestamp="2026-07-01T00:00:00+00:00")]
        assert filter_entries_by_day(entries, date(2026, 7, 14)) == []


# --- filter_entries_by_action() ---

class TestFilterEntriesByAction:
    def test_keeps_only_matching_single_action(self):
        entries = [
            _entry(file_id="f1", action="discover"),
            _entry(file_id="f2", action="classify"),
            _entry(file_id="f3", action="discover"),
        ]
        result = filter_entries_by_action(entries, {"discover"})
        assert [e["file_id"] for e in result] == ["f1", "f3"]

    def test_accepts_a_list_as_well_as_a_set(self):
        entries = [_entry(file_id="f1", action="discover")]
        result = filter_entries_by_action(entries, ["discover", "classify"])
        assert [e["file_id"] for e in result] == ["f1"]

    def test_keeps_entries_matching_any_of_multiple_actions(self):
        entries = [
            _entry(file_id="f1", action="discover"),
            _entry(file_id="f2", action="classify"),
            _entry(file_id="f3", action="detect_duplicates_and_versions"),
        ]
        result = filter_entries_by_action(entries, {"classify", "detect_duplicates_and_versions"})
        assert [e["file_id"] for e in result] == ["f2", "f3"]

    def test_no_matching_action_returns_empty(self):
        entries = [_entry(action="discover")]
        assert filter_entries_by_action(entries, {"classify"}) == []

    def test_empty_entries_returns_empty(self):
        assert filter_entries_by_action([], {"discover"}) == []


# --- Zero-write immutability (Module 08 Design.md §0.3/I1-I3, simplified: no
# FileRecord field and no Database/* file changes at all) ---

class TestZeroWriteImmutability:
    def test_read_action_log_entries_safe_writes_nothing(self, tmp_path, monkeypatch):
        _isolate_action_log(tmp_path, monkeypatch)
        _write_raw_lines(tmp_path, [json.dumps(_entry())])
        before = sorted(p.name for p in tmp_path.iterdir())
        before_content = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")

        read_action_log_entries_safe()

        after = sorted(p.name for p in tmp_path.iterdir())
        after_content = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")
        assert before == after
        assert before_content == after_content

    def test_compute_as_of_marker_writes_nothing(self, tmp_path):
        entries = [_entry(timestamp="2026-07-14T08:00:00+00:00")]
        before = sorted(p.name for p in tmp_path.iterdir())
        compute_as_of_marker(entries)
        after = sorted(p.name for p in tmp_path.iterdir())
        assert before == after

    def test_filter_entries_by_day_writes_nothing(self, tmp_path):
        entries = [_entry(timestamp="2026-07-14T08:00:00+00:00")]
        before = sorted(p.name for p in tmp_path.iterdir())
        filter_entries_by_day(entries, date(2026, 7, 14))
        after = sorted(p.name for p in tmp_path.iterdir())
        assert before == after

    def test_filter_entries_by_action_writes_nothing(self, tmp_path):
        entries = [_entry(action="discover")]
        before = sorted(p.name for p in tmp_path.iterdir())
        filter_entries_by_action(entries, {"discover"})
        after = sorted(p.name for p in tmp_path.iterdir())
        assert before == after

    def test_wp1_helpers_do_not_import_load_or_save_as_bare_names(
        self, tmp_path, monkeypatch
    ):
        """WP-1's own four primitives never import storage.database at all
        (Module 08 owns zero FileRecord fields, G1/G2) — a structural check,
        not just a behavioral one. WP-2's `generate_daily_summary()` has since
        added a *read-only* `storage.database.load_metadata_store()` dependency
        (§5's own explicit dual-source statement for Daily Summary) — see
        `test_generate_daily_summary_never_calls_save_file_record` below for
        the write-side guarantee that still holds."""
        import src.pipeline.reporting as reporting_module

        assert not hasattr(reporting_module, "load_metadata_store")
        assert not hasattr(reporting_module, "save_file_record")

    def test_generate_daily_summary_never_calls_save_file_record(self):
        """Source-level check: `save_file_record()` — the metadata store's only
        write path (`storage/database.py`) — is never referenced anywhere in
        reporting.py, WP-2 included. Module 08 owns zero FileRecord fields and
        this is the one guarantee `hasattr()` alone can't express, since WP-2
        legitimately imports the `database` module itself for its read-only
        `load_metadata_store()` call."""
        import inspect

        import src.pipeline.reporting as reporting_module

        source = inspect.getsource(reporting_module)
        assert "save_file_record" not in source


# --- generate_daily_summary() (WP-2) ---

def _score_confidence(file_id, tier, timestamp="2026-07-14T09:00:00+00:00", **kwargs):
    return _entry(file_id=file_id, action="score_confidence", timestamp=timestamp,
                  details={"tier": tier}, **kwargs)


def _move_rename(file_id, timestamp="2026-07-14T10:00:00+00:00", **kwargs):
    return _entry(file_id=file_id, action="move_rename", timestamp=timestamp, **kwargs)


def _archive_duplicate(file_id, timestamp="2026-07-14T10:00:00+00:00", **kwargs):
    return _entry(file_id=file_id, action="archive_duplicate", timestamp=timestamp, **kwargs)


def _archive_superseded_version(file_id, timestamp="2026-07-14T10:00:00+00:00", **kwargs):
    return _entry(file_id=file_id, action="archive_superseded_version", timestamp=timestamp, **kwargs)


def _detect_duplicates(file_id, duplicate_of=None, timestamp="2026-07-14T09:30:00+00:00", **kwargs):
    return _entry(file_id=file_id, action="detect_duplicates_and_versions", timestamp=timestamp,
                  details={"duplicate_of": duplicate_of}, **kwargs)


def _error(file_id, timestamp="2026-07-14T10:00:00+00:00", **kwargs):
    return _entry(file_id=file_id, action="error", timestamp=timestamp, **kwargs)


class TestGenerateDailySummaryAggregation:
    def test_matches_the_worked_example_scenario_field_for_field(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        day = date(2026, 7, 5)

        lines = [
            json.dumps(_entry(file_id="f1", action="discover", timestamp="2026-07-05T08:00:00+00:00")),
            json.dumps(_score_confidence("f1", "approval_required", timestamp="2026-07-05T08:05:00+00:00")),
            json.dumps(_move_rename("f1", timestamp="2026-07-05T08:10:00+00:00")),
        ]
        _write_raw_lines(tmp_path, lines)

        database_module.save_file_record(_record(
            "f1", "invoice.pdf", category=Category.INVOICE, tier="approval_required",
            confidence_score=82, suggested_name="GST_Invoice_Amazon_2026-07-05.pdf",
            suggested_destination="Finance/",
        ))

        content = Path(generate_daily_summary(day)).read_text(encoding="utf-8")

        assert content.startswith("# Daily Summary — 2026-07-05\n")
        assert "- Files scanned: 1" in content
        assert "- Auto-filed: 0" in content
        assert "- Approval required: 1" in content
        assert "- Review required: 0" in content
        assert "- Duplicates found: 0" in content
        assert "- Versions archived: 0" in content
        assert "- Errors: 0" in content
        assert (
            "| invoice.pdf | GST_Invoice_Amazon_2026-07-05.pdf | Finance/ | Invoice | 82 | approval_required |"
            in content
        )

    def test_auto_filed_approval_required_review_required_counted_by_tier(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [
            json.dumps(_score_confidence("f1", "auto")),
            json.dumps(_score_confidence("f2", "auto")),
            json.dumps(_score_confidence("f3", "approval_required")),
            json.dumps(_score_confidence("f4", "review_required")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Auto-filed: 2" in content
        assert "- Approval required: 1" in content
        assert "- Review required: 1" in content

    def test_files_scanned_counts_discover_entries_only(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [
            json.dumps(_entry(file_id="f1", action="discover")),
            json.dumps(_entry(file_id="f2", action="discover")),
            json.dumps(_entry(file_id="f2", action="classify")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Files scanned: 2" in content

    def test_errors_counts_error_action_entries(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [json.dumps(_error("f1")), json.dumps(_error("f2"))]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Errors: 2" in content

    def test_duplicates_found_excludes_version_relationships(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [
            json.dumps(_detect_duplicates("f1", duplicate_of="f0")),
            json.dumps(_entry(
                file_id="f2", action="detect_duplicates_and_versions",
                timestamp="2026-07-14T09:30:00+00:00",
                details={"duplicate_of": None, "version_group_id": "g1", "version_rank": "superseded"},
            )),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Duplicates found: 1" in content

    def test_duplicates_found_shows_archived_count_when_partial(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [
            json.dumps(_detect_duplicates("f1", duplicate_of="f0")),
            json.dumps(_detect_duplicates("f2", duplicate_of="f0")),
            json.dumps(_archive_duplicate("f1")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Duplicates found: 2 (1 archived)" in content

    def test_duplicates_found_all_archived_matches_worked_example_shorthand(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [
            json.dumps(_detect_duplicates("f1", duplicate_of="f0")),
            json.dumps(_archive_duplicate("f1")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Duplicates found: 1 (archived)" in content

    def test_versions_archived_detail_names_the_latest_sibling(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [json.dumps(_archive_superseded_version("v8"))]
        _write_raw_lines(tmp_path, lines)
        database_module.save_file_record(_record(
            "v8", "Resume_v8.pdf", version_group_id="g1", version_rank="superseded",
        ))
        database_module.save_file_record(_record(
            "v9", "Resume_v9.pdf", version_group_id="g1", version_rank="latest",
        ))
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Versions archived: 1 (Resume_v8.pdf → superseded by Resume_v9.pdf)" in content

    def test_versions_archived_detail_unknown_when_no_latest_sibling_found(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [json.dumps(_archive_superseded_version("v8"))]
        _write_raw_lines(tmp_path, lines)
        database_module.save_file_record(_record(
            "v8", "Resume_v8.pdf", version_group_id="g1", version_rank="superseded",
        ))
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Versions archived: 1 (Resume_v8.pdf → superseded by Unknown)" in content

    def test_multiple_versions_archived_joined_with_semicolons(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [
            json.dumps(_archive_superseded_version("v8")),
            json.dumps(_archive_superseded_version("r1")),
        ]
        _write_raw_lines(tmp_path, lines)
        database_module.save_file_record(_record("v8", "Resume_v8.pdf", version_group_id="g1", version_rank="superseded"))
        database_module.save_file_record(_record("v9", "Resume_v9.pdf", version_group_id="g1", version_rank="latest"))
        database_module.save_file_record(_record("r1", "Report_v1.pdf", version_group_id="g2", version_rank="superseded"))
        database_module.save_file_record(_record("r2", "Report_v2.pdf", version_group_id="g2", version_rank="latest"))
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert (
            "- Versions archived: 2 (Resume_v8.pdf → superseded by Resume_v9.pdf; "
            "Report_v1.pdf → superseded by Report_v2.pdf)" in content
        )

    def test_files_table_includes_every_distinct_filed_file_once(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [
            json.dumps(_move_rename("f1", timestamp="2026-07-14T09:00:00+00:00")),
            json.dumps(_move_rename("f1", timestamp="2026-07-14T09:05:00+00:00")),
            json.dumps(_archive_duplicate("f2", timestamp="2026-07-14T09:10:00+00:00")),
        ]
        _write_raw_lines(tmp_path, lines)
        database_module.save_file_record(_record(
            "f1", "a.pdf", category=Category.DOCUMENT, tier="auto", confidence_score=95,
            suggested_name="A.pdf", suggested_destination="Docs/",
        ))
        database_module.save_file_record(_record(
            "f2", "b.pdf", category=Category.IMAGE, tier="auto", confidence_score=90,
            suggested_name="B.jpg", suggested_destination="Images/",
        ))
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert content.count("| a.pdf |") == 1
        assert "| b.pdf | B.jpg | Images/ | Image | 90 | auto |" in content

    def test_files_table_row_shows_unknown_for_missing_metadata_record(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [json.dumps(_move_rename("ghost"))]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "| Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |" in content

    def test_files_table_row_shows_unknown_for_missing_individual_field(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [json.dumps(_move_rename("f1"))]
        _write_raw_lines(tmp_path, lines)
        database_module.save_file_record(_record("f1", "a.pdf"))
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "| a.pdf | Unknown | Unknown | Unknown | Unknown | Unknown |" in content


class TestGenerateDailySummaryEmptyDay:
    def test_empty_day_renders_full_zeroed_shape(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert content == (
            "# Daily Summary — 2026-07-14\n"
            "\n"
            "- Files scanned: 0\n"
            "- Auto-filed: 0\n"
            "- Approval required: 0\n"
            "- Review required: 0\n"
            "- Duplicates found: 0\n"
            "- Versions archived: 0\n"
            "- Errors: 0\n"
            "\n"
            "## Files\n"
            "| Original | New Name | Destination | Category | Confidence | Tier |\n"
            "|---|---|---|---|---|---|\n"
        )

    def test_no_action_log_file_at_all_is_treated_as_an_empty_day(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        assert not (tmp_path / "action_log.jsonl").exists()
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Files scanned: 0" in content

    def test_activity_on_other_days_does_not_leak_into_this_day(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [json.dumps(_entry(file_id="f1", action="discover", timestamp="2026-07-13T23:59:59+00:00"))]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Files scanned: 0" in content


class TestGenerateDailySummaryMalformedLineDisclosure:
    def test_normal_day_with_no_malformed_lines_has_no_disclosure_line(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [json.dumps(_entry(file_id="f1", action="discover"))]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "Malformed" not in content

    def test_malformed_lines_are_disclosed_and_do_not_crash_generation(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [
            json.dumps(_entry(file_id="f1", action="discover", timestamp="2026-07-14T08:00:00+00:00")),
            "{not valid json",
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_daily_summary(date(2026, 7, 14))).read_text(encoding="utf-8")
        assert "- Files scanned: 1" in content
        assert "- Malformed log lines skipped: 1" in content


class TestGenerateDailySummaryClosedDayProtection:
    """§11, `ARCHITECTURE_DECISIONS.md` decision 27, G6: a closed (prior UTC)
    day's file, once written, is never silently rewritten."""

    def test_a_closed_past_day_with_an_existing_file_is_never_rewritten(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        past_day = date(2020, 1, 1)
        lines = [json.dumps(_entry(file_id="f1", action="discover", timestamp="2020-01-01T08:00:00+00:00"))]
        _write_raw_lines(tmp_path, lines)

        first_path = generate_daily_summary(past_day)
        first_content = Path(first_path).read_text(encoding="utf-8")
        assert "- Files scanned: 1" in first_content

        # New activity is appended for that same past day after the fact —
        # a second call must not pick it up.
        lines.append(json.dumps(_entry(file_id="f2", action="discover", timestamp="2020-01-01T09:00:00+00:00")))
        _write_raw_lines(tmp_path, lines)

        second_path = generate_daily_summary(past_day)
        second_content = Path(second_path).read_text(encoding="utf-8")
        assert second_path == first_path
        assert second_content == first_content
        assert "- Files scanned: 1" in second_content

    def test_a_closed_past_day_with_no_existing_file_is_computed_and_written(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        past_day = date(2020, 1, 1)
        lines = [json.dumps(_entry(file_id="f1", action="discover", timestamp="2020-01-01T08:00:00+00:00"))]
        _write_raw_lines(tmp_path, lines)

        path = generate_daily_summary(past_day)
        assert Path(path).exists()
        assert "- Files scanned: 1" in Path(path).read_text(encoding="utf-8")

    def test_todays_open_day_is_always_recomputed(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        today = datetime.now(timezone.utc).date()
        ts_prefix = today.isoformat()

        lines = [json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{ts_prefix}T08:00:00+00:00"))]
        _write_raw_lines(tmp_path, lines)
        first_content = Path(generate_daily_summary(today)).read_text(encoding="utf-8")
        assert "- Files scanned: 1" in first_content

        lines.append(json.dumps(_entry(file_id="f2", action="discover", timestamp=f"{ts_prefix}T09:00:00+00:00")))
        _write_raw_lines(tmp_path, lines)
        second_content = Path(generate_daily_summary(today)).read_text(encoding="utf-8")
        assert "- Files scanned: 2" in second_content


class TestGenerateDailySummaryIdempotency:
    def test_repeated_calls_with_unchanged_source_data_are_byte_identical(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        today = datetime.now(timezone.utc).date()
        ts_prefix = today.isoformat()
        lines = [
            json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{ts_prefix}T08:00:00+00:00")),
            json.dumps(_score_confidence("f1", "auto", timestamp=f"{ts_prefix}T08:05:00+00:00")),
            json.dumps(_move_rename("f1", timestamp=f"{ts_prefix}T08:10:00+00:00")),
        ]
        _write_raw_lines(tmp_path, lines)
        database_module.save_file_record(_record(
            "f1", "a.pdf", category=Category.DOCUMENT, tier="auto", confidence_score=95,
            suggested_name="A.pdf", suggested_destination="Docs/",
        ))
        first = Path(generate_daily_summary(today)).read_text(encoding="utf-8")
        second = Path(generate_daily_summary(today)).read_text(encoding="utf-8")
        assert first == second


class TestGenerateDailySummaryZeroWrite:
    def test_touches_nothing_outside_reports_given_a_pre_seeded_metadata_store(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("f1", "a.pdf"))
        metadata_path = tmp_path / "metadata_store.json"
        before = metadata_path.read_text(encoding="utf-8")

        lines = [json.dumps(_entry(file_id="f1", action="discover"))]
        _write_raw_lines(tmp_path, lines)
        generate_daily_summary(date(2026, 7, 14))

        after = metadata_path.read_text(encoding="utf-8")
        assert before == after

    def test_touches_nothing_in_the_action_log(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [json.dumps(_entry(file_id="f1", action="discover"))]
        _write_raw_lines(tmp_path, lines)
        before = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")

        generate_daily_summary(date(2026, 7, 14))

        after = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")
        assert before == after

    def test_metadata_store_record_count_is_unchanged_end_to_end(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("f1", "a.pdf", category=Category.DOCUMENT, tier="auto"))
        records_before = database_module.load_metadata_store()

        lines = [json.dumps(_move_rename("f1"))]
        _write_raw_lines(tmp_path, lines)
        generate_daily_summary(date(2026, 7, 14))

        records_after = database_module.load_metadata_store()
        assert len(records_before) == len(records_after) == 1

    def test_disclosed_first_time_metadata_store_creation_writes_only_an_empty_array(
        self, tmp_path, monkeypatch
    ):
        """Module docstring's disclosed exception: a fresh install with no
        metadata_store.json yet gets one created holding `[]` — identical to
        "no records recorded yet," and not itself a FileRecord write."""
        _isolate_all(tmp_path, monkeypatch)
        metadata_path = tmp_path / "metadata_store.json"
        assert not metadata_path.exists()

        generate_daily_summary(date(2026, 7, 14))

        assert metadata_path.exists()
        assert json.loads(metadata_path.read_text(encoding="utf-8")) == []


# --- generate_duplicate_report() (WP-3) ---

def _reject(file_id, timestamp="2026-07-14T10:00:00+00:00", **kwargs):
    return _entry(file_id=file_id, action="reject", timestamp=timestamp, approved_by="user", **kwargs)


def _undo(file_id, reversed_action, timestamp="2026-07-14T11:00:00+00:00", **kwargs):
    return _entry(file_id=file_id, action="undo", timestamp=timestamp, approved_by="user",
                  details={"reversed_action": reversed_action}, **kwargs)


class TestGenerateDuplicateReportCategorization:
    def test_archived_duplicate(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "invoice_copy.pdf", duplicate_of="orig1"))
        database_module.save_file_record(_record("orig1", "invoice.pdf"))
        lines = [
            json.dumps(_detect_duplicates("d1", duplicate_of="orig1")),
            json.dumps(_archive_duplicate("d1")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Archived: 1" in content
        assert "- Kept: 0" in content
        assert "- Overridden by user: 0" in content
        assert "| invoice_copy.pdf | Duplicate | invoice.pdf | Archived |" in content

    def test_archived_superseded_version(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record(
            "v8", "Resume_v8.pdf", version_group_id="g1", version_rank="superseded",
        ))
        database_module.save_file_record(_record(
            "v9", "Resume_v9.pdf", version_group_id="g1", version_rank="latest",
        ))
        lines = [json.dumps(_archive_superseded_version("v8"))]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Archived: 1" in content
        assert "| Resume_v8.pdf | Superseded Version | Resume_v9.pdf | Archived |" in content

    def test_kept_no_execution_action_yet(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "invoice_copy.pdf", duplicate_of="orig1"))
        database_module.save_file_record(_record("orig1", "invoice.pdf"))
        lines = [json.dumps(_detect_duplicates("d1", duplicate_of="orig1"))]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Kept: 1" in content
        assert "| invoice_copy.pdf | Duplicate | invoice.pdf | Kept |" in content

    def test_kept_rejected(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "invoice_copy.pdf", duplicate_of="orig1"))
        lines = [
            json.dumps(_detect_duplicates("d1", duplicate_of="orig1")),
            json.dumps(_reject("d1")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Kept: 1" in content
        assert "- Archived: 0" in content

    def test_kept_after_undo_reverses_a_prior_archive(self, tmp_path, monkeypatch):
        """An archive later undone must not still read as Archived — the LAST
        chronological disposition action wins (decision 25's "always-current
        view" philosophy)."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "invoice_copy.pdf", duplicate_of="orig1"))
        lines = [
            json.dumps(_detect_duplicates("d1", duplicate_of="orig1")),
            json.dumps(_archive_duplicate("d1", timestamp="2026-07-14T10:00:00+00:00")),
            json.dumps(_undo("d1", "archive_duplicate", timestamp="2026-07-14T11:00:00+00:00")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Archived: 0" in content
        assert "- Kept: 1" in content

    def test_overridden_by_user_duplicate_filed_via_ordinary_move(self, tmp_path, monkeypatch):
        """Decision 23: an edited destination can route a genuine duplicate
        through the ordinary move_rename path instead of the archive
        override — that is the "Overridden by user" case."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "invoice_copy.pdf", duplicate_of="orig1"))
        database_module.save_file_record(_record("orig1", "invoice.pdf"))
        lines = [
            json.dumps(_detect_duplicates("d1", duplicate_of="orig1")),
            json.dumps(_move_rename("d1")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Overridden by user: 1" in content
        assert "| invoice_copy.pdf | Duplicate | invoice.pdf | Overridden by user |" in content

    def test_overridden_by_user_superseded_version_filed_via_ordinary_move(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record(
            "v8", "Resume_v8.pdf", version_group_id="g1", version_rank="superseded",
        ))
        database_module.save_file_record(_record(
            "v9", "Resume_v9.pdf", version_group_id="g1", version_rank="latest",
        ))
        lines = [json.dumps(_move_rename("v8"))]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Overridden by user: 1" in content

    def test_last_disposition_action_wins_over_an_earlier_one(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "invoice_copy.pdf", duplicate_of="orig1"))
        lines = [
            json.dumps(_detect_duplicates("d1", duplicate_of="orig1")),
            json.dumps(_reject("d1", timestamp="2026-07-14T09:00:00+00:00")),
            json.dumps(_archive_duplicate("d1", timestamp="2026-07-14T10:00:00+00:00")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Archived: 1" in content
        assert "- Kept: 0" in content


class TestGenerateDuplicateReportExclusion:
    def test_ordinary_records_never_appear(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("f1", "resume.pdf"))
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Records tracked: 0" in content
        assert "resume.pdf" not in content

    def test_latest_ranked_version_record_is_not_a_first_class_row(self, tmp_path, monkeypatch):
        """A "latest" record carries a non-null version_group_id but is the
        surviving file, not itself a duplicate/superseded item — it must not
        get its own row, even though it shares a group with a superseded
        sibling."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record(
            "v8", "Resume_v8.pdf", version_group_id="g1", version_rank="superseded",
        ))
        database_module.save_file_record(_record(
            "v9", "Resume_v9.pdf", version_group_id="g1", version_rank="latest",
        ))
        lines = [json.dumps(_move_rename("v9"))]  # the survivor gets filed normally
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        # Only the superseded sibling is a row; the survivor is referenced
        # only as "Related To", never given its own row (if it had one, its
        # own "Original" cell would make "Resume_v9.pdf" appear a second
        # time — it appears exactly once, as v8's "Related To" value only).
        assert "- Records tracked: 1 (0 duplicates, 1 superseded versions)" in content
        assert content.count("Resume_v9.pdf") == 1
        assert "| Resume_v8.pdf | Superseded Version | Resume_v9.pdf | Kept |" in content


class TestGenerateDuplicateReportTraceability:
    def test_related_to_shows_the_duplicate_of_targets_original_name(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "copy.pdf", duplicate_of="orig1"))
        database_module.save_file_record(_record("orig1", "original.pdf"))
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "| copy.pdf | Duplicate | original.pdf | Kept |" in content

    def test_related_to_is_unknown_when_duplicate_of_target_missing(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "copy.pdf", duplicate_of="ghost"))
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "| copy.pdf | Duplicate | Unknown | Kept |" in content

    def test_related_to_is_unknown_when_no_latest_sibling_found(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record(
            "v8", "Resume_v8.pdf", version_group_id="g1", version_rank="superseded",
        ))
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "| Resume_v8.pdf | Superseded Version | Unknown | Kept |" in content

    def test_every_count_traces_to_a_real_action_log_entry_or_field(self, tmp_path, monkeypatch):
        """Hand-computable cross-check across a mixed scenario."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "a.pdf", duplicate_of="orig1"))
        database_module.save_file_record(_record("orig1", "original.pdf"))
        database_module.save_file_record(_record("d2", "b.pdf", duplicate_of="orig1"))
        database_module.save_file_record(_record(
            "v8", "Resume_v8.pdf", version_group_id="g1", version_rank="superseded",
        ))
        database_module.save_file_record(_record(
            "v9", "Resume_v9.pdf", version_group_id="g1", version_rank="latest",
        ))
        lines = [
            json.dumps(_detect_duplicates("d1", duplicate_of="orig1")),
            json.dumps(_archive_duplicate("d1")),
            json.dumps(_detect_duplicates("d2", duplicate_of="orig1")),
            json.dumps(_move_rename("d2")),
            json.dumps(_archive_superseded_version("v8")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Records tracked: 3 (2 duplicates, 1 superseded versions)" in content
        assert "- Archived: 2" in content
        assert "- Kept: 0" in content
        assert "- Overridden by user: 1" in content


class TestGenerateDuplicateReportAlwaysOverwritten:
    """Decision 25: no period concept, no G6/closed-period protection at all
    — every call is a full, unconditional recomputation and overwrite."""

    def test_second_call_reflects_new_data_unconditionally(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "a.pdf", duplicate_of="orig1"))
        first = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Records tracked: 1" in first

        database_module.save_file_record(_record("d2", "b.pdf", duplicate_of="orig1"))
        second_path = generate_duplicate_report()
        second = Path(second_path).read_text(encoding="utf-8")
        assert "- Records tracked: 2" in second
        assert second != first

    def test_writes_to_the_single_fixed_path_every_time(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        path1 = generate_duplicate_report()
        database_module.save_file_record(_record("d1", "a.pdf", duplicate_of="orig1"))
        path2 = generate_duplicate_report()
        assert path1 == path2


class TestGenerateDuplicateReportEmptyState:
    def test_no_signal_bearing_records_renders_honest_zeroed_shape(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert content == (
            "# Duplicate Report\n"
            "\n"
            "- As of: no activity recorded yet\n"
            "- Records tracked: 0 (0 duplicates, 0 superseded versions)\n"
            "- Archived: 0\n"
            "- Kept: 0\n"
            "- Overridden by user: 0\n"
            "\n"
            "## Records\n"
            "| Original | Type | Related To | Disposition |\n"
            "|---|---|---|---|\n"
        )


class TestGenerateDuplicateReportAsOfMarker:
    def test_as_of_reflects_the_latest_relevant_entry_only(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "a.pdf", duplicate_of="orig1"))
        lines = [
            json.dumps(_detect_duplicates("d1", duplicate_of="orig1", timestamp="2026-07-14T09:00:00+00:00")),
            json.dumps(_archive_duplicate("d1", timestamp="2026-07-14T10:00:00+00:00")),
            # Unrelated entry, for a non-signal-bearing file, with a later timestamp —
            # must NOT affect the marker.
            json.dumps(_entry(file_id="unrelated", action="discover", timestamp="2026-07-14T23:00:00+00:00")),
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- As of: 2026-07-14T10:00:00+00:00" in content


class TestGenerateDuplicateReportMalformedLineDisclosure:
    def test_malformed_lines_disclosed_and_do_not_crash_generation(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "a.pdf", duplicate_of="orig1"))
        lines = [
            json.dumps(_detect_duplicates("d1", duplicate_of="orig1")),
            "{not valid json",
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "- Records tracked: 1" in content
        assert "- Malformed log lines skipped: 1" in content

    def test_no_disclosure_line_when_nothing_malformed(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        content = Path(generate_duplicate_report()).read_text(encoding="utf-8")
        assert "Malformed" not in content


class TestGenerateDuplicateReportZeroWrite:
    def test_touches_nothing_in_the_action_log(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        lines = [json.dumps(_entry(file_id="f1", action="discover"))]
        _write_raw_lines(tmp_path, lines)
        before = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")

        generate_duplicate_report()

        after = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")
        assert before == after

    def test_metadata_store_record_count_is_unchanged_end_to_end(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_record("d1", "a.pdf", duplicate_of="orig1"))
        records_before = database_module.load_metadata_store()

        generate_duplicate_report()

        records_after = database_module.load_metadata_store()
        assert len(records_before) == len(records_after) == 1

    def test_writes_only_within_reports_duplicate_report(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        (tmp_path / "Database").mkdir()
        (tmp_path / "Database" / "sentinel.json").write_text("[]", encoding="utf-8")

        generate_duplicate_report()

        assert (tmp_path / "Database" / "sentinel.json").read_text(encoding="utf-8") == "[]"


# --- generate_weekly_summary() (WP-4) ---

def _iso_week_monday(iso_year, iso_week):
    return date.fromisocalendar(iso_year, iso_week, 1)


class TestGenerateWeeklySummaryRollup:
    def test_multi_day_rollup_against_real_generate_daily_summary_output(self, tmp_path, monkeypatch):
        """Seeds real action-log activity for two days within a fully-past,
        fully-closed ISO week, generates their Daily Summary files via the
        real generate_daily_summary() (never hand-crafted Markdown), then
        confirms generate_weekly_summary() correctly parses and sums both."""
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 2)  # 2020-01-06, fully closed
        tuesday = monday + timedelta(days=1)

        database_module.save_file_record(_record(
            "f1", "a.pdf", category=Category.DOCUMENT, tier="auto",
            confidence_score=95, suggested_name="A.pdf", suggested_destination="Docs/",
        ))
        database_module.save_file_record(_record(
            "f2", "b.pdf", category=Category.IMAGE, tier="approval_required",
            confidence_score=70, suggested_name="B.jpg", suggested_destination="Images/",
        ))
        lines = [
            json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{monday.isoformat()}T08:00:00+00:00")),
            json.dumps(_score_confidence("f1", "auto", timestamp=f"{monday.isoformat()}T08:05:00+00:00")),
            json.dumps(_move_rename("f1", timestamp=f"{monday.isoformat()}T08:10:00+00:00")),
            json.dumps(_entry(file_id="f2", action="discover", timestamp=f"{tuesday.isoformat()}T09:00:00+00:00")),
            json.dumps(_score_confidence("f2", "approval_required", timestamp=f"{tuesday.isoformat()}T09:05:00+00:00")),
        ]
        _write_raw_lines(tmp_path, lines)

        generate_daily_summary(monday)
        generate_daily_summary(tuesday)

        content = Path(generate_weekly_summary(monday)).read_text(encoding="utf-8")
        assert "- Files scanned: 2" in content
        assert "- Auto-filed: 1" in content
        assert "- Approval required: 1" in content
        assert f"| {monday.isoformat()} | Reported | 1 | 1 | 0 | 0 | 0 | 0 | 0 |" in content
        assert f"| {tuesday.isoformat()} | Reported | 1 | 0 | 1 | 0 | 0 | 0 | 0 |" in content

    def test_ignores_the_parenthetical_disposition_detail_when_parsing(self, tmp_path, monkeypatch):
        """Daily Summary's own "Duplicates found: 1 (archived)"/"Versions
        archived: 1 (X → superseded by Y)" parenthetical detail must not
        break parsing — only the leading integer is read."""
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 3)
        database_module.save_file_record(_record("d1", "copy.pdf", duplicate_of="orig1"))
        database_module.save_file_record(_record("orig1", "invoice.pdf"))
        lines = [
            json.dumps(_detect_duplicates("d1", duplicate_of="orig1", timestamp=f"{monday.isoformat()}T09:00:00+00:00")),
            json.dumps(_archive_duplicate("d1", timestamp=f"{monday.isoformat()}T09:05:00+00:00")),
        ]
        _write_raw_lines(tmp_path, lines)
        generate_daily_summary(monday)

        content = Path(generate_weekly_summary(monday)).read_text(encoding="utf-8")
        assert "- Duplicates found: 1" in content
        assert f"| {monday.isoformat()} | Reported | 0 | 0 | 0 | 0 | 1 | 0 | 0 |" in content

    def test_days_with_no_daily_summary_and_no_activity_are_no_activity(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 5)  # fully closed, no data at all
        content = Path(generate_weekly_summary(monday)).read_text(encoding="utf-8")
        assert "- Files scanned: 0" in content
        for offset in range(7):
            day = monday + timedelta(days=offset)
            assert f"| {day.isoformat()} | No activity | 0 | 0 | 0 | 0 | 0 | 0 | 0 |" in content


class TestGenerateWeeklySummaryDisambiguation:
    """§12 Layer 1's L1 fix: "no activity" and "generation previously failed"
    must never be conflated."""

    def test_closed_day_with_no_file_and_no_activity_is_no_activity(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 6)
        content = Path(generate_weekly_summary(monday)).read_text(encoding="utf-8")
        assert f"| {monday.isoformat()} | No activity | 0 | 0 | 0 | 0 | 0 | 0 | 0 |" in content

    def test_closed_day_with_activity_but_no_file_is_report_unavailable(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 7)
        lines = [json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{monday.isoformat()}T08:00:00+00:00"))]
        _write_raw_lines(tmp_path, lines)
        # Deliberately never call generate_daily_summary(monday) — simulates
        # a day whose own Daily Summary generation never ran/failed.

        content = Path(generate_weekly_summary(monday)).read_text(encoding="utf-8")
        assert f"| {monday.isoformat()} | Report unavailable for this date | - | - | - | - | - | - | - |" in content

    def test_report_unavailable_day_is_excluded_from_totals_not_zeroed(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 8)
        tuesday = monday + timedelta(days=1)
        database_module.save_file_record(_record("f2", "b.pdf", tier="auto"))
        lines = [
            # Monday: activity happened, but no Daily Summary was generated.
            json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{monday.isoformat()}T08:00:00+00:00")),
            # Tuesday: properly reported.
            json.dumps(_entry(file_id="f2", action="discover", timestamp=f"{tuesday.isoformat()}T08:00:00+00:00")),
            json.dumps(_score_confidence("f2", "auto", timestamp=f"{tuesday.isoformat()}T08:05:00+00:00")),
        ]
        _write_raw_lines(tmp_path, lines)
        generate_daily_summary(tuesday)

        content = Path(generate_weekly_summary(monday)).read_text(encoding="utf-8")
        # Only Tuesday's real, known count — Monday's real figures are
        # unknown and must never be silently folded in as zero.
        assert "- Files scanned: 1" in content
        assert "- Auto-filed: 1" in content


class TestGenerateWeeklySummaryIsoYearBoundary:
    def test_year_boundary_week_matches_write_weekly_summarys_own_precedent(self, tmp_path, monkeypatch):
        """2027-01-01 is ISO week 53 of 2026 — matches
        storage/test_runtime_io.py's own already-established precedent for
        write_weekly_summary()'s identical filename computation."""
        _isolate_all(tmp_path, monkeypatch)
        result_path = generate_weekly_summary(date(2027, 1, 1))
        expected_path = tmp_path / "Reports" / "Weekly Summary" / "summary_2026-W53.md"
        assert result_path == str(expected_path)
        content = expected_path.read_text(encoding="utf-8")
        assert content.startswith("# Weekly Summary — 2026-W53\n")


class TestGenerateWeeklySummaryNotYetClosed:
    def test_current_week_excludes_todays_still_open_day(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        today = datetime.now(timezone.utc).date()
        content = Path(generate_weekly_summary(today)).read_text(encoding="utf-8")
        assert f"| {today.isoformat()} | Not yet closed | - | - | - | - | - | - | - |" in content

    def test_a_future_day_within_the_requested_week_is_also_not_yet_closed(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        today = datetime.now(timezone.utc).date()
        iso_year, iso_week, _ = today.isocalendar()
        sunday = date.fromisocalendar(iso_year, iso_week, 7)
        assert sunday >= today  # guards this test's own premise
        content = Path(generate_weekly_summary(today)).read_text(encoding="utf-8")
        assert f"| {sunday.isoformat()} | Not yet closed | - | - | - | - | - | - | - |" in content

    def test_not_yet_closed_days_are_excluded_from_totals(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        today = datetime.now(timezone.utc).date()
        lines = [json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{today.isoformat()}T08:00:00+00:00"))]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_weekly_summary(today)).read_text(encoding="utf-8")
        assert "- Files scanned: 0" in content  # today's activity not yet closed, excluded


class TestGenerateWeeklySummaryDeterminism:
    def test_closed_week_reproduces_byte_identical_content(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 10)
        lines = [json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{monday.isoformat()}T08:00:00+00:00"))]
        _write_raw_lines(tmp_path, lines)
        generate_daily_summary(monday)

        first = Path(generate_weekly_summary(monday)).read_text(encoding="utf-8")
        second = Path(generate_weekly_summary(monday)).read_text(encoding="utf-8")
        assert first == second


class TestGenerateWeeklySummaryMalformedLineDisclosure:
    def test_malformed_lines_disclosed_and_do_not_crash_generation(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 15)
        lines = [
            json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{monday.isoformat()}T08:00:00+00:00")),
            "{not valid json",
        ]
        _write_raw_lines(tmp_path, lines)
        content = Path(generate_weekly_summary(monday)).read_text(encoding="utf-8")
        assert "- Malformed log lines skipped: 1" in content

    def test_no_disclosure_line_when_nothing_malformed(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        content = Path(generate_weekly_summary(_iso_week_monday(2020, 16))).read_text(encoding="utf-8")
        assert "Malformed" not in content


class TestGenerateWeeklySummaryZeroWrite:
    def test_touches_nothing_in_the_action_log(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 11)
        lines = [json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{monday.isoformat()}T08:00:00+00:00"))]
        _write_raw_lines(tmp_path, lines)
        before = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")

        generate_weekly_summary(monday)

        after = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")
        assert before == after

    def test_never_touches_the_metadata_store_at_all(self, tmp_path, monkeypatch):
        """Unlike WP-2/WP-3, WP-4 never calls load_metadata_store() at all
        (§5: Weekly Summary's own source is Daily Summary files, not the
        metadata store) — confirmed structurally: metadata_store.json isn't
        even created as a side effect."""
        _isolate_all(tmp_path, monkeypatch)
        metadata_path = tmp_path / "metadata_store.json"
        assert not metadata_path.exists()

        generate_weekly_summary(_iso_week_monday(2020, 12))

        assert not metadata_path.exists()

    def test_writes_only_within_reports_weekly_summary(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        (tmp_path / "Database").mkdir()
        (tmp_path / "Database" / "sentinel.json").write_text("[]", encoding="utf-8")

        generate_weekly_summary(_iso_week_monday(2020, 13))

        assert (tmp_path / "Database" / "sentinel.json").read_text(encoding="utf-8") == "[]"

    def test_never_writes_to_the_daily_summary_folder(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        monday = _iso_week_monday(2020, 14)
        lines = [json.dumps(_entry(file_id="f1", action="discover", timestamp=f"{monday.isoformat()}T08:00:00+00:00"))]
        _write_raw_lines(tmp_path, lines)
        generate_daily_summary(monday)
        daily_path = tmp_path / "Reports" / "Daily Summary" / f"summary_{monday.isoformat()}.md"
        before = daily_path.read_text(encoding="utf-8")

        generate_weekly_summary(monday)

        after = daily_path.read_text(encoding="utf-8")
        assert before == after


# --- generate_storage_report() (WP-5) ---
#
# Decision 25: single, continuously-updated current-state file, unconditionally
# overwritten. Decision 29: derived entirely from size_bytes/suggested_destination/
# category already in the metadata store — no action-log read, no filesystem walk.
# Decision 30: a record contributes only if processed_at is not None.

def _filed_record(file_id, name, category, suggested_destination, size_bytes,
                   processed_at="2026-07-14T12:00:00+00:00", **kwargs):
    """A record that has actually been filed (decision 30's inclusion
    predicate) — processed_at set, exactly as ExecutionEngine.execute_file()
    step 6 sets it after a real move/archive."""
    return _record(
        file_id, name, category=category, suggested_destination=suggested_destination,
        size_bytes=size_bytes, processed_at=processed_at, **kwargs,
    )


def _unfiled_record(file_id, name, category=None, suggested_destination=None,
                     size_bytes=None, **kwargs):
    """A record that has NOT been filed — processed_at stays None (its
    dataclass default), exactly as a review_required/unreadable/
    not-yet-approved/undone record's real state is."""
    return _record(
        file_id, name, category=category, suggested_destination=suggested_destination,
        size_bytes=size_bytes, **kwargs,
    )


class TestGenerateStorageReportInclusionPredicate:
    """Decision 30: record.processed_at is not None is the sole, authoritative
    inclusion signal."""

    def test_filed_record_contributes(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records: 1" in content

    def test_review_required_record_excluded(self, tmp_path, monkeypatch):
        """§0.1 I2: a review_required record is left completely unchanged —
        processed_at is never set for it, so it must never contribute."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_unfiled_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000, tier="review_required",
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records: 0" in content
        assert "Finance/" not in content

    def test_unreadable_record_excluded(self, tmp_path, monkeypatch):
        """A record that never reached Module 05 has no suggested_destination
        and no processed_at — excluded, not crashed on."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(FileRecord(
            file_id="f1", source_id="downloads", original_name="corrupt.pdf",
            original_path="/tmp/corrupt.pdf", current_path="/tmp/corrupt.pdf",
            status="unreadable", size_bytes=500,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records: 0" in content

    def test_record_awaiting_approval_excluded(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_unfiled_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000, tier="approval_required",
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records: 0" in content

    def test_undone_record_excluded(self, tmp_path, monkeypatch):
        """decision 30 / decision 25's "always-current view": undo_single_action()
        resets processed_at to None — the record must fall out of the totals
        on the very next call, with no special-casing."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_unfiled_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records: 0" in content
        assert "Finance/" not in content

    def test_mixed_filed_and_unfiled_only_filed_counted(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        database_module.save_file_record(_unfiled_record(
            "f2", "review_me.pdf", Category.DOCUMENT, "Documents/", 2000, tier="review_required",
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records: 1" in content
        assert "Documents/" not in content


class TestGenerateStorageReportAggregation:
    def test_groups_by_suggested_destination(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        database_module.save_file_record(_filed_record(
            "f2", "statement.pdf", Category.BANK_STATEMENT, "Finance/", 2000,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "| Finance/ | 2.9 KB |" in content

    def test_groups_by_category(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        database_module.save_file_record(_filed_record(
            "f2", "invoice2.pdf", Category.INVOICE, "Finance/", 500,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "| Invoice | 1.5 KB |" in content

    def test_different_categories_same_destination_both_counted_toward_folder_total(
        self, tmp_path, monkeypatch
    ):
        """Finance/ holds both Invoice and Bank Statement (Rules/Folder Rules.md)
        — the destination breakdown must sum across categories, and the
        category breakdown must keep them separate."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1024,
        ))
        database_module.save_file_record(_filed_record(
            "f2", "statement.pdf", Category.BANK_STATEMENT, "Finance/", 1024,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "| Finance/ | 2.0 KB |" in content
        assert "| Invoice | 1.0 KB |" in content
        assert "| Bank Statement | 1.0 KB |" in content

    def test_archive_override_destinations_are_their_own_buckets(self, tmp_path, monkeypatch):
        """decision 30's Trade-offs note: ~ARCHIVE~/ destinations are real,
        currently-occupied space and must be included, not folded away."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "invoice_copy.pdf", Category.INVOICE, "~ARCHIVE~/Duplicates/", 4096,
            duplicate_of="orig1",
        ))
        database_module.save_file_record(_filed_record(
            "f2", "Resume_v8.pdf", Category.RESUME, "~ARCHIVE~/Old Versions/", 8192,
            version_group_id="g1", version_rank="superseded",
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "| ~ARCHIVE~/Duplicates/ | 4.0 KB |" in content
        assert "| ~ARCHIVE~/Old Versions/ | 8.0 KB |" in content

    def test_missing_suggested_destination_buckets_as_unknown(self, tmp_path, monkeypatch):
        """Defensive handling (§12 Layer 1) — should not occur for a filed
        record given Module 05's own ownership guarantee, but never crashes
        or silently drops the record."""
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "mystery.pdf", Category.UNKNOWN, None, 1000,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "| Unknown | 1000 B |" in content

    def test_missing_category_buckets_as_unknown(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "mystery.pdf", None, "Unknown/", 1000,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        # Two "Unknown" buckets can coexist (one per breakdown table) without
        # collision, since they're independent tables.
        assert "## By Category" in content
        assert content.count("| Unknown | 1000 B |") == 1

    def test_totals_sorted_deterministically(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "a.pdf", Category.VIDEO, "Videos/", 100,
        ))
        database_module.save_file_record(_filed_record(
            "f2", "b.pdf", Category.AUDIO, "Audio/", 100,
        ))
        database_module.save_file_record(_filed_record(
            "f3", "c.pdf", Category.ARCHIVE, "Archives/", 100,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert content.index("Archives/") < content.index("Audio/") < content.index("Videos/")


class TestGenerateStorageReportMissingSize:
    def test_missing_size_bytes_excluded_from_totals(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "known.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        database_module.save_file_record(_filed_record(
            "f2", "unknown_size.pdf", Category.INVOICE, "Finance/", None,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "| Finance/ | 1000 B |" in content

    def test_missing_size_count_disclosed(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "unknown_size.pdf", Category.INVOICE, "Finance/", None,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records with unknown size (excluded from totals): 1" in content
        assert "- Filed records: 1" in content  # still counted in the honest total

    def test_no_disclosure_line_when_no_size_is_missing(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "known.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "unknown size" not in content


class TestGenerateStorageReportAsOfMarker:
    def test_as_of_is_the_latest_processed_at_among_filed_records(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "a.pdf", Category.INVOICE, "Finance/", 100,
            processed_at="2026-07-14T09:00:00+00:00",
        ))
        database_module.save_file_record(_filed_record(
            "f2", "b.pdf", Category.INVOICE, "Finance/", 100,
            processed_at="2026-07-14T15:30:00+00:00",
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- As of: 2026-07-14T15:30:00+00:00" in content

    def test_as_of_ignores_unfiled_records(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "a.pdf", Category.INVOICE, "Finance/", 100,
            processed_at="2026-07-14T09:00:00+00:00",
        ))
        database_module.save_file_record(_unfiled_record(
            "f2", "b.pdf", Category.INVOICE, "Finance/", 100,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- As of: 2026-07-14T09:00:00+00:00" in content

    def test_as_of_when_no_filed_records_exist(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- As of: no filed records yet" in content


class TestGenerateStorageReportEmptyState:
    def test_empty_metadata_store_produces_honest_zero_report(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records: 0" in content
        assert "- Total space used: 0 B" in content
        assert "# Storage Report" in content


class TestGenerateStorageReportIdempotency:
    def test_regeneration_against_unchanged_data_is_byte_for_byte_identical(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        database_module.save_file_record(_filed_record(
            "f2", "photo.jpg", Category.IMAGE, "Images/", 2000,
        ))
        first = Path(generate_storage_report()).read_text(encoding="utf-8")
        second = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert first == second

    def test_a_second_call_always_overwrites_no_scoping_parameter(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        generate_storage_report()
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records: 1" in content


class TestGenerateStorageReportNeverReadsActionLog:
    """decision 29: Storage Report is derived entirely from the metadata store —
    a first among the four report types, it reads no action-log entries at all."""

    def test_action_log_is_never_read_even_when_present(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        # A malformed action log would crash any report type that reads it via
        # read_action_log_entries_safe()'s counterpart, read_action_log_entries()
        # (unsafe) — Storage Report must be entirely unaffected either way,
        # since it never opens the file at all.
        (tmp_path / "action_log.jsonl").write_text("{not valid json at all", encoding="utf-8")
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "Malformed" not in content
        assert "- Filed records: 1" in content

    def test_generates_correctly_when_action_log_does_not_exist_at_all(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        assert not (tmp_path / "action_log.jsonl").exists()
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        content = Path(generate_storage_report()).read_text(encoding="utf-8")
        assert "- Filed records: 1" in content
        assert not (tmp_path / "action_log.jsonl").exists()


class TestGenerateStorageReportZeroWrite:
    def test_touches_nothing_in_the_metadata_store(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        database_module.save_file_record(_filed_record(
            "f1", "invoice.pdf", Category.INVOICE, "Finance/", 1000,
        ))
        metadata_path = tmp_path / "metadata_store.json"
        before = metadata_path.read_text(encoding="utf-8")

        generate_storage_report()

        after = metadata_path.read_text(encoding="utf-8")
        assert before == after

    def test_writes_only_within_reports_storage_report(self, tmp_path, monkeypatch):
        _isolate_all(tmp_path, monkeypatch)
        (tmp_path / "action_log.jsonl").write_text("", encoding="utf-8")
        before_log = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")

        generate_storage_report()

        after_log = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")
        assert before_log == after_log
        assert (tmp_path / "Reports" / "Storage Report" / "storage_report.md").exists()
