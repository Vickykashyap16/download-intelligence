"""
Entry point for Downloads Intelligence.

Usage: `python -m src.main` (run from the project root, so the `src.` package
imports resolve correctly).

Module 01 (Watch & Ingest), Module 02 (Classification), Module 03 (Metadata
Extraction), Module 04 (Duplicate & Version Detection), Module 05 (Naming &
Destination), and Module 06 (Confidence & Review) are implemented and wired in
below. Module 07 (Preview, Approval & Execution)'s core batch functions
(preview_batch()/execute_batch()/undo_batch()) are also wired in below as
CLI-facing functions (preview()/execute()/undo() — WP-12, Module 07
Implementation Plan.md). The actual human-approval interaction mechanism (Open
Decision OD-3, Module 07 Design.md §2/§26) remains unresolved: execute() accepts
an externally-supplied ApprovalDecision set as a parameter rather than collecting
one itself, mirroring classify(provider=...)/extract(provider=...)'s own
"supplied by the live session, not hardcoded" precedent. Unlike scan() through
score_confidence(), execute() and undo() are deliberately NOT part of the
automatic `python -m src.main` chain at the bottom of this file — execute()
causes real filesystem moves, and undo() requires a batch_id — invoking either
is left as an explicit, separate operator action.

Module 08 (Logging & Reporting)'s report() (WP-6, Module 08 Implementation
Plan.md) is also wired in below, as the sole CLI entry point for all four
report-generation functions (Governance/ARCHITECTURE_DECISIONS.md decision 26:
"a single report() call invokes all four generate_*() functions in one pass").
Like execute()/undo(), report() is deliberately NOT part of the automatic
chain at the bottom of this file (decision 31) — reports summarize completed
execution results, and running report() before execute() would produce
technically correct but systematically premature output (an honest zero for
every not-yet-executed file, misleadingly presented as "today's" activity).
"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import yaml

from src.models.execution import ApprovalDecision, ApprovalDecisionType
from src.pipeline.classification import classify_batch
from src.pipeline.confidence import score_confidence_batch
from src.pipeline.duplicate_detector import detect_duplicates_batch, needs_duplicate_detection
from src.pipeline.execution import (
    capture_user_correction,
    execute_batch,
    preview_batch,
    undo_batch,
)
from src.pipeline.metadata import extract_metadata_batch
from src.pipeline.naming import suggest_naming_and_destination_batch
from src.pipeline.reporting import (
    generate_daily_summary,
    generate_duplicate_report,
    generate_storage_report,
    generate_weekly_summary,
)
from src.pipeline.watch_ingest import load_source_config, scan_source
from src.storage.database import (
    load_metadata_store,
    metadata_store_path,
    save_file_record,
)
from src.storage.runtime_io import action_log_path

# Module 07's destination library root config file (Open Decision OD-1, resolved
# as Governance/ARCHITECTURE_DECISIONS.md decision 20). No Module 07 work
# package's own "Owned components" list ever named the actual config key/reader
# as its own scope — resolve_destination_path() (WP-2) and execute_batch()
# (WP-9) both take `library_root` as a caller-supplied parameter, neither reads
# config itself. Disclosed as WP-12's own small addition below
# (_load_destination_root()): CLI startup is the one place that must turn "a
# library root exists somewhere" into a concrete value, mirroring this same
# file's load_source_config() import above for the source side.
_SOURCES_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "sources.yaml"

# Mirrors src/pipeline/execution.py's own _MOVE_LOG_ACTIONS action-value set
# ({"move_rename", "archive_duplicate", "archive_superseded_version"}) — not
# imported directly since that name is a private (underscore-prefixed) module
# constant; redeclared here as this file's own disclosed copy for CLI summary
# purposes only (execute()'s log read-back), never used to make any execution
# decision.
_EXECUTION_MOVE_ACTIONS = frozenset(
    {"move_rename", "archive_duplicate", "archive_superseded_version"}
)
_EXECUTION_OUTCOME_ACTIONS = _EXECUTION_MOVE_ACTIONS | {"reject", "error"}

# Human-readable label for each SkippedEntry.reason value (see watch_ingest.py's
# SkippedEntry docstring for the canonical list). Falls back to the raw reason string
# for anything not listed here, so an unrecognized future reason still prints instead
# of being hidden.
_SKIP_REASON_LABELS = {
    "symlink": "symlink (never followed — may point outside the source folder)",
    "directory": "a folder (v1 only scans the top level, not subfolders)",
    "system_file": "OS/system junk file (e.g. .DS_Store, Thumbs.db)",
    "temporary_download": "in-progress/partial download (e.g. .crdownload, .part)",
    "ignored_pattern": "matches an ignored pattern",
    "zero_byte": "empty file (0 bytes) — likely an incomplete/failed download",
    "unstable": "still changing size — mid-write, will be re-checked next scan",
    "unsupported_extension": "file type not yet supported by this pipeline",
}


def _describe_reason(reason: str) -> str:
    """Human-readable text for a SkippedEntry.reason, including the "error: ..."
    catch-all scan_source() uses for a single bad entry that raised unexpectedly."""
    if reason in _SKIP_REASON_LABELS:
        return _SKIP_REASON_LABELS[reason]
    if reason.startswith("error:"):
        return f"unexpected error — {reason[len('error:'):].strip()}"
    return reason


def scan() -> None:
    """Run Module 01 only: load the source config, scan it, persist every discovered
    record, and print a complete summary — total entries scanned, discovered count,
    skipped count with human-readable reasons, and where the generated metadata/log
    files live. Later pipeline stages (classification onward) are not yet implemented.
    """
    source_config = load_source_config()
    result = scan_source(source_config["path"], source_config["source_id"])
    for record in result.records:
        save_file_record(record)

    total = len(result.records) + len(result.skipped)

    print(f"Scanned {source_config['path']}")
    print(f"  Total entries seen: {total}")
    print(f"  Discovered:         {len(result.records)}")
    print(f"  Skipped:            {len(result.skipped)}")

    if result.records:
        print("\nDiscovered files:")
        for record in result.records:
            note = f" [{record.status}: {record.error}]" if record.status == "unreadable" else ""
            print(f"  - {record.original_name} ({record.extension}, {record.size_bytes} bytes){note}")

    if result.skipped:
        print("\nSkipped items:")
        for entry in result.skipped:
            print(f"  - {Path(entry.path).name} — {_describe_reason(entry.reason)}")

    print(f"\nMetadata written to:    {metadata_store_path()}")
    print(f"Action log written to: {action_log_path()}")
    print("\nModule 01 complete.")


def classify(provider=None) -> None:
    """Run Module 02 on every record in the metadata store that Module 01 discovered
    but nothing has classified yet, persist the results, and print a summary.

    `provider` defaults to `None`, which makes `classify_batch()` fall back to
    `ClaudeLiveClassifier` (its own default — see pipeline/classification.py).
    IMPORTANT: `ClaudeLiveClassifier.classify()` is a documented placeholder, not
    autonomous code (see its docstring) — running this function outside a live
    Claude-driven session means every file needing the text/vision deep pass will
    fall back to Category.UNKNOWN (fallback_reason: "provider_exception"), not
    silently produce real categories. This is expected, safe behavior, not a defect.
    A real (UAT/production) run supplies live judgment by passing an explicit
    provider built during that session — e.g. `classify(provider=my_live_provider)`
    — instead of relying on this function's default. This optional parameter is the
    only change this CLI wiring needed to support that documented pattern; it does
    not change default behavior for a normal, non-live invocation.
    """
    records = [
        record for record in load_metadata_store()
        if record.status == "discovered" and record.category is None
    ]
    if not records:
        print("Nothing to classify — no discovered-but-unclassified records in the metadata store.")
        return

    file_ids = {record.file_id for record in records}
    classify_batch(records, provider=provider)

    # mode/fallback/provider detail lives in the action log, not on FileRecord itself
    # (design §12 scopes that detail to the log, not the persisted record) — read it
    # back for an accurate summary rather than guessing from FileRecord's fields.
    log_details_by_file_id = _read_classify_log_details(file_ids)

    category_counts = Counter(record.category.value for record in records if record.category)
    mode_counts = Counter(
        log_details_by_file_id[record.file_id]["mode"]
        for record in records if record.file_id in log_details_by_file_id
    )
    fallback_count = sum(
        1 for details in log_details_by_file_id.values() if details.get("fallback_used")
    )

    print(f"Classified {len(records)} file(s):")
    for record in records:
        note = ""
        if record.classification_signals and record.classification_signals.locked:
            note = " [locked]"
        print(f"  - {record.original_name}: {record.category.value}{note}")

    print("\nBy category:")
    for category_value, count in sorted(category_counts.items()):
        print(f"  - {category_value}: {count}")

    print("\nBy mode:")
    for mode, count in sorted(mode_counts.items()):
        print(f"  - {mode}: {count}")

    if fallback_count:
        print(f"\n{fallback_count} file(s) fell back to Unknown (provider unavailable/invalid response).")

    print(f"\nMetadata written to: {metadata_store_path()}")
    print(f"Action log written to: {action_log_path()}")
    print("\nModule 02 complete.")


def extract(provider=None) -> None:
    """Run Module 03 on every record in the metadata store that Module 02 assigned
    a real, non-Unknown category to but nothing has extracted metadata for yet,
    persist the results, and print a summary. Mirrors `classify()`'s exact shape.

    `provider` defaults to `None`, which makes `extract_metadata_batch()` fall back
    to `ClaudeLiveExtractor` (its own default — see pipeline/metadata.py).
    IMPORTANT: `ClaudeLiveExtractor.extract()` is a documented placeholder, not
    autonomous code (see its docstring) — running this function outside a live
    Claude-driven session means every judgment-dependent field falls back to
    `null` (fallback_reason: "provider_exception"), not silently produce real
    values. This is expected, safe behavior, not a defect. A real (UAT/production)
    run supplies live judgment by passing an explicit provider — e.g.
    `extract(provider=my_live_provider)` — instead of relying on this function's
    default.
    """
    records = [
        record for record in load_metadata_store()
        if record.status == "discovered"
        and record.category is not None
        and record.category.value != "Unknown"
        and record.extracted_metadata == {}
    ]
    if not records:
        print("Nothing to extract — no classified-but-unextracted records in the metadata store.")
        return

    file_ids = {record.file_id for record in records}
    extract_metadata_batch(records, provider=provider)

    log_details_by_file_id = _read_action_log_details(file_ids, action="extract_metadata")

    mode_counts = Counter(
        log_details_by_file_id[record.file_id]["mode"]
        for record in records if record.file_id in log_details_by_file_id
    )
    fallback_count = sum(
        1 for details in log_details_by_file_id.values() if details.get("fallback_used")
    )
    incomplete_count = sum(
        1 for details in log_details_by_file_id.values()
        if details.get("extraction_complete") is False
    )
    provider_call_count = sum(1 for details in log_details_by_file_id.values() if "provider_metadata" in details)

    print(f"Extracted metadata for {len(records)} file(s):")
    for record in records:
        details = log_details_by_file_id.get(record.file_id, {})
        redacted = details.get("redacted_fields") or []
        note = f" [redacted: {', '.join(redacted)}]" if redacted else ""
        note += " [incomplete]" if details.get("extraction_complete") is False else ""
        print(f"  - {record.original_name}: {record.category.value}{note}")

    print("\nBy mode:")
    for mode, count in sorted(mode_counts.items()):
        print(f"  - {mode}: {count}")

    print(f"\nProvider was called {provider_call_count} time(s).")
    if fallback_count:
        print(f"{fallback_count} file(s) fell back (provider unavailable/extraction failed).")
    if incomplete_count:
        print(f"{incomplete_count} file(s) have incomplete extraction (a required field is missing).")

    print(f"\nMetadata written to: {metadata_store_path()}")
    print(f"Action log written to: {action_log_path()}")
    print("\nModule 03 complete.")


def detect_duplicates() -> None:
    """Run Module 04 on every `status == "discovered"` record nothing has run
    duplicate/version detection on yet, persist the results, and print a summary.

    Unlike `classify()`/`extract()`, this takes no `provider` parameter — Module 04
    is fully deterministic, with no Provider layer at all (Module 04 Design.md §14).
    Also unlike them, the filter below does not require a real, non-Unknown
    `category` — exact-duplicate detection runs on every discovered record
    regardless of category (§3/§9), so gating on category here would silently skip
    files this module is specifically designed to still cover.

    The "not yet processed" check itself is `needs_duplicate_detection()`, not a
    bare field-null check — see that function's docstring for why (§7, post-freeze
    correction #2): checking `duplicate_of`/`version_group_id`/`version_rank`
    directly would re-select every record Module 04 already correctly found
    nothing for, on every single run, forever.
    """
    records = [
        record for record in load_metadata_store()
        if record.status == "discovered" and needs_duplicate_detection(record)
    ]
    if not records:
        print("Nothing to check — no discovered records still awaiting duplicate/version detection.")
        return

    file_ids = {record.file_id for record in records}
    detect_duplicates_batch(records)

    log_details_by_file_id = _read_action_log_details(file_ids, action="detect_duplicates_and_versions")

    exact_count = sum(1 for r in records if r.duplicate_of is not None)
    fuzzy_count = sum(
        1 for r in records if r.duplicate_signals and r.duplicate_signals.fuzzy_duplicate
    )
    version_count = sum(1 for r in records if r.version_group_id is not None)
    conflict_count = sum(
        1 for r in records if r.duplicate_signals and r.duplicate_signals.version_conflict
    )

    print(f"Checked {len(records)} file(s) for duplicates/versions:")
    for record in records:
        note = ""
        if record.duplicate_of is not None:
            note = f" [exact duplicate of {record.duplicate_of}]"
        elif record.version_group_id is not None:
            note = f" [{record.version_rank}, version_group_id={record.version_group_id}]"
        elif record.duplicate_signals and record.duplicate_signals.fuzzy_duplicate:
            note = f" [near-duplicate, phash_distance={record.duplicate_signals.phash_distance}]"
        details = log_details_by_file_id.get(record.file_id, {})
        if details.get("conflict_type"):
            note += f" [conflict: {details['conflict_type']}]"
        print(f"  - {record.original_name}{note}")

    print(f"\nExact duplicates:  {exact_count}")
    print(f"Near-duplicates:   {fuzzy_count}")
    print(f"Version chains:    {version_count}")
    if conflict_count:
        print(f"Conflicts flagged: {conflict_count} (never auto-resolved — see action log)")

    print(f"\nMetadata written to: {metadata_store_path()}")
    print(f"Action log written to: {action_log_path()}")
    print("\nModule 04 complete.")


def suggest_naming() -> None:
    """Run Module 05 on every `status == "discovered"` record with a real category
    that hasn't had a name/destination suggested yet, persist the results, and
    print a summary. Mirrors `classify()`/`extract()`'s exact shape.

    Unlike `classify()`/`extract()`, this takes no `provider` parameter — Module 05
    is fully deterministic, with no Provider layer at all (Module 05 Design.md §17,
    confirmed §29 item 11). Unlike `extract()`, the filter below does NOT exclude
    `Category.UNKNOWN` — Module 05 must include it (§3): `Rules/Folder Rules.md`'s
    own override table always routes Unknown-category files to `Unknown/`.

    The "not yet processed" check is a direct `suggested_name is None` field check,
    not a Module-04-style dedicated idempotency function — mirrors `classify()`'s
    `category is None`/`extract()`'s `extracted_metadata == {}` precedent, since
    `suggested_name` is unambiguously null only pre-processing and always a real,
    non-empty string afterward (Module 05 Design.md §5's guarantee) — no
    "legitimately stays null forever" case exists here the way it does for Module
    04's `duplicate_of`/`version_group_id`/`version_rank`.
    """
    records = [
        record for record in load_metadata_store()
        if record.status == "discovered"
        and record.category is not None
        and record.suggested_name is None
    ]
    if not records:
        print("Nothing to name — no discovered, classified records still awaiting a suggested name/destination.")
        return

    file_ids = {record.file_id for record in records}
    suggest_naming_and_destination_batch(records)

    log_details_by_file_id = _read_action_log_details(file_ids, action="suggest_naming_and_destination")

    fallback_count = sum(
        1 for r in records if r.naming_signals and r.naming_signals.fields_fell_back
    )
    collision_count = sum(
        1 for details in log_details_by_file_id.values() if details.get("collision_suffix_applied")
    )
    override_counts = Counter(
        details.get("override_applied") for details in log_details_by_file_id.values()
        if details.get("override_applied")
    )

    print(f"Suggested a name/destination for {len(records)} file(s):")
    for record in records:
        note = ""
        if record.naming_signals and record.naming_signals.fields_fell_back:
            note = f" [fallback: {', '.join(record.naming_signals.fields_fell_back)}]"
        print(f"  - {record.original_name} -> {record.suggested_destination}{record.suggested_name}{note}")

    if fallback_count:
        print(f"\n{fallback_count} file(s) used a naming fallback for at least one field.")
    if collision_count:
        print(f"{collision_count} file(s) got a collision suffix (another record in this batch suggested the same name/destination).")
    for override, count in sorted(override_counts.items()):
        if override:
            print(f"{count} file(s) routed via override: {override}")

    print(f"\nMetadata written to: {metadata_store_path()}")
    print(f"Action log written to: {action_log_path()}")
    print("\nModule 05 complete.")


def score_confidence() -> None:
    """Run Module 06 on every `status == "discovered"` record that has a real
    category and a suggested name but hasn't been scored yet, persist the
    results, and print a summary. Mirrors `suggest_naming()`'s exact shape.

    Unlike `classify()`/`extract()`, this takes no `provider` parameter — Module
    06 is fully deterministic, with no Provider layer at all (Module 06
    Design.md §2, confirmed). The eligibility filter below is the per-record
    filter defined in Design.md §11 step 1 (status/category/suggested_name);
    `confidence_score is None` is this function's own CLI-level idempotency
    check — mirroring `suggest_naming()`'s `suggested_name is None` precedent —
    so a second run doesn't re-score a record already scored (§11, §24).
    """
    records = [
        record for record in load_metadata_store()
        if record.status == "discovered"
        and record.category is not None
        and record.suggested_name is not None
        and record.confidence_score is None
    ]
    if not records:
        print("Nothing to score — no discovered, named records still awaiting a confidence score.")
        return

    file_ids = {record.file_id for record in records}
    score_confidence_batch(records)

    log_details_by_file_id = _read_action_log_details(file_ids, action="score_confidence")

    tier_counts = Counter(record.tier for record in records if record.tier)
    hard_floor_count = sum(
        1 for details in log_details_by_file_id.values() if details.get("hard_floors_applied")
    )

    print(f"Scored {len(records)} file(s):")
    for record in records:
        details = log_details_by_file_id.get(record.file_id, {})
        floors = details.get("hard_floors_applied") or []
        note = f" [hard floor: {', '.join(floors)}]" if floors else ""
        print(f"  - {record.original_name}: {record.confidence_score} ({record.tier}){note}")

    print("\nBy tier:")
    for tier, count in sorted(tier_counts.items()):
        print(f"  - {tier}: {count}")

    if hard_floor_count:
        print(f"\n{hard_floor_count} file(s) had at least one hard floor applied.")

    print(f"\nMetadata written to: {metadata_store_path()}")
    print(f"Action log written to: {action_log_path()}")
    print("\nModule 06 complete.")


def _eligible_for_execution_records() -> list:
    """The §5 CLI-level eligibility filter for Module 07 (Module 07 Design.md §5):
    every `status == "discovered"` record with `category`/`suggested_name`/
    `confidence_score` all populated (i.e. `tier` populated — confirming the full
    Module 01→06 chain already ran) AND `processed_at is None` — mirroring every
    earlier module's own CLI-level idempotency check (e.g. `score_confidence()`'s
    `confidence_score is None`), so a record already successfully executed in a
    prior run is never re-selected (§13A).

    Shared by `preview()` and `execute()` so both apply the exact same filter —
    `execute()` still reloads fresh from the metadata store itself rather than
    reusing any list `preview()` built, since time may have passed between the
    two calls (see `execute()`'s own docstring).
    """
    return [
        record for record in load_metadata_store()
        if record.status == "discovered"
        and record.category is not None
        and record.suggested_name is not None
        and record.confidence_score is not None
        and record.processed_at is None
    ]


def _load_destination_root() -> Optional[Path]:
    """Reads `destination_root` from `src/config/sources.yaml` (Open Decision
    OD-1, resolved as `Governance/ARCHITECTURE_DECISIONS.md` decision 20) — see
    this file's own module docstring / the `_SOURCES_CONFIG_PATH` comment above
    for why this reader lives here rather than in an already-approved Module 07
    work package or in Module 01's `watch_ingest.py`.

    Deliberately returns `None` (never raises) when `destination_root` is
    missing or still `null` — unlike `load_source_config()`'s own "raise a
    clear error if unset" style for the *source* side. This is a disclosed,
    intentional difference, not an inconsistency: `execute_batch()`'s own
    already-approved `_validate_library_root()` (WP-9, §14's closing
    paragraph) already treats `library_root is None` as exactly this batch's
    precondition failure — it logs one `error` action-log entry per eligible
    record explaining the whole batch was blocked, and returns cleanly, never
    raising. Raising here instead would duplicate a decision WP-9 already owns
    (an ownership-boundary concern the WP-12 architecture review flagged and
    resolved by favoring "read config, pass it through" over "read config,
    also decide what an invalid value means").
    """
    with open(_SOURCES_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    destination_root = config.get("destination_root")
    if not destination_root:
        return None
    return Path(destination_root)


def preview() -> None:
    """Run Module 07's preview stage (WP-12, Module 07 Design.md §9/§10 step 1)
    on every record `_eligible_for_execution_records()` selects. Read-only:
    `preview_batch()` (WP-3) performs zero filesystem/log/Database writes, and
    this CLI wrapper performs none either — printing only.

    Groups rows by tier, mirroring §10 step 1's grouping exactly: `auto`
    pre-checked (will execute without further input), `approval_required`
    unchecked (needs a recorded `ApprovalDecision`), `review_required` shown
    separately as "needs your attention" (never pre-filed, no dedicated folder,
    `Rules/Folder Rules.md`).

    Does not collect approval decisions itself — per Open Decision OD-3 (Module
    07 Design.md §2/§26), that interaction mechanism is explicitly out of this
    function's scope. Producing an `ApprovalDecision` set is the caller's job —
    see `execute()`'s own docstring for the same "supplied by the live session,
    not hardcoded" pattern already established by
    `classify(provider=...)`/`extract(provider=...)`.
    """
    records = _eligible_for_execution_records()
    if not records:
        print("Nothing to preview — no discovered, scored records still awaiting execution.")
        return

    rows = preview_batch(records)
    rows_by_tier = {"auto": [], "approval_required": [], "review_required": []}
    for row in rows:
        rows_by_tier.setdefault(row.tier, []).append(row)

    print(f"Previewing {len(rows)} file(s):")

    if rows_by_tier["auto"]:
        print(f"\nAuto (will execute without further input) — {len(rows_by_tier['auto'])}:")
        for row in rows_by_tier["auto"]:
            print(f"  - {row.original_name} -> {row.suggested_destination}{row.suggested_name}")

    if rows_by_tier["approval_required"]:
        print(f"\nNeeds your decision — {len(rows_by_tier['approval_required'])}:")
        for row in rows_by_tier["approval_required"]:
            note = f" [{row.override}]" if row.override else ""
            print(
                f"  - {row.file_id}: {row.original_name} -> "
                f"{row.suggested_destination}{row.suggested_name}{note}"
            )

    if rows_by_tier["review_required"]:
        print(f"\nNeeds attention (never auto-filed) — {len(rows_by_tier['review_required'])}:")
        for row in rows_by_tier["review_required"]:
            print(
                f"  - {row.file_id}: {row.original_name} "
                f"(suggested: {row.suggested_destination}{row.suggested_name})"
            )

    print(f"\nMetadata store: {metadata_store_path()}")
    print("\nModule 07 preview complete — no files have been moved.")


def execute(decisions: Optional[Dict[str, ApprovalDecision]] = None) -> None:
    """Run Module 07's execution stage (WP-12, Module 07 Design.md §9/§10 step 3)
    on every record `_eligible_for_execution_records()` selects, reloaded fresh
    here — never trusting an earlier `preview()` call's snapshot, since time may
    have passed and another run may have changed eligibility.

    `decisions` defaults to `{}` (no `ApprovalDecision` for any
    `approval_required` record — every such record, and every `review_required`
    record, is safely left unchanged by `evaluate_gate()`'s own "absent decision
    is never treated as consent" rule, WP-4/§13). A real (interactive) run
    supplies an externally-built decisions set — e.g.
    `execute(decisions=my_live_decisions)` — the same "supplied by the live
    session, not hardcoded" pattern `classify(provider=...)`/
    `extract(provider=...)` already established; producing that set (the actual
    Open Decision OD-3 interaction) is explicitly out of this function's scope
    (Module 07 Design.md §2/§26) — this parameter is the only change this CLI
    wiring needed to support that documented pattern, mirroring the `provider`
    parameter precedent exactly.

    For every decision that is `APPROVE_WITH_EDIT` or `REJECT`, captures the
    correction to `Database/Learning/User Corrections.json` via
    `capture_user_correction()` (WP-10, §19/G7) — before `execute_batch()` runs,
    per §10 step 2's explicit "at this step, before execution" ordering.
    `capture_user_correction()` itself decides whether an edit is a no-op
    resubmission (its own established WP-10 logic); this function does not
    duplicate that judgment, it only decides *which* decisions to hand it
    (anything other than `APPROVE_AS_SUGGESTED` — a mechanical presence/type
    check on an already-made decision, not a business decision about the file).

    Resolves `library_root` from `destination_root` in `src/config/sources.yaml`
    via `_load_destination_root()` — a disclosed WP-12 addition (see that
    function's own docstring).

    Prints a batch-level summary (§10 step 4): counts by tier, then
    executed/declined/failed/skipped, read back from the action log — the same
    "reconstruct from the authoritative log" pattern
    `classify()`/`extract()`/`detect_duplicates()`/`suggest_naming()`/
    `score_confidence()` already use, rather than re-deriving an outcome from
    `FileRecord` fields alone (which don't distinguish "declined" from "still
    awaiting a decision," for example).
    """
    if decisions is None:
        decisions = {}

    records = _eligible_for_execution_records()
    if not records:
        print("Nothing to execute — no discovered, scored records still awaiting execution.")
        return

    library_root = _load_destination_root()

    for record in records:
        decision = decisions.get(record.file_id)
        if decision is not None and decision.decision != ApprovalDecisionType.APPROVE_AS_SUGGESTED:
            capture_user_correction(record, decision)

    batch_id = records[0].batch_id
    file_ids = {record.file_id for record in records}
    tier_by_file_id = {record.file_id: record.tier for record in records}

    records = execute_batch(records, decisions, library_root)

    log_action_by_file_id = _read_execution_log_actions(file_ids, batch_id)

    executed_count = sum(
        1 for action in log_action_by_file_id.values() if action in _EXECUTION_MOVE_ACTIONS
    )
    declined_count = sum(1 for action in log_action_by_file_id.values() if action == "reject")
    failed_count = sum(1 for action in log_action_by_file_id.values() if action == "error")
    skipped_count = len(file_ids) - executed_count - declined_count - failed_count

    tier_counts = Counter(tier_by_file_id.values())

    print(f"Executed batch {batch_id} ({len(records)} eligible file(s)):")

    print("\nBy tier:")
    for tier, count in sorted(tier_counts.items()):
        print(f"  - {tier}: {count}")

    print(f"\nExecuted: {executed_count}")
    if declined_count:
        print(f"Declined:  {declined_count}")
    if failed_count:
        print(f"Failed:    {failed_count}")
    if skipped_count:
        print(f"Skipped (review_required or no decision yet): {skipped_count}")

    print(f"\nMetadata written to: {metadata_store_path()}")
    print(f"Action log written to: {action_log_path()}")
    print("\nModule 07 execution complete.")


def undo(batch_id: str) -> None:
    """Manually reverses every undoable action-log entry for `batch_id`
    (WP-11's `undo_batch()`, Module 07 Design.md §15) — a separate, explicitly
    -invoked CLI command, never called automatically from `execute()` or
    anywhere else in this module (§15: undo is a manual operation only, never
    an automatic on-failure recovery step).

    Prints a per-file outcome summary (`UNDONE` / `SKIPPED_IRREVERSIBLE` /
    `SKIPPED_MISSING` / `SKIPPED_COLLISION` / `SKIPPED_NO_RECORD` / `FAILED`,
    WP-11's own `UndoOutcome` vocabulary) — this function does not decide any
    of these outcomes itself, only reports what `undo_batch()` already decided.
    """
    report = undo_batch(batch_id)

    if not report.outcomes:
        print(f"Nothing to undo for batch {batch_id} — no move-type action-log entries found.")
        return

    print(f"Undo results for batch {batch_id} ({len(report.outcomes)} entrie(s)):")
    for file_id, outcome in report.outcomes.items():
        print(f"  - {file_id}: {outcome.value}")

    outcome_counts = Counter(outcome.value for outcome in report.outcomes.values())
    print("\nBy outcome:")
    for outcome_value, count in sorted(outcome_counts.items()):
        print(f"  - {outcome_value}: {count}")

    print(f"\nMetadata written to: {metadata_store_path()}")
    print(f"Action log written to: {action_log_path()}")
    print("\nUndo complete.")


def report() -> None:
    """Run Module 08's report generation (WP-6, Module 08 Design.md §10;
    Governance/ARCHITECTURE_DECISIONS.md decisions 25/26/28/29/30/31): invoke
    all four generate_*() functions in one pass and print a CLI summary.

    A separate, explicitly-invoked command — deliberately NOT part of the
    automatic chain at the bottom of this file (decision 31, mirroring
    execute()/undo()'s own precedent): reports summarize completed execution
    results, and running this before execute() would produce systematically
    premature Daily Summary output.

    Layer 2's outer safety net (Module 08 Design.md §12): each of the four
    report types is generated independently, in its own try/except — one
    report type's failure never prevents the other three from being
    attempted, and never propagates to fail this command as a whole. This is
    also, by construction, never able to affect anything Module 07 already
    did (G4/I4): report() never touches Database/* or the action log, only
    Runtime/Reports/*, so there is no shared state through which a report
    failure could reach backward.

    Daily Summary/Weekly Summary are scoped to UTC "today"/the ISO week
    containing it — the same `datetime.now(timezone.utc).date()` convention
    those two functions already use internally (decision 27). Duplicate
    Report/Storage Report take no scoping parameter (decision 25) — both are
    single, continuously-updated current-state files.
    """
    today = datetime.now(timezone.utc).date()

    written: Dict[str, str] = {}
    failed: Dict[str, str] = {}

    try:
        written["Daily Summary"] = generate_daily_summary(today)
    except Exception as exc:  # Layer 2's own outer safety net, §12
        failed["Daily Summary"] = str(exc)

    try:
        written["Weekly Summary"] = generate_weekly_summary(today)
    except Exception as exc:  # Layer 2's own outer safety net, §12
        failed["Weekly Summary"] = str(exc)

    try:
        written["Duplicate Report"] = generate_duplicate_report()
    except Exception as exc:  # Layer 2's own outer safety net, §12
        failed["Duplicate Report"] = str(exc)

    try:
        written["Storage Report"] = generate_storage_report()
    except Exception as exc:  # Layer 2's own outer safety net, §12
        failed["Storage Report"] = str(exc)

    print("Report generation:")
    for label in ("Daily Summary", "Weekly Summary", "Duplicate Report", "Storage Report"):
        if label in written:
            print(f"  - {label}: {written[label]}")
        else:
            print(f"  - {label}: FAILED — {failed[label]}")

    if failed:
        print(f"\n{len(failed)} report(s) failed to generate — see above; the rest were unaffected.")

    print("\nModule 08 report generation complete.")


def _read_execution_log_actions(file_ids: set, batch_id: str) -> dict:
    """Read back this batch's own move/reject/error action-log entries, keyed
    by `file_id` — used only to build `execute()`'s CLI summary from the
    authoritative log, mirroring `extract()`/`detect_duplicates()`/
    `suggest_naming()`/`score_confidence()`'s own established "read back from
    the log" pattern (`_read_action_log_details()` below). A separate helper
    rather than a call to `_read_action_log_details()` itself because this one
    matches against a *set* of action values, not a single one, and additionally
    filters by `batch_id` (multiple of Module 07's action values can legally
    appear for the same `file_id` across different batches after an undo +
    re-execute cycle, so filtering by this run's own `batch_id` avoids
    attributing a stale, earlier batch's outcome to this summary).

    A `file_id` with no matching entry here was left unchanged by the tier gate
    (`review_required`, or `approval_required` with no decision yet, WP-4/§13)
    — not an error, the correct and expected outcome for those records.
    """
    action_by_file_id = {}
    log_path = action_log_path()
    if not log_path.exists():
        return action_by_file_id
    for line in log_path.read_text(encoding="utf-8").strip().splitlines():
        entry = json.loads(line)
        if (
            entry.get("batch_id") == batch_id
            and entry.get("file_id") in file_ids
            and entry.get("action") in _EXECUTION_OUTCOME_ACTIONS
        ):
            action_by_file_id[entry["file_id"]] = entry["action"]
    return action_by_file_id


def _read_classify_log_details(file_ids: set) -> dict:
    """Read back this run's `classify` action-log entries for `file_ids`, keyed by
    file_id — used only to build the CLI summary from the authoritative log rather
    than reconstructing mode/fallback info from FileRecord fields that don't carry it.
    """
    return _read_action_log_details(file_ids, action="classify")


def _read_action_log_details(file_ids: set, action: str) -> dict:
    """Generic version of `_read_classify_log_details()`, parameterized by action
    type so `extract()` can reuse the same read-back-from-the-log pattern for
    `extract_metadata` entries instead of duplicating the loop."""
    details_by_file_id = {}
    log_path = action_log_path()
    if not log_path.exists():
        return details_by_file_id
    for line in log_path.read_text(encoding="utf-8").strip().splitlines():
        entry = json.loads(line)
        if entry.get("action") == action and entry.get("file_id") in file_ids:
            details_by_file_id[entry["file_id"]] = entry.get("details", {})
    return details_by_file_id


if __name__ == "__main__":
    scan()
    classify()
    extract()
    detect_duplicates()
    suggest_naming()
    score_confidence()
