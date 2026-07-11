"""
Unit tests for pipeline/confidence.py — Module 06 (Confidence & Review). Structured
per the frozen design's committed Test Strategy (§21): every deterministic deduction
rule (§12, 9 rules), every hard floor including the Unknown category/Corrupted file
merge (§13, 4 rows -> exactly one identifier for the shared trigger), deduction-cap
enforcement in both categories including the exact boundary (§12's "Cap
representation" note, M3), hard_floors_applied logging isolation and stacking (§16,
M1), the Module Contract immutability test (§5), the eligibility filter (§11),
deterministic batch order (§11), action-log shape (§16), defensive None-signals
handling, and a taxonomy cross-check regression test against pipeline/metadata.py's
real REQUIRED_FIELDS/OPTIONAL_FIELDS constants (§10 — Module 06 defines its own
independent table but must match Module 03's real values).

Run with: pytest src/pipeline/test_confidence.py -v
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
from src.pipeline.confidence import (
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    ConfidenceEngine,
    apply_hard_floors,
    compute_deductions,
    compute_score,
    lookup_tier,
    score_confidence_batch,
    _apply_capped_field_deductions,
)


def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


def _record(file_id, name="file.pdf", category=Category.INVOICE,
            discovered_at="2026-01-01T00:00:00Z", extracted_metadata=None,
            classification_signals=None, duplicate_signals=None, naming_signals=None,
            suggested_name="Amazon_2026-07-05.pdf", status="discovered", **kwargs):
    return FileRecord(
        file_id=file_id, source_id="downloads", original_name=name,
        original_path=f"/tmp/{name}", current_path=f"/tmp/{name}",
        extension=Path(name).suffix, status=status, category=category,
        discovered_at=discovered_at, extracted_metadata=extracted_metadata or {},
        classification_signals=classification_signals, duplicate_signals=duplicate_signals,
        naming_signals=naming_signals, suggested_name=suggested_name,
        batch_id="batch-1", **kwargs,
    )


# --- Taxonomy cross-check regression test (§10) ---
# Module 06's REQUIRED_FIELDS/OPTIONAL_FIELDS are an independent table, not an import
# from pipeline/metadata.py — this test's only purpose is to catch drift between the
# two, never to be read by production code.

def test_taxonomy_matches_metadata_module_real_constants():
    from src.pipeline import metadata as metadata_module
    assert REQUIRED_FIELDS == metadata_module.REQUIRED_FIELDS
    assert OPTIONAL_FIELDS == metadata_module.OPTIONAL_FIELDS


def test_taxonomy_has_no_entry_for_unknown_category():
    assert Category.UNKNOWN not in REQUIRED_FIELDS
    assert Category.UNKNOWN not in OPTIONAL_FIELDS


# --- compute_deductions(): each of the 9 deduction rules (§12) ---

def test_no_deductions_when_nothing_wrong():
    record = _record("d0", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
        "invoice_number": "INV1", "amount": "100", "currency": "USD", "tax_type": "none",
    }, classification_signals=ClassificationSignals(), duplicate_signals=DuplicateSignals(),
        naming_signals=NamingSignals())
    assert compute_deductions(record) == {}


def test_ambiguous_classification_deduction():
    record = _record("d1", classification_signals=ClassificationSignals(ambiguous=True))
    deductions = compute_deductions(record)
    assert deductions["ambiguous_classification"] == -15


def test_no_extractable_text_deduction():
    record = _record("d2", classification_signals=ClassificationSignals(no_extractable_text=True))
    deductions = compute_deductions(record)
    assert deductions["no_extractable_text"] == -30


def test_missing_required_field_deduction_per_field():
    record = _record("d3", category=Category.INVOICE, extracted_metadata={})
    deductions = compute_deductions(record)
    assert deductions["missing_required_field:vendor"] == -8
    assert deductions["missing_required_field:invoice_date"] == -8


def test_missing_optional_field_deduction_per_field():
    record = _record("d4", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    deductions = compute_deductions(record)
    assert deductions["missing_optional_field:invoice_number"] == -2
    assert deductions["missing_optional_field:amount"] == -2
    assert deductions["missing_optional_field:currency"] == -2
    assert deductions["missing_optional_field:tax_type"] == -2


def test_naming_fallback_deduction_per_field():
    record = _record("d5", naming_signals=NamingSignals(fields_fell_back=["vendor", "invoice_date"]))
    deductions = compute_deductions(record)
    assert deductions["naming_fallback:vendor"] == -10
    assert deductions["naming_fallback:invoice_date"] == -10


def test_fuzzy_duplicate_deduction():
    record = _record("d6", duplicate_signals=DuplicateSignals(fuzzy_duplicate=True))
    deductions = compute_deductions(record)
    assert deductions["fuzzy_duplicate"] == -20


def test_version_conflict_deduction():
    record = _record("d7", duplicate_signals=DuplicateSignals(version_conflict=True))
    deductions = compute_deductions(record)
    assert deductions["version_conflict"] == -25


def test_non_english_content_deduction():
    record = _record("d8", classification_signals=ClassificationSignals(non_english_detected=True))
    deductions = compute_deductions(record)
    assert deductions["non_english_content"] == -10


def test_locked_file_deduction():
    record = _record("d9", classification_signals=ClassificationSignals(locked=True))
    deductions = compute_deductions(record)
    assert deductions["locked_file"] == -40


def test_deductions_stack_across_independent_rules():
    record = _record(
        "d10", category=Category.INVOICE, extracted_metadata={},
        classification_signals=ClassificationSignals(ambiguous=True),
        duplicate_signals=DuplicateSignals(fuzzy_duplicate=True),
        naming_signals=NamingSignals(fields_fell_back=["vendor"]),
    )
    deductions = compute_deductions(record)
    assert deductions["ambiguous_classification"] == -15
    assert deductions["fuzzy_duplicate"] == -20
    assert deductions["naming_fallback:vendor"] == -10
    assert deductions["missing_required_field:vendor"] == -8
    assert deductions["missing_required_field:invoice_date"] == -8


def test_all_nine_deduction_rules_simultaneously_with_cap_enforcement(monkeypatch):
    """§21's design-committed test: "a record with every deduction simultaneously
    (to confirm summation, not just single-deduction correctness)" — Implementation
    Audit finding M1 (fresh pass). Covers all 9 rows of §12's table on one record in
    one call, with the required/optional taxonomy temporarily widened (same
    monkeypatch technique as test_required_and_optional_caps_are_independent) so
    both caps are actually tripped in the same record that also carries every other
    deduction — not just the field-count deductions in isolation. Verifies the
    complete confidence_breakdown, cap enforcement, the final score, and the
    resulting tier all agree with hand-computed values."""
    import src.pipeline.confidence as confidence_module
    monkeypatch.setitem(confidence_module.REQUIRED_FIELDS, Category.DOCUMENT,
                         ("r1", "r2", "r3", "r4"))
    monkeypatch.setitem(confidence_module.OPTIONAL_FIELDS, Category.DOCUMENT,
                         ("o1", "o2", "o3", "o4", "o5", "o6"))

    record = _record(
        "all9", category=Category.DOCUMENT, extracted_metadata={},
        classification_signals=ClassificationSignals(
            ambiguous=True, no_extractable_text=True,
            non_english_detected=True, locked=True,
        ),
        duplicate_signals=DuplicateSignals(fuzzy_duplicate=True, version_conflict=True),
        naming_signals=NamingSignals(fields_fell_back=["nf1", "nf2"]),
    )

    deductions = compute_deductions(record)

    expected_breakdown = {
        "ambiguous_classification": -15,
        "no_extractable_text": -30,
        "missing_required_field:r1": -8,
        "missing_required_field:r2": -8,
        "missing_required_field:r3": -8,
        "missing_required_field:r4": 0,   # beyond the -30 required cap — recorded, not omitted
        "missing_optional_field:o1": -2,
        "missing_optional_field:o2": -2,
        "missing_optional_field:o3": -2,
        "missing_optional_field:o4": -2,
        "missing_optional_field:o5": -2,
        "missing_optional_field:o6": 0,   # exactly at the -10 optional cap boundary
        "naming_fallback:nf1": -10,
        "naming_fallback:nf2": -10,
        "fuzzy_duplicate": -20,
        "version_conflict": -25,
        "non_english_content": -10,
        "locked_file": -40,
    }
    assert deductions == expected_breakdown

    # Cap behavior, asserted explicitly (not just via the dict equality above):
    required_total = sum(v for k, v in deductions.items() if k.startswith("missing_required_field:"))
    optional_total = sum(v for k, v in deductions.items() if k.startswith("missing_optional_field:"))
    assert required_total == -24   # 3 fields at -8 fit under the -30 cap; the 4th is capped to 0
    assert optional_total == -10   # 5 fields at -2 land exactly on the -10 cap; the 6th is capped to 0

    # Final score: 100 + sum(all 18 breakdown values, including the two 0-valued
    # capped entries) = 100 + (-194) = -94, clipped to the [0, 100] floor.
    score = compute_score(deductions)
    assert sum(expected_breakdown.values()) == -194
    assert score == 0

    # Resulting tier from the arithmetic alone (lookup_tier, before any hard floor).
    assert lookup_tier(score) == "review_required"


def test_defensive_none_signals_treated_as_no_signals():
    """A record with every *_signals field still None (upstream module never ran)
    must not raise — treated the same as a freshly-constructed "nothing unusual"
    signals instance."""
    record = _record("d11", classification_signals=None, duplicate_signals=None,
                      naming_signals=None, extracted_metadata={
                          "vendor": "Amazon", "invoice_date": "2026-07-05",
                          "invoice_number": "INV1", "amount": "100",
                          "currency": "USD", "tax_type": "none",
                      })
    assert compute_deductions(record) == {}


# --- Cap enforcement (§12's "Cap representation" note, M3) ---

def test_capped_field_deductions_under_cap_gets_full_value():
    deductions = {}
    record = _record("cap1", extracted_metadata={})
    _apply_capped_field_deductions(deductions, record, ("a", "b", "c"), "test", 8, 30)
    assert deductions == {"test:a": -8, "test:b": -8, "test:c": -8}


def test_capped_field_deductions_at_exact_cap_boundary():
    """4 fields x -8 = -32 > cap 30 -> the 4th field lands exactly at the boundary
    check: running subtotal after 3 fields is 24; 24 + 8 = 32 > 30, so the 4th
    field gets 0, never -8 (cap is a hard ceiling, never partially applied)."""
    deductions = {}
    record = _record("cap2", extracted_metadata={})
    _apply_capped_field_deductions(deductions, record, ("a", "b", "c", "d"), "test", 8, 30)
    assert deductions["test:a"] == -8
    assert deductions["test:b"] == -8
    assert deductions["test:c"] == -8
    assert deductions["test:d"] == 0
    assert sum(deductions.values()) == -24


def test_capped_field_deductions_beyond_cap_records_zero_never_omitted():
    """Every field beyond the cap must still appear in the breakdown at value 0 —
    never silently dropped, keeping confidence_breakdown fully truthful/auditable."""
    deductions = {}
    record = _record("cap3", extracted_metadata={})
    _apply_capped_field_deductions(deductions, record, ("a", "b", "c", "d", "e"), "test", 8, 30)
    assert set(deductions.keys()) == {"test:a", "test:b", "test:c", "test:d", "test:e"}
    assert deductions["test:e"] == 0


def test_capped_field_deductions_optional_cap_boundary():
    """5 fields x -2 = -10 exactly at cap (10 <= 10, still full value); a 6th
    field would push to 12 > 10 and get 0."""
    deductions = {}
    record = _record("cap4", extracted_metadata={})
    _apply_capped_field_deductions(deductions, record, ("a", "b", "c", "d", "e", "f"), "test", 2, 10)
    for name in ("a", "b", "c", "d", "e"):
        assert deductions[f"test:{name}"] == -2
    assert deductions["test:f"] == 0
    assert sum(deductions.values()) == -10


def test_capped_field_deductions_present_field_never_deducted():
    deductions = {}
    record = _record("cap5", extracted_metadata={"a": "present"})
    _apply_capped_field_deductions(deductions, record, ("a", "b"), "test", 8, 30)
    assert "test:a" not in deductions
    assert deductions["test:b"] == -8


def test_capped_field_deductions_empty_string_counts_as_present():
    """An extracted field whose value is "" (a found, honest empty value) is not
    None, so it must not be treated as missing (matches Module 05's own
    contents_summary precedent)."""
    deductions = {}
    record = _record("cap6", extracted_metadata={"a": ""})
    _apply_capped_field_deductions(deductions, record, ("a",), "test", 8, 30)
    assert "test:a" not in deductions


def test_required_and_optional_caps_are_independent(monkeypatch):
    """A category with enough missing required AND optional fields to trip both
    caps must have each cap enforced independently — the required cap tripping
    must not affect the optional cap's own running subtotal, and vice versa.
    Required: 4 fields x -8; the 4th would push 24 -> 32 > cap 30, so it lands
    at 0 and the true total stops at -24 (the cap is a ceiling never exceeded,
    not a target always exactly hit — §12). Optional: 6 fields x -2; 5 fields
    divide evenly into the -10 cap, so the 6th lands at 0 and the total is
    exactly -10."""
    import src.pipeline.confidence as confidence_module
    monkeypatch.setitem(confidence_module.REQUIRED_FIELDS, Category.DOCUMENT,
                         ("r1", "r2", "r3", "r4"))
    monkeypatch.setitem(confidence_module.OPTIONAL_FIELDS, Category.DOCUMENT,
                         ("o1", "o2", "o3", "o4", "o5", "o6"))
    record = _record("cap7", category=Category.DOCUMENT, extracted_metadata={})
    deductions = compute_deductions(record)
    required_total = sum(v for k, v in deductions.items() if k.startswith("missing_required_field:"))
    optional_total = sum(v for k, v in deductions.items() if k.startswith("missing_optional_field:"))
    assert required_total == -24
    assert optional_total == -10
    assert deductions["missing_required_field:r4"] == 0
    assert deductions["missing_optional_field:o6"] == 0


# --- compute_score() (post-freeze corrected sign convention) ---

def test_compute_score_matches_rules_worked_example():
    """Rules/Confidence Rules.md's own worked example: 100 + (-8) + (-10) = 82."""
    deductions = {"missing_required_field:invoice_number": -8, "naming_fallback:vendor": -10}
    assert compute_score(deductions) == 82


def test_compute_score_no_deductions_is_100():
    assert compute_score({}) == 100


def test_compute_score_clips_at_zero_floor():
    deductions = {"a": -60, "b": -60}
    assert compute_score(deductions) == 0


def test_compute_score_never_exceeds_100():
    # Defensive: even if a caller somehow passed a positive value, the clip still
    # holds — compute_score() performs no capping logic of its own, but the
    # min(100, ...) clip is unconditional.
    assert compute_score({"a": 5}) == 100


# --- lookup_tier() (§13) ---

def test_lookup_tier_auto_band():
    assert lookup_tier(100) == "auto"
    assert lookup_tier(95) == "auto"


def test_lookup_tier_approval_required_band():
    assert lookup_tier(94) == "approval_required"
    assert lookup_tier(80) == "approval_required"


def test_lookup_tier_review_required_band():
    assert lookup_tier(79) == "review_required"
    assert lookup_tier(0) == "review_required"


# --- apply_hard_floors() (§13, M1 tuple-return, M2 merge) ---

def test_hard_floor_unknown_category_forces_review_required_single_identifier():
    """M2: Category.UNKNOWN and "Corrupted file" share one identical trigger —
    exactly one identifier (unknown_category) is ever logged, never a second
    "corrupted_file" entry for the same fact."""
    record = _record("h1", category=Category.UNKNOWN)
    tier, hard_floors_applied = apply_hard_floors(record, "auto")
    assert tier == "review_required"
    assert hard_floors_applied == ["unknown_category"]


def test_hard_floor_fuzzy_duplicate_forces_approval_required():
    record = _record("h2", duplicate_signals=DuplicateSignals(fuzzy_duplicate=True))
    tier, hard_floors_applied = apply_hard_floors(record, "auto")
    assert tier == "approval_required"
    assert hard_floors_applied == ["fuzzy_duplicate"]


def test_hard_floor_fuzzy_duplicate_does_not_raise_an_already_stricter_tier():
    """Hard floors only clamp down, never up (§13) — a tier already at
    review_required stays review_required even though fuzzy_duplicate's own
    minimum is only approval_required."""
    record = _record("h3", duplicate_signals=DuplicateSignals(fuzzy_duplicate=True))
    tier, hard_floors_applied = apply_hard_floors(record, "review_required")
    assert tier == "review_required"
    assert hard_floors_applied == ["fuzzy_duplicate"]


def test_hard_floor_multi_document_forces_review_required():
    record = _record("h4", classification_signals=ClassificationSignals(multi_document_detected=True))
    tier, hard_floors_applied = apply_hard_floors(record, "auto")
    assert tier == "review_required"
    assert hard_floors_applied == ["multi_document_detected"]


def test_hard_floor_locked_file_forces_review_required():
    record = _record("h5", classification_signals=ClassificationSignals(locked=True))
    tier, hard_floors_applied = apply_hard_floors(record, "auto")
    assert tier == "review_required"
    assert hard_floors_applied == ["locked_file"]


def test_hard_floor_none_trigger_returns_unchanged_tier_and_empty_list():
    record = _record("h6")
    tier, hard_floors_applied = apply_hard_floors(record, "auto")
    assert tier == "auto"
    assert hard_floors_applied == []


def test_hard_floors_stack_in_fixed_table_order():
    """Multiple simultaneous floors are all recorded, in the table's fixed row
    order, regardless of which order the underlying conditions happen to be
    true — never independently recomputed, never reordered."""
    record = _record(
        "h7", category=Category.UNKNOWN,
        classification_signals=ClassificationSignals(locked=True, multi_document_detected=True),
        duplicate_signals=DuplicateSignals(fuzzy_duplicate=True),
    )
    tier, hard_floors_applied = apply_hard_floors(record, "auto")
    assert tier == "review_required"
    assert hard_floors_applied == [
        "unknown_category", "fuzzy_duplicate", "multi_document_detected", "locked_file",
    ]


def test_hard_floors_defensive_none_signals_never_trigger():
    record = _record("h8", classification_signals=None, duplicate_signals=None)
    tier, hard_floors_applied = apply_hard_floors(record, "auto")
    assert tier == "auto"
    assert hard_floors_applied == []


# --- ConfidenceEngine (end-to-end per-file) ---

def test_engine_produces_consistent_score_breakdown_and_tier():
    record = _record("eng1", category=Category.INVOICE, extracted_metadata={})
    result = ConfidenceEngine().score_file(record)
    assert result.confidence_score == compute_score(result.confidence_breakdown)
    assert result.tier in ("auto", "approval_required", "review_required")


def test_engine_hard_floor_data_flow_is_the_same_walk_as_the_tier_clamp():
    """M1: hard_floors_applied is exactly the second element of
    apply_hard_floors()'s own return — the Engine must never independently
    recompute which floors applied."""
    record = _record("eng2", category=Category.UNKNOWN)
    result = ConfidenceEngine().score_file(record)
    expected_tier, expected_floors = apply_hard_floors(record, lookup_tier(
        compute_score(compute_deductions(record))
    ))
    assert result.tier == expected_tier
    assert result.hard_floors_applied == expected_floors


def test_engine_processing_time_ms_is_non_negative_int():
    record = _record("eng3")
    result = ConfidenceEngine().score_file(record)
    assert isinstance(result.processing_time_ms, int)
    assert result.processing_time_ms >= 0


# --- score_confidence_batch() orchestration ---

def test_batch_populates_confidence_fields(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("batch1", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    result = score_confidence_batch([record])
    assert result[0].confidence_score is not None
    assert result[0].tier is not None
    assert isinstance(result[0].confidence_breakdown, dict)


def test_batch_skips_non_discovered_status(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    unreadable = FileRecord(
        file_id="unreadable-1", source_id="downloads", original_name="broken.pdf",
        original_path="/tmp/broken.pdf", current_path="/tmp/broken.pdf",
        status="unreadable",
    )
    result = score_confidence_batch([unreadable])
    assert result[0].confidence_score is None


def test_batch_skips_records_with_no_category(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("nocat-1", category=None)
    result = score_confidence_batch([record])
    assert result[0].confidence_score is None


def test_batch_skips_records_with_no_suggested_name(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("noname-1", suggested_name=None)
    result = score_confidence_batch([record])
    assert result[0].confidence_score is None


def test_batch_processes_category_unknown(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("unk-1", category=Category.UNKNOWN)
    result = score_confidence_batch([record])
    assert result[0].confidence_score is not None
    assert result[0].tier == "review_required"


def test_batch_writes_a_score_confidence_action_log_entry(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("log-1", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
        "invoice_number": "INV1", "amount": "100", "currency": "USD", "tax_type": "none",
    })
    score_confidence_batch([record])

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines]
    matching = [e for e in entries if e["action"] == "score_confidence" and e["file_id"] == "log-1"]
    assert len(matching) == 1
    details = matching[0]["details"]
    assert details["confidence_score"] == 100
    assert details["confidence_breakdown"] == {}
    assert details["tier"] == "auto"
    assert details["hard_floors_applied"] == []
    assert "processing_time_ms" in details


def test_batch_action_log_records_hard_floors_applied(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("log-2", category=Category.UNKNOWN)
    score_confidence_batch([record])

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines]
    matching = [e for e in entries if e["action"] == "score_confidence" and e["file_id"] == "log-2"]
    assert matching[0]["details"]["hard_floors_applied"] == ["unknown_category"]


def test_batch_deterministic_order_by_discovered_at_then_file_id(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    early = _record("det-early", discovered_at="2026-01-01T00:00:00Z")
    late = _record("det-late", discovered_at="2026-02-01T00:00:00Z")
    same_time_a = _record("a-record", discovered_at="2026-03-01T00:00:00Z")
    same_time_b = _record("b-record", discovered_at="2026-03-01T00:00:00Z")

    score_confidence_batch([same_time_b, late, same_time_a, early])

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines if json.loads(line)["action"] == "score_confidence"]
    order = [e["file_id"] for e in entries]
    assert order == ["det-early", "det-late", "a-record", "b-record"]


def test_batch_deterministic_order_reversed_input_produces_byte_identical_field_values(tmp_path, monkeypatch):
    """§21's design-committed test: "same batch, reversed input order, byte-identical
    confidence_score/confidence_breakdown/tier for every record (confirming §7's
    claim that order doesn't affect output value, not just that it doesn't crash)"
    — Implementation Audit finding M2 (fresh pass). Unlike
    test_batch_deterministic_order_by_discovered_at_then_file_id above (which only
    checks the order of the resulting action-log lines), this test runs the same
    logical batch twice — once forward, once reversed — in two independently
    isolated storage locations, and compares the actual per-record output values
    (confidence_score, confidence_breakdown, tier, and hard_floors_applied read back
    from the action log) for byte-identical equality per file_id. Mirrors Module 05's
    own test_batch_deterministic_order_reruns_assign_same_collision_suffixes
    precedent, which Module 06 Design.md §21 explicitly modeled itself on."""
    def build_records():
        clean = _record(
            "ord-clean", category=Category.INVOICE, discovered_at="2026-01-01T00:00:00Z",
            extracted_metadata={
                "vendor": "Amazon", "invoice_date": "2026-07-05",
                "invoice_number": "INV1", "amount": "100", "currency": "USD", "tax_type": "none",
            },
        )
        unknown = _record("ord-unknown", category=Category.UNKNOWN, discovered_at="2026-02-01T00:00:00Z")
        fuzzy = _record(
            "ord-fuzzy", category=Category.INVOICE, discovered_at="2026-03-01T00:00:00Z",
            extracted_metadata={
                "vendor": "Amazon", "invoice_date": "2026-07-05",
                "invoice_number": "INV1", "amount": "100", "currency": "USD", "tax_type": "none",
            },
            duplicate_signals=DuplicateSignals(fuzzy_duplicate=True),
        )
        return [clean, unknown, fuzzy]

    def run_and_collect(records, storage_dir):
        storage_dir.mkdir()
        monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", storage_dir / "metadata_store.json")
        monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", storage_dir / "action_log.jsonl")
        score_confidence_batch(records)

        records_by_id = {r.file_id: r for r in records}
        log_lines = (storage_dir / "action_log.jsonl").read_text().strip().splitlines()
        hard_floors_by_id = {}
        for line in log_lines:
            entry = json.loads(line)
            if entry["action"] == "score_confidence":
                hard_floors_by_id[entry["file_id"]] = entry["details"]["hard_floors_applied"]
        return records_by_id, hard_floors_by_id

    forward_records, forward_hard_floors = run_and_collect(build_records(), tmp_path / "forward")
    reversed_records, reversed_hard_floors = run_and_collect(
        list(reversed(build_records())), tmp_path / "reversed"
    )

    for file_id in ("ord-clean", "ord-unknown", "ord-fuzzy"):
        assert forward_records[file_id].confidence_score == reversed_records[file_id].confidence_score
        assert forward_records[file_id].confidence_breakdown == reversed_records[file_id].confidence_breakdown
        assert forward_records[file_id].tier == reversed_records[file_id].tier
        assert forward_hard_floors[file_id] == reversed_hard_floors[file_id]

    # Confirm this isn't trivially passing because nothing interesting happened.
    assert forward_records["ord-clean"].tier == "auto"
    assert forward_records["ord-unknown"].tier == "review_required"
    assert forward_hard_floors["ord-unknown"] == ["unknown_category"]
    assert forward_hard_floors["ord-fuzzy"] == ["fuzzy_duplicate"]


def test_batch_persists_records_to_metadata_store(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("persist-1", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    score_confidence_batch([record])

    reloaded = next(r for r in database_module.load_metadata_store() if r.file_id == "persist-1")
    assert reloaded.confidence_score is not None
    assert reloaded.tier is not None


def test_batch_bad_record_does_not_abort_whole_batch(tmp_path, monkeypatch):
    """A single record whose scoring raises unexpectedly must not prevent the
    rest of the batch from being scored — logs an `error` entry and continues
    (§18's resilience pattern, matching every earlier module's precedent)."""
    _isolate_storage(tmp_path, monkeypatch)

    good = _record("good-1", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    bad = _record("bad-1", category=Category.INVOICE, extracted_metadata={
        "vendor": "Amazon", "invoice_date": "2026-07-05",
    })
    bad.extracted_metadata = None  # forces an AttributeError inside compute_deductions

    result = score_confidence_batch([bad, good])

    good_result = next(r for r in result if r.file_id == "good-1")
    bad_result = next(r for r in result if r.file_id == "bad-1")
    assert good_result.confidence_score is not None
    assert bad_result.confidence_score is None

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines]
    error_entries = [e for e in entries if e["action"] == "error" and e["file_id"] == "bad-1"]
    assert len(error_entries) == 1


# --- Module Contract immutability (§5) ---
# Mirrors Module 05's own exhaustive asdict()-loop pattern — every FileRecord field
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
        classification_signals=ClassificationSignals(ambiguous=False),
        extracted_metadata={
            "vendor": "Acme", "invoice_date": "2020-01-01",
            "invoice_number": "INV1", "amount": "100", "currency": "USD", "tax_type": "none",
        },
        duplicate_of=None,
        version_group_id=None,
        version_rank=None,
        duplicate_signals=DuplicateSignals(exact_duplicate=False),
        suggested_name="Acme_2020-01-01.pdf",
        suggested_destination="Finance/",
        naming_signals=NamingSignals(fields_fell_back=[]),
        batch_id="batch-contract-test",
        processed_at="2020-01-04T00:00:00Z",
        approved_by="user",
        approved_at="2020-01-05T00:00:00Z",
        reversible=False,
    )

    before = asdict(record)
    score_confidence_batch([record])
    after = asdict(record)

    owned_fields = {"confidence_score", "confidence_breakdown", "tier"}
    for field_name in before:
        if field_name in owned_fields:
            continue
        assert after[field_name] == before[field_name], (
            f"Module 06 modified {field_name!r}, which it does not own per "
            f"Module 06 Design.md §5's DOES NOT MODIFY list"
        )

    # Confirm Module 06 actually did its job — otherwise this test would trivially
    # pass by score_confidence_batch() doing nothing.
    assert after["confidence_score"] == 100
    assert after["tier"] == "auto"
