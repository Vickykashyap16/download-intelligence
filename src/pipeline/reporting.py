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

Disclosed, pre-existing exception: `storage.database.load_metadata_store()`
(WP-2's own call, `generate_daily_summary()`) inherits that function's
already-established `_ensure_metadata_store_exists()` convenience — a fresh
install with no `Database/Metadata/metadata_store.json` yet gets one created
holding `[]`. This is identical, byte-for-byte, to "no records recorded yet"
and creates/mutates zero FileRecord data; it is the same precedent every
earlier module's own read of the metadata store already relies on, not
something WP-2 introduces.

Single-layer batch-function architecture, no Engine/Provider split (§2/§9): four
report-generation functions, each following load -> filter -> aggregate -> render
-> write, calling storage/runtime_io.py's correspondingly-named write_*() function
(the raw-I/O layer) to actually persist rendered Markdown to Runtime/Reports/.

Named `reporting.py` instead of `logging.py` to avoid shadowing Python's stdlib
`logging` module.

Module 08 Implementation Plan.md status: WP-1 (scaffold reconciliation) implemented
the shared, pure aggregation primitives every generate_*() function needs — a
malformed-line-safe action-log reader (§12 Layer 1), a data-derived "as of"
recency marker (§7), and calendar-day/action-type action-log filters — leaving
all four generate_*() functions as signature-only stubs. WP-2 implemented
`generate_daily_summary()`'s real aggregation/rendering logic against those
primitives plus `storage.database.load_metadata_store()` (§5). WP-3 implemented
`generate_duplicate_report()`'s real aggregation/rendering logic — a single,
continuously-updated current-state file per decision 25, using
`compute_as_of_marker()` (unlike WP-2, which doesn't need it) since this report
type has no period concept of its own. WP-4 has since implemented
`generate_weekly_summary()`'s real roll-up logic — reads already-written Daily
Summary files (never the metadata store), with a narrow action-log exception
solely to disambiguate a missing day; inherits closed-period (G6/I6) protection
transitively from Daily Summary's own per-day guarantee rather than
implementing an independent week-boundary mechanism. `generate_storage_report()`
(WP-5) remains a stub — not implemented here.

This file replaces the pre-existing `write_daily_summary()`/`write_weekly_summary()`/
`write_duplicate_report()`/`write_storage_report()`-named stubs that used to live
here, which took a `batch`/`records` pair each — a shape from the superseded,
per-batch-triggered architecture (§0.6) that cannot represent the real, date/week/
whole-store-scoped aggregation the frozen design actually specifies (§5). See
`Module 08 Implementation Plan.md Review.md` finding F1 for the full reasoning.
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from src.storage import database, runtime_io


# --- Report generation (stubs — WP-2 through WP-5's own implementation scope) ---

def generate_daily_summary(report_date: date) -> str:
    """Aggregate `report_date`'s action-log entries and the current metadata
    store into Runtime/Reports/Daily Summary/summary_YYYY-MM-DD.md, matching
    `Metadata & Log Schema.md`'s worked example field-for-field (§3, §6), and
    return the path written. Module 08 Implementation Plan.md WP-2's own scope.

    Field derivation (each traces to a real, cited source — G3/I5):
    - "Files scanned": count of `discover` entries that day (Module 01).
    - "Auto-filed" / "Approval required" / "Review required": counts of
      `score_confidence` entries that day by `details.tier` — Module 08
      Design.md §13's own explicit statement that Module 06's score_confidence
      entries are "the primary source for auto/approval-required/
      review-required breakdowns in the Daily Summary."
    - "Duplicates found": count of `detect_duplicates_and_versions` entries
      that day with a non-null `details.duplicate_of` (excludes pure version
      relationships, which carry `version_group_id`/`version_rank` instead).
      Parenthetical disposition counts same-day `archive_duplicate` entries.
    - "Versions archived": count of `archive_superseded_version` entries that
      day; each one's detail cross-references the metadata store for the
      archived file's `original_name` and its version-group sibling with
      `version_rank == "latest"`. Disclosed interpretation: the worked
      example's abbreviated "superseded by v9" is rendered here as the
      sibling's full `original_name` (e.g. "superseded by Resume_v9.pdf")
      rather than an inferred short label, since no field anywhere stores a
      short version label, and inventing one would violate G3.
    - "Errors": count of `error` entries that day.
    - "## Files" table: one row per distinct file_id with a `move_rename` /
      `archive_duplicate` / `archive_superseded_version` entry that day (i.e.
      every file actually filed today), in first-seen action-log order for
      determinism (G5). Columns are read from that file_id's current
      FileRecord (`storage.database.load_metadata_store()`, per §5's explicit
      dual-source statement: Daily Summary receives both the action log and
      the metadata store). "New Name"/"Destination" are read from
      `suggested_name`/`suggested_destination` — Module 05's own fields,
      already relative-path-shaped — rather than reconstructed from
      `current_path`, which would require destination-root-resolution logic
      that is not part of WP-2's certified, single-file scope. A missing
      field on a referenced FileRecord renders as "Unknown", never a
      fabricated value (§12 Layer 1's third bullet).

    No "as of" marker is included — the worked example has none; a calendar
    day is already its own unambiguous scope, unlike the Duplicate/Storage
    Report's continuously-updated current-state shape (decision 25) that
    `compute_as_of_marker()` exists for.

    Closed-day protection (§11, `ARCHITECTURE_DECISIONS.md` decision 27, G6):
    if `report_date` is before today (UTC) and that day's file already
    exists, it is never recomputed or rewritten — the existing path is
    returned unchanged. A closed day with no file yet (a legitimate
    first-time-late generation) still computes and writes normally. Today's
    file (still "open", §11) is always recomputed and overwritten in place —
    this is `write_daily_summary()`'s own already-tested WP-1 behavior, not a
    new mechanism.
    """
    today = datetime.now(timezone.utc).date()
    existing_path = _daily_summary_path(report_date)
    if report_date < today and existing_path.exists():
        return str(existing_path)

    all_entries, malformed_count = read_action_log_entries_safe()
    day_entries = filter_entries_by_day(all_entries, report_date)

    records_by_id: Dict[str, "database.FileRecord"] = {
        record.file_id: record for record in database.load_metadata_store()
    }

    files_scanned = len(filter_entries_by_action(day_entries, {"discover"}))

    score_entries = filter_entries_by_action(day_entries, {"score_confidence"})
    auto_filed = _count_by_tier(score_entries, "auto")
    approval_required = _count_by_tier(score_entries, "approval_required")
    review_required = _count_by_tier(score_entries, "review_required")

    errors = len(filter_entries_by_action(day_entries, {"error"}))

    duplicate_entries = filter_entries_by_action(day_entries, {"detect_duplicates_and_versions"})
    duplicates_found = sum(
        1 for entry in duplicate_entries if entry.get("details", {}).get("duplicate_of") is not None
    )
    duplicates_archived = len(filter_entries_by_action(day_entries, {"archive_duplicate"}))

    archived_version_entries = filter_entries_by_action(day_entries, {"archive_superseded_version"})
    versions_archived = len(archived_version_entries)
    version_detail_parts = [
        _render_version_archived_detail(records_by_id.get(entry.get("file_id")), records_by_id)
        for entry in archived_version_entries
    ]

    filed_entries = filter_entries_by_action(
        day_entries, {"move_rename", "archive_duplicate", "archive_superseded_version"}
    )
    seen_file_ids: List[str] = []
    for entry in filed_entries:
        file_id = entry.get("file_id")
        if file_id not in seen_file_ids:
            seen_file_ids.append(file_id)
    table_rows = [_render_file_row(records_by_id.get(file_id)) for file_id in seen_file_ids]

    content = _render_daily_summary(
        report_date=report_date,
        files_scanned=files_scanned,
        auto_filed=auto_filed,
        approval_required=approval_required,
        review_required=review_required,
        duplicates_found=duplicates_found,
        duplicates_archived=duplicates_archived,
        versions_archived=versions_archived,
        version_detail_parts=version_detail_parts,
        errors=errors,
        malformed_count=malformed_count,
        table_rows=table_rows,
    )
    return runtime_io.write_daily_summary(report_date, content)


# --- generate_daily_summary() helpers (WP-2) ---

def _daily_summary_path(report_date: date) -> Path:
    """Read-only path reconstruction, used only for the closed-day existence
    check above — never to open or write the file directly (the actual write
    still goes exclusively through `runtime_io.write_daily_summary()`).
    Mirrors that function's own path formula (Module 08 Design.md §6) via its
    already-existing `_RUNTIME_REPORTS_PATH` constant, rather than adding a
    new public path-accessor function to `storage/runtime_io.py` — WP-2's
    certified scope is "Files expected to change: reporting.py... only"."""
    return runtime_io._RUNTIME_REPORTS_PATH / "Daily Summary" / f"summary_{report_date.isoformat()}.md"


def _count_by_tier(score_confidence_entries: List[dict], tier: str) -> int:
    """Count `score_confidence` entries whose `details.tier` matches `tier`."""
    return sum(1 for entry in score_confidence_entries if entry.get("details", {}).get("tier") == tier)


def _field_or_unknown(value) -> str:
    """§12 Layer 1's third bullet: a missing/empty field on a referenced
    FileRecord renders as an explicit "Unknown", never a fabricated value."""
    if value is None or value == "":
        return "Unknown"
    return str(value)


def _render_version_archived_detail(record, records_by_id: Dict[str, "database.FileRecord"]) -> str:
    """Render one "<original name> → superseded by <latest sibling's original
    name>" detail for the "Versions archived" line. `record` is the archived
    file's own current FileRecord; its version-group sibling with
    `version_rank == "latest"` is looked up by shared `version_group_id`."""
    if record is None:
        return "Unknown"
    original_name = _field_or_unknown(record.original_name)
    latest_sibling = None
    if record.version_group_id:
        for other in records_by_id.values():
            if other.version_group_id == record.version_group_id and other.version_rank == "latest":
                latest_sibling = other
                break
    latest_name = _field_or_unknown(latest_sibling.original_name) if latest_sibling else "Unknown"
    return f"{original_name} → superseded by {latest_name}"


def _render_file_row(record) -> str:
    """Render one "## Files" table row from a FileRecord — Original, New Name
    (`suggested_name`), Destination (`suggested_destination`), Category,
    Confidence, Tier. A wholly-missing record (referenced by the action log
    but absent from the metadata store) renders every cell as "Unknown"."""
    if record is None:
        return "| Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |"
    category = record.category.value if record.category else "Unknown"
    return "| {} | {} | {} | {} | {} | {} |".format(
        _field_or_unknown(record.original_name),
        _field_or_unknown(record.suggested_name),
        _field_or_unknown(record.suggested_destination),
        category,
        _field_or_unknown(record.confidence_score),
        _field_or_unknown(record.tier),
    )


def _render_daily_summary(
    report_date: date,
    files_scanned: int,
    auto_filed: int,
    approval_required: int,
    review_required: int,
    duplicates_found: int,
    duplicates_archived: int,
    versions_archived: int,
    version_detail_parts: List[str],
    errors: int,
    malformed_count: int,
    table_rows: List[str],
) -> str:
    """Render the Daily Summary Markdown body, matching
    `Metadata & Log Schema.md`'s worked example field-for-field."""
    lines = [f"# Daily Summary — {report_date.isoformat()}", ""]
    lines.append(f"- Files scanned: {files_scanned}")
    lines.append(f"- Auto-filed: {auto_filed}")
    lines.append(f"- Approval required: {approval_required}")
    lines.append(f"- Review required: {review_required}")

    if duplicates_found == 0:
        lines.append("- Duplicates found: 0")
    elif duplicates_archived == duplicates_found:
        lines.append(f"- Duplicates found: {duplicates_found} (archived)")
    else:
        lines.append(f"- Duplicates found: {duplicates_found} ({duplicates_archived} archived)")

    if versions_archived == 0:
        lines.append("- Versions archived: 0")
    else:
        lines.append(f"- Versions archived: {versions_archived} ({'; '.join(version_detail_parts)})")

    lines.append(f"- Errors: {errors}")

    # G3: a malformed line is never silently absorbed into a lower count —
    # disclosed only when it actually occurs, so a normal day's output still
    # matches the worked example exactly (which has no such line).
    if malformed_count > 0:
        lines.append(f"- Malformed log lines skipped: {malformed_count}")

    lines.append("")
    lines.append("## Files")
    lines.append("| Original | New Name | Destination | Category | Confidence | Tier |")
    lines.append("|---|---|---|---|---|---|")
    lines.extend(table_rows)
    lines.append("")
    return "\n".join(lines)


_DAILY_SUMMARY_FIELD_LABELS = {
    "Files scanned": "files_scanned",
    "Auto-filed": "auto_filed",
    "Approval required": "approval_required",
    "Review required": "review_required",
    "Duplicates found": "duplicates_found",
    "Versions archived": "versions_archived",
    "Errors": "errors",
}


def generate_weekly_summary(report_week: date) -> str:
    """Roll up the ISO week containing `report_week` from already-written Daily
    Summary files into Runtime/Reports/Weekly Summary/summary_YYYY-Www.md (§3,
    §9) and return the path written. Module 08 Implementation Plan.md WP-4's
    own scope.

    Reads already-rendered Daily Summary Markdown files (§9: "reads already-
    written Daily Summary files rather than re-deriving a week's aggregation
    from the raw action log directly... keeps Weekly Summary consistent with
    whatever Daily Summary already reported for each day") — never the
    metadata store at all (§5's own precise Weekly Summary source statement
    names only Daily Summary files, plus the one narrow action-log exception
    below; unlike Daily Summary/Duplicate Report, Weekly Summary never calls
    `storage.database.load_metadata_store()`).

    Per-day handling, for each of the requested ISO week's 7 calendar days:
    - **Not yet closed** (`day >= today`, UTC): excluded entirely from the
      roll-up — never read, never included in totals (§11: "never generated
      from a still-open, current day's partial data"). Still listed in the
      "## Days" table (with "-" placeholders) so the week's full 7-day shape
      is always visible, never silently truncated — a disclosed extension of
      G3's "never fabricate, always disclose" principle to this case, which
      §12 Layer 1 doesn't separately name (it only names the closed-but-
      missing-file case below).
    - **Closed, Daily Summary file exists:** parsed and included in the
      week's totals, per-day counts shown in the table ("Reported").
    - **Closed, no Daily Summary file, day has action-log entries** (§12
      Layer 1's L1 fix): "Report unavailable for this date" — a reporting
      gap, never silently treated as zero. Excluded from totals (the real
      figures are genuinely unknown, not zero — G3).
    - **Closed, no Daily Summary file, day has zero action-log entries**
      (§12 Layer 1's L1 fix): "No activity" — a real, known zero, shown as
      such in the table and included in totals (contributing 0, which is
      the honest, traceable figure, not a placeholder).

    The action log (via WP-1's `read_action_log_entries_safe()`/
    `filter_entries_by_day()`) is consulted *solely* for this missing-day
    disambiguation — never to recompute or re-derive a day's actual figures,
    which always come from that day's own already-rendered Daily Summary
    file when one exists (§5's own "narrow, disclosed exception... a
    read-scope exception, not a write-ownership one").

    No closed-period (G6/I6) protection of any kind is implemented here, by
    design, not omission: a fully-closed week's only inputs (7 individually
    G6-protected Daily Summary files, per WP-2's own already-audited closed-
    day check) can never change again, so re-generating that week's file is
    guaranteed to reproduce byte-identical content — G5/G6/I6 compliance for
    a closed week is inherited transitively from Daily Summary's own
    protection, not something this function separately implements or
    decides. A still-open week (spanning today) legitimately produces
    different content as more days close, exactly mirroring Daily Summary's
    own "still open, not a G6 violation" carve-out (§11). Confirmed during
    the WP-4 pre-implementation architecture audit — no new Architecture
    Decision introduced, no independent week-boundary mechanism built.
    """
    today = datetime.now(timezone.utc).date()
    iso_year, iso_week, _ = report_week.isocalendar()
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    week_days = [week_start + timedelta(days=offset) for offset in range(7)]

    all_entries, malformed_count = read_action_log_entries_safe()

    totals = {field: 0 for field in _DAILY_SUMMARY_FIELD_LABELS.values()}
    day_rows: List[Tuple[date, str, Optional[Dict[str, int]]]] = []
    for day in week_days:
        if day >= today:
            day_rows.append((day, "Not yet closed", None))
            continue

        summary_path = _daily_summary_file_path(day)
        if summary_path.exists():
            counts = _parse_daily_summary_counts(summary_path.read_text(encoding="utf-8"))
            for field, value in counts.items():
                totals[field] += value
            day_rows.append((day, "Reported", counts))
        else:
            day_entries = filter_entries_by_day(all_entries, day)
            if day_entries:
                day_rows.append((day, "Report unavailable for this date", None))
            else:
                zero_counts = {field: 0 for field in _DAILY_SUMMARY_FIELD_LABELS.values()}
                day_rows.append((day, "No activity", zero_counts))

    content = _render_weekly_summary(
        iso_year=iso_year,
        iso_week=iso_week,
        week_start=week_days[0],
        week_end=week_days[-1],
        totals=totals,
        day_rows=day_rows,
        malformed_count=malformed_count,
    )
    return runtime_io.write_weekly_summary(report_week, content)


# --- generate_weekly_summary() helpers (WP-4) ---

def _daily_summary_file_path(day: date) -> Path:
    """Read-only path reconstruction for checking whether `day`'s Daily
    Summary file exists — WP-4's own lookup, mirroring
    `generate_daily_summary()`'s own `_daily_summary_path()` helper (WP-2),
    deliberately not shared, to keep this package's diff isolated from
    already-audited WP-2 code (the same disclosed precedent WP-3's
    `_find_latest_sibling_name()` already established over WP-2's own
    `_render_version_archived_detail()`). Read-only — this file is only ever
    opened for reading here, never written; the actual Weekly Summary write
    still goes exclusively through `runtime_io.write_weekly_summary()`."""
    return runtime_io._RUNTIME_REPORTS_PATH / "Daily Summary" / f"summary_{day.isoformat()}.md"


def _parse_daily_summary_counts(content: str) -> Dict[str, int]:
    """Parse a Daily Summary file's own already-committed bullet format
    (`- <Label>: <N>...`, WP-2's `_render_daily_summary()`) back into a
    `{field_name: count}` dict, reading only the leading integer of each
    value and ignoring any parenthetical disposition detail (e.g. "1
    (archived)", "1 (Resume_v8.pdf → superseded by Resume_v9.pdf)") — this
    function only needs the count, never the detail. A label this function
    doesn't recognize (e.g. an optional "Malformed log lines skipped" line)
    is silently skipped, not an error. A recognized label with no parseable
    leading digit defaults to 0 for that field alone, matching §12 Layer 1's
    general "handled defensively rather than assumed impossible" philosophy
    for a file this module itself always renders correctly under normal
    operation."""
    counts = {field: 0 for field in _DAILY_SUMMARY_FIELD_LABELS.values()}
    for line in content.splitlines():
        if not line.startswith("- ") or ": " not in line:
            continue
        label, _, value = line[2:].partition(": ")
        field = _DAILY_SUMMARY_FIELD_LABELS.get(label)
        if field is None:
            continue
        leading_digits = ""
        for character in value:
            if character.isdigit():
                leading_digits += character
            else:
                break
        counts[field] = int(leading_digits) if leading_digits else 0
    return counts


def _render_weekly_summary(
    iso_year: int,
    iso_week: int,
    week_start: date,
    week_end: date,
    totals: Dict[str, int],
    day_rows: List[Tuple[date, str, Optional[Dict[str, int]]]],
    malformed_count: int,
) -> str:
    """Render the Weekly Summary Markdown body. No committed worked example
    exists for this report type (unlike Daily Summary) — this format is a
    disclosed, reasonable design choice, matching the project's established
    header/bullets/table style and `Runtime/Reports/README.md`'s own
    "totals, trends... any recurring error" framing (the per-day breakdown
    columns, not just a status column, are what make a trend actually
    visible)."""
    lines = [f"# Weekly Summary — {iso_year}-W{iso_week:02d}", ""]
    lines.append(f"- Week range: {week_start.isoformat()} to {week_end.isoformat()}")
    lines.append(f"- Files scanned: {totals['files_scanned']}")
    lines.append(f"- Auto-filed: {totals['auto_filed']}")
    lines.append(f"- Approval required: {totals['approval_required']}")
    lines.append(f"- Review required: {totals['review_required']}")
    lines.append(f"- Duplicates found: {totals['duplicates_found']}")
    lines.append(f"- Versions archived: {totals['versions_archived']}")
    lines.append(f"- Errors: {totals['errors']}")

    if malformed_count > 0:
        lines.append(f"- Malformed log lines skipped: {malformed_count}")

    lines.append("")
    lines.append("## Days")
    lines.append(
        "| Date | Status | Files scanned | Auto-filed | Approval required "
        "| Review required | Duplicates found | Versions archived | Errors |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for day, status, counts in day_rows:
        if counts is None:
            lines.append(f"| {day.isoformat()} | {status} | - | - | - | - | - | - | - |")
        else:
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    day.isoformat(), status,
                    counts["files_scanned"], counts["auto_filed"], counts["approval_required"],
                    counts["review_required"], counts["duplicates_found"], counts["versions_archived"],
                    counts["errors"],
                )
            )
    lines.append("")
    return "\n".join(lines)


_DISPOSITION_ACTIONS = {"move_rename", "archive_duplicate", "archive_superseded_version", "reject", "undo"}
_RELEVANT_DUPLICATE_REPORT_ACTIONS = _DISPOSITION_ACTIONS | {"detect_duplicates_and_versions"}


def generate_duplicate_report() -> str:
    """Aggregate every duplicate/superseded-version record in the metadata
    store into Runtime/Reports/Duplicate Report/duplicate_report.md — a
    single, continuously-updated current-state file, always overwritten in
    place (§3/§6, `ARCHITECTURE_DECISIONS.md` decision 25) — and return the
    path written. Module 08 Implementation Plan.md WP-3's own scope.

    Signal-bearing record definition (§3: "every duplicate_of/
    version_group_id/version_rank-bearing record"): a record is included if
    `duplicate_of is not None` (a genuine duplicate) or `version_rank ==
    "superseded"` (a superseded version). Disclosed interpretation: a
    "latest"-ranked version record, despite carrying a non-null
    `version_group_id`, is the surviving file in its group, not itself a
    duplicate or superseded item needing its own disposition row — it is
    referenced only as the "Related To" value of its superseded sibling's own
    row, never included as a first-class row itself. A literal reading of
    "version_group_id-bearing" would wrongly include it and miscategorize a
    perfectly ordinary `move_rename` of the surviving file as "Overridden by
    user", which is not what happened.

    Disposition categorization — three categories per `Runtime/Reports/
    README.md`/§6 ("archived, kept, overridden by the user"), determined by
    the LAST chronological execution-type action-log entry for that file_id
    (mirrors decision 25's own "always-current view" philosophy — an earlier
    archive later undone is correctly re-classified as Kept, not Archived,
    rather than reporting a stale disposition):
    - `archive_duplicate` / `archive_superseded_version` → "Archived" — the
      system's default duplicate/superseded-version override actually ran.
    - `move_rename` → "Overridden by user" — the record was duplicate/
      version-flagged, yet filed through the *ordinary* path instead of the
      archive override; per `ARCHITECTURE_DECISIONS.md` decision 23, this can
      only happen when a human's edited destination intentionally overrode
      the automatic archive placement (`move_rename`'s own `details.
      override_applied` is `null`, unlike `archive_duplicate`/
      `archive_superseded_version`, confirming no override branch fired).
    - `reject`, `undo`, or no execution-type entry at all → "Kept" — the
      record was never filed anywhere (still awaiting a decision, explicitly
      declined, or an executed disposition was since reversed), so it is
      still sitting wherever it already was.

    "As of" marker (§7, option D — chosen specifically because this report
    type has no period concept of its own, unlike Daily Summary, §7's own
    "relevant chiefly to... a continuously-updated Duplicate/Storage Report"
    reasoning): the latest timestamp among only the entries this report
    actually consulted (`detect_duplicates_and_versions` plus the five
    disposition action types, scoped to signal-bearing file_ids) — never the
    whole, possibly-unrelated action log.

    Every count and row traces to a real action-log entry or metadata-store
    field (G3/I5); reads only `duplicate_of`/`version_group_id`/
    `version_rank` off each FileRecord, never `Database/FileIndex/*` or
    `Database/History/*` directly (§8). No closed-period protection of any
    kind — this report type is always fully recomputed and overwritten
    (decision 25's own explicit consequence: "no G6/closed-period test case
    for these two report types").
    """
    all_entries, malformed_count = read_action_log_entries_safe()

    records = database.load_metadata_store()
    records_by_id: Dict[str, "database.FileRecord"] = {record.file_id: record for record in records}
    signal_bearing_records = [
        record for record in records
        if record.duplicate_of is not None or record.version_rank == "superseded"
    ]
    signal_bearing_ids = {record.file_id for record in signal_bearing_records}

    last_disposition_action: Dict[str, str] = {}
    relevant_entries: List[dict] = []
    for entry in all_entries:
        action = entry.get("action")
        file_id = entry.get("file_id")
        if action in _DISPOSITION_ACTIONS:
            last_disposition_action[file_id] = action
        if file_id in signal_bearing_ids and action in _RELEVANT_DUPLICATE_REPORT_ACTIONS:
            relevant_entries.append(entry)

    as_of = compute_as_of_marker(relevant_entries)

    duplicates_count = sum(1 for record in signal_bearing_records if record.duplicate_of is not None)
    versions_count = sum(1 for record in signal_bearing_records if record.version_rank == "superseded")

    archived_count = 0
    kept_count = 0
    overridden_count = 0
    table_rows: List[str] = []
    for record in signal_bearing_records:
        disposition = _categorize_disposition(last_disposition_action.get(record.file_id))
        if disposition == "Archived":
            archived_count += 1
        elif disposition == "Overridden by user":
            overridden_count += 1
        else:
            kept_count += 1
        table_rows.append(_render_duplicate_report_row(record, records_by_id, disposition))

    content = _render_duplicate_report(
        as_of=as_of,
        total=len(signal_bearing_records),
        duplicates_count=duplicates_count,
        versions_count=versions_count,
        archived_count=archived_count,
        kept_count=kept_count,
        overridden_count=overridden_count,
        malformed_count=malformed_count,
        table_rows=table_rows,
    )
    return runtime_io.write_duplicate_report(content)


# --- generate_duplicate_report() helpers (WP-3) ---

def _categorize_disposition(last_action: Optional[str]) -> str:
    """Map a signal-bearing record's own LAST chronological execution-type
    action-log entry (or `None`) to one of the three disposition categories
    `Runtime/Reports/README.md` names."""
    if last_action in ("archive_duplicate", "archive_superseded_version"):
        return "Archived"
    if last_action == "move_rename":
        return "Overridden by user"
    return "Kept"


def _find_latest_sibling_name(record, records_by_id: Dict[str, "database.FileRecord"]) -> Optional[str]:
    """For a superseded-version record, find its version-group sibling with
    `version_rank == "latest"` and return that sibling's `original_name`, or
    `None` if no such sibling is found (WP-3's own lookup — deliberately not
    shared with WP-2's identically-shaped `_render_version_archived_detail()`
    helper, to keep this package's diff isolated from already-audited WP-2
    code)."""
    if not record.version_group_id:
        return None
    for other in records_by_id.values():
        if other.version_group_id == record.version_group_id and other.version_rank == "latest":
            return other.original_name
    return None


def _render_duplicate_report_row(record, records_by_id: Dict[str, "database.FileRecord"], disposition: str) -> str:
    """Render one "## Records" table row — Original, Type (Duplicate /
    Superseded Version), Related To (the other file this record relates to),
    Disposition."""
    if record.duplicate_of is not None:
        record_type = "Duplicate"
        related_record = records_by_id.get(record.duplicate_of)
        related_name = _field_or_unknown(related_record.original_name if related_record else None)
    else:
        record_type = "Superseded Version"
        related_name = _field_or_unknown(_find_latest_sibling_name(record, records_by_id))
    return "| {} | {} | {} | {} |".format(
        _field_or_unknown(record.original_name), record_type, related_name, disposition,
    )


def _render_duplicate_report(
    as_of: Optional[str],
    total: int,
    duplicates_count: int,
    versions_count: int,
    archived_count: int,
    kept_count: int,
    overridden_count: int,
    malformed_count: int,
    table_rows: List[str],
) -> str:
    """Render the Duplicate Report Markdown body. No committed worked example
    exists for this report type (unlike Daily Summary) — this format is a
    disclosed, reasonable design choice, matching the project's established
    header/bullets/table style and the exact vocabulary §6/`Runtime/Reports/
    README.md` already fix (archived/kept/overridden by the user)."""
    lines = ["# Duplicate Report", ""]
    lines.append(f"- As of: {as_of if as_of is not None else 'no activity recorded yet'}")
    lines.append(f"- Records tracked: {total} ({duplicates_count} duplicates, {versions_count} superseded versions)")
    lines.append(f"- Archived: {archived_count}")
    lines.append(f"- Kept: {kept_count}")
    lines.append(f"- Overridden by user: {overridden_count}")

    if malformed_count > 0:
        lines.append(f"- Malformed log lines skipped: {malformed_count}")

    lines.append("")
    lines.append("## Records")
    lines.append("| Original | Type | Related To | Disposition |")
    lines.append("|---|---|---|---|")
    lines.extend(table_rows)
    lines.append("")
    return "\n".join(lines)


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
