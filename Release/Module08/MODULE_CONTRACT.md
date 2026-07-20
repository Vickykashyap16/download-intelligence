# Module Contract — Module 08 (Logging & Reporting)

The authoritative, tested statement of Module 08's INPUT/OUTPUT/guarantees/DOES NOT MODIFY (`ARCHITECTURE_DECISIONS.md` decision 15) — the module a future reader may depend on. Internal architecture (`reporting.py`'s private helpers, the exact rendering shape of each Markdown template) is not part of this contract and may change freely as long as the behavior below holds. Traces to `Build-out/08 Logging & Reporting/Module 08 Design.md` (frozen 2026-07-14) and its three post-freeze addenda, plus the full WP-1–7 implementation record (`Module 08 Implementation Plan.md`). See `Release/DEPENDENCY_DIAGRAM.md` and `Release/VERSIONS.md` for this module's position in the pipeline and its current version.

**Status note:** this contract describes Module 08's implemented, tested behavior as of WP-7, validated against the real Module 01→08 chain through Integration Testing (`Tests/Module 08 Integration Test Plan.md`, zero findings) and UAT (`Tests/Module 08 UAT Plan.md`, PASS WITH RECOMMENDATIONS — two disclosed non-blocking observations, no defect). Module 08 is released at v1.0.0 — see `RELEASE_AUDIT.md` for the full certification record.

## INPUT

**Receives (for Daily Summary and Duplicate Report):** the full contents of `Runtime/Logs/action_log.jsonl` (via `read_action_log_entries_safe()`, WP-1's malformed-line-safe wrapper over Module 07's `read_action_log_entries()`) and the full contents of `Database/Metadata/metadata_store.json` (via `storage.database.load_metadata_store()`) — not a `List[FileRecord]` handed in by a caller the way every earlier module receives one, since Module 08 summarizes everything recorded so far, scoped by time window (a day) or by signal type (duplicate/version presence), never a specific batch.

**Receives (for Weekly Summary):** already-written `Runtime/Reports/Daily Summary/` files for the requested week only, plus a narrow, disclosed exception — the raw action log, consulted solely to distinguish "genuinely no activity that day" from "that day's Daily Summary generation previously failed," never to re-derive a day's actual figures. Never reads the metadata store at all.

**Receives (for Storage Report):** `size_bytes`/`suggested_destination`/`category`/`processed_at` values already present on every `FileRecord` in `Database/Metadata/metadata_store.json` (`ARCHITECTURE_DECISIONS.md` decisions 29/30) — no filesystem walk, no destination-library read of any kind. Reads no action-log entries at all.

Every field this module reads traces to an explicit upstream guarantee:

- `discovered_at`, `status`, `error`, `source_id`, `discover`/`skip`/`error` action-log entries — Module 01's contract.
- `category`, `classification_signals`, `classify` action-log entries — Module 02's contract.
- `extract_metadata` action-log entries only (never `extracted_metadata`'s own field content — see DOES NOT MODIFY / privacy note below) — Module 03's contract.
- `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals`, `detect_duplicates_and_versions` action-log entries — Module 04's contract.
- `suggested_name`, `suggested_destination`, `suggest_naming_and_destination` action-log entries — Module 05's contract.
- `confidence_score`, `confidence_breakdown`, `tier`, `score_confidence` action-log entries — Module 06's contract.
- `current_path`, `processed_at`, `approved_by`, `approved_at`, `reversible`, `move_rename`/`archive_duplicate`/`archive_superseded_version`/`reject`/`error`/`undo` action-log entries — Module 07's contract.

**Also receives (internally):** nothing else. No provider, no human decision input, no configuration beyond the already-established `Database`/`Runtime` path constants — Module 08 does not read `destination_root` (Open Decision OD-4 resolved to metadata-store-only, decision 29, never exercising that conditional dependency).

## OUTPUT

**Produces / Guarantees:**
- `Runtime/Reports/Daily Summary/summary_YYYY-MM-DD.md` — one file per calendar day with reportable activity, closed once the day ends (decision 27) and never rewritten thereafter while still today, always recomputed and overwritten.
- `Runtime/Reports/Weekly Summary/summary_YYYY-Www.md` — one file per reported ISO week, rolled up from already-closed Daily Summary files.
- `Runtime/Reports/Duplicate Report/duplicate_report.md` — a single, continuously-updated current-state file, overwritten in place on every call (decision 25).
- `Runtime/Reports/Storage Report/storage_report.md` — a single, continuously-updated current-state file, overwritten in place on every call (decision 25).
- **No `FileRecord` field changes of any kind. No `Database/*` writes of any kind. No `Runtime/Logs/action_log.jsonl` writes of any kind.** Module 08 owns zero fields — the only module in the pipeline of which this is true.
- CLI-facing function `report()` in `src/main.py` (WP-6) — a standalone, explicitly-invoked command (never part of the automatic `if __name__ == "__main__":` chain, decision 31), invoking all four `generate_*()` functions in one pass, each independently isolated by its own `try`/`except` (Layer 2, §12) so one report type's failure never prevents the other three.

**Verified by:** `src/pipeline/test_reporting.py` (117 tests), `src/storage/test_runtime_io.py` (21 tests, Module 08's own `write_*()` functions and zero-write immutability), `src/test_main.py` (10 tests, `report()`'s CLI-level coverage) — see `TEST_RESULTS.md`.

## DOES NOT MODIFY

Every field owned by Modules 01–07, without exception: `file_id`, `source_id`, `original_name`, `original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `category`, `classification_signals`, `extracted_metadata`, `suggested_name`, `suggested_destination`, `naming_signals`, `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals`, `confidence_score`, `confidence_breakdown`, `tier`, `batch_id`, `processed_at`, `approved_by`, `approved_at`, `reversible`. Every one is read, none is ever rewritten — the cleanest ownership boundary of any module in the pipeline; unlike Module 04 (`version_group_id`/`version_rank` on another record) and Module 07 (`current_path`), Module 08 has zero disclosed exceptions.

Never writes to `Database/Metadata/metadata_store.json`, `Database/FileIndex/*.json`, `Database/History/version_history.json`, or `Database/Learning/User Corrections.json` — read via `load_metadata_store()` only, never via `save_file_record()` (confirmed structurally: `save_file_record` is never referenced anywhere in `reporting.py`). Never touches `Database/FileIndex/*`/`Database/History/*` directly at all — it reads Module 04's already-written `duplicate_of`/`version_group_id`/`version_rank` fields on each `FileRecord`, sufficient for the Duplicate Report, with no direct FileIndex/History access.

Never writes to `Runtime/Logs/action_log.jsonl` — read via `read_action_log_entries_safe()` only, never appended to. The single most important line in this contract: every earlier module writes to this file; Module 08 is the first and only module in the pipeline that reads it back as a primary data source without ever adding to it.

Never touches `Runtime/Temp/*` — Module 07's exclusively; Module 08 has no interaction with in-flight batch staging.

**Privacy note (structural, not merely behavioral):** `extracted_metadata` is loaded as part of every full `FileRecord` object (no partial-load mechanism exists in this codebase) but is never accessed for report content anywhere in `reporting.py` — confirmed by grep, zero matches. This resolves Module 03's field-privacy question structurally for Module 08's own reporting surface: there is nothing to leak because the field is never read for this purpose, not merely never displayed by convention.

## Provider boundary (internal architecture, not part of the external contract)

Module 08 has no Provider and no Engine/Provider pattern of any kind (`Module 08 Design.md` §2). There is no judgment call, no human decision, and no non-deterministic input anywhere in this module's scope — it reads only its own two already-fully-structured sources (the metadata store, the action log) and performs pure computation (counting, grouping, summing) over them. A single-layer, four-function shape: `generate_daily_summary(date)`, `generate_weekly_summary(week)`, `generate_duplicate_report()`, `generate_storage_report()`.

## Idempotency is unconditional, not a carve-out (G5)

Given an unchanged action log and metadata store, report generation always produces byte-for-byte identical output — same counts, same table rows, same totals, same everything — every time it runs, with no exception for a "generated at" timestamp of any kind. Where a report needs to convey how current its content is, it uses a data-derived "as of" marker (the latest included action-log entry's own `timestamp`, or for Storage Report the latest included record's own `processed_at` — `compute_as_of_marker()`), never a live `now()` read at render time. Both breakdown tables in the Storage Report are rendered in sorted key order for the same reason, regardless of the metadata store's own on-disk record order.

## A report-generation failure never affects a file operation that already happened (G4/I4)

By construction, not by reconciliation: Module 08 never touches `Database/*` or the action log at all, so there is no shared write path through which a `Runtime/Reports/` failure could reach backward into anything Module 07 already did. `report()`'s own four independent `try`/`except` blocks (Layer 2, §12) additionally isolate each report type's failure from the other three.
