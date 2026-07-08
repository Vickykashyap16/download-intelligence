# Module 04 UAT — Restart Summary (batch `2026-07-08_211306`)

Restart of Module 04 (Duplicate & Version Detection) UAT from Run 1, following the design-correction cycle for **post-freeze correction #4** (near-duplicate category scoping). This run supersedes the stopped Run 1 archived at `Runtime/UAT/Module04_UAT_2026-07-08_205215/`, which discovered and reported Finding UAT-1.

## What changed since the stopped run

UAT-1 (`Diagram_v1.png` Image vs. `Diagram_v2.png` Screenshot cross-flagged as near-duplicates) was independently re-verified as a **design-completeness gap** (Design Review finding F5 was fully propagated into `lookup_name_matches()`'s version-chain mechanism but never propagated into `lookup_phash_matches()`'s near-duplicate mechanism), not an implementation defect. Per your instruction, this was resolved as a design correction: `Module 04 Design.md` §7/§11/§16/§20/§22 corrected, a targeted design review performed and the design re-frozen, `lookup_phash_matches()` extended to accept `category` (mirroring `lookup_name_matches()`'s existing pattern) with a matching call-site change in `duplicate_detector.py`, two new regression tests added and confirmed load-bearing via mutation testing, a fresh Independent Implementation Audit performed (third pass, 0 Critical/High/Medium), and only then this UAT restart.

## Results, Run 1 (initial batch, 19 discoverable files)

19 discovered, 3 skipped (`.DS_Store`, `empty_placeholder.pdf`, `movie_download.torrent`) — reconciles exactly.

- **Exact duplicates:** `Amazon_Order_Invoice.pdf` → `duplicate_of` `Amazon_Order_Invoice (1).pdf`. `IMG_4821.jpg` → `duplicate_of` `Diagram_v1.png`'s sibling (shared source image, `exact_duplicate=True`).
- **Fuzzy/near-duplicate:** `IMG_4821_edited.jpg` → `fuzzy_duplicate=True`, `phash_distance=0` against `IMG_4821.jpg` (same category, Screenshot/Image cross-check not applicable here — both correctly matched within category).
- **UAT-1 fix confirmed:** `Diagram_v1.png` (Image) and `Diagram_v2.png` (Screenshot) both now show `fuzzy_duplicate=False` — previously `Diagram_v2.png` incorrectly showed `fuzzy_duplicate=True` against the Image record. The fix holds on the real fixture that originally exposed the defect.
- **Version chains:** `NDA_Contract_v1→v2`, `Report_Draft_v1→v2`, `Resume_JordanPatel_v1→v2` all formed correctly with correct `version_group_id`/`rank`. `NDA_Contract_v2` and `Report_Draft_v2` both correctly flagged `version_conflict=True` (`date_token_disagreement`, from deliberately reversed mtimes) — flagged, not silently resolved, per design.
- **Recovery from malformed/corrupted files:** `Corrupted_Photo.jpg`, `Corrupted_Invoice.pdf`, `Confidential_Agreement.pdf` (real password-protected PDF) all handled gracefully — `Unknown` category where extraction failed, no unhandled exception, no crash of the batch.
- **Security/adversarial filename:** `Weird File Name With 'Quotes" And Emoji 📄_v1.txt` processed without incident.
- **Deterministic baselines:** `SomeApp_1.0.0_Mac.dmg` (Application), `project_files.zip` (Archive) — zero provider calls, correct category.
- `detect_duplicates_and_versions` action-log entries after Run 1: 22.

## Results, Run 2 (idempotency, no new files)

Records whose state changed across Run 2: **0**. Full idempotency confirmed on a clean re-run with no new arrivals.

## Synthetic Group B seeding

Per design §26 (cross-group conflict cannot arise from a single undisturbed real-time run), a second, independent version lineage (`Report_Draft_v4.pdf` → `Report_Draft_v5.pdf`, `version_group_id=8535de33-...`) was seeded via real `save_file_record()`/`update_indexes()` calls — disclosed, not fabricated internals.

## Results, Run 3 (new arrivals: `Resume_JordanPatel_v3.pdf`, `Report_Draft_v3.pdf`)

- `Resume_JordanPatel_v3.pdf` correctly joins the existing Resume chain (`rank=latest`, group unchanged) and organically (not engineered) triggers `date_token_disagreement` — a benign side effect of near-simultaneous fixture mtimes, correctly flagged rather than silently resolved.
- `Report_Draft_v3.pdf` correctly produces a **real cross-group conflict**: `conflict_type=cross_group`, `conflicting_group_ids=['69f3c846-e6f6-4cf1-b97b-a4677a3c0486', '8535de33-68b3-4ee1-a1c0-153aace1c733']` (the original Report_Draft group and the seeded Group B) — `version_group_id=None`, left unresolved per design, exactly the precondition §26 describes.

## Results, Run 4 (idempotency re-check after cross-group conflict)

Records still eligible for re-processing: `['Report_Draft_v3.pdf']` only. Confirms the idempotency-exception logic (post-freeze correction #2 / Finding H1) correctly distinguishes an unresolved cross-group conflict (`version_group_id is None`, stays eligible) from a within-group `date_token_disagreement` conflict (becomes idempotent like everything else) — `NDA_Contract_v2.pdf`, `Report_Draft_v2.pdf`, and `Resume_JordanPatel_v3.pdf` all correctly excluded from re-processing despite carrying `version_conflict=True`.

## Persistence

- `hash_index.json`: 21 entries.
- `phash_index.json`: one shared degenerate-hash bucket (the two solid-color test images), now correctly excluded from cross-category matching at query time per the fix.
- `name_index.json`: correct entries for all three version-chain name families plus Group B.
- `version_history.json`: 3 real groups present (NDA_Contract, Report_Draft — now with Group B split recorded separately, Resume) with correct rank progressions across all runs.

## Module Contract boundaries

0 diffs across all 27 non-Module-04-owned `FileRecord` fields, checked via `asdict()` before/after re-running `detect_duplicates_batch()` on a real, fully multi-module-populated record (`Resume_JordanPatel_v3.pdf`).

## Performance

Full multi-run restart (4 runs, live-judgment classification/extraction, full duplicate/version detection): **13.557s real** wall-clock time.

## Regression

Full suite: **226/226 passed** (up from 224 pre-fix; +2 new tests added for post-freeze correction #4, both confirmed load-bearing via mutation testing).

## Security / adversarial / recovery

All adversarial-filename, corrupted-file, and password-protected-file cases handled without incident (see Run 1 above) — no unhandled exception anywhere across all 4 runs.

## Findings

None. No Critical, High, or Medium finding on this restart.

## Disposition

**Module 04 UAT (restarted from Run 1) is complete with no Critical, High, or Medium findings.** Per your original instruction, this is where I stop and wait for your approval before beginning the Release Audit.
