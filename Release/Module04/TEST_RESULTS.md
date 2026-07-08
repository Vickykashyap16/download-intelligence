# Test Results — Module 04 (Duplicate & Version Detection)

Full detail lives in `Tests/Module 04 Integration Test Plan.md`, `Tests/Module 04 UAT Plan.md`, and `Runtime/UAT/`; this is the release-record summary. All counts below were re-verified by direct `pytest` execution during release-package preparation (2026-07-08), not carried forward from memory.

## Unit tests

**226 of 226 passing**, pytest, isolated `tmp_path`/`monkeypatch` fixtures, no real Database/Runtime files touched:

| File | Tests | Owner |
|---|---|---|
| `src/pipeline/test_watch_ingest.py` | 13 | Module 01 |
| `src/pipeline/test_classification.py` | 48 | Module 02 |
| `src/models/test_classification.py` | 6 | Module 02 |
| `src/core/test_pdf.py` | 6 | Module 02 |
| `src/core/test_text.py` | 7 | Module 02 |
| `src/core/test_images.py` | 7 | Module 02 |
| `src/core/test_exif.py` | 4 | Module 02 |
| `src/pipeline/test_metadata.py` | 57 | Module 03 |
| `src/core/test_archive.py` | 7 | Module 03 |
| `src/core/test_media.py` | 4 | Module 03 |
| `src/pipeline/test_duplicate_detector.py` | 47 | **Module 04** |
| `src/core/test_hashing.py` | 4 | **Module 04** |
| `src/storage/test_database.py` | 16 (2 Module 02 typed-field serialization + 14 **Module 04** FileIndex/History) | Module 02 + **Module 04** |
| **Total** | **226** | |

Module 04's own contribution: **65 new tests** (47 + 4 + 14), grown across this module's lifecycle: 32 `test_duplicate_detector.py` + 4 `test_hashing.py` at initial implementation → 224 total suite-wide after the second Independent Implementation Audit resolved H1/M1/M2/M3 (17 new tests) → 226 total suite-wide after post-freeze correction #4 added 2 further regression tests, confirmed genuinely load-bearing via mutation testing. Modules 01–03's baseline (161) is unchanged and re-confirmed passing alongside Module 04's.

Key groups in `test_duplicate_detector.py`: exact-duplicate detection (same/different category), near-duplicate boundary cases (distance exactly at/above/below threshold, verified via a controlled Hamming-distance fixture), the near-duplicate Image-vs-Screenshot category-exclusion test added for post-freeze correction #4, filename-similarity boundary cases, version-token parsing (numbered/`_final`/no token/malformed token), version-conflict detection (agree/disagree/one signal missing), cross-group conflict handling, the H1/M1-corrected candidate-collection-before-narrowing sequence, the exhaustive 31-field Module Contract immutability tests, idempotency tests (including the deliberately-preserved cross-group exception), and deterministic batch-order tests. `test_database.py`'s Module 04 additions cover `lookup_hash()`/`lookup_phash_matches()`/`lookup_name_matches()` (including the category-scoping tests for both post-freeze corrections #4 and F2), `update_indexes()`, and `record_version_history()`.

Last confirmed run: 2026-07-08, `226 passed in 2.63s` (full suite). Module 01–03 isolated (`test_watch_ingest.py` + `test_classification.py` + `test_metadata.py`): `118 passed in 2.13s`. Module 04 isolated (`test_duplicate_detector.py` + `test_database.py` + `test_hashing.py`): `67 passed`.

## Integration tests

`Tests/Module 04 Integration Test Plan.md` — a real four-module batch (`scan_source()` → `classify_batch()` → `extract_metadata_batch()` → `detect_duplicates_batch()`/`needs_duplicate_detection()`), routing fake providers for Module 02/03 judgment, across 31 named cases:

| Section | Cases | Result |
|---|---|---|
| Functional (F01–F07) | 7 | 7 PASS |
| Cross-module contract (C01–C03) | 3 | 3 PASS |
| Idempotency (IDEM01–IDEM04) | 4 | 4 PASS |
| Version-chain creation/joining (VER01–VER03) | 3 | 3 PASS |
| Conflict handling (CONF01–CONF03) | 3 | 3 PASS |
| Image/Screenshot category separation (CAT01) | 1 | 1 PASS |
| Determinism (DET01–DET02) | 2 | 2 PASS (DET02 covered by existing unit-level tests, not independently re-built at integration level, per the plan's own note) |
| Logging (LOG01–LOG03) | 3 | 3 PASS |
| Database/persistence (DB01–DB04) | 4 | 4 PASS |
| Performance (PERF01) | 1 | measured, see below |
| Regression (REG01–REG03) | 3 | 3 PASS |

**All planned cases passed on final execution.** Two issues surfaced during harness development, both confirmed to be defects in the test harness itself, not in Module 04 or any upstream module:
- The harness re-scanned one ever-growing source folder containing already-processed files from earlier runs, triggering Module 01's real, correct, already-frozen "reset fields on a rediscovered path" behavior on unrelated files. Fixed in the harness by giving each run its own fresh source subfolder.
- The synthetic cross-group-conflict seed filenames scored below the 90 similarity threshold by design (verified directly via `rapidfuzz.fuzz.ratio()`), so no conflict was ever triggered — correct behavior for the filenames as originally chosen. Fixed by renaming the seeds to normalize to an identical string.

**Addendum (post-UAT-Run-1):** this plan's own M04-CAT01 case, and its persisted `phash_index.json`, in fact already contained the first observable instance of the near-duplicate category-scoping defect UAT later independently reproduced and diagnosed as Finding UAT-1 — not correctly diagnosed as a defect at the time, because this plan's category-separation case was scoped to the version-chain half of the requirement only. See `Tests/Module 04 Integration Test Plan.md` §6's correction note. The plan's "zero defects" conclusion is superseded by UAT-1; its harness-bug findings stand independently, confirmed by reproducing each in isolation before being classified as harness-only.

## Defects found and fixed

**During the first Independent Implementation Audit (`Build-out/04 Duplicate & Version Detection/Module 04 Implementation Audit.md`, first pass), 1 High + 3 Medium findings, all resolved:**
- **H1 (High):** the idempotency gate never actually fired for a "nothing found" outcome — the single most common real-world result — confirmed empirically (a genuinely unique record reprocessed and re-logged on every run). Fixed: the check now keys off `duplicate_signals is not None`, with the cross-group-conflict exception preserved exactly (post-freeze correction #2).
- **M1 (Medium):** an undisclosed, unreported implementation-time candidate tie-break rule. Retroactively disclosed and formally added to §10 (post-freeze correction #3).
- **M2 (Medium):** the Module Contract immutability tests spot-checked a handful of fields instead of exhaustively covering all non-owned `FileRecord` fields. Fixed: replaced with the exhaustive `asdict()`-loop pattern Module 03 established.
- **M3 (Medium):** five test cases the design's §22 explicitly committed to were missing. Added.
- 3 Low findings (L1 — `main.py`'s `detect_duplicates()` filter has no `category is not None` precondition, now explicitly documented inline as an intentional scope choice; L2 — no regression test cross-checking `_normalize_for_index()`/`normalize_filename()` stay identical; L3 — no index-backfill tooling) remain open as disclosed, non-blocking technical debt — see `KNOWN_LIMITATIONS.md`.

**Re-verified independently on a second Implementation Audit pass:** all four resolved and confirmed with no remaining issue; suite grew from 207 to 224 (17 new tests).

**Discovered during UAT Run 1, independently verified as a design-completeness gap (not an implementation defect), corrected as post-freeze correction #4, and re-verified clean on a third Implementation Audit pass:**
- **Finding UAT-1 (High):** near-duplicate detection was never category-scoped, contradicting the frozen design's own confirmed Image/Screenshot separation requirement. Fixed: `lookup_phash_matches()` extended to accept `category`, mirroring `lookup_name_matches()`'s existing pattern. Two new regression tests added, confirmed genuinely load-bearing via mutation testing (temporarily disabling the fix reproduces the exact UAT-1 symptom, then cleanly reverted). Suite grew from 224 to 226.

**During the final Release Audit (`RELEASE_AUDIT.md`), 2 Medium findings, both resolved:**
- **F1 (Medium):** `CHANGELOG.md` had no dated entry for anything after Module 04's initial implementation. Fixed: nine new dated entries added, covering the full lifecycle.
- **F2 (Medium):** `src/README.md`'s Module 04 status bullet was stale (described the module as awaiting its first Implementation Audit, cited 207 tests). Fixed: bullet updated to the module's actual current state and the correct 226 test count.

See `IMPLEMENTATION_AUDIT.md` and `RELEASE_AUDIT.md` for full findings, evidence, and verification.

## UAT summary

Two UAT runs, both executed exactly as production would: the real four-module chain (`scan()` → `classify(provider=...)` → `extract(provider=...)` → `detect_duplicates()`, via `src/main.py`'s actual CLI entry points) against an external, temporary Downloads-like folder (`/tmp/uat_m04_downloads`, outside the project), using **live Claude judgment as the actual Module 02/03 providers** — Module 04 itself needed no provider (fully deterministic, §14).

**Run 1 (2026-07-08, archived at `Runtime/UAT/Module04_UAT_2026-07-08_205215/`):** 19 discovered, 3 skipped, reconciling exactly. Stopped immediately, per the standing "stop, don't auto-fix" instruction, on discovering a genuine, independently-reproduced defect: Finding UAT-1 (near-duplicate detection not category-scoped). Full finding (root cause, impact, smallest recommended fix) archived alongside the real console transcript and persisted index/log files.

**Restart (2026-07-08, after the post-freeze correction #4 design-correction cycle, archived at `Runtime/UAT/Module04_UAT_2026-07-08_211306/`):** all four planned runs executed cleanly:
- Run 1 — 19 discovered files; exact/fuzzy/version-chain detection all correct; the original UAT-1 defect confirmed fixed (`Diagram_v1.png`/`Diagram_v2.png` no longer cross-flag).
- Run 2 — idempotency, 0 records changed.
- Run 3 (after a synthetic Group B lineage seeded per §26's disclosed methodology) — `Resume_JordanPatel_v3.pdf` joins its existing chain; `Report_Draft_v3.pdf` triggers a real cross-group conflict against the seeded lineage.
- Run 4 — idempotency re-check; only the unresolved cross-group conflict remains eligible for re-processing, confirming the H1 idempotency-exception logic.
- Module Contract boundaries: 0 diffs across 27 non-owned fields on a real, fully multi-module-populated record. Performance: 13.557s real wall-clock for the complete 4-run scenario. All adversarial/corrupted-file cases (a corrupted image, a corrupted/malformed PDF, a real password-protected PDF, an adversarial filename) handled gracefully, no unhandled exception.

`metadata_store.json`, `action_log.jsonl`, index files, `version_history.json`, `terminal_output.txt`, and `summary.md` preserved in both timestamped run folders.

**Caveat:** Module 04's own correctness is verified by deterministic, re-derivable computation, not judgment-quality sampling, so the usual "same person who implemented also defined 'correct'" caveat that applies to Modules 02/03's UATs does not apply to Module 04's own logic in the same way. The live-judgment classification/extraction that fed Module 04's input during UAT carries that same caveat as Modules 02/03's own UATs did — disclosed there, not restated as a new limitation here. The cross-group-conflict precondition (Run 3) was transparently, disclosedly synthetic — seeded via real `save_file_record()`/`update_indexes()` calls per the frozen design's own §26 acknowledgment that this precondition cannot arise from a single undisturbed real-time run.

## Security review

- **No new code-execution surface.** Perceptual hashing reads image bytes via the already-vetted `Pillow`/`imagehash` path; no archive extraction, no shelling out, no `eval`.
- **Bounded blast radius for a false positive/negative** — a wrongly-flagged near-duplicate or version conflict can, at worst, route a file to manual review it didn't strictly need (Module 06's existing hard floors already force this); nothing in this pipeline ever deletes a file, and Module 04 never touches the filesystem itself beyond reading bytes.
- **Adversarial cases exercised during UAT restart:** a corrupted image, a corrupted/malformed PDF, a real password-protected PDF, and an adversarial filename (embedded quotes/emoji) all degraded gracefully — no unhandled exception, no sensitive value newly exposed to a log or diagnostic.
- **Mutation testing** independently confirmed the near-duplicate category-scoping fix (post-freeze correction #4) is genuinely load-bearing, not merely present — disabling it reproduces the exact original UAT-1 symptom.

## Regression tests

Full unit suite re-run after every change during this release cycle, 100% pass rate each time: 207 after initial implementation, 224 after the first Implementation Audit's H1/M1/M2/M3 fixes, unchanged through Integration Testing, 226 after post-freeze correction #4's fix during the UAT-driven design-correction cycle, unchanged through the UAT restart and the Release Audit's documentation-only fixes. Module 01–03 isolated re-run (`test_watch_ingest.py` + `test_classification.py` + `test_metadata.py`): confirmed unchanged throughout, most recently 118/118 alongside Module 04's own tests.

## Performance observations

- **Integration Testing baseline (deterministic-only path, no image work):** 75 synthetic Document-category records through `detect_duplicates_batch()` completed in **0.312 seconds**. No algorithmic concern.
- **UAT restart, full production-style scenario:** the complete 4-run scenario (initial batch + idempotency re-run + synthetic seeding + new-arrivals run + final idempotency re-check), including live-judgment classification/extraction through the real CLI, measured at **13.557 seconds real** wall-clock time.
- `save_file_record()`'s inherited O(N×M) full-store-rewrite cost, already disclosed by Modules 02/03 as their own inherited problem, is now also disclosed as Module 04's own concern (`Module 04 Design.md` §20; see `KNOWN_LIMITATIONS.md`).
