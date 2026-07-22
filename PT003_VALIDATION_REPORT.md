# PT-003 Validation Report

**Date:** 2026-07-23
**Scope:** post-implementation validation gate for PT-003 (`Build-out/04 Duplicate & Version Detection/Module 04 Post-Freeze Design Correction — PT-003.md`, implemented per `PT003_IMPLEMENTATION_REPORT.md`). No production code was modified in this cycle. No release documentation was updated. PT-003 is not archived — it remains open pending this report's disposition.

---

## 1. Methodology

### 1.1 Dataset reconstruction (Objective 1)

Rather than re-scanning from raw source files a second time, this validation reuses the already-reconstructed, already-hash-verified Run 002 and Run 003 datasets produced for PT-002's own post-implementation validation (`PT002_VALIDATION_REPORT.md` §1), specifically their final states after that validation's full pipeline run:

- `Runtime/Validation/RUN002_PT002VAL/Database/Metadata/metadata_store.json` (9 records — the real academic mark-sheet photo set, `Desktop/Validation Sample/`).
- `Runtime/Validation/RUN003_PT002VAL/Database/Metadata/metadata_store.json` (36 records — the real external UAT Downloads dataset).

This is a deliberate methodology choice, not a shortcut, and is explained here rather than left implicit: PT-003 does not touch classification, metadata extraction, or any pipeline stage upstream of Module 04. The `*_PT002VAL` metadata stores already reflect the correct, real, hash-verified post-PT-002 classification and extracted-metadata state for both datasets — including the fact that both confirmed PT-003 false pairings are still present in that stored state, produced by the OLD (pre-PT-003) `duplicate_detector.py` logic running on top of the corrected PT-002 categories. That stored state is therefore itself a faithful, real "BEFORE" snapshot for this specific validation — re-deriving it by re-running the entire pipeline from scratch a second time would reproduce the identical inputs at real cost with no additional rigor.

The "AFTER" snapshot was produced by taking a fresh copy of every record in each store, resetting exactly the four Module-04-owned fields (`duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals` — per `MODULE_CONTRACT.md`'s ownership list) to their pre-Module-04 state, and re-running `detect_duplicates_batch()` — the real, unmodified production function, now backed by the corrected `duplicate_detector.py` — against an isolated, empty `Database/FileIndex/` and `Runtime/Logs/action_log.jsonl` (the same module-level path-reassignment isolation technique used throughout this project's prior validation cycles). No file in the real `Database/`, `Runtime/`, or either `*_PT002VAL` directory was modified in the process; results were written to new, separate `RUN002_PT003VAL/` and `RUN003_PT003VAL/` directories under `Runtime/Validation/`.

### 1.2 Dataset fidelity verification (Objective 2)

Every record's `current_path` file was re-hashed (SHA-256) and compared against its stored `content_hash`, for both datasets, immediately before this validation ran:

| Dataset | Records | Missing files | Hash mismatches |
|---|---|---|---|
| RUN002_PT002VAL | 9 | 0 | 0 |
| RUN003_PT002VAL | 36 | 0 | 0 |

All 45 real files are byte-for-byte unchanged since PT-002's own validation reconstruction — confirming no drift and satisfying Objective 2 using the same hash-verification methodology PT-002's validation established.

### 1.3 Re-run against corrected code (Objective 3)

`detect_duplicates_batch()` was executed against both reset datasets using the current, PT-003-corrected `src/pipeline/duplicate_detector.py` — the exact same code already covered by the full regression suite, not a reimplementation or simulation of it.

---

## 2. Before vs After Metrics

| Metric | Run 002 — Before | Run 002 — After | Run 003 — Before | Run 003 — After |
|---|---|---|---|---|
| Records processed | 9 | 9 | 36 | 36 |
| Version-chain groups formed | 3 | **0** | 1 | **0** |
| Files in a version-chain group | 6 | **0** | 2 | **0** |
| Exact duplicates (`duplicate_of` set) | 0 | 0 | 0 | 0 |
| Records with any field change (Before→After) | — | 6 | — | 2 |
| Records with a change to a non-Module-04-owned field | — | 0 | — | 0 |
| `tier` values changed | — | 0 | — | 0 |
| `confidence_score` values changed | — | 0 | — | 0 |

## 3. Comparison Against the v0.8.0 Baseline

The v0.8.0 baseline (frozen per `VALIDATION_LEDGER.md`/`PATTERN_TRACKER.md`) is exactly what the "Before" column above reproduces for Module 04's behavior specifically — the 3 Run 002 groups and 1 Run 003 group are the same confirmed false pairings recorded as PT-003 (VL-002-3, VL-003-2), reproduced here from the real, hash-verified dataset rather than re-quoted from memory. This confirms the "Before" side of this validation is a true, faithful representation of the baseline being corrected, not an approximation of it.

---

## 4. Version-Chain Improvements

All 4 confirmed false-positive version-chain groupings — 3 in Run 002 (10th/12th grade, 1st/4th semester, 2nd/3rd semester mark sheets), 1 in Run 003 (`image (2).png`/`image (42).png`) — are eliminated. Every one of the 8 affected files now has `version_group_id: None` and `version_rank: None`, matching the design's predicted outcome exactly. No replacement pairing formed in place of any eliminated one: the full before/after diff (§5) shows zero new non-null `version_group_id` values anywhere in either dataset — the fix reduced version-chain groups from 4 to 0 across both datasets combined, not from 4 to some smaller nonzero number via re-pairing.

## 5. False-Positive Reduction

100% of the confirmed false positives (4 of 4) are resolved. As reported in `PT003_IMPLEMENTATION_REPORT.md` §3, this matches the design's Test Plan predictions (T2, T3) directly, now confirmed against real data rather than only synthetic fixtures.

**Generic-identical-name exposure (Finding E1 / residual R6), checked directly against real data (Validation Plan §11 step 5, Acceptance Criterion 7):** both datasets were scanned for any same-category pair of files sharing an identical normalized filename. **None was found in either dataset.** This is reported explicitly, as required, rather than silently omitted: E1's exposure and its R6 residual are real (confirmed via synthetic tests in the implementation phase) but do not occur anywhere in either of the two real datasets available for this validation. This is an absence of evidence for that specific scenario in this data, not evidence that the scenario cannot occur in a broader real Downloads folder (`PATTERN_TRACKER.md` PT-003 §4's Suspected finding S2/S3 remain open, unconfirmed either way).

## 6. Duplicate Detection Regression Analysis

`duplicate_of` (exact-duplicate detection, Module 04 Step 1) is untouched by this design and was verified unchanged for all 45 records — 0 exact duplicates before, 0 after, in both datasets. Near-duplicate/phash detection (`_check_near_duplicate`) is likewise untouched by this design; `duplicate_signals.fuzzy_duplicate` and `phash_distance` were compared before/after for every record and found identical in every case (§1.3's re-run exercises this code path unchanged, since it runs before the version-chain step for every Image/Screenshot record in both datasets — 9 in Run 002, several in Run 003 — and produced no diffs).

**No genuine version chain exists in either dataset**, before or after this fix. This was independently confirmed two ways: (a) the "Before" snapshot itself shows exactly 4 groups total, all 4 already-confirmed false positives, and (b) a direct scan of both datasets' real filenames for either corroboration signal — an identical normalized name (none found, §5) or an explicit version token (`Mark_Sheet_Final.jpg` in Run 002 only, `('final', 0)`) — found that the one tokened file's similarity score against every other same-category file falls well below the unchanged 90% similarity threshold on its own naming pattern, so it was never a version-chain candidate before or after this change, for reasons unrelated to PT-003. **This means Acceptance Criterion "genuine version chains continue to work" cannot be positively demonstrated from either dataset** — there is no real positive control in this data to demonstrate it against. This is the same U1 gap the design package itself disclosed (§2, §11) and is reported here explicitly rather than treated as satisfied by default.

## 7. Safety Comparison

`tier` and `confidence_score` are identical, per-record, before and after, for all 45 records in both datasets (§2). Every one of the 8 files affected by the version-chain fix was already `review_required` before this change (for reasons unrelated to PT-003 — the pre-PT-002 Screenshot/Image ambiguity, per `PATTERN_TRACKER.md` PT-003 §2 finding C9), and remains `review_required` after it. This means, exactly as the design package's Risk Assessment (R2) anticipated, **this validation does not exercise the `resolve_precedence()` auto-tier-archival exposure** the design flagged as a real, separate, out-of-scope risk — neither before nor after this fix does either dataset contain a case where a false (or, now, a corrected) version-chain grouping reaches a non-`review_required` tier. That risk remains open, real, and untested by this or any prior validation cycle, consistent with the design's own disclosure.

## 8. Files Whose Behavior Changed

| File | Dataset | Before | After |
|---|---|---|---|
| `MarK_Sheet_10th.jpg` | Run 002 | version_group_id set, rank=superseded | version_group_id=None, rank=None |
| `Mark_Sheet_12th.jpg` | Run 002 | version_group_id set, rank=latest | version_group_id=None, rank=None |
| `Mark_Sheet_1st Semester.jpg` | Run 002 | version_group_id set, rank=superseded | version_group_id=None, rank=None |
| `Mark_Sheet_2nd Semester.jpg` | Run 002 | version_group_id set, rank=superseded | version_group_id=None, rank=None |
| `Mark_Sheet_3rd Semester.jpg` | Run 002 | version_group_id set, rank=latest | version_group_id=None, rank=None |
| `Mark_Sheet_4th Semester.jpg` | Run 002 | version_group_id set, rank=latest | version_group_id=None, rank=None |
| `image (2).png` | Run 003 | version_group_id set, rank=superseded | version_group_id=None, rank=None |
| `image (42).png` | Run 003 | version_group_id set, rank=latest | version_group_id=None, rank=None |

No other file, in either dataset (7 remaining Run 002 records, 34 remaining Run 003 records), shows any field change of any kind.

## 9. Unexpected Behavior

None found. The outcome matched the design's predictions exactly: the 4 confirmed false positives were eliminated, no replacement pairing formed, and no field outside Module 04's own ownership changed. The one notable non-outcome, reported for completeness rather than treated as a surprise, is that neither dataset contains a real instance of Finding E1's generic-identical-name scenario (§5) or a real genuine version chain to positively test recall against (§6) — both are pre-existing, disclosed gaps in what these two datasets can validate, not new findings produced by this run.

## 10. New Regressions

None found.

- Full project-wide regression suite: **729 passed, 0 failed** (`python3 -m pytest src/ -q`, re-run fresh for this validation gate).
- Exact-duplicate detection: unchanged (§6).
- Near-duplicate detection: unchanged (§6).
- Tier/confidence outcomes: unchanged for all 45 real records (§7).
- No field outside Module 04's four owned fields changed for any record in either dataset (§2, §8).

---

## 11. Acceptance Criteria — Disposition

| Criterion | Result |
|---|---|
| The confirmed PT-003 false-positive version chains are eliminated. | **Met.** 4/4 eliminated, confirmed against real, hash-verified data. |
| Genuine version chains continue to work. | **Not demonstrable from this data.** Neither dataset contains a real genuine version chain (§6) — a pre-existing gap (`PATTERN_TRACKER.md` U1), not something this validation can pass or fail on. Covered by synthetic regression tests only (`PT003_IMPLEMENTATION_REPORT.md` §3, T4/T12/token-branch test). |
| No increase in incorrect duplicate/version grouping. | **Met.** Groups went from 4 to 0 combined; zero new groupings of any kind appeared. |
| No change outside the approved PT-003 scope. | **Met.** Verified field-by-field across all 45 records; only the 4 Module-04-owned fields on the 8 affected files changed. |
| Safety behavior remains unchanged. | **Met**, with the same caveat the design itself disclosed: `tier`/`confidence_score` are identical before/after for every record, but neither dataset exercises the `resolve_precedence()` R2 exposure either way (§7). |
| All regression tests continue passing. | **Met.** 729/729. |

---

## 12. Recommendation

**PASS WITH NOTES.**

Every criterion within this validation's reach is fully met: all 4 confirmed false positives are eliminated against real, hash-verified data; no unintended change occurred anywhere outside Module 04's own four owned fields; safety-relevant fields (`tier`, `confidence_score`) are byte-for-byte unchanged; the full regression suite passes at 729/729.

The "notes" qualifying this recommendation are pre-existing, previously-disclosed gaps in what these two specific datasets can validate — not new problems this validation surfaced, and not shortfalls in how this validation was conducted:

1. Neither dataset contains a genuine version chain, so "genuine version chains continue to work" is demonstrated only by synthetic unit tests, not by this real-world validation (the same U1 gap the design package itself named, `VALIDATION_PROGRESS.md` §4 item still open).
2. Neither dataset contains a real instance of Finding E1's generic-identical-name scenario, so the corroboration fix's most novel branch (the size-proximity check) is exercised only by synthetic tests here, not by real data.
3. `resolve_precedence()`'s R2 exposure (non-`review_required` auto-archival of a false version pairing) remains untested by any real dataset to date — a standing, disclosed, out-of-scope risk, unaffected by this validation either way.

None of these three notes represents a defect, a regression, or a failure of this specific correction — they are honest boundaries of what a two-dataset real-world validation can and cannot demonstrate, reported explicitly per this project's own established disclosure discipline rather than implied away.

**Per the user's explicit instruction: no release documentation has been updated, and PT-003 has not been archived.** This report's disposition is available for the next authorized step.
