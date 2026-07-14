"""
Deterministic module — no Claude judgment involved.

Reads/writes Runtime/ (Logs/, Reports/, Temp/).

Module 01 (Watch & Ingest) scope: `append_action_log()` is implemented, since every
module needs to write to the action log. Report-writing functions remain
unimplemented — they belong to Module 08 (Logging & Reporting), and Module 01 does
not touch them. Temp/ staging functions (`stage_batch_temp()`/`clear_batch_temp()`)
were implemented at Module 07 (Preview, Approval & Execution) implementation time
(`Module 07 Implementation Plan.md` WP-8, §18/§13A) — `write_batch_plan()`/
`read_batch_plan()`/`read_action_log_entries()` are WP-8's own disclosed additions
alongside them (raw Runtime/Temp/ and Runtime/Logs/ I/O primitives only; the actual
§13A five-step reconciliation *business logic* that calls these lives in
`pipeline/execution.py`'s `reconcile_batch()`, mirroring how this file's own
`append_action_log()` is a raw I/O primitive Module 07's `log_move()`/`log_error()`/
`log_decline()` call, never business logic itself).
"""

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ACTION_LOG_PATH = _PROJECT_ROOT / "Runtime" / "Logs" / "action_log.jsonl"
_RUNTIME_TEMP_PATH = _PROJECT_ROOT / "Runtime" / "Temp"
_RUNTIME_REPORTS_PATH = _PROJECT_ROOT / "Runtime" / "Reports"


def action_log_path() -> Path:
    """Public accessor for where action_log.jsonl lives — for callers (e.g. the CLI)
    that want to tell the user where their generated log ended up without reaching
    into the module's underlying path constant directly."""
    return _ACTION_LOG_PATH


def append_action_log(batch_id: str, file_id: str, action: str,
                       from_path: Optional[str] = None, to_path: Optional[str] = None,
                       approved_by: str = "auto", details: Optional[dict] = None) -> None:
    """Append one JSON line to Runtime/Logs/action_log.jsonl.

    `action` values defined in Build-out/08 .../Metadata & Log Schema.md: move_rename |
    archive_duplicate | archive_superseded_version | skip | error | undo. Module 01
    additionally uses `discover` (a supported file was found and queued), Module 02
    additionally uses `classify` (a file was assigned a category and classification
    signals), and Module 03 additionally uses `extract_metadata` — minimal, documented
    extensions to that vocabulary, since the original schema was written before any
    module existed and didn't anticipate any of them. Module 04 additionally uses
    `detect_duplicates_and_versions` (Module 04 Design.md §18, F6) — updated in the
    same release cycle Module 04 ships, per that design's own explicit requirement
    not to repeat the gap this docstring/schema doc already had to close twice before.
    Module 05 additionally uses `suggest_naming_and_destination` (Module 05
    Design.md §18) — updated at implementation time for the same reason.
    Module 06 additionally uses `score_confidence` (Module 06 Design.md §16)
    — updated at implementation time for the same reason.
    Module 07 additionally uses `reject` (Module 07 Design.md §17, Open Decision
    OD-2, confirmed as `Governance/ARCHITECTURE_DECISIONS.md` decision 21;
    `move_rename`/`archive_duplicate`/`archive_superseded_version`/`error` were
    already part of this vocabulary before Module 07 existed) — updated at
    implementation time (`Module 07 Implementation Plan.md` WP-6) for the same
    reason.
    """
    _ACTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "batch_id": batch_id,
        "file_id": file_id,
        "action": action,
        "from": from_path,
        "to": to_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "approved_by": approved_by,
    }
    if details:
        entry["details"] = details
    with open(_ACTION_LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry) + "\n")


def read_action_log_entries() -> List[dict]:
    """Reads every entry in `Runtime/Logs/action_log.jsonl` back into plain dicts,
    in file order (append-only, so this is also chronological order) — added by
    WP-8 (`Module 07 Implementation Plan.md`) as the raw-read counterpart to
    `append_action_log()`'s raw write, needed by `pipeline/execution.py`'s
    `reconcile_batch()` (§13A step 1: "check whether the action log has a
    completed entry... matching the plan's intended `to` path") to search the
    log without duplicating `append_action_log()`'s own path/format knowledge.
    No earlier module needed to read this file back — every module before
    Module 07 only ever appended to it — so no reader existed until now.

    Returns `[]` if the log doesn't exist yet (a fresh installation with no
    prior activity) rather than raising — mirroring `load_metadata_store()`'s
    own "nothing recorded yet is a valid, empty state, not an error" precedent
    (`src/storage/database.py`).
    """
    if not _ACTION_LOG_PATH.exists():
        return []
    raw_text = _ACTION_LOG_PATH.read_text(encoding="utf-8").strip()
    if not raw_text:
        return []
    return [json.loads(line) for line in raw_text.splitlines()]


# --- Module 07 (Preview, Approval & Execution) territory ---

def undo_batch(batch_id: str) -> None:
    """Replay every action_log.jsonl line for this batch_id with from/to swapped."""
    raise NotImplementedError("Module 07 (Preview, Approval & Execution) territory")


def stage_batch_temp(batch_id: str) -> str:
    """Create/return the working directory Runtime/Temp/<batch_id>/ for an in-progress
    batch, so a crash mid-execution can resume or be cleanly discarded (§18,
    implemented at WP-8, `Module 07 Implementation Plan.md`).

    Idempotent — matches `ensure_destination_folder()`'s own established
    "calling this twice, or when the folder already exists, is a no-op, not an
    error" convention (`pipeline/execution.py`, WP-5), applied here to Module
    07's other folder-creation site.
    """
    dir_path = _RUNTIME_TEMP_PATH / batch_id
    dir_path.mkdir(parents=True, exist_ok=True)
    return str(dir_path)


def clear_batch_temp(batch_id: str) -> None:
    """Remove Runtime/Temp/<batch_id>/ once a batch completes successfully — i.e.
    once `pipeline/execution.py`'s `reconcile_batch()` (§13A step 5, WP-8) has
    resolved every leftover `plan.json` entry to a terminal state, or once a
    clean (non-crash-interrupted) batch finishes normally.

    Idempotent — a no-op if the directory doesn't exist (already cleared, or
    never staged in the first place), consistent with `stage_batch_temp()`'s
    own idempotency. Deliberately does NOT swallow a genuine deletion failure
    (e.g. a permissions error) behind `ignore_errors=True` — `Runtime/Temp/` is
    disposable pipeline-internal bookkeeping, not user data, so `shutil.rmtree()`
    is safe to use here (unlike `perform_move()`, `pipeline/execution.py`, WP-5,
    which deliberately never imports `shutil` for *file moves*, since
    `shutil.move()`'s cross-device copy-then-delete fallback would violate G1's
    spirit for a real, user-owned file — that constraint is about moving a
    user's file, not about deleting this module's own disposable temp
    directory) — but a real failure here should still fail loudly rather than
    be silently absorbed (`ARCHITECTURE_DECISIONS.md` decision 19), so any
    `OSError` `shutil.rmtree()` raises is left to propagate, not caught.
    """
    dir_path = _RUNTIME_TEMP_PATH / batch_id
    if dir_path.exists():
        shutil.rmtree(dir_path)


def write_batch_plan(batch_id: str, planned_operations: List[Dict[str, str]]) -> None:
    """Writes `Runtime/Temp/<batch_id>/plan.json` — the batch's planned operations
    (§18: "source -> resolved destination pairs, post-collision-check"), staged
    before executing any file in the batch so a crash mid-batch leaves a
    resumption record behind.

    `planned_operations` is a plain list of `{"file_id": ..., "from": ...,
    "to": ...}` dicts, deliberately mirroring `append_action_log()`'s own
    `from`/`to` naming rather than inventing a new vocabulary — a disclosed
    scope clarification beyond the Implementation Plan's own prose (which
    describes `stage_batch_temp(batch_id, planned_operations)` as one
    function; the already-existing, frozen `stage_batch_temp(batch_id) -> str`
    stub signature above takes no such parameter, so this function is added
    alongside it rather than changing that stub's signature — the same
    "frozen artifact wins over descriptive Plan prose" precedent already
    established at WP-2/WP-3/WP-5). Calls `stage_batch_temp()` itself, so
    callers never need to call both separately.
    """
    dir_path = Path(stage_batch_temp(batch_id))
    plan_path = dir_path / "plan.json"
    plan_path.write_text(json.dumps(planned_operations, indent=2), encoding="utf-8")


def read_batch_plan(batch_id: str) -> Optional[List[Dict[str, str]]]:
    """Reads `Runtime/Temp/<batch_id>/plan.json` back, or `None` if no such file
    exists — a `None` result means either this batch was never staged, or it
    already completed cleanly and `clear_batch_temp()` already removed it
    (§13A: "a prior run's batch that never reached a clean `clear_batch_temp()`"
    is the only case a *leftover* plan.json represents; a `None` here is not
    itself evidence of a crash, and `reconcile_batch()` treats it as nothing-
    to-reconcile, not an error)."""
    plan_path = _RUNTIME_TEMP_PATH / batch_id / "plan.json"
    if not plan_path.exists():
        return None
    return json.loads(plan_path.read_text(encoding="utf-8"))


# --- Module 08 (Logging & Reporting) territory.
# Implemented at Module 08 Implementation Plan.md WP-1 (scaffold reconciliation),
# per Module 08 Design.md §6/§9 and Governance/ARCHITECTURE_DECISIONS.md decision 25.
# Raw I/O only: each function receives already-rendered Markdown content from its
# `generate_*()` caller (pipeline/reporting.py) and writes it to a fixed path,
# exactly mirroring append_action_log()'s own "raw I/O primitive, business logic
# lives one layer up" role above. The four pre-existing stubs this replaces took a
# `batch`/`records` pair each — a shape from the superseded, per-batch-triggered
# architecture (Module 08 Design.md §0.6) that cannot represent the real, date/week/
# whole-store-scoped aggregation the frozen design actually specifies (§5); WP-1's
# own scope is correcting that signature mismatch, per
# `Module 08 Implementation Plan.md Review.md` finding F1. ---

def write_daily_summary(report_date: date, content: str) -> str:
    """Write `content` to Runtime/Reports/Daily Summary/summary_YYYY-MM-DD.md
    (Module 08 Design.md §6) and return the path written. Makes no aggregation or
    rendering decision of its own — `report_date` and `content` are already fully
    computed by `generate_daily_summary()` (`pipeline/reporting.py`, WP-2's own
    scope, not implemented here)."""
    target_dir = _RUNTIME_REPORTS_PATH / "Daily Summary"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"summary_{report_date.isoformat()}.md"
    target_path.write_text(content, encoding="utf-8")
    return str(target_path)


def write_weekly_summary(report_week: date, content: str) -> str:
    """Write `content` to Runtime/Reports/Weekly Summary/summary_YYYY-Www.md, ISO
    week numbering (Module 08 Design.md §6), and return the path written.
    `report_week` is any date within the target ISO week — the ISO year/week
    number are derived from it via `date.isocalendar()` (stdlib only, no new
    dependency). Deciding *which* week a given run belongs to, and every rollup
    decision, is `generate_weekly_summary()`'s own scope (`pipeline/reporting.py`,
    WP-4, not implemented here) — this function only persists already-rendered
    content to the correct path, mirroring `write_daily_summary()`'s identical
    division of labor."""
    target_dir = _RUNTIME_REPORTS_PATH / "Weekly Summary"
    target_dir.mkdir(parents=True, exist_ok=True)
    iso_year, iso_week, _ = report_week.isocalendar()
    target_path = target_dir / f"summary_{iso_year}-W{iso_week:02d}.md"
    target_path.write_text(content, encoding="utf-8")
    return str(target_path)


def write_duplicate_report(content: str) -> str:
    """Module 08 (Logging & Reporting) territory — `generate_duplicate_report()`'s
    own raw-I/O counterpart (WP-3, not implemented here).

    Signature corrected to the smallest OD-1-agnostic shape (content in, path out)
    at WP-1 per `Module 08 Implementation Plan.md Review.md` finding F5. Open
    Decision OD-1 has since been resolved (`Governance/ARCHITECTURE_DECISIONS.md`
    decision 25: a single, continuously-updated current-state file,
    `Runtime/Reports/Duplicate Report/duplicate_report.md`, no scoping parameter
    needed) — but finalizing this function's real body against that resolution is
    explicitly WP-3's own scope, per the certified Implementation Plan and the
    project owner's explicit instruction that WP-1 implement only scaffold
    reconciliation, never Duplicate Report logic. Left unimplemented here by
    design, not by omission."""
    raise NotImplementedError("Module 08 Implementation Plan.md WP-3 territory")


def write_storage_report(content: str) -> str:
    """Module 08 (Logging & Reporting) territory — `generate_storage_report()`'s
    own raw-I/O counterpart (WP-5, not implemented here).

    Signature corrected to the smallest OD-1-agnostic shape (content in, path out)
    at WP-1, mirroring `write_duplicate_report()`'s identical treatment and the
    same finding F5 resolution. Finalizing this function's real body against
    OD-1's resolved shape (decision 25) is explicitly WP-5's own scope, not WP-1's
    — left unimplemented here by design."""
    raise NotImplementedError("Module 08 Implementation Plan.md WP-5 territory")
