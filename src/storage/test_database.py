"""
Unit tests for storage/database.py — focused on the Module 02 typed-field
(de)serialization round-trip (Category, ClassificationSignals). Module 01's storage
behavior (cumulative store, find_by_current_path idempotency) is already exercised
indirectly via pipeline/test_watch_ingest.py; these tests add direct coverage for the
new typed fields specifically.

Run with: pytest src/storage/test_database.py -v
"""

import src.storage.database as database_module
from src.models.classification import Category, ClassificationSignals
from src.models.file_record import FileRecord


def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")


def test_save_and_load_round_trips_category_and_signals(tmp_path, monkeypatch):
    _isolate_store(tmp_path, monkeypatch)

    record = FileRecord(
        file_id="abc-123",
        source_id="downloads",
        original_name="invoice.pdf",
        original_path="/tmp/invoice.pdf",
        current_path="/tmp/invoice.pdf",
        category=Category.INVOICE,
        classification_signals=ClassificationSignals(
            ambiguous=True, non_english_detected=True, detected_language="fr"
        ),
    )
    database_module.save_file_record(record)

    loaded = database_module.load_metadata_store()
    assert len(loaded) == 1
    reloaded = loaded[0]

    # Types must survive the JSON round-trip, not degrade to plain str/dict:
    assert reloaded.category is Category.INVOICE
    assert isinstance(reloaded.category, Category)
    assert isinstance(reloaded.classification_signals, ClassificationSignals)
    assert reloaded.classification_signals.ambiguous is True
    assert reloaded.classification_signals.non_english_detected is True
    assert reloaded.classification_signals.detected_language == "fr"
    assert reloaded.classification_signals.locked is False  # untouched default


def test_load_handles_records_module_02_never_touched(tmp_path, monkeypatch):
    """A record still at its Module 01 defaults (category=None,
    classification_signals=None) must load cleanly — no crash on None fields."""
    _isolate_store(tmp_path, monkeypatch)

    record = FileRecord(
        file_id="def-456",
        source_id="downloads",
        original_name="notes.txt",
        original_path="/tmp/notes.txt",
        current_path="/tmp/notes.txt",
    )
    database_module.save_file_record(record)

    loaded = database_module.load_metadata_store()
    assert loaded[0].category is None
    assert loaded[0].classification_signals is None
