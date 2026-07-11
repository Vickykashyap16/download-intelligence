"""
Unit tests for pipeline/watch_ingest.py (Module 01).

Run with: pytest src/pipeline/test_watch_ingest.py -v

These monkeypatch the storage-layer path constants so tests never touch the real
Database/Metadata or Runtime/Logs of the actual project — see the note in
src/README.md about hardcoded project-relative paths being a known testability
limitation of the current storage/*.py modules.
"""

import dataclasses

import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.classification import Category, ClassificationSignals
from src.models.duplicate import DuplicateSignals
from src.models.naming import NamingSignals
from src.pipeline.watch_ingest import (
    build_file_record,
    classify_ignored_name,
    generate_new_file_id,
    get_extension,
    is_ignored_name,
    is_supported_extension,
    is_zero_byte,
    scan_source,
)


def _isolate_storage(tmp_path, monkeypatch):
    """Point Database/Metadata and Runtime/Logs at a scratch location for this test,
    and make the stability check instant so tests don't sleep."""
    monkeypatch.setattr(
        database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json"
    )
    monkeypatch.setattr(
        runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl"
    )
    monkeypatch.setattr("src.pipeline.watch_ingest.STABILITY_CHECK_INTERVAL_SECONDS", 0)


def test_is_ignored_name_matches_known_junk():
    assert is_ignored_name(".DS_Store") is True
    assert is_ignored_name("Thumbs.db") is True
    assert is_ignored_name("invoice.pdf.crdownload") is True
    assert is_ignored_name("invoice.pdf") is False


def test_classify_ignored_name_returns_specific_reason():
    """Regression test for the UAT-driven change to specific skip reasons: callers
    that need to know *which* kind of ignore rule matched (not just yes/no) get one
    of the specific reason strings, never the old generic "ignored_name"."""
    assert classify_ignored_name(".DS_Store") == "system_file"
    assert classify_ignored_name("Thumbs.db") == "system_file"
    assert classify_ignored_name("desktop.ini") == "system_file"
    assert classify_ignored_name("invoice.pdf.crdownload") == "temporary_download"
    assert classify_ignored_name("movie.mp4.part") == "temporary_download"
    assert classify_ignored_name("invoice.pdf") is None


def test_is_supported_extension():
    assert is_supported_extension(".pdf") is True
    assert is_supported_extension(".docx") is True
    assert is_supported_extension(".exe") is False  # deliberately excluded — see assumptions


def test_get_extension_is_lowercased(tmp_path):
    path = tmp_path / "Invoice.PDF"
    path.write_text("dummy")
    assert get_extension(path) == ".pdf"


def test_is_zero_byte(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    non_empty = tmp_path / "content.txt"
    non_empty.write_text("hello")

    assert is_zero_byte(empty) is True
    assert is_zero_byte(non_empty) is False


def test_generate_new_file_id_is_random_each_call():
    first = generate_new_file_id()
    second = generate_new_file_id()
    assert first != second  # no path/content dependence — every call is a fresh identity


def test_build_file_record_reads_supported_file(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    path = tmp_path / "resume.txt"
    path.write_text("Jordan Patel — Resume")

    record, content_changed = build_file_record(path, source_id="downloads", batch_id="test-batch")

    assert content_changed is False
    assert record.status == "discovered"
    assert record.original_name == "resume.txt"
    assert record.current_path == str(path.resolve())
    assert record.original_path == record.current_path  # first time seen: original == current
    assert record.extension == ".txt"
    assert record.content_hash is not None
    assert record.size_bytes == path.stat().st_size
    assert record.batch_id == "test-batch"
    # Fields owned by later modules must stay untouched:
    assert record.category is None
    assert record.suggested_name is None
    assert record.confidence_score is None


def test_build_file_record_two_different_files_get_different_ids(tmp_path, monkeypatch):
    """Same content, different paths -> different file_id (content alone must not
    determine identity — that would silently merge two distinct physical files)."""
    _isolate_storage(tmp_path, monkeypatch)
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("same content")
    file_b.write_text("same content")

    record_a, _ = build_file_record(file_a, source_id="downloads", batch_id="batch-1")
    database_module.save_file_record(record_a)
    record_b, _ = build_file_record(file_b, source_id="downloads", batch_id="batch-1")

    assert record_a.file_id != record_b.file_id
    assert record_a.content_hash == record_b.content_hash  # same bytes, confirmed


def test_build_file_record_reuses_id_for_unmoved_file(tmp_path, monkeypatch):
    """Scanning the same still-unmoved file twice must return the SAME file_id and
    the SAME discovered_at — this is what makes repeated manual scans idempotent."""
    _isolate_storage(tmp_path, monkeypatch)
    path = tmp_path / "invoice.pdf"
    path.write_text("invoice content")

    first_record, first_changed = build_file_record(path, source_id="downloads", batch_id="batch-1")
    database_module.save_file_record(first_record)

    second_record, second_changed = build_file_record(path, source_id="downloads", batch_id="batch-2")

    assert first_changed is False
    assert second_changed is False
    assert second_record.file_id == first_record.file_id
    assert second_record.discovered_at == first_record.discovered_at
    assert second_record.batch_id == "batch-2"  # batch_id itself does refresh


def test_build_file_record_flags_content_change_at_same_path(tmp_path, monkeypatch):
    """If the file at a known path now hashes differently, that's surfaced via the
    content_changed flag rather than silently overwritten."""
    _isolate_storage(tmp_path, monkeypatch)
    path = tmp_path / "notes.txt"
    path.write_text("version one")

    first_record, _ = build_file_record(path, source_id="downloads", batch_id="batch-1")
    database_module.save_file_record(first_record)

    path.write_text("version two — completely different content")
    second_record, content_changed = build_file_record(path, source_id="downloads", batch_id="batch-2")

    assert content_changed is True
    assert second_record.file_id == first_record.file_id  # still the same tracked file
    assert second_record.content_hash != first_record.content_hash


def _populate_downstream_fields(record) -> None:
    """Test helper (post-freeze correction #1 regression coverage): stamp every
    downstream-owned field (Modules 02-07's, per Release/Module01/MODULE_CONTRACT.md's
    DOES NOT MODIFY list) with a real, non-default value, simulating a record that has
    already been through the full Module 01->06 pipeline (and, hypothetically,
    Module 07). Kept as one shared helper so the two regression tests below and any
    future one all stamp the exact same 17 fields, deliberately mirroring
    _reset_downstream_owned_fields()'s own field list in watch_ingest.py so a drift
    between the two would show up as a real test failure, not a silent gap."""
    record.category = Category.INVOICE
    record.classification_signals = ClassificationSignals(ambiguous=True)
    record.extracted_metadata = {"vendor": "Acme Corp"}
    record.suggested_name = "Acme_Corp_2026-01-01.pdf"
    record.suggested_destination = "Finance/"
    record.naming_signals = NamingSignals(fields_fell_back=["invoice_number"])
    record.duplicate_of = "some-other-file-id"
    record.version_group_id = "some-version-group-id"
    record.version_rank = "latest"
    record.duplicate_signals = DuplicateSignals(fuzzy_duplicate=True, phash_distance=3)
    record.confidence_score = 82
    record.confidence_breakdown = {"missing_required_field:invoice_number": -8, "naming_fallback:vendor": -10}
    record.tier = "approval_required"
    record.processed_at = "2026-01-02T00:00:00+00:00"
    record.approved_by = "user"
    record.approved_at = "2026-01-02T00:00:01+00:00"
    record.reversible = False


def test_build_file_record_preserves_downstream_fields_on_unchanged_rescan(tmp_path, monkeypatch):
    """Post-freeze correction #1 (2026-07-11), Finding UAT-1 (Module 06 UAT): a
    re-scan of an unmoved, content-unchanged file must not disturb any
    downstream-owned field, even though build_file_record() constructs an entirely
    new object on first discovery. Every downstream field is asserted byte-for-byte
    identical (via dataclasses.asdict(), mirroring Module 02-06's own established
    Module Contract immutability test pattern) before and after the re-scan — not
    merely spot-checked."""
    _isolate_storage(tmp_path, monkeypatch)
    path = tmp_path / "invoice.pdf"
    path.write_text("invoice content — unchanged across both scans")

    first_record, _ = build_file_record(path, source_id="downloads", batch_id="batch-1")
    _populate_downstream_fields(first_record)
    database_module.save_file_record(first_record)
    before = dataclasses.asdict(first_record)

    second_record, content_changed = build_file_record(path, source_id="downloads", batch_id="batch-2")
    after = dataclasses.asdict(second_record)

    assert content_changed is False
    downstream_fields = [
        "category", "classification_signals", "extracted_metadata",
        "suggested_name", "suggested_destination", "naming_signals",
        "duplicate_of", "version_group_id", "version_rank", "duplicate_signals",
        "confidence_score", "confidence_breakdown", "tier",
        "processed_at", "approved_by", "approved_at", "reversible",
    ]
    for field_name in downstream_fields:
        assert after[field_name] == before[field_name], f"{field_name} changed on an unchanged re-scan"
    # Module 01's own fields still correctly refresh (batch_id in particular).
    assert second_record.batch_id == "batch-2"
    assert second_record.file_id == first_record.file_id


def test_build_file_record_clears_downstream_fields_on_content_change(tmp_path, monkeypatch):
    """Post-freeze correction #1 (2026-07-11), Finding UAT-1 (Module 06 UAT): a
    re-scan where content_hash has genuinely changed must reset every
    downstream-owned field to its FileRecord default — the same shape as a
    first-discovery record — so it re-enters Modules 02-06's existing null-based
    reprocessing path. Module 01's own fields (content_hash in particular) must
    still correctly reflect the NEW content, and identity fields must be preserved."""
    _isolate_storage(tmp_path, monkeypatch)
    path = tmp_path / "invoice.pdf"
    path.write_text("invoice content — version one")

    first_record, _ = build_file_record(path, source_id="downloads", batch_id="batch-1")
    _populate_downstream_fields(first_record)
    database_module.save_file_record(first_record)
    old_content_hash = first_record.content_hash

    path.write_text("invoice content — version two, completely different")
    second_record, content_changed = build_file_record(path, source_id="downloads", batch_id="batch-2")

    assert content_changed is True
    # Identity preserved (still the same tracked file, per Module 01's own contract).
    assert second_record.file_id == first_record.file_id
    assert second_record.original_name == first_record.original_name
    assert second_record.original_path == first_record.original_path
    assert second_record.discovered_at == first_record.discovered_at
    # Module 01's own fields correctly reflect the new content.
    assert second_record.content_hash != old_content_hash
    assert second_record.batch_id == "batch-2"
    # Every downstream-owned field reset to its default.
    assert second_record.category is None
    assert second_record.classification_signals is None
    assert second_record.extracted_metadata == {}
    assert second_record.suggested_name is None
    assert second_record.suggested_destination is None
    assert second_record.naming_signals is None
    assert second_record.duplicate_of is None
    assert second_record.version_group_id is None
    assert second_record.version_rank is None
    assert second_record.duplicate_signals is None
    assert second_record.confidence_score is None
    assert second_record.confidence_breakdown == {}
    assert second_record.tier is None
    assert second_record.processed_at is None
    assert second_record.approved_by is None
    assert second_record.approved_at is None
    assert second_record.reversible is True


def test_scan_source_skips_ignored_and_unsupported(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)

    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    (source_dir / "invoice.pdf").write_text("real invoice content")
    (source_dir / ".DS_Store").write_text("junk")
    (source_dir / "partial.crdownload").write_text("still downloading")
    (source_dir / "unsupported.xyz").write_text("unknown type")
    (source_dir / "empty.pdf").write_text("")
    (source_dir / "subfolder").mkdir()

    result = scan_source(str(source_dir), source_id="downloads")

    assert len(result.records) == 1
    assert result.records[0].original_name == "invoice.pdf"

    skipped_reasons = {entry.reason for entry in result.skipped}
    assert "system_file" in skipped_reasons        # .DS_Store
    assert "temporary_download" in skipped_reasons  # partial.crdownload
    assert "unsupported_extension" in skipped_reasons
    assert "zero_byte" in skipped_reasons
    assert "directory" in skipped_reasons

    # The action log should have one line per entry processed (5 skipped + 1 discovered).
    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    assert len(log_lines) == 6


def test_scan_source_skips_symlinks_without_following_them(tmp_path, monkeypatch):
    """Regression test for a real defect found during Module 01 validation: a symlink
    inside the source folder pointing outside it must never be hashed/ingested."""
    _isolate_storage(tmp_path, monkeypatch)

    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    outside_target = tmp_path / "outside_secret.txt"
    outside_target.write_text("should never be read by the scan")
    (source_dir / "looks_harmless.txt").symlink_to(outside_target)

    result = scan_source(str(source_dir), source_id="downloads")

    assert len(result.records) == 0
    assert any(entry.reason == "symlink" for entry in result.skipped)


def test_scan_source_raises_on_missing_directory(tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    try:
        scan_source(str(missing_dir))
        assert False, "expected NotADirectoryError"
    except NotADirectoryError:
        pass
