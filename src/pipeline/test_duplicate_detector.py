"""
Unit tests for pipeline/duplicate_detector.py — Module 04 (Duplicate & Version
Detection). Structured per the design's committed Test Strategy (§22): filename/
version-token helpers, DuplicateDetectionEngine tests (exact/near/version-chain,
one section each), the H1/M1 sequencing fix, F1-F7 regressions, then
detect_duplicates_batch() orchestration tests, then the Module Contract
immutability test.

Run with: pytest src/pipeline/test_duplicate_detector.py -v
"""

from dataclasses import asdict
from pathlib import Path

import pytest
from PIL import Image

import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.classification import Category, ClassificationSignals
from src.models.duplicate import DuplicateSignals
from src.models.file_record import FileRecord
from src.pipeline.duplicate_detector import (
    DuplicateDetectionEngine,
    detect_duplicates_batch,
    needs_duplicate_detection,
    normalize_filename,
    parse_version_token,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")
    monkeypatch.setattr(database_module, "_HASH_INDEX_PATH", tmp_path / "hash_index.json")
    monkeypatch.setattr(database_module, "_PHASH_INDEX_PATH", tmp_path / "phash_index.json")
    monkeypatch.setattr(database_module, "_NAME_INDEX_PATH", tmp_path / "name_index.json")
    monkeypatch.setattr(database_module, "_VERSION_HISTORY_PATH", tmp_path / "version_history.json")


def _record(file_id, name, category=None, discovered_at="2026-01-01T00:00:00Z",
            content_hash=None, extracted_metadata=None, modified_at=None,
            version_group_id=None, version_rank=None, path=None, **kwargs):
    return FileRecord(
        file_id=file_id, source_id="downloads", original_name=name,
        original_path=path or f"/tmp/{name}", current_path=path or f"/tmp/{name}",
        extension=Path(name).suffix, status="discovered", category=category,
        discovered_at=discovered_at, content_hash=content_hash,
        extracted_metadata=extracted_metadata or {}, modified_at=modified_at,
        version_group_id=version_group_id, version_rank=version_rank,
        batch_id="batch-1", **kwargs,
    )


def _make_image(path, color, size=(64, 64)):
    Image.new("RGB", size, color=color).save(path)


# --- Filename/version-token helpers (§6/§10) ---

def test_normalize_filename_strips_numbered_version_token():
    assert normalize_filename("Resume_v9.pdf") == normalize_filename("Resume_v8.pdf") == "resume"


def test_normalize_filename_strips_final_token():
    assert normalize_filename("Resume_final.pdf") == "resume"


def test_normalize_filename_no_token_present():
    assert normalize_filename("Resume.pdf") == "resume"


def test_parse_version_token_numbered():
    assert parse_version_token("Resume_v9.pdf") == ("numbered", 9)


def test_parse_version_token_final():
    assert parse_version_token("Resume_final.pdf") == ("final", 0)


def test_parse_version_token_none():
    assert parse_version_token("Resume.pdf") is None


def test_parse_version_token_malformed_v_with_no_digits():
    """M3 (§22-committed, missing from the original pass): 'v' with no following
    digits is not a recognizable version token — must not be mistaken for one."""
    assert parse_version_token("Resume_v.pdf") is None


# --- Engine: exact-duplicate (§7 step 1, §8) ---

def test_engine_exact_duplicate_detected_regardless_of_category(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-1", "invoice.pdf", category=Category.UNKNOWN, content_hash="hash-x")
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-1", "invoice_copy.pdf", category=Category.UNKNOWN, content_hash="hash-x")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-1": existing, "new-1": new_record})

    assert result.duplicate_of == "existing-1"
    assert result.duplicate_signals.exact_duplicate is True
    assert result.match_type == "exact"


def test_engine_exact_duplicate_detected_across_different_categories(tmp_path, monkeypatch):
    """M3 (§22/§26-committed, missing from the original pass): §26's named edge
    case is two records with the SAME content_hash but DIFFERENT categories — hash
    equality is authoritative for duplicate_of regardless of category agreement
    (category scoping only matters for near-duplicate/version-chain matching, §9).
    The original test above used the same category for both records, which never
    actually exercised this."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-diffcat", "invoice.pdf", category=Category.INVOICE, content_hash="hash-diffcat")
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-diffcat", "invoice_copy.pdf", category=Category.UNKNOWN, content_hash="hash-diffcat")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-diffcat": existing, "new-diffcat": new_record})

    assert result.duplicate_of == "existing-diffcat"
    assert result.duplicate_signals.exact_duplicate is True


def test_engine_exact_duplicate_short_circuits_version_chain_check(tmp_path, monkeypatch):
    """A byte-identical file cannot simultaneously be "a different version" of
    anything (§7 step 1) — version_group_id must stay None even if the filename
    would otherwise look like a version-chain candidate."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-1", "Resume_v1.pdf", category=Category.RESUME, content_hash="hash-x")
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-1", "Resume_v1.pdf", category=Category.RESUME, content_hash="hash-x")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-1": existing, "new-1": new_record})

    assert result.duplicate_of == "existing-1"
    assert result.version_group_id is None


def test_engine_no_exact_duplicate_when_hash_not_indexed(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    new_record = _record("new-1", "invoice.pdf", category=Category.INVOICE, content_hash="hash-unique")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"new-1": new_record})
    assert result.duplicate_of is None
    assert result.duplicate_signals.exact_duplicate is False


# --- Engine: near-duplicate (§7 step 2, §8, §9, §11) ---

def test_engine_near_duplicate_detected_for_images_within_threshold(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    existing_path = tmp_path / "existing.png"
    new_path = tmp_path / "new.png"
    _make_image(existing_path, (100, 150, 200))
    _make_image(new_path, (100, 150, 200))  # identical -> distance 0, well within threshold

    existing = _record("existing-1", "existing.png", category=Category.IMAGE,
                        content_hash="hash-existing", path=str(existing_path))
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-1", "new.png", category=Category.IMAGE,
                          content_hash="hash-new", path=str(new_path))
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-1": existing, "new-1": new_record})

    assert result.duplicate_signals.fuzzy_duplicate is True
    assert result.duplicate_signals.phash_distance == 0
    assert result.duplicate_of is None  # near-duplicate is a signal, never a fact (§8)


def test_engine_near_duplicate_never_sets_duplicate_of(tmp_path, monkeypatch):
    """Rules/Confidence Rules.md's hard floor requires human review for any fuzzy
    match — Module 04 must never treat it as certain (§8)."""
    _isolate_storage(tmp_path, monkeypatch)
    existing_path = tmp_path / "existing.png"
    new_path = tmp_path / "new.png"
    _make_image(existing_path, (100, 150, 200))
    _make_image(new_path, (100, 150, 200))

    existing = _record("existing-1", "existing.png", category=Category.IMAGE,
                        content_hash="hash-existing", path=str(existing_path))
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-1", "new.png", category=Category.IMAGE,
                          content_hash="hash-new", path=str(new_path))
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-1": existing, "new-1": new_record})
    assert result.duplicate_of is None


def test_engine_near_duplicate_not_checked_for_non_image_categories(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    new_record = _record("new-1", "invoice.pdf", category=Category.INVOICE, content_hash="hash-new")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"new-1": new_record})
    assert result.duplicate_signals.fuzzy_duplicate is False
    assert result.duplicate_signals.phash_distance is None


def test_engine_perceptual_hash_failure_is_caught_not_raised(tmp_path, monkeypatch):
    """§21: perceptual_hash() raising on a corrupted image must not crash
    detect_file() — the near-duplicate check is simply skipped."""
    _isolate_storage(tmp_path, monkeypatch)
    garbage_path = tmp_path / "corrupt.png"
    garbage_path.write_bytes(b"not an image")

    new_record = _record("new-1", "corrupt.png", category=Category.IMAGE,
                          content_hash="hash-new", path=str(garbage_path))
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"new-1": new_record})
    assert result.duplicate_signals.fuzzy_duplicate is False


# --- M3 (§22-committed, missing from the original pass): perceptual-hash boundary
# cases, exercised through the Engine itself (not just lookup_phash_matches()
# directly, which storage/test_database.py already covers) — distance exactly at
# the configured max (5), one above (6), one below (4). Hash values are patched
# directly rather than generated from real images, so the Hamming distance between
# the "existing" and "new" record's perceptual hashes is exact and reproducible,
# not dependent on incidental image content. ---

def _patch_perceptual_hash(monkeypatch, hash_by_path):
    """Make both perceptual_hash() call sites (the Engine's own near-duplicate
    check, and update_indexes()'s index-population call) return a fixed,
    controlled hex hash for a given path, so the Hamming distance between two
    records is exact rather than incidental to real image content."""
    def fake(path):
        key = str(path)
        if key not in hash_by_path:
            raise ValueError(f"no fake perceptual hash configured for {key!r}")
        return hash_by_path[key]

    monkeypatch.setattr(database_module, "perceptual_hash", fake)
    import src.pipeline.duplicate_detector as duplicate_detector_module
    monkeypatch.setattr(duplicate_detector_module, "perceptual_hash", fake)


def test_engine_near_duplicate_boundary_exactly_at_max_distance(tmp_path, monkeypatch):
    """Distance exactly at the configured max (5) must still count as a
    near-duplicate — an inclusive boundary (§11: "maximum Hamming-distance
    threshold")."""
    _isolate_storage(tmp_path, monkeypatch)
    existing_path = str(tmp_path / "existing.png")
    new_path = str(tmp_path / "new.png")
    _patch_perceptual_hash(monkeypatch, {
        existing_path: "0" * 16,
        new_path: format(0b11111, "016x"),  # exactly 5 bits different from all-zero
    })

    existing = _record("existing-boundary", "existing.png", category=Category.IMAGE,
                        content_hash="hash-existing-b", path=existing_path)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-boundary", "new.png", category=Category.IMAGE,
                          content_hash="hash-new-b", path=new_path)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-boundary": existing, "new-boundary": new_record})

    assert result.duplicate_signals.fuzzy_duplicate is True
    assert result.duplicate_signals.phash_distance == 5


def test_engine_near_duplicate_boundary_one_above_max_distance(tmp_path, monkeypatch):
    """One above the threshold (6) must NOT count as a near-duplicate."""
    _isolate_storage(tmp_path, monkeypatch)
    existing_path = str(tmp_path / "existing.png")
    new_path = str(tmp_path / "new.png")
    _patch_perceptual_hash(monkeypatch, {
        existing_path: "0" * 16,
        new_path: format(0b111111, "016x"),  # exactly 6 bits different
    })

    existing = _record("existing-above", "existing.png", category=Category.IMAGE,
                        content_hash="hash-existing-a", path=existing_path)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-above", "new.png", category=Category.IMAGE,
                          content_hash="hash-new-a", path=new_path)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-above": existing, "new-above": new_record})

    assert result.duplicate_signals.fuzzy_duplicate is False


def test_engine_near_duplicate_boundary_one_below_max_distance(tmp_path, monkeypatch):
    """One below the threshold (4) must count as a near-duplicate."""
    _isolate_storage(tmp_path, monkeypatch)
    existing_path = str(tmp_path / "existing.png")
    new_path = str(tmp_path / "new.png")
    _patch_perceptual_hash(monkeypatch, {
        existing_path: "0" * 16,
        new_path: format(0b1111, "016x"),  # exactly 4 bits different
    })

    existing = _record("existing-below", "existing.png", category=Category.IMAGE,
                        content_hash="hash-existing-be", path=existing_path)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-below", "new.png", category=Category.IMAGE,
                          content_hash="hash-new-be", path=new_path)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-below": existing, "new-below": new_record})

    assert result.duplicate_signals.fuzzy_duplicate is True
    assert result.duplicate_signals.phash_distance == 4


def test_engine_near_duplicate_never_crosses_image_screenshot_category(tmp_path, monkeypatch):
    """Post-freeze correction #4 (Module 04 UAT Finding UAT-1, independently verified
    as a design-completeness gap, not an implementation defect): §9/F5 requires Image
    and Screenshot to be strictly separate categories for near-duplicate grouping,
    exactly as much as for version-chain grouping (the version-chain half was already
    covered by test_engine_image_and_screenshot_never_group_with_each_other below --
    this is its near-duplicate counterpart). An Image and a Screenshot sharing the
    exact same perceptual hash (distance 0) must never be flagged as near-duplicates
    of each other."""
    _isolate_storage(tmp_path, monkeypatch)
    existing_path = str(tmp_path / "existing.png")
    new_path = str(tmp_path / "new.png")
    _patch_perceptual_hash(monkeypatch, {
        existing_path: "0" * 16,
        new_path: "0" * 16,  # identical hash, distance 0 -- would match if category-blind
    })

    existing_screenshot = _record("existing-shot", "existing.png", category=Category.SCREENSHOT,
                                   content_hash="hash-existing-shot", path=existing_path)
    database_module.save_file_record(existing_screenshot)
    database_module.update_indexes(existing_screenshot)

    new_image = _record("new-image", "new.png", category=Category.IMAGE,
                         content_hash="hash-new-image", path=new_path)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_image, {"existing-shot": existing_screenshot, "new-image": new_image})

    assert result.duplicate_signals.fuzzy_duplicate is False
    assert result.duplicate_signals.phash_distance is None


# --- Engine: version-chain (§7 step 3, §9, §10) ---

def test_engine_creates_new_version_group_for_first_time_pairing(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    v1 = _record("v1", "Resume_v1.pdf", category=Category.RESUME, content_hash="hash-v1")
    database_module.save_file_record(v1)
    database_module.update_indexes(v1)

    v2 = _record("v2", "Resume_v2.pdf", category=Category.RESUME, content_hash="hash-v2")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(v2, {"v1": v1, "v2": v2})

    assert result.version_group_id is not None
    assert result.version_rank == "latest"
    # post-freeze correction: v1 also joins the new group, and — since v2 is
    # actually the newer file — v1's rank flips to "superseded".
    assert result.other_record_id == "v1"
    assert result.other_record_needs_group_id is True
    assert result.other_record_version_rank == "superseded"


def test_engine_joins_existing_group_and_supersedes_previous_latest(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    group_id = "existing-group-1"
    v1 = _record("v1", "Resume_v1.pdf", category=Category.RESUME,
                  version_group_id=group_id, version_rank="superseded")
    v2 = _record("v2", "Resume_v2.pdf", category=Category.RESUME,
                  version_group_id=group_id, version_rank="latest")
    database_module.save_file_record(v1)
    database_module.save_file_record(v2)
    database_module.update_indexes(v1)
    database_module.update_indexes(v2)

    v3 = _record("v3", "Resume_v3.pdf", category=Category.RESUME)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(v3, {"v1": v1, "v2": v2, "v3": v3})

    assert result.version_group_id == group_id
    assert result.version_rank == "latest"
    assert result.other_record_id == "v2"
    assert result.other_record_version_rank == "superseded"
    assert result.other_record_needs_group_id is False  # already had a group


def test_engine_version_chain_scoped_categories_only(tmp_path, monkeypatch):
    """Video/Audio/Archive/Application/Unknown are excluded from version-chain
    scope (§9, confirmed) — a similarly-named Video file must never form a chain."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-1", "Movie_v1.mp4", category=Category.VIDEO)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-1", "Movie_v2.mp4", category=Category.VIDEO)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-1": existing, "new-1": new_record})
    assert result.version_group_id is None


def test_engine_image_and_screenshot_never_group_with_each_other(tmp_path, monkeypatch):
    """F5, confirmed: category equality is exact for version-chain grouping."""
    _isolate_storage(tmp_path, monkeypatch)
    screenshot = _record("shot-1", "Design_v1.png", category=Category.SCREENSHOT)
    database_module.save_file_record(screenshot)
    database_module.update_indexes(screenshot)

    image = _record("img-1", "Design_v2.png", category=Category.IMAGE)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(image, {"shot-1": screenshot, "img-1": image})
    assert result.version_group_id is None


def test_engine_version_conflict_when_token_and_date_disagree(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    group_id = "group-conflict"
    older = _record(
        "v8", "Resume_v8.pdf", category=Category.RESUME, version_group_id=group_id,
        version_rank="latest", modified_at="2026-06-01T00:00:00Z",
    )
    database_module.save_file_record(older)
    database_module.update_indexes(older)

    # v9's filename token is higher, but its date is EARLIER than v8's — a conflict.
    newer = _record(
        "v9", "Resume_v9.pdf", category=Category.RESUME, modified_at="2026-01-01T00:00:00Z",
    )
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(newer, {"v8": older, "v9": newer})

    assert result.duplicate_signals.version_conflict is True
    assert result.conflict_type == "date_token_disagreement"
    # Tie-break default: filename token wins (§10) — v9 (higher number) still latest.
    assert result.version_rank == "latest"
    assert result.other_record_id == "v8"
    assert result.other_record_version_rank == "superseded"


def test_engine_no_conflict_when_token_and_date_agree(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    group_id = "group-agree"
    older = _record(
        "v8", "Resume_v8.pdf", category=Category.RESUME, version_group_id=group_id,
        version_rank="latest", modified_at="2026-01-01T00:00:00Z",
    )
    database_module.save_file_record(older)
    database_module.update_indexes(older)

    newer = _record(
        "v9", "Resume_v9.pdf", category=Category.RESUME, modified_at="2026-06-01T00:00:00Z",
    )
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(newer, {"v8": older, "v9": newer})

    assert result.duplicate_signals.version_conflict is False
    assert result.conflict_type is None
    assert result.version_rank == "latest"


# --- M3 (§22-committed, missing from the original pass): version-conflict
# detection when one of the two signals (filename token, date) is entirely
# unavailable rather than merely agreeing or disagreeing with the other. ---

def test_engine_version_rank_by_token_only_when_date_unavailable_on_both(tmp_path, monkeypatch):
    """When neither record has a usable date (no category-appropriate
    extracted_metadata field and no modified_at), the decision falls entirely to
    the filename token, with no conflict — there's no second signal to disagree."""
    _isolate_storage(tmp_path, monkeypatch)
    group_id = "group-token-only"
    older = _record(
        "v8-token-only", "Resume_v8.pdf", category=Category.RESUME, version_group_id=group_id,
        version_rank="latest", modified_at=None, extracted_metadata={},
    )
    database_module.save_file_record(older)
    database_module.update_indexes(older)

    newer = _record(
        "v9-token-only", "Resume_v9.pdf", category=Category.RESUME,
        modified_at=None, extracted_metadata={},
    )
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(newer, {"v8-token-only": older, "v9-token-only": newer})

    assert result.duplicate_signals.version_conflict is False
    assert result.conflict_type is None
    assert result.version_rank == "latest"  # v9 > v8 by token alone


def test_engine_version_rank_by_date_only_when_token_missing_on_one_side(tmp_path, monkeypatch):
    """The reverse case: one filename has no parseable version token at all, so
    the decision falls entirely to date comparison, with no conflict."""
    _isolate_storage(tmp_path, monkeypatch)
    group_id = "group-date-only"
    older = _record(
        "untokened-old", "Resume.pdf", category=Category.RESUME, version_group_id=group_id,
        version_rank="latest", modified_at="2026-01-01T00:00:00Z",
    )
    database_module.save_file_record(older)
    database_module.update_indexes(older)

    newer = _record(
        "tokened-new", "Resume_v9.pdf", category=Category.RESUME,
        modified_at="2026-06-01T00:00:00Z",
    )
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(newer, {"untokened-old": older, "tokened-new": newer})

    assert result.duplicate_signals.version_conflict is False
    assert result.conflict_type is None
    assert result.version_rank == "latest"  # newer date wins, token comparison unavailable


# --- H1/M1: cross-group conflict sequencing ---

def test_engine_cross_group_conflict_flags_and_does_not_merge(tmp_path, monkeypatch):
    """F3/H1: a new record whose above-threshold candidates span two different
    existing, non-null version_group_ids must be flagged, never auto-merged, and
    left with version_group_id/version_rank both None.

    PT-003 post-freeze correction: all three records share matching size_bytes
    (5000) so the identical-name candidacy corroboration (§6) is satisfied —
    this test exercises cross-group-conflict sequencing, not PT-003's own fix,
    so the fixtures are adapted to keep reaching that logic under the revised
    candidacy rule (Module 04 Post-Freeze Design Correction — PT-003.md §9)."""
    _isolate_storage(tmp_path, monkeypatch)
    group_a_member = _record(
        "a1", "Statement.pdf", category=Category.BANK_STATEMENT,
        version_group_id="group-a", version_rank="latest", size_bytes=5000,
    )
    group_b_member = _record(
        "b1", "Statement.pdf", category=Category.BANK_STATEMENT,
        version_group_id="group-b", version_rank="latest",
        path="/tmp/other/Statement.pdf", size_bytes=5000,
    )
    database_module.save_file_record(group_a_member)
    database_module.save_file_record(group_b_member)
    database_module.update_indexes(group_a_member)
    database_module.update_indexes(group_b_member)

    new_record = _record("new-1", "Statement.pdf", category=Category.BANK_STATEMENT,
                          path="/tmp/newest/Statement.pdf", size_bytes=5000)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(
        new_record, {"a1": group_a_member, "b1": group_b_member, "new-1": new_record}
    )

    assert result.version_group_id is None
    assert result.version_rank is None
    assert result.duplicate_signals.version_conflict is True
    assert result.conflict_type == "cross_group"
    assert set(result.conflicting_group_ids) == {"group-a", "group-b"}


def test_engine_m1_null_group_never_counts_as_distinct_cross_group(tmp_path, monkeypatch):
    """M1: an ungrouped candidate (version_group_id=None) alongside a grouped one
    must NOT be treated as a cross-group conflict — this is the single most common
    real case (a first-time pairing), and must proceed as ordinary chain creation.

    PT-003 post-freeze correction: all three records share matching size_bytes
    (5000) so the identical-name candidacy corroboration (§6) is satisfied — this
    test exercises M1's group-membership sequencing, not PT-003's own fix, so the
    fixtures are adapted to keep reaching that logic under the revised candidacy
    rule (Module 04 Post-Freeze Design Correction — PT-003.md §9)."""
    _isolate_storage(tmp_path, monkeypatch)
    ungrouped = _record("u1", "Contract.pdf", category=Category.CONTRACT, size_bytes=5000)
    grouped = _record(
        "g1", "Contract.pdf", category=Category.CONTRACT,
        version_group_id="group-existing", version_rank="latest",
        path="/tmp/other/Contract.pdf", size_bytes=5000,
    )
    database_module.save_file_record(ungrouped)
    database_module.save_file_record(grouped)
    database_module.update_indexes(ungrouped)
    database_module.update_indexes(grouped)

    new_record = _record("new-1", "Contract.pdf", category=Category.CONTRACT,
                          path="/tmp/newest/Contract.pdf", size_bytes=5000)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(
        new_record, {"u1": ungrouped, "g1": grouped, "new-1": new_record}
    )

    assert result.conflict_type != "cross_group"
    assert result.version_group_id == "group-existing"


def test_engine_all_null_candidates_proceeds_as_ordinary_creation(tmp_path, monkeypatch):
    """M1: multiple candidates that are ALL ungrouped must not trigger a
    cross-group conflict either — zero non-null groups is not "multiple".

    PT-003 post-freeze correction: all three records share matching size_bytes
    (5000) so the identical-name candidacy corroboration (§6) is satisfied — see
    the same note on the M1 test above (Module 04 Post-Freeze Design Correction —
    PT-003.md §9)."""
    _isolate_storage(tmp_path, monkeypatch)
    candidate_one = _record("c1", "Doc.pdf", category=Category.DOCUMENT, size_bytes=5000)
    candidate_two = _record("c2", "Doc.pdf", category=Category.DOCUMENT, path="/tmp/other/Doc.pdf",
                             size_bytes=5000)
    database_module.save_file_record(candidate_one)
    database_module.save_file_record(candidate_two)
    database_module.update_indexes(candidate_one)
    database_module.update_indexes(candidate_two)

    new_record = _record("new-1", "Doc.pdf", category=Category.DOCUMENT, path="/tmp/newest/Doc.pdf",
                          size_bytes=5000)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(
        new_record, {"c1": candidate_one, "c2": candidate_two, "new-1": new_record}
    )
    assert result.conflict_type != "cross_group"
    assert result.version_group_id is not None


# --- F4: single-best-match retention ---

def test_engine_retains_only_single_best_scoring_version_candidate(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    close_match = _record(
        "close", "Invoice_Acme_v1.pdf", category=Category.INVOICE,
        version_group_id="group-close", version_rank="latest",
    )
    weaker_match = _record(
        "weak", "Invoice_Other_v1.pdf", category=Category.INVOICE,
        version_group_id="group-weak", version_rank="latest",
        path="/tmp/other/Invoice_Other_v1.pdf",
    )
    database_module.save_file_record(close_match)
    database_module.save_file_record(weaker_match)
    database_module.update_indexes(close_match)
    database_module.update_indexes(weaker_match)

    new_record = _record("new-1", "Invoice_Acme_v2.pdf", category=Category.INVOICE,
                          path="/tmp/newest/Invoice_Acme_v2.pdf")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(
        new_record, {"close": close_match, "weak": weaker_match, "new-1": new_record}
    )
    # Only ever one group_id assigned — never ambiguity between two candidates.
    assert result.version_group_id in ("group-close", "group-weak")
    assert result.conflict_type != "cross_group"


# --- F2: category-scoped lookup_name_matches() ---

def test_lookup_name_matches_is_category_scoped(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    resume = _record("r1", "Report.pdf", category=Category.RESUME)
    document = _record("d1", "Report.pdf", category=Category.DOCUMENT, path="/tmp/other/Report.pdf")
    database_module.save_file_record(resume)
    database_module.save_file_record(document)
    database_module.update_indexes(resume)
    database_module.update_indexes(document)

    matches = database_module.lookup_name_matches("report", Category.RESUME)
    assert "r1" in matches
    assert "d1" not in matches


# --- PT-003 post-freeze correction: corroborating-signal requirement for
# version-chain candidacy (Module 04 Post-Freeze Design Correction — PT-003.md
# §6/§10). Reproduces the two confirmed real-world false-positive shapes
# (PATTERN_TRACKER.md PT-003) as regression tests, the identical-name branch's
# own corroboration requirement (Round 1 review Finding E1), and its documented
# edge cases (R6/R7, the zero-byte division-by-zero found during the round-2
# design re-evaluation). ---

def test_version_chain_near_miss_template_name_without_token_does_not_group(tmp_path, monkeypatch):
    """Reproduces Run 002's confirmed false-positive shape (VALIDATION_LEDGER.md
    VL-002-3): two same-category files sharing a long common template prefix,
    differing only in a trailing ordinal — similarity score >= 90, no explicit
    version token, no identical normalized name. Must NOT form a version-chain
    group."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-ms10", "Mark Sheet 10th.pdf", category=Category.DOCUMENT)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-ms12", "Mark Sheet 12th.pdf", category=Category.DOCUMENT)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-ms10": existing, "new-ms12": new_record})
    assert result.version_group_id is None


def test_version_chain_near_miss_generic_increment_without_token_does_not_group(tmp_path, monkeypatch):
    """Reproduces Run 003's confirmed false-positive shape (VALIDATION_LEDGER.md
    VL-003-2): a generic, tool-assigned filename differing only by an
    incrementing number in parentheses. Must NOT form a version-chain group."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-img2", "image (2).pdf", category=Category.DOCUMENT)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-img42", "image (42).pdf", category=Category.DOCUMENT)
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-img2": existing, "new-img42": new_record})
    assert result.version_group_id is None


def test_version_chain_identical_name_with_similar_size_and_no_token_groups(tmp_path, monkeypatch):
    """Positive control for the revised identical-name branch (§6): identical
    normalized name, no version token, sizes within the proximity ratio — must
    form a version-chain group."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-resave", "Report.pdf", category=Category.DOCUMENT, size_bytes=10000)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-resave", "Report.pdf", category=Category.DOCUMENT, size_bytes=11000,
                          path="/tmp/other/Report.pdf")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-resave": existing, "new-resave": new_record})
    assert result.version_group_id is not None


def test_version_chain_organic_rename_without_token_or_identical_name_does_not_group(tmp_path, monkeypatch):
    """Disclosed trade-off (R1/U3, design §6/§8/§12): a genuine version chain
    that uses neither an explicit version token nor an identical normalized name
    is not detected under the revised logic. This test reports the actual,
    accepted behavior explicitly, rather than presenting it as a silently
    "correct" outcome either way."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-summary", "Summary.pdf", category=Category.DOCUMENT, size_bytes=5000)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-summary", "Summary2.pdf", category=Category.DOCUMENT, size_bytes=5200,
                          path="/tmp/other/Summary2.pdf")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-summary": existing, "new-summary": new_record})
    assert result.version_group_id is None


def test_version_chain_identical_generic_name_with_dissimilar_size_does_not_group(tmp_path, monkeypatch):
    """Round 1 review Finding E1: a generic, uncustomized filename (e.g. two
    unrelated invoices both saved as "invoice.pdf") shared by two unrelated
    files must not be accepted as a version-chain candidate merely because the
    names are identical — the size-proximity check must reject a large size
    discrepancy."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-inv-a", "invoice.pdf", category=Category.INVOICE, size_bytes=20000)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-inv-b", "invoice.pdf", category=Category.INVOICE, size_bytes=2000,
                          path="/tmp/other/invoice.pdf")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-inv-a": existing, "new-inv-b": new_record})
    assert result.version_group_id is None


def test_version_chain_identical_generic_name_with_similar_size_groups_as_disclosed_residual(tmp_path, monkeypatch):
    """R6 (disclosed residual, design §6/§8): the size-proximity check narrows
    but does not eliminate Finding E1's exposure — two unrelated files that
    coincidentally share both a generic name and a similar size still group.
    This is the documented, accepted ambiguous case, not a defect."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-inv-c", "invoice.pdf", category=Category.INVOICE, size_bytes=20000)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-inv-d", "invoice.pdf", category=Category.INVOICE, size_bytes=21000,
                          path="/tmp/other2/invoice.pdf")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-inv-c": existing, "new-inv-d": new_record})
    assert result.version_group_id is not None


def test_version_chain_identical_name_with_missing_size_on_one_side_does_not_group(tmp_path, monkeypatch):
    """R7 (design §6/§8): size_bytes is Optional[int] — if either side lacks a
    value, the size-proximity check cannot be evaluated and must fail
    conservatively (does not qualify), never default to qualifying."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-nosize", "Contract2.pdf", category=Category.CONTRACT, size_bytes=None)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-nosize", "Contract2.pdf", category=Category.CONTRACT, size_bytes=8000,
                          path="/tmp/other/Contract2.pdf")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-nosize": existing, "new-nosize": new_record})
    assert result.version_group_id is None


def test_version_chain_identical_name_with_both_sizes_zero_groups_without_error(tmp_path, monkeypatch):
    """Zero-byte edge case identified during the round-2 design re-evaluation
    (design §6): the size-proximity formula min/max is undefined for 0/0. Two
    zero-byte files sharing an identical name must be treated as unambiguously
    equal in size (special-cased) — must group, and must not raise."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-zero", "Empty.pdf", category=Category.DOCUMENT, size_bytes=0)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-zero", "Empty.pdf", category=Category.DOCUMENT, size_bytes=0,
                          path="/tmp/other/Empty.pdf")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-zero": existing, "new-zero": new_record})
    assert result.version_group_id is not None


def test_version_chain_explicit_token_still_sufficient_without_size_data(tmp_path, monkeypatch):
    """Confirms the explicit-token branch is genuinely unaffected by the PT-003
    correction: an explicit version token remains sufficient corroboration on
    its own, with no size data required on either side (design §6 — unchanged
    from Revision 1)."""
    _isolate_storage(tmp_path, monkeypatch)
    existing = _record("existing-token", "Notes_v1.pdf", category=Category.DOCUMENT, size_bytes=None)
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    new_record = _record("new-token", "Notes_v2.pdf", category=Category.DOCUMENT, size_bytes=None,
                          path="/tmp/other/Notes_v2.pdf")
    engine = DuplicateDetectionEngine()
    result = engine.detect_file(new_record, {"existing-token": existing, "new-token": new_record})
    assert result.version_group_id is not None


# --- Module Contract immutability (§5) ---
# M2 (Independent Implementation Audit): exhaustive asdict()-loop pattern, mirroring
# Module 03's own precedent
# (test_extract_metadata_batch_leaves_every_non_owned_field_byte_identical) — every
# FileRecord field is compared automatically, not a hand-picked subset.

def test_module_contract_immutability_every_non_owned_field_byte_identical(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)

    existing = _record("existing-2", "invoice.pdf", category=Category.INVOICE, content_hash="hash-shared")
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

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
        extracted_metadata={"vendor": "Acme"},
        suggested_name="already_set_name.pdf",
        suggested_destination="Finance/Somewhere",
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
    detect_duplicates_batch([record])
    after = asdict(record)

    owned_fields = {"duplicate_of", "version_group_id", "version_rank", "duplicate_signals"}
    for field_name in before:
        if field_name in owned_fields:
            continue
        assert after[field_name] == before[field_name], (
            f"Module 04 modified {field_name!r}, which it does not own per "
            f"Module 04 Design.md §5's DOES NOT MODIFY list"
        )

    # Confirm Module 04 actually did its job — otherwise this test would trivially
    # pass by detect_duplicates_batch() doing nothing.
    assert after["duplicate_of"] == "existing-2"
    assert after["duplicate_signals"]["exact_duplicate"] is True


def test_module_contract_side_effect_exhaustively_verified_on_other_record(tmp_path, monkeypatch):
    """The one disclosed exception (§4/§7, post-freeze correction) never touches
    any field on another record besides version_group_id/version_rank — verified
    exhaustively over every FileRecord field, not a hand-picked subset, and the
    resulting version_rank VALUE is checked, not merely that it changed (the gap
    M2 found in the original spot-check version of this test)."""
    _isolate_storage(tmp_path, monkeypatch)

    existing = FileRecord(
        file_id="existing-3",
        source_id="contract-source",
        original_name="Resume_v1.pdf",
        original_path="arbitrary/original/path.pdf",
        current_path="/tmp/Resume_v1.pdf",
        extension=".pdf",
        mime_type="application/pdf",
        size_bytes=54321,
        created_at="2020-02-01T00:00:00Z",
        modified_at="2020-02-02T00:00:00Z",
        content_hash="hash-existing-3",
        discovered_at="2020-02-03T00:00:00Z",
        status="discovered",
        error=None,
        category=Category.RESUME,
        classification_signals=ClassificationSignals(ambiguous=False),
        extracted_metadata={"last_modified_date": "2020-02-01"},
        suggested_name="already_set_other.pdf",
        suggested_destination="Finance/Elsewhere",
        confidence_score=81,
        confidence_breakdown={"another_deduction": -3},
        tier="approval_required",
        batch_id="batch-other-contract-test",
        processed_at="2020-02-04T00:00:00Z",
        approved_by="user",
        approved_at="2020-02-05T00:00:00Z",
        reversible=False,
    )
    database_module.save_file_record(existing)
    database_module.update_indexes(existing)

    before = asdict(existing)

    new_record = _record("new-3", "Resume_v2.pdf", category=Category.RESUME, content_hash="hash-new-3")
    detect_duplicates_batch([new_record])

    reloaded_existing = next(
        r for r in database_module.load_metadata_store() if r.file_id == "existing-3"
    )
    after = asdict(reloaded_existing)

    owned_fields = {"version_group_id", "version_rank"}
    for field_name in before:
        if field_name in owned_fields:
            continue
        assert after[field_name] == before[field_name], (
            f"Module 04's side effect modified {field_name!r} on another record, "
            f"outside the one disclosed exception (§4/§7)"
        )

    # Confirm the disclosed exception actually fired, with the CORRECT resulting
    # value on the other record — v2 is newer, so v1 (existing-3) becomes superseded.
    assert after["version_group_id"] is not None
    assert after["version_rank"] == "superseded"


# --- detect_duplicates_batch() orchestration ---

def test_batch_skips_records_already_processed(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    already_done = _record("done-1", "invoice.pdf", category=Category.INVOICE,
                            content_hash="hash-1", version_group_id=None,
                            duplicate_of="something-else",
                            duplicate_signals=DuplicateSignals(exact_duplicate=True))
    result = detect_duplicates_batch([already_done])
    assert result[0].duplicate_of == "something-else"  # unchanged, not reprocessed


# --- H1 (post-freeze correction #2): needs_duplicate_detection() idempotency rule ---
# Independent Implementation Audit finding H1 — the original idempotency check
# (duplicate_of/version_group_id/version_rank all None) never actually fires for a
# "nothing found" outcome, since all three legitimately stay None forever after a
# fully correct, negative-result run. These tests cover every outcome shape
# `needs_duplicate_detection()` must distinguish (§7 post-freeze correction #2).

def test_needs_duplicate_detection_true_when_never_processed():
    never_touched = _record("never-1", "invoice.pdf", category=Category.INVOICE)
    assert never_touched.duplicate_signals is None
    assert needs_duplicate_detection(never_touched) is True


def test_needs_duplicate_detection_false_after_exact_duplicate_found():
    settled = _record("settled-1", "invoice.pdf", category=Category.INVOICE,
                       duplicate_of="original-1",
                       duplicate_signals=DuplicateSignals(exact_duplicate=True))
    assert needs_duplicate_detection(settled) is False


def test_needs_duplicate_detection_false_after_genuinely_nothing_found():
    """The core H1 regression: a record Module 04 processed and correctly found no
    exact duplicate, no near-duplicate, and no version chain for — duplicate_of/
    version_group_id/version_rank all stay None, but duplicate_signals is a real,
    fully-populated (all-negative) instance. Must be treated as settled, not
    perpetually eligible."""
    settled_unique = _record("unique-1", "totally_unique.pdf", category=Category.DOCUMENT,
                              duplicate_signals=DuplicateSignals())
    assert settled_unique.duplicate_of is None
    assert settled_unique.version_group_id is None
    assert settled_unique.version_rank is None
    assert needs_duplicate_detection(settled_unique) is False


def test_needs_duplicate_detection_false_after_version_chain_formed_with_conflict():
    """A within-group date/token conflict still results in a real version_group_id
    being set (§7 step 3.4) — must NOT be confused with the cross-group case below,
    even though both set duplicate_signals.version_conflict = True."""
    settled_conflict = _record(
        "settled-conflict-1", "Resume_v9.pdf", category=Category.RESUME,
        version_group_id="group-1", version_rank="latest",
        duplicate_signals=DuplicateSignals(version_conflict=True),
    )
    assert needs_duplicate_detection(settled_conflict) is False


def test_needs_duplicate_detection_true_for_unresolved_cross_group_conflict():
    """The one deliberately-preserved exception (fifth architecture-review pass):
    an unresolved cross-group conflict stays eligible for re-examination on every
    run — version_group_id/version_rank both None, version_conflict True."""
    unresolved = _record(
        "conflict-1", "Statement.pdf", category=Category.BANK_STATEMENT,
        duplicate_signals=DuplicateSignals(version_conflict=True),
    )
    assert unresolved.version_group_id is None
    assert needs_duplicate_detection(unresolved) is True


def test_batch_does_not_reprocess_or_relog_a_genuinely_unique_file_on_a_second_run(tmp_path, monkeypatch):
    """H1 integration-level regression: run the same never-seen-before, no-match
    file through detect_duplicates_batch() twice (simulating two runs of a
    scheduled/repeated automation) and confirm only ONE action-log entry and ONE
    settled outcome results — not two."""
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("unique-run-1", "totally_unique_file.pdf", category=Category.DOCUMENT,
                      content_hash="hash-unique-xyz")
    detect_duplicates_batch([record])

    # Simulate a second, independent run: reload from the store and re-filter,
    # exactly like main.py's detect_duplicates() would.
    eligible_second_run = [
        r for r in database_module.load_metadata_store()
        if r.status == "discovered" and needs_duplicate_detection(r)
    ]
    assert eligible_second_run == []  # nothing left to process — this is the fix
    detect_duplicates_batch(eligible_second_run)

    import json
    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines if json.loads(line)["file_id"] == "unique-run-1"]
    assert len(entries) == 1  # not two — the record was never reprocessed


def test_batch_still_reprocesses_an_unresolved_cross_group_conflict_on_every_run(tmp_path, monkeypatch):
    """The flip side of the fix above: H1's correction must NOT silently make a
    genuinely-unresolved cross-group conflict idempotent too — the fifth
    architecture-review pass explicitly decided this state should stay visible
    (re-examined and re-logged) on every run until manually resolved.

    PT-003 post-freeze correction: all three records share matching size_bytes
    (5000) so the identical-name candidacy corroboration (§6) is satisfied — this
    test exercises re-examination idempotency, not PT-003's own fix, so the
    fixtures are adapted to keep reaching that logic under the revised candidacy
    rule (Module 04 Post-Freeze Design Correction — PT-003.md §9)."""
    _isolate_storage(tmp_path, monkeypatch)
    group_a_member = _record("ga-1", "Statement.pdf", category=Category.BANK_STATEMENT,
                              version_group_id="group-a", version_rank="latest", size_bytes=5000)
    group_b_member = _record("gb-1", "Statement.pdf", category=Category.BANK_STATEMENT,
                              version_group_id="group-b", version_rank="latest",
                              path="/tmp/other/Statement.pdf", size_bytes=5000)
    database_module.save_file_record(group_a_member)
    database_module.save_file_record(group_b_member)
    database_module.update_indexes(group_a_member)
    database_module.update_indexes(group_b_member)

    conflicted = _record("conflicted-1", "Statement.pdf", category=Category.BANK_STATEMENT,
                          path="/tmp/newest/Statement.pdf", size_bytes=5000)
    detect_duplicates_batch([conflicted])

    for _ in range(2):
        eligible = [
            r for r in database_module.load_metadata_store()
            if r.status == "discovered" and needs_duplicate_detection(r)
            and r.file_id == "conflicted-1"
        ]
        assert len(eligible) == 1  # still eligible every run — not a bug
        detect_duplicates_batch(eligible)

    import json
    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines if json.loads(line)["file_id"] == "conflicted-1"]
    assert len(entries) == 3  # one initial run + two re-runs, all logged — preserved behavior


def test_batch_skips_non_discovered_status(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    unreadable = FileRecord(
        file_id="unreadable-1", source_id="downloads", original_name="broken.pdf",
        original_path="/tmp/broken.pdf", current_path="/tmp/broken.pdf",
        status="unreadable", content_hash=None,
    )
    result = detect_duplicates_batch([unreadable])
    assert result[0].duplicate_signals is None


def test_batch_writes_a_detect_duplicates_and_versions_action_log_entry(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _record("log-1", "invoice.pdf", category=Category.INVOICE, content_hash="hash-log")
    detect_duplicates_batch([record])

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    import json
    entries = [json.loads(line) for line in log_lines]
    assert any(e["action"] == "detect_duplicates_and_versions" and e["file_id"] == "log-1"
               for e in entries)


def test_batch_deterministic_order_f1(tmp_path, monkeypatch):
    """F1: re-running the same batch (or supplying it in a different input-list
    order) must produce the same result — records are processed by discovered_at
    ascending, file_id as the final tie-break."""
    _isolate_storage(tmp_path, monkeypatch)
    early = _record("early", "Resume_v1.pdf", category=Category.RESUME,
                     discovered_at="2026-01-01T00:00:00Z")
    late = _record("late", "Resume_v2.pdf", category=Category.RESUME,
                    discovered_at="2026-02-01T00:00:00Z")

    # Supply in reverse order — outcome must be identical either way.
    result = detect_duplicates_batch([late, early])
    early_result = next(r for r in result if r.file_id == "early")
    late_result = next(r for r in result if r.file_id == "late")

    # early is processed first (no candidate exists yet, so no group forms). late is
    # processed second, finds early as a candidate, and — since v2 genuinely outranks
    # v1 by version token — late becomes "latest" while early flips to "superseded"
    # as this module's one disclosed side effect (§4/§7).
    assert late_result.version_rank == "latest"
    assert early_result.version_rank == "superseded"
    assert early_result.version_group_id == late_result.version_group_id


def test_batch_tie_break_by_file_id_for_identical_discovered_at(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    same_time = "2026-01-01T00:00:00Z"
    record_b = _record("b-record", "Resume_v2.pdf", category=Category.RESUME, discovered_at=same_time)
    record_a = _record("a-record", "Resume_v1.pdf", category=Category.RESUME, discovered_at=same_time)

    result = detect_duplicates_batch([record_b, record_a])
    a_result = next(r for r in result if r.file_id == "a-record")
    b_result = next(r for r in result if r.file_id == "b-record")
    # "a-record" sorts before "b-record" lexicographically -> processed first (no
    # candidate exists yet at that point, so it forms no group on its own). Once
    # "b-record" is processed second, it finds "a-record" as a candidate and — since
    # v2 genuinely outranks v1 by version token — becomes "latest" while "a-record"
    # flips to "superseded" as the disclosed side effect. This is the observable
    # proof that processing order is deterministic given the discovered_at tie.
    assert b_result.version_rank == "latest"
    assert a_result.version_rank == "superseded"
    assert a_result.version_group_id == b_result.version_group_id


def test_batch_side_effect_gets_its_own_second_log_line(tmp_path, monkeypatch):
    """§18: the affected other record's own log entry is never rewritten — a
    second, separate line is appended instead."""
    _isolate_storage(tmp_path, monkeypatch)
    v1 = _record("v1", "Resume_v1.pdf", category=Category.RESUME, discovered_at="2026-01-01T00:00:00Z")
    detect_duplicates_batch([v1])

    v2 = _record("v2", "Resume_v2.pdf", category=Category.RESUME, discovered_at="2026-02-01T00:00:00Z")
    detect_duplicates_batch([v2])

    import json
    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines]
    v1_entries = [e for e in entries if e["file_id"] == "v1"]
    assert len(v1_entries) == 2  # original + side-effect line
    assert v1_entries[1]["details"].get("joined_by") == "v2"
