# PT-002 Post-Implementation Validation Report

**Date:** 2026-07-23
**Scope:** Post-implementation validation gate for the PT-002 correction (`src/pipeline/classification.py`'s `classify_screenshot_or_image()`, implemented under `Build-out/02 Classification/Module 02 Post-Freeze Design Correction — PT-002.md`, approved and implemented in the prior session). No production code was modified in producing this report. PT-003 was not touched, designed, or implemented. This report re-runs the same two datasets Run 002/Run 003 already used, compares results against the `v0.8.0-validated-baseline` recorded in `Release/VERSIONS.md`, and issues a verdict — it does not re-run the 13-check PCV gate or produce a release package; those remain separate, unauthorized next steps.

---

## 1. Methodology

### 1.1 Dataset reconstruction (verified, not assumed)

- **Run 002 dataset** (`Desktop/Validation Sample/`, 9 real files): never executed in the original run (all 9 landed `review_required`), so the original files were still present, untouched. Verified byte-identical to the original run's own recorded `content_hash` for all 9 files before re-running.
- **Run 003 dataset** (43-file systematic sample of the real Downloads folder): 29 of the original 43 files were still present in `Runtime/Validation/RUN003_staging/` (the 22 that stayed `review_required` plus the 7 skipped-at-scan files). The 14 files that were actually executed in the original run had been moved into `Runtime/Validation/RUN003_2026-07-20/Filed/` under their post-approval filenames. These 14 were copied back and renamed to their **original** pre-filing filenames using the exact mapping recorded in that run's own `action_log.jsonl` (`discover`/`move_rename` pairs), reconstructing the original 43-file input set into a fresh staging directory. All 36 discovered files were then verified byte-identical to the original run's own recorded `content_hash` before re-running. The 7 skipped files (unsupported extensions) don't participate in classification and weren't separately hash-checked.

### 1.2 Execution

Both runs were re-executed via the real, unmodified pipeline functions (`scan_source()`, `classify_batch()`, `extract_metadata_batch()`, `detect_duplicates_batch()`, `suggest_naming_and_destination_batch()`, `score_confidence_batch()`, `preview_batch()`, `execute_batch()`) — the same functions `main.py`'s CLI wraps, called directly, exactly mirroring the original runs' own execution method. State was fully isolated to fresh `Runtime/Validation/RUN002_PT002VAL/` and `Runtime/Validation/RUN003_PT002VAL/` directories (own Database/Runtime/Filed), never touching the real project state, via the same module-constant-reassignment isolation technique the original runs used.

- **Run 002:** no provider supplied — matches the original run exactly (all 9 files are `.jpg`, handled entirely by the deterministic Screenshot-vs-Image split; no provider call was needed then or now).
- **Run 003:** the 11 PDFs' text-based classification/extraction (judgment-dependent, not touched by PT-002) was served by a **replay provider** that returns the exact category/field values the original run's real, live-judgment provider produced, sourced directly from that run's own `metadata_store.json`. This is disclosed, not hidden: the file content is unchanged (hash-verified), that ground truth was already established as unambiguous, and PT-002 never touches the text/PDF judgment path — Module 02's deterministic paths (including the corrected function) never call a provider at all, so this replay choice has zero effect on the actual system under test. The 6 `approval_required` decisions (2 approve-as-is, 4 approve-with-edit) were replayed identically to the original real approver's decisions, matched by original filename and applied only after confirming the same 6 files landed `approval_required` this run too (verified below, not assumed).

### 1.3 Safety verification

After each run: every executed file's post-move content was SHA-256-verified against its pre-move `content_hash`; every non-executed file's original was confirmed still present and untouched.

---

## 2. Before vs. After metrics

### 2.1 Run 002 (9 real scanned-document photos)

| Metric | Before (`v0.8.0-validated-baseline`) | After (this run) |
|---|---|---|
| Classification | 9/9 `Screenshot` | 9/9 `Image` |
| PT-002 defect rate (EXIF-absence forcing Screenshot) | 9/9 (100%) | 0/9 (0%) |
| Accuracy vs. strict ground truth (`Document`) | 0/9 (0%) | 0/9 (0%) — unchanged, see §3 |
| Tier | 9/9 `review_required` | 9/9 `review_required` — unchanged |
| Confidence score | 9/9 scored 70 | 9/9 scored 68 |
| Files executed/moved | 0 | 0 |
| Version-chain false positives (PT-003, out of scope) | 3 groups (6 files) | 3 groups (6 files) — identical, unaffected |
| Original files altered | 0 | 0 |

### 2.2 Run 003 (36 discovered files, 19 image-family)

| Metric | Before | After |
|---|---|---|
| Image-family classification | 18/19 `Screenshot`, 1/19 `Image` | 19/19 `Image` |
| PT-002 defect rate | 18/19 (95%) | 0/19 (0%) |
| Classification accuracy, confidently-ground-truthed subset (24 files: 10 Document + 1 Resume + 2 Video + 2 Archive + 2 Unknown + 1 Image control + 6 directly-visually-confirmed non-screenshot images) | 18/24 (75%) | **24/24 (100%)** |
| Non-image categories (PDFs, Video, Archive, Unknown) | unchanged | **identical, 0 diffs** (verified by full before/after diff of all 36 records — only the 18 expected Screenshot→Image changes appeared; nothing else moved) |
| Tier distribution | 8 `auto`, 6 `approval_required`, 22 `review_required` | 8 `auto`, 6 `approval_required`, 22 `review_required` — **identical**, same 6 filenames in `approval_required` |
| Files executed | 14/14 (8 auto + 6 approval_required, same set) | 14/14 (same set, same destinations, same filenames) |
| Post-move content integrity | 14/14 byte-identical | 14/14 byte-identical |
| Version-chain false positive (`image (2).png`/`image (42).png`, PT-003) | Present | Present, unchanged — expected, out of scope |
| Naming collision-suffix count | 14/36 | 15/36 — see §4 |
| Batch cleanup fault (FUSE mount, PT-009/VL-003-6) | Occurred, after all file work completed | **Reproduced identically**, after all file work completed — environment-attributable, not a regression |

---

## 3. Classification improvements

The specific PT-002 defect — an image-family file with no filename marker and no screen-resolution match being forced to `Screenshot` solely because it lacks camera EXIF — is **fully eliminated** across both real datasets: 27 of 27 previously-misclassified real files (9 in Run 002, 18 in Run 003) now correctly fall through to `Image`. Combined with the one file that was already correctly `Image` before (real camera EXIF present), every image-family file in both datasets — 28 of 28 — now lands outside `Screenshot` correctly. On Run 003's confidently-ground-truthed subset, this moves classification accuracy from 75% to 100%.

One distinction worth stating precisely, not glossing over: PT-002 fixes the **Screenshot-vs-Image boundary only**. It was never designed to add a route from image-family extensions to `Document` — that is a separate, already-disclosed architecture gap (`TECHNICAL_DEBT_REGISTER.md` TD-16, `VALIDATION_LEDGER.md` VL-002-1) that the design package's own Problem Statement explicitly did not take on. Run 002's 9 files are genuinely scanned documents whose true category is `Document`; after this fix they land on `Image`, not `Document` — correctly outside the wrong bucket (`Screenshot`) but not yet in the fully-correct one. This is exactly what the design predicted and disclosed, not a shortfall discovered now.

---

## 4. Screenshot regression analysis

**No regression found.** A full field-by-field diff of every record in both runs (category, tier, duplicate/version relationships) shows category changes exactly where expected (27 files, all `Screenshot` → `Image`) and **zero unexpected changes anywhere else** — no PDF, video, archive, or `Unknown`-category record's classification, tier, or duplicate/version relationship differs from the original run.

The confidence score for the reclassified files dropped 2 points (70 → 68 in Run 002; 70 → 68 in Run 003), with tier unchanged (`review_required` in both runs, both before and after) — this is an expected, explainable side effect of `Image` and `Screenshot` having different required/optional metadata fields (`Image` requires `description`; `Screenshot` does not), not a defect. No file moved tiers as a result of the reclassification, and in particular **no file newly reached `auto` or `approval_required` tier** because of this change — the safety-relevant boundary was not affected.

The naming-collision-suffix count moved from 14/36 to 15/36. This is not a regression PT-002 introduced: both before and after, the generic per-category naming template (`Screenshot_Unknown_Context_Unknown_Date` before, `Unknown_Description_Unknown_Variant` after) collides across unrelated files because neither `Screenshot` nor `Image` extraction has live-judgment provider coverage in this framework (a pre-existing, already-disclosed gap — `VALIDATION_LEDGER.md` VL-002-2/VL-003-9 — affecting both categories symmetrically, not something PT-002 changed the presence of).

The disclosed trade-off named in the design's own Risk Assessment — a genuine screenshot with neither a marker filename nor a matching resolution now defaulting to `Image` — was **not exercised by either real-world dataset**: no file in either sample was a genuine screenshot lacking both signals. This trade-off remains covered by the dedicated adversarial unit test (T4) added during implementation, not by real-world evidence one way or the other; that is disclosed here rather than presented as validated.

---

## 5. Safety comparison

| Property | Before | After |
|---|---|---|
| Data loss / unauthorized action | 0 across both original runs | 0 across both re-runs (14/14 + 14/14 executed files byte-identical; all non-executed originals confirmed untouched) |
| Files newly eligible for `auto`/`approval_required` due to reclassification | N/A | 0 |
| Batch-halting faults (excluding the known environment fault) | 0 | 0 |
| Known environment fault (FUSE cleanup, PT-009) | Occurred once (Run 003), after all file work completed | Reproduced once (Run 003 re-run), after all file work completed — same signature, same non-impact |

Safety held identically before and after. The one fault present in both runs is confirmed, both times, to be a sandbox/mount artifact (`shutil.rmtree()` against a FUSE-mounted validation folder) that fires only after every real per-file action already completed and logged correctly — not a new or PT-002-related issue.

---

## 6. New regressions

**None found.** Specifically checked and confirmed clean:

- Every non-image-family classification (11 PDFs, 2 videos, 2 archives, 2 Unknown-category files) — unchanged, verified by full diff.
- Tier distribution — identical in both runs.
- The set of files reaching `approval_required` and their approve/edit outcomes — identical.
- Post-execution file integrity — 14/14 byte-identical in both runs.
- The pre-existing PT-003 version-chain false positive — present and unchanged in both runs, as expected since Module 04 was not touched this cycle.
- Full automated regression suite — 720/720 passing (confirmed in the prior implementation step, re-confirmed unaffected by this validation gate since no code changed during it).

---

## 7. Recommendation: **PASS**

The correction resolves the confirmed defect (100% of real-world PT-002 occurrences in both validation datasets, 27/27) with zero collateral change anywhere else in either dataset — a clean, surgical fix exactly matching its approved design scope. Safety properties (zero data loss, zero new auto/approval-eligible misfiles, zero new batch-halting faults) held identically before and after. The one environment-level fault present is pre-existing, unrelated, and non-data-affecting in both runs.

This is not "PASS WITH NOTES" despite the disclosed items in §3/§4 (the Document-routing gap, the unchanged naming-collision mechanism, the untested T4 trade-off) because none of them are new information or unmet acceptance criteria — all three were named explicitly in the approved design package's own Problem Statement, Risk Assessment, and Test Plan before implementation began, and this validation gate's job was to confirm the fix behaves as that design predicted, which it does, precisely.

**Not covered by this report, per explicit scope:** the 13-check Pipeline Contract Verification gate, a fresh Independent Implementation Audit, and release package generation — these remain separate, unauthorized next steps under `Governance/FROZEN_MODULE_CHANGE_POLICY.md`'s re-release path. PT-003 remains untouched and unauthorized for design or implementation.
