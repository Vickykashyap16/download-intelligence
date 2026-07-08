# Module 04 UAT — Run 1 (2026-07-08, batch `2026-07-08_205215`) — STOPPED, genuine defect found

First real user-acceptance run of Module 04, via the real production chain: Module 01's real `scan_source()` against an external, temporary Downloads-like folder (`/tmp/uat_m04_downloads`, not preserved), Module 02's real `classify_batch()` and Module 03's real `extract_metadata_batch()` using **live Claude judgment as the actual providers** (exactly as Module 03's own UAT established), and Module 04's real `detect_duplicates_batch()` with **no provider at all** — fully deterministic, per design §14. Run via `src/main.py`'s real `scan()` → `classify(provider=...)` → `extract(provider=...)` → `detect_duplicates()` (`sources.yaml` temporarily pointed at the external folder, restored immediately after). Plan: this document, §"Test data" and "Steps" below.

**This run surfaced a genuine, reproduced implementation/design defect during the very first pass. Per your explicit instruction, the run was stopped immediately, no fix was applied, and this document records the finding instead of a completed UAT report.**

## Test data

19 discovered entries in `/tmp/uat_m04_downloads` (3 skipped at Module 01: `.DS_Store` → `system_file`, `empty_placeholder.pdf` → `zero_byte`, `movie_download.torrent` → `unsupported_extension`) — full reconciliation in `terminal_output.txt`. Highlights relevant to what was being verified: `Amazon_Order_Invoice.pdf`/`(1).pdf` (exact duplicate), `Resume_JordanPatel_v1.pdf`/`v2.pdf` (version chain), `NDA_Contract_v1.pdf`/`v2.pdf` (reversed mtimes → token/date conflict), `Report_Draft_v1.pdf`/`v2.pdf` (a second, independent version chain, held-out `v3.pdf` for a later "joining" run that was never reached), `IMG_4821.jpg`/`IMG_4821_edited.jpg` (intended fuzzy-image-duplicate pair), `Diagram_v1.png`/`Diagram_v2.png` (intended Image-vs-Screenshot category-separation pair), `Corrupted_Photo.jpg`/`Corrupted_Invoice.pdf` (malformed-file recovery), `Confidential_Agreement.pdf` (real password-protected PDF), plus `SomeApp_1.0.0_Mac.dmg`/`project_files.zip` (deterministic categories) and an adversarial filename (`Weird File Name With 'Quotes" And Emoji 📄_v1.txt`).

## Steps executed before stopping

1. **Module 01 (real scan):** `scan()` against the external folder — 19 discovered, 3 skipped, reconciling exactly.
2. **Module 02 (live classification):** `classify(provider=LiveClassificationProvider())` — a real provider built for this run, backed by Claude's own reading of each file's actual extracted text (via `src/core/pdf.py`'s `extract_text()`, shown in-session before answering). 12 files needed a live call; 7 were deterministic.
3. **Module 03 (live extraction):** `extract(provider=LiveMetadataExtractionProvider())` — 14 provider calls (10 text, 4 vision — including genuine visual inspection of the real image bytes via the Read tool before answering).
4. **Module 04 (deterministic, no provider):** `detect_duplicates()` — **this is where the defect surfaced.**

Full console transcript: `terminal_output.txt`. Raw output: `metadata_store.json`, `action_log.jsonl`, `version_history.json`, `hash_index.json`, `phash_index.json`, `name_index.json` (all in this folder).

## The finding

**Finding UAT-1 — Near-duplicate detection is not category-scoped, contradicting the frozen design's explicit F5 guarantee.**

### What was observed

`Diagram_v1.png` (real camera-style EXIF → classified `Category.IMAGE`) and `Diagram_v2.png` (no camera EXIF, screen-resolution-like dimensions → classified `Category.SCREENSHOT`) are two different files, different filenames beyond their shared normalized base, and — critically — **different categories**. Module 04 flagged `Diagram_v2.png` as a near-duplicate of `Diagram_v1.png`:

```
Diagram_v1.png -> category: Image      file_id: a526e42a... sig: fuzzy_duplicate=False
Diagram_v2.png -> category: Screenshot file_id: d3fdfa4c... sig: fuzzy_duplicate=True, phash_distance=0
```

`phash_index.json` confirms both file_ids share the same perceptual-hash bucket, with no category information anywhere in the index:

```json
{"8000000000000000": ["a526e42a-...(Image)", "d3fdfa4c-...(Screenshot)", "76e1aefc-...(Image)", "3c15b4c4-...(Screenshot)"]}
```

### Independent, deliberate reproduction (isolated from this run's specific fixtures)

To rule out any confound from this dataset (e.g. accidental exact-duplicate content — `IMG_4821.jpg` and `Diagram_v1.png` did turn out to be exact duplicates of each other due to a fixture-construction mistake, reusing the same source image under two names), a clean, minimal, deliberately-isolated repro was built and run directly against `detect_duplicates_batch()`: two records with different filenames, different content hashes, and different categories (`Category.IMAGE` vs `Category.SCREENSHOT`), each a distinctly-colored solid-color image so no reasonable person would call them "the same picture":

```
Image record     : Category.IMAGE      DuplicateSignals(fuzzy_duplicate=False, ...)
Screenshot record: Category.SCREENSHOT DuplicateSignals(fuzzy_duplicate=True, phash_distance=0, ...)

CROSS-CATEGORY NEAR-DUP FLAGGED: True
```

Confirmed reproducible on demand, independent of this UAT's specific fixtures.

### Root cause

`Module 04 Design.md` §9 states explicitly: *"Image and Screenshot are strictly different categories for **both near-duplicate and version-chain grouping** (F5, confirmed). A Screenshot never groups with a plain Image, and vice versa — no category-equivalence mapping exists in v1."* This is an audited, twice-confirmed design guarantee (original five-pass architecture review, both implementation audit passes).

The version-chain half of F5 is correctly implemented: `lookup_name_matches(normalized_name, category)` (`src/storage/database.py`) takes `category` as an explicit parameter and scopes candidates accordingly (§16 documents this explicitly).

**The near-duplicate half of F5 was never given the same treatment.** `Database/FileIndex/phash_index.json`'s schema (§16) is `{ "<perceptual_hash>": ["<file_id>", ...] }` — no category dimension anywhere. `lookup_phash_matches(phash, max_distance)`'s frozen signature (§16) has no `category` parameter, unlike `lookup_name_matches()`. `src/pipeline/duplicate_detector.py`'s `_check_near_duplicate()` calls `lookup_phash_matches(phash, _MAX_PHASH_DISTANCE)` and accepts every returned candidate without ever checking `candidate.category == record.category`. The implementation faithfully follows what §16 actually specifies for `phash_index.json` — the gap is that **§9's F5 promise and §16's storage/lookup design for the near-duplicate path are inconsistent with each other within the frozen design itself**, and neither the original architecture review nor either implementation-audit pass caught the inconsistency, because the one existing regression test for F5 (`test_engine_image_and_screenshot_never_group_with_each_other`, `src/pipeline/test_duplicate_detector.py`) only exercises the version-chain half (it asserts `result.version_group_id is None`; it never sets up phash-matching content and never asserts anything about `fuzzy_duplicate`). This same gap was actually already visible in `Tests/Module 04 Integration Test Plan.md`'s own Run 1 output (`Design_v2.png` showed `fuzzy_duplicate=True, phash_distance=0`) — that plan's own note on case M04-CAT01 incorrectly concluded "no perceptual-hash coincidence occurred between them in this run," which this UAT's closer inspection shows was not correctly verified at the time; the phash bucket dumped in that same document's "CHECK 1" output already contained all four image-family file_ids (both categories) under one shared hash, which is corrected here for the record.

### Impact

Any two images of different categories (a real photo and a screenshot) that happen to be visually flat/low-texture enough to land within Hamming distance 5 of each other — not a rare occurrence for solid-color or low-detail images, and plausible for real screenshots (which are often visually simple) — will be incorrectly cross-flagged as near-duplicates of each other. Per `Rules/Confidence Rules.md`, `fuzzy_duplicate=True` triggers a `-20` confidence deduction and a hard floor (never `auto`), so a Screenshot could be routed to unnecessary manual review because of an unrelated Image (or vice versa) — a real, user-visible correctness gap, though bounded (per design's own §19: at worst, an unnecessary review, never a silent wrong or irreversible action, since Module 04 never touches the filesystem and near-duplicates never set `duplicate_of`).

### Severity

**High** — per this project's standard severity scale (`Governance/ENGINEERING_STANDARD.md` §14, the same scale used throughout Module 04's audits): a designed, explicitly-confirmed detection-outcome guarantee (F5's near-duplicate category scoping) is violated, reproducibly, on the very first real dataset that happened to exercise it meaningfully. Not Critical — no data loss, no irreversible action, no crash; the pipeline completed the batch cleanly and every other file's outcome was correct.

### Recommended smallest fix

Mirror `lookup_name_matches()`'s existing, already-frozen precedent exactly:

1. Extend `Database/FileIndex/phash_index.json`'s schema to carry category alongside each file_id (e.g. `{ "<perceptual_hash>": [{"file_id": "...", "category": "..."}, ...] }`, or a parallel `{phash: {category: [file_id, ...]}}` shape — either preserves the existing "list of candidates within a hash bucket" structure while adding the one missing dimension).
2. Extend `lookup_phash_matches(phash, max_distance)` to `lookup_phash_matches(phash, max_distance, category)`, filtering candidates to the same category before the Hamming-distance comparison — exactly the treatment §16 already gives `lookup_name_matches()`.
3. Update `_check_near_duplicate()` (`src/pipeline/duplicate_detector.py`) to pass `record.category` through.
4. Add the missing regression test this gap should have caught: a same-perceptual-hash, different-category pair asserting `fuzzy_duplicate is False` — the near-duplicate counterpart to the existing version-chain-only F5 test.

This is a schema/signature change to an internal storage index and lookup function, not a Module Contract change (the same latitude §16 already claims for `phash_index.json`'s format), but Module 04 is frozen, so per `Governance/FROZEN_MODULE_CHANGE_POLICY.md` this requires the design document to be explicitly updated and re-frozen (adding a "Post-freeze correction #4" alongside the three already on record) before any implementation change is made — matching exactly how H1/M1/M2/M3 were handled in the Implementation Audit remediation pass.

## Disposition

**Module 04 UAT is stopped. Not approved for Release Audit.** No implementation change was made (per instruction: stop, do not auto-fix). Awaiting your decision on Finding UAT-1 before this UAT can resume — once addressed under the Frozen Module Change Policy (the same discipline the H1/M1/M2/M3 remediation followed), UAT would need to restart from Run 1, since Module 04's own logic will have changed.

Everything executed before the stop (Modules 01/02/03/04's Run 1 output) is archived in this folder for reference; no conclusions are drawn about Module 04's other behaviors (idempotency, cross-group conflict, version-chain joining across runs, etc.) from this partial run — those remain unverified at the UAT level until this finding is resolved and the run restarts.
