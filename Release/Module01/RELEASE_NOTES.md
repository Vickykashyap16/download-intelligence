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

---

## Post-freeze correction #1 (2026-07-11) — re-scan of an already-processed file silently discarded Modules 02–06's work

**Severity:** Critical (`Governance/FROZEN_MODULE_CHANGE_POLICY.md` §2). **Module Version:** patched, `1.0.0` → `1.0.1` (patch-level: no change to this module's `MODULE_CONTRACT.md` INPUT/OUTPUT/guarantees shape — see the contract's own dated clarification for exactly what was newly disclosed).

**Discovered by:** Module 06 UAT's idempotency check (`Tests/Module 06 UAT Plan.md`, Finding UAT-1) — the first invocation in this project's history to call `scan()` a second time against a store already carrying real Module 02–06 output.

**Root cause:** `build_file_record()` always constructed a brand-new `FileRecord` object, even when re-identifying an already-tracked file via `find_by_current_path()`. Combined with `storage/database.py`'s `save_file_record()` whole-object-replace upsert, this silently reset every downstream-owned field (`category` through `reversible` — 17 fields, Modules 02–07's) to its default on every re-scan, regardless of whether the file's content had actually changed. An Independent Root Cause Analysis (performed fresh, not assuming the reporting UAT's own conclusion) confirmed this as primarily an implementation defect — `Release/Module01/MODULE_CONTRACT.md`'s DOES NOT MODIFY guarantee already applied, unqualified, to a re-scan; the code simply didn't deliver on a promise the contract already made.

**Fix:** `build_file_record()` now updates an already-tracked file's existing `FileRecord` in place for Module 01's own fields only, rather than reconstructing it — so downstream fields survive a re-scan untouched when content is unchanged. One disclosed, deliberate exception: if `content_hash` has genuinely changed, downstream fields are explicitly reset to their defaults (a new `_reset_downstream_owned_fields()` helper), so the record re-enters Modules 02–06's existing null-based reprocessing path exactly like a first-discovery record — the only mechanism anywhere in this pipeline that ever re-selects a record for processing. See `Build-out/01 Watch & Ingest/01 Watch & Ingest.md`'s "Post-freeze correction #1" for the full design rationale and `Release/Module01/MODULE_CONTRACT.md` for the matching contract clarification.

**Scope:** `src/pipeline/watch_ingest.py` only (`build_file_record()`, plus new `_reset_downstream_owned_fields()`). `storage/database.py`/`save_file_record()` and every other module's code confirmed untouched and unaffected — no shared-infrastructure change was needed or made.

**Regression tests added:** `test_build_file_record_preserves_downstream_fields_on_unchanged_rescan` (byte-for-byte field comparison, mirroring Modules 02–06's own Module Contract immutability test pattern) and `test_build_file_record_clears_downstream_fields_on_content_change`, both in `src/pipeline/test_watch_ingest.py`. Confirmed genuinely load-bearing via mutation testing: reconstructing the exact pre-fix code reproduces the reported symptom (`category` silently reset on an unchanged re-scan) against the first new test.

**Verification performed:** full regression suite 352/352 passing; the 337 tests outside `test_watch_ingest.py` confirmed to match the pre-fix baseline exactly (zero impact on Modules 02–06); `git status` confirmed only the four intended files touched; a targeted Independent Implementation Audit found the fix's 17-field reset list matches `FileRecord`'s real dataclass defaults exactly (verified programmatically, not by eye) and surfaced one Low-severity, pre-existing (not introduced by this fix), disclosed observation — see `KNOWN_LIMITATIONS.md`.

**Version ledger and gate re-run (2026-07-11, completed):** `Release/VERSIONS.md` updated to `1.0.1` with a dated History entry; the 13-check Pipeline Contract Verification gate (`Governance/PIPELINE_CONTRACT_VERIFICATION.md`) re-run fresh against the corrected module — 13/13 clean, including a fresh, real 75-file re-scan performance measurement (no regression) and full isolated test-suite re-runs for every downstream module (02–06, unchanged counts).

**`MODULE_STATUS.md` intentionally left unchanged.** During the gate re-run, `Release/Module01/MODULE_STATUS.md` was found still showing `Module Version: 1.0.0`, raising a genuine question: should it be updated to `1.0.1`? Resolved by checking the established convention across every existing `MODULE_STATUS.md` (Modules 02–05): each one explicitly self-labels "the permanent release record for Module NN," and each one's own `Pipeline Version` field stays fixed at whatever the pipeline's version was on its generation date — none were ever bumped forward as the pipeline later advanced (Module 02's still reads `0.2.0`, Module 05's still reads `0.5.0`, both against a current pipeline version of `0.5.0` that has since moved past Module 02's and matches Module 05's only coincidentally). This is a deliberate, consistently-applied pattern, not an oversight: `MODULE_STATUS.md` is a point-in-time snapshot, generated once at release and never revised, the same way a `CHANGELOG.md` entry correctly preserves what was true on its own date rather than being edited to stay current. Module 01's `MODULE_STATUS.md` therefore correctly continues to describe its `2026-07-06` original-freeze state, `Module Version: 1.0.0` included, and was not edited as part of this correction. `Release/VERSIONS.md` (this module's current, authoritative version — see its own "Versioning convention" section, clarified the same day for this exact reason) is where `1.0.1` is reflected.
