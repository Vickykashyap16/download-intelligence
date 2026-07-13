# Module 07 (Preview, Approval & Execution) — Integration Test Plan

Validates the complete interaction between `src/pipeline/watch_ingest.py` (Module 01) through `src/pipeline/confidence.py` (Module 06) and `src/pipeline/execution.py` (Module 07) — real files, real batches, run through the full `scan()` → `classify()` → `extract()` → `detect_duplicates()` → `suggest_naming()` → `score_confidence()` → `preview()` → `execute()` → `undo()` chain, invoked through the real `src/main.py` CLI functions, against `Build-out/07 Preview, Approval & Execution/Module 07 Design.md` (frozen), the Module 01–06 Module Contracts, and Module 07's own fresh Independent Implementation Audit (WP-1 through WP-12, all findings resolved and re-verified), before Module 07 is allowed to proceed to UAT.

Existing unit tests (`src/pipeline/test_execution.py`, 216 of the full 568-test `src/` suite) already cover Module 07's own functions in isolation — `resolve_precedence()`, `resolve_destination_path()`, `evaluate_gate()`, `perform_move()`, `log_move()`, `ExecutionEngine.execute_file()`, `reconcile_batch()`, `execute_batch()`, `capture_user_correction()`, `undo_batch()`/`undo_single_action()` — using synthetic `FileRecord`s constructed directly. This plan is the complementary **integration-level, black-box** pass: real files from `Tests/`, a real seven-module batch, routing fake providers standing in for live Claude judgment (Modules 02/03 only — Module 07 itself has no Provider, decision 22) exactly as Module 03/04/05/06's own Integration Test Plans established as precedent, and real, black-box-inspected persisted output — `execute_batch()`/`ExecutionEngine`/`reconcile_batch()`/`undo_batch()` exercised only as a consequence of the real upstream pipeline's real output and the real CLI functions (`main.preview()`, `main.execute()`), never called directly against hand-built in-memory objects except where this plan explicitly simulates a crash boundary (Run C, documented inline), and no pipeline stage skipped or shortcut.

**Datasets used — 9 files for the primary run (Run A/B), plus 2 additional files for the crash-reconciliation run (Run C), all reused unchanged from Modules 02/04/05's own `Tests/` fixtures; no new files created for this plan:**
- `Tests/Module 05 Naming/Invoice_Alpha.pdf` — clean invoice, every field present (baseline `auto`-tier case, and the execution-time collision target).
- `Tests/Module 05 Naming/Invoice_MissingVendor.pdf` — missing required field → `approval_required`, and the forced-move-failure target (G6/I4 partial-batch continuation).
- `Tests/Module 02 Classification/password_protected_contract.pdf` — locked PDF, `review_required` with two stacked hard floors — the adversarial forged-decision target.
- `Tests/Duplicate Files/invoice_download.txt` / `invoice_download (1).txt` — real Module 04 exact-duplicate pair — the decision-23 edited-destination-overrides-archive-placement target (exact-duplicate case).
- `Tests/Duplicate Files/Resume_v8.pdf` / `Resume_v9.pdf` — real Module 04 version chain — the default-archive-placement (auto tier) and adversarial-forged-decision (review_required, date-token-conflict) targets.
- `Tests/Duplicate Files/product_photo_v1.jpg` / `product_photo_v2.jpg` — real Module 04 near-duplicate pair — the decision-23 edited-destination-overrides-archive-placement target (superseded-version case) and a second adversarial forged-decision target (review_required, fuzzy_duplicate).
- `Tests/Small Batch/notes.txt` (copied twice, as `crash_retry.txt`/`crash_repaired.txt`) — clean auto-tier fixtures for Run C's crash/restart reconciliation scenarios.

Test IDs map to this plan's sections: `F` functional (preview/execution/tier-gate outcomes), `ADV` adversarial, `COL` collision, `D23` decision-23 override, `FAIL` forced-failure/partial-batch continuation, `CR` crash/restart reconciliation, `IDEM` CLI-level idempotency, `UNDO` undo, `REG` regression.

**Because `ClaudeLiveClassifier.classify()`/`ClaudeLiveExtractor.extract()` are documented placeholders** (fulfilled live by Claude during a real agent-driven run, not autonomous code), every Module 02/03 judgment call in this plan uses a routing fake provider (`RoutingClassificationProvider`/`RoutingMetadataProvider`, keyed by filename substring), mirroring Module 03/04/05/06's own Integration Test Plan precedent exactly. **Module 07 itself has no Provider at all (design decision 22 — approval decisions come from the human/CLI, not a judgment layer) and needed no fake; it uses its real, unmodified implementation throughout.** This proves the plumbing — the real Module 01→07 handoff, Module Contract boundaries, and persisted output — works correctly end-to-end. It does not, and cannot, validate the *quality* of live Claude's classification/extraction judgment — that remains UAT's job, not this plan's.

`main.py`'s real `scan()` reads its source folder from `load_source_config()`; `main.load_source_config` is monkeypatched to return the isolated test source folder's path, and `main._SOURCES_CONFIG_PATH` is monkeypatched to an isolated `sources.yaml` carrying a real `destination_root` — the same category of test-only isolation as monkeypatching the `Database`/`Runtime` path constants, not a shortcut around any pipeline stage (every line of every CLI function's own real logic still executes against real files and a real destination library folder on disk).

---

## 1. Functional scenarios — full pipeline through preview (Run A)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M07-F01 | Full six-stage pipeline (Modules 01–06) runs cleanly against a real 9-file batch, feeding Module 07 real, fully-populated records | All 9 fixtures | All 9 discovered, classified, extracted, duplicate/version-checked, named, and scored; tier spread includes all three tiers (`auto`, `approval_required`, `review_required`). |
| M07-F02 | `preview()` is read-only — no file moved, no metadata/log write | Full 9-file batch | Metadata store and action log byte-identical before and after `main.preview()`; console output correctly buckets all 9 records into "Auto" / "Needs your decision" / "Needs attention" groups matching their real tiers. |

## 2. Functional scenarios — execution, all tiers (Run B)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M07-F03 | `auto` tier executes without any decision supplied | `Invoice_Alpha.pdf` | `processed_at` set, `approved_by == "auto"`, file physically moved. |
| M07-F04 | `auto` tier + `superseded_version` override lands at its default archive placement | `Resume_v8.pdf` | Executes to `~ARCHIVE~/Old Versions/...`, `reversible` computed `False` (§15). |
| M07-F05 | `approval_required` tier executes only with an explicit decision | `invoice_download.txt`/`invoice_download (1).txt` (canonical + edited-destination duplicate) | Both execute only because a decision was supplied for each. |

## 3. Adversarial — forged decisions for `review_required` records (G3/I2)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M07-ADV01 | A forged `APPROVE_AS_SUGGESTED` decision for a `review_required` record must be ignored — `review_required` records are never eligible for execution, decision or not | `password_protected_contract.pdf` (locked, two hard floors) | `processed_at` stays `None`; `current_path` unchanged; forged decision has zero effect. |
| M07-ADV02 | Same guarantee, second independent `review_required` record | `product_photo_v2.jpg` (`fuzzy_duplicate`) | `processed_at` stays `None`. |
| M07-ADV03 | `review_required` record with **no decision supplied at all** is also correctly skipped (baseline, not adversarial, but exercised in the same batch) | `Resume_v9.pdf` (date-token conflict) | `processed_at` stays `None`. |

## 4. Real execution-time collision re-check (§12)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M07-COL01 | A real file pre-placed at a record's naive suggested destination forces a genuine collision re-check at execution time, not just at preview time | `Invoice_Alpha.pdf`, with a real file pre-written to `Finance/Acme_Corp_Inv-001_2026-06-01.pdf` before `execute()` runs | Final `current_path` differs from the naive suggested path (a numeric suffix applied); the pre-placed collision file is never overwritten; `reversible` computed `False` (§15, collision-suffixed). |

## 5. Decision 23 — edited destination overrides archive placement

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M07-D23-01 | An `APPROVE_WITH_EDIT` decision on an `exact_duplicate`-routed record must honor the edited destination, not the default `~ARCHIVE~/Duplicates/` placement | `invoice_download.txt` (the duplicate, edited to `Finance/Reviewed/`) | Executes to `Finance/Reviewed/...`, never `~ARCHIVE~/Duplicates/...`. |
| M07-D23-02 | Same guarantee for `superseded_version` | `product_photo_v1.jpg` (edited to `Images/Reviewed/`) | Executes to `Images/Reviewed/...`, never `~ARCHIVE~/Old Versions/...`. |
| M07-D23-03 | Control: the canonical (non-duplicate) record in the same pair executes normally, unaffected | `invoice_download (1).txt` | Executes to its normal suggested destination, no archive involved. |

## 6. Forced per-file failure / partial-batch continuation (G6/I4)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M07-FAIL01 | A real OS-level move failure for one file must leave that file safely un-executed and retryable, without raising out of `execute_batch()` | `Invoice_MissingVendor.pdf` (`Path.rename` monkeypatched to raise only for this file's real source path) | `processed_at` stays `None`; original file still exists at its pre-move location; an `error` action-log entry is written. |
| M07-FAIL02 | Every other eligible record in the same batch still executes despite one file's forced failure | The other 4 eligible records in the same `execute()` call | All 4 reach `processed_at is not None`. |

## 7. Restart / crash reconciliation (§13A)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M07-CR01 | A batch staged in `Runtime/Temp/` with no move yet attempted (crash before any filesystem action) resolves `SAFE_TO_RETRY` on reconciliation, and reconciliation alone does not execute anything | `crash_retry.txt` (auto tier), plan staged, no move performed | `reconcile_batch()` returns `SAFE_TO_RETRY`; `processed_at` still `None` after reconciliation. |
| M07-CR02 | A real move + real log entry with the `FileRecord` deliberately never updated (crash between log write and record save) resolves `REPAIRED` on reconciliation, using the log entry's own recorded values as authoritative | `crash_repaired.txt` (auto tier), real move performed, log written, record save skipped | `reconcile_batch()` returns `REPAIRED`; post-reconciliation, `processed_at` is set and `current_path` matches the real move; `reversible` correctly computed `True` (normal destination, no archive, no collision suffix). |
| M07-CR03 | `Runtime/Temp/` plan entry is cleared after reconciliation resolves it | Same batch | `read_batch_plan(batch_id)` returns `None` after `reconcile_batch()`. |
| M07-CR04 | A real restart (`main.execute()` called again) actually retries and completes the `SAFE_TO_RETRY` record, and does not re-touch the already-`REPAIRED` record (I7 idempotency) | Same batch, second `execute()` call | `crash_retry.txt` reaches `processed_at is not None` and its file is really moved; `crash_repaired.txt`'s `processed_at` is unchanged from its post-reconciliation value. |

## 8. CLI-level idempotency

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M07-IDEM01 | A second `execute()` call with the same decisions dict leaves every already-terminal or `review_required` record byte-identical | Run B's batch, re-invoked with the same decisions | `current_path`/`processed_at`/`approved_by`/`approved_at`/`reversible`/`tier`/`confidence_score` unchanged for all 8 already-resolved records. |
| M07-IDEM02 | A record whose move genuinely failed on the first call (and was never persisted as processed) legitimately retries and succeeds on the second call — correct G6 recovery, not an idempotency violation | `Invoice_MissingVendor.pdf` | New action-log lines appear only for this record; it reaches `processed_at is not None` on the second call. |

## 9. Undo — batch and single-action granularity

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M07-UNDO01 | Collision-suffixed and archive-landed moves are correctly recorded `reversible == False`; normal-destination moves are `reversible == True` | Run B's 5 executed records | `Invoice_Alpha.pdf`/`Resume_v8.pdf` → `False`; the other 3 → `True`. |
| M07-UNDO02 | `undo_batch()` produces one outcome per executed record, correctly split between `SKIPPED_IRREVERSIBLE` and `UNDONE` | Same 5 records | 2 `SKIPPED_IRREVERSIBLE`, 3 `UNDONE`. |
| M07-UNDO03 | Irreversible records are left completely untouched by undo | `Invoice_Alpha.pdf`/`Resume_v8.pdf` | Still at their executed location, still `processed_at is not None`. |
| M07-UNDO04 | Reversible records are fully restored — path, and all WP-7-owned fields reset — and become eligible for execution again | The other 3 records | `current_path == original_path`; `processed_at`/`approved_by`/`approved_at` all `None`; `needs_execution()` true again. |
| M07-UNDO05 | Single-action granularity: `undo_single_action()` reverses one specific log entry directly, independent of batch undo | A re-executed canonical record, undone via its own fresh log entry | Path restored, `processed_at` reset — without touching any other record. |

## 10. Regression validation

| ID | Objective | Method | Expected result |
|---|---|---|---|
| M07-REG01 | Full existing unit suite still passes | `pytest src/ -q` | All unit tests pass, no new failures introduced by this integration pass. |
| M07-REG02 | No Module 01–06 source file modified during this pass | `git diff --stat` (content-based, not mtime) | No `pipeline/watch_ingest.py`, `pipeline/classification.py`, `pipeline/metadata.py`, `pipeline/duplicate_detector.py`, `pipeline/naming.py`, or `pipeline/confidence.py` change present. |
| M07-REG03 | No Module 07 source file modified during this pass either (zero defects found → no fix needed) | Same `git diff` check | `pipeline/execution.py` shows no new edits beyond what was already implemented and independently audited before this session began. |

---

## 11. Expected outputs

For a real batch run through the full `scan()` → `classify()` → `extract()` → `detect_duplicates()` → `suggest_naming()` → `score_confidence()` → `preview()` → `execute()` → `undo()` chain, a correct Module 07 integration: never executes a `review_required` record regardless of any decision supplied or absent (G3/I2); executes `auto`-tier records without requiring a decision and `approval_required`-tier records only with one; re-checks for filesystem collisions at the moment of execution, not just at preview time, and never overwrites a real colliding file; honors an edited destination over a default archive-placement override exactly per decision 23; continues processing every other eligible record in a batch when one file's move fails at the OS level, logging the failure and leaving that one record safely retryable; correctly reconciles a `Runtime/Temp/`-staged batch after a simulated crash, in both the no-move-attempted and moved-but-unrecorded cases, using the action log as the authoritative source of truth for the latter; is idempotent across repeated `execute()` calls for every already-resolved record while still correctly allowing a genuinely-failed-and-unrecorded record to retry; and correctly distinguishes reversible from irreversible executed moves at undo time, both at batch and single-action granularity, never silently reversing a collision-suffixed or archive-landed move.

## 12. Pass / fail criteria

Each case above passes only if every assertion in its expected result holds simultaneously against the real implementation — not a partial match. The plan as a whole passes if every executable case passes and the regression suite (§10) shows no new failures. Per the standing instruction for this integration-testing phase, any genuine implementation or design defect discovered here is stopped on immediately, not auto-fixed, and reported as its own finding using the project's standard severity scale (`Governance/ENGINEERING_STANDARD.md` §14): **Critical** (data loss, irreversible action, or a crash that halts the pipeline), **High** (a core guarantee — determinism, idempotency, Module Contract, or a designed gate/reversibility outcome — is violated), **Medium** (a designed behavior is incomplete or a test gap allows a real defect to go undetected), **Low** (a minor correctness or completeness gap with limited blast radius), or **Cosmetic** (documentation/wording only, no behavioral impact) — each with a recommended smallest fix. A failure traced to this plan's own test-harness code (fixture construction, isolation setup, or assertion logic) rather than to `src/pipeline/execution.py` or its Module 01–06 dependencies is a harness-authoring error, corrected in the harness and disclosed in Execution Results, not counted as a Module 07 finding — the same distinction Module 03/04/05/06's own Integration Test Plans draw.

---

## Execution Results (run against the real code, 2026-07-13)

All sections above were implemented as a real, executable Python harness (`m07_integration_harness.py`, not a permanent pytest file — mirroring Module 03/04/05/06's own precedent that only this markdown plan persists) and run against the real `src/pipeline/watch_ingest.py`, `src/pipeline/classification.py`, `src/pipeline/metadata.py`, `src/pipeline/duplicate_detector.py`, `src/pipeline/naming.py`, `src/pipeline/confidence.py`, `src/pipeline/execution.py`, and the real `src/main.py` CLI functions, using isolated `Database`/`Runtime` paths (monkeypatched module-level path constants pointed at a fresh `/tmp` tree, exactly as Module 04/05/06's own precedent) and an isolated destination-library folder, so nothing touched the project's real store, logs, or `Downloads`-equivalent. `main.load_source_config` and `main._SOURCES_CONFIG_PATH` were monkeypatched to point at the isolated test source folder and an isolated `sources.yaml` (real `destination_root`), so the real `scan()`/`execute()` functions ran unmodified against real files and a real destination folder, without editing `src/config/sources.yaml`.

**Run A (9-file primary batch), executed via the real CLI functions in sequence — `main.scan()` → `main.classify(provider=fake_cls)` → `main.extract(provider=fake_meta)` → `main.detect_duplicates()` → `main.suggest_naming()` → `main.score_confidence()` → `main.preview()`:**

```
Classified 9 file(s):
  - Invoice_Alpha.pdf: Invoice
  - Invoice_MissingVendor.pdf: Invoice
  - Resume_v8.pdf: Resume
  - Resume_v9.pdf: Resume
  - invoice_download (1).txt: Invoice
  - invoice_download.txt: Invoice
  - password_protected_contract.pdf: Unknown [locked]
  - product_photo_v1.jpg: Screenshot
  - product_photo_v2.jpg: Screenshot

Checked 9 file(s) for duplicates/versions — Exact duplicates: 1, Near-duplicates: 1, Version chains: 4, Conflicts flagged: 1

Scored 9 file(s):
  - Invoice_Alpha.pdf: 100 (auto)
  - Invoice_MissingVendor.pdf: 82 (approval_required)
  - Resume_v8.pdf: 98 (auto)
  - Resume_v9.pdf: 73 (review_required)
  - invoice_download (1).txt: 92 (approval_required)
  - invoice_download.txt: 92 (approval_required)
  - password_protected_contract.pdf: 60 (review_required) [hard floor: unknown_category, locked_file]
  - product_photo_v1.jpg: 88 (approval_required)
  - product_photo_v2.jpg: 68 (review_required) [hard floor: fuzzy_duplicate]

By tier: approval_required: 4, auto: 2, review_required: 3

Pipeline stages 1-6 took 5.050s for 9 files

Previewing 9 file(s):
Auto (will execute without further input) — 2:
  - Invoice_Alpha.pdf -> Finance/Acme_Corp_Inv-001_2026-06-01.pdf
  - Resume_v8.pdf -> ~ARCHIVE~/Old Versions/Resume_Jordan_Lee_2026-04-01.pdf
Needs your decision — 4:
  - Invoice_MissingVendor.pdf, invoice_download (1).txt, invoice_download.txt [exact_duplicate], product_photo_v1.jpg [superseded_version]
Needs attention (never auto-filed) — 3:
  - Resume_v9.pdf, password_protected_contract.pdf, product_photo_v2.jpg

Module 07 preview complete — no files have been moved.
```

**Run A: 12/12 checks passed** — all 9 files discovered/classified/scored; tier assignments confirmed for `Invoice_Alpha` (auto), `Invoice_MissingVendor` (approval_required), `password_protected_contract` (review_required); exact-duplicate pair, version chain, and asymmetric near-duplicate flag all confirmed against real Module 04 output; `preview()` confirmed to write nothing to the metadata store or action log (byte-identical before/after).

**Run B (execution — all tiers, adversarial, collision, decision 23, forced failure), via `main.execute(decisions=decisions)`:**

```
Executed batch 2026-07-13_111853 (9 eligible file(s)):
By tier: approval_required: 4, auto: 2, review_required: 3
Executed: 5   Failed: 1   Skipped (review_required or no decision yet): 3
execute() took 0.007s
```

**Run B: 33/33 checks passed** — both `review_required` records with forged `APPROVE_AS_SUGGESTED` decisions (`password_protected_contract.pdf`, `product_photo_v2.jpg`) correctly never executed (G3/I2); the `review_required` record with no decision at all (`Resume_v9.pdf`) also correctly never executed; `Invoice_Alpha.pdf` (auto) executed with `approved_by == "auto"`; `Resume_v8.pdf` (auto, superseded_version) executed to its default `~ARCHIVE~/Old Versions/` placement; the real execution-time collision re-check applied a numeric suffix to `Invoice_Alpha.pdf`'s final path (differing from the naive, pre-collided path) and never overwrote the pre-placed collision file (§12); decision 23 correctly honored both edited destinations (`invoice_download.txt`'s exact-duplicate override to `Finance/Reviewed/`, `product_photo_v1.jpg`'s superseded-version override to `Images/Reviewed/`), neither landing in `~ARCHIVE~/`; the canonical duplicate record executed normally to its unedited destination; `Invoice_MissingVendor.pdf`'s forced `Path.rename` failure left it correctly un-executed and its original file untouched, with a real `error` action-log entry written (G6/I4); every other eligible record in the same batch still executed despite that one failure.

**Run C (restart / crash reconciliation, fresh second batch — `crash_retry.txt`/`crash_repaired.txt`):**

```
Scanned /tmp/m07_it_run/downloads — Discovered: 6 (2 new: crash_repaired.txt, crash_retry.txt)
Checked for duplicates: Exact duplicates: 1 (crash_retry.txt is an exact duplicate of crash_repaired.txt)
Scored: crash_repaired.txt: 100 (auto), crash_retry.txt: 100 (auto)
```

Both crash-test records reached `auto` tier and shared one fresh batch_id, distinct from Run B's batch. (a) `crash_retry.txt` was staged in `Runtime/Temp/` with no move attempted, simulating a crash immediately after staging. (b) `crash_repaired.txt` had a real move performed and a real log entry written, but its `FileRecord` was deliberately never updated/saved, simulating a crash between the log write and the record save.

```
[PASS] Plan staged for retry_rec with no move yet attempted
[PASS] Real move for repaired_rec succeeded
[PASS] repaired_rec's FileRecord deliberately NOT updated yet (simulated crash)
[PASS] Reconciliation: retry_rec resolved SAFE_TO_RETRY
[PASS] Reconciliation: repaired_rec resolved REPAIRED
[PASS] repaired_rec repaired: processed_at now set, current_path matches the real move
[PASS] repaired_rec repaired: reversible correctly computed True
[PASS] retry_rec still un-executed after reconciliation alone
[PASS] Runtime/Temp plan cleared after reconciliation

Executed batch 2026-07-13_111858 (5 eligible file(s)) — Executed: 1, Skipped: 4

[PASS] Restart recovery: retry_rec successfully executed on the real restart call
[PASS] Restart recovery: retry_rec's file really moved
[PASS] Restart recovery: repaired_rec untouched by the restart execute() call (I7 idempotency)
```

**Run C: 47/47 checks passed** — a single `reconcile_batch()` call correctly resolved both the not-yet-attempted crash case (`SAFE_TO_RETRY`) and the moved-but-unrecorded crash case (`REPAIRED`, using the log entry's own values as authoritative and correctly recomputing `reversible == True` for this normal-destination move); the `Runtime/Temp/` plan was cleared after reconciliation; a real second `main.execute()` call (simulating a restart) correctly completed the retryable record and left the already-repaired record untouched.

**Run D (CLI-level idempotency, re-invoking Run B's batch with the same decisions):**

```
Executed batch 2026-07-13_111858 (4 eligible file(s)) — Executed: 1, Skipped: 3
```

**Run D: 50/50 checks passed** — every already-terminal or `review_required` record's fields (`current_path`, `processed_at`, `approved_by`, `approved_at`, `reversible`, `tier`, `confidence_score`) were byte-identical across the second call; new action-log lines appeared only for `Invoice_MissingVendor.pdf`, which legitimately retried and succeeded on this second call (its Run B failure was a one-shot monkeypatch, already restored — correct G6 recovery-on-retry, not an idempotency violation; `needs_execution()`'s I7 eligibility rule correctly still selected it since `processed_at` was never set after the forced failure).

**Run E (undo — batch and single-action granularity):**

```
[PASS] Invoice_Alpha/Resume_v8 correctly recorded reversible=False (collision-suffixed / landed in ~ARCHIVE~); the other three recorded reversible=True
[PASS] Undo report has one outcome per executed record
[PASS] Undo report correctly marks the two irreversible records SKIPPED_IRREVERSIBLE
[PASS] Undo report correctly marks the three reversible records UNDONE
[PASS] Both irreversible records left completely untouched by undo
[PASS] Undo restored all three reversible records to their original paths, reset their WP-7-owned fields, and made them eligible for execution again
[PASS] Single-action undo (undo_single_action()) directly reversed a freshly re-executed record's move, independent of batch undo
```

**Run E: 71/71 checks passed** — `Invoice_Alpha.pdf` (collision-suffixed) and `Resume_v8.pdf` (archive-landed) were both correctly recorded `reversible == False` and left completely untouched by `undo_batch()`, surfaced for human review rather than silently reversed (§15/NG7); the other three executed records were correctly restored to their original paths with all WP-7-owned fields reset and `needs_execution()` true again; `undo_single_action()` was confirmed to work independently of batch undo, reversing one specific log entry directly without touching any other record.

**Final: 71/71 integration checks passed. Zero failures.**

### Harness corrections during development (disclosed, not Module 07 findings)

Three issues surfaced while building the harness, all traced directly to the harness's own fixture construction, not to `src/pipeline/execution.py` or any upstream module — confirmed by reading the real implementation before concluding anything, per this project's standing discipline:

1. **Missing `ensure_destination_folder()` call before a manually-constructed `perform_move()` in Run C's REPAIRED simulation** — the harness initially skipped this step (unlike `ExecutionEngine.execute_file()`'s own real sequence), causing a `[Errno 2] No such file or directory`. Fixed by adding the same `ensure_destination_folder(final_path.parent)` call `execute_file()` itself makes.
2. **Wrong field shape supplied for the exact-duplicate pair's fake metadata** — initially Document-shaped fields were supplied for a pair classified as Invoice, landing the pair at `review_required` instead of the `approval_required` tier needed to exercise decision 23's edited-destination override. Fixed by supplying Invoice's real required fields (`vendor`, `invoice_date`) and omitting the four optional fields, correctly landing at score 92.
3. **Run D's idempotency check was initially over-scoped**, comparing the entire store byte-for-byte including `Invoice_MissingVendor.pdf`, which legitimately (and correctly) retried and succeeded on the second call. Fixed by scoping the byte-identical comparison to only the 8 already-terminal/`review_required` records, with a separate explicit check confirming the legitimate retry.

None of these three required any change to `src/pipeline/execution.py` or any other production file.

### Regression validation (§10) results

- **M07-REG01:** `pytest src/ -q` → **568/568 passed.**
- **M07-REG02:** `git diff --stat` confirmed zero changes to `pipeline/watch_ingest.py`, `pipeline/classification.py`, `pipeline/metadata.py`, `pipeline/duplicate_detector.py`, `pipeline/naming.py`, or `pipeline/confidence.py`.
- **M07-REG03:** `pipeline/execution.py` shows no new edits introduced during this Integration Testing pass — only the implementation already in place and independently audited before this session began.

### Conclusion

Every functional, adversarial, collision, decision-23, forced-failure, crash-reconciliation, CLI-level-idempotency, and undo case this plan checked passed against the real Module 07 implementation and its real Module 01–06 dependencies, run as a genuine seven-module batch through isolated storage, an isolated destination library, and the real CLI entry points — not against Module 07 in isolation, and not through any implementation shortcut. The full regression suite (568 unit tests) passed unchanged, and no Module 01–07 source file was modified during this pass. The three issues encountered during harness development were all root-caused to this plan's own fixture/harness construction and corrected there, consistent with the standing instruction not to modify implementation absent a genuine, reproduced defect.

**No Critical, High, Medium, Low, or Cosmetic finding was raised during this Integration Testing pass. Module 07 Integration Testing is complete with zero defects found (71/71 checks passed).**
