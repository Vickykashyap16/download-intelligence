# Final E2E Validation Report — Deterministic Mode

**Date:** 2026-07-26 · **Phase:** Final engineering phase before beta, Priority 3 ("one final end-to-end validation using the production workflow: scan, classify, extract, duplicate detection, naming, confidence scoring, preview, execute, undo, reports")

## 1. Scope and method

This is a single, final confirmation that the complete production workflow — every pipeline stage plus the real CLI's execute/undo/report surface — works correctly end-to-end, run in **deterministic-only mode** (`ai_provider_consent: false`, today's shipped default). TD-01's real-key provider judgment-quality validation is separately tracked and deferred (see `TECHNICAL_DEBT_REGISTER.md`'s 2026-07-26 update) — this validation exercises exactly what a beta user gets on first install, before ever touching `provider enable`.

**Method:** `Tests/Final Beta E2E Validation/run_e2e_validation.py` builds a small, synthetic, throwaway dataset (8 files: a JPEG and a byte-identical duplicate of it, an MP4, an MP3, a DMG, a real ZIP, an ambiguous `.txt`, and a `.DS_Store`), isolates both the config (`_SOURCES_CONFIG_PATH` in `src.main`/`src.cli`/`src.pipeline.watch_ingest`) and storage (`database_module`/`runtime_io_module`'s path constants) to temp directories, then drives the real `src.cli.main()` entry point — the exact function `python -m src.cli` calls — through `status → scan → run → preview → execute -y → undo --last → report → status`, verifying the real outcome at each stage against expectation. No reimplementation of pipeline logic; this is the same production code path a beta user's terminal invokes.

## 2. Result: clean pass, zero findings

After two isolation-gap fixes to the validation script itself (§3 below), a full run produced:

- **scan:** 7 discovered, 1 skipped (`.DS_Store` → `system_file`, confirmed via the action log).
- **run (classify → extract → duplicate detection → naming → confidence):** all 6 deterministic-category files (Image, Video, Audio, Application, Archive) classified correctly; the ambiguous `.txt` correctly fell back to `Category.UNKNOWN` / `review_required` — expected, disclosed TD-01 behavior, not a defect; the byte-identical duplicate pair was correctly flagged as an exact duplicate and routed to `~ARCHIVE~/Duplicates/`.
- **preview:** correctly split 2 auto-tier files from 5 needing attention, matching Module 06's own scores exactly.
- **execute -y:** correctly filed only the 2 auto-tier files (Video, Archive), left the 5 `review_required` files untouched — confirmed both by the log and by checking the filesystem directly (files physically present at the new path, gone from the old one).
- **undo --last:** correctly restored both moved files to their original location — confirmed on disk, not just in the log.
- **report:** all four reports (Daily Summary, Weekly Summary, Duplicate Report, Storage Report) generated without error.
- **status:** correct record/batch counts throughout.

Final run: **0 findings.** Full regression suite: **889/889**, unaffected (no production code was touched — see §3).

## 3. Two isolation gaps found and fixed in the validation script (tooling, not pipeline defects)

Because this script is the first one in the project to actually call `execute()`/`undo()`/`report()` for real (`run_harness.py` and `run_production_validation.py` only exercise classify/extract), it needed to isolate two additional path constants neither prior script needed. Both were missing on the first attempt and are now fixed:

- **`runtime_io_module._RUNTIME_TEMP_PATH`** — `execute()` stages `Runtime/Temp/<batch_id>/plan.json` for crash-reconciliation (Module 07/08). Missing this isolation caused the first run to write 3 real (harmless, synthetic-data-only) staging directories into the real project's `Runtime/Temp/`.
- **`runtime_io_module._RUNTIME_REPORTS_PATH`** — `report()` writes through this same constant (`src/pipeline/reporting.py` reads it directly). Missing this isolation caused `Runtime/Reports/Duplicate Report/duplicate_report.md` and `Runtime/Reports/Storage Report/storage_report.md` (real, pre-existing tracked files) to be overwritten with synthetic test content across several runs before being caught.

**Disposition:**
- Both constants are now isolated in `_isolate_storage()`/`_restore_storage()`; a clean re-run after the fix produced zero new writes to any real path (verified via `git status` before/after).
- The real Duplicate Report and Storage Report were regenerated for real (`python -m src.cli report`, against the real, never-touched `Database/`) and verified to contain zero synthetic filenames — real contamination fully reversed.
- The 3 stray `Runtime/Temp/<batch_id>/` directories from the first (pre-fix) run could **not** be deleted from this sandboxed session — `rm`, `chmod`, and `mv` all failed with `Operation not permitted` on the underlying `plan.json` files. This reproduces the previously-disclosed **TD-21** finding ("FUSE/sandbox filesystem blocked post-execution cleanup verification during UAT") in a new context, not a new defect. These 3 directories contain only synthetic test data (fake file paths under `/tmp`, no real file content, no real filenames) and are safe to delete manually via Finder on the real machine, where this sandbox restriction doesn't apply: `Runtime/Temp/2026-07-26_145254/`, `Runtime/Temp/2026-07-26_145323/`, `Runtime/Temp/2026-07-26_145348/`.
- Confirmed via `git diff`/timestamps that the pre-existing `Database/*` and `Runtime/Logs/action_log.jsonl` modifications visible in `git status` are unrelated to this validation — they're from the user's own earlier real TD-01 production validation run (timestamps ~19:40, hours before this validation), not touched by this script at any point (its `database_module`/`action_log` isolation was correct from the first run).

## 4. What this validation does and doesn't tell us

**Confirmed working, end-to-end, via the real CLI:** ingest/ignore-pattern handling, deterministic classification for every non-judgment category, exact-duplicate detection, naming/destination suggestion (including the duplicate-override routing path), confidence scoring and tiering, preview, selective auto-tier execution, full undo reversal, and report generation — all exactly as designed, with no code changes required.

**Not covered here (already covered elsewhere, not re-tested to keep this validation minimal):** the interactive `approval_required` decision loop (`execute` without `-y`) — already exercised in C1's and H5's own Product Acceptance Tests; real AI-provider judgment quality — separately tracked as TD-01's deferred post-beta validation; multi-file version-chain detection and naming collision re-resolution — already covered by Module 04/05/07's own dedicated test suites and UAT runs.

## 5. Verdict

The production workflow is correct end-to-end in deterministic mode, the shipped default. No pipeline defect was found. The only issues surfaced were in this validation script's own isolation (now fixed) — not in `src/main.py`, `src/cli.py`, or any pipeline module. Proceeding to the Beta Readiness Report.
