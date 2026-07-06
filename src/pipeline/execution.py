"""
Preview, Approval & Execution. HYBRID module: deterministic execution + the human
(not Claude) makes the approval call. This is the human checkpoint.

Architecture: Build-out/07 Preview, Approval & Execution/07 Preview, Approval & Execution.md

`build_preview()` and `execute_approved()` are pure code. The actual approve/edit/reject
decision comes from the user during a live run — this module doesn't decide FOR them.
Scaffold only: signatures defined, no logic yet.
"""

from typing import List

from src.models.file_record import FileRecord


def build_preview(records: List[FileRecord]) -> str:
    """Render the batch as a preview table: old name -> new name, old location ->
    new destination, category, confidence, tier. `auto` tier rows pre-checked;
    `review_required` rows shown separately, flagged, never pre-filed."""
    raise NotImplementedError


def execute_approved(records: List[FileRecord], approved_file_ids: List[str]) -> None:
    """Move + rename each approved file in one step. Records the pre-move path via
    storage/runtime_io.append_action_log() before the move — that log entry IS the
    undo mechanism. Must update record.current_path (and persist via
    storage/database.save_file_record()) to the new location once the move succeeds —
    current_path is the single authoritative "where is this file now" field
    (see models/file_record.py); original_path stays fixed as the first-discovery
    record. Never deletes anything. Destination folders are created if they don't
    exist yet (safe/idempotent)."""
    raise NotImplementedError


def log_rejected_edit(file_id: str, field_name: str, suggested_value: str,
                       corrected_value: str, category: str) -> None:
    """When the user edits or rejects a suggestion, log it to
    Database/Learning/User Corrections.json via storage/database.log_user_correction()."""
    raise NotImplementedError


# After execute_approved() runs, hand off to pipeline/reporting.py's finalize_batch()
# to write the action log, Database updates, and Daily Summary.
