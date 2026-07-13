"""
Unit tests for storage/database.py — focused on the Module 02 typed-field
(de)serialization round-trip (Category, ClassificationSignals). Module 01's storage
behavior (cumulative store, find_by_current_path idempotency) is already exercised
indirectly via pipeline/test_watch_ingest.py; these tests add direct coverage for the
new typed fields specifically.

Run with: pytest src/storage/test_database.py -v
"""

from pathlib import Path

from PIL import Image

import src.storage.database as database_module
from src.models.classification import Category, ClassificationSignals
from src.models.duplicate import DuplicateSignals
from src.models.file_record import FileRecord
from src.models.naming import NamingSignals


def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")


def _isolate_file_index(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_HASH_INDEX_PATH", tmp_path / "hash_index.json")
    monkeypatch.setattr(database_module, "_PHASH_INDEX_PATH", tmp_path / "phash_index.json")
    monkeypatch.setattr(database_module, "_NAME_INDEX_PATH", tmp_path / "name_index.json")
    monkeypatch.setattr(database_module, "_VERSION_HISTORY_PATH", tmp_path / "version_history.json")


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


# --- Module 04 (Duplicate & Version Detection) — Build-out/04 Duplicate & Version
# Detection/Module 04 Design.md §16 ---

def test_save_and_load_round_trips_duplicate_signals(tmp_path, monkeypatch):
    _isolate_store(tmp_path, monkeypatch)

    record = FileRecord(
        file_id="dup-1",
        source_id="downloads",
        original_name="Resume_v2.pdf",
        original_path="/tmp/Resume_v2.pdf",
        current_path="/tmp/Resume_v2.pdf",
        category=Category.RESUME,
        version_group_id="group-1",
        version_rank="latest",
        duplicate_signals=DuplicateSignals(version_conflict=True),
    )
    database_module.save_file_record(record)

    reloaded = database_module.load_metadata_store()[0]
    assert isinstance(reloaded.duplicate_signals, DuplicateSignals)
    assert reloaded.duplicate_signals.version_conflict is True
    assert reloaded.duplicate_signals.exact_duplicate is False  # untouched default
    assert reloaded.version_group_id == "group-1"
    assert reloaded.version_rank == "latest"


# --- Module 05 (Naming & Destination) — Build-out/05 Naming & Destination/
# Module 05 Design.md §5/§25 ---

def test_save_and_load_round_trips_naming_signals(tmp_path, monkeypatch):
    _isolate_store(tmp_path, monkeypatch)

    record = FileRecord(
        file_id="name-1",
        source_id="downloads",
        original_name="invoice.pdf",
        original_path="/tmp/invoice.pdf",
        current_path="/tmp/invoice.pdf",
        category=Category.INVOICE,
        suggested_name="Unknown_Vendor_2026-07-05.pdf",
        suggested_destination="Finance/",
        naming_signals=NamingSignals(fields_fell_back=["vendor"]),
    )
    database_module.save_file_record(record)

    reloaded = database_module.load_metadata_store()[0]
    assert isinstance(reloaded.naming_signals, NamingSignals)
    assert reloaded.naming_signals.fields_fell_back == ["vendor"]
    assert reloaded.suggested_name == "Unknown_Vendor_2026-07-05.pdf"
    assert reloaded.suggested_destination == "Finance/"


def test_load_handles_records_module_05_never_touched(tmp_path, monkeypatch):
    """A record still at its pre-Module-05 defaults (suggested_name=None,
    naming_signals=None) must load cleanly — no crash on None fields."""
    _isolate_store(tmp_path, monkeypatch)

    record = FileRecord(
        file_id="name-2",
        source_id="downloads",
        original_name="notes.txt",
        original_path="/tmp/notes.txt",
        current_path="/tmp/notes.txt",
    )
    database_module.save_file_record(record)

    loaded = database_module.load_metadata_store()
    assert loaded[0].suggested_name is None
    assert loaded[0].naming_signals is None


def test_lookup_hash_returns_none_when_not_indexed(tmp_path, monkeypatch):
    _isolate_file_index(tmp_path, monkeypatch)
    assert database_module.lookup_hash("nonexistent-sha256") is None


def test_lookup_hash_finds_indexed_file_id(tmp_path, monkeypatch):
    _isolate_file_index(tmp_path, monkeypatch)
    database_module._write_index(database_module._HASH_INDEX_PATH, {"abc123": "file-1"})
    assert database_module.lookup_hash("abc123") == "file-1"


def test_update_indexes_adds_content_hash_to_hash_index(tmp_path, monkeypatch):
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)

    record = FileRecord(
        file_id="file-1", source_id="downloads", original_name="a.pdf",
        original_path="/tmp/a.pdf", current_path="/tmp/a.pdf",
        content_hash="hash-abc",
    )
    database_module.update_indexes(record)

    assert database_module.lookup_hash("hash-abc") == "file-1"


def test_update_indexes_never_overwrites_first_filer_of_a_hash(tmp_path, monkeypatch):
    """The first file filed under a given hash is definitionally never anyone
    else's duplicate (§16) — a second update_indexes() call for a different
    file_id with the same hash must not steal the original mapping."""
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)

    first = FileRecord(
        file_id="file-1", source_id="downloads", original_name="a.pdf",
        original_path="/tmp/a.pdf", current_path="/tmp/a.pdf", content_hash="hash-abc",
    )
    second = FileRecord(
        file_id="file-2", source_id="downloads", original_name="a_copy.pdf",
        original_path="/tmp/a_copy.pdf", current_path="/tmp/a_copy.pdf", content_hash="hash-abc",
    )
    database_module.update_indexes(first)
    database_module.update_indexes(second)

    assert database_module.lookup_hash("hash-abc") == "file-1"


def test_lookup_phash_matches_within_and_outside_threshold(tmp_path, monkeypatch):
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)
    # Two hex phashes differing by exactly one bit (last hex digit 0 vs 1).
    database_module._write_index(
        database_module._PHASH_INDEX_PATH,
        {"00000000000000f0": ["file-near"], "ffffffffffffffff": ["file-far"]},
    )
    near = FileRecord(
        file_id="file-near", source_id="downloads", original_name="near.jpg",
        original_path="/tmp/near.jpg", current_path="/tmp/near.jpg", category=Category.IMAGE,
    )
    far = FileRecord(
        file_id="file-far", source_id="downloads", original_name="far.jpg",
        original_path="/tmp/far.jpg", current_path="/tmp/far.jpg", category=Category.IMAGE,
    )
    database_module.save_file_record(near)
    database_module.save_file_record(far)

    matches = database_module.lookup_phash_matches("00000000000000f1", max_distance=2, category=Category.IMAGE)
    assert "file-near" in matches
    assert "file-far" not in matches


def test_lookup_phash_matches_excludes_different_category_even_within_distance(tmp_path, monkeypatch):
    """Post-freeze correction #4 (Module 04 UAT Finding UAT-1): an Image and a
    Screenshot that happen to share (or nearly share) a perceptual hash must never
    be returned as a match for each other — §9/F5 requires category scoping for
    near-duplicate detection exactly as much as for version-chain detection, the
    same guarantee `lookup_name_matches()` already provides."""
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)

    database_module._write_index(
        database_module._PHASH_INDEX_PATH,
        {"0000000000000000": ["img-1", "shot-1"]},
    )
    image_record = FileRecord(
        file_id="img-1", source_id="downloads", original_name="photo.jpg",
        original_path="/tmp/photo.jpg", current_path="/tmp/photo.jpg", category=Category.IMAGE,
    )
    screenshot_record = FileRecord(
        file_id="shot-1", source_id="downloads", original_name="shot.png",
        original_path="/tmp/shot.png", current_path="/tmp/shot.png", category=Category.SCREENSHOT,
    )
    database_module.save_file_record(image_record)
    database_module.save_file_record(screenshot_record)

    # Exact same hash (distance 0) -- would match on hash alone; category must still
    # scope the result: querying as Image finds the Image but never the Screenshot,
    # and vice versa (lookup_phash_matches() itself doesn't exclude the querying
    # record's own file_id -- that filtering is the caller's job, per
    # _check_near_duplicate()'s `if file_id != record.file_id`).
    matches_for_image = database_module.lookup_phash_matches("0000000000000000", max_distance=5, category=Category.IMAGE)
    assert "img-1" in matches_for_image
    assert "shot-1" not in matches_for_image

    matches_for_screenshot = database_module.lookup_phash_matches("0000000000000000", max_distance=5, category=Category.SCREENSHOT)
    assert "shot-1" in matches_for_screenshot
    assert "img-1" not in matches_for_screenshot


def test_update_indexes_adds_perceptual_hash_for_image_category(tmp_path, monkeypatch):
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)

    photo_path = tmp_path / "photo.png"
    Image.new("RGB", (64, 64), color=(10, 20, 30)).save(photo_path)

    record = FileRecord(
        file_id="img-1", source_id="downloads", original_name="photo.png",
        original_path=str(photo_path), current_path=str(photo_path),
        content_hash="hash-img", category=Category.IMAGE,
    )
    database_module.update_indexes(record)

    index = database_module._load_index(database_module._PHASH_INDEX_PATH, {})
    assert any("img-1" in file_ids for file_ids in index.values())


def test_lookup_name_matches_finds_similar_names_same_category_only(tmp_path, monkeypatch):
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)

    same_category = FileRecord(
        file_id="resume-old", source_id="downloads", original_name="Resume_v1.pdf",
        original_path="/tmp/Resume_v1.pdf", current_path="/tmp/Resume_v1.pdf",
        category=Category.RESUME,
    )
    different_category = FileRecord(
        file_id="other-cat", source_id="downloads", original_name="Resume_v1.pdf",
        original_path="/tmp/other/Resume_v1.pdf", current_path="/tmp/other/Resume_v1.pdf",
        category=Category.DOCUMENT,
    )
    database_module.save_file_record(same_category)
    database_module.save_file_record(different_category)
    database_module.update_indexes(same_category)
    database_module.update_indexes(different_category)

    matches = database_module.lookup_name_matches("resume", Category.RESUME)
    assert "resume-old" in matches
    assert "other-cat" not in matches


def test_lookup_name_matches_below_threshold_returns_nothing(tmp_path, monkeypatch):
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)

    unrelated = FileRecord(
        file_id="unrelated-1", source_id="downloads", original_name="Vacation_Photos.pdf",
        original_path="/tmp/Vacation_Photos.pdf", current_path="/tmp/Vacation_Photos.pdf",
        category=Category.RESUME,
    )
    database_module.save_file_record(unrelated)
    database_module.update_indexes(unrelated)

    matches = database_module.lookup_name_matches("resume", Category.RESUME)
    assert matches == []


# --- M3 (Independent Implementation Audit, missing from the original pass):
# filename-similarity boundary cases exercising _NAME_SIMILARITY_THRESHOLD (90)
# directly — score exactly at the threshold, one point above, one point below.
# Fixtures use a single-character substitution ('0', never present in the base
# alphabet string, so every substitution is a real edit) at computed positions so
# rapidfuzz.fuzz.ratio() lands on an exact integer, verified via a sanity-check
# assertion in each test rather than assumed from hand-derived positions. ---

def test_lookup_name_matches_boundary_exactly_at_threshold_is_included(tmp_path, monkeypatch):
    """A candidate scoring exactly at the threshold (90) must be included — an
    inclusive boundary (§10: "treat a score >= 90... as a candidate match")."""
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)

    base = "abcdefghij"
    stored = FileRecord(
        file_id="boundary-90", source_id="downloads", original_name=f"{base}.pdf",
        original_path=f"/tmp/{base}.pdf", current_path=f"/tmp/{base}.pdf",
        category=Category.RESUME,
    )
    database_module.save_file_record(stored)
    database_module.update_indexes(stored)

    query = "0" + base[1:]  # one substitution -> exactly 90.0
    from rapidfuzz import fuzz
    assert fuzz.ratio(base, query) == 90.0  # sanity-check the fixture itself

    matches = database_module.lookup_name_matches(query, Category.RESUME)
    assert "boundary-90" in matches


def test_lookup_name_matches_boundary_one_below_threshold_is_excluded(tmp_path, monkeypatch):
    """One point below the threshold (89) must be excluded."""
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)

    base = "".join(chr(97 + (i % 26)) for i in range(100))
    stored = FileRecord(
        file_id="boundary-89", source_id="downloads", original_name=f"{base}.pdf",
        original_path=f"/tmp/{base}.pdf", current_path=f"/tmp/{base}.pdf",
        category=Category.RESUME,
    )
    database_module.save_file_record(stored)
    database_module.update_indexes(stored)

    query = list(base)
    for position in range(0, 99, 9):  # 11 substitutions -> exactly 89.0
        query[position] = "0"
    query = "".join(query)

    from rapidfuzz import fuzz
    assert fuzz.ratio(base, query) == 89.0  # sanity-check the fixture itself

    matches = database_module.lookup_name_matches(query, Category.RESUME)
    assert "boundary-89" not in matches


def test_lookup_name_matches_boundary_one_above_threshold_is_included(tmp_path, monkeypatch):
    """One point above the threshold (91) must be included."""
    _isolate_file_index(tmp_path, monkeypatch)
    _isolate_store(tmp_path, monkeypatch)

    base = "".join(chr(97 + (i % 26)) for i in range(100))
    stored = FileRecord(
        file_id="boundary-91", source_id="downloads", original_name=f"{base}.pdf",
        original_path=f"/tmp/{base}.pdf", current_path=f"/tmp/{base}.pdf",
        category=Category.RESUME,
    )
    database_module.save_file_record(stored)
    database_module.update_indexes(stored)

    query = list(base)
    for position in range(0, 99, 11):  # 9 substitutions -> exactly 91.0
        query[position] = "0"
    query = "".join(query)

    from rapidfuzz import fuzz
    assert fuzz.ratio(base, query) == 91.0  # sanity-check the fixture itself

    matches = database_module.lookup_name_matches(query, Category.RESUME)
    assert "boundary-91" in matches


def test_record_version_history_creates_and_updates_group(tmp_path, monkeypatch):
    _isolate_file_index(tmp_path, monkeypatch)

    v1 = FileRecord(
        file_id="v1", source_id="downloads", original_name="Resume_v1.pdf",
        original_path="/tmp/Resume_v1.pdf", current_path="/tmp/Resume_v1.pdf",
    )
    database_module.record_version_history("group-1", v1, "latest")

    history = database_module._load_index(database_module._VERSION_HISTORY_PATH, {})
    assert history["group-1"]["files"][0]["file_id"] == "v1"
    assert history["group-1"]["files"][0]["rank_at_time"] == "latest"

    # Superseding v1 updates its existing entry, not append a duplicate one.
    database_module.record_version_history("group-1", v1, "superseded")
    history = database_module._load_index(database_module._VERSION_HISTORY_PATH, {})
    assert len(history["group-1"]["files"]) == 1
    assert history["group-1"]["files"][0]["rank_at_time"] == "superseded"
    assert history["group-1"]["files"][0]["superseded_at"] is not None


# --- WP-10: log_user_correction() (§19/G7, Module 07 Implementation Plan.md) ---

def _isolate_learning(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database_module, "_USER_CORRECTIONS_PATH", tmp_path / "User Corrections.json"
    )


def test_log_user_correction_creates_file_and_matches_readme_schema(tmp_path, monkeypatch):
    """Schema shape matches Database/Learning/README.md's own worked example
    exactly: file_id, field, suggested_value, corrected_value, category,
    timestamp — no more, no fewer keys."""
    _isolate_learning(tmp_path, monkeypatch)

    database_module.log_user_correction(
        file_id="f1", field_name="filename",
        suggested_value="invoice.pdf", corrected_value="Amazon_Invoice.pdf",
        category="Invoice",
    )

    corrections = database_module._load_index(database_module._USER_CORRECTIONS_PATH, [])
    assert len(corrections) == 1
    entry = corrections[0]
    assert set(entry.keys()) == {
        "file_id", "field", "suggested_value", "corrected_value", "category", "timestamp",
    }
    assert entry["file_id"] == "f1"
    assert entry["field"] == "filename"
    assert entry["suggested_value"] == "invoice.pdf"
    assert entry["corrected_value"] == "Amazon_Invoice.pdf"
    assert entry["category"] == "Invoice"
    assert entry["timestamp"]  # non-empty, real ISO timestamp


def test_log_user_correction_is_append_only_across_multiple_calls(tmp_path, monkeypatch):
    _isolate_learning(tmp_path, monkeypatch)

    database_module.log_user_correction(
        file_id="f1", field_name="filename",
        suggested_value="a.pdf", corrected_value="b.pdf", category="Invoice",
    )
    database_module.log_user_correction(
        file_id="f2", field_name="destination",
        suggested_value="Finance/", corrected_value="Finance/2026/", category="Invoice",
    )

    corrections = database_module._load_index(database_module._USER_CORRECTIONS_PATH, [])
    assert len(corrections) == 2  # both entries present, neither overwritten
    assert corrections[0]["file_id"] == "f1"
    assert corrections[1]["file_id"] == "f2"


def test_log_user_correction_supports_none_corrected_value_for_rejection(tmp_path, monkeypatch):
    """A rejection proposes no specific corrected value — None must round-trip
    as JSON null, not be coerced into a placeholder string."""
    _isolate_learning(tmp_path, monkeypatch)

    database_module.log_user_correction(
        file_id="f1", field_name="category",
        suggested_value="Invoice", corrected_value=None, category="Invoice",
    )

    corrections = database_module._load_index(database_module._USER_CORRECTIONS_PATH, [])
    assert corrections[0]["corrected_value"] is None
