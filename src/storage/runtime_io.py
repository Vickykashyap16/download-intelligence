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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.models.batch import Batch
from src.models.file_record import FileRecord

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ACTION_LOG_PATH = _PROJECT_ROOT / "Runtime" / "Logs" / "action_log.jsonl"
_RUNTIME_TEMP_PATH = _PROJECT_ROOT / "Runtime" / "Temp"


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


# --- Module 08 (Logging & Reporting) territory ---

def write_daily_summary(batch: Batch, records: List[FileRecord]) -> str:
    """Generate/append today's Runtime/Reports/Daily Summary/ entry."""
    raise NotImplementedError("Module 08 (Logging & Reporting) territory")


def write_weekly_summary() -> str:
    """Roll up the week's Daily Summaries into Runtime/Reports/Weekly Summary/."""
    raise NotImplementedError("Module 08 (Logging & Reporting) territory")


def write_duplicate_report() -> str:
    """Update the running Runtime/Reports/Duplicate Report/ view."""
    raise NotImplementedError("Module 08 (Logging & Reporting) territory")


def write_storage_report() -> str:
    """Update the running Runtime/Reports/Storage Report/ view."""
    raise NotImplementedError("Module 08 (Logging & Reporting) territory")
