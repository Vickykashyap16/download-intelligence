"""
Unit tests for pipeline/reporting.py — Module 08 (Logging & Reporting).

Module 08 Implementation Plan.md WP-1 scope: the shared aggregation primitives
`read_action_log_entries_safe()`, `compute_as_of_marker()`, `filter_entries_by_day()`,
and `filter_entries_by_action()` (Module 08 Design.md §7, §12 Layer 1).

WP-2 scope: `generate_daily_summary()` — the real aggregation/rendering logic,
tested below against `Metadata & Log Schema.md`'s own worked example. `generate_weekly_
summary()`/`generate_duplicate_report()`/`generate_storage_report()` remain
NotImplementedError stubs, out of every work package's scope so far (WP-3/WP-4/WP-5),
and are not tested here — the same convention `pipeline/test_execution.py` already
established for its own untouched pre-existing stubs.

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
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.classification import Category
from src.models.file_record import FileRecord
from src.pipeline.reporting import (
    compute_as_of_marker,
    filter_entries_by_action,
    filter_entries_by_day,
    generate_daily_summary,
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
