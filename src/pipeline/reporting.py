"""
Logging & Reporting. DETERMINISTIC module (no Claude judgment).

Architecture: Build-out/08 Logging & Reporting/08 Logging & Reporting.md
Schema: Build-out/08 Logging & Reporting/Metadata & Log Schema.md

Thin orchestration layer over storage/database.py and storage/runtime_io.py — this
module's job is "call the right writes in the right order after a batch," not to
reimplement the storage logic itself.

Responsible for:
- Writing the action log (Runtime/Logs/action_log.jsonl)
- Generating Daily Summary reports (Runtime/Reports/Daily Summary/)
- Generating batch summaries (the per-run rollup that feeds into a Daily Summary)
- Producing execution reports (Weekly Summary, Duplicate Report, Storage Report)

Named `reporting.py` instead of `logging.py` to avoid shadowing Python's stdlib
`logging` module.

Scaffold only: signatures defined, no logic yet.
"""

from typing import List

from src.models.batch import Batch
from src.models.file_record import FileRecord


def finalize_batch(batch: Batch) -> None:
    """After execution.py runs a batch: update Database/Metadata + FileIndex + History
    for every processed file, append the action log entries, then write that day's
    Daily Summary. Never let a logging/reporting failure block the file moves that
    already happened — surface failures in the Daily Summary instead."""
    raise NotImplementedError


def write_action_log(batch: Batch, records: List[FileRecord]) -> None:
    """Append one JSON line per action to Runtime/Logs/action_log.jsonl, via
    storage/runtime_io.append_action_log()."""
    raise NotImplementedError


def write_daily_summary(batch: Batch, records: List[FileRecord]) -> str:
    """Generate/append today's Runtime/Reports/Daily Summary/ entry from a completed
    batch, via storage/runtime_io.write_daily_summary()."""
    raise NotImplementedError


def write_weekly_summary() -> str:
    """Roll up the week's Daily Summaries into Runtime/Reports/Weekly Summary/."""
    raise NotImplementedError


def write_duplicate_report() -> str:
    """Update the running Runtime/Reports/Duplicate Report/ view."""
    raise NotImplementedError


def write_storage_report() -> str:
    """Update the running Runtime/Reports/Storage Report/ view."""
    raise NotImplementedError
