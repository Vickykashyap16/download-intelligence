# Module 07 (Preview, Approval & Execution) — User Acceptance Testing Plan

Follows the exact UAT methodology established by `Tests/Module 04 UAT Plan.md`, `Tests/Module 05 UAT Plan.md`, and `Tests/Module 06 UAT Plan.md` (per `Governance/ENGINEERING_STANDARD.md` §6.3): a realistic external Downloads-style folder and a realistic external destination-library folder, both outside the project, the real `src/main.py` CLI entry points end to end, live Claude judgment as the actual provider for Modules 02/03 (never a canned/routing fake — that pattern is Integration-Testing-only, already used and closed out in `Tests/Module 07 Integration Test Plan.md`), and — per Module 06 UAT's own established precedent — the real project `Database/`/`Runtime/` (not an isolated harness), because part of what UAT validates is behavior against the actual live system a real user would run this tool against. Module 07 itself uses its real, deterministic `execute_batch()`/`ExecutionEngine`/`reconcile_batch()`/`undo_batch()` implementation, with no Provider — Module 07 Design.md decision 22 confirms it has none.

## Why this has to be a real, external, multi-call pipeline

Module 07's own unit tests and Integration Testing already exercise every gate outcome, every override, every crash-recovery path, and every undo case against controlled/isolated inputs. What neither can validate is whether the full Module 01→07 chain behaves correctly when a real human supplies real approval decisions against real files sitting in a real external Downloads-style folder, moving into a real external destination library, logged into and persisted against the real project `Database/`/`Runtime/` — including the parts of the system UAT is specifically positioned to catch that unit/integration testing structurally cannot: real provider judgment quality feeding real tier assignments (with its disclosed self-graded-sample caveat, per §6.3), and genuine multi-invocation behavior (a real crash simulation, a real restart, real idempotency, real undo) against the live project database rather than a disposable `/tmp` harness.

## Test data

External Downloads folder: `/tmp/uat_m07_downloads/` (outside the project, ephemeral, not preserved past this session). External destination library: `/tmp/uat_m07_library/` (same). 12 real files, self-authored by Claude then live-judged by reading each one's actual real content (PDF text verified via `pdfplumber` before judging; the `.txt` files read directly; the two images described from their actual real drawn content) — designed to organically exercise every Module-07-specific behavior this plan needs, reusing Modules 04/06's own proven `Tests/Duplicate Files/product_photo_v1.jpg`/`product_photo_v2.jpg` fixtures for the near-duplicate pair specifically (disclosed in Execution Results — a deliberate, honest substitution after synthetically-generated near-duplicate candidates failed to land within the real perceptual-hash threshold; not a defect):

- **`Invoice_Clean_Acme.pdf`** — clean invoice, every field present. Auto tier; also the real execution-time collision target (§12) — a real file is pre-placed at its naive suggested destination before execution.
- **`Invoice_Sparse_Draft.pdf`** — vendor + invoice date present (both required), all four optional fields genuinely absent from the real text. Approval-required tier; also the real forced-move-failure target (G6/I4).
- **`Locked_Contract_Vendor.pdf`** — a real password-protected PDF (`pypdf`-encrypted). Review-required tier (`unknown_category` + `locked_file` hard floors); the adversarial forged-decision target.
- **`Utility_Bill_Download.txt`** / **`Utility_Bill_Download_copy.txt`** — a real, byte-identical exact-duplicate pair (vendor + invoice date present, four optional fields absent). Approval-required tier; the decision-23 edited-destination-overrides-`~ARCHIVE~/Duplicates/` target (duplicate side) plus a normal-execution control (canonical side).
- **`Resume_Alex_v1.pdf`** / **`Resume_Alex_v2.pdf`** — a real, clean (non-conflicting) version chain. Auto tier both; v1 (superseded) is the clean default-archive-placement case, v2 (latest) the clean normal-destination case.
- **`Photo_Sunset_v1.jpg`** / **`Photo_Sunset_v2.jpg`** — Modules 04/06/07's own proven near-duplicate fixtures, copied in under new names (real phash distance 0, well inside the threshold-5 window). v1 (superseded-version, real naming fallback for the missing `capture_date`) lands approval-required — the decision-23 edited-destination-overrides-`~ARCHIVE~/Old Versions/` target. v2 (latest, `fuzzy_duplicate` hard floor) lands review-required — the no-decision-supplied-at-all baseline target.
- **`CrashTest_Alpha.txt`** / **`CrashTest_Beta.txt`** — clean, full-field auto-tier fixtures reserved for the real restart/crash-reconciliation scenario.
- **`Screenshot_Dashboard.png`** — a real, no-EXIF screenshot (Pillow-drawn), live vision-judged `context_description`. Approval-required tier (real naming fallback for the missing `capture_date`).

## Steps (planned)

1. Temporarily edit `src/config/sources.yaml`'s `path` (to `/tmp/uat_m07_downloads`) and `destination_root` (to `/tmp/uat_m07_library`); restore both to `null` immediately after the run (same convention as every prior module's own UAT).
2. Real `main.scan()`.
3. Real `main.classify(provider=...)` / `main.extract(provider=...)` — purpose-built providers whose answers are literal live judgments formed by reading each real file's actual content, not a filename-substring routing fake.
4. Real, deterministic `main.detect_duplicates()` / `main.suggest_naming()` / `main.score_confidence()` (Modules 04/05/06, no provider).
5. Real `main.preview()` — read-only.
6. A real, deliberately-induced crash simulation for the two `CrashTest_*` records (one staged with no move attempted, one moved-and-logged with its `FileRecord` save deliberately skipped), then a real `main.execute(decisions={})` call — reconciling both crash cases and executing every auto-tier record in the same call, including a real execution-time collision re-check on `Invoice_Clean_Acme.pdf`.
7. A second real `main.execute(decisions=...)` call carrying the real human approval decisions for every `approval_required` record (two `APPROVE_WITH_EDIT` decision-23 overrides, the rest `APPROVE_AS_SUGGESTED`), a forged `APPROVE_AS_SUGGESTED` decision for one `review_required` record (adversarial), and no decision at all for the other `review_required` record — plus a real forced OS-level move failure for `Invoice_Sparse_Draft.pdf` (G6/I4).
8. A third real `main.execute(decisions=...)` call with the identical decisions dict — CLI-level idempotency check; also confirms `Invoice_Sparse_Draft.pdf`'s one-shot forced failure legitimately retries and succeeds this time.
9. Real `undo_batch()` for the batch, confirming the correct reversible/irreversible split, then a real single-action re-execute + `undo_single_action()`.
10. A separate performance-measurement pass against `Tests/Large Batch/` (75 files, isolated `/tmp` paths, instant fixed-answer fake providers — mirroring Module 05/06's own addendum methodology exactly, so as not to pollute the real project database with 75 synthetic files just for timing), comparing the real Module 01→07 chain (including `preview()`/`execute()`) against Module 06's own 40.122s Module 01→06 baseline on the same dataset.
11. Full regression suite (`pytest src/ -q`); confirm zero Module 01–07 source file touched during this session (via real mtimes, since this repo's entire uncommitted implementation history makes `git status`/`git diff` alone unhelpful for this specific check).
12. Archive `metadata_store.json`, `action_log.jsonl`, and every driver script used, under `Runtime/UAT/Module07_UAT_<timestamp>/`; reset the real `Database/`/`Runtime/` to pristine; restore `src/config/sources.yaml`; remove the ephemeral external folders.

## Expected outcomes

Every tier gate outcome (auto executes without a decision, approval-required only with one, review-required never regardless of decision or its absence) holds against real, live-judged content; the real execution-time collision re-check applies correctly; both decision-23 overrides (exact-duplicate and superseded-version) are honored exactly; the forced move failure leaves its file safely retryable without blocking the rest of the batch; the crash simulation reconciles correctly (`SAFE_TO_RETRY` and `REPAIRED`, using the log as authoritative for the latter); CLI-level idempotency holds across a real second and third invocation; undo correctly distinguishes reversible from irreversible executed moves at both batch and single-action granularity; performance at 75-file scale shows no regression against Module 06's own baseline; no crash on the locked/adversarial-filename/duplicate-pair files.

## Pass / Fail

Pass if every expected outcome holds with no Critical/High/Medium finding. Per standing project instruction, a genuine defect found at any point stops the run immediately — reported, not fixed — rather than completing the plan.

---

## Execution Results (Run 1, 2026-07-13, archived at `Runtime/UAT/Module07_UAT_2026-07-13_113200/`)

Run 1 executed the complete plan (steps 1–12) in full against the real code, real project `Database/`/`Runtime/`, and real external Downloads/destination-library folders. **No stop was required — every step completed clean.**

### Steps 1–5: real scan → classify(live) → extract(live) → detect_duplicates → suggest_naming → score_confidence → preview

All 12 files discovered, classified, and extracted via real Claude live judgment (11 provider calls — `Locked_Contract_Vendor.pdf` correctly never reached the provider, routed deterministically by the real `is_locked()` check). Real Module 04/05/06 output:

```
Scored 12 file(s):
  - CrashTest_Alpha.txt: 100 (auto)
  - CrashTest_Beta.txt: 100 (auto)
  - Invoice_Clean_Acme.pdf: 100 (auto)
  - Invoice_Sparse_Draft.pdf: 92 (approval_required)
  - Locked_Contract_Vendor.pdf: 60 (review_required) [hard floor: unknown_category, locked_file]
  - Photo_Sunset_v1.jpg: 88 (approval_required)
  - Photo_Sunset_v2.jpg: 68 (review_required) [hard floor: fuzzy_duplicate]
  - Resume_Alex_v1.pdf: 98 (auto)
  - Resume_Alex_v2.pdf: 98 (auto)
  - Screenshot_Dashboard.png: 88 (approval_required)
  - Utility_Bill_Download.txt: 92 (approval_required)
  - Utility_Bill_Download_copy.txt: 92 (approval_required)

By tier: approval_required: 5, auto: 5, review_required: 2
```

A genuine, organic confirmation worth noting: `Photo_Sunset_v1.jpg`/`Screenshot_Dashboard.png` both landed at 88, not the higher score their single missing optional `capture_date` field alone would suggest — real, correct behavior, since the Screenshot naming template (`Screenshot_{ContextDescription}_{Date}`) references `capture_date` directly, so its absence triggers both `missing_optional_field` (−2) **and** a real `naming_fallback` (−10), exactly as `Rules/Naming Rules.md`/`Rules/Confidence Rules.md` together specify — not a defect, a correct interaction between two already-frozen modules this UAT happened to exercise organically.

`preview()` correctly grouped all 12 into Auto (5) / Needs your decision (5) / Needs attention (2), matching the real persisted tiers exactly.

### Step 6: crash simulation + Call 1 (`main.execute(decisions={})`)

`CrashTest_Alpha.txt` was staged in `Runtime/Temp/` with no move attempted (simulating a crash immediately after staging); `CrashTest_Beta.txt` had a real move performed and a real log entry written, with its `FileRecord` deliberately never saved (simulating a crash between the log write and the record save). A real file was pre-placed at `Invoice_Clean_Acme.pdf`'s naive suggested destination in the real external library folder.

```
Executed batch 2026-07-13_112732 (12 eligible file(s)):
By tier: approval_required: 5, auto: 5, review_required: 2
Executed: 5   Skipped: 7
```

Post-call state confirmed directly against the real, reloaded records:

| Record | processed_at | reversible | current_path |
|---|---|---|---|
| `Invoice_Clean_Acme.pdf` | set | **False** | `.../Finance/Acme_Robotics_Inc_Inv-9001_2026-07-01_2.pdf` (real collision suffix applied — §12) |
| `Resume_Alex_v1.pdf` | set | **False** | `.../~ARCHIVE~/Old Versions/...` (default archive placement) |
| `Resume_Alex_v2.pdf` | set | True | `.../Documents/...` (normal destination) |
| `CrashTest_Alpha.txt` | set | True | `.../Documents/...` (reconciled `SAFE_TO_RETRY`, then executed for real in this same call) |
| `CrashTest_Beta.txt` | set (unchanged from the simulated pre-crash move) | True | `.../Documents/...` (reconciled `REPAIRED`, correctly not re-touched) |

All 7 `approval_required`/`review_required` records confirmed untouched (`processed_at is None`). `Runtime/Temp/`'s plan entry for the batch was confirmed cleared after reconciliation.

### Step 7: Call 2 (`main.execute(decisions=...)`) — real approval decisions, decision 23 ×2, forced failure, adversarial forged decision, no-decision baseline

```
Executed batch 2026-07-13_112732 (7 eligible file(s)):
By tier: approval_required: 5, review_required: 2
Executed: 4   Failed: 1   Skipped: 2
```

- `Photo_Sunset_v1.jpg` (`APPROVE_WITH_EDIT`, edited to `Images/Reviewed/`): executed to `.../Images/Reviewed/...` — **never** `~ARCHIVE~/Old Versions/` (decision 23, superseded-version case).
- `Utility_Bill_Download_copy.txt` (`APPROVE_WITH_EDIT`, edited to `Finance/Reviewed/`): executed to `.../Finance/Reviewed/...` — **never** `~ARCHIVE~/Duplicates/` (decision 23, exact-duplicate case).
- `Utility_Bill_Download.txt` (canonical, `APPROVE_AS_SUGGESTED`) and `Screenshot_Dashboard.png` (`APPROVE_AS_SUGGESTED`): both executed normally to their unedited suggested destinations.
- `Invoice_Sparse_Draft.pdf` (`APPROVE_AS_SUGGESTED`, real `Path.rename` forced to fail for this file's source path only): `processed_at` stayed `None`, the original file was confirmed still present at its pre-move location, and exactly one real `error` action-log entry was written (G6/I4).
- `Locked_Contract_Vendor.pdf` (forged `APPROVE_AS_SUGGESTED`): `processed_at` stayed `None` — the forged decision had zero effect (G3/I2).
- `Photo_Sunset_v2.jpg` (no decision supplied at all): `processed_at` stayed `None`.

### Step 8: Call 3 (`main.execute(decisions=...)`, identical decisions) — CLI-level idempotency

```
Executed batch 2026-07-13_112732 (3 eligible file(s)):
Executed: 1   Skipped: 2
```

Every one of the 11 already-terminal or `review_required` records (all except the one legitimately-retrying record) was confirmed byte-identical (`current_path`/`processed_at`/`approved_by`/`approved_at`/`reversible`/`tier`/`confidence_score`) across this call — zero changes. `Invoice_Sparse_Draft.pdf` legitimately retried and succeeded this time (`processed_at` now set, moved to `.../Finance/Northstar_Supplies_2026-07-02.pdf`) — correct G6 recovery-on-retry, not an idempotency violation, since its Call 2 failure was a one-shot monkeypatch already restored. Exactly one new action-log line appeared, for that legitimate retry.

### Step 9: undo — batch and single-action granularity

```
Reversible flags before undo: Invoice_Clean_Acme=False, Resume_Alex_v1=False,
  Resume_Alex_v2=True, CrashTest_Alpha=True, CrashTest_Beta=True,
  Photo_Sunset_v1=True, Screenshot_Dashboard=True, Utility_Bill_Download=True,
  Utility_Bill_Download_copy=True, Invoice_Sparse_Draft=True
```

`undo_batch()` on the full batch (10 executed records) produced exactly the expected split: `Invoice_Clean_Acme.pdf` (collision-suffixed) and `Resume_Alex_v1.pdf` (archive-landed) both correctly `SKIPPED_IRREVERSIBLE`, left completely untouched at their executed locations; the other 8 all correctly `UNDONE`, restored to their real original paths in the external Downloads folder with their WP-7-owned fields reset. A subsequent single-action test — re-executing the (now-undone, reversible) canonical `Utility_Bill_Download.txt` record and then calling `undo_single_action()` directly against its own fresh log entry — correctly reversed just that one move, restoring its original path independent of any batch-level call.

### Step 10: performance measurement (75-file `Tests/Large Batch/`, isolated `/tmp`, instant fake providers)

```
Discovered: 75  Scored: 75  Executed: 9
Tier spread: {'review_required': 57, 'approval_required': 9, 'auto': 9}
Modules 1-6 (scan->score_confidence) time: 40.066s
preview() time: 0.001s
execute() time: 0.049s
TOTAL Module 1-7 (scan->execute) time: 40.116s
```

Compared against Module 06's own measured baseline for the identical 75-file dataset and methodology (Module 01→06, 40.122s): Module 07's own addition to the chain (`preview()` + `execute()`) measured **0.050s combined** — a **−0.006s (−0.01%)** difference from the prior baseline, i.e., no measurable regression at all; `preview()`/`execute()` are both effectively instantaneous relative to the six upstream stages, consistent with Module 07's own design claim that per-file execution work is dominated by a single real filesystem `rename()` call, not by any heavier computation. **No genuine performance regression found. No fix required.**

### Regression validation

`pytest src/ -q` → **568/568 passed**, unchanged. Real file mtimes for `src/pipeline/execution.py`, `src/main.py`, `src/storage/database.py`, and `src/storage/runtime_io.py` were all confirmed to predate this UAT session's start — none was touched during Run 1 (this repo's entire implementation history remains uncommitted from prior sessions, which makes plain `git status`/`git diff` an unreliable signal for "changed during this specific session" on its own; mtime comparison was used instead, as the precise, disclosed method for this check).

### Housekeeping performed after Run 1

The real `Database/Metadata/metadata_store.json`, `Database/FileIndex/*.json`, `Database/History/version_history.json`, and `Database/Learning/User Corrections.json` were reset to their pristine empty state; the real `Runtime/Logs/action_log.jsonl` was reset to empty; `Runtime/Temp/` was cleared. `src/config/sources.yaml`'s `path`/`destination_root` were restored to `null` (confirmed via `git diff` showing only the same pre-existing, already-uncommitted `destination_root: null` addition from Module 07's original WP-12 implementation — zero residual UAT edits). The external `/tmp/uat_m07_downloads/`, `/tmp/uat_m07_library/`, and `/tmp/m07_uat_perf_run/` folders are ephemeral and were removed; they are not preserved past this session, per the same convention every prior module UAT has followed. Run 1's real results (`metadata_store.json`, `action_log.jsonl`, and all five driver scripts used) are fully preserved in `Runtime/UAT/Module07_UAT_2026-07-13_113200/`.

### Disposition

**No Critical, High, Medium, Low, or Cosmetic finding.** Every dimension this plan required — tier gating (all three tiers, both directions of the auto/approval-required/review-required boundary), the real execution-time collision re-check, both decision-23 override cases, the forced-failure/partial-batch-continuation guarantee, real crash reconciliation (both `SAFE_TO_RETRY` and `REPAIRED`), CLI-level idempotency across three real invocations, undo at both batch and single-action granularity with the correct reversible/irreversible split, and 75-file-scale performance with no regression — is verified clean with direct, real evidence against the live project `Database/`/`Runtime/` and real external folders. **Module 07 UAT is complete. Module 07 is approved to proceed to Release Audit re-certification.**
