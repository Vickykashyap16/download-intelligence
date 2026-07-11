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

Colocated at src/test_main.py (not under pipeline/) since it exercises the CLI layer
itself, not a single pipeline module.

Run with: pytest src/test_main.py -v
"""

import json

import src.main as main_module
import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.classification import Category
from src.models.file_record import FileRecord


def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


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
