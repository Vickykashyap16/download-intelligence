# Module 08 (Logging & Reporting) — User Acceptance Testing Plan

Follows the exact UAT methodology established by `Tests/Module 04 UAT Plan.md` through `Tests/Module 07 UAT Plan.md` (per `Governance/ENGINEERING_STANDARD.md` §6.3): a realistic external Downloads-style folder outside the project, the real `src/main.py` CLI entry points end to end, live Claude judgment as the actual provider for Modules 02/03 (never a canned/routing fake — that pattern is Integration-Testing-only, already used and closed out in `Tests/Module 08 Integration Test Plan.md`), and the real project `Database/`/`Runtime/` (not an isolated harness), because part of what UAT validates is whether Module 08's four report types are correct, readable, and internally consistent against the actual live system a real user would run this tool against. Module 08 itself has no Provider (its `report()` command only reads the metadata store and action log back and writes to `Runtime/Reports/*` — Decision 26).

## Why this has to be a real, external, multi-stage pipeline

Module 08's own unit tests and Integration Testing already exercise every report generator against controlled/isolated fixtures, including corrupted-log and mixed-batch scenarios. What neither can validate is whether the four report types read correctly and present understandably when generated from a real, human-approved batch that has passed through the entire live Module 01→07 chain — real classification/extraction judgment, real duplicate/version detection, real naming, real confidence scoring, real human approval decisions, and a real `execute()` — with `report()` then invoked as a genuine end-user CLI step afterward, exactly as a real user would run it.

## Test data

External Downloads folder: `/tmp/uat_m08_downloads/` (outside the project, ephemeral, not preserved past this session). External destination library: `/tmp/uat_m08_library/` (same). 9 real files, self-authored by Claude then live-judged by reading each one's actual real extracted content (PDF text verified via `pdfplumber` before judging; `.txt` files read directly; the screenshot's `context_description` formed from its actual real drawn content) — reusing Module 06/07's proven fixture-construction approach, chosen to organically exercise all four report types together in one batch:

- **`Invoice_CloudHosting_Vendor.pdf`** — clean invoice, every field present (vendor, invoice_date, invoice_number, amount, currency, tax_type). Auto tier — the Daily Summary's auto-filed row and the Storage Report's Invoice-category/Finance-destination contribution.
- **`Receipt_Coffee_Shop.pdf`** — vendor + invoice date present, four optional fields genuinely absent. Approval-required tier.
- **`Resume_Morgan_Taylor.pdf`** — candidate name present, version indicator and last-modified date absent. Review-required tier — left untouched, the Daily Summary's review-required row.
- **`Screenshot_ErrorDialog.png`** — a real, no-EXIF screenshot (Pillow-drawn), live vision-judged `context_description`, `capture_date` absent. Approval-required tier — the Storage Report's Screenshot-category contribution.
- **`Locked_NDA_Contract.pdf`** — a real password-protected PDF (`pypdf`-encrypted). Review-required tier (`unknown_category` + `locked_file` hard floors) — left untouched, a second review-required row.
- **`Old_Meeting_Notes.txt`** / **`Old_Meeting_Notes_backup.txt`** — a real, byte-identical exact-duplicate pair. Approval-required tier both — the Duplicate Report's duplicate/archived row.
- **`Budget_Plan_v1.pdf`** / **`Budget_Plan_v2.pdf`** — a real, similar-but-different version chain (v1 in Dutch, non-English content signal; v2 in English). v1 (superseded) lands review-required (locked out by the non-English hard floor plus naming fallback) and is left untouched; v2 (latest) lands approval-required — together the Duplicate Report's superseded-version/kept row.

## Steps (planned)

1. Temporarily edit `src/config/sources.yaml`'s `path` (to `/tmp/uat_m08_downloads`) and `destination_root` (to `/tmp/uat_m08_library`); restore both to `null` immediately after the run (same convention as every prior module's own UAT).
2. Real `main.scan()` → `main.classify(provider=...)` / `main.extract(provider=...)` (live-judgment providers, not a routing fake) → `main.detect_duplicates()` → `main.suggest_naming()` → `main.score_confidence()` → `main.preview()`.
3. Real `main.execute(decisions=...)` — `APPROVE_AS_SUGGESTED` for all 5 `approval_required` records; no decision supplied for the 3 `review_required` records (left in place, per design).
4. Real `main.report()` — invokes all four generators (Daily Summary, Weekly Summary, Duplicate Report, Storage Report) in one CLI pass.
5. Read all four generated reports as a human reviewer would: verify counts reconcile against the real metadata store and action log, verify each report is internally consistent with the others, verify the CLI workflow (`scan → classify → extract → detect_duplicates → suggest_naming → score_confidence → preview → execute → report`) matches what a real end user would actually type.
6. Full regression suite (`pytest src/ -q`).
7. Archive `metadata_store.json`, `action_log.jsonl`, all four generated reports, and every driver script used, under `Runtime/UAT/Module08_UAT_<timestamp>/`; reset the real `Database/`/`Runtime/` to pristine; restore `src/config/sources.yaml`; remove the ephemeral external folders.

## Expected outcomes

The Daily Summary's totals and per-file table match the real batch exactly (9 scanned, 1 auto-filed, 5 approval-required, 3 review-required, 1 duplicate archived, 0 errors); the Duplicate Report correctly shows one exact-duplicate pair (archived) and one superseded-version pair (kept); the Storage Report's by-destination/by-category tables sum to the real total filed-record count and byte total; the Weekly Summary correctly rolls up the current ISO week with today's day marked "Not yet closed" (Decision 27); `report()` touches only `Runtime/Reports/*`, never the action log (per the WP-7 documentation correction); no crash on the locked/non-English/duplicate-pair files.

## Pass / Fail

Pass if every expected outcome holds with no Critical/High/Medium finding. Per standing project instruction, a genuine production-code defect found at any point stops the run immediately — reported, not fixed — rather than completing the plan.

---

## Execution Results (Run 1, 2026-07-19/20, archived at `Runtime/UAT/Module08_UAT_2026-07-20_044936/`)

Run 1 executed the complete plan (steps 1–7) against the real code, real project `Database/`/`Runtime/`, and real external Downloads/destination-library folders.

### Steps 1–2: real scan → classify(live) → extract(live) → detect_duplicates → suggest_naming → score_confidence → preview

All 9 files discovered, classified, and extracted via real Claude live judgment (8 provider calls — `Locked_NDA_Contract.pdf` correctly never reached the provider, routed deterministically by the real `is_locked()` check). Real tier spread: auto: 1, approval_required: 5, review_required: 3 — matching each file's designed target above.

### Step 3: `main.execute(decisions=...)`

5 `approval_required` records approved as suggested; the 3 `review_required` records (`Budget_Plan_v1.pdf`, `Locked_NDA_Contract.pdf`, `Resume_Morgan_Taylor.pdf`) correctly left untouched (`processed_at` stayed `None` for all three, confirmed against the real reloaded records).

During this call, `execute_batch()`'s post-execution temp-directory cleanup (`clear_batch_temp()` → `shutil.rmtree()`) raised a real `PermissionError` on `Runtime/Temp/2026-07-19_231500/`. Per standing instruction, no production code was modified; the failure was investigated directly and reported before any fix was attempted. Evidence gathered: all 6 intended file operations (moves/archive/log writes) had already completed correctly and consistently in the metadata store and action log before cleanup ran; the identical `shutil.rmtree()` call was reproduced failing on a brand-new, completely unrelated directory, ruling out anything file- or batch-specific; the session's mount was confirmed FUSE-backed via `mount` output, and the same `clear_batch_temp()` function had succeeded without issue earlier in this same session against an isolated `/tmp`-based Integration Testing harness. **The user reviewed this evidence and did not classify it as a production code defect** — it was accepted as an environment-specific UAT observation (sandbox/FUSE filesystem restriction on unlink/rmtree operations, not Module 07/08 logic), with the explicit standing exception that if reproducibility on a normal local filesystem is ever discovered, it is to be treated as a genuine defect. **Cleanup could not be fully verified in this execution environment because of these filesystem restrictions** — this is disclosed here per that instruction, not as a Module 08 finding.

### Step 4: `main.report()`

Ran clean, no errors, no crash. Generated all four report types in one pass, writing exclusively to `Runtime/Reports/*` — no write to `Runtime/Logs/action_log.jsonl` was made or attempted, confirmed against the log's own reloaded content (54 lines, all pre-dating the `report()` call).

### Step 5: human review of all four generated reports

**Daily Summary (`summary_2026-07-19.md`):** 9 scanned, 1 auto-filed, 5 approval-required, 3 review-required, 1 duplicate archived, 0 versions archived, 0 errors — matches the real batch exactly. The Files table lists all 6 processed/archived records with correct new name, destination, category, confidence, and tier; the 3 untouched review-required records are correctly absent from this table (design: only `processed_at is not None` records appear), which is documented, expected behavior, not an omission.

**Duplicate Report (`duplicate_report.md`):** 1 duplicate (archived) + 1 superseded version (kept) = 2 records tracked, reconciling exactly against the batch. `Old_Meeting_Notes_backup.txt` correctly shown as Duplicate/Archived, related to `Old_Meeting_Notes.txt`; `Budget_Plan_v1.pdf` correctly shown as Superseded Version/Kept, related to `Budget_Plan_v2.pdf` (its status "Kept" is correct — v1 was left in place because it was `review_required` and never executed, not because Module 07 chose to retain it).

**Storage Report (`storage_report.md`):** 6 filed records, 10.1 KB total, By Destination and By Category tables both sum correctly to the same 6-record/10.1 KB totals (Documents/Finance/Images.Screenshots/~ARCHIVE~.Duplicates by destination; Document/Invoice/Screenshot by category). Consistent with Decision 29 (metadata-store-only, no filesystem walk) and Decision 30 (`processed_at is not None` inclusion).

**Weekly Summary (`summary_2026-W29.md`):** Week 2026-07-13 to 2026-07-19 correctly identified via UTC-invocation-based day boundary (Decision 27). Days 07-13 through 07-18 correctly show "No activity" (0 across all columns — genuinely no prior activity those days). 07-19 (today, the day this UAT ran) correctly shows "Not yet closed" in the Days table, per design — the current day is never rolled into week-to-date totals while still open. One genuine, non-blocking UAT observation: the top-line bullet summary (Files scanned: 0, Auto-filed: 0, etc.) shows all zeros on the same day real activity happened, because those bullets aggregate only closed days; the "Not yet closed" status is disclosed in the Days table below but not reiterated next to the top-line zeros. This is correct, designed behavior (not a defect, no code change indicated or authorized) but could read as confusing to a first-time user glancing only at the summary line without scrolling to the Days table — recorded here as a UAT observation/recommendation for a future documentation or UX pass, not a release blocker.

### Step 6: regression validation

`pytest src/ -q` → **716/716 passed**, unchanged from the pre-UAT baseline. No Module 01–08 source file was modified during this UAT run — per standing instruction, cleanup logic and all other production Python code were left untouched throughout, including after the `PermissionError` finding above.

### Step 7: housekeeping performed after Run 1

The real `Database/Metadata/metadata_store.json`, `Database/FileIndex/*.json`, and `Database/History/version_history.json` were reset to their pristine committed content (`[]`/`{}`/`{}`/`{}`/`{}`); `Database/Learning/User Corrections.json` was never touched (all decisions were `APPROVE_AS_SUGGESTED`, no corrections captured). `Runtime/Logs/action_log.jsonl` was reset to empty. `src/config/sources.yaml`'s `path`/`destination_root` were restored to `null`/`null`. The external `/tmp/uat_m08_downloads/` and `/tmp/uat_m08_library/` folders were removed successfully (plain `/tmp` paths, not FUSE-restricted).

**Full cleanup could not be completed this session**, disclosed here explicitly per standing instruction: the leftover `Runtime/Temp/2026-07-19_231500/plan.json` (from the `PermissionError` above) and a diagnostic `Runtime/Temp/_diag_test/` directory created while investigating it, plus the four newly-generated `Runtime/Reports/*` report files themselves, could not be removed — every `shutil.rmtree()`/`Path.unlink()` attempt against them failed identically with `PermissionError(1, 'Operation not permitted')`, consistent with the same FUSE-mount restriction. These are harmless, correctly-generated artifacts left in place rather than evidence of any defect. Run 1's real results (`metadata_store.json`, `action_log.jsonl`, all four generated reports, and all three driver scripts used) are fully preserved in `Runtime/UAT/Module08_UAT_2026-07-20_044936/`.

### Disposition

**No Critical, High, or Medium finding.** All four report types were verified correct, internally consistent with each other and with the real batch, and generated cleanly via the real end-user CLI workflow. Two Low/non-blocking UAT observations are recorded, neither requiring or authorizing a code change:

1. **Environmental** — post-execution temp-directory cleanup could not be fully verified in this execution environment due to a sandbox/FUSE filesystem restriction on unlink/rmtree operations (not Module 07/08 logic), per the user's own explicit, evidence-based disposition.
2. **UX/documentation** — the Weekly Summary's top-line bullets show all-zero totals on a day with real same-day activity, because the current day is correctly excluded from week-to-date aggregation while open; the "Not yet closed" context lives only in the Days table below, which a user glancing only at the summary line could miss.

**Module 08 UAT is complete.**
