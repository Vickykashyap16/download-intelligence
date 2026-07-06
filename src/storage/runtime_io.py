"""
Deterministic module — no Claude judgment involved.

Reads/writes Runtime/ (Logs/, Reports/, Temp/).

Module 01 (Watch & Ingest) scope: `append_action_log()` is implemented, since every
module needs to write to the action log. Report-writing and Temp/ staging functions
remain unimplemented — they belong to Module 07 (Preview, Approval & Execution) and
Module 08 (Logging & Reporting), and Module 01 does not touch them.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.models.batch import Batch
from src.models.file_record import FileRecord

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ACTION_LOG_PATH = _PROJECT_ROOT / "Runtime" / "Logs" / "action_log.jsonl"


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
    additionally uses `discover` (a supported file was found and queued), and Module 02
    additionally uses `classify` (a file was assigned a category and classification
    signals) — both minimal, documented extensions to that vocabulary, since the
    original schema was written before any module existed and didn't anticipate
    either event. (The `classify` addition was missing from this docstring and the
    schema doc until the Module 02 release audit, 2026-07-06, found the gap.)
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


# --- Module 07 (Preview, Approval & Execution) territory ---

def undo_batch(batch_id: str) -> None:
    """Replay every action_log.jsonl line for this batch_id with from/to swapped."""
    raise NotImplementedError("Module 07 (Preview, Approval & Execution) territory")


def stage_batch_temp(batch_id: str) -> str:
    """Create/return the working directory Runtime/Temp/<batch_id>/ for an in-progress
    batch, so a crash mid-execution can resume or be cleanly discarded."""
    raise NotImplementedError("Module 07 (Preview, Approval & Execution) territory")


def clear_batch_temp(batch_id: str) -> None:
    """Remove Runtime/Temp/<batch_id>/ once a batch completes successfully."""
    raise NotImplementedError("Module 07 (Preview, Approval & Execution) territory")


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
