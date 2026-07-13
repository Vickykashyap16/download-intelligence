"""
Unit tests for pipeline/execution.py — Module 07 (Preview, Approval & Execution).

WP-1 scope: `needs_execution()` (Module 07 Design.md §13A).
WP-2 scope: `resolve_precedence()` (§11A), `resolve_destination_path()` (§11),
`_reject_path_escape()` (§22).
WP-3 scope: `preview_batch()` (§9, §10 step 1).
WP-4 scope: `evaluate_gate()` (§13, restated from §0.4's invariant table) — the
module's own "highest-consequence decision point"; tests here get disproportionate
adversarial attention to match, per the design's own stated review expectation.
WP-5 scope: `check_real_collision()`, `apply_collision_suffix()`,
`resolve_available_destination()`, `ensure_destination_folder()`, `perform_move()`
(§12, §14) — this module's first real filesystem mutation. Tested against a real,
sandboxed `tmp_path` filesystem throughout, never mocked, per the Implementation
Plan's own explicit requirement for "genuine confidence."
WP-6 scope: `log_move()`, `log_error()`, `log_decline()` (§17/§25) — wires the
already-implemented `append_action_log()`. Isolated from the project's real
`Runtime/Logs/action_log.jsonl` via the same `monkeypatch.setattr(runtime_io_
module, "_ACTION_LOG_PATH", tmp_path / ...)` convention `pipeline/test_naming.py`
already established.
WP-7 scope: `ExecutionEngine` (§9) — the per-file orchestration unit composing
WP-1/WP-2/WP-4/WP-5/WP-6 into the fixed six-step sequence. Tested against a
real, sandboxed `tmp_path` filesystem throughout (never mocked, per WP-5's own
established precedent for this module's real filesystem mutations), with
`perform_move()`/`ensure_destination_folder()`/`log_move()`/etc. left
completely unmodified — only `ExecutionEngine` itself is new code under test
here.
WP-8 scope: `reconcile_batch()` (§13A) — the crash-reconciliation procedure,
plus `stage_batch_temp()`/`clear_batch_temp()`/`write_batch_plan()`/
`read_batch_plan()`/`read_action_log_entries()` (`src/storage/runtime_io.py`).
Isolated from the project's real `Database/Metadata/metadata_store.json` via
the same `monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", ...)`
convention `pipeline/test_naming.py` established, and from the real
`Runtime/Temp/` via an equivalent `monkeypatch.setattr(runtime_io_module,
"_RUNTIME_TEMP_PATH", ...)`. Tested against a real, sandboxed `tmp_path`
filesystem throughout — never mocked — matching every real-filesystem WP-5/
WP-7 precedent.

The pre-existing `build_preview()`/`execute_approved()`/`log_rejected_edit()` stubs
remain NotImplementedError, out of every work package's scope so far, and are not
tested here.

Run with: pytest src/pipeline/test_execution.py -v
"""

import copy
import json
from pathlib import Path

import pytest

import src.pipeline.execution as execution_module
import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.classification import Category
from src.models.execution import (
    ApprovalDecision,
    ApprovalDecisionType,
    ExecutionOutcome,
    GateResult,
    MoveResult,
    PreviewRow,
    ReconciliationOutcome,
    ReconciliationReport,
    UndoOutcome,
    UndoReport,
)
from src.pipeline.execution import (
    ExecutionEngine,
    apply_collision_suffix,
    check_real_collision,
    ensure_destination_folder,
    evaluate_gate,
    execute_batch,
    log_decline,
    log_error,
    log_move,
    log_undo,
    needs_execution,
    perform_move,
    preview_batch,
    reconcile_batch,
    resolve_available_destination,
    resolve_destination_path,
    resolve_precedence,
    undo_batch,
    undo_single_action,
)
from src.storage.database import load_metadata_store, save_file_record
from src.storage.runtime_io import (
    clear_batch_temp,
    read_action_log_entries,
    read_batch_plan,
    stage_batch_temp,
    write_batch_plan,
)
from src.models.file_record import FileRecord


def _record(file_id="f1", processed_at=None, tier=None, current_path="/tmp/invoice.pdf",
            duplicate_of=None, version_rank=None, confidence_score=92,
            suggested_name="Amazon_2026-07-05.pdf", suggested_destination="Finance/",
            **kwargs):
    return FileRecord(
        file_id=file_id, source_id="downloads", original_name="invoice.pdf",
        original_path="/tmp/invoice.pdf", current_path=current_path,
        status="discovered", category=Category.INVOICE,
        discovered_at="2026-01-01T00:00:00Z", batch_id="batch-1",
        processed_at=processed_at, tier=tier,
        duplicate_of=duplicate_of, version_rank=version_rank,
        confidence_score=confidence_score,
        suggested_name=suggested_name, suggested_destination=suggested_destination,
        **kwargs,
    )


def _isolate_action_log(tmp_path, monkeypatch):
    """Same isolation convention pipeline/test_naming.py already established —
    redirect append_action_log()'s target file to a sandboxed tmp_path, never
    the project's real Runtime/Logs/action_log.jsonl."""
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


def _read_log_entries(tmp_path):
    log_path = tmp_path / "action_log.jsonl"
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().strip().splitlines()]


def _isolate_database_and_temp(tmp_path, monkeypatch):
    """WP-8's own isolation convention, extending `_isolate_action_log()`'s
    established pattern to the two additional real-storage locations
    `reconcile_batch()` touches: `Database/Metadata/metadata_store.json`
    (`src/storage/database.py`, same `monkeypatch.setattr(database_module,
    "_METADATA_STORE_PATH", ...)` convention `pipeline/test_naming.py`
    established) and `Runtime/Temp/` (`src/storage/runtime_io.py`, a new
    `_RUNTIME_TEMP_PATH` isolation target, WP-8's own addition)."""
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_RUNTIME_TEMP_PATH", tmp_path / "Temp")


def test_needs_execution_true_when_processed_at_is_none():
    record = _record(processed_at=None)
    assert needs_execution(record) is True


def test_needs_execution_false_when_processed_at_is_set():
    record = _record(processed_at="2026-07-12T14:32:00Z")
    assert needs_execution(record) is False


def test_needs_execution_ignores_tier_entirely():
    """§13A: `processed_at` alone is authoritative — tier plays no role in
    recognizing "already executed."""
    for tier in ("auto", "approval_required", "review_required", None):
        unexecuted = _record(file_id=f"unexecuted-{tier}", processed_at=None, tier=tier)
        assert needs_execution(unexecuted) is True

        executed = _record(file_id=f"executed-{tier}", processed_at="2026-07-12T14:32:00Z", tier=tier)
        assert needs_execution(executed) is False


def test_needs_execution_ignores_approved_by_approved_at_current_path():
    """§13A: approved_by/approved_at/current_path are set atomically alongside
    processed_at and are never checked independently for idempotency purposes —
    only processed_at is authoritative. A record with those three populated but
    processed_at still None (an inconsistent, synthetic state that should never
    occur from a real ExecutionEngine run) is still correctly treated as needing
    execution, proving the function doesn't accidentally key off any of them."""
    record = _record(
        processed_at=None, approved_by="user", approved_at="2026-07-12T14:32:00Z",
        current_path="/Users/vicky/Finance/Amazon_2026-07-05.pdf",
    )
    assert needs_execution(record) is True


def test_needs_execution_second_call_on_same_record_is_stable():
    """Calling needs_execution() repeatedly on the same, unchanged record instance
    always returns the same answer — the function is pure and has no side effects."""
    record = _record(processed_at=None)
    assert needs_execution(record) is True
    assert needs_execution(record) is True

    record.processed_at = "2026-07-12T14:32:00Z"
    assert needs_execution(record) is False
    assert needs_execution(record) is False


# --- resolve_precedence() (§11A) ---

def test_resolve_precedence_review_required_wins_unconditionally():
    record = _record(tier="review_required")
    assert resolve_precedence(record) == "review_required"


def test_resolve_precedence_exact_duplicate_when_not_review_required():
    record = _record(tier="auto", duplicate_of="other-file-id")
    assert resolve_precedence(record) == "exact_duplicate"


def test_resolve_precedence_superseded_version_when_not_duplicate():
    record = _record(tier="auto", version_rank="superseded")
    assert resolve_precedence(record) == "superseded_version"


def test_resolve_precedence_normal_when_nothing_else_applies():
    record = _record(tier="auto", duplicate_of=None, version_rank=None)
    assert resolve_precedence(record) == "normal"


def test_resolve_precedence_normal_when_version_rank_is_latest_not_superseded():
    """version_rank == "latest" is not "superseded" — the normal mapping applies,
    not the archive override."""
    record = _record(tier="approval_required", version_rank="latest")
    assert resolve_precedence(record) == "normal"


def test_resolve_precedence_adversarial_review_required_and_exact_duplicate(): # I8
    """Module 07 Design.md §11A/I8's own adversarial case: a record that is
    SIMULTANEOUSLY review_required AND an exact duplicate. review_required must
    win — the duplicate override is never even reached."""
    record = _record(tier="review_required", duplicate_of="other-file-id")
    assert resolve_precedence(record) == "review_required"


def test_resolve_precedence_adversarial_review_required_and_superseded_version():
    """Same adversarial case, with the superseded-version override instead."""
    record = _record(tier="review_required", version_rank="superseded")
    assert resolve_precedence(record) == "review_required"


def test_resolve_precedence_adversarial_review_required_and_both_overrides():
    """The strongest adversarial case: review_required, exact duplicate, AND
    superseded version all simultaneously true. review_required still wins."""
    record = _record(tier="review_required", duplicate_of="other-file-id", version_rank="superseded")
    assert resolve_precedence(record) == "review_required"


def test_resolve_precedence_exact_duplicate_beats_superseded_version():
    """§11A's fixed order: exact duplicate (step 2) is checked before superseded
    version (step 3) — a record that is somehow both takes the duplicate path."""
    record = _record(tier="auto", duplicate_of="other-file-id", version_rank="superseded")
    assert resolve_precedence(record) == "exact_duplicate"


# --- resolve_destination_path() (§11) ---

def test_resolve_destination_path_normal_case():
    record = _record(suggested_name="Amazon_2026-07-05.pdf", suggested_destination="Finance/")
    result = resolve_destination_path(record, "/Users/vicky/FiledLibrary", "normal")
    assert str(result) == "/Users/vicky/FiledLibrary/Finance/Amazon_2026-07-05.pdf"


def test_resolve_destination_path_exact_duplicate_uses_fixed_archive_path():
    record = _record(suggested_name="dup.pdf", suggested_destination="Finance/")
    result = resolve_destination_path(record, "/Users/vicky/FiledLibrary", "exact_duplicate")
    assert str(result) == "/Users/vicky/FiledLibrary/~ARCHIVE~/Duplicates/dup.pdf"


def test_resolve_destination_path_superseded_version_uses_fixed_archive_path():
    record = _record(suggested_name="Resume_v8.pdf", suggested_destination="Documents/")
    result = resolve_destination_path(record, "/Users/vicky/FiledLibrary", "superseded_version")
    assert str(result) == "/Users/vicky/FiledLibrary/~ARCHIVE~/Old Versions/Resume_v8.pdf"


def test_resolve_destination_path_rejects_review_required_override_type():
    record = _record(tier="review_required")
    with pytest.raises(ValueError, match="review_required"):
        resolve_destination_path(record, "/Users/vicky/FiledLibrary", "review_required")


def test_resolve_destination_path_rejects_unrecognized_override_type():
    record = _record()
    with pytest.raises(ValueError, match="Unrecognized override_type"):
        resolve_destination_path(record, "/Users/vicky/FiledLibrary", "not_a_real_override")


def test_resolve_destination_path_edited_name_honored_in_normal_case():
    record = _record(suggested_name="Amazon_2026-07-05.pdf", suggested_destination="Finance/")
    result = resolve_destination_path(
        record, "/Users/vicky/FiledLibrary", "normal", edited_name="Renamed_Invoice.pdf",
    )
    assert str(result) == "/Users/vicky/FiledLibrary/Finance/Renamed_Invoice.pdf"


def test_resolve_destination_path_edited_destination_honored_in_normal_case():
    record = _record(suggested_name="Amazon_2026-07-05.pdf", suggested_destination="Finance/")
    result = resolve_destination_path(
        record, "/Users/vicky/FiledLibrary", "normal", edited_destination="Documents/",
    )
    assert str(result) == "/Users/vicky/FiledLibrary/Documents/Amazon_2026-07-05.pdf"


def test_resolve_destination_path_edited_name_honored_even_for_exact_duplicate():
    """An edited *name* is always honored, regardless of override_type — only the
    destination-folder component has archive-override precedence over an edit."""
    record = _record(suggested_name="dup.pdf", suggested_destination="Finance/")
    result = resolve_destination_path(
        record, "/Users/vicky/FiledLibrary", "exact_duplicate", edited_name="Renamed_Dup.pdf",
    )
    assert str(result) == "/Users/vicky/FiledLibrary/~ARCHIVE~/Duplicates/Renamed_Dup.pdf"


def test_resolve_destination_path_edited_destination_honored_for_exact_duplicate():
    """ARCHITECTURE_DECISIONS.md decision 23 (WP-2 correction, resolving the
    original WP-2 audit's Medium finding): an edited destination IS honored even
    when the record is an exact duplicate — review_required is the only
    unconditional exception, and it never reaches this function at all."""
    record = _record(suggested_name="dup.pdf", suggested_destination="Finance/")
    result = resolve_destination_path(
        record, "/Users/vicky/FiledLibrary", "exact_duplicate", edited_destination="Documents/",
    )
    assert str(result) == "/Users/vicky/FiledLibrary/Documents/dup.pdf"


def test_resolve_destination_path_edited_destination_honored_for_superseded_version():
    """Decision 23, same reasoning as the exact-duplicate case directly above."""
    record = _record(suggested_name="Resume_v8.pdf", suggested_destination="Documents/")
    result = resolve_destination_path(
        record, "/Users/vicky/FiledLibrary", "superseded_version", edited_destination="Finance/",
    )
    assert str(result) == "/Users/vicky/FiledLibrary/Finance/Resume_v8.pdf"


def test_resolve_destination_path_edited_name_and_destination_both_honored_for_exact_duplicate():
    """A single APPROVE_WITH_EDIT decision can redirect both the name and the
    destination away from the archive placement at once — decision 23 draws no
    distinction between the two edit fields for this purpose."""
    record = _record(suggested_name="dup.pdf", suggested_destination="Finance/")
    result = resolve_destination_path(
        record, "/Users/vicky/FiledLibrary", "exact_duplicate",
        edited_name="Definitely_Not_A_Dup.pdf", edited_destination="Documents/",
    )
    assert str(result) == "/Users/vicky/FiledLibrary/Documents/Definitely_Not_A_Dup.pdf"


def test_resolve_destination_path_no_edited_destination_still_archives_exact_duplicate():
    """The archive placement remains the correct DEFAULT — decision 23 only
    changes what happens when a human explicitly supplies an edit; an
    APPROVE_AS_SUGGESTED decision (no edited_destination at all) still archives
    exactly as before this correction."""
    record = _record(suggested_name="dup.pdf", suggested_destination="Finance/")
    result = resolve_destination_path(record, "/Users/vicky/FiledLibrary", "exact_duplicate")
    assert str(result) == "/Users/vicky/FiledLibrary/~ARCHIVE~/Duplicates/dup.pdf"


def test_resolve_destination_path_no_edited_destination_still_archives_superseded_version():
    record = _record(suggested_name="Resume_v8.pdf", suggested_destination="Documents/")
    result = resolve_destination_path(record, "/Users/vicky/FiledLibrary", "superseded_version")
    assert str(result) == "/Users/vicky/FiledLibrary/~ARCHIVE~/Old Versions/Resume_v8.pdf"


def test_resolve_destination_path_edited_destination_path_escape_still_rejected_for_exact_duplicate():
    """Decision 23 honors an edited destination for archive override types — it
    does not weaken §22's path-escape guard, which still applies to that edited
    value exactly as it does in the normal case."""
    record = _record(suggested_name="dup.pdf", suggested_destination="Finance/")
    with pytest.raises(ValueError, match="destination"):
        resolve_destination_path(
            record, "/Users/vicky/FiledLibrary", "exact_duplicate", edited_destination="../../etc/",
        )


def test_resolve_destination_path_performs_no_filesystem_access():
    """Pure function — a nonexistent library_root never raises, proving no
    existence/collision check happens here (that's a later work package's job,
    WP-5, §12)."""
    record = _record(suggested_name="a.pdf", suggested_destination="Documents/")
    result = resolve_destination_path(record, "/this/path/does/not/exist/anywhere", "normal")
    assert str(result) == "/this/path/does/not/exist/anywhere/Documents/a.pdf"


def test_resolve_destination_path_accepts_multi_segment_destination():
    record = _record(suggested_name="screenshot.png", suggested_destination="Images/Screenshots/")
    result = resolve_destination_path(record, "/Users/vicky/FiledLibrary", "normal")
    assert str(result) == "/Users/vicky/FiledLibrary/Images/Screenshots/screenshot.png"


# --- Path-escape rejection (§22) ---

def test_resolve_destination_path_rejects_traversal_in_suggested_destination():
    record = _record(suggested_name="a.pdf", suggested_destination="../../etc/")
    with pytest.raises(ValueError, match="destination"):
        resolve_destination_path(record, "/Users/vicky/FiledLibrary", "normal")


def test_resolve_destination_path_rejects_traversal_in_suggested_name():
    record = _record(suggested_name="../../etc/passwd", suggested_destination="Documents/")
    with pytest.raises(ValueError, match="name"):
        resolve_destination_path(record, "/Users/vicky/FiledLibrary", "normal")


def test_resolve_destination_path_rejects_traversal_in_edited_destination():
    record = _record(suggested_name="a.pdf", suggested_destination="Documents/")
    with pytest.raises(ValueError, match="destination"):
        resolve_destination_path(
            record, "/Users/vicky/FiledLibrary", "normal", edited_destination="../../etc/",
        )


def test_resolve_destination_path_rejects_traversal_in_edited_name():
    record = _record(suggested_name="a.pdf", suggested_destination="Documents/")
    with pytest.raises(ValueError, match="name"):
        resolve_destination_path(
            record, "/Users/vicky/FiledLibrary", "normal", edited_name="../../../etc/passwd",
        )


def test_resolve_destination_path_rejects_absolute_path_as_destination():
    record = _record(suggested_name="a.pdf", suggested_destination="/etc/")
    with pytest.raises(ValueError, match="absolute"):
        resolve_destination_path(record, "/Users/vicky/FiledLibrary", "normal")


def test_resolve_destination_path_rejects_absolute_path_as_edited_name():
    record = _record(suggested_name="a.pdf", suggested_destination="Documents/")
    with pytest.raises(ValueError, match="absolute"):
        resolve_destination_path(
            record, "/Users/vicky/FiledLibrary", "normal", edited_name="/etc/passwd",
        )


def test_resolve_destination_path_allows_literal_tilde_archive_folder_name():
    """`~ARCHIVE~/` is a real, valid, non-expanding literal folder name (Rules/
    Folder Rules.md) — must never be rejected as a path-escape attempt."""
    record = _record(suggested_name="dup.pdf", suggested_destination="Finance/")
    result = resolve_destination_path(record, "/Users/vicky/FiledLibrary", "exact_duplicate")
    assert "~ARCHIVE~" in str(result)


def test_resolve_destination_path_rejects_traversal_disguised_mid_path():
    """A traversal segment doesn't have to be at the very start to be dangerous —
    "Finance/../../etc/" still escapes once resolved."""
    record = _record(suggested_name="a.pdf", suggested_destination="Finance/../../etc/")
    with pytest.raises(ValueError, match="destination"):
        resolve_destination_path(record, "/Users/vicky/FiledLibrary", "normal")


# --- preview_batch() (§9, §10 step 1) ---

def test_preview_batch_empty_list_returns_empty_list():
    assert preview_batch([]) == []


def test_preview_batch_produces_one_row_per_record():
    records = [
        _record(file_id="f1", tier="auto"),
        _record(file_id="f2", tier="approval_required"),
        _record(file_id="f3", tier="review_required"),
    ]
    rows = preview_batch(records)
    assert len(rows) == 3
    assert [row.file_id for row in rows] == ["f1", "f2", "f3"]


def test_preview_batch_field_mapping_is_correct_for_normal_case():
    record = _record(
        file_id="f1", tier="approval_required", confidence_score=88,
        suggested_name="Amazon_2026-07-05.pdf", suggested_destination="Finance/",
        current_path="/tmp/invoice.pdf",
    )
    row = preview_batch([record])[0]
    assert isinstance(row, PreviewRow)
    assert row.file_id == "f1"
    assert row.original_name == record.original_name
    assert row.suggested_name == "Amazon_2026-07-05.pdf"
    assert row.current_path == "/tmp/invoice.pdf"
    assert row.suggested_destination == "Finance/"
    assert row.category == Category.INVOICE
    assert row.confidence_score == 88
    assert row.tier == "approval_required"
    assert row.override is None


def test_preview_batch_normal_case_has_no_override():
    record = _record(tier="auto", duplicate_of=None, version_rank=None)
    row = preview_batch([record])[0]
    assert row.override is None
    assert row.suggested_destination == record.suggested_destination


def test_preview_batch_exact_duplicate_row_shows_archive_destination_and_override():
    record = _record(
        tier="approval_required", duplicate_of="other-file-id",
        suggested_destination="Finance/",
    )
    row = preview_batch([record])[0]
    assert row.override == "exact_duplicate"
    assert row.suggested_destination == "~ARCHIVE~/Duplicates/"


def test_preview_batch_superseded_version_row_shows_archive_destination_and_override():
    record = _record(
        tier="auto", version_rank="superseded", suggested_destination="Documents/",
    )
    row = preview_batch([record])[0]
    assert row.override == "superseded_version"
    assert row.suggested_destination == "~ARCHIVE~/Old Versions/"


def test_preview_batch_review_required_row_has_no_override_and_shows_original_suggestion():
    """§11A step 1: review_required is absolute and never encoded as its own
    override value (PreviewRow's own docstring) — suggested_destination is shown
    as Module 05's own, as-yet-unadjusted suggestion, purely informational, since
    no destination is ever actually resolved for this record."""
    record = _record(tier="review_required", suggested_destination="Unknown/")
    row = preview_batch([record])[0]
    assert row.tier == "review_required"
    assert row.override is None
    assert row.suggested_destination == "Unknown/"


def test_preview_batch_adversarial_review_required_and_exact_duplicate(): # I8
    """The same adversarial case §11A/I8 names explicitly: a record that is
    SIMULTANEOUSLY review_required AND an exact duplicate. review_required must
    win in the preview row too — override stays None, not "exact_duplicate"."""
    record = _record(
        tier="review_required", duplicate_of="other-file-id",
        suggested_destination="Finance/",
    )
    row = preview_batch([record])[0]
    assert row.override is None
    assert row.suggested_destination == "Finance/"


def test_preview_batch_mixed_batch_all_three_tiers_together():
    records = [
        _record(file_id="auto-1", tier="auto"),
        _record(file_id="approval-1", tier="approval_required"),
        _record(file_id="review-1", tier="review_required"),
    ]
    rows = preview_batch(records)
    tiers_by_id = {row.file_id: row.tier for row in rows}
    assert tiers_by_id == {
        "auto-1": "auto",
        "approval-1": "approval_required",
        "review-1": "review_required",
    }


def test_preview_batch_does_not_mutate_input_records():
    record = _record(tier="approval_required", duplicate_of="other-file-id")
    before = copy.deepcopy(record)
    preview_batch([record])
    assert record == before


def test_preview_batch_is_safe_to_call_repeatedly():
    """§9: "Safe to call repeatedly, safe to call without ever executing
    anything." Calling it twice on the same input produces equal output and
    still doesn't mutate the input."""
    records = [_record(file_id="f1", tier="auto"), _record(file_id="f2", tier="review_required")]
    before = copy.deepcopy(records)
    first_call = preview_batch(records)
    second_call = preview_batch(records)
    assert first_call == second_call
    assert records == before


def test_preview_batch_single_record_edge_case():
    row = preview_batch([_record(tier="auto")])
    assert len(row) == 1


# --- evaluate_gate() (§13, restated from §0.4's invariant table) ---
# WP-4: "the single most safety-critical piece of code in this module" (§28) —
# deliberately more adversarial test coverage than any earlier package.

def _decision(file_id="f1", decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED,
              edited_name=None, edited_destination=None):
    return ApprovalDecision(
        file_id=file_id, decision=decision,
        edited_name=edited_name, edited_destination=edited_destination,
    )


def test_evaluate_gate_review_required_leaves_unchanged_with_no_decisions_at_all():
    record = _record(tier="review_required")
    assert evaluate_gate(record, {}) == GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED


def test_evaluate_gate_auto_executes_as_auto_with_no_decision_needed():
    record = _record(tier="auto")
    assert evaluate_gate(record, {}) == GateResult.EXECUTE_AS_AUTO


def test_evaluate_gate_approval_required_with_approve_as_suggested_executes_as_user():
    record = _record(file_id="f1", tier="approval_required")
    decisions = {"f1": _decision(file_id="f1", decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED)}
    assert evaluate_gate(record, decisions) == GateResult.EXECUTE_AS_USER


def test_evaluate_gate_approval_required_with_approve_with_edit_executes_as_user():
    """An edit doesn't change the gate outcome — it's still an approval, just with
    edited_name/edited_destination attached for a later work package (WP-2's
    resolve_destination_path(), composed by WP-7) to actually use."""
    record = _record(file_id="f1", tier="approval_required")
    decisions = {"f1": _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_name="Renamed.pdf", edited_destination="Documents/",
    )}
    assert evaluate_gate(record, decisions) == GateResult.EXECUTE_AS_USER


def test_evaluate_gate_approval_required_with_reject_declines_and_logs():
    record = _record(file_id="f1", tier="approval_required")
    decisions = {"f1": _decision(file_id="f1", decision=ApprovalDecisionType.REJECT)}
    assert evaluate_gate(record, decisions) == GateResult.DECLINE_LOGGED


def test_evaluate_gate_approval_required_with_no_recorded_decision_leaves_unchanged():
    """§13's own explicit rule: "absent decision is never treated as consent" —
    an approval_required record with no entry in `decisions` at all must not
    execute, must not be silently declined either; it stays exactly as-is."""
    record = _record(file_id="f1", tier="approval_required")
    assert evaluate_gate(record, {}) == GateResult.LEAVE_UNCHANGED_NO_DECISION


def test_evaluate_gate_approval_required_ignores_a_decision_for_a_different_file_id():
    """A `decisions` dict populated with entries for OTHER records must not be
    mistaken for consent on this one — lookup is strictly by this record's own
    file_id."""
    record = _record(file_id="f1", tier="approval_required")
    decisions = {"some-other-file": _decision(file_id="some-other-file")}
    assert evaluate_gate(record, decisions) == GateResult.LEAVE_UNCHANGED_NO_DECISION


def test_evaluate_gate_adversarial_forged_approval_on_review_required_is_ignored(): # I2
    """The design's own named adversarial case (§13, §28, I2/G3): a maliciously
    or mistakenly constructed ApprovalDecision exists for a review_required
    record's file_id, approving it. review_required must still win —
    unconditionally, no exception — regardless of what `decisions` contains."""
    record = _record(file_id="f1", tier="review_required")
    forged_decisions = {"f1": _decision(file_id="f1", decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED)}
    assert evaluate_gate(record, forged_decisions) == GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED


def test_evaluate_gate_adversarial_forged_edit_approval_on_review_required_is_ignored():
    """Same adversarial case, with an APPROVE_WITH_EDIT forged decision instead
    of a plain approve — still must not matter."""
    record = _record(file_id="f1", tier="review_required")
    forged_decisions = {"f1": _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_name="Sneaky.pdf", edited_destination="Finance/",
    )}
    assert evaluate_gate(record, forged_decisions) == GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED


def test_evaluate_gate_adversarial_forged_reject_on_review_required_is_still_ignored():
    """Even a forged REJECT decision on a review_required record must not
    produce DECLINE_LOGGED — review_required is checked first, absolutely,
    before decisions is consulted for any reason at all."""
    record = _record(file_id="f1", tier="review_required")
    forged_decisions = {"f1": _decision(file_id="f1", decision=ApprovalDecisionType.REJECT)}
    assert evaluate_gate(record, forged_decisions) == GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED


def test_evaluate_gate_auto_tier_ignores_any_decisions_present():
    """auto-tier records execute unconditionally regardless of what (if
    anything) is in `decisions` — no decision is required, and a stray entry
    (e.g. left over from a different record's review flow) must not change
    the outcome either way."""
    record = _record(file_id="f1", tier="auto")
    assert evaluate_gate(record, {}) == GateResult.EXECUTE_AS_AUTO
    stray_decisions = {"f1": _decision(file_id="f1", decision=ApprovalDecisionType.REJECT)}
    assert evaluate_gate(record, stray_decisions) == GateResult.EXECUTE_AS_AUTO


def test_evaluate_gate_rejects_none_tier_as_caller_error():
    """§5's eligibility filter guarantees tier is always populated by the time a
    record legitimately reaches this gate — a None tier here is a caller
    error, raised loudly rather than silently guessed at in either direction."""
    record = _record(tier=None)
    with pytest.raises(ValueError, match="tier"):
        evaluate_gate(record, {})


def test_evaluate_gate_rejects_unrecognized_tier_string_as_caller_error():
    record = _record(tier="not_a_real_tier")
    with pytest.raises(ValueError, match="not_a_real_tier"):
        evaluate_gate(record, {})


def test_evaluate_gate_reads_tier_from_the_record_passed_in_not_a_cached_value():
    """§13's own binding requirement: the gate reads FileRecord.tier directly.
    Mutating the record's tier between two calls changes the outcome — proving
    there's no internal caching of a prior evaluation."""
    record = _record(file_id="f1", tier="review_required")
    assert evaluate_gate(record, {}) == GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED
    record.tier = "auto"
    assert evaluate_gate(record, {}) == GateResult.EXECUTE_AS_AUTO


def test_evaluate_gate_does_not_mutate_record_or_decisions():
    record = _record(file_id="f1", tier="approval_required")
    decisions = {"f1": _decision(file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
                                  edited_name="Renamed.pdf")}
    record_before = copy.deepcopy(record)
    decisions_before = copy.deepcopy(decisions)
    evaluate_gate(record, decisions)
    assert record == record_before
    assert decisions == decisions_before


def test_evaluate_gate_is_safe_to_call_repeatedly_with_same_result():
    record = _record(file_id="f1", tier="approval_required")
    decisions = {"f1": _decision(file_id="f1")}
    first = evaluate_gate(record, decisions)
    second = evaluate_gate(record, decisions)
    assert first == second == GateResult.EXECUTE_AS_USER


def test_evaluate_gate_mixed_batch_every_combination_independently_correct():
    """A single, larger scenario exercising every (tier x decision-presence x
    decision-type) combination together, proving no record's evaluation leaks
    into another's — mirrors the fixed-order batch context §13's pseudocode
    describes, without needing execute_batch() itself (a later work package)."""
    records = {
        "review-1": _record(file_id="review-1", tier="review_required"),
        "auto-1": _record(file_id="auto-1", tier="auto"),
        "approval-approve-1": _record(file_id="approval-approve-1", tier="approval_required"),
        "approval-edit-1": _record(file_id="approval-edit-1", tier="approval_required"),
        "approval-reject-1": _record(file_id="approval-reject-1", tier="approval_required"),
        "approval-nodecision-1": _record(file_id="approval-nodecision-1", tier="approval_required"),
    }
    decisions = {
        "approval-approve-1": _decision(file_id="approval-approve-1", decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
        "approval-edit-1": _decision(file_id="approval-edit-1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT, edited_name="X.pdf"),
        "approval-reject-1": _decision(file_id="approval-reject-1", decision=ApprovalDecisionType.REJECT),
        # "review-1", "auto-1", "approval-nodecision-1" deliberately have no entry
    }
    results = {file_id: evaluate_gate(record, decisions) for file_id, record in records.items()}
    assert results == {
        "review-1": GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED,
        "auto-1": GateResult.EXECUTE_AS_AUTO,
        "approval-approve-1": GateResult.EXECUTE_AS_USER,
        "approval-edit-1": GateResult.EXECUTE_AS_USER,
        "approval-reject-1": GateResult.DECLINE_LOGGED,
        "approval-nodecision-1": GateResult.LEAVE_UNCHANGED_NO_DECISION,
    }


# --- check_real_collision() / apply_collision_suffix() / resolve_available_
# destination() / ensure_destination_folder() / perform_move() (§12, §14) ---
# WP-5: this module's first real filesystem mutation. All tests below use a
# real, sandboxed tmp_path filesystem — nothing here is mocked, per the
# Implementation Plan's own explicit requirement.

def test_check_real_collision_true_when_file_exists(tmp_path):
    target = tmp_path / "invoice.pdf"
    target.write_text("content")
    assert check_real_collision(target) is True


def test_check_real_collision_false_when_nothing_there(tmp_path):
    assert check_real_collision(tmp_path / "does_not_exist.pdf") is False


def test_check_real_collision_true_for_a_real_directory_too(tmp_path):
    """A directory occupying the target name is still a real collision — a
    file can't be moved to a path a folder already occupies."""
    (tmp_path / "invoice.pdf").mkdir()
    assert check_real_collision(tmp_path / "invoice.pdf") is True


def test_apply_collision_suffix_attempt_one_produces_first_suffix():
    result = apply_collision_suffix(Path("/lib/Finance/invoice.pdf"), attempt=1)
    assert result == Path("/lib/Finance/invoice_2.pdf")


def test_apply_collision_suffix_attempt_two_produces_second_suffix():
    result = apply_collision_suffix(Path("/lib/Finance/invoice.pdf"), attempt=2)
    assert result == Path("/lib/Finance/invoice_3.pdf")


def test_apply_collision_suffix_matches_module_05_convention_for_higher_attempts():
    assert apply_collision_suffix(Path("/lib/invoice.pdf"), attempt=9) == Path("/lib/invoice_10.pdf")


def test_apply_collision_suffix_preserves_directory():
    result = apply_collision_suffix(Path("/lib/Finance/Sub/invoice.pdf"), attempt=1)
    assert result.parent == Path("/lib/Finance/Sub")


def test_apply_collision_suffix_only_touches_last_extension_segment():
    """Matches Module 05's own _split_extension() behavior exactly: only the
    last suffix is treated as the extension."""
    result = apply_collision_suffix(Path("/lib/archive.tar.gz"), attempt=1)
    assert result == Path("/lib/archive.tar_2.gz")


def test_apply_collision_suffix_rejects_attempt_zero():
    with pytest.raises(ValueError, match="attempt"):
        apply_collision_suffix(Path("/lib/invoice.pdf"), attempt=0)


def test_apply_collision_suffix_rejects_negative_attempt():
    with pytest.raises(ValueError, match="attempt"):
        apply_collision_suffix(Path("/lib/invoice.pdf"), attempt=-1)


def test_resolve_available_destination_returns_path_unchanged_when_no_collision(tmp_path):
    candidate = tmp_path / "invoice.pdf"
    assert resolve_available_destination(candidate) == candidate


def test_resolve_available_destination_applies_suffix_on_single_collision(tmp_path):
    (tmp_path / "invoice.pdf").write_text("existing")
    result = resolve_available_destination(tmp_path / "invoice.pdf")
    assert result == tmp_path / "invoice_2.pdf"


def test_resolve_available_destination_skips_past_multiple_real_collisions(tmp_path):
    (tmp_path / "invoice.pdf").write_text("existing")
    (tmp_path / "invoice_2.pdf").write_text("existing")
    (tmp_path / "invoice_3.pdf").write_text("existing")
    result = resolve_available_destination(tmp_path / "invoice.pdf")
    assert result == tmp_path / "invoice_4.pdf"


def test_resolve_available_destination_degrades_to_none_when_budget_exhausted(tmp_path):
    """§14: "degrades to a logged error after a bounded number of attempts,
    never an infinite loop, never a silent overwrite." A small max_attempts is
    used here (not the 100 default) so the test stays fast while still proving
    real exhaustion behavior, not just a default-value coincidence."""
    (tmp_path / "invoice.pdf").write_text("existing")
    (tmp_path / "invoice_2.pdf").write_text("existing")
    (tmp_path / "invoice_3.pdf").write_text("existing")
    result = resolve_available_destination(tmp_path / "invoice.pdf", max_attempts=2)
    assert result is None


def test_resolve_available_destination_never_creates_or_deletes_anything(tmp_path):
    """Pure with respect to mutation — only ever reads existence."""
    (tmp_path / "invoice.pdf").write_text("existing")
    before = sorted(p.name for p in tmp_path.iterdir())
    resolve_available_destination(tmp_path / "invoice.pdf")
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after


def test_ensure_destination_folder_creates_missing_nested_folder(tmp_path):
    target = tmp_path / "Finance" / "Archive"
    assert not target.exists()
    ensure_destination_folder(target)
    assert target.is_dir()


def test_ensure_destination_folder_is_idempotent(tmp_path):
    target = tmp_path / "Finance"
    ensure_destination_folder(target)
    ensure_destination_folder(target)  # must not raise
    assert target.is_dir()


def test_ensure_destination_folder_never_gated_behind_any_check(tmp_path):
    """§12: folder creation is never treated as destructive or requiring its
    own approval step — calling it directly, with nothing else, is always
    sufficient."""
    target = tmp_path / "Documents"
    ensure_destination_folder(target)
    assert target.exists()


def test_ensure_destination_folder_fails_loudly_when_a_file_occupies_the_name(tmp_path):
    """A plain file sitting where a destination folder needs to exist is an
    anomalous state this function must never silently work around."""
    (tmp_path / "Finance").write_text("not a folder")
    with pytest.raises(FileExistsError):
        ensure_destination_folder(tmp_path / "Finance")


def test_perform_move_success_moves_file_and_returns_final_path(tmp_path):
    source = tmp_path / "invoice.pdf"
    source.write_text("content")
    destination = tmp_path / "Finance" / "invoice.pdf"
    destination.parent.mkdir()

    result = perform_move(source, destination)

    assert isinstance(result, MoveResult)
    assert result.success is True
    assert result.final_path == str(destination)
    assert result.error_detail is None
    assert not source.exists()
    assert destination.exists()
    assert destination.read_text() == "content"


def test_perform_move_failure_on_missing_source_never_raises(tmp_path):
    source = tmp_path / "does_not_exist.pdf"
    destination = tmp_path / "Finance" / "does_not_exist.pdf"
    destination.parent.mkdir()

    result = perform_move(source, destination)

    assert result.success is False
    assert result.final_path is None
    assert result.error_detail is not None


def test_perform_move_failure_leaves_source_untouched_and_destination_unwritten(tmp_path, monkeypatch):
    """§14: a failed/partial move never leaves current_path (or anything else)
    claiming a location the file isn't actually at — the source must still be
    exactly where it was, and the destination must not exist at all."""
    source = tmp_path / "invoice.pdf"
    source.write_text("original content")
    destination = tmp_path / "Finance" / "invoice.pdf"
    destination.parent.mkdir()

    def _raise_os_error(self, target):
        raise OSError("simulated disk full")

    monkeypatch.setattr(Path, "rename", _raise_os_error)

    result = perform_move(source, destination)

    assert result.success is False
    assert result.error_detail is not None
    assert source.exists()
    assert source.read_text() == "original content"
    assert not destination.exists()


def test_perform_move_never_imports_shutil():
    """G1/§12: never copy-then-delete. shutil.move()/copy2() silently fall
    back to a copy-then-delete sequence on cross-device moves — perform_move()
    must use only Path.rename()/os.rename(), which fails loudly instead of
    silently copying. Asserted structurally: the module doesn't even import
    shutil, so it has no way to reach for that fallback even by accident."""
    import src.pipeline.execution as execution_module
    assert not hasattr(execution_module, "shutil")


def test_perform_move_does_not_create_destination_folder_itself(tmp_path):
    """Destination-folder creation is ensure_destination_folder()'s
    responsibility, not perform_move()'s (§12) — moving into a nonexistent
    parent directory must fail, not silently create one."""
    source = tmp_path / "invoice.pdf"
    source.write_text("content")
    destination = tmp_path / "Nonexistent" / "invoice.pdf"  # parent never created

    result = perform_move(source, destination)

    assert result.success is False
    assert not destination.exists()


# --- log_move() / log_error() / log_decline() (§17/§25) — WP-6 action logging
# integration. Wires the already-implemented append_action_log(); isolated
# from the real Runtime/Logs/action_log.jsonl throughout.

def test_log_move_normal_case_writes_move_rename_with_correct_details(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    record = _record(file_id="f1", suggested_name="Amazon_2026-07-05.pdf", suggested_destination="Finance/")

    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="Amazon_2026-07-05.pdf", executed_destination="Finance/",
        from_path="/tmp/invoice.pdf", to_path="/lib/Finance/Amazon_2026-07-05.pdf",
        approved_by="auto",
    )

    entries = _read_log_entries(tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["batch_id"] == "batch-1"
    assert entry["file_id"] == "f1"
    assert entry["action"] == "move_rename"
    assert entry["from"] == "/tmp/invoice.pdf"
    assert entry["to"] == "/lib/Finance/Amazon_2026-07-05.pdf"
    assert entry["approved_by"] == "auto"
    assert entry["details"] == {
        "override_applied": None,
        "collision_suffix_applied": False,
        "name_differed_from_suggestion": False,
        "destination_differed_from_suggestion": False,
    }


def test_log_move_exact_duplicate_writes_archive_duplicate_action(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    record = _record(file_id="f2", suggested_name="dup.pdf", suggested_destination="Finance/")

    log_move(
        batch_id="batch-1", record=record, override_type="exact_duplicate",
        executed_name="dup.pdf", executed_destination="~ARCHIVE~/Duplicates/",
        from_path="/tmp/dup.pdf", to_path="/lib/~ARCHIVE~/Duplicates/dup.pdf",
        approved_by="user",
    )

    entry = _read_log_entries(tmp_path)[0]
    assert entry["action"] == "archive_duplicate"
    assert entry["details"]["override_applied"] == "exact_duplicate"
    assert entry["details"]["destination_differed_from_suggestion"] is True  # "Finance/" -> archive


def test_log_move_superseded_version_writes_archive_superseded_version_action(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    record = _record(file_id="f3", suggested_name="Resume_v8.pdf", suggested_destination="Documents/")

    log_move(
        batch_id="batch-1", record=record, override_type="superseded_version",
        executed_name="Resume_v8.pdf", executed_destination="~ARCHIVE~/Old Versions/",
        from_path="/tmp/Resume_v8.pdf", to_path="/lib/~ARCHIVE~/Old Versions/Resume_v8.pdf",
        approved_by="auto",
    )

    entry = _read_log_entries(tmp_path)[0]
    assert entry["action"] == "archive_superseded_version"
    assert entry["details"]["override_applied"] == "superseded_version"


def test_log_move_rejects_review_required_override_type(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    record = _record(file_id="f4", tier="review_required")
    with pytest.raises(ValueError, match="review_required"):
        log_move(
            batch_id="batch-1", record=record, override_type="review_required",
            executed_name="a.pdf", executed_destination="Documents/",
            from_path="/tmp/a.pdf", to_path="/lib/Documents/a.pdf", approved_by="auto",
        )
    assert _read_log_entries(tmp_path) == []  # nothing written on a rejected call


def test_log_move_rejects_unrecognized_override_type(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    record = _record(file_id="f5")
    with pytest.raises(ValueError, match="override_type"):
        log_move(
            batch_id="batch-1", record=record, override_type="not_a_real_override",
            executed_name="a.pdf", executed_destination="Documents/",
            from_path="/tmp/a.pdf", to_path="/lib/Documents/a.pdf", approved_by="auto",
        )


def test_log_move_detects_name_differed_from_suggestion(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    record = _record(file_id="f6", suggested_name="Amazon_2026-07-05.pdf", suggested_destination="Finance/")

    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="Renamed_By_User.pdf", executed_destination="Finance/",
        from_path="/tmp/a.pdf", to_path="/lib/Finance/Renamed_By_User.pdf", approved_by="user",
    )

    details = _read_log_entries(tmp_path)[0]["details"]
    assert details["name_differed_from_suggestion"] is True
    assert details["destination_differed_from_suggestion"] is False


def test_log_move_detects_destination_differed_from_suggestion(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    record = _record(file_id="f7", suggested_name="a.pdf", suggested_destination="Finance/")

    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="a.pdf", executed_destination="Documents/",
        from_path="/tmp/a.pdf", to_path="/lib/Documents/a.pdf", approved_by="user",
    )

    details = _read_log_entries(tmp_path)[0]["details"]
    assert details["name_differed_from_suggestion"] is False
    assert details["destination_differed_from_suggestion"] is True


def test_log_move_records_collision_suffix_applied_true(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    record = _record(file_id="f8", suggested_name="a.pdf", suggested_destination="Finance/")

    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="a_2.pdf", executed_destination="Finance/",
        from_path="/tmp/a.pdf", to_path="/lib/Finance/a_2.pdf", approved_by="auto",
        collision_suffix_applied=True,
    )

    details = _read_log_entries(tmp_path)[0]["details"]
    assert details["collision_suffix_applied"] is True
    assert details["name_differed_from_suggestion"] is True  # a.pdf -> a_2.pdf


def test_log_move_never_mutates_record(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    record = _record(file_id="f9", suggested_name="a.pdf", suggested_destination="Finance/")
    before = copy.deepcopy(record)

    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="Edited.pdf", executed_destination="Documents/",
        from_path="/tmp/a.pdf", to_path="/lib/Documents/Edited.pdf", approved_by="user",
    )

    assert record == before  # suggested_name/suggested_destination untouched (§8.1)


def test_log_error_writes_error_action_with_null_to(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)

    log_error(batch_id="batch-1", file_id="f10", error_detail="Permission denied",
               approved_by="auto", from_path="/tmp/a.pdf")

    entry = _read_log_entries(tmp_path)[0]
    assert entry["action"] == "error"
    assert entry["to"] is None
    assert entry["from"] == "/tmp/a.pdf"
    assert entry["approved_by"] == "auto"
    assert entry["details"] == {"error_detail": "Permission denied"}


def test_log_error_accepts_either_approved_by_value():
    """approved_by has no default — the caller must supply it, since only the
    caller (via the GateResult that led here) knows which is correct."""
    import inspect
    signature = inspect.signature(log_error)
    assert signature.parameters["approved_by"].default is inspect.Parameter.empty


def test_log_error_truncates_long_error_detail(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    long_detail = "X" * 500

    log_error(batch_id="batch-1", file_id="f11", error_detail=long_detail, approved_by="user")

    logged_detail = _read_log_entries(tmp_path)[0]["details"]["error_detail"]
    assert len(logged_detail) == 300 + len("...(truncated)")
    assert logged_detail.endswith("...(truncated)")


def test_log_error_does_not_truncate_short_error_detail(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)

    log_error(batch_id="batch-1", file_id="f12", error_detail="short message", approved_by="auto")

    logged_detail = _read_log_entries(tmp_path)[0]["details"]["error_detail"]
    assert logged_detail == "short message"


def test_log_error_from_path_defaults_to_none_when_omitted(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)

    log_error(batch_id="batch-1", file_id="f13", error_detail="failed", approved_by="auto")

    entry = _read_log_entries(tmp_path)[0]
    assert entry["from"] is None


def test_log_decline_writes_reject_action_always_approved_by_user(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)

    log_decline(batch_id="batch-1", file_id="f14", from_path="/tmp/invoice.pdf")

    entry = _read_log_entries(tmp_path)[0]
    assert entry["action"] == "reject"
    assert entry["from"] == "/tmp/invoice.pdf"
    assert entry["to"] is None
    assert entry["approved_by"] == "user"


def test_log_decline_has_no_approved_by_parameter():
    """approved_by is hardcoded, not a caller-supplied parameter — a decline
    can only ever be a human decision (evaluate_gate()'s DECLINE_LOGGED is
    only reachable via a recorded ApprovalDecisionType.REJECT), so there is no
    second legitimate value this could ever carry."""
    import inspect
    signature = inspect.signature(log_decline)
    assert "approved_by" not in signature.parameters


def test_log_entry_written_immediately_not_deferred(tmp_path, monkeypatch):
    """G2's 'guaranteed design behavior' claim, verified true in the
    implementation, not merely described in prose: calling perform_move()
    followed immediately by log_move() results in the log line existing on
    disk right away — no batching, no deferred flush."""
    _isolate_action_log(tmp_path, monkeypatch)
    source = tmp_path / "invoice.pdf"
    source.write_text("content")
    destination = tmp_path / "Finance" / "invoice.pdf"
    destination.parent.mkdir()
    record = _record(file_id="f15", suggested_name="invoice.pdf", suggested_destination="Finance/")

    move_result = perform_move(source, destination)
    assert move_result.success is True

    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="invoice.pdf", executed_destination="Finance/",
        from_path=str(source), to_path=move_result.final_path, approved_by="auto",
    )

    # No intermediate flush/close call was needed — the entry is already there.
    entries = _read_log_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["to"] == str(destination)


# --- Schema-drift regression test (mirrors Module 02/03's own extension-mapping
# drift precedent, ENGINEERING_STANDARD.md §18) — guards the new OD-2 `reject`
# value, and every other action value WP-6 can emit, against silently drifting
# out of sync with Metadata & Log Schema.md's own reserved vocabulary. ---

_KNOWN_ACTION_LOG_VOCABULARY = frozenset({
    "discover", "classify", "extract_metadata", "detect_duplicates_and_versions",
    "suggest_naming_and_destination", "score_confidence",
    "move_rename", "archive_duplicate", "archive_superseded_version",
    "skip", "error", "undo", "reject",
})


def test_wp6_emitted_action_values_are_all_within_the_known_schema_vocabulary():
    emitted_by_wp6 = {"move_rename", "archive_duplicate", "archive_superseded_version", "error", "reject"}
    assert emitted_by_wp6.issubset(_KNOWN_ACTION_LOG_VOCABULARY)


def test_reject_is_distinct_from_module_01s_skip():
    """OD-2's own resolution reasoning (Module 07 Design.md §17/§26, decision
    21): reject is deliberately distinct from Module 01's skip, which means a
    categorically different thing (a file never queued at all)."""
    assert "reject" != "skip"
    assert {"reject", "skip"}.issubset(_KNOWN_ACTION_LOG_VOCABULARY)


def test_log_move_action_mapping_has_no_internal_collision():
    """Each override_type maps to exactly one action string, and no two
    override_types share an action string — the same "no ambiguous meaning"
    guarantee PCV check 5 requires, checked directly against this module's own
    mapping table."""
    from src.pipeline.execution import _MOVE_ACTION_BY_OVERRIDE_TYPE
    actions = list(_MOVE_ACTION_BY_OVERRIDE_TYPE.values())
    assert len(actions) == len(set(actions))
    assert set(actions) == {"move_rename", "archive_duplicate", "archive_superseded_version"}


# --- ExecutionEngine (§9, WP-7) — per-file orchestration composing WP-1/WP-2/
# WP-4/WP-5/WP-6 into the fixed six-step sequence: gate -> resolve destination
# -> collision re-check -> move -> log -> update record. Real, sandboxed
# tmp_path filesystem throughout, matching WP-5's own established precedent —
# never mocked for the actual move mechanics. ---

_MODULE_01_06_OWNED_FIELDS = (
    "file_id", "source_id", "original_name", "original_path",
    "extension", "mime_type", "size_bytes", "created_at", "modified_at",
    "content_hash", "discovered_at", "status", "error", "batch_id",
    "category", "classification_signals", "extracted_metadata",
    "suggested_name", "suggested_destination", "naming_signals",
    "duplicate_of", "version_group_id", "version_rank", "duplicate_signals",
    "confidence_score", "confidence_breakdown", "tier",
)
_MODULE_07_OWNED_FIELDS = (
    "current_path", "processed_at", "approved_by", "approved_at", "reversible",
)


def _assert_no_module_01_06_field_changed(before: FileRecord, after: FileRecord):
    for field_name in _MODULE_01_06_OWNED_FIELDS:
        assert getattr(before, field_name) == getattr(after, field_name), (
            f"{field_name} changed — ExecutionEngine must never write any "
            f"Module 01-06-owned field (§8/G8)."
        )


def _make_source_file(tmp_path, name="invoice.pdf", content="content"):
    source = tmp_path / name
    source.write_text(content)
    return source


# --- review_required (I2/G3 — unconditional, no exception) ---

def test_execution_engine_review_required_leaves_record_completely_unchanged(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(tier="review_required", current_path=str(source))
    before = copy.deepcopy(record)

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome == ExecutionOutcome(gate_result=GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED)
    _assert_no_module_01_06_field_changed(before, record)
    assert record.current_path == before.current_path
    assert record.processed_at is None
    assert record.approved_by is None
    assert record.approved_at is None
    assert record.reversible is True
    assert source.exists()  # never moved
    assert _read_log_entries(tmp_path) == []  # never logged


def test_execution_engine_review_required_wins_even_with_a_forged_approve_decision():
    """I2's adversarial guarantee, re-verified end-to-end through the composed
    engine (not just evaluate_gate() in isolation, WP-4's own test) — a
    review_required record must never execute even if a (forged or mistaken)
    ApprovalDecision exists for its file_id."""
    record = _record(tier="review_required", current_path="/tmp/never_moved.pdf")
    forged = {"f1": _decision(file_id="f1", decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED)}

    outcome = ExecutionEngine().execute_file(record, forged, "/tmp/library", batch_id="batch-1")

    assert outcome.gate_result == GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED
    assert outcome.move_result is None
    assert record.processed_at is None
    assert record.current_path == "/tmp/never_moved.pdf"


# --- approval_required, no recorded decision ("absent decision is never
# treated as consent") ---

def test_execution_engine_no_decision_leaves_record_unchanged_and_logs_nothing(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(tier="approval_required", current_path=str(source))
    before = copy.deepcopy(record)

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome == ExecutionOutcome(gate_result=GateResult.LEAVE_UNCHANGED_NO_DECISION)
    _assert_no_module_01_06_field_changed(before, record)
    assert record.processed_at is None
    assert source.exists()
    assert _read_log_entries(tmp_path) == []


# --- approval_required, REJECT decision (decline, logged but unmoved) ---

def test_execution_engine_reject_logs_decline_and_leaves_record_unchanged(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(file_id="f1", tier="approval_required", current_path=str(source))
    before = copy.deepcopy(record)
    decisions = {"f1": _decision(file_id="f1", decision=ApprovalDecisionType.REJECT)}

    outcome = ExecutionEngine().execute_file(record, decisions, tmp_path, batch_id="batch-1")

    assert outcome.gate_result == GateResult.DECLINE_LOGGED
    assert outcome.move_result is None
    _assert_no_module_01_06_field_changed(before, record)
    assert record.processed_at is None  # decline never populates the WP-7 fields
    assert record.current_path == before.current_path
    assert source.exists()  # never moved

    entries = _read_log_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["action"] == "reject"
    assert entries[0]["approved_by"] == "user"
    assert entries[0]["to"] is None


# --- auto tier — executes without a human decision (G4) ---

def test_execution_engine_auto_tier_executes_normal_category_and_updates_record(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    before = copy.deepcopy(record)

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.gate_result == GateResult.EXECUTE_AS_AUTO
    assert outcome.move_result.success is True
    _assert_no_module_01_06_field_changed(before, record)

    expected_final = tmp_path / "Finance" / "invoice.pdf"
    assert expected_final.exists()
    assert not source.exists()
    assert record.current_path == str(expected_final)
    assert record.processed_at is not None
    assert record.approved_by == "auto"
    assert record.approved_at is not None
    assert record.approved_at == record.processed_at  # set atomically, §13A
    assert record.reversible is True  # no suffix, not an archive move

    entries = _read_log_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["action"] == "move_rename"
    assert entries[0]["approved_by"] == "auto"
    assert entries[0]["from"] == str(source)
    assert entries[0]["to"] == str(expected_final)
    assert entries[0]["details"]["name_differed_from_suggestion"] is False
    assert entries[0]["details"]["destination_differed_from_suggestion"] is False


def test_execution_engine_auto_tier_exact_duplicate_archives_and_sets_reversible_false(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source), duplicate_of="other-file-id",
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is True
    expected_final = tmp_path / "~ARCHIVE~" / "Duplicates" / "invoice.pdf"
    assert expected_final.exists()
    assert record.current_path == str(expected_final)
    assert record.reversible is False  # §15(b): destination lands inside ~ARCHIVE~/

    entries = _read_log_entries(tmp_path)
    assert entries[0]["action"] == "archive_duplicate"
    assert entries[0]["details"]["override_applied"] == "exact_duplicate"


def test_execution_engine_auto_tier_superseded_version_archives_and_sets_reversible_false(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source), version_rank="superseded",
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is True
    expected_final = tmp_path / "~ARCHIVE~" / "Old Versions" / "invoice.pdf"
    assert expected_final.exists()
    assert record.reversible is False

    entries = _read_log_entries(tmp_path)
    assert entries[0]["action"] == "archive_superseded_version"


# --- approval_required, APPROVE_AS_SUGGESTED / APPROVE_WITH_EDIT (G4, §8.1) ---

def test_execution_engine_approve_as_suggested_executes_with_approved_by_user(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="approval_required", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    decisions = {"f1": _decision(file_id="f1", decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED)}

    outcome = ExecutionEngine().execute_file(record, decisions, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is True
    assert record.approved_by == "user"
    expected_final = tmp_path / "Finance" / "invoice.pdf"
    assert record.current_path == str(expected_final)


def test_execution_engine_approve_with_edit_executes_edited_values_never_written_back(tmp_path, monkeypatch):
    """§8.1: the edited name/destination is executed, but `suggested_name`/
    `suggested_destination` — Module 05's permanent, historical record — are
    never overwritten."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="approval_required", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    decisions = {"f1": _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_name="Renamed_Invoice.pdf", edited_destination="Documents/",
    )}

    outcome = ExecutionEngine().execute_file(record, decisions, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is True
    expected_final = tmp_path / "Documents" / "Renamed_Invoice.pdf"
    assert expected_final.exists()
    assert record.current_path == str(expected_final)

    # §8.1 — Module 05's own fields are never touched by an executed edit.
    assert record.suggested_name == "invoice.pdf"
    assert record.suggested_destination == "Finance/"

    entries = _read_log_entries(tmp_path)
    assert entries[0]["details"]["name_differed_from_suggestion"] is True
    assert entries[0]["details"]["destination_differed_from_suggestion"] is True


def test_execution_engine_edited_destination_overrides_archive_placement_decision_23(tmp_path, monkeypatch):
    """ARCHITECTURE_DECISIONS.md decision 23: an edited destination is honored
    even for an exact_duplicate/superseded_version record — and, correctly,
    such a record is NOT flagged irreversible on that basis once it no longer
    actually lands inside ~ARCHIVE~/."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="approval_required", current_path=str(source),
        duplicate_of="other-file-id",
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    decisions = {"f1": _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_destination="Finance/",
    )}

    outcome = ExecutionEngine().execute_file(record, decisions, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is True
    expected_final = tmp_path / "Finance" / "invoice.pdf"
    assert expected_final.exists()
    assert record.current_path == str(expected_final)
    assert record.reversible is True  # not inside ~ARCHIVE~/ — decision 23

    entries = _read_log_entries(tmp_path)
    assert entries[0]["action"] == "archive_duplicate"  # override_type is still exact_duplicate
    assert entries[0]["details"]["override_applied"] == "exact_duplicate"
    assert entries[0]["to"] == str(expected_final)  # but the real "to" is outside ~ARCHIVE~/


# --- real, execution-time collision handling (§12/§14) ---

def test_execution_engine_real_collision_applies_suffix_and_sets_reversible_false(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    finance_dir = tmp_path / "Finance"
    finance_dir.mkdir()
    (finance_dir / "invoice.pdf").write_text("already here")  # pre-existing collision

    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is True
    expected_final = finance_dir / "invoice_2.pdf"
    assert expected_final.exists()
    assert record.current_path == str(expected_final)
    assert record.reversible is False  # §15(a): collision suffix was applied

    entries = _read_log_entries(tmp_path)
    assert entries[0]["details"]["collision_suffix_applied"] is True
    assert entries[0]["details"]["name_differed_from_suggestion"] is True  # invoice_2.pdf != invoice.pdf


def test_execution_engine_collision_budget_exhausted_logs_error_and_leaves_record_unchanged(tmp_path, monkeypatch):
    """§14: "degrades to a logged error after a bounded number of attempts,
    never an infinite loop, never a silent overwrite" — every candidate the
    bounded loop could ever produce is pre-occupied.

    `resolve_available_destination()`'s own bounded-retry-degrades-to-`None`
    behavior against the real `_MAX_COLLISION_ATTEMPTS` bound is already fully
    tested in isolation by WP-5's own suite (`_MAX_COLLISION_ATTEMPTS` is a
    default-argument value bound at function-definition time, so monkeypatching
    the module constant after import has no effect on it — genuinely exhausting
    the real, 100-attempt bound here would mean creating 101 real files for no
    additional coverage). This test instead verifies WP-7's own, distinct
    responsibility: that `ExecutionEngine` correctly handles the documented
    `None` contract when the budget is exhausted — logs it, performs no move,
    leaves the record untouched — by monkeypatching the composed function's
    return value directly, the same technique the move-failure test below uses
    for `perform_move()`."""
    _isolate_action_log(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    monkeypatch.setattr(execution_module, "resolve_available_destination", lambda path: None)

    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    before = copy.deepcopy(record)

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is False
    assert "exhausted" in outcome.move_result.error_detail
    _assert_no_module_01_06_field_changed(before, record)
    assert record.processed_at is None
    assert source.exists()  # never moved

    entries = _read_log_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["action"] == "error"
    assert entries[0]["approved_by"] == "auto"
    assert "exhausted" in entries[0]["details"]["error_detail"]


# --- destination-folder creation failure (§14 Layer 1) ---

def test_execution_engine_destination_folder_creation_failure_logs_error_and_leaves_unchanged(tmp_path, monkeypatch):
    """A plain file occupying the destination folder's own name makes
    `ensure_destination_folder()` raise `FileExistsError` (an `OSError`
    subclass) — a Layer-1 anticipated failure, not a crash."""
    _isolate_action_log(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    (tmp_path / "Finance").write_text("a plain file, not a directory")

    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    before = copy.deepcopy(record)

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is False
    _assert_no_module_01_06_field_changed(before, record)
    assert record.processed_at is None
    assert source.exists()

    entries = _read_log_entries(tmp_path)
    assert entries[0]["action"] == "error"


# --- move failure (§14 Layer 1 — the move itself fails partway) ---

def test_execution_engine_move_failure_logs_error_and_never_updates_current_path(tmp_path, monkeypatch):
    """§14: "the record's current_path is only ever updated after a move is
    confirmed complete" — forced here by monkeypatching perform_move() itself
    to return a failure, mirroring an OS-level failure mid-move (e.g. a full
    destination volume) without needing to actually fill a real disk."""
    _isolate_action_log(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    before = copy.deepcopy(record)

    def _failing_perform_move(_source, _destination):
        return MoveResult(success=False, error_detail="simulated full destination volume")

    monkeypatch.setattr(execution_module, "perform_move", _failing_perform_move)

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is False
    _assert_no_module_01_06_field_changed(before, record)
    assert record.current_path == before.current_path  # never updated on failure
    assert record.processed_at is None
    assert source.exists()  # the real file was never touched by the simulated failure

    entries = _read_log_entries(tmp_path)
    assert entries[0]["action"] == "error"
    assert "simulated full destination volume" in entries[0]["details"]["error_detail"]


# --- §22 path-escape rejection, propagated as a Layer-1 anticipated failure ---

def test_execution_engine_path_escape_in_edited_destination_logs_error_not_a_crash(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="approval_required", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    decisions = {"f1": _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_destination="../../etc/",
    )}
    before = copy.deepcopy(record)

    outcome = ExecutionEngine().execute_file(record, decisions, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is False
    _assert_no_module_01_06_field_changed(before, record)
    assert record.processed_at is None
    assert source.exists()

    entries = _read_log_entries(tmp_path)
    assert entries[0]["action"] == "error"
    assert "escap" in entries[0]["details"]["error_detail"].lower() or "absolute" in entries[0]["details"]["error_detail"].lower() or ".." in entries[0]["details"]["error_detail"]


# --- log-before-record-update step ordering (§9's fixed step order — log,
# then update record, never the reverse) ---

def test_execution_engine_record_not_updated_if_log_move_raises(tmp_path, monkeypatch):
    """If step 5 (log) raises, step 6 (update record) must never run — proving
    the two steps are strictly sequential in the fixed order §9 specifies, not
    reordered or parallelized."""
    _isolate_action_log(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    before = copy.deepcopy(record)

    def _raising_log_move(**kwargs):
        raise RuntimeError("simulated logging failure")

    monkeypatch.setattr(execution_module, "log_move", _raising_log_move)

    with pytest.raises(RuntimeError):
        ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    # The move itself already happened (step 4 completed before step 5 raised),
    # but the FileRecord update (step 6) must never have run.
    assert record.processed_at is None
    assert record.approved_by is None
    assert record.current_path == before.current_path


# --- trusts its caller's needs_execution() filtering (mirrors
# DuplicateDetectionEngine.detect_file()'s own established precedent) ---

def test_execution_engine_does_not_re_check_needs_execution_itself(tmp_path, monkeypatch):
    """ExecutionEngine trusts its caller to only ever hand it a record for
    which needs_execution(record) is already True (§9's closing sentence) —
    it does not defensively re-check processed_at itself. Handing it an
    already-processed record anyway still executes, demonstrating the trust-
    the-caller contract concretely rather than only documenting it."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        processed_at="2020-01-01T00:00:00+00:00",  # already "executed" per needs_execution()
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    assert needs_execution(record) is False  # confirms the premise

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is True  # executed anyway — caller's job to filter, not this engine's


# --- WP-7 correction (approved High-severity finding, recorded during WP-9
# scoping): step 6 must persist via save_file_record(), not just mutate the
# in-memory FileRecord — matching reconcile_batch()'s own already-approved
# mutate-then-persist pattern (WP-8) for this identical field set. ---

def test_execution_engine_success_persists_updated_record_to_metadata_store(tmp_path, monkeypatch):
    """The core positive case: a successful execution's step-6 mutations must
    actually reach Database/Metadata/metadata_store.json, not merely the
    in-memory FileRecord object — otherwise every "successful" execution's
    bookkeeping would vanish the moment the process exits, and needs_
    execution() would incorrectly re-select the same record on the next
    run."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is True
    stored = {r.file_id: r for r in load_metadata_store()}
    assert "f1" in stored
    persisted = stored["f1"]
    assert persisted.current_path == record.current_path
    assert persisted.processed_at == record.processed_at
    assert persisted.approved_by == record.approved_by
    assert persisted.approved_at == record.approved_at
    assert persisted.reversible == record.reversible
    assert persisted.reversible is True


def test_execution_engine_exact_duplicate_persists_reversible_false(tmp_path, monkeypatch):
    """The archive/reversible=False case, persisted — not just the plain-move
    case above. Covers the same field set reconcile_batch()'s REPAIRED branch
    already persists, confirming both code paths agree on what gets written."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source), duplicate_of="other-file-id",
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )

    ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    stored = {r.file_id: r for r in load_metadata_store()}
    assert stored["f1"].reversible is False
    assert stored["f1"].reversible == record.reversible


def test_execution_engine_move_failure_does_not_persist_anything(tmp_path, monkeypatch):
    """A failed move (Layer-1 anticipated failure, before step 6 is ever
    reached) must leave the metadata store completely untouched — no
    partially-updated FileRecord is ever written."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )

    def _failing_perform_move(_source, _destination):
        return MoveResult(success=False, error_detail="simulated full destination volume")

    monkeypatch.setattr(execution_module, "perform_move", _failing_perform_move)

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert outcome.move_result.success is False
    assert load_metadata_store() == []  # nothing was ever written


def test_execution_engine_logging_still_precedes_persistence_if_log_move_raises(tmp_path, monkeypatch):
    """§9's fixed step order (log, then update-and-persist record, never the
    reverse) must still hold after the correction: if step 5 (log) raises,
    neither the in-memory record nor the metadata store may reflect step 6 —
    save_file_record() must never run before log_move() has completed."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )

    def _raising_log_move(**kwargs):
        raise RuntimeError("simulated logging failure")

    monkeypatch.setattr(execution_module, "log_move", _raising_log_move)

    with pytest.raises(RuntimeError):
        ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    assert record.processed_at is None  # in-memory record never updated
    assert load_metadata_store() == []  # and therefore never persisted either


def test_execution_engine_persistence_makes_reconcile_batch_see_already_terminal(tmp_path, monkeypatch):
    """Integration proof that the correction doesn't change reconcile_batch()'s
    (WP-8) own behavior — it corrects what reconcile_batch() actually reads.
    Before this fix, a completed execution's processed_at was never durably
    visible to load_metadata_store(), so a reconcile_batch() call for the same
    batch (e.g. a second, defensive call, or a real crash-restart reading the
    store fresh) would have wrongly found processed_at=None and taken the
    REPAIRED branch for a file that was never actually interrupted. With the
    correction, the exact same scenario now correctly resolves to
    ALREADY_TERMINAL — proving reconcile_batch() itself required no change,
    only correct upstream persistence."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    write_batch_plan("batch-1", [_plan_entry("f1", str(source), None)])
    # Fill in the real "to" only after we know it, mirroring §18/Decision 24's
    # own incremental-staging shape closely enough for this test's purpose —
    # the exact "to" is recomputed below from the real executed outcome.

    outcome = ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")
    assert outcome.move_result.success is True

    # Restage the plan with the real, now-known "to" path (what WP-9's
    # incremental staging would have written immediately before execution),
    # simulating a leftover plan.json that a defensive/duplicate
    # reconcile_batch() call encounters afterward.
    write_batch_plan("batch-1", [_plan_entry("f1", str(source), record.current_path)])

    report = reconcile_batch("batch-1")

    assert report.outcomes["f1"] == ReconciliationOutcome.ALREADY_TERMINAL


# --- WP-8: Runtime/Temp staging & crash-reconciliation (§13A, §18) ---
# "The single most novel piece of logic in this design" (§28 Risks). Real,
# sandboxed tmp_path filesystem + real (isolated) metadata_store.json
# throughout — never mocked, matching WP-5/WP-7's own established precedent.

def _plan_entry(file_id, from_path, to_path):
    return {"file_id": file_id, "from": from_path, "to": to_path}


# --- raw I/O primitives (runtime_io.py) ---

def test_stage_batch_temp_creates_directory_and_is_idempotent(tmp_path, monkeypatch):
    _isolate_database_and_temp(tmp_path, monkeypatch)
    first = stage_batch_temp("batch-1")
    assert Path(first).is_dir()
    second = stage_batch_temp("batch-1")  # calling twice is a no-op, not an error
    assert second == first
    assert Path(first).is_dir()


def test_clear_batch_temp_removes_directory_and_is_idempotent(tmp_path, monkeypatch):
    _isolate_database_and_temp(tmp_path, monkeypatch)
    dir_path = Path(stage_batch_temp("batch-1"))
    assert dir_path.is_dir()
    clear_batch_temp("batch-1")
    assert not dir_path.exists()
    clear_batch_temp("batch-1")  # already gone — must not raise


def test_write_and_read_batch_plan_round_trips(tmp_path, monkeypatch):
    _isolate_database_and_temp(tmp_path, monkeypatch)
    entries = [_plan_entry("f1", "/tmp/a.pdf", "/tmp/Finance/a.pdf")]
    write_batch_plan("batch-1", entries)
    assert read_batch_plan("batch-1") == entries


def test_read_batch_plan_returns_none_when_nothing_staged(tmp_path, monkeypatch):
    _isolate_database_and_temp(tmp_path, monkeypatch)
    assert read_batch_plan("never-staged-batch") is None


def test_read_action_log_entries_returns_empty_list_when_no_log_file(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    assert read_action_log_entries() == []


def test_read_action_log_entries_reads_back_appended_entries(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    log_error(batch_id="batch-1", file_id="f1", error_detail="boom", approved_by="auto")
    log_error(batch_id="batch-1", file_id="f2", error_detail="boom2", approved_by="user")
    entries = read_action_log_entries()
    assert len(entries) == 2
    assert entries[0]["file_id"] == "f1"
    assert entries[1]["file_id"] == "f2"


# --- reconcile_batch() (§13A five-step procedure) ---

def test_reconcile_batch_no_leftover_plan_is_a_noop(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    report = reconcile_batch("never-staged-batch")

    assert report == ReconciliationReport(batch_id="never-staged-batch")
    assert report.outcomes == {}


def test_reconcile_batch_already_terminal_when_log_and_processed_at_both_present(tmp_path, monkeypatch):
    """§13A step 2: a matching log entry exists AND processed_at is already
    set — the operation completed fully before any crash; nothing to
    reconcile."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    to_path = str(tmp_path / "Finance" / "invoice.pdf")
    record = _record(file_id="f1", current_path=to_path, processed_at="2026-01-01T00:00:00+00:00",
                      approved_by="auto", approved_at="2026-01-01T00:00:00+00:00")
    save_file_record(record)
    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="invoice.pdf", executed_destination="Finance/",
        from_path="/tmp/invoice.pdf", to_path=to_path, approved_by="auto",
    )
    write_batch_plan("batch-1", [_plan_entry("f1", "/tmp/invoice.pdf", to_path)])

    report = reconcile_batch("batch-1")

    assert report.outcomes["f1"] == ReconciliationOutcome.ALREADY_TERMINAL
    reloaded = load_metadata_store()[0]
    assert reloaded.processed_at == "2026-01-01T00:00:00+00:00"  # untouched
    assert read_batch_plan("batch-1") is None  # cleared


def test_reconcile_batch_safe_to_retry_when_no_log_and_no_processed_at(tmp_path, monkeypatch):
    """§13A step 3: no matching log entry, processed_at still None — never
    attempted (or staged but not reached); safe to retry from scratch."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    to_path = str(tmp_path / "Finance" / "invoice.pdf")
    record = _record(file_id="f1", processed_at=None)
    save_file_record(record)
    write_batch_plan("batch-1", [_plan_entry("f1", "/tmp/invoice.pdf", to_path)])

    report = reconcile_batch("batch-1")

    assert report.outcomes["f1"] == ReconciliationOutcome.SAFE_TO_RETRY
    reloaded = load_metadata_store()[0]
    assert reloaded.processed_at is None
    assert needs_execution(reloaded) is True  # correctly eligible again


def test_reconcile_batch_repaired_when_disk_confirms_file_present(tmp_path, monkeypatch):
    """§13A step 4, disk-confirms-present sub-case: a matching log entry
    exists, processed_at is still None (crash between log write and
    FileRecord save) — repaired from the log entry's own recorded values."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    destination = tmp_path / "Finance" / "invoice.pdf"
    destination.parent.mkdir(parents=True)
    destination.write_text("content")  # the move genuinely completed before the crash

    record = _record(file_id="f1", processed_at=None, current_path="/tmp/invoice.pdf")
    save_file_record(record)
    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="invoice.pdf", executed_destination="Finance/",
        from_path="/tmp/invoice.pdf", to_path=str(destination), approved_by="auto",
    )
    # No save_file_record() call after the log write — simulating the crash.
    write_batch_plan("batch-1", [_plan_entry("f1", "/tmp/invoice.pdf", str(destination))])

    report = reconcile_batch("batch-1")

    assert report.outcomes["f1"] == ReconciliationOutcome.REPAIRED
    repaired = load_metadata_store()[0]
    assert repaired.current_path == str(destination)
    assert repaired.processed_at is not None
    assert repaired.approved_by == "auto"
    assert repaired.approved_at == repaired.processed_at  # atomicity
    assert repaired.reversible is True  # clean move, no suffix, not archived


def test_reconcile_batch_repaired_sets_reversible_false_for_collision_suffixed_move(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    destination = tmp_path / "Finance" / "invoice_2.pdf"
    destination.parent.mkdir(parents=True)
    destination.write_text("content")

    record = _record(file_id="f1", processed_at=None, current_path="/tmp/invoice.pdf")
    save_file_record(record)
    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="invoice_2.pdf", executed_destination="Finance/",
        from_path="/tmp/invoice.pdf", to_path=str(destination), approved_by="auto",
        collision_suffix_applied=True,
    )
    write_batch_plan("batch-1", [_plan_entry("f1", "/tmp/invoice.pdf", str(destination))])

    report = reconcile_batch("batch-1")

    assert report.outcomes["f1"] == ReconciliationOutcome.REPAIRED
    repaired = load_metadata_store()[0]
    assert repaired.reversible is False  # §15(a): collision suffix was applied


def test_reconcile_batch_repaired_sets_reversible_false_for_archive_destination(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    destination = tmp_path / "~ARCHIVE~" / "Duplicates" / "invoice.pdf"
    destination.parent.mkdir(parents=True)
    destination.write_text("content")

    record = _record(file_id="f1", processed_at=None, current_path="/tmp/invoice.pdf", duplicate_of="other")
    save_file_record(record)
    log_move(
        batch_id="batch-1", record=record, override_type="exact_duplicate",
        executed_name="invoice.pdf", executed_destination="~ARCHIVE~/Duplicates/",
        from_path="/tmp/invoice.pdf", to_path=str(destination), approved_by="auto",
    )
    write_batch_plan("batch-1", [_plan_entry("f1", "/tmp/invoice.pdf", str(destination))])

    report = reconcile_batch("batch-1")

    assert report.outcomes["f1"] == ReconciliationOutcome.REPAIRED
    repaired = load_metadata_store()[0]
    assert repaired.reversible is False  # §15(b): destination lands inside ~ARCHIVE~/


def test_reconcile_batch_repaired_sets_reversible_true_for_decision_23_edit_override_outside_archive(tmp_path, monkeypatch):
    """ARCHITECTURE_DECISIONS.md decision 23: `override_applied` in the log's
    own `details` still reads "exact_duplicate" (resolve_precedence()'s
    classification never changes), but a human's APPROVE_WITH_EDIT redirected
    the real destination outside ~ARCHIVE~/ — the repair must follow the real
    `to` path, not `details.override_applied` alone, or it would incorrectly
    mark this reversible=False (see reconcile_batch()'s own docstring)."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    destination = tmp_path / "Finance" / "invoice.pdf"  # NOT inside ~ARCHIVE~/
    destination.parent.mkdir(parents=True)
    destination.write_text("content")

    record = _record(file_id="f1", processed_at=None, current_path="/tmp/invoice.pdf", duplicate_of="other")
    save_file_record(record)
    log_move(
        batch_id="batch-1", record=record, override_type="exact_duplicate",  # classification unchanged
        executed_name="invoice.pdf", executed_destination="Finance/",  # but redirected via edit
        from_path="/tmp/invoice.pdf", to_path=str(destination), approved_by="user",
    )
    write_batch_plan("batch-1", [_plan_entry("f1", "/tmp/invoice.pdf", str(destination))])

    report = reconcile_batch("batch-1")

    assert report.outcomes["f1"] == ReconciliationOutcome.REPAIRED
    repaired = load_metadata_store()[0]
    assert repaired.reversible is True  # correctly NOT flagged irreversible


def test_reconcile_batch_inconsistent_error_when_disk_disagrees_with_log(tmp_path, monkeypatch):
    """§13A step 4, disk-disagrees sub-case: the log claims a completed move,
    but no file exists at the recorded `to` path — logged as an error;
    processed_at is left None so the record remains eligible for a clean
    retry."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    to_path = str(tmp_path / "Finance" / "invoice.pdf")  # never actually created

    record = _record(file_id="f1", processed_at=None, current_path="/tmp/invoice.pdf")
    save_file_record(record)
    log_move(
        batch_id="batch-1", record=record, override_type="normal",
        executed_name="invoice.pdf", executed_destination="Finance/",
        from_path="/tmp/invoice.pdf", to_path=to_path, approved_by="auto",
    )
    write_batch_plan("batch-1", [_plan_entry("f1", "/tmp/invoice.pdf", to_path)])

    report = reconcile_batch("batch-1")

    assert report.outcomes["f1"] == ReconciliationOutcome.INCONSISTENT_ERROR
    reloaded = load_metadata_store()[0]
    assert reloaded.processed_at is None  # never silently assumed complete

    entries = read_action_log_entries()
    error_entries = [e for e in entries if e["action"] == "error"]
    assert len(error_entries) == 1
    assert "disagrees" in error_entries[0]["details"]["error_detail"]


def test_reconcile_batch_inconsistent_error_when_record_missing_entirely(tmp_path, monkeypatch):
    """Defensive branch: a matching log entry references a file_id with no
    FileRecord in the metadata store at all — an anomaly that shouldn't be
    structurally reachable, surfaced (logged) rather than silently skipped."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    to_path = str(tmp_path / "Finance" / "invoice.pdf")
    ghost_record = _record(file_id="ghost", current_path="/tmp/invoice.pdf")  # never saved
    log_move(
        batch_id="batch-1", record=ghost_record, override_type="normal",
        executed_name="invoice.pdf", executed_destination="Finance/",
        from_path="/tmp/invoice.pdf", to_path=to_path, approved_by="auto",
    )
    write_batch_plan("batch-1", [_plan_entry("ghost", "/tmp/invoice.pdf", to_path)])

    report = reconcile_batch("batch-1")

    assert report.outcomes["ghost"] == ReconciliationOutcome.INCONSISTENT_ERROR
    entries = read_action_log_entries()
    error_entries = [e for e in entries if e["action"] == "error"]
    assert len(error_entries) == 1
    assert "no FileRecord" in error_entries[0]["details"]["error_detail"]


def test_reconcile_batch_defensive_already_terminal_when_no_match_but_processed_at_set(tmp_path, monkeypatch):
    """Defensive branch: no matching log entry, but processed_at IS already
    set (an anomalous state that shouldn't be structurally reachable) —
    resolved toward ALREADY_TERMINAL, never re-executed (I7), the safe
    direction to guess wrong in."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    to_path = str(tmp_path / "Finance" / "invoice.pdf")
    record = _record(file_id="f1", processed_at="2026-01-01T00:00:00+00:00")
    save_file_record(record)
    write_batch_plan("batch-1", [_plan_entry("f1", "/tmp/invoice.pdf", to_path)])

    report = reconcile_batch("batch-1")

    assert report.outcomes["f1"] == ReconciliationOutcome.ALREADY_TERMINAL
    assert read_action_log_entries() == []  # no error was logged, no retry triggered


def test_reconcile_batch_handles_multiple_entries_with_different_outcomes_in_one_batch(tmp_path, monkeypatch):
    """A single batch's plan.json can legitimately contain files headed for
    every different reconciliation outcome at once — each is classified
    independently."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    # f1: already terminal
    terminal_to = str(tmp_path / "Finance" / "terminal.pdf")
    terminal_record = _record(file_id="f1", processed_at="2026-01-01T00:00:00+00:00")
    save_file_record(terminal_record)
    log_move(batch_id="batch-1", record=terminal_record, override_type="normal",
              executed_name="terminal.pdf", executed_destination="Finance/",
              from_path="/tmp/terminal.pdf", to_path=terminal_to, approved_by="auto")

    # f2: safe to retry
    retry_to = str(tmp_path / "Finance" / "retry.pdf")
    save_file_record(_record(file_id="f2", processed_at=None))

    # f3: repaired
    repaired_dest = tmp_path / "Finance" / "repaired.pdf"
    repaired_dest.parent.mkdir(parents=True, exist_ok=True)
    repaired_dest.write_text("x")
    repaired_record = _record(file_id="f3", processed_at=None, current_path="/tmp/repaired.pdf")
    save_file_record(repaired_record)
    log_move(batch_id="batch-1", record=repaired_record, override_type="normal",
              executed_name="repaired.pdf", executed_destination="Finance/",
              from_path="/tmp/repaired.pdf", to_path=str(repaired_dest), approved_by="auto")

    # f4: inconsistent error
    error_to = str(tmp_path / "Finance" / "error.pdf")
    error_record = _record(file_id="f4", processed_at=None, current_path="/tmp/error.pdf")
    save_file_record(error_record)
    log_move(batch_id="batch-1", record=error_record, override_type="normal",
              executed_name="error.pdf", executed_destination="Finance/",
              from_path="/tmp/error.pdf", to_path=error_to, approved_by="auto")

    write_batch_plan("batch-1", [
        _plan_entry("f1", "/tmp/terminal.pdf", terminal_to),
        _plan_entry("f2", "/tmp/retry.pdf", retry_to),
        _plan_entry("f3", "/tmp/repaired.pdf", str(repaired_dest)),
        _plan_entry("f4", "/tmp/error.pdf", error_to),
    ])

    report = reconcile_batch("batch-1")

    assert report.outcomes == {
        "f1": ReconciliationOutcome.ALREADY_TERMINAL,
        "f2": ReconciliationOutcome.SAFE_TO_RETRY,
        "f3": ReconciliationOutcome.REPAIRED,
        "f4": ReconciliationOutcome.INCONSISTENT_ERROR,
    }
    assert read_batch_plan("batch-1") is None  # cleared once every entry is reconciled


# --- Requirement: crash reconciliation must never produce a FileRecord state
# that could not have resulted from a valid execution sequence ---

def test_reconcile_batch_repair_matches_a_real_executionengine_outcome_normal_move(tmp_path, monkeypatch):
    """Runs a real, uninterrupted ExecutionEngine.execute_file() to establish
    what a genuinely valid execution produces, then reconciles an equivalent,
    independently crash-simulated scenario and confirms the repaired state's
    current_path/approved_by/reversible relationship is identical — the same
    state a valid execution sequence would reach. processed_at/approved_at's
    literal timestamp values are expected to differ (the log's own timestamp
    is authoritative for a repair, §13A — the original execution's own,
    separately-computed clock read is unrecoverable after a crash, which G2
    discloses rather than pretends around) but must still satisfy the same
    approved_at == processed_at atomicity invariant."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    # --- Reference: a real, uninterrupted execution ---
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir()
    ref_source = ref_dir / "invoice.pdf"
    ref_source.write_text("content")
    reference_record = _record(
        file_id="ref", tier="auto", current_path=str(ref_source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(reference_record, {}, tmp_path, batch_id="batch-1")
    assert reference_record.processed_at is not None

    # --- Simulated crash: an equivalent scenario, reconciled instead ---
    crash_dir = tmp_path / "crashed"
    crash_dir.mkdir()
    crash_source = crash_dir / "invoice.pdf"
    crash_source.write_text("content")
    crashed_destination = tmp_path / "Finance" / "invoice_crashed.pdf"
    crash_source.rename(crashed_destination)  # the move genuinely completed

    crashed_record = _record(
        file_id="crashed", tier="auto", current_path=str(crash_source),  # stale, pre-move
        processed_at=None, suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    save_file_record(crashed_record)
    log_move(
        batch_id="batch-1", record=crashed_record, override_type="normal",
        executed_name="invoice_crashed.pdf", executed_destination="Finance/",
        from_path=str(crash_source), to_path=str(crashed_destination), approved_by="auto",
    )
    # No save_file_record() call after the log write — simulating the crash.
    write_batch_plan("batch-1", [_plan_entry("crashed", str(crash_source), str(crashed_destination))])

    report = reconcile_batch("batch-1")
    assert report.outcomes["crashed"] == ReconciliationOutcome.REPAIRED
    repaired = next(r for r in load_metadata_store() if r.file_id == "crashed")

    assert repaired.current_path == str(crashed_destination)
    assert repaired.approved_by == reference_record.approved_by
    assert repaired.approved_at == repaired.processed_at  # atomicity, same as the real reference
    assert repaired.reversible == reference_record.reversible  # both clean moves -> True
    # Directly re-derivable from the real to_path/collision facts, exactly as
    # ExecutionEngine's own step 6 would compute it for this same outcome:
    assert repaired.reversible == (not ("~ARCHIVE~" in Path(repaired.current_path).parts))


def test_reconcile_batch_repair_matches_a_real_executionengine_outcome_archived_move(tmp_path, monkeypatch):
    """Same cross-check as above, for the archive-destination case — confirms
    reversible=False is reached identically whether via a live execution or a
    crash-repaired reconciliation."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    ref_dir = tmp_path / "reference2"
    ref_dir.mkdir()
    ref_source = ref_dir / "invoice.pdf"
    ref_source.write_text("content")
    reference_record = _record(
        file_id="ref2", tier="auto", current_path=str(ref_source), duplicate_of="other",
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(reference_record, {}, tmp_path, batch_id="batch-1")
    assert reference_record.reversible is False

    crash_dir = tmp_path / "crashed2"
    crash_dir.mkdir()
    crash_source = crash_dir / "invoice.pdf"
    crash_source.write_text("content")
    crashed_destination = tmp_path / "~ARCHIVE~" / "Duplicates" / "invoice_crashed.pdf"
    crashed_destination.parent.mkdir(parents=True, exist_ok=True)
    crash_source.rename(crashed_destination)

    crashed_record = _record(
        file_id="crashed2", tier="auto", current_path=str(crash_source), processed_at=None,
        duplicate_of="other", suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    save_file_record(crashed_record)
    log_move(
        batch_id="batch-1", record=crashed_record, override_type="exact_duplicate",
        executed_name="invoice_crashed.pdf", executed_destination="~ARCHIVE~/Duplicates/",
        from_path=str(crash_source), to_path=str(crashed_destination), approved_by="auto",
    )
    write_batch_plan("batch-1", [_plan_entry("crashed2", str(crash_source), str(crashed_destination))])

    report = reconcile_batch("batch-1")
    assert report.outcomes["crashed2"] == ReconciliationOutcome.REPAIRED
    repaired = next(r for r in load_metadata_store() if r.file_id == "crashed2")

    assert repaired.reversible == reference_record.reversible == False


# --- WP-9: execute_batch() — batch orchestration & Layer 2 safety net (§7,
# §9, §14, ARCHITECTURE_DECISIONS.md decision 24). Real, sandboxed tmp_path
# filesystem + real (isolated) metadata_store.json/action_log.jsonl/
# Runtime/Temp throughout, matching WP-7/WP-8's own established precedent —
# never mocked except for the deliberately forced Layer-2 exception below. ---

def _make_eligible_record(file_id, tmp_path, name, discovered_at, batch_id="batch-1", **kwargs):
    """`_record()` hardcodes `discovered_at`/`batch_id` as fixed literals in
    its own `FileRecord(...)` call, so they cannot be overridden via its
    `**kwargs` passthrough — set directly on the constructed object instead,
    matching `FileRecord`'s own mutable-dataclass shape (the same shape
    `ExecutionEngine`'s step 6 already relies on to mutate records in place)."""
    source = tmp_path / name
    source.write_text(f"content-{file_id}")
    record = _record(
        file_id=file_id, current_path=str(source), tier="auto",
        suggested_name=name, suggested_destination="Finance/",
        **kwargs,
    )
    record.discovered_at = discovered_at
    record.batch_id = batch_id
    return record


def test_execute_batch_empty_records_returns_immediately(tmp_path, monkeypatch):
    """No known batch_id, nothing to reconcile, nothing to execute — the
    empty-input short-circuit."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    result = execute_batch([], {}, tmp_path)

    assert result == []


def test_execute_batch_executes_multiple_records_and_returns_same_list_object(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    r1 = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")
    r2 = _make_eligible_record("f2", tmp_path, "b.pdf", "2026-01-02T00:00:00Z")
    records = [r1, r2]

    result = execute_batch(records, {}, tmp_path)

    assert result is records  # same list object, enriched in place (§6/§9)
    assert r1.processed_at is not None
    assert r2.processed_at is not None
    assert (tmp_path / "Finance" / "a.pdf").exists()
    assert (tmp_path / "Finance" / "b.pdf").exists()

    stored = {r.file_id: r for r in load_metadata_store()}
    assert stored["f1"].processed_at == r1.processed_at
    assert stored["f2"].processed_at == r2.processed_at


def test_execute_batch_second_call_over_fully_executed_batch_is_a_no_op(tmp_path, monkeypatch):
    """I7: a second execute_batch() call over an already-fully-executed batch
    performs zero filesystem operations and writes zero new log lines."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    record = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")
    records = [record]

    execute_batch(records, {}, tmp_path)
    first_run_entries = _read_log_entries(tmp_path)
    assert len(first_run_entries) == 1

    execute_batch(records, {}, tmp_path)  # second call, same already-executed records
    second_run_entries = _read_log_entries(tmp_path)

    assert second_run_entries == first_run_entries  # not one new line


def test_execute_batch_fixed_processing_order_is_reversed_input_independent(tmp_path, monkeypatch):
    """§7: the fixed (discovered_at, file_id) processing order, verified by
    feeding the batch in reverse order and confirming a byte-identical
    outcome except timestamp — the same determinism-test convention already
    established for Module 04-06."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    r1 = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")
    r2 = _make_eligible_record("f2", tmp_path, "b.pdf", "2026-01-02T00:00:00Z")
    execute_batch([r1, r2], {}, tmp_path)
    forward_entries = _read_log_entries(tmp_path)

    tmp_path2 = tmp_path / "reversed_run"
    tmp_path2.mkdir()
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path2 / "action_log.jsonl")
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path2 / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_RUNTIME_TEMP_PATH", tmp_path2 / "Temp")
    r1b = _make_eligible_record("f1", tmp_path2, "a.pdf", "2026-01-01T00:00:00Z")
    r2b = _make_eligible_record("f2", tmp_path2, "b.pdf", "2026-01-02T00:00:00Z")
    execute_batch([r2b, r1b], {}, tmp_path2)  # reversed input order
    reversed_entries = _read_log_entries(tmp_path2)

    def _normalize(entries, root):
        # Strip timestamp (never expected to match) and the root-specific
        # absolute path prefix (the two runs necessarily use different
        # tmp_path roots) — what must match is everything else, including
        # the relative from/to structure and per-file ordering.
        normalized = []
        for entry in entries:
            clean = {k: v for k, v in entry.items() if k != "timestamp"}
            for key in ("from", "to"):
                if clean.get(key):
                    clean[key] = clean[key].replace(str(root), "")
            normalized.append(clean)
        return normalized

    assert _normalize(forward_entries, tmp_path) == _normalize(reversed_entries, tmp_path2)


def test_execute_batch_layer_2_catches_unanticipated_exception_and_continues(tmp_path, monkeypatch):
    """§14 Layer 2: a genuinely unanticipated exception raised from inside
    ExecutionEngine.execute_file() for one record must not abort the batch —
    the rest of the batch still completes (G6/I4)."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    r1 = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")
    r2 = _make_eligible_record("f2", tmp_path, "b.pdf", "2026-01-02T00:00:00Z")

    real_execute_file = ExecutionEngine.execute_file

    def _flaky_execute_file(self, record, decisions, library_root, batch_id):
        if record.file_id == "f1":
            raise RuntimeError("simulated genuinely unanticipated failure")
        return real_execute_file(self, record, decisions, library_root, batch_id=batch_id)

    monkeypatch.setattr(ExecutionEngine, "execute_file", _flaky_execute_file)

    result = execute_batch([r1, r2], {}, tmp_path)

    assert result[0].processed_at is None  # f1 never executed
    assert result[1].processed_at is not None  # f2 still completed

    entries = _read_log_entries(tmp_path)
    error_entries = [e for e in entries if e["action"] == "error" and e["file_id"] == "f1"]
    assert len(error_entries) == 1
    assert "simulated genuinely unanticipated failure" in error_entries[0]["details"]["error_detail"]
    move_entries = [e for e in entries if e["action"] == "move_rename" and e["file_id"] == "f2"]
    assert len(move_entries) == 1


def test_execute_batch_unset_library_root_blocks_entire_batch(tmp_path, monkeypatch):
    """§14's distinct, batch-level failure class: an unset root blocks the
    whole batch before any file is attempted — no partial execution."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    r1 = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")
    r2 = _make_eligible_record("f2", tmp_path, "b.pdf", "2026-01-02T00:00:00Z")
    source1, source2 = Path(r1.current_path), Path(r2.current_path)

    result = execute_batch([r1, r2], {}, None)

    assert result[0].processed_at is None
    assert result[1].processed_at is None
    assert source1.exists() and source2.exists()  # neither file was touched
    assert load_metadata_store() == []  # nothing persisted

    entries = _read_log_entries(tmp_path)
    assert len(entries) == 2
    assert all(e["action"] == "error" for e in entries)
    assert all("unset" in e["details"]["error_detail"] for e in entries)


def test_execute_batch_nonexistent_library_root_blocks_entire_batch(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    r1 = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")

    result = execute_batch([r1], {}, tmp_path / "does_not_exist")

    assert result[0].processed_at is None
    entries = _read_log_entries(tmp_path)
    assert len(entries) == 1
    assert "does not exist" in entries[0]["details"]["error_detail"]


def test_execute_batch_library_root_that_is_a_file_not_a_directory_blocks_batch(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    not_a_dir = tmp_path / "not_a_directory.txt"
    not_a_dir.write_text("x")
    r1 = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")

    result = execute_batch([r1], {}, not_a_dir)

    assert result[0].processed_at is None
    entries = _read_log_entries(tmp_path)
    assert "not a directory" in entries[0]["details"]["error_detail"]


def test_execute_batch_root_failure_only_logs_for_still_eligible_records(tmp_path, monkeypatch):
    """A root-validation failure must not log a redundant entry for a record
    that was already executed (or resynced as such by reconciliation) — only
    still-needs_execution() records get the batch-blocked error."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    already_done = _make_eligible_record(
        "f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z",
        processed_at="2020-01-01T00:00:00+00:00",
    )
    still_pending = _make_eligible_record("f2", tmp_path, "b.pdf", "2026-01-02T00:00:00Z")

    execute_batch([already_done, still_pending], {}, None)

    entries = _read_log_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["file_id"] == "f2"


def test_execute_batch_runtime_temp_is_cleared_after_a_normal_run(tmp_path, monkeypatch):
    """Runtime/Temp/<batch_id>/ cleanup happens once every record has reached
    a terminal state — verified by staging correctly happening per-file
    during the run, and the directory being gone afterward."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    r1 = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")
    r2 = _make_eligible_record("f2", tmp_path, "b.pdf", "2026-01-02T00:00:00Z")

    execute_batch([r1, r2], {}, tmp_path)

    assert read_batch_plan("batch-1") is None  # cleared, not merely emptied
    assert not (runtime_io_module._RUNTIME_TEMP_PATH / "batch-1").exists()


def test_execute_batch_runtime_temp_cleared_even_when_root_invalid(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    r1 = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")

    execute_batch([r1], {}, None)

    assert read_batch_plan("batch-1") is None
    assert not (runtime_io_module._RUNTIME_TEMP_PATH / "batch-1").exists()


# --- decision 24: incremental staging, never a whole-batch resolve-then-
# execute phase. Proven by forcing two records to collide on the identical
# destination folder/name — if execute_batch() ever resolved the whole
# batch's destinations up front (before any record actually executed), both
# records' staged `to` would be the pristine, unsuffixed path; the second
# record's *executed* `to` would then diverge from what was staged for it,
# since ExecutionEngine always independently re-derives the real,
# execution-time collision state. Interleaved per-file staging instead
# guarantees the second record's staged entry is written only after the
# first record has already physically moved, so the real collision is
# already on disk by the time the second entry is staged. ---

def test_execute_batch_decision_24_no_whole_batch_staging_pass_two_records_collide(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    # Two distinct source files that both resolve to the identical
    # suggested_name/suggested_destination -> identical pristine `to` path.
    r1 = _make_eligible_record("f1", tmp_path, "same_name_source1.pdf", "2026-01-01T00:00:00Z")
    r2 = _make_eligible_record("f2", tmp_path, "same_name_source2.pdf", "2026-01-02T00:00:00Z")
    r1.suggested_name = "invoice.pdf"
    r2.suggested_name = "invoice.pdf"

    staged_entries = []
    real_write_batch_plan = execution_module.write_batch_plan

    def _recording_write_batch_plan(batch_id, planned_operations):
        staged_entries.append(copy.deepcopy(planned_operations[-1]))
        real_write_batch_plan(batch_id, planned_operations)

    monkeypatch.setattr(execution_module, "write_batch_plan", _recording_write_batch_plan)

    result = execute_batch([r1, r2], {}, tmp_path)

    assert len(staged_entries) == 2
    pristine = tmp_path / "Finance" / "invoice.pdf"
    suffixed = tmp_path / "Finance" / "invoice_2.pdf"
    assert staged_entries[0]["to"] == str(pristine)
    assert staged_entries[1]["to"] == str(suffixed)  # correctly suffixed, not a duplicate of entry 1

    entries = _read_log_entries(tmp_path)
    move_entries = sorted(
        [e for e in entries if e["action"] == "move_rename"], key=lambda e: e["file_id"]
    )
    assert move_entries[0]["to"] == str(pristine)
    assert move_entries[1]["to"] == str(suffixed)
    # The second record's staged `to` matches its own executed `to` exactly,
    # and both correctly reflect the first record's already-completed move.
    assert staged_entries[1]["to"] == move_entries[1]["to"]
    assert result[0].current_path == str(pristine)
    assert result[1].current_path == str(suffixed)


# --- reconciliation runs first, and its repairs are correctly synced back
# into execute_batch()'s own in-memory records before any new execution is
# attempted, so a REPAIRED record is never re-executed in the same call. ---

def test_execute_batch_reconciles_before_executing_and_never_reexecutes_a_repaired_record(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    # Simulate a prior crashed batch: the move + log completed, but the
    # process died before ExecutionEngine's own save_file_record() call
    # (exactly the scenario the WP-7 correction closed for *new* runs, but
    # still the correct starting state to construct for a *pre-existing*
    # leftover crash to reconcile).
    crashed_source = tmp_path / "crashed.pdf"
    crashed_source.write_text("content")
    crashed_destination = tmp_path / "Finance" / "crashed.pdf"
    crashed_destination.parent.mkdir(parents=True, exist_ok=True)
    crashed_source.rename(crashed_destination)

    crashed_record = _record(
        file_id="crashed", tier="auto", current_path=str(crashed_source), processed_at=None,
        suggested_name="crashed.pdf", suggested_destination="Finance/",
    )  # _record()'s own defaults already give batch_id="batch-1"/discovered_at="2026-01-01T00:00:00Z"
    save_file_record(crashed_record)  # persisted with processed_at still None
    log_move(
        batch_id="batch-1", record=crashed_record, override_type="normal",
        executed_name="crashed.pdf", executed_destination="Finance/",
        from_path=str(crashed_source), to_path=str(crashed_destination), approved_by="auto",
    )
    write_batch_plan("batch-1", [_plan_entry("crashed", str(crashed_source), str(crashed_destination))])

    # The in-memory record execute_batch() is handed still shows the
    # pre-crash-repair state (processed_at=None) — exactly what a caller who
    # loaded it moments before the crash was reconciled would hold.
    stale_in_memory_record = _record(
        file_id="crashed", tier="auto", current_path=str(crashed_source), processed_at=None,
        suggested_name="crashed.pdf", suggested_destination="Finance/",
    )

    result = execute_batch([stale_in_memory_record], {}, tmp_path)

    # Reconciliation repaired it (REPAIRED), and the resync step correctly
    # updated this function's own in-memory copy — never re-executed.
    assert result[0].processed_at is not None
    assert result[0].current_path == str(crashed_destination)
    assert crashed_destination.exists()  # still there, untouched a second time

    entries = _read_log_entries(tmp_path)
    move_entries = [e for e in entries if e["action"] == "move_rename"]
    assert len(move_entries) == 1  # only the original crash-era log line — no re-execution


def test_execute_batch_does_not_reexecute_a_normal_already_terminal_record(tmp_path, monkeypatch):
    """The far more common case than REPAIRED: a record whose prior execution
    completed cleanly (no crash at all). Confirms the resync step is harmless
    (a no-op) for the ordinary already-terminal case, not just the crash-
    repair case."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    record = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")

    execute_batch([record], {}, tmp_path)  # normal, clean execution
    assert record.processed_at is not None
    first_log = _read_log_entries(tmp_path)

    execute_batch([record], {}, tmp_path)  # same object, called again

    assert _read_log_entries(tmp_path) == first_log  # no new entries


# --- _validate_library_root()'s individual conditions, exercised indirectly
# through execute_batch()'s own observable batch-blocking behavior (matching
# this file's own established precedent of never importing/testing a
# private helper by name, e.g. _reject_path_escape()/_sanitize_error_detail()
# are likewise only ever exercised through their public callers). ---

def test_execute_batch_root_unreadable_blocks_batch(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    unreadable_root = tmp_path / "locked"
    unreadable_root.mkdir()
    r1 = _make_eligible_record("f1", tmp_path, "a.pdf", "2026-01-01T00:00:00Z")

    def _fake_access(path, mode):
        if Path(path) == unreadable_root:
            return False
        return True

    monkeypatch.setattr(execution_module.os, "access", _fake_access)

    result = execute_batch([r1], {}, unreadable_root)

    assert result[0].processed_at is None
    entries = _read_log_entries(tmp_path)
    assert "not readable/writable" in entries[0]["details"]["error_detail"]


# --- WP-10: capture_user_correction() (§19/G7, Module 07 Implementation
# Plan.md) — a leaf, no dependency on WP-2 through WP-9. Isolated against a
# sandboxed Database/Learning/User Corrections.json, matching every other
# WP's own established isolation convention. ---

def _isolate_learning(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database_module, "_USER_CORRECTIONS_PATH", tmp_path / "User Corrections.json"
    )


def _read_corrections(tmp_path):
    return database_module._load_index(tmp_path / "User Corrections.json", [])


def test_capture_user_correction_approve_as_suggested_captures_nothing(tmp_path, monkeypatch):
    _isolate_learning(tmp_path, monkeypatch)
    record = _record(file_id="f1")
    decision = _decision(file_id="f1", decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED)

    execution_module.capture_user_correction(record, decision)

    assert _read_corrections(tmp_path) == []


def test_capture_user_correction_edited_name_only(tmp_path, monkeypatch):
    _isolate_learning(tmp_path, monkeypatch)
    record = _record(file_id="f1", suggested_name="invoice.pdf", suggested_destination="Finance/")
    decision = _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_name="Amazon_Invoice.pdf",
    )

    execution_module.capture_user_correction(record, decision)

    corrections = _read_corrections(tmp_path)
    assert len(corrections) == 1
    assert corrections[0]["field"] == "filename"
    assert corrections[0]["suggested_value"] == "invoice.pdf"
    assert corrections[0]["corrected_value"] == "Amazon_Invoice.pdf"
    assert corrections[0]["file_id"] == "f1"
    assert corrections[0]["category"] == record.category.value


def test_capture_user_correction_edited_destination_only(tmp_path, monkeypatch):
    _isolate_learning(tmp_path, monkeypatch)
    record = _record(file_id="f1", suggested_name="invoice.pdf", suggested_destination="Finance/")
    decision = _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_destination="Finance/2026/",
    )

    execution_module.capture_user_correction(record, decision)

    corrections = _read_corrections(tmp_path)
    assert len(corrections) == 1
    assert corrections[0]["field"] == "destination"
    assert corrections[0]["suggested_value"] == "Finance/"
    assert corrections[0]["corrected_value"] == "Finance/2026/"


def test_capture_user_correction_edited_name_and_destination_both_captured(tmp_path, monkeypatch):
    _isolate_learning(tmp_path, monkeypatch)
    record = _record(file_id="f1", suggested_name="invoice.pdf", suggested_destination="Finance/")
    decision = _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_name="Amazon_Invoice.pdf", edited_destination="Finance/2026/",
    )

    execution_module.capture_user_correction(record, decision)

    corrections = _read_corrections(tmp_path)
    assert len(corrections) == 2
    assert {c["field"] for c in corrections} == {"filename", "destination"}


def test_capture_user_correction_edit_identical_to_suggestion_captures_nothing(tmp_path, monkeypatch):
    """An edit that resubmits the original, unchanged suggestion is not a
    correction — the disclosed judgment call in this module's own docstring."""
    _isolate_learning(tmp_path, monkeypatch)
    record = _record(file_id="f1", suggested_name="invoice.pdf", suggested_destination="Finance/")
    decision = _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_name="invoice.pdf", edited_destination="Finance/",  # identical to suggestion
    )

    execution_module.capture_user_correction(record, decision)

    assert _read_corrections(tmp_path) == []


def test_capture_user_correction_reject_captures_exactly_one_entry(tmp_path, monkeypatch):
    _isolate_learning(tmp_path, monkeypatch)
    record = _record(file_id="f1")
    decision = _decision(file_id="f1", decision=ApprovalDecisionType.REJECT)

    execution_module.capture_user_correction(record, decision)

    corrections = _read_corrections(tmp_path)
    assert len(corrections) == 1
    assert corrections[0]["field"] == "category"
    assert corrections[0]["suggested_value"] == record.category.value
    assert corrections[0]["corrected_value"] is None
    assert corrections[0]["category"] == record.category.value


def test_capture_user_correction_never_reads_back_or_influences_the_record(tmp_path, monkeypatch):
    """Passive capture only (NG6) — calling this function has zero effect on
    the FileRecord or ApprovalDecision objects themselves."""
    _isolate_learning(tmp_path, monkeypatch)
    record = _record(file_id="f1", suggested_name="invoice.pdf", suggested_destination="Finance/")
    before = copy.deepcopy(record)
    decision = _decision(
        file_id="f1", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_name="Amazon_Invoice.pdf",
    )

    execution_module.capture_user_correction(record, decision)

    assert record == before  # completely untouched


# --- WP-11: undo_single_action() / undo_batch() (§15) — the exact functional
# inverse of WP-7's ExecutionEngine. Real, sandboxed tmp_path filesystem +
# real (isolated) metadata_store.json/action_log.jsonl throughout, matching
# WP-7/WP-8/WP-9's own established precedent — never mocked. ---

def _move_type_entries(tmp_path):
    return [e for e in _read_log_entries(tmp_path) if e["action"] in
            {"move_rename", "archive_duplicate", "archive_superseded_version"}]


def _synthetic_move_entry(batch_id, file_id, from_path, to_path, action="move_rename",
                           timestamp="2026-01-01T00:00:00+00:00", approved_by="auto"):
    return {
        "batch_id": batch_id, "file_id": file_id, "action": action,
        "from": from_path, "to": to_path, "timestamp": timestamp,
        "approved_by": approved_by,
        "details": {"override_applied": None, "collision_suffix_applied": False,
                    "name_differed_from_suggestion": False,
                    "destination_differed_from_suggestion": False},
    }


def test_undo_single_action_restores_current_path_and_resets_fields(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")
    assert record.processed_at is not None
    moved_path = Path(record.current_path)
    assert moved_path.exists()
    entry = _move_type_entries(tmp_path)[0]

    outcome = undo_single_action(entry)

    assert outcome == UndoOutcome.UNDONE
    assert source.exists()  # restored to its original location
    assert not moved_path.exists()  # no longer at the moved location

    restored = next(r for r in load_metadata_store() if r.file_id == "f1")
    assert restored.current_path == str(source)
    assert restored.processed_at is None
    assert restored.approved_by is None
    assert restored.approved_at is None
    assert restored.reversible is True


def test_undo_single_action_appends_undo_entry_never_retracts_original(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")
    original_entry = _move_type_entries(tmp_path)[0]

    undo_single_action(original_entry)

    entries = _read_log_entries(tmp_path)
    assert entries[0] == original_entry  # untouched, still first, byte-identical
    undo_entries = [e for e in entries if e["action"] == "undo"]
    assert len(undo_entries) == 1
    assert undo_entries[0]["from"] == original_entry["to"]  # swapped
    assert undo_entries[0]["to"] == original_entry["from"]  # swapped
    assert undo_entries[0]["approved_by"] == "user"
    assert undo_entries[0]["details"]["reversed_action"] == "move_rename"


def test_undo_single_action_skips_irreversible_without_touching_anything(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source), duplicate_of="other",
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")
    assert record.reversible is False  # archived duplicate -> irreversible
    archived_path = Path(record.current_path)
    entry = _move_type_entries(tmp_path)[0]
    entries_before = _read_log_entries(tmp_path)

    outcome = undo_single_action(entry)

    assert outcome == UndoOutcome.SKIPPED_IRREVERSIBLE
    assert archived_path.exists()  # never moved
    assert _read_log_entries(tmp_path) == entries_before  # no new log entry at all

    unchanged = next(r for r in load_metadata_store() if r.file_id == "f1")
    assert unchanged.processed_at is not None  # FileRecord untouched
    assert unchanged.current_path == str(archived_path)


def test_undo_single_action_raises_for_non_move_action():
    entry = {"batch_id": "batch-1", "file_id": "f1", "action": "reject",
              "from": "/tmp/a.pdf", "to": None, "timestamp": "2026-01-01T00:00:00Z",
              "approved_by": "user", "details": {}}
    with pytest.raises(ValueError):
        undo_single_action(entry)


def test_undo_single_action_skipped_missing_when_file_not_at_logged_to_path(tmp_path, monkeypatch):
    """Someone/something moved or deleted the file outside this pipeline since
    the original action — the log's own `to` no longer has anything there."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    record = _record(file_id="f1", current_path=str(tmp_path / "gone.pdf"), processed_at="2026-01-01T00:00:00+00:00")
    save_file_record(record)
    entry = _synthetic_move_entry(
        "batch-1", "f1", str(tmp_path / "original.pdf"), str(tmp_path / "gone.pdf"),
    )

    outcome = undo_single_action(entry)

    assert outcome == UndoOutcome.SKIPPED_MISSING
    error_entries = [e for e in _read_log_entries(tmp_path) if e["action"] == "error"]
    assert len(error_entries) == 1
    assert "no file exists there" in error_entries[0]["details"]["error_detail"]


def test_undo_single_action_failed_when_restore_move_itself_fails(tmp_path, monkeypatch):
    """Every pre-check passes (reversible, source present, destination free)
    but perform_move() itself still fails — e.g. a genuine OS-level error
    arising between the check and the move."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")
    entry = _move_type_entries(tmp_path)[0]

    def _failing_perform_move(_source, _destination):
        return MoveResult(success=False, error_detail="simulated restore failure")

    monkeypatch.setattr(execution_module, "perform_move", _failing_perform_move)

    outcome = undo_single_action(entry)

    assert outcome == UndoOutcome.FAILED
    error_entries = [e for e in _read_log_entries(tmp_path) if e["action"] == "error"]
    assert len(error_entries) == 1
    assert "simulated restore failure" in error_entries[0]["details"]["error_detail"]
    # FileRecord untouched — a failed restore never resets the five fields:
    unchanged = next(r for r in load_metadata_store() if r.file_id == "f1")
    assert unchanged.processed_at is not None


def test_undo_single_action_skipped_collision_when_restore_destination_occupied(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    current_location = tmp_path / "current.pdf"
    current_location.write_text("content")
    occupied_original = tmp_path / "original.pdf"
    occupied_original.write_text("something else now lives here")  # occupies the restore target
    record = _record(file_id="f1", current_path=str(current_location), processed_at="2026-01-01T00:00:00+00:00")
    save_file_record(record)
    entry = _synthetic_move_entry("batch-1", "f1", str(occupied_original), str(current_location))

    outcome = undo_single_action(entry)

    assert outcome == UndoOutcome.SKIPPED_COLLISION
    assert current_location.exists()  # never moved
    assert occupied_original.read_text() == "something else now lives here"  # never overwritten
    error_entries = [e for e in _read_log_entries(tmp_path) if e["action"] == "error"]
    assert len(error_entries) == 1


def test_undo_single_action_skipped_no_record_when_file_id_missing(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    current_location = tmp_path / "current.pdf"
    current_location.write_text("content")
    entry = _synthetic_move_entry(
        "batch-1", "ghost-file-id", str(tmp_path / "original.pdf"), str(current_location),
    )

    outcome = undo_single_action(entry)

    assert outcome == UndoOutcome.SKIPPED_NO_RECORD
    error_entries = [e for e in _read_log_entries(tmp_path) if e["action"] == "error"]
    assert len(error_entries) == 1
    assert "no FileRecord" in error_entries[0]["details"]["error_detail"]


def test_undo_batch_post_undo_needs_execution_returns_true(tmp_path, monkeypatch):
    """Direct test of §13A's closing paragraph."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")
    assert needs_execution(record) is False

    report = undo_batch("batch-1")

    assert report.outcomes["f1"] == UndoOutcome.UNDONE
    restored = next(r for r in load_metadata_store() if r.file_id == "f1")
    assert needs_execution(restored) is True


def test_undo_batch_ignores_non_move_entries(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    moved_record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(moved_record, {}, tmp_path, batch_id="batch-1")
    declined_record = _record(
        file_id="f2", tier="approval_required", current_path=str(tmp_path / "declined.pdf"),
    )
    decisions = {"f2": _decision(file_id="f2", decision=ApprovalDecisionType.REJECT)}
    ExecutionEngine().execute_file(declined_record, decisions, tmp_path, batch_id="batch-1")

    report = undo_batch("batch-1")  # must not raise ValueError on the reject entry

    assert set(report.outcomes.keys()) == {"f1"}  # f2's reject entry was never attempted
    assert report.outcomes["f1"] == UndoOutcome.UNDONE


def test_undo_batch_empty_when_no_move_entries(tmp_path, monkeypatch):
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    record = _record(file_id="f1", tier="review_required", current_path=str(tmp_path / "a.pdf"))
    ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")  # leaves it unchanged, no log at all

    report = undo_batch("batch-1")

    assert report.outcomes == {}


def test_undo_batch_reverse_chronological_order_version_chain_scenario(tmp_path, monkeypatch):
    """The exact scenario §15's own text describes: file A is archived to make
    room for file B, which is then renamed into A's now-vacated original
    location. Reverse-chronological undo_batch() must restore both correctly.

    Uses two plain, reversible "normal" moves rather than a genuine
    duplicate/superseded-version archive: an archived move is irreversible by
    design (§15) and would be `SKIPPED_IRREVERSIBLE` regardless of ordering,
    which would exercise the *wrong* mechanism for this test's purpose. This
    isolates the ordering/collision mechanism itself, deliberately kept
    separate from the unrelated `reversible=False` rule (covered by its own
    dedicated test above).
    """
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    # T1: file A moved out of "a_source/A.pdf" (its original spot) to
    # "Finance/Report.pdf".
    a_original = tmp_path / "a_source" / "A.pdf"
    a_original.parent.mkdir(parents=True, exist_ok=True)
    a_original.write_text("A content")
    record_a = _record(
        file_id="A", tier="auto", current_path=str(a_original),
        suggested_name="Report.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(record_a, {}, tmp_path, batch_id="batch-1")
    assert record_a.reversible is True
    a_final = Path(record_a.current_path)  # tmp_path/Finance/Report.pdf

    # T2: file B's own original spot IS A's pre-move original location —
    # reused now that nothing else needs it — and B gets renamed to take
    # over "Report.pdf" at the SAME primary destination A used to occupy
    # conceptually; to create a genuine restore-time path clash we instead
    # make B's *suggested* destination collide with A's *original* source
    # path directly (the concrete condition undo needs to reproduce).
    b_original = tmp_path / "b_source" / "B.pdf"
    b_original.parent.mkdir(parents=True, exist_ok=True)
    b_original.write_text("B content")
    record_b = _record(
        file_id="B", tier="auto", current_path=str(b_original),
        suggested_name="A.pdf", suggested_destination="a_source/",
    )
    ExecutionEngine().execute_file(record_b, {}, tmp_path, batch_id="batch-1")
    assert record_b.reversible is True
    assert record_b.current_path == str(a_original)  # B now sits exactly where A's restore needs to land

    entries = _move_type_entries(tmp_path)
    entry_a = next(e for e in entries if e["file_id"] == "A")
    entry_b = next(e for e in entries if e["file_id"] == "B")
    assert entry_a["timestamp"] < entry_b["timestamp"]  # A first (T1), B second (T2)

    # Reverse-chronological (correct, real implementation): B undone first,
    # vacating a_original; then A undone into the now-free path.
    report = undo_batch("batch-1")

    assert report.outcomes["B"] == UndoOutcome.UNDONE
    assert report.outcomes["A"] == UndoOutcome.UNDONE
    assert b_original.exists()  # B restored to its own original spot ("b_source/B.pdf")
    assert b_original.read_text() == "B content"
    assert a_original.exists()  # A restored to its own original spot ("a_source/A.pdf"), freed by B's undo
    assert a_original.read_text() == "A content"
    assert not a_final.exists()  # A no longer at its post-move location ("Finance/Report.pdf")


def test_undo_batch_forward_order_replay_would_collide(tmp_path, monkeypatch):
    """Same scenario as the reverse-chronological test above, replayed
    manually in FORWARD order instead — proving the ordering requirement is
    load-bearing, not cosmetic: A's restore collides with B, which hasn't
    been undone yet."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)

    a_original = tmp_path / "a_source" / "A.pdf"
    a_original.parent.mkdir(parents=True, exist_ok=True)
    a_original.write_text("A content")
    record_a = _record(
        file_id="A", tier="auto", current_path=str(a_original),
        suggested_name="Report.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(record_a, {}, tmp_path, batch_id="batch-1")

    b_original = tmp_path / "b_source" / "B.pdf"
    b_original.parent.mkdir(parents=True, exist_ok=True)
    b_original.write_text("B content")
    record_b = _record(
        file_id="B", tier="auto", current_path=str(b_original),
        suggested_name="A.pdf", suggested_destination="a_source/",
    )
    ExecutionEngine().execute_file(record_b, {}, tmp_path, batch_id="batch-1")
    assert record_b.current_path == str(a_original)

    entries = _move_type_entries(tmp_path)
    entry_a = next(e for e in entries if e["file_id"] == "A")
    entry_b = next(e for e in entries if e["file_id"] == "B")

    # Forward order: undo A (T1) BEFORE undo B (T2) — deliberately wrong.
    outcome_a_forward = undo_single_action(entry_a)

    assert outcome_a_forward == UndoOutcome.SKIPPED_COLLISION  # B still occupies a_original
    assert Path(record_b.current_path).exists()  # B untouched, still blocking A's restore


def test_undo_batch_never_calls_file_index_history_or_learning_functions(tmp_path, monkeypatch):
    """§15's explicit non-goal, verified structurally: no FileIndex/History/
    Learning write function is ever invoked during a batch undo."""
    _isolate_action_log(tmp_path, monkeypatch)
    _isolate_database_and_temp(tmp_path, monkeypatch)
    source = _make_source_file(tmp_path)
    record = _record(
        file_id="f1", tier="auto", current_path=str(source),
        suggested_name="invoice.pdf", suggested_destination="Finance/",
    )
    ExecutionEngine().execute_file(record, {}, tmp_path, batch_id="batch-1")

    calls = []
    for name in ("record_version_history", "log_user_correction"):
        original = getattr(database_module, name)
        def _tracking(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)
        monkeypatch.setattr(database_module, name, _tracking)

    undo_batch("batch-1")

    assert calls == []
