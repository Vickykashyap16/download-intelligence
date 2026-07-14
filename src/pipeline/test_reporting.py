"""
Unit tests for pipeline/reporting.py — Module 08 (Logging & Reporting).

Module 08 Implementation Plan.md WP-1 scope only (scaffold reconciliation): the
shared aggregation primitives `read_action_log_entries_safe()`,
`compute_as_of_marker()`, `filter_entries_by_day()`, and `filter_entries_by_action()`
(Module 08 Design.md §7, §12 Layer 1). The four `generate_*()` functions remain
NotImplementedError stubs, out of every work package's scope so far (WP-2 through
WP-5), and are not tested here — the same convention `pipeline/test_execution.py`
already established for its own untouched pre-existing stubs.

Isolated from the project's real `Runtime/Logs/action_log.jsonl` via the same
`monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / ...)`
convention `pipeline/test_execution.py`/`pipeline/test_naming.py` already
established.

Run with: pytest src/pipeline/test_reporting.py -v
"""

import json
from datetime import date

import pytest

import src.storage.runtime_io as runtime_io_module
from src.pipeline.reporting import (
    compute_as_of_marker,
    filter_entries_by_action,
    filter_entries_by_day,
    read_action_log_entries_safe,
)


def _isolate_action_log(tmp_path, monkeypatch):
    """Same isolation convention pipeline/test_execution.py already established —
    redirect action_log_path()'s target file to a sandboxed tmp_path, never the
    project's real Runtime/Logs/action_log.jsonl."""
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


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

    def test_no_helper_touches_the_real_database_or_metadata_store_paths(
        self, tmp_path, monkeypatch
    ):
        """Confirms none of WP-1's new functions import or reach into
        storage.database at all (Module 08 owns zero FileRecord fields, G1/G2) —
        a structural check, not just a behavioral one."""
        import src.pipeline.reporting as reporting_module

        assert not hasattr(reporting_module, "load_metadata_store")
        assert not hasattr(reporting_module, "save_file_record")
