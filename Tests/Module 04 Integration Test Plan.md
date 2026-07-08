# Module 04 (Duplicate & Version Detection) — Integration Test Plan

Validates the complete interaction between `src/pipeline/watch_ingest.py` (Module 01), `src/pipeline/classification.py` (Module 02), `src/pipeline/metadata.py` (Module 03), and `src/pipeline/duplicate_detector.py` (Module 04) — real files, real batches, run through `scan_source()` → `classify_batch()` → `extract_metadata_batch()` → `detect_duplicates_batch()`/`needs_duplicate_detection()` end-to-end — against `Build-out/04 Duplicate & Version Detection/Module 04 Design.md` (frozen, including post-freeze corrections #1–#3), the Design Review, the Module 01/02/03 Module Contracts, `Rules/*`, and the second Independent Implementation Audit (`Module 04 Implementation Audit.md`), before Module 04 is allowed to proceed to UAT.

Existing unit tests (`src/pipeline/test_duplicate_detector.py`, `src/storage/test_database.py` — 224 passing across the full `src/` suite) already cover Module 04's own functions, Engine decision branches, and every boundary case named in the design's §22 Test Strategy in isolation, including the H1/M1/M2/M3 remediation added during the second implementation audit. This plan is the complementary **integration-level** pass: real files from `Tests/`, real four-module batches, a routing fake provider standing in for live Claude judgment exactly as Module 03's own Integration Test Plan established as precedent, and real, black-box-inspected persisted output — not Module 04 called directly against in-memory objects, and not just Module 04 exercised in isolation from Modules 01–03.

**Datasets used:** `Tests/Duplicate Files/` (reused unchanged — `Resume_v8.pdf`/`Resume_v9.pdf`, `invoice_download.txt`/`invoice_download (1).txt`, `product_photo_v1.jpg`/`product_photo_v2.jpg`). **New dataset built for this plan:** `Tests/Module 04 Duplicates/` — `generic_doc_a.txt`/`generic_doc_b.txt` (byte-identical content, routed to two different categories, for the exact-duplicate-across-categories edge case §26 names explicitly), `Contract_v1.pdf`/`Contract_v2.pdf` (real reportlab-generated PDFs with deliberately reversed mtimes, so the higher version token and the newer file date disagree — exercises §10's `date_token_disagreement` tie-break), `Resume_v10.pdf` (held back from the initial batch, introduced in a later run to exercise a file joining an already-formed version group), `Statement.pdf` plus two synthetic seed records (`Statement_v1.pdf`/`Statement_v2.pdf`, seeded directly via real `save_file_record()`/`update_indexes()` calls into two different pre-existing `version_group_id`s) to construct the cross-group-conflict precondition §26 documents as arising only "from files discovered out of order" — a state that cannot arise from a single undisturbed real-time pipeline run, so it is seeded via real production storage functions rather than fabricated Module 04 internals — and `Design_v1.png`/`Design_v2.png` (same base filename, one with real camera EXIF and one without, verified via direct execution to classify as `Category.IMAGE` and `Category.SCREENSHOT` respectively) to exercise §9/F5's strict Image-vs-Screenshot category separation.

Test IDs map to this plan's sections: `F` functional (duplicate/version outcomes), `C` cross-module contract, `IDEM` idempotency, `VER` version-chain creation/joining, `CONF` conflict handling (token/date and cross-group), `CAT` Image/Screenshot category separation, `DET` determinism, `LOG` logging, `DB` database/persistence, `PERF` performance, `REG` regression.

**Because `ClaudeLiveClassifier.classify()`/`ClaudeLiveExtractor.extract()` are documented placeholders** (fulfilled live by Claude during a real agent-driven run, not autonomous code), every Module 02/03 judgment call in this plan uses a routing fake provider (`RoutingFakeClassificationProvider`/`RoutingFakeMetadataExtractionProvider`, keyed by filename substring), mirroring Module 03's own Integration Test Plan precedent exactly. Module 04 itself has no provider at all (design §14 — fully deterministic) and needed no fake. This proves the plumbing — the real Module 01→02→03→04 handoff, index/log/history persistence, and Module Contract boundaries — works correctly end-to-end. It does not, and cannot, validate the *quality* of live Claude's classification/extraction judgment — that remains UAT's job, not this plan's, and is out of scope here since Module 04's own behavior does not depend on judgment quality (§14: every Module 04 decision is a computation over already-structured data).

---

## 1. Functional scenarios (real four-module batch, Run 1)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-F01 | Full Module01→02→03→04 chain over a mixed-category real folder | 12 files across `Tests/Duplicate Files/` + `Tests/Module 04 Duplicates/` | Every discovered record ends with a real `duplicate_signals` instance; nothing crashes across Contract/Resume/Invoice/Document/Image/Screenshot in one batch. |
| M04-F02 | Exact duplicate, same category | `invoice_download.txt` / `invoice_download (1).txt` | Second-filed record's `duplicate_of` set to the first's `file_id`; `duplicate_signals.exact_duplicate == True`. |
| M04-F03 | Exact duplicate, different categories (§26 edge case) | `generic_doc_a.txt` (routed to Document) / `generic_doc_b.txt` (routed to Contract) | `duplicate_of` still set despite the category mismatch — hash equality is authoritative regardless of category (§26). |
| M04-F04 | Near-duplicate image, real perceptual hash | `product_photo_v1.jpg` / `product_photo_v2.jpg` | Both records show `duplicate_signals.fuzzy_duplicate == True`, `phash_distance == 0`; `duplicate_of` stays `None` for both (a near-duplicate is a signal, never a certain fact, §8). |
| M04-F05 | Version chain, clean (no conflict) | `Resume_v8.pdf` / `Resume_v9.pdf` | Both join one `version_group_id`; v8 `version_rank == "superseded"`, v9 `== "latest"`; `version_conflict == False` on both. |
| M04-F06 | Version chain with a token/date disagreement | `Contract_v1.pdf` (newer mtime, lower token) / `Contract_v2.pdf` (older mtime, higher token) | Both join one group; v2 wins (`"latest"`) per the token-wins tie-break (§10); v2's `version_conflict == True` (the token/date disagreement is flagged, not silently resolved). |
| M04-F07 | A near-duplicate image pair independently also forms a version chain | `product_photo_v1.jpg` / `product_photo_v2.jpg` (same pair as F04) | Both `fuzzy_duplicate == True` **and** joined into a `version_group_id` simultaneously — confirms step 2's "continue to step 3 regardless" (§7). |

## 2. Cross-module contract validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-C01 | Module 04 changes only its four owned fields, verified on a real multi-module record | Any fully-processed record from Run 1, re-run through `detect_duplicates_batch()` | All 27 non-Module-04-owned `FileRecord` fields (every field checked programmatically, not spot-checked) byte-identical before/after. |
| M04-C02 | Module 04's side effect touches only `version_group_id`/`version_rank` on the *other* record | `Resume_v9.pdf` after Run 3 (`Resume_v10.pdf` supersedes it) | Every other field on `Resume_v9.pdf`'s record (all 25 fields besides those two) unchanged from its Run-1 state. |
| M04-C03 | Exact-duplicate detection runs regardless of category, including a record Module 02 could not classify | (Covered by F03 — `generic_doc_b.txt` classifies to a real category, not Unknown, in this dataset; exact-hash logic itself does not gate on category per §9) | `duplicate_of` set independent of category value. |

## 3. Idempotency (H1, post-freeze correction #2)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-IDEM01 | A settled "nothing found" record is never re-selected on a later run | All Run 1 files with no duplicate/version outcome (`Design_v1.png`, `generic_doc_a.txt`, `invoice_download (1).txt`) | `needs_duplicate_detection()` returns `False` for all of them on Run 2; zero re-selection, zero state change, zero new log lines. |
| M04-IDEM02 | A settled "match found" record is never re-selected on a later run | All Run 1 files with an exact/fuzzy/version outcome | Same as IDEM01 — zero re-selection across the entire 12-file Run 1 output on Run 2. |
| M04-IDEM03 | An unresolved cross-group conflict remains eligible for re-processing forever (the one deliberately-preserved exception) | `Statement.pdf` after Run 4 | `needs_duplicate_detection(statement_record) == True` even after being fully processed once — confirmed by direct re-check after Run 4 completes. |
| M04-IDEM04 | The real `detect_duplicates()` CLI filter (`main.py`) and the harness's own filter select identically | N/A — both use `needs_duplicate_detection()` directly, same function, same call site pattern as `main.py` | No divergence possible; same function under test in both places. |

## 4. Version-chain creation and joining

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-VER01 | A version chain is created from scratch within a single batch | Run 1, `Resume_v8.pdf`/`Resume_v9.pdf` | New `version_group_id` minted, shared by both records (post-freeze correction #1's broadened side effect). |
| M04-VER02 | A later-arriving file joins an already-formed group in a **separate, later run** | Run 3, `Resume_v10.pdf` introduced alone | `Resume_v10.pdf` joins the existing group (same `version_group_id` as v8/v9, not a new one); becomes `"latest"`; the previous latest (`Resume_v9.pdf`) is correctly demoted to `"superseded"` — confirming the side effect works across separate pipeline runs, not just within one batch. |
| M04-VER03 | `Database/History/version_history.json` reflects the full, current lineage | After Run 3 | The Resume group's history entry lists all three files with their rank at time of the last update (`v8`→superseded, `v9`→superseded, `v10`→latest). |

## 5. Conflict handling

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-CONF01 | Within-group token/date disagreement | Run 1, `Contract_v1.pdf`/`Contract_v2.pdf` | `version_conflict == True` on the record where the disagreement is detected; `conflict_type == "date_token_disagreement"` in the log; token-based answer wins (§10's confirmed tie-break); no automatic silent resolution. |
| M04-CONF02 | Cross-group conflict — candidates span two pre-existing version groups | Run 4, `Statement.pdf` against seeded `Statement_v1.pdf`(group A)/`Statement_v2.pdf`(group B) | `version_group_id`/`version_rank` both stay `None` on `Statement.pdf`; `duplicate_signals.version_conflict == True`; log's `conflict_type == "cross_group"` with both conflicting group IDs listed; no auto-merge of the two pre-existing groups. |
| M04-CONF03 | Cross-group conflict remains unresolved/re-examined, never silently frozen | Run 4, re-checked after completion | Same as IDEM03 — `Statement.pdf` stays eligible for re-processing (cross-referenced here as the conflict-handling half of the same behavior). |

## 6. Image vs. Screenshot category separation (F5)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-CAT01 | Same normalized filename, different category (Image vs. Screenshot), never grouped or matched | `Design_v1.png` (real camera EXIF → `Category.IMAGE`) / `Design_v2.png` (no camera EXIF → `Category.SCREENSHOT`) | Neither `version_group_id` is set for either file, despite an identical normalized name — category-scoped `lookup_name_matches()` correctly excludes the cross-category candidate. `Design_v2.png` (Screenshot) still independently reports `fuzzy_duplicate` against itself... — see note below. |

**Correction added 2026-07-08 (post-UAT-Run-1):** the note originally here claimed "no perceptual-hash coincidence occurred" between `Design_v1.png` and `Design_v2.png` in this run. That claim was not actually verified against this plan's own persisted `phash_index.json` at the time and is **incorrect** — Module 04 UAT's Run 1 (`Tests/Module 04 UAT Plan.md`, Finding UAT-1) discovered that `lookup_phash_matches()`/`phash_index.json` carry no category dimension at all, so `Design_v1.png` (Image) and `Design_v2.png` (Screenshot) — both derived from a visually flat, low-texture source image — in fact landed in the *same* perceptual-hash bucket in this very run, the same cross-category collision UAT later reproduced independently and minimally. `Design_v2.png`'s `fuzzy_duplicate == True` result recorded above was this defect surfacing here first, not a benign coincidence. See `Tests/Module 04 UAT Plan.md` for the full finding (severity: High) and recommended fix. This integration-testing pass did not catch it as a defect at the time because M04-CAT01 was scoped to the version-chain half of F5 only, matching the same scope gap the UAT finding identifies in the unit test suite.

## 7. Determinism

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-DET01 | Same candidates, reversed input-list order, fresh isolated store | Synthetic `Doc_v1.pdf`/`Doc_v2.pdf` pair (same category, distinct content hashes, one-second `discovered_at` gap), processed once as `[v1, v2]` and once as `[v2, v1]` | Byte-identical outcome (`version_group_id` assignment, `version_rank` on each) regardless of the caller's input-list order — confirms §7/F1's batch-order determinism holds even when the *input list itself* (not just timestamps) is reordered. |
| M04-DET02 | Deterministic batch order re-verified at integration level (cross-reference to unit suite) | (Existing unit tests already cover the `file_id`-tie-break-on-identical-`discovered_at` case exhaustively) | Not re-built here — see "existing unit tests already cover" note above. |

## 8. Logging validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-LOG01 | Full per-file lifecycle across all four modules | Any Run 1 file | Exactly one `discover`, `classify`, `extract_metadata` (if category is real/non-Unknown), and `detect_duplicates_and_versions` entry, in that order, same `file_id`. |
| M04-LOG02 | Side-effect update produces a **second, later log line**, never a rewrite of the first | `Resume_v9.pdf` across Run 1 → Run 3 | Its original Run-1 log line (`version_rank: "latest"`) is unmodified and still present; a second, distinct log line appears later (Run 3's batch_id) noting the supersession (`version_rank: "superseded"`, `superseded_by: <Resume_v10's file_id>`) — confirmed by direct inspection of both raw log lines. |
| M04-LOG03 | Both `conflict_type` values appear correctly in the persisted log | `Contract_v2.pdf` (`"date_token_disagreement"`) and `Statement.pdf` (`"cross_group"`) | Both values observed exactly as designed, read back from the real persisted `action_log.jsonl`, not asserted only against the in-memory `EngineResult`. |

## 9. Database / persistence validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-DB01 | `hash_index.json` round-trip | Full Run 1–4 dataset | One entry per distinct content hash; exact-duplicate pairs correctly resolve to the first-filed `file_id`. |
| M04-DB02 | `phash_index.json` round-trip | `product_photo_v1.jpg`/`v2.jpg` | Entry present, correctly grouping both `file_id`s under the shared perceptual hash. |
| M04-DB03 | `name_index.json` round-trip, category-scoped | Full dataset | Candidate retrieval by normalized name works; category scoping confirmed by CAT01 never cross-matching. |
| M04-DB04 | `version_history.json` reflects every group formed across this plan | Contract, Resume, product_photo, and the two Statement seed groups | 3 real (non-seeded) groups fully populated per VER03; seeded groups present as pre-existing state, untouched except where CONF02 explicitly requires it (they are not touched — the conflict leaves both alone). |

## 10. Performance

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M04-PERF01 | Baseline throughput, deterministic-only category (no image work) | 75 synthetic Document-category records, no matches | Informational baseline; fails only if the run hangs, errors, or takes unreasonably long. |

## 11. Regression validation

| ID | Objective | Method | Expected result |
|---|---|---|---|
| M04-REG01 | Full existing unit suite still passes | `pytest src/ -q` | All unit tests pass, no new failures introduced by this integration pass. |
| M04-REG02 | No Module 01/02/03 source file modified during this pass | `ls -la --time-style=full-iso` mtime comparison | All Module 01/02/03 source files' mtimes predate this integration-testing session (2026-07-08). |
| M04-REG03 | No Module 04 source file modified during this pass either (zero defects found → no fix needed) | Same mtime comparison | Module 04's own files' mtimes reflect only the prior H1/M1/M2/M3 remediation session, not new edits made during this integration pass. |

---

## 12. Expected outputs

For a real batch run through `scan_source()` → `classify_batch()` → `extract_metadata_batch()` → `detect_duplicates_batch()`/`needs_duplicate_detection()`, a correct Module 04 integration produces: every `status == "discovered"` record ends with a fully-populated `duplicate_signals` instance regardless of category; an exact content-hash match always sets `duplicate_of`, regardless of category agreement; a near-duplicate image match is recorded only as a signal, never as `duplicate_of`; a version chain forms or is joined only within the same category, with the previous latest correctly demoted the moment a new record supersedes it — via a second, later, non-destructive log line, never a rewrite of the original; a token/date disagreement is flagged (never silently resolved) and the token-based answer wins; a cross-group conflict leaves `version_group_id`/`version_rank` both `null`, is logged with the full conflicting-group-ID list, and remains eligible for re-examination on every subsequent run; every other outcome becomes correctly idempotent and is never re-selected or re-logged on a later run; batch outcome never depends on the caller's input-list order; and every `FileRecord` field outside Module 04's four owned fields is byte-identical before and after Module 04 runs, across the real multi-module pipeline, not just Module 04 in isolation.

## 13. Pass / fail criteria

Each case above passes only if every assertion in its expected result holds simultaneously against the real implementation — not a partial match. The plan as a whole passes if every executable case passes and the regression suite (§11) shows no new failures. Per the standing instruction for this integration-testing phase, any genuine implementation or design defect discovered here is stopped on immediately, not auto-fixed, and reported as its own finding using the project's standard severity scale (`Governance/ENGINEERING_STANDARD.md` §14): **Critical** (data loss, irreversible action, or a crash that halts the pipeline), **High** (a core guarantee — determinism, idempotency, Module Contract, or a designed detection outcome — is violated), **Medium** (a designed behavior is incomplete or a test gap allows a real defect to go undetected), **Low** (a minor correctness or completeness gap with limited blast radius), or **Cosmetic** (documentation/wording only, no behavioral impact) — each with a recommended smallest fix. A failure traced to this plan's own test-harness code (fixture construction, isolation setup, or assertion logic) rather than to `src/pipeline/duplicate_detector.py` or its Module 01/02/03 dependencies is a harness-authoring error, corrected in the harness and disclosed in Execution Results, not counted as a Module 04 finding — the same distinction Module 03's own Integration Test Plan draws (see its §20).

---

## Execution Results (run against the real code, 2026-07-08)

All sections above were implemented as a real, executable Python harness (not a permanent pytest file — mirroring Module 03 Integration Testing's own precedent that only this markdown plan persists) and run against the real `src/pipeline/watch_ingest.py`, `src/pipeline/classification.py`, `src/pipeline/metadata.py`, and `src/pipeline/duplicate_detector.py`, using isolated `Database`/`Runtime` paths (monkeypatched module-level path constants pointed at a fresh `/tmp` tree) so nothing touched the project's real store or logs.

**Four real pipeline runs were executed, each black-box-inspected via the persisted `metadata_store.json`, `action_log.jsonl`, `Database/FileIndex/*.json`, and `Database/History/version_history.json` — never by reaching into `DuplicateDetectionEngine` internals directly:**

- **Run 1 (initial batch, 12 files):** `Resume_v8.pdf`/`v9.pdf`, `invoice_download.txt`/`(1).txt`, `product_photo_v1.jpg`/`v2.jpg`, `generic_doc_a.txt`/`generic_doc_b.txt`, `Contract_v1.pdf`/`v2.pdf`, `Design_v1.png`/`Design_v2.png` — through the real four-module chain with a routing fake provider for classification/extraction.
- **Run 2 (idempotency re-run, no new files):** re-derived `needs_duplicate_detection()`'s selection against the now-settled store.
- **Run 3 (joining an existing group, separate run):** `Resume_v10.pdf` introduced alone, in its own fresh source subfolder (see harness-correction note below).
- **Run 4 (cross-group conflict):** two synthetic pre-existing version-group members seeded via real `save_file_record()`/`update_indexes()` calls, then the real `Statement.pdf` fixture run through the full chain.

**All planned cases across sections 1–10 passed on final execution.** Two issues surfaced during development — **both confirmed to be defects in this plan's own test harness, not in Module 04, Module 03, Module 02, or Module 01**, following the same reproduce-in-isolation-before-concluding-anything discipline Module 03's Integration Test Plan established:

1. **Initial Run 3/Run 4 construction (would have affected F01/IDEM/CAT/DET results): the harness re-scanned one ever-growing source folder containing already-fully-processed files from earlier runs.** `scan_source()`/`build_file_record()`'s real, correct, already-frozen behavior (`watch_ingest.py`: "Only populates the fields Module 01 owns; everything from classification onward is left at its default... for later modules" whenever a path is *rediscovered*) is intended for a Downloads folder where Module 07 — not yet built — has already relocated previously-filed files by the next scan. Re-scanning the same accumulating folder made this real behavior silently reset already-settled `category`/`extracted_metadata`/`duplicate_signals` fields on unrelated, already-processed files (observed directly: `Design_v1.png`'s `duplicate_signals` changed between the Run 1 and Run 3 dumps even though it was never an intended part of Run 3). Root-caused by reproducing it directly (confirming `build_file_record()`'s documented reuse-vs-reset behavior is exactly as designed, and that the reset was a consequence of the harness's redundant re-scan, not of any pipeline code). **Fixed in the harness** by giving each run its own fresh source subfolder, scanned independently — never rediscovering a path already filed in an earlier run, consistent with how `main.py`'s `scan()`/`classify()`/`extract()`/`detect_duplicates()` are actually intended to be invoked over time in production.
2. **M04-CONF02 (cross-group conflict) initially failed to produce any conflict at all.** The synthetic seed filenames (`Statement_seedA.pdf`/`Statement_seedB.pdf`) were verified directly via `rapidfuzz.fuzz.ratio()` on their normalized forms to score only 75.0 against `Statement.pdf` — below the design's confirmed 90 similarity threshold (§10), so the seeded candidates were correctly (per real, unmodified Module 04 logic) never even considered a match, let alone a cross-group conflict. **Fixed in the harness** by renaming the seeds to `Statement_v1.pdf`/`Statement_v2.pdf`, verified via direct computation to normalize to an identical 100.0-scoring base string; re-execution then produced the intended cross-group conflict exactly as designed.

**Re-execution after both harness corrections: every case in sections 1–10 passed**, including the four supplementary checks built to directly satisfy this phase's explicit requirements beyond the section tables above:

- **Module Contract boundary, exhaustively checked (not spot-checked):** all 27 non-Module-04-owned `FileRecord` fields confirmed byte-identical on a real, fully multi-module-populated record before/after a Module 04 re-run.
- **"Second log line, not a rewrite":** `Resume_v9.pdf`'s original Run-1 log line (`version_rank: "latest"`) confirmed still present and unmodified; a second, later log line (Run 3's `batch_id`) confirmed appended separately, carrying `superseded_by`.
- **Cross-group conflict's deliberately-preserved idempotency exception:** `Statement.pdf` confirmed still eligible for re-processing (`needs_duplicate_detection() == True`) after being fully processed once — the one exception the H1 fix (post-freeze correction #2) is required to preserve, verified here in a genuine four-module integration context, not only at the unit level.
- **Integration-level determinism:** a synthetic same-category version-chain pair processed twice — once in each input-list order — produced byte-identical `version_group_id`/`version_rank` outcomes both times.

### Regression validation (§11) results

- **M04-REG01:** `pytest src/ -q` → **224/224 passed** (unchanged from the second Independent Implementation Audit's count; no new fixtures or harness code live under `src/`).
- **M04-REG02:** `ls -la --time-style=full-iso` on `watch_ingest.py`, `classification.py`, `metadata.py` confirmed all three predate this session (last touched 2026-07-06, prior to any Module 04 work).
- **M04-REG03:** Module 04's own files (`duplicate_detector.py`, `main.py`, `storage/database.py`, `storage/runtime_io.py`, `models/duplicate.py`, `models/file_record.py`) all carry mtimes from the prior H1/M1/M2/M3 remediation session (2026-07-08, before this integration-testing pass began) — none was modified during this pass, consistent with finding zero implementation defects.

### Performance (§10) — measured, not estimated

- **M04-PERF01:** 75 synthetic Document-category records (deterministic-only path: exact-hash + name-index lookups, no perceptual hashing) through `detect_duplicates_batch()` completed in **0.312 seconds**. Well within the informational baseline; no algorithmic concern.

### Conclusion

Every functional, cross-module-contract, idempotency, version-chain, conflict-handling, category-separation, determinism, logging, and persistence case *this plan explicitly checked* passed against the real Module 04 implementation and its real Module 01/02/03 dependencies, run as genuine four-module batches through isolated storage — not against Module 04 in isolation, and not through any implementation shortcut. The full regression suite (224 unit tests) passed unchanged, and no Module 01/02/03 source file, nor any Module 04 source file, was modified during this pass. The two issues encountered during harness development were both root-caused to this plan's own fixture/harness construction (confirmed by reproducing each in isolation before drawing any conclusion) and corrected there — consistent with the standing instruction not to modify implementation absent a genuine, reproduced defect.

**Addendum, 2026-07-08 (post-UAT-Run-1):** the "zero defects" conclusion originally stated here was incomplete. Module 04 UAT's Run 1 identified and independently reproduced a genuine High-severity defect (near-duplicate detection is not category-scoped — Finding UAT-1, full details in `Tests/Module 04 UAT Plan.md`) that was, in fact, already observable in this very plan's own M04-CAT01 result and this document's own persisted `phash_index.json`, but was not correctly diagnosed at the time (see the corrected note under §6 above). This plan's other findings stand — the harness-bug corrections in this section were genuinely test-authoring errors, independently reproduced in isolation before being classified as such — but the disposition below is superseded by UAT-1 and should not be read as a clean bill of health for Module 04 as a whole.

**Module 04 Integration Testing, as originally scoped, completed with no Critical/High/Medium finding raised at the time — superseded by Finding UAT-1, discovered during the subsequent UAT phase. See `Tests/Module 04 UAT Plan.md` for the active finding and disposition.**
