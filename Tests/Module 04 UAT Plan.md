# Module 04 (Duplicate & Version Detection) — UAT Plan

Real end-to-end acceptance test of the complete Module 01 → 02 → 03 → 04 pipeline, run the way an actual user would experience it: a realistic, external, Downloads-style folder, scanned by Module 01's real `scan_source()`, classified by Module 02 and metadata-extracted by Module 03 using **live Claude judgment as the actual providers** (exactly as `Tests/Module 03 UAT Plan.md` established), and duplicate/version-detected by Module 04's real `detect_duplicates_batch()` with **no provider at all** — Module 04 is fully deterministic by design (§14), so unlike Modules 02/03 this stage needed no live-judgment wiring, only the real, unmodified implementation running against real files.

## Why this has to be a real, external, multi-run pipeline

`Tests/Module 04 Integration Test Plan.md` already proved the plumbing works using a routing fake provider for Modules 02/03. What that plan explicitly could not cover is whether the *whole* system — including live classification/extraction judgment quality feeding into Module 04's deterministic logic — behaves correctly on a genuinely external, unscripted, realistic Downloads folder, across multiple real pipeline invocations over time (not a single script call), exactly the way a real user's automation would run.

## Test data

A new, external folder — `/tmp/uat_m04_downloads` (outside the project, ephemeral, not preserved after the run, same convention as Modules 01–03's UATs) — 22 entries, 19 discoverable. Built to cover, in one realistic-looking Downloads folder: an exact-duplicate invoice pair, a clean version chain (Resume, with a third version held back for a later run), a second independent version chain (Report_Draft, with a third version held back to trigger a real cross-group-conflict precondition against a synthetically-seeded second lineage — necessary because the frozen design's own §26 states this precondition cannot arise from a single undisturbed real-time run), a token/date-disagreement version conflict (NDA Contract, via deliberately reversed file mtimes), an intended fuzzy-image-duplicate pair and an intended Image-vs-Screenshot category-separation pair, a corrupted image and a malformed PDF (recovery from corrupted/malformed files), a real password-protected PDF, an adversarial filename (quotes, embedded newline-equivalent tab, emoji), and deterministic-category baseline files (Archive, Application). Full file-by-file list and rationale, and the complete real console transcript, are in the archived run folder (see below).

## Steps (planned)

1. **Module 01 (real scan):** `src/main.py`'s real `scan()`, pointed at `/tmp/uat_m04_downloads` via a temporary `sources.yaml` edit (restored immediately after), against isolated `Database`/`Runtime` paths.
2. **Live classification (real judgment):** every text-bearing file's real extracted content read via `src/core/pdf.py`, judged live and wired into a `ClassificationProvider` built for this run, passed to `classify(provider=...)`.
3. **Live metadata extraction (real judgment):** every judgment-dependent field, including real visual inspection of the image-family files, wired into a `MetadataExtractionProvider` built for this run, passed to `extract(provider=...)`.
4. **Module 04 (real, deterministic, no provider):** `detect_duplicates()` — no fake, no shortcut, the actual frozen implementation.
5. **Repeat runs:** a second, later scan of a fresh external subfolder (simulating new arrivals) to prove version-chain joining and idempotency across genuinely separate invocations; a synthetic pre-existing second version-group lineage seeded via real `save_file_record()`/`update_indexes()` calls (disclosed, per §26) to construct the cross-group-conflict precondition; a repeat `detect_duplicates()` call with no new files to prove idempotency.
6. **Archive:** `metadata_store.json`, `action_log.jsonl`, `version_history.json`, `hash_index.json`, `phash_index.json`, `name_index.json`, `terminal_output.txt`, and `summary.md` under `Runtime/UAT/Module04_UAT_<timestamp>/`.

## Expected outcomes

19 discovered, 3 skipped, reconciling exactly; every deterministic category gets its outcome with zero provider calls; every judgment-needing file gets a real, defensible category/extraction; the exact-duplicate pair resolves via `duplicate_of`; the fuzzy-image pair resolves via `fuzzy_duplicate`/`phash_distance` **without ever crossing category lines**; both version chains form correctly with the token/date conflict flagged and never silently resolved; the held-back files correctly join their existing chains and trigger the cross-group conflict on schedule; idempotency holds across repeated runs except for the deliberately-preserved cross-group exception; no unhandled exception anywhere in the run.

## Pass / Fail

Pass if every outcome above holds against the real implementation with no Critical/High/Medium finding. Per your standing instruction: if Integration/UAT discovers a genuine implementation or design defect, stop immediately, do not fix it, and report the finding with severity/root cause/impact/smallest fix instead of completing the plan.

---

## Execution Results (Run 1, 2026-07-08, batch `2026-07-08_205215`)

**Run 1 was executed in full through Module 04 and stopped there.** A genuine, independently-reproduced implementation/design defect was found on this very first pass — **Finding UAT-1: near-duplicate detection is not category-scoped**, contradicting the frozen design's explicit §9/F5 guarantee that Image and Screenshot must never group for *either* near-duplicate or version-chain detection. The version-chain half of F5 is correctly implemented (category-scoped via `lookup_name_matches()`); the near-duplicate half was never given the same treatment (`lookup_phash_matches()`/`phash_index.json` carry no category dimension at all), and the one existing regression test for F5 only ever exercised the version-chain half. Confirmed reproducible via both this run's real fixtures and an independent, minimal, deliberately-isolated repro built specifically to rule out any dataset-specific confound.

**Severity: High.** Full root cause, impact, and recommended smallest fix (a category parameter added to `lookup_phash_matches()`/`phash_index.json`, mirroring `lookup_name_matches()`'s existing precedent, plus the missing regression test) are recorded in `Runtime/UAT/Module04_UAT_2026-07-08_205215/summary.md`, alongside the full real console transcript and raw `metadata_store.json`/`action_log.jsonl`/`version_history.json`/index files from the real run.

**No implementation change was made** — per instruction, the run was stopped immediately on discovering the defect rather than auto-fixed. The planned later steps (chain-joining across separate runs, the cross-group-conflict construction, repeated-run idempotency, and the remaining verification dimensions) were not reached and remain unverified at the UAT level.

**Module 04 UAT is not approved to proceed. This finding is pending your decision — likely remediation under the Frozen Module Change Policy (a "Post-freeze correction #4"), followed by a fresh Independent Implementation Audit pass and a UAT restart from Run 1, mirroring exactly how the H1/M1/M2/M3 Integration Testing findings were previously resolved.**

---

## Execution Results (Run 1 restart, 2026-07-08, batch `2026-07-08_211306`)

UAT-1 was independently re-verified as a design-completeness gap (Design Review finding F5, fully propagated into `lookup_name_matches()` but never into `lookup_phash_matches()`), corrected via the Frozen Module Change Policy as a design-correction cycle: `Module 04 Design.md` §7/§11/§16/§20/§22 corrected → targeted design review → re-freeze → minimal code change (`lookup_phash_matches()` extended to accept `category`, mirroring `lookup_name_matches()`'s existing pattern) → two new regression tests, confirmed load-bearing via mutation testing → fresh Independent Implementation Audit (third pass, 0 Critical/High/Medium) → this UAT restart from Run 1.

**The restart ran the full plan to completion, all four runs, with no defects found:**

- **Exact duplicate detection** ✓ — `Amazon_Order_Invoice.pdf`/`(1).pdf`, `IMG_4821.jpg`.
- **Fuzzy image duplicate detection** ✓ — `IMG_4821_edited.jpg` vs. `IMG_4821.jpg` (`phash_distance=0`), **and the original UAT-1 defect confirmed fixed**: `Diagram_v1.png` (Image) / `Diagram_v2.png` (Screenshot) both now correctly show `fuzzy_duplicate=False`.
- **Version-chain creation** ✓ — NDA_Contract, Report_Draft, Resume, each with correct `version_group_id`/rank.
- **Joining an existing version chain** ✓ — `Resume_JordanPatel_v3.pdf` joins the Run 1 chain in Run 3.
- **Version-rank updates** ✓ — verified across all 4 runs.
- **Cross-group conflict handling** ✓ — `Report_Draft_v3.pdf` (Run 3) real cross-group conflict against a synthetically-seeded Group B, per §26 methodology: `conflict_type=cross_group`, correct `conflicting_group_ids`, `version_group_id=None`, left unresolved per design.
- **Idempotency across repeated runs** ✓ — Run 2: 0 records changed. Run 4: only `Report_Draft_v3.pdf` (unresolved cross-group conflict) remains eligible for re-processing; the within-group `date_token_disagreement` conflicts on `NDA_Contract_v2.pdf`/`Report_Draft_v2.pdf`/`Resume_JordanPatel_v3.pdf` correctly became idempotent (H1 exception logic verified).
- **Persistence** ✓ — `hash_index.json` (21 entries), `phash_index.json` (shared degenerate bucket now correctly excluded cross-category at query time), `name_index.json`, `version_history.json` (3 groups, correct rank progressions) all inspected directly.
- **Action logs** ✓ — 22 `detect_duplicates_and_versions` entries after Run 1 alone.
- **Database indexes** ✓ — see persistence above.
- **Version history** ✓ — see persistence above.
- **Module Contract boundaries** ✓ — 0 diffs across all 27 non-Module-04-owned `FileRecord` fields.
- **Performance** ✓ — 13.557s real wall-clock for the complete 4-run restart.
- **Regression** ✓ — 226/226 passed (224 + 2 new tests for post-freeze correction #4).
- **Security** ✓ — adversarial filename processed without incident.
- **Recovery from malformed/corrupted files** ✓ — `Corrupted_Photo.jpg`, `Corrupted_Invoice.pdf`, `Confidential_Agreement.pdf` (real password-protected PDF) all handled gracefully, no unhandled exception.

Full detail, raw persisted files, and terminal transcript archived at `Runtime/UAT/Module04_UAT_2026-07-08_211306/`.

**Disposition: Module 04 UAT (restart) is complete with no Critical, High, or Medium findings. Per the original instruction, stopping here to await your approval before beginning the Release Audit.**
