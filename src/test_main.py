"""
Unit test for src/main.py's score_confidence() CLI entry point — specifically its
CLI-level idempotency filter (`confidence_score is None`), which is the only place
this check exists (Module 06 Design.md §11/§24: score_confidence_batch() itself has
no such check on its own — a record already scored still passes its own per-record
eligibility filter and would be re-scored, deterministically, to the same values, if
handed to it again; it's main.py's own re-run filter that actually prevents a second
CLI run from doing anything to an already-scored record).

§21's design-committed test: "a record that's already been scored once
(confidence_score is not None) is confirmed excluded from a second run (idempotency,
mirroring suggest_naming()'s CLI-level idempotency check)" — Implementation Audit
finding M3 (fresh pass).

Also covers Module 07 (Preview, Approval & Execution)'s CLI wiring — WP-12,
Module 07 Implementation Plan.md — `preview()`/`execute()`/`undo()`: the §5
CLI-level eligibility filter (`_eligible_for_execution_records()`), `preview()`'s
read-only tier-grouped output, `execute()`'s externally-supplied `decisions`
parameter (OD-3 deferral), its `capture_user_correction()` call site (§10 step 2,
before execution), its `_load_destination_root()` config reader (the disclosed
WP-12 gap-fill for Open Decision OD-1), its batch-level-failure path when
`destination_root` is unset, its CLI-level idempotency filter (`processed_at is
None`), and `undo()`'s manual-only invocation of `undo_batch()`.

Colocated at src/test_main.py (not under pipeline/) since it exercises the CLI layer
itself, not a single pipeline module.

Run with: pytest src/test_main.py -v
"""

import json

import yaml

import src.main as main_module
import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.classification import Category
from src.models.execution import ApprovalDecision, ApprovalDecisionType
from src.models.file_record import FileRecord


def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


def _isolate_reports_storage(tmp_path, monkeypatch):
    """Extends `_isolate_storage()` with `Runtime/Reports/` — the additional
    real-storage location Module 08's `report()` touches, mirroring
    `pipeline/test_reporting.py`'s own `_isolate_reports()` isolation
    convention."""
    _isolate_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime_io_module, "_RUNTIME_REPORTS_PATH", tmp_path / "Reports")


def _isolate_execution_storage(tmp_path, monkeypatch):
    """Extends `_isolate_storage()` with the two additional real-storage
    locations Module 07's execute()/undo() touch beyond metadata/the action
    log: `Runtime/Temp/` (reconciliation/staging, WP-8/WP-9) and
    `Database/Learning/User Corrections.json` (WP-10) — mirroring
    `pipeline/test_execution.py`'s own `_isolate_database_and_temp()`/
    `_isolate_learning()` isolation conventions exactly.
    """
    _isolate_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime_io_module, "_RUNTIME_TEMP_PATH", tmp_path / "Temp")
    monkeypatch.setattr(database_module, "_USER_CORRECTIONS_PATH", tmp_path / "User Corrections.json")


def _write_sources_config(tmp_path, monkeypatch, destination_root=None):
    """Writes a sandboxed `sources.yaml` (mirroring the real file's shape,
    `src/config/sources.yaml`) and points `main_module._SOURCES_CONFIG_PATH`
    at it — so `_load_destination_root()` (WP-12) is exercised against a real,
    isolated config file rather than the project's own real config.
    """
    config_path = tmp_path / "sources.yaml"
    config = {
        "sources": [
            {"source_id": "downloads", "path": None, "type": "local_folder",
             "enabled": True, "recursive": False},
        ],
        "execution_mode": "manual",
        "destination_root": str(destination_root) if destination_root is not None else None,
    }
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(main_module, "_SOURCES_CONFIG_PATH", config_path)


def _make_execution_record(
    tmp_path, file_id, name="Amazon_2026-07-05.pdf", tier="auto",
    batch_id="batch-1", discovered_at="2026-01-01T00:00:00Z",
    suggested_destination="Finance/", category=Category.INVOICE,
    confidence_score=95, processed_at=None,
):
    """Builds and persists one execution-eligible `FileRecord` (§5's filter:
    status/category/suggested_name/confidence_score all populated) backed by a
    real file on disk, since `execute()` ultimately reaches `ExecutionEngine`'s
    real `Path.rename()` move — never mocked, mirroring
    `pipeline/test_execution.py`'s own established real-filesystem testing
    convention.
    """
    source = tmp_path / f"{file_id}_{name}"
    source.write_text(f"content-{file_id}")
    record = FileRecord(
        file_id=file_id, source_id="downloads", original_name=name,
        original_path=str(source), current_path=str(source),
        status="discovered", category=category,
        discovered_at=discovered_at, batch_id=batch_id,
        tier=tier, confidence_score=confidence_score,
        suggested_name=name, suggested_destination=suggested_destination,
        processed_at=processed_at,
    )
    database_module.save_file_record(record)
    return record


def _score_confidence_log_entries():
    log_path = runtime_io_module.action_log_path()
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if json.loads(line)["action"] == "score_confidence"]


def test_score_confidence_cli_skips_already_scored_record_on_second_run(tmp_path, monkeypatch, capsys):
    _isolate_storage(tmp_path, monkeypatch)

    record = FileRecord(
        file_id="cli-1", source_id="downloads", original_name="invoice.pdf",
        original_path="/tmp/invoice.pdf", current_path="/tmp/invoice.pdf",
        extension=".pdf", status="discovered", category=Category.INVOICE,
        discovered_at="2026-01-01T00:00:00Z",
        extracted_metadata={
            "vendor": "Amazon", "invoice_date": "2026-07-05",
            "invoice_number": "INV1", "amount": "100", "currency": "USD", "tax_type": "none",
        },
        suggested_name="Amazon_2026-07-05.pdf", batch_id="batch-1",
    )
    database_module.save_file_record(record)

    # First run: the record is eligible (confidence_score is None) and gets scored.
    main_module.score_confidence()

    first_run_records = database_module.load_metadata_store()
    scored = next(r for r in first_run_records if r.file_id == "cli-1")
    assert scored.confidence_score is not None
    first_run_score = scored.confidence_score
    first_run_breakdown = scored.confidence_breakdown
    first_run_tier = scored.tier

    entries_after_first_run = _score_confidence_log_entries()
    assert len(entries_after_first_run) == 1

    # Second run: confidence_score is no longer None, so the CLI-level idempotency
    # filter must exclude this record entirely — score_confidence_batch() is never
    # even called with it.
    capsys.readouterr()  # discard first run's stdout
    main_module.score_confidence()
    captured = capsys.readouterr()
    assert "Nothing to score" in captured.out

    second_run_records = database_module.load_metadata_store()
    reloaded = next(r for r in second_run_records if r.file_id == "cli-1")
    assert reloaded.confidence_score == first_run_score
    assert reloaded.confidence_breakdown == first_run_breakdown
    assert reloaded.tier == first_run_tier

    entries_after_second_run = _score_confidence_log_entries()
    assert len(entries_after_second_run) == 1
    assert entries_after_second_run == entries_after_first_run


# --- Module 07 (Preview, Approval & Execution) CLI wiring — WP-12 ---


def test_preview_prints_nothing_to_preview_when_no_eligible_records(tmp_path, monkeypatch, capsys):
    _isolate_execution_storage(tmp_path, monkeypatch)

    main_module.preview()

    captured = capsys.readouterr()
    assert "Nothing to preview" in captured.out


def test_preview_groups_rows_by_tier_and_never_writes_anything(tmp_path, monkeypatch, capsys):
    """Read-only (§9): preview() must not touch the metadata store, the action
    log, or the filesystem — only print."""
    _isolate_execution_storage(tmp_path, monkeypatch)

    _make_execution_record(tmp_path, "auto-1", name="a.pdf", tier="auto")
    _make_execution_record(tmp_path, "appr-1", name="b.pdf", tier="approval_required", confidence_score=85)
    _make_execution_record(tmp_path, "rev-1", name="c.pdf", tier="review_required", confidence_score=40)

    main_module.preview()

    captured = capsys.readouterr()
    assert "Previewing 3 file(s):" in captured.out
    assert "Auto (will execute without further input) — 1:" in captured.out
    assert "Needs your decision — 1:" in captured.out
    assert "Needs attention (never auto-filed) — 1:" in captured.out
    assert "appr-1" in captured.out
    assert "rev-1" in captured.out

    # No side effects: none of the three records were mutated, no action log
    # entries were written, and the source files are still exactly where they
    # started.
    records_after = {r.file_id: r for r in database_module.load_metadata_store()}
    assert records_after["auto-1"].processed_at is None
    assert records_after["appr-1"].processed_at is None
    assert records_after["rev-1"].processed_at is None
    assert not runtime_io_module.action_log_path().exists()
    assert (tmp_path / "auto-1_a.pdf").exists()


def test_execute_prints_nothing_to_execute_when_no_eligible_records(tmp_path, monkeypatch, capsys):
    _isolate_execution_storage(tmp_path, monkeypatch)

    main_module.execute()

    captured = capsys.readouterr()
    assert "Nothing to execute" in captured.out


def test_execute_auto_tier_executes_without_any_decisions_supplied(tmp_path, monkeypatch, capsys):
    """G4: an `auto`-tier record needs no human decision at all — `execute()`'s
    default `decisions={}` must still file it."""
    _isolate_execution_storage(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _write_sources_config(tmp_path, monkeypatch, destination_root=library_root)

    _make_execution_record(tmp_path, "auto-1", name="a.pdf", tier="auto", suggested_destination="Finance/")

    main_module.execute()

    captured = capsys.readouterr()
    assert "Executed: 1" in captured.out
    assert "Declined" not in captured.out
    assert "Failed" not in captured.out

    moved = library_root / "Finance" / "a.pdf"
    assert moved.exists()
    assert not (tmp_path / "auto-1_a.pdf").exists()

    record = next(r for r in database_module.load_metadata_store() if r.file_id == "auto-1")
    assert record.processed_at is not None
    assert record.approved_by == "auto"
    assert record.current_path == str(moved)


def test_execute_missing_destination_root_blocks_whole_batch_and_reports_failed(tmp_path, monkeypatch, capsys):
    """`_load_destination_root()` returns `None` when `destination_root` is
    unset — execute_batch()'s own already-approved WP-9 precondition check
    (`_validate_library_root()`) must be the thing that turns this into a
    logged, batch-level failure; execute() itself never raises or duplicates
    that decision (see `_load_destination_root()`'s own docstring)."""
    _isolate_execution_storage(tmp_path, monkeypatch)
    _write_sources_config(tmp_path, monkeypatch, destination_root=None)

    _make_execution_record(tmp_path, "auto-1", name="a.pdf", tier="auto")

    main_module.execute()

    captured = capsys.readouterr()
    assert "Failed:    1" in captured.out
    assert "Executed: 0" in captured.out

    record = next(r for r in database_module.load_metadata_store() if r.file_id == "auto-1")
    assert record.processed_at is None  # never executed
    assert (tmp_path / "auto-1_a.pdf").exists()  # never moved

    log_lines = runtime_io_module.action_log_path().read_text(encoding="utf-8").strip().splitlines()
    entries = [json.loads(line) for line in log_lines]
    assert any(e["action"] == "error" and e["file_id"] == "auto-1" for e in entries)


def test_execute_approve_with_edit_captures_correction_before_moving(tmp_path, monkeypatch, capsys):
    """§10 step 2: an edit is captured to Database/Learning/User Corrections.json
    before execute_batch() runs; the edited name (not the original suggestion)
    is what actually gets filed."""
    _isolate_execution_storage(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _write_sources_config(tmp_path, monkeypatch, destination_root=library_root)

    _make_execution_record(
        tmp_path, "appr-1", name="b.pdf", tier="approval_required",
        suggested_destination="Finance/", confidence_score=85,
    )
    decisions = {
        "appr-1": ApprovalDecision(
            file_id="appr-1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
            edited_name="Custom.pdf",
        ),
    }

    main_module.execute(decisions=decisions)

    captured = capsys.readouterr()
    assert "Executed: 1" in captured.out

    moved = library_root / "Finance" / "Custom.pdf"
    assert moved.exists()

    corrections = database_module._load_index(database_module._USER_CORRECTIONS_PATH, [])
    assert len(corrections) == 1
    assert corrections[0]["file_id"] == "appr-1"
    assert corrections[0]["field"] == "filename"
    assert corrections[0]["suggested_value"] == "b.pdf"
    assert corrections[0]["corrected_value"] == "Custom.pdf"


def test_execute_reject_declines_captures_correction_and_never_moves_the_file(tmp_path, monkeypatch, capsys):
    _isolate_execution_storage(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _write_sources_config(tmp_path, monkeypatch, destination_root=library_root)

    _make_execution_record(
        tmp_path, "appr-2", name="c.pdf", tier="approval_required", confidence_score=85,
    )
    decisions = {
        "appr-2": ApprovalDecision(file_id="appr-2", decision=ApprovalDecisionType.REJECT),
    }

    main_module.execute(decisions=decisions)

    captured = capsys.readouterr()
    assert "Declined:  1" in captured.out
    assert "Executed: 0" in captured.out

    assert (tmp_path / "appr-2_c.pdf").exists()  # never moved
    record = next(r for r in database_module.load_metadata_store() if r.file_id == "appr-2")
    assert record.processed_at is None

    corrections = database_module._load_index(database_module._USER_CORRECTIONS_PATH, [])
    assert len(corrections) == 1
    assert corrections[0]["field"] == "category"
    assert corrections[0]["corrected_value"] is None


def test_execute_review_required_never_executes_even_with_a_forged_decision(tmp_path, monkeypatch, capsys):
    """I2, re-verified at the CLI boundary: a review_required record must never
    execute, even if a (malformed/malicious) decisions dict supplies an
    APPROVE_AS_SUGGESTED entry for it."""
    _isolate_execution_storage(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _write_sources_config(tmp_path, monkeypatch, destination_root=library_root)

    _make_execution_record(
        tmp_path, "rev-1", name="d.pdf", tier="review_required", confidence_score=40,
    )
    decisions = {
        "rev-1": ApprovalDecision(file_id="rev-1", decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
    }

    main_module.execute(decisions=decisions)

    captured = capsys.readouterr()
    assert "Skipped (review_required or no decision yet): 1" in captured.out

    assert (tmp_path / "rev-1_d.pdf").exists()  # never moved
    record = next(r for r in database_module.load_metadata_store() if r.file_id == "rev-1")
    assert record.processed_at is None


def test_execute_cli_idempotency_skips_already_processed_record_on_second_run(tmp_path, monkeypatch, capsys):
    _isolate_execution_storage(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _write_sources_config(tmp_path, monkeypatch, destination_root=library_root)

    _make_execution_record(tmp_path, "auto-1", name="a.pdf", tier="auto")

    main_module.execute()
    first_run_records = database_module.load_metadata_store()
    first_processed_at = next(r for r in first_run_records if r.file_id == "auto-1").processed_at
    assert first_processed_at is not None

    capsys.readouterr()  # discard first run's stdout
    main_module.execute()
    captured = capsys.readouterr()
    assert "Nothing to execute" in captured.out

    second_run_records = database_module.load_metadata_store()
    reloaded = next(r for r in second_run_records if r.file_id == "auto-1")
    assert reloaded.processed_at == first_processed_at  # untouched by the second run


def test_undo_prints_nothing_to_undo_when_batch_has_no_move_entries(tmp_path, monkeypatch, capsys):
    _isolate_execution_storage(tmp_path, monkeypatch)

    main_module.undo("batch-does-not-exist")

    captured = capsys.readouterr()
    assert "Nothing to undo" in captured.out


def test_undo_reverses_an_executed_batch_and_restores_the_original_file(tmp_path, monkeypatch, capsys):
    """A full execute() -> undo() cycle through the real CLI functions —
    undo() is a separate, explicitly-invoked command (§15: manual operation
    only), never called from execute() itself."""
    _isolate_execution_storage(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _write_sources_config(tmp_path, monkeypatch, destination_root=library_root)

    _make_execution_record(tmp_path, "auto-1", name="a.pdf", tier="auto", suggested_destination="Finance/")

    main_module.execute()
    capsys.readouterr()  # discard execute()'s stdout

    moved = library_root / "Finance" / "a.pdf"
    assert moved.exists()

    main_module.undo("batch-1")
    captured = capsys.readouterr()
    assert "undone" in captured.out
    assert "Undo results for batch batch-1 (1 entrie(s)):" in captured.out

    assert not moved.exists()
    assert (tmp_path / "auto-1_a.pdf").exists()  # restored to its original location

    record = next(r for r in database_module.load_metadata_store() if r.file_id == "auto-1")
    assert record.processed_at is None  # needs_execution() recognizes it as eligible again


def test_execute_source_never_calls_undo_batch_directly(tmp_path):
    """Structural check of the §15 "undo is a manual operation only" boundary:
    execute()'s own source code must not reference undo_batch() at all — the
    only call site for undo_batch() in this file is undo()'s own body."""
    import inspect

    execute_source = inspect.getsource(main_module.execute)
    assert "undo_batch" not in execute_source


# --- report() (Module 08, WP-6) ---
#
# Decision 26: a single report() call invokes all four generate_*() functions
# in one pass. Decision 31: report() is a separate, explicitly-invoked command,
# never part of the automatic `if __name__ == "__main__":` chain. §12 Layer 2:
# each report type's failure is isolated from the other three.

def test_report_generates_all_four_reports_and_prints_their_paths(tmp_path, monkeypatch, capsys):
    _isolate_reports_storage(tmp_path, monkeypatch)

    main_module.report()

    captured = capsys.readouterr()
    assert "Report generation:" in captured.out
    assert "Daily Summary" in captured.out
    assert "Weekly Summary" in captured.out
    assert "Duplicate Report" in captured.out
    assert "Storage Report" in captured.out
    assert "Module 08 report generation complete." in captured.out

    assert (tmp_path / "Reports" / "Duplicate Report" / "duplicate_report.md").exists()
    assert (tmp_path / "Reports" / "Storage Report" / "storage_report.md").exists()
    assert list((tmp_path / "Reports" / "Daily Summary").glob("summary_*.md"))
    assert list((tmp_path / "Reports" / "Weekly Summary").glob("summary_*.md"))


def test_report_failure_in_daily_summary_does_not_block_the_other_three(tmp_path, monkeypatch, capsys):
    _isolate_reports_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(
        main_module, "generate_daily_summary",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    main_module.report()

    captured = capsys.readouterr()
    assert "Daily Summary: FAILED" in captured.out
    assert "boom" in captured.out
    assert "1 report(s) failed to generate" in captured.out

    assert (tmp_path / "Reports" / "Duplicate Report" / "duplicate_report.md").exists()
    assert (tmp_path / "Reports" / "Storage Report" / "storage_report.md").exists()
    assert list((tmp_path / "Reports" / "Weekly Summary").glob("summary_*.md"))
    assert not (tmp_path / "Reports" / "Daily Summary").exists()


def test_report_failure_in_weekly_summary_does_not_block_the_other_three(tmp_path, monkeypatch, capsys):
    _isolate_reports_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(
        main_module, "generate_weekly_summary",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    main_module.report()

    captured = capsys.readouterr()
    assert "Weekly Summary: FAILED" in captured.out

    assert (tmp_path / "Reports" / "Duplicate Report" / "duplicate_report.md").exists()
    assert (tmp_path / "Reports" / "Storage Report" / "storage_report.md").exists()
    assert list((tmp_path / "Reports" / "Daily Summary").glob("summary_*.md"))
    assert not (tmp_path / "Reports" / "Weekly Summary").exists()


def test_report_failure_in_duplicate_report_does_not_block_the_other_three(tmp_path, monkeypatch, capsys):
    _isolate_reports_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(
        main_module, "generate_duplicate_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    main_module.report()

    captured = capsys.readouterr()
    assert "Duplicate Report: FAILED" in captured.out

    assert (tmp_path / "Reports" / "Storage Report" / "storage_report.md").exists()
    assert list((tmp_path / "Reports" / "Daily Summary").glob("summary_*.md"))
    assert list((tmp_path / "Reports" / "Weekly Summary").glob("summary_*.md"))
    assert not (tmp_path / "Reports" / "Duplicate Report").exists()


def test_report_failure_in_storage_report_does_not_block_the_other_three(tmp_path, monkeypatch, capsys):
    _isolate_reports_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(
        main_module, "generate_storage_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    main_module.report()

    captured = capsys.readouterr()
    assert "Storage Report: FAILED" in captured.out

    assert (tmp_path / "Reports" / "Duplicate Report" / "duplicate_report.md").exists()
    assert list((tmp_path / "Reports" / "Daily Summary").glob("summary_*.md"))
    assert list((tmp_path / "Reports" / "Weekly Summary").glob("summary_*.md"))
    assert not (tmp_path / "Reports" / "Storage Report").exists()


def test_report_never_appends_to_the_action_log(tmp_path, monkeypatch):
    _isolate_reports_storage(tmp_path, monkeypatch)
    (tmp_path / "action_log.jsonl").write_text('{"sentinel": true}\n', encoding="utf-8")
    before = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")

    main_module.report()

    after = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8")
    assert before == after


def test_report_never_writes_to_the_metadata_store(tmp_path, monkeypatch):
    _isolate_reports_storage(tmp_path, monkeypatch)
    database_module.save_file_record(FileRecord(
        file_id="f1", source_id="downloads", original_name="invoice.pdf",
        original_path="/tmp/invoice.pdf", current_path="/tmp/invoice.pdf",
        status="discovered", category=Category.INVOICE,
        suggested_destination="Finance/", size_bytes=1000,
        processed_at="2026-07-14T12:00:00+00:00",
    ))
    before = database_module.metadata_store_path().read_text(encoding="utf-8")

    main_module.report()

    after = database_module.metadata_store_path().read_text(encoding="utf-8")
    assert before == after


def test_report_writes_only_within_runtime_reports(tmp_path, monkeypatch):
    _isolate_reports_storage(tmp_path, monkeypatch)
    (tmp_path / "Database").mkdir()
    (tmp_path / "Database" / "sentinel.json").write_text("[]", encoding="utf-8")

    main_module.report()

    assert (tmp_path / "Database" / "sentinel.json").read_text(encoding="utf-8") == "[]"


def test_report_repeated_execution_is_idempotent_with_unchanged_data(tmp_path, monkeypatch):
    """Decision 25/G5: Duplicate Report and Storage Report are single,
    continuously-updated current-state files — re-running report() against
    unchanged source data must reproduce byte-for-byte identical content."""
    _isolate_reports_storage(tmp_path, monkeypatch)

    main_module.report()
    duplicate_first = (tmp_path / "Reports" / "Duplicate Report" / "duplicate_report.md").read_text(encoding="utf-8")
    storage_first = (tmp_path / "Reports" / "Storage Report" / "storage_report.md").read_text(encoding="utf-8")

    main_module.report()
    duplicate_second = (tmp_path / "Reports" / "Duplicate Report" / "duplicate_report.md").read_text(encoding="utf-8")
    storage_second = (tmp_path / "Reports" / "Storage Report" / "storage_report.md").read_text(encoding="utf-8")

    assert duplicate_first == duplicate_second
    assert storage_first == storage_second


def test_report_not_part_of_the_automatic_main_chain():
    """Decision 31: report() is a separate, explicitly-invoked command —
    never added to the automatic chain at the bottom of main.py."""
    import inspect

    source = inspect.getsource(main_module)
    chain_start = source.index('if __name__ == "__main__":')
    chain_block = source[chain_start:]
    assert "report()" not in chain_block
