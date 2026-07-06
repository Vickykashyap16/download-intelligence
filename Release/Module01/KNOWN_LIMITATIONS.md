# Known Limitations — Module 01 (Watch & Ingest)

## Known limitations

- **Manual mode only.** `scheduled` and `watch_folder` execution modes are defined in `src/config/sources.yaml` but rejected with an error if selected — only on-demand manual scans work in v1.
- **Non-recursive.** Only the top level of the configured source folder is scanned; anything in a subfolder is invisible to the pipeline (confirmed by test — a nested file never appears in either discovered or skipped output).
- **No file-format validation.** Module 01 only reads raw bytes to compute a hash — it does not check that a `.pdf` is actually a valid PDF, that a `.jpg` is a real JPEG, etc. A malformed or truncated file with the "right" extension is discovered normally with `status: "discovered"`, not flagged as corrupt. Format validation is a later module's responsibility (`core/pdf.py`, `core/images.py`, Module 03).
- **No size floor/ceiling.** Every file that passes the ignore/stability/extension checks is processed regardless of size; very large files (multi-GB video/disk images) have not been performance-tested at that scale.
- **`find_by_current_path()` is a linear scan** of the full metadata store on every file processed. Fine at v1 volumes (hundreds of records); would need revisiting if the store grows into the thousands.
- **Sequential stability-check cost at volume.** Each file gets its own `is_stable()` check (default: one 0.5-second sleep). At realistic daily Downloads volumes this is a few seconds at most; measured at 38.12 seconds for a 75-file batch. Not a defect — v1 is Manual mode, triggered on demand — but the first thing worth optimizing if scan time ever becomes noticeable.
- **`is_stable()` has never been tested against a genuinely still-downloading file.** All validation used already-finished files; true "wait, re-check next pass" behavior against an actively-growing file hasn't been exercised.
- **Extension allowlist is narrower than the full classification taxonomy** in `Rules/Classification Rules.md` (e.g. no `.exe`/`.msi`) — deliberate v1 scope, not an oversight.
- **Test-harness nit (not a runtime defect):** `test_watch_ingest.py`'s `monkeypatch.setattr(..., "STABILITY_CHECK_INTERVAL_SECONDS", 0)` doesn't actually disable the real sleep, because `is_stable()`'s `interval_seconds` parameter is bound to the module constant's value at function-definition time, not read live. Harmless today (the suite still runs in ~1 second); flagged in `src/README.md` for whenever the test file is next touched.
- **One validation gap not yet executed:** action-log JSON safety against an adversarial filename (quotes/control characters) — `Tests/Module 01 Validation & Test Plan.md`, case M01-S05, needs one more dataset file before it can run.
- **Video/audio test data is placeholder binary, not real media.** Sufficient for Module 01 (byte-level hashing only) but will need replacing with real files before Module 03 (metadata extraction) can be validated against them.

## Intentional design decisions

- **`file_id` is a permanent UUID4, never derived from path or content.** Deliberately decoupled so Module 07 can move/rename files without breaking identity, and so two different files with identical bytes don't silently collide onto one record before Module 04 gets to decide what to do about the duplicate. See `CHANGELOG.md` for the full trade-off writeup.
- **Symlinks are always skipped, unconditionally.** Not a v1 requirement to support following them in any form; the security/data-integrity risk of an unbounded target outweighs any convenience.
- **`metadata_store.json` is cumulative, not a per-scan snapshot.** Every scan upserts into the full history; nothing from a prior batch is ever dropped by a later one.
- **No YAML mirrors of `Rules/*.md` in v1.** `Rules/` stays the single source of truth while business rules are still evolving; v1 code implements them directly in Python. Machine-readable config is deferred until the rules stabilize.
- **`ignored_pattern` reason exists but is currently unused.** Reserved for a future ignore rule that's neither an exact filename match nor a suffix match, so the reason taxonomy has somewhere to grow without another rename.
- **`build_ingest_queue()` still returns only the discovered records list**, not the full `IngestResult` — that contract is what Module 02 will consume. The CLI gets the full picture by calling `scan_source()` directly instead, so this module-to-module contract didn't need to change to fix the UAT's CLI-visibility finding.

## Deferred improvements for future modules

- `Database/FileIndex/` (hash/phash/name indexes) and duplicate/near-duplicate detection — Module 04.
- `Database/History/` (version lineage) — Module 04.
- `Database/Learning/User Corrections.json` — Module 07.
- `Runtime/Reports/` (Daily/Weekly Summary, Duplicate Report, Storage Report) — Module 08 (`reporting.py`).
- Actual file moves/renames and the undo mechanism (`storage/runtime_io.py`'s `undo_batch()`, `stage_batch_temp()`, `clear_batch_temp()`) — Module 07.
- Classification and content-based metadata extraction (the "judgment" modules) — Modules 02 and 03.
- `scheduled` / `watch_folder` execution modes, multiple sources (Desktop, Google Drive, OneDrive, Dropbox) — see `ROADMAP.md` Version 2/3.
- Injectable base paths for `storage/database.py` / `storage/runtime_io.py` instead of hardcoded project-relative constants — quality-of-life fix, not urgent at current module count.
- Fixing the `is_stable()` default-argument test-harness nit described above.
- Executing M01-S05 (adversarial filename in the action log) once the one missing test-data file is added.
