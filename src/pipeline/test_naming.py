"""
Unit tests for pipeline/naming.py — Module 05 (Naming & Destination). Structured per
the design's committed Test Strategy (§22): per-category template-filling
correctness (§10/§11), sanitization boundary cases (§12), within-batch collision
resolution (§13), destination override precedence (§14), Category.UNKNOWN end-to-end
(§3), the Module Contract immutability test (§5), an adversarial sanitization test
(§19), action-log shape (§18), and deterministic batch-processing order (§29 item 12).

Run with: pytest src/pipeline/test_naming.py -v
"""

import json
from dataclasses import asdict
from pathlib import Path

import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.classification import Category, ClassificationSignals
from src.models.duplicate import DuplicateSignals
from src.models.file_record import FileRecord
from src.models.naming import NamingSignals
from src.pipeline.naming import (
    NamingEngine,
    build_filename,
    resolve_destination,
    resolve_within_batch_collision,
    sanitize_filename,
    suggest_naming_and_destination_batch,
)


def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


def _record(file_id, name, category=None, discovered_at="2026-01-01T00:00:00Z",
            extracted_metadata=None, modified_at=None, extension=None,
            duplicate_of=None, version_rank=None, **kwargs):
    return FileRecord(
        file_id=file_id, source_id="downloads", original_name=name,
        original_path=f"/tmp/{name}", current_path=f"/tmp/{name}",
        extension=extension or Path(name).suffix, status="discovered", category=category,
        discovered_at=discovered_at, extracted_metadata=extracted_metadata or {},
        modified_at=modified_at, duplicate_of=duplicate_of, version_rank=version_rank,
        batch_id="batch-1", **kwargs,
    )


# --- Per-category template filling (§10/§11) ---

def test_invoice_all_fields_present():
    record = _record("i1", "invoice.pdf", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_number": "INV123", "invoice_date": "2026-07-05",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Amazon_Inv123_2026-07-05.pdf"
    assert fields_fell_back == []


def test_invoice_missing_required_fields_get_unknown_fallback():
    record = _record("i2", "invoice.pdf", category=Category.INVOICE, extracted_metadata={})
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Vendor" in name
    assert "Unknown_Date" in name
    assert set(fields_fell_back) == {"vendor", "invoice_date"}


def test_invoice_number_omitted_not_flagged_as_fallback_when_absent():
    """§29 item 4: invoice_number is an optional enrichment field, OMITTED (not
    placeholder-filled) when absent — never recorded in naming_signals."""
    record = _record("i3", "invoice.pdf", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Amazon_2026-07-05.pdf"
    assert "invoice_number" not in fields_fell_back
    assert fields_fell_back == []


def test_resume_version_indicator_takes_priority_over_last_modified_date():
    record = _record("r1", "resume.pdf", category=Category.RESUME, extracted_metadata={
        "candidate_name": "JordanPatel", "version_indicator": "v9",
        "last_modified_date": "2026-01-01",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Resume_Jordanpatel_V9.pdf"
    assert fields_fell_back == []


def test_resume_falls_back_to_last_modified_date_when_version_indicator_absent():
    record = _record("r2", "resume.pdf", category=Category.RESUME, extracted_metadata={
        "candidate_name": "JordanPatel", "last_modified_date": "2026-01-01",
    })
    name, fields_fell_back = build_filename(record)
    assert "2026-01-01" in name
    # Using last_modified_date successfully is a real value, not a placeholder —
    # never recorded as a fallback (§11/§29 item 9).
    assert fields_fell_back == []


def test_resume_composite_falls_back_to_literal_unknown_when_both_absent():
    """When both version_indicator and last_modified_date are absent, both real
    taxonomy field names are recorded individually — never the synthetic label
    "version_or_date" (Module 05 Implementation Audit M1) — applying §5's "one
    entry per affected field" rule the same way every other multi-required-field
    category already does."""
    record = _record("r3", "resume.pdf", category=Category.RESUME, extracted_metadata={
        "candidate_name": "JordanPatel",
    })
    name, fields_fell_back = build_filename(record)
    assert "Unknown" in name
    assert set(fields_fell_back) == {"version_indicator", "last_modified_date"}


def test_bank_statement_clean_match():
    record = _record("b1", "statement.pdf", category=Category.BANK_STATEMENT, extracted_metadata={
        "bank_name": "Chase", "statement_period": "2026-06",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Chase_Statement_2026-06.pdf"
    assert fields_fell_back == []


def test_bank_statement_missing_required_fields_get_unknown_fallback():
    """Module 05 Implementation Audit M3: §22 commits to the fallback path for
    every required/optional field, per category — previously untested here."""
    record = _record("b2", "statement.pdf", category=Category.BANK_STATEMENT, extracted_metadata={})
    name, fields_fell_back = build_filename(record)
    # "BankName" is a multi-word placeholder label, so it goes through the same
    # per-segment capitalize() flattening as every other multi-word segment
    # (§12's "NDA" -> "Nda" cosmetic cost) -> "Bankname", not "BankName".
    assert "Unknown_Bankname" in name
    assert "Unknown_Period" in name
    assert set(fields_fell_back) == {"bank_name", "statement_period"}


def test_contract_uses_counterparty_not_party_name():
    record = _record("c1", "nda.pdf", category=Category.CONTRACT, extracted_metadata={
        "contract_type": "NDA", "counterparty": "AcmeCorp", "effective_date": "2026-07-01",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Nda_Acmecorp_2026-07-01.pdf"
    assert fields_fell_back == []


def test_contract_missing_required_fields_get_unknown_fallback():
    """Module 05 Implementation Audit M3."""
    record = _record("c2", "contract.pdf", category=Category.CONTRACT, extracted_metadata={})
    name, fields_fell_back = build_filename(record)
    # Multi-word placeholder labels get flattened by per-segment capitalize()
    # (§12's "NDA" -> "Nda" cosmetic cost); "Counterparty" is already single-word.
    assert "Unknown_Contracttype" in name
    assert "Unknown_Counterparty" in name
    assert "Unknown_Effectivedate" in name
    assert set(fields_fell_back) == {"contract_type", "counterparty", "effective_date"}


def test_document_missing_optional_date_gets_unknown_placeholder():
    record = _record("d1", "manual.pdf", category=Category.DOCUMENT, extracted_metadata={
        "best_guess_title": "UserManual",
    })
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Date" in name
    assert fields_fell_back == ["document_date"]


def test_document_missing_required_title_gets_unknown_fallback():
    """Module 05 Implementation Audit M3: the required field's own fallback path
    was never exercised previously (only the optional `document_date` was)."""
    record = _record("d2", "manual.pdf", category=Category.DOCUMENT, extracted_metadata={
        "document_date": "2026-07-05",
    })
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Title" in name
    assert fields_fell_back == ["best_guess_title"]


def test_image_clean_match():
    record = _record("img1", "photo.jpg", category=Category.IMAGE, extracted_metadata={
        "description": "CoffeeTable", "variant": "Black",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Coffeetable_Black.jpg"
    assert fields_fell_back == []


def test_image_missing_description_gets_unknown_fallback():
    """Module 05 Implementation Audit M3."""
    record = _record("img2", "photo.jpg", category=Category.IMAGE, extracted_metadata={
        "variant": "Black",
    })
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Description" in name
    assert fields_fell_back == ["description"]


def test_image_missing_variant_gets_unknown_fallback():
    """Module 05 Implementation Audit M3."""
    record = _record("img3", "photo.jpg", category=Category.IMAGE, extracted_metadata={
        "description": "CoffeeTable",
    })
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Variant" in name
    assert fields_fell_back == ["variant"]


def test_screenshot_clean_match():
    record = _record("s1", "shot.png", category=Category.SCREENSHOT, extracted_metadata={
        "context_description": "LoginError", "capture_date": "2026-07-05",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Screenshot_Loginerror_2026-07-05.png"
    assert fields_fell_back == []


def test_screenshot_missing_context_description_gets_unknown_fallback():
    """Module 05 Implementation Audit M3."""
    record = _record("s2", "shot.png", category=Category.SCREENSHOT, extracted_metadata={
        "capture_date": "2026-07-05",
    })
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Context" in name
    assert fields_fell_back == ["context_description"]


def test_screenshot_missing_capture_date_gets_unknown_fallback():
    """Module 05 Implementation Audit M3."""
    record = _record("s3", "shot.png", category=Category.SCREENSHOT, extracted_metadata={
        "context_description": "LoginError",
    })
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Date" in name
    assert fields_fell_back == ["capture_date"]


def test_application_clean_match():
    record = _record("a1", "zoom.pkg", category=Category.APPLICATION, extracted_metadata={
        "app_name": "Zoom", "version": "6.1", "platform": "Mac",
    })
    name, fields_fell_back = build_filename(record)
    # "." is not whitelisted and is stripped deterministically -> always "61", never
    # "6.1" (Module 05 Implementation Audit L1: previously a hedged OR-assertion).
    assert name == "Zoom_61_Mac.pkg"
    assert fields_fell_back == []


def test_application_missing_required_app_name_gets_unknown_fallback():
    """Module 05 Implementation Audit M3."""
    record = _record("a2", "zoom.pkg", category=Category.APPLICATION, extracted_metadata={
        "version": "6", "platform": "Mac",
    })
    name, fields_fell_back = build_filename(record)
    # "AppName" is a multi-word placeholder label, flattened by capitalize() ->
    # "Appname" (§12's "NDA" -> "Nda" cosmetic cost).
    assert "Unknown_Appname" in name
    assert fields_fell_back == ["app_name"]


def test_application_missing_optional_fields_get_unknown_fallback():
    """Module 05 Implementation Audit M3."""
    record = _record("a3", "zoom.pkg", category=Category.APPLICATION, extracted_metadata={
        "app_name": "Zoom",
    })
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Version" in name
    assert "Unknown_Platform" in name
    assert set(fields_fell_back) == {"version", "platform"}


def test_archive_falls_back_to_modified_at_when_no_date_field_exists():
    """§29 item 5: Archive has no date field of any kind — always falls to
    modified_at (tier-4), formatted to YYYY-MM-DD."""
    record = _record("arc1", "project.zip", category=Category.ARCHIVE,
                      modified_at="2026-07-05T14:31:40Z",
                      extracted_metadata={"contents_summary": "ProjectPhotos"})
    name, fields_fell_back = build_filename(record)
    assert name == "Projectphotos_2026-07-05.zip"
    assert fields_fell_back == []  # modified_at is a real value, not a placeholder


def test_archive_falls_back_to_unknown_date_when_modified_at_also_missing():
    """The real field that had no value (`modified_at`, a Module 01 field) is
    recorded — never the synthetic label "date" (Module 05 Implementation Audit
    M1)."""
    record = _record("arc2", "project.zip", category=Category.ARCHIVE, modified_at=None,
                      extracted_metadata={"contents_summary": "ProjectPhotos"})
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Date" in name
    assert fields_fell_back == ["modified_at"]


def test_archive_empty_contents_summary_is_a_real_value_not_a_fallback():
    """A genuinely empty (but successfully opened) archive yields "" (Module 03
    Design.md) — a found, honest value distinct from None, so it must NOT trigger
    the Unknown_ContentsSummary fallback."""
    record = _record("arc3", "empty.zip", category=Category.ARCHIVE,
                      modified_at="2026-07-05T00:00:00Z",
                      extracted_metadata={"contents_summary": ""})
    name, fields_fell_back = build_filename(record)
    assert "Unknown_ContentsSummary" not in name
    assert "contents_summary" not in fields_fell_back


def test_video_falls_back_to_modified_at():
    """§29 item 7: content_date is always null in v1 -> falls to modified_at, same
    rule as Archive."""
    record = _record("v1", "demo.mp4", category=Category.VIDEO,
                      modified_at="2026-07-05T00:00:00Z",
                      extracted_metadata={"description": "ProductDemo", "content_date": None})
    name, fields_fell_back = build_filename(record)
    assert name == "Productdemo_2026-07-05.mp4"
    assert fields_fell_back == []


def test_video_falls_back_to_unknown_date_when_modified_at_also_missing():
    """The real field that had no value (`modified_at`) is recorded — never the
    synthetic label "date", and never `content_date` (whose own absence is never
    itself recorded, since falling to `modified_at` would have been an honest
    value) — Module 05 Implementation Audit M1."""
    record = _record("v2", "demo.mp4", category=Category.VIDEO, modified_at=None,
                      extracted_metadata={"description": "ProductDemo", "content_date": None})
    name, fields_fell_back = build_filename(record)
    assert "Unknown_Date" in name
    assert fields_fell_back == ["modified_at"]


def test_audio_prefers_artist_over_recording_date():
    record = _record("aud1", "track.mp3", category=Category.AUDIO, extracted_metadata={
        "track_title": "Interview", "artist": "Draft", "recording_date": "2026-07-05",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Interview_Draft.mp3"
    assert fields_fell_back == []


def test_audio_falls_back_to_recording_date_when_artist_absent():
    record = _record("aud2", "track.mp3", category=Category.AUDIO, extracted_metadata={
        "track_title": "Interview", "recording_date": "2026-07-05",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Interview_2026-07-05.mp3"
    assert fields_fell_back == []


def test_audio_omits_second_slot_when_both_artist_and_recording_date_absent():
    """§29 item 8: falls back to {TrackTitle} alone — omitted, not placeholder-filled."""
    record = _record("aud3", "track.mp3", category=Category.AUDIO, extracted_metadata={
        "track_title": "Interview",
    })
    name, fields_fell_back = build_filename(record)
    assert name == "Interview.mp3"
    assert fields_fell_back == []


def test_unknown_category_uses_original_name_stem_only():
    """§3/§10: Category.UNKNOWN's naming depends only on original_name, never
    extracted_metadata (always {} for these records)."""
    record = _record("u1", "file2384.dat", category=Category.UNKNOWN)
    name, fields_fell_back = build_filename(record)
    assert name == "Unsorted_File2384.dat"
    assert fields_fell_back == []


# --- Sanitization (§12) ---

def test_sanitize_filename_strips_non_whitelisted_characters():
    assert sanitize_filename("Weird'Name\"WithQuotes") == "Weirdnamewithquotes"


def test_sanitize_filename_preserves_hyphens_for_dates():
    assert sanitize_filename("2026-07-05") == "2026-07-05"


def test_sanitize_filename_acronym_renders_capitalize_style_cosmetic_cost():
    """§12's own worked example: "NDA" -> "Nda" — an explicitly accepted cosmetic
    cost of the no-exceptions-list rule."""
    assert sanitize_filename("NDA_Acme") == "Nda_Acme"


def test_sanitize_filename_converts_single_space_to_underscore():
    """Post-freeze correction #1 (Module 05 UAT Finding UAT-1): internal whitespace
    is converted to "_", not silently stripped like every other disallowed
    character — a real, multi-word field value keeps its word boundaries."""
    assert sanitize_filename("Northwind Traders") == "Northwind_Traders"


def test_sanitize_filename_collapses_multiple_consecutive_spaces_to_one_underscore():
    assert sanitize_filename("Espresso    Machine") == "Espresso_Machine"


def test_sanitize_filename_converts_tabs_to_underscore():
    assert sanitize_filename("Tab\tSeparated\tValue") == "Tab_Separated_Value"


def test_sanitize_filename_converts_mixed_whitespace_to_single_underscore():
    """Tabs, newlines, and spaces mixed together in one run still collapse to a
    single "_" separator, matching how a single space alone behaves."""
    assert sanitize_filename("Mixed \t\n Whitespace  Here") == "Mixed_Whitespace_Here"


def test_sanitize_filename_strips_leading_and_trailing_whitespace_no_stray_underscore():
    """Leading/trailing whitespace converts to a leading/trailing "_", which the
    existing segment-split-and-filter step already drops — no stray leading or
    trailing "_" in the result."""
    result = sanitize_filename("  Leading And Trailing  ")
    assert result == "Leading_And_Trailing"
    assert not result.startswith("_")
    assert not result.endswith("_")


def test_sanitize_filename_whitespace_adjacent_to_existing_underscore_does_not_double():
    """A pre-existing "_" immediately followed by whitespace (which itself
    converts to "_") must not produce a doubled "__" in the result — the existing
    segment-split-and-filter logic collapses it to one separator."""
    result = sanitize_filename("Foo_ Bar")
    assert result == "Foo_Bar"
    assert "__" not in result


def test_sanitize_filename_converts_unicode_whitespace_to_underscore():
    """Python's `\\s` regex class matches Unicode whitespace (e.g. U+00A0 non-
    breaking space) for `str` input, not just ASCII space/tab/newline — confirming
    this is actually exercised, not just assumed."""
    non_breaking_space = " "
    result = sanitize_filename(f"Unicode{non_breaking_space}Space")
    assert result == "Unicode_Space"


def test_sanitize_filename_truncates_longest_segment_over_80_chars():
    long_segment = "X" * 100
    result = sanitize_filename(f"Short_{long_segment}_Tail")
    assert len(result) <= 80
    assert result.startswith("Short_")
    assert result.endswith("_Tail")


def test_sanitize_filename_enforces_cap_when_overflow_exceeds_single_longest_segment():
    """Module 05 Implementation Audit M2: several comparably-large segments whose
    combined overflow exceeds any single segment's own length must still be
    brought under the ~80-character cap via iterative truncation, not a single
    pass (previously left the result at 84 characters, still over budget)."""
    segments = "_".join(["X" * 20] * 5)  # 104 chars total, no segment >= 24
    result = sanitize_filename(segments)
    assert len(result) <= 80


def test_sanitize_filename_never_leaves_stray_or_doubled_underscore_after_truncation():
    """A segment truncated to zero length must be dropped entirely, not joined as
    an empty string (which previously produced a leading/doubled "_") — Module 05
    Implementation Audit M2."""
    segments = "_".join(["X" * 20] * 5)
    result = sanitize_filename(segments)
    assert "__" not in result
    assert not result.startswith("_")
    assert not result.endswith("_")


def test_sanitize_filename_truncation_reduces_to_empty_when_content_wholly_exceeds_cap():
    """If truncation removes every segment entirely (an extreme, unrealistic case),
    the result is an empty string, not a crash — build_filename() is the layer
    responsible for the "never blank" guarantee (falls back to "Unknown")."""
    segments = "_".join(["X" * 20] * 20)  # wildly over budget
    result = sanitize_filename(segments)
    assert isinstance(result, str)


def test_sanitize_filename_never_produces_path_traversal_sequences():
    """§19 adversarial test: a maliciously crafted value must never survive into a
    sanitized filename."""
    malicious = "../../etc/passwd"
    result = sanitize_filename(malicious)
    assert "/" not in result
    assert ".." not in result


def test_build_filename_adversarial_extracted_metadata_never_produces_traversal():
    record = _record("adv1", "doc.pdf", category=Category.DOCUMENT, extracted_metadata={
        "best_guess_title": "../../etc/passwd", "document_date": "2026-07-05",
    })
    name, _ = build_filename(record)
    assert "/" not in name
    assert ".." not in name


# --- Destination resolution and override precedence (§14) ---

def test_resolve_destination_category_mapping():
    record = _record("dest1", "invoice.pdf", category=Category.INVOICE)
    assert resolve_destination(record) == "Finance/"


def test_resolve_destination_unknown_always_unknown_folder():
    record = _record("dest2", "file.dat", category=Category.UNKNOWN)
    assert resolve_destination(record) == "Unknown/"


def test_resolve_destination_exact_duplicate_override_beats_category():
    record = _record("dest3", "invoice.pdf", category=Category.INVOICE, duplicate_of="other-1")
    assert resolve_destination(record) == "~ARCHIVE~/Duplicates/"


def test_resolve_destination_superseded_version_override_beats_category():
    record = _record("dest4", "resume.pdf", category=Category.RESUME, version_rank="superseded")
    assert resolve_destination(record) == "~ARCHIVE~/Old Versions/"


def test_resolve_destination_naming_still_computed_normally_under_override():
    """§29 item 10: an override never short-circuits naming — a real, category-
    based suggested_name is still produced even when routed to an archive."""
    record = _record("dest5", "invoice.pdf", category=Category.INVOICE, duplicate_of="other-1",
                      extracted_metadata={"vendor": "Amazon", "invoice_date": "2026-07-05"})
    name, _ = build_filename(record)
    assert name == "Amazon_2026-07-05.pdf"


# --- Within-batch collision resolution (§13) ---

def test_within_batch_collision_appends_suffix():
    seen = {}
    first = resolve_within_batch_collision("Amazon_2026-07-05.pdf", "Finance/", seen)
    second = resolve_within_batch_collision("Amazon_2026-07-05.pdf", "Finance/", seen)
    assert first == "Amazon_2026-07-05.pdf"
    assert second == "Amazon_2026-07-05_2.pdf"


def test_within_batch_collision_three_or_more_records():
    seen = {}
    names = [
        resolve_within_batch_collision("Amazon_2026-07-05.pdf", "Finance/", seen)
        for _ in range(3)
    ]
    assert names == [
        "Amazon_2026-07-05.pdf",
        "Amazon_2026-07-05_2.pdf",
        "Amazon_2026-07-05_3.pdf",
    ]


def test_within_batch_collision_different_destinations_do_not_collide():
    seen = {}
    a = resolve_within_batch_collision("Report.pdf", "Documents/", seen)
    b = resolve_within_batch_collision("Report.pdf", "Finance/", seen)
    assert a == "Report.pdf"
    assert b == "Report.pdf"  # different destination -> no collision


# --- NamingEngine ---

def test_engine_produces_naming_signals_with_fields_fell_back():
    record = _record("eng1", "invoice.pdf", category=Category.INVOICE, extracted_metadata={})
    engine = NamingEngine()
    result = engine.suggest_file(record, {})
    assert isinstance(result.naming_signals, NamingSignals)
    assert set(result.naming_signals.fields_fell_back) == {"vendor", "invoice_date"}


def test_engine_naming_signals_empty_when_no_fallback():
    record = _record("eng2", "invoice.pdf", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    engine = NamingEngine()
    result = engine.suggest_file(record, {})
    assert result.naming_signals.fields_fell_back == []


def test_engine_reports_override_applied():
    record = _record("eng3", "invoice.pdf", category=Category.INVOICE, duplicate_of="other-1")
    engine = NamingEngine()
    result = engine.suggest_file(record, {})
    assert result.override_applied == "exact_duplicate"


def test_engine_reports_no_override_when_none_applies():
    record = _record("eng4", "invoice.pdf", category=Category.INVOICE)
    engine = NamingEngine()
    result = engine.suggest_file(record, {})
    assert result.override_applied is None


def test_override_detection_shared_between_destination_and_engine():
    """Module 05 Implementation Audit L2: resolve_destination() and
    NamingEngine.suggest_file() now share one override-detection source of truth
    (_determine_override()), so the destination actually returned and the
    override_applied value actually logged cannot independently drift apart."""
    cases = [
        ({"duplicate_of": "other-1"}, "exact_duplicate", "~ARCHIVE~/Duplicates/"),
        ({"version_rank": "superseded"}, "superseded_version", "~ARCHIVE~/Old Versions/"),
        ({}, None, "Finance/"),
    ]
    for kwargs, expected_override, expected_destination in cases:
        record = _record("ov1", "invoice.pdf", category=Category.INVOICE, **kwargs)
        result = NamingEngine().suggest_file(record, {})
        assert result.override_applied == expected_override
        assert resolve_destination(record) == expected_destination


# --- suggest_naming_and_destination_batch() orchestration ---

def test_batch_populates_suggested_name_and_destination(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("batch1", "invoice.pdf", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    result = suggest_naming_and_destination_batch([record])
    assert result[0].suggested_name == "Amazon_2026-07-05.pdf"
    assert result[0].suggested_destination == "Finance/"
    assert isinstance(result[0].naming_signals, NamingSignals)


def test_batch_skips_non_discovered_status(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    unreadable = FileRecord(
        file_id="unreadable-1", source_id="downloads", original_name="broken.pdf",
        original_path="/tmp/broken.pdf", current_path="/tmp/broken.pdf",
        status="unreadable",
    )
    result = suggest_naming_and_destination_batch([unreadable])
    assert result[0].suggested_name is None
    assert result[0].naming_signals is None


def test_batch_skips_records_with_no_category(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("nocat-1", "file.pdf", category=None)
    result = suggest_naming_and_destination_batch([record])
    assert result[0].suggested_name is None


def test_batch_processes_category_unknown(tmp_path, monkeypatch):
    """§3: unlike Module 03, Module 05 must NOT skip Category.UNKNOWN."""
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("unk-1", "mystery.dat", category=Category.UNKNOWN)
    result = suggest_naming_and_destination_batch([record])
    assert result[0].suggested_name == "Unsorted_Mystery.dat"
    assert result[0].suggested_destination == "Unknown/"


def test_batch_writes_a_suggest_naming_and_destination_action_log_entry(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("log-1", "invoice.pdf", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    suggest_naming_and_destination_batch([record])

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines]
    matching = [e for e in entries if e["action"] == "suggest_naming_and_destination" and e["file_id"] == "log-1"]
    assert len(matching) == 1
    details = matching[0]["details"]
    assert details["suggested_name"] == "Amazon_2026-07-05.pdf"
    assert details["suggested_destination"] == "Finance/"
    assert details["fields_fell_back"] == []
    assert details["collision_suffix_applied"] is False
    assert details["override_applied"] is None


def test_batch_within_batch_collision_across_two_records(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    same_metadata = {"vendor": "Amazon", "invoice_date": "2026-07-05"}
    first = _record("coll-1", "invoice1.pdf", category=Category.INVOICE,
                     extracted_metadata=dict(same_metadata), discovered_at="2026-01-01T00:00:00Z")
    second = _record("coll-2", "invoice2.pdf", category=Category.INVOICE,
                      extracted_metadata=dict(same_metadata), discovered_at="2026-01-01T00:00:01Z")
    result = suggest_naming_and_destination_batch([first, second])
    names = sorted(r.suggested_name for r in result)
    assert names == ["Amazon_2026-07-05.pdf", "Amazon_2026-07-05_2.pdf"]


def test_batch_deterministic_order_reruns_assign_same_collision_suffixes(tmp_path, monkeypatch):
    """§29 item 12: re-running the same batch (or supplying it in a different
    input-list order) must assign the same collision suffixes every time."""
    _isolate_storage(tmp_path, monkeypatch)
    same_metadata = {"vendor": "Amazon", "invoice_date": "2026-07-05"}
    early = _record("det-early", "invoice1.pdf", category=Category.INVOICE,
                     extracted_metadata=dict(same_metadata), discovered_at="2026-01-01T00:00:00Z")
    late = _record("det-late", "invoice2.pdf", category=Category.INVOICE,
                    extracted_metadata=dict(same_metadata), discovered_at="2026-02-01T00:00:00Z")

    # Supply in reverse order — outcome must be identical either way.
    result = suggest_naming_and_destination_batch([late, early])
    early_result = next(r for r in result if r.file_id == "det-early")
    late_result = next(r for r in result if r.file_id == "det-late")
    assert early_result.suggested_name == "Amazon_2026-07-05.pdf"       # processed first
    assert late_result.suggested_name == "Amazon_2026-07-05_2.pdf"      # processed second


def test_batch_tie_break_by_file_id_for_identical_discovered_at(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    same_time = "2026-01-01T00:00:00Z"
    same_metadata = {"vendor": "Amazon", "invoice_date": "2026-07-05"}
    record_b = _record("b-record", "invoice2.pdf", category=Category.INVOICE,
                        extracted_metadata=dict(same_metadata), discovered_at=same_time)
    record_a = _record("a-record", "invoice1.pdf", category=Category.INVOICE,
                        extracted_metadata=dict(same_metadata), discovered_at=same_time)

    result = suggest_naming_and_destination_batch([record_b, record_a])
    a_result = next(r for r in result if r.file_id == "a-record")
    b_result = next(r for r in result if r.file_id == "b-record")
    # "a-record" sorts before "b-record" lexicographically -> processed first.
    assert a_result.suggested_name == "Amazon_2026-07-05.pdf"
    assert b_result.suggested_name == "Amazon_2026-07-05_2.pdf"


def test_batch_persists_records_to_metadata_store(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("persist-1", "invoice.pdf", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    suggest_naming_and_destination_batch([record])

    reloaded = next(r for r in database_module.load_metadata_store() if r.file_id == "persist-1")
    assert reloaded.suggested_name == "Amazon_2026-07-05.pdf"
    assert isinstance(reloaded.naming_signals, NamingSignals)


# --- Module Contract immutability (§5) ---
# Mirrors Module 04's own exhaustive asdict()-loop pattern — every FileRecord field
# is compared automatically, not a hand-picked subset.

def test_module_contract_immutability_every_non_owned_field_byte_identical(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)

    record = FileRecord(
        file_id="contract-test-id",
        source_id="contract-source",
        original_name="invoice.pdf",
        original_path="arbitrary/original/path.pdf",
        current_path="/tmp/invoice.pdf",
        extension=".pdf",
        mime_type="application/pdf",
        size_bytes=12345,
        created_at="2020-01-01T00:00:00Z",
        modified_at="2020-01-02T00:00:00Z",
        content_hash="hash-shared",
        discovered_at="2020-01-03T00:00:00Z",
        status="discovered",
        error=None,
        category=Category.INVOICE,
        classification_signals=ClassificationSignals(ambiguous=True),
        extracted_metadata={"vendor": "Acme", "invoice_date": "2020-01-01"},
        duplicate_of=None,
        version_group_id=None,
        version_rank=None,
        duplicate_signals=DuplicateSignals(exact_duplicate=False),
        confidence_score=77,
        confidence_breakdown={"some_deduction": -5},
        tier="approval_required",
        batch_id="batch-contract-test",
        processed_at="2020-01-04T00:00:00Z",
        approved_by="user",
        approved_at="2020-01-05T00:00:00Z",
        reversible=False,
    )

    before = asdict(record)
    suggest_naming_and_destination_batch([record])
    after = asdict(record)

    owned_fields = {"suggested_name", "suggested_destination", "naming_signals"}
    for field_name in before:
        if field_name in owned_fields:
            continue
        assert after[field_name] == before[field_name], (
            f"Module 05 modified {field_name!r}, which it does not own per "
            f"Module 05 Design.md §5's DOES NOT MODIFY list"
        )

    # Confirm Module 05 actually did its job — otherwise this test would trivially
    # pass by suggest_naming_and_destination_batch() doing nothing.
    assert after["suggested_name"] == "Acme_2020-01-01.pdf"
    assert after["suggested_destination"] == "Finance/"
