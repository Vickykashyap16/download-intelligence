"""
Entry point for Downloads Intelligence.

Usage: `python -m src.main` (run from the project root, so the `src.` package
imports resolve correctly).

Module 01 (Watch & Ingest), Module 02 (Classification), Module 03 (Metadata
Extraction), Module 04 (Duplicate & Version Detection), Module 05 (Naming &
Destination), and Module 06 (Confidence & Review) are implemented and wired in
below. Everything past confidence/review (the actual move/file step onward) is
still scaffold.
"""

import json
from collections import Counter
from pathlib import Path

from src.pipeline.classification import classify_batch
from src.pipeline.confidence import score_confidence_batch
from src.pipeline.duplicate_detector import detect_duplicates_batch, needs_duplicate_detection
from src.pipeline.metadata import extract_metadata_batch
from src.pipeline.naming import suggest_naming_and_destination_batch
from src.pipeline.watch_ingest import load_source_config, scan_source
from src.storage.database import (
    load_metadata_store,
    metadata_store_path,
    save_file_record,
)
from src.storage.runtime_io import action_log_path

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
