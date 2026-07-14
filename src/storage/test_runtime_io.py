"""
Unit tests for storage/runtime_io.py's Module 08 (Logging & Reporting) territory —
the four `write_*()` functions.

Module 08 Implementation Plan.md status: WP-1 (scaffold reconciliation) fully
implemented `write_daily_summary()`/`write_weekly_summary()` (Module 08 Design.md
§6, `Governance/ARCHITECTURE_DECISIONS.md` decision 25/26/27), tested here directly,
called with an already-rendered `content` string, never via a `generate_*()` caller
(that wiring is WP-2/WP-4's own scope). WP-1 left `write_duplicate_report()`/
`write_storage_report()` with only a minimal, OD-1-agnostic signature — their body
was `NotImplementedError` by design (per `Module 08 Implementation Plan.md
Review.md` finding F5). WP-3 has since finalized `write_duplicate_report()`'s body
(decision 25: no scoping parameter needed, a single continuously-updated
current-state file, unconditionally overwritten in place) — tested here directly
below, same convention as `write_daily_summary()`/`write_weekly_summary()`.
`write_storage_report()` remains `NotImplementedError` — WP-5's own scope, not yet
performed.

This project's other `storage/*.py` functions are conventionally tested via the
`pipeline/*.py` module that calls them (e.g. `append_action_log()`/
`read_action_log_entries()` via `pipeline/test_execution.py`'s own
`runtime_io_module` import), rather than a dedicated `storage/test_*.py` file. This
file is a deliberate, disclosed departure from that convention, per
`Module 08 Implementation Plan.md` WP-1's own explicit "Required tests" line, which
names `storage/test_runtime_io.py` directly — these four functions are owned
entirely by Module 08 and have no `pipeline/reporting.py` caller yet to be tested
alongside (the four `generate_*()` functions remain stubs until WP-2 through WP-5).

Isolated from the project's real `Runtime/Reports/` via the same
`monkeypatch.setattr(runtime_io_module, "_RUNTIME_REPORTS_PATH", ...)` convention
`pipeline/test_execution.py` already established for `_ACTION_LOG_PATH`/
`_RUNTIME_TEMP_PATH`.

Run with: pytest src/storage/test_runtime_io.py -v
"""

from datetime import date

import pytest

import src.storage.runtime_io as runtime_io_module
from src.storage.runtime_io import (
    write_daily_summary,
    write_duplicate_report,
    write_storage_report,
    write_weekly_summary,
)


def _isolate_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_io_module, "_RUNTIME_REPORTS_PATH", tmp_path / "Reports")


# --- write_daily_summary() ---

class TestWriteDailySummary:
    def test_writes_content_verbatim_and_returns_the_path(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        result = write_daily_summary(date(2026, 7, 14), "# Daily Summary\n\nhello")

        expected_path = tmp_path / "Reports" / "Daily Summary" / "summary_2026-07-14.md"
        assert result == str(expected_path)
        assert expected_path.read_text(encoding="utf-8") == "# Daily Summary\n\nhello"

    def test_creates_the_daily_summary_subfolder_if_missing(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        assert not (tmp_path / "Reports").exists()
        write_daily_summary(date(2026, 1, 1), "content")
        assert (tmp_path / "Reports" / "Daily Summary").is_dir()

    def test_filename_matches_the_exact_design_pattern(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        write_daily_summary(date(2026, 3, 5), "content")
        expected = tmp_path / "Reports" / "Daily Summary" / "summary_2026-03-05.md"
        assert expected.exists()

    def test_a_second_call_for_the_same_day_overwrites_in_place(self, tmp_path, monkeypatch):
        """§11: "the same day's file is updated to reflect the day's cumulative
        activity so far" while the day is still open — not a violation of G6.
        Overwrite mechanics themselves are WP-1's own scope; the closed-period
        rule that governs *when* this stops being safe is WP-2's own scope."""
        _isolate_reports(tmp_path, monkeypatch)
        write_daily_summary(date(2026, 7, 14), "first version")
        result = write_daily_summary(date(2026, 7, 14), "second version")

        expected_path = tmp_path / "Reports" / "Daily Summary" / "summary_2026-07-14.md"
        assert result == str(expected_path)
        assert expected_path.read_text(encoding="utf-8") == "second version"


# --- write_weekly_summary() ---

class TestWriteWeeklySummary:
    def test_writes_content_verbatim_and_returns_the_path(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        # 2026-07-14 is a Tuesday in ISO week 29 of 2026.
        result = write_weekly_summary(date(2026, 7, 14), "# Weekly Summary\n\nhello")

        expected_path = tmp_path / "Reports" / "Weekly Summary" / "summary_2026-W29.md"
        assert result == str(expected_path)
        assert expected_path.read_text(encoding="utf-8") == "# Weekly Summary\n\nhello"

    def test_creates_the_weekly_summary_subfolder_if_missing(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        assert not (tmp_path / "Reports").exists()
        write_weekly_summary(date(2026, 7, 14), "content")
        assert (tmp_path / "Reports" / "Weekly Summary").is_dir()

    def test_week_number_is_zero_padded_to_two_digits(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        # 2026-01-05 is a Monday in ISO week 2 of 2026.
        write_weekly_summary(date(2026, 1, 5), "content")
        expected = tmp_path / "Reports" / "Weekly Summary" / "summary_2026-W02.md"
        assert expected.exists()

    def test_iso_year_boundary_case_is_attributed_to_the_correct_iso_year(
        self, tmp_path, monkeypatch
    ):
        """2027-01-01 is a Friday, ISO week 53 of 2026 (not week 1 of 2027) —
        `date.isocalendar()`'s own well-defined stdlib behavior, exercised here
        directly since `write_weekly_summary()` relies on it for the filename;
        the full year-boundary *rollup* correctness is WP-4's own scope."""
        _isolate_reports(tmp_path, monkeypatch)
        write_weekly_summary(date(2027, 1, 1), "content")
        expected = tmp_path / "Reports" / "Weekly Summary" / "summary_2026-W53.md"
        assert expected.exists()

    def test_any_date_within_the_same_iso_week_produces_the_same_filename(
        self, tmp_path, monkeypatch
    ):
        _isolate_reports(tmp_path, monkeypatch)
        write_weekly_summary(date(2026, 7, 13), "monday")   # Monday, week 29
        write_weekly_summary(date(2026, 7, 19), "sunday")   # Sunday, same week 29

        expected = tmp_path / "Reports" / "Weekly Summary" / "summary_2026-W29.md"
        assert expected.read_text(encoding="utf-8") == "sunday"


# --- write_duplicate_report() (WP-3) ---

class TestWriteDuplicateReport:
    def test_writes_content_verbatim_and_returns_the_path(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        result = write_duplicate_report("# Duplicate Report\n\nhello")

        expected_path = tmp_path / "Reports" / "Duplicate Report" / "duplicate_report.md"
        assert result == str(expected_path)
        assert expected_path.read_text(encoding="utf-8") == "# Duplicate Report\n\nhello"

    def test_creates_the_duplicate_report_subfolder_if_missing(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        assert not (tmp_path / "Reports").exists()
        write_duplicate_report("content")
        assert (tmp_path / "Reports" / "Duplicate Report").is_dir()

    def test_filename_is_fixed_not_dated(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        write_duplicate_report("content")
        expected = tmp_path / "Reports" / "Duplicate Report" / "duplicate_report.md"
        assert expected.exists()

    def test_a_second_call_always_overwrites_in_place_no_scoping_parameter(self, tmp_path, monkeypatch):
        """Decision 25: a single, continuously-updated current-state file —
        unlike `write_daily_summary()`, there is no closed-period concept at
        all here, so every call unconditionally overwrites."""
        _isolate_reports(tmp_path, monkeypatch)
        write_duplicate_report("first version")
        result = write_duplicate_report("second version")

        expected_path = tmp_path / "Reports" / "Duplicate Report" / "duplicate_report.md"
        assert result == str(expected_path)
        assert expected_path.read_text(encoding="utf-8") == "second version"

    def test_signature_takes_no_scoping_parameter(self, tmp_path, monkeypatch):
        """Structural check that WP-1's OD-1-agnostic signature (`content: str
        -> str`) was preserved, not expanded — decision 25 confirmed no
        scoping parameter is needed."""
        import inspect

        signature = inspect.signature(write_duplicate_report)
        assert list(signature.parameters) == ["content"]


class TestWriteStorageReportPlaceholder:
    def test_raises_not_implemented_error(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        with pytest.raises(NotImplementedError):
            write_storage_report("some rendered content")

    def test_raises_without_writing_any_file(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        with pytest.raises(NotImplementedError):
            write_storage_report("content")
        assert not (tmp_path / "Reports").exists()


# --- Zero-write immutability beyond Runtime/Reports/ itself (Module 08 Design.md
# §0.3/I1-I3: no FileRecord field and no Database/* file changes at all) ---

class TestZeroWriteImmutabilityBeyondReports:
    def test_write_daily_summary_touches_nothing_outside_reports(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        (tmp_path / "Database").mkdir()
        (tmp_path / "Database" / "sentinel.json").write_text("[]", encoding="utf-8")

        write_daily_summary(date(2026, 7, 14), "content")

        assert (tmp_path / "Database" / "sentinel.json").read_text(encoding="utf-8") == "[]"

    def test_write_weekly_summary_touches_nothing_outside_reports(self, tmp_path, monkeypatch):
        _isolate_reports(tmp_path, monkeypatch)
        (tmp_path / "Database").mkdir()
        (tmp_path / "Database" / "sentinel.json").write_text("[]", encoding="utf-8")

        write_weekly_summary(date(2026, 7, 14), "content")

        assert (tmp_path / "Database" / "sentinel.json").read_text(encoding="utf-8") == "[]"
