# Test Results — Module 07 (Preview, Approval & Execution)

Unit-level results below are real, freshly re-run for this release pass (2026-07-13), not carried forward from an earlier point in the implementation. Integration Testing and UAT have both since been executed to completion against the real Module 01→07 chain — see their own sections below and `RELEASE_AUDIT.md` for the full certification record.

## Unit tests

Full regression suite: **568/568 passing**, re-run fresh immediately before this document was written.

| File | Tests | Owner |
|---|---|---|
| `src/pipeline/test_watch_ingest.py` | 15 | Module 01 |
| `src/pipeline/test_classification.py` | 48 | Module 02 |
| `src/pipeline/test_metadata.py` | 57 | Module 03 |
| `src/pipeline/test_duplicate_detector.py` | 47 | Module 04 |
| `src/pipeline/test_naming.py` | 69 | Module 05 |
| `src/pipeline/test_confidence.py` | 52 | Module 06 |
| `src/pipeline/test_execution.py` | 188 | **Module 07** |
| `src/models/test_execution.py` | 13 | **Module 07** |
| `src/storage/test_database.py` | 21 | Shared storage layer (includes Module 07's `log_user_correction()` coverage) |
| `src/test_main.py` | 13 | CLI layer (includes Module 07's `preview()`/`execute()`/`undo()` coverage) |
| `src/core/test_images.py` | 7 | Shared core utility |
| `src/core/test_pdf.py` | 6 | Shared core utility |
| `src/core/test_archive.py` | 7 | Shared core utility |
| `src/core/test_media.py` | 4 | Shared core utility |
| `src/core/test_text.py` | 7 | Shared core utility |
| `src/core/test_exif.py` | 4 | Shared core utility |
| `src/core/test_hashing.py` | 4 | Shared core utility |
| `src/models/test_classification.py` | 6 | Module 02 |
| **Total** | **568** | |

**Module 07's own contribution:** 188 (`test_execution.py`) + 13 (`test_execution.py` models) = 201 tests directly authored for this module, plus 3 tests added to `src/storage/test_database.py` for `log_user_correction()` and 12 tests added to `src/test_main.py` for the CLI layer (`test_main.py` also retains its one pre-existing Module 06 test) — 216 tests total attributable to Module 07's own implementation work, added incrementally across WP-1 through WP-12 with the full suite re-run and required at 100% after every single work package (never batched, never deferred).

**Growth arithmetic (pre-Module-07 baseline → current):** the suite stood at 352/352 immediately after Module 06's release. Module 07's own work added 216 tests across WP-1–12 (18 at WP-1, 20 at WP-2 correction+WP-2 base combined, 12 at WP-3, 17 at WP-4, 24 at WP-5, 20 at WP-6, 17 at WP-7, 19 at WP-8, 20 at WP-9, 7+3 at WP-10, 14 at WP-11, 12 at WP-12 — see `Module 07 Implementation Plan.md`'s per-WP status notes for the exact count at each step), bringing the total to 568.

**Key groups in `test_execution.py`:** per-function unit coverage for every WP-1–11 function; the I2 adversarial forged-approval suite (three variants, WP-4); real-filesystem collision/move tests against `tmp_path`, never mocked (WP-5); the ownership-boundary immutability test (every non-Module-07-owned field byte-identical before/after, WP-7); the reconciliation four-way classification suite plus two cross-checks against `ExecutionEngine`'s own real output (WP-8); the fixed-processing-order determinism test, the Layer-2 forced-exception test, and the decision-24 no-whole-batch-staging collision test (WP-9); the reverse-chronological-order/forward-order-would-collide pair (WP-11).

**Key groups in `test_main.py`:** the §5 CLI-level eligibility filter; tier-grouped read-only preview; auto-tier execution requiring no decisions (G4); the missing-`destination_root` batch-level failure path; approve-with-edit and reject correction-capture-before-execution ordering; `review_required` resisting a forged decision at the CLI boundary (I2); CLI-level idempotency; a full execute→undo cycle; the structural undo-is-manual-only check.

Last confirmed run: 2026-07-13, `568 passed in 2.87s` (re-confirmed after the test-isolation fix below and again before this release package was generated).

## Integration tests

**Performed 2026-07-13 — 71/71 checks passed, zero findings.** A real, executable harness (`m07_integration_harness.py`) ran the full real Module 01→07 chain — isolated `/tmp` storage, routing fake Module 02/03 providers — through five runs: Run A (full six-stage pipeline + read-only preview, 12 checks), Run B (execution across all three tiers, adversarial forged decisions, real execution-time collision re-check, both decision-23 overrides, forced-failure/partial-batch continuation, 33 checks), Run C (crash/restart reconciliation — both `SAFE_TO_RETRY` and `REPAIRED` — 47 cumulative), Run D (CLI-level idempotency, 50 cumulative), Run E (undo at batch and single-action granularity, 71 cumulative). Three harness-authoring errors were found and corrected during development (documented in `Tests/Module 07 Integration Test Plan.md`'s "Harness corrections" section) — none required any change to `src/pipeline/execution.py` or any other production file. Full detail: `Tests/Module 07 Integration Test Plan.md`.

## Defects found and fixed

**During implementation work-package audits (WP-1 through WP-12):**
- WP-7 correction (High): `ExecutionEngine.execute_file()` never persisted its own field mutations — fixed by adding `save_file_record()` immediately after step 6.
- WP-2 Medium: whether an edited destination overrides archive placement was undefined — resolved via `ARCHITECTURE_DECISIONS.md` decision 23 and a corrective implementation pass.
- WP-11: one coverage gap (`FAILED` `UndoOutcome` branch untested) found and closed immediately during the audit itself.

**During the composed-system architecture audit (after WP-12, before WP-13):**
- Medium: `Module 07 Implementation Plan.md`'s inconsistent WP-9–12 completion status — resolved by appending the missing status notes.

**During release validation, before Integration Testing began:**
- Medium: a test-isolation gap in `src/pipeline/test_execution.py` — 8 test functions omitted `_isolate_database_and_temp()`, silently writing synthetic fixture data into the real `Database/Metadata/metadata_store.json` on every regression run since the WP-7 persistence correction. Found via `git diff --stat` after a routine regression re-run, reported, approved, and fixed (the missing isolation call added to exactly the 8 affected functions; no other test or production code touched). A scripted, function-by-function audit of every test file in `src/` that writes to persistent storage confirmed zero remaining gaps anywhere in the suite. The real, contaminated `metadata_store.json` was reset to pristine as disclosed housekeeping.

**During Integration Testing:** zero genuine Module 07 defects found. Three harness-authoring errors found and corrected in the harness itself (see Integration tests section above).

**During UAT:** zero findings (see UAT summary below).

## UAT summary

**Performed 2026-07-13 — zero findings.** A real external Downloads-like folder (`/tmp/uat_m07_downloads/`, 12 files) and a real external destination-library folder (`/tmp/uat_m07_library/`), real live-Claude-judged Module 02/03 content, and — per Module 06 UAT's own established precedent — the real project `Database`/`Runtime` rather than an isolated harness. Three real, separate `main.execute()` invocations: (1) a real crash simulation for two fixtures followed by reconciliation-and-auto-tier-execution, including a real execution-time collision re-check; (2) real human approval decisions covering both decision-23 override cases, a real forced OS-level move failure (G6/I4), an adversarial forged decision on a `review_required` record, and a `review_required` record given no decision at all; (3) a CLI-level idempotency re-invocation, confirming the forced-failure record legitimately retried and succeeded. Real `undo_batch()` correctly split 8 reversible/2 irreversible outcomes; a real single-action re-execute-then-undo confirmed `undo_single_action()` independent of batch granularity. Full detail, including every intermediate state transcribed from real command output: `Tests/Module 07 UAT Plan.md`.

## Security review

- Path-escape rejection (§22) adversarially tested: absolute paths and `..`-bearing path components are rejected before ever being joined into a destination path, for both `suggested_destination`/`suggested_name` and simulated edited values.
- `evaluate_gate()`'s `review_required`-unconditional check adversarially tested against three distinct forged-`ApprovalDecision` constructions (WP-4), and re-verified against a fourth construction arriving through the new external CLI surface (WP-12).
- `perform_move()` uses `Path.rename()` exclusively; the module imports no `shutil`, verified by a dedicated structural test, so no code path can silently fall back to copy-then-delete on a cross-device move.
- `src/main.py`'s new `destination_root` config reader uses `yaml.safe_load`, never `yaml.load` — no arbitrary-code-execution risk from a malformed config file.
- No new file-content-derived operation was introduced (Module 07 never reads file bytes; it only moves/renames based on already-computed metadata).

## Regression tests

Full project-wide suite re-run after every one of WP-1 through WP-12 (and again for this document): 370 → 403 → 415 → 432 → 456 → 476 → 493 → 512 → 532 → 542 → 556 → 568, monotonically increasing, zero regressions at any step. Every already-frozen module's isolated test suite reconfirmed at its exact prior count at every step (Modules 01–06: 15/15, 48/48, 57/57, 47/47, 69/69, 52/52 respectively, unchanged throughout).

## Performance observations

**Measured 2026-07-13, as part of UAT's own performance-measurement step.** Method mirrors Module 05/06's own precedent exactly: the real Module 01→07 chain (`scan()` → `classify()` → `extract()` → `detect_duplicates()` → `suggest_naming()` → `score_confidence()` → `preview()` → `execute()`) run against `Tests/Large Batch/` (75 files), isolated `/tmp` `Database`/`Runtime` paths, instant fixed-answer fake providers for Modules 02/03 (judgment latency is not what's being measured).

**Result:** 75 discovered, 75 scored, 9 executed (tier spread: 9 `auto` / 9 `approval_required` / 57 `review_required`). Modules 1–6 (`scan()` through `score_confidence()`): 40.066s. `preview()`: 0.001s. `execute()`: 0.049s. **Total Module 01→07 chain: 40.116s.**

**Comparison against the Module 06 baseline:** Module 06's own measurement (Module 01→06, same 75-file dataset, same methodology) was 40.122s. Module 07's addition to the chain (`preview()` + `execute()`, one more real pipeline stage) measured 40.116s total — a **−0.006s (−0.01%)** difference, i.e. no measurable regression at all; `preview()`/`execute()` combined added only 0.050s, consistent with Module 07's own design claim that per-file execution work is dominated by a single real filesystem `rename()` call. **No performance regression found. No fix required.**
