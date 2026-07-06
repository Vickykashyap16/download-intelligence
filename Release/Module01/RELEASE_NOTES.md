# Release Notes — Module 01 (Watch & Ingest)

```
Pipeline Version:  0.1.0
Module Version:    1.0.0
Date:              2026-07-06
Status:            Frozen, approved, production-ready
```

See `Release/VERSIONS.md` for how Pipeline Version and Module Version relate (each module versions independently; the pipeline number tracks overall project maturity, not a function of module numbers).

This is the first module of the Downloads Intelligence pipeline. It scans the top level of a configured source folder (Manual mode only, v1), filters out junk/in-progress/unsupported entries, assigns each supported file a permanent identity, hashes its contents, and hands a clean list of `FileRecord`s to whatever runs next — currently nothing, since Module 02 (Classification) doesn't exist yet.

## Features implemented

- Scans the top level of a configured source (`src/config/sources.yaml`, Manual mode only in v1 — `scheduled`/`watch_folder` are rejected with a clear error).
- Discovers supported file types: PDF, images (`.jpg`/`.jpeg`/`.png`/`.webp`/`.tiff`), `.docx`, `.txt`, `.zip`, video (`.mp4`/`.mov`/`.mkv`/`.avi`), audio (`.mp3`/`.wav`/`.m4a`/`.flac`), and application installers (`.dmg`/`.pkg`).
- Filters entries per `Rules/Ignore Rules.md`: OS/system junk, in-progress downloads, zero-byte files, mid-write (unstable) files, symlinks, directories, and unsupported extensions — each recorded with a specific reason rather than silently dropped.
- Collects raw file metadata for every discovered file: original name/path, current path, extension, MIME type (via stdlib `mimetypes`), size, creation/modification timestamps, and a SHA-256 content hash.
- Assigns a permanent `file_id` (UUID4) at first discovery — never derived from path or content — with re-identification via `current_path` so repeated manual scans are idempotent instead of piling up duplicate records.
- Detects unreadable/locked files (permission errors, etc.) without crashing — records `status: "unreadable"` and the underlying error, and keeps scanning the rest of the batch.
- Persists every discovered `FileRecord` to `Database/Metadata/metadata_store.json` — a cumulative, append/upsert store, never a per-scan snapshot.
- Writes an append-only action log (`Runtime/Logs/action_log.jsonl`) with one line per entry processed — `discover`, `skip`, or `error` — for full auditability and future undo support.
- CLI entry point (`python -m src.main`) prints a complete scan summary: total entries scanned, discovered/skipped counts, every skipped item with a human-readable reason, and the on-disk locations of the generated metadata and log files.

## Bugs fixed

- **Symlink following (security/data-integrity defect, found during validation, 2026-07-06).** A symlink inside the source folder pointing outside it was previously followed, hashed, and its external path recorded. Fixed: symlinks are now checked first and skipped unconditionally (reason `symlink`), before any `is_dir()`/content check runs. Regression test added.
- **`file_id` derived from filesystem path (design defect, caught in review before implementation was approved).** Original design hashed the absolute path for identity, which would have broken the moment Module 07 moves/renames a file. Redesigned to a permanent UUID4 assigned once at discovery, with `content_hash` and `current_path` as separate, independently-meaningful fields.
- **CLI showed discovered files only, never skipped items (UAT finding, 2026-07-06).** `main.py` only printed `build_ingest_queue()`'s return value, which deliberately excludes skipped entries — a real user had no way to see, from the terminal, what was ignored or why. Fixed: CLI now calls `scan_source()` directly and prints the full picture.
- **Generic `ignored_name` skip reason (UAT finding, 2026-07-06).** OS junk files and in-progress downloads were indistinguishable in the action log. Split into specific reasons: `system_file` and `temporary_download` (plus `ignored_pattern`, reserved for future pattern-based rules).
- **Import bug in the CLI rewrite (self-caught during UAT rerun, 2026-07-06).** First draft of the CLI fix imported `action_log_path` from the wrong module; caught by a real `ImportError` on rerun, fixed before the run was reported as complete.

## Breaking changes

- **`SkippedEntry.reason` vocabulary changed.** `"ignored_name"` no longer appears; replaced by `"system_file"` / `"temporary_download"` (plus the reserved, currently-unused `"ignored_pattern"`). No breaking impact today — Module 01 is the only consumer of this value so far — but any future code, dashboard, or report that pattern-matches on the literal string `"ignored_name"` will need updating to the new vocabulary. Documented in `Rules/Ignore Rules.md` and the schema doc.
- No other breaking changes. This is the first release of any pipeline module, so there is no prior public contract to break beyond the above.

## Improvements

- `metadata_store_path()` / `action_log_path()` public accessors added to `storage/database.py` / `storage/runtime_io.py`, so callers (the CLI, and future modules) don't need to reach into private path constants.
- `classify_ignored_name()` added alongside the original `is_ignored_name()` (kept as a thin bool wrapper — no existing caller broke).
- Documentation kept in sync throughout: `Rules/Ignore Rules.md`, `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`, `src/README.md`, and `Tests/Module 01 Validation & Test Plan.md` all updated to match the current code and reason vocabulary.
