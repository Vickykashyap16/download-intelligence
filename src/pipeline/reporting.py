"""
Logging & Reporting. DETERMINISTIC module (no Claude judgment).

Architecture: Build-out/08 Logging & Reporting/Module 08 Design.md
Schema: Build-out/08 Logging & Reporting/Metadata & Log Schema.md

Read-only aggregation and Markdown report generation over data every earlier
module (01-07) already wrote — Module 08 owns zero FileRecord fields, never
writes to Database/*, and never appends to the action log itself. Every module
already writes its own action-log entries via storage/runtime_io.append_action_log()
as it goes (Module 08 Design.md §0.6); this module only reads that log and the
metadata store back, and its only write surface is Runtime/Reports/*.

Single-layer batch-function architecture, no Engine/Provider split (§2/§9): four
report-generation functions, each following load -> filter -> aggregate -> render
-> write, calling storage/runtime_io.py's correspondingly-named write_*() function
(the raw-I/O layer) to actually persist rendered Markdown to Runtime/Reports/.

Named `reporting.py` instead of `logging.py` to avoid shadowing Python's stdlib
`logging` module.

Module 08 Implementation Plan.md WP-1 scope only (scaffold reconciliation): the
four generate_*() functions below are stubs — signatures fixed, no aggregation/
rendering logic yet. That logic is WP-2 (Daily Summary), WP-3 (Duplicate Report),
WP-4 (Weekly Summary), and WP-5 (Storage Report)'s own scope, not implemented
here. What IS implemented here are the shared, pure aggregation primitives every
one of those four functions will need: a malformed-line-safe action-log reader
(§12 Layer 1), a data-derived "as of" recency marker (§7), and calendar-day/
action-type action-log filters.

This file replaces the pre-existing `write_daily_summary()`/`write_weekly_summary()`/
`write_duplicate_report()`/`write_storage_report()`-named stubs that used to live
here, which took a `batch`/`records` pair each — a shape from the superseded,
per-batch-triggered architecture (§0.6) that cannot represent the real, date/week/
whole-store-scoped aggregation the frozen design actually specifies (§5). See
`Module 08 Implementation Plan.md Review.md` finding F1 for the full reasoning.
"""

import json
from datetime import date
from typing import Iterable, List, Optional, Tuple

from src.storage import runtime_io


# --- Report generation (stubs — WP-2 through WP-5's own implementation scope) ---

def generate_daily_summary(report_date: date) -> str:
    """Aggregate `report_date`'s action-log entries and resulting FileRecord
    states into Runtime/Reports/Daily Summary/summary_YYYY-MM-DD.md (§3, §6) and
    return the path written. Not implemented here — WP-2's own scope
    (`Module 08 Implementation Plan.md`)."""
    raise NotImplementedError("Module 08 Implementation Plan.md WP-2 territory")


def generate_weekly_summary(report_week: date) -> str:
    """Roll up the ISO week containing `report_week` from already-written Daily
    Summary files into Runtime/Reports/Weekly Summary/summary_YYYY-Www.md (§3, §9)
    and return the path written. Not implemented here — WP-4's own scope
    (`Module 08 Implementation Plan.md`)."""
    raise NotImplementedError("Module 08 Implementation Plan.md WP-4 territory")


def generate_duplicate_report() -> str:
    """Aggregate every duplicate/version-signal-bearing record in the metadata
    store into Runtime/Reports/Duplicate Report/duplicate_report.md (§3, single
    continuously-updated current-state file per
    `Governance/ARCHITECTURE_DECISIONS.md` decision 25) and return the path
    written. Not implemented here — WP-3's own scope
    (`Module 08 Implementation Plan.md`)."""
    raise NotImplementedError("Module 08 Implementation Plan.md WP-3 territory")


def generate_storage_report() -> str:
    """Aggregate space-used-per-destination-folder/category into
    Runtime/Reports/Storage Report/storage_report.md (§3, single
    continuously-updated current-state file per
    `Governance/ARCHITECTURE_DECISIONS.md` decision 25) and return the path
    written. Not implemented here — WP-5's own scope
    (`Module 08 Implementation Plan.md`)."""
    raise NotImplementedError("Module 08 Implementation Plan.md WP-5 territory")


# --- Shared aggregation primitives (WP-1) ---

def read_action_log_entries_safe() -> Tuple[List[dict], int]:
    """Malformed-line-safe counterpart to
    `storage.runtime_io.read_action_log_entries()` (§12 Layer 1): a malformed/
    corrupt line (e.g. a truncated write from a genuinely interrupted process) is
    skipped rather than raised, so one bad line never crashes an entire report.
    Returns `(valid_entries, malformed_line_count)` — every `generate_*()`
    function that reads the action log uses this, never the raw, unsafe
    `read_action_log_entries()` directly, and discloses `malformed_line_count`
    visibly in its rendered output rather than silently under-reporting (G3).

    Reads via `runtime_io.action_log_path()` (the existing public path accessor)
    rather than reimplementing path resolution, and mirrors
    `read_action_log_entries()`'s own "returns `[]` if the log doesn't exist yet"
    precedent — a fresh install with no activity is "nothing to report," not an
    error (§12 Layer 1's first bullet)."""
    path = runtime_io.action_log_path()
    if not path.exists():
        return [], 0

    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return [], 0

    entries: List[dict] = []
    malformed_count = 0
    for line in raw_text.splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            malformed_count += 1
    return entries, malformed_count


def compute_as_of_marker(entries: List[dict]) -> Optional[str]:
    """The data-derived "as of" recency marker (§7, option D): the latest
    `timestamp` value among `entries` (a report's own already-filtered entry
    list), or `None` if `entries` is empty. A tie (multiple entries sharing the
    single latest timestamp) is not a distinct case — the marker is still exactly
    that one (repeated) timestamp value, so no special-casing is needed beyond a
    plain max().

    Every `timestamp` in this project is ISO-8601 with a fixed UTC offset
    (`storage.runtime_io.append_action_log()`: `datetime.now(timezone.utc)
    .isoformat()`), so lexicographic string comparison already agrees with
    chronological order — no `datetime.fromisoformat()` parsing is required to
    find the maximum. This is itself part of the same unchanged source data G5 is
    already defined against, never a live `now()` read (§7's own rejected
    alternative B)."""
    if not entries:
        return None
    return max(entry["timestamp"] for entry in entries)


def filter_entries_by_day(entries: List[dict], day: date) -> List[dict]:
    """Return only the entries in `entries` whose own `timestamp` falls on the
    UTC calendar `day` — never wall-clock "today" (`Governance/
    ARCHITECTURE_DECISIONS.md` decision 27). Every `timestamp` is ISO-8601 UTC
    (see `compute_as_of_marker()`), so the calendar date is simply its first 10
    characters (`YYYY-MM-DD`) — no parsing into a full `datetime` is needed for a
    same-day comparison."""
    day_prefix = day.isoformat()
    return [entry for entry in entries if entry["timestamp"].startswith(day_prefix)]


def filter_entries_by_action(entries: List[dict], actions: Iterable[str]) -> List[dict]:
    """Return only the entries in `entries` whose `action` is in `actions` — the
    "by signal type" filter (e.g. `{"detect_duplicates_and_versions"}` for the
    Duplicate Report's own cross-referencing need, §13). `actions` accepts any
    iterable (a single-action list or a full multi-action set for a broader
    aggregation like Daily Summary's), never assuming a specific container type."""
    action_set = set(actions)
    return [entry for entry in entries if entry.get("action") in action_set]
