# Release Notes — Module 07 (Preview, Approval & Execution)

```
Pipeline Version: 0.7.0
Module Version: 1.0.0
Date: 2026-07-13
Status: Frozen, Released
```

See `Release/VERSIONS.md` for the authoritative version ledger.

**Deployment model, stated plainly:** `auto`-tier records file themselves with zero human input, in either an interactive or unattended run. Everything else (`approval_required`, `review_required`) currently requires a live Claude session to supply the approval decisions — there is no autonomous mechanism for producing them in v1. See `KNOWN_LIMITATIONS.md`.

Module 07 is the human checkpoint and the pipeline's first (and only) filesystem-mutating stage: it shows the whole batch's proposed outcome, obtains (or, for `auto` tier, forgoes) a human decision, then executes — reversibly, auditably, never destructively. It is the first module in this pipeline capable of moving, renaming, or archiving a real file, and the first capable of undoing its own work.

## Features implemented

- `preview_batch()` — pure, read-only batch preview generation, grouped by tier.
- `evaluate_gate()` — the tier gate, Module 07's single most safety-critical function: `review_required` is never executed, unconditionally, even against a forged approval.
- `resolve_precedence()`/`resolve_destination_path()` — the four-step override precedence order (`review_required` → exact duplicate → superseded version → normal), with an edited destination honored uniformly across every override type except `review_required` (`ARCHITECTURE_DECISIONS.md` decision 23).
- `check_real_collision()`/`apply_collision_suffix()`/`perform_move()` — real, execution-time collision detection and a `Path.rename()`-only move (never copy-then-delete).
- `ExecutionEngine` — the fixed six-step per-file sequence: gate → resolve destination → collision re-check → move → log → update record.
- `reconcile_batch()` — five-step crash-reconciliation procedure, using the real on-disk file location as the tie-breaker whenever the log and `FileRecord` disagree.
- `execute_batch()` — batch orchestration: reconciliation first, fixed processing order, incremental `plan.json` staging one record at a time (`ARCHITECTURE_DECISIONS.md` decision 24), a Layer-2 safety net so one file's failure never aborts the batch.
- `log_user_correction()`/`capture_user_correction()` — every edit or rejection captured to `Database/Learning/User Corrections.json`, passive-capture only.
- `undo_batch()`/`undo_single_action()` — reverse-chronological batch undo, restoring `FileRecord` to a state `needs_execution()` recognizes as eligible again.
- `preview()`/`execute(decisions=None)`/`undo(batch_id)` — CLI wiring in `src/main.py`, with `execute()` accepting an externally-supplied decision set (Open Decision OD-3's pluggability preserved) and `undo()` a strictly manual, never-automatic command.
- `destination_root` — a new key in `src/config/sources.yaml` (Open Decision OD-1), read by the CLI layer.

## Bugs fixed

- **WP-7 correction (High, discovered during WP-9 scoping).** `ExecutionEngine.execute_file()` mutated its five owned `FileRecord` fields in memory but never persisted them — every successful execution's bookkeeping was lost on process exit. Fixed by adding `save_file_record()` immediately after the mutation, matching `reconcile_batch()`'s own already-approved pattern.
- **WP-2 destination-override ambiguity (Medium).** The frozen design never stated whether a human's edited destination could override the exact-duplicate/superseded-version archive placement. Resolved via `ARCHITECTURE_DECISIONS.md` decision 23: it can, `review_required` remains the sole absolute exception. `resolve_destination_path()` and its tests were corrected to match.
- **Implementation Plan documentation inconsistency (Medium, found during the composed-system architecture audit).** WP-1 through WP-8 had inline completion-status notes; WP-9 through WP-12 did not, despite equal completion. Fixed by appending the missing notes, append-only.
- **Test-isolation gap (Medium, found during release validation, before Integration Testing began).** 8 test functions in `src/pipeline/test_execution.py` called `_isolate_action_log()` but omitted `_isolate_database_and_temp()`, causing them to silently write synthetic fixture data into the real `Database/Metadata/metadata_store.json` on every regression-suite run since the WP-7 persistence correction. Fixed by adding the missing isolation call to exactly the 8 affected functions; no other test or production code changed. A scripted, function-by-function audit of every test file in `src/` that writes to persistent storage confirmed zero remaining gaps.

## Breaking changes

None to any Module 01–06 contract. Verified structurally (content-diffed, not mtime alone) at every stage from WP-1 through this release. `src/main.py` gained new functions (`preview()`/`execute()`/`undo()`); no existing CLI function in that file was modified.

## Improvements

- Twelve independent implementation-work-package audits (WP-1 through WP-12), each with zero unresolved Critical/High findings, one High finding resolved (the WP-7 persistence correction), and three Medium findings resolved (WP-2's ambiguity, its corrective implementation, and the Implementation Plan status-note inconsistency).
- A dedicated composed-system architecture audit after WP-1–WP-8 and again after WP-1–WP-12, each covering every Architecture Decision, Guarantee, Non-Guarantee, and Invariant fresh, not by trusting individual WP audits alone.
- A dedicated architecture review of the CLI/orchestration boundary before any WP-12 code was written, certifying all seven ownership boundaries preservable and OD-3's pluggable design future-proof.
- Full regression suite grown from 352/352 (Module 06's baseline) to 568/568, zero regressions at any step across the whole implementation and release-validation lifecycle.
- **Integration Testing** (`Tests/Module 07 Integration Test Plan.md`) — a real, executable harness against the full Module 01→07 chain (isolated storage, routing fake Module 02/03 providers): all three tiers, two independent adversarial forged-decision cases, a real execution-time collision re-check, both decision-23 override cases, forced-failure/partial-batch continuation, crash/restart reconciliation (both `SAFE_TO_RETRY` and `REPAIRED`), CLI-level idempotency, and undo at both granularities. **71/71 checks passed, zero findings.**
- **UAT** (`Tests/Module 07 UAT Plan.md`) — a real external Downloads-like folder and real external destination-library folder, real live-Claude-judged Module 02/03 content, and the real project `Database`/`Runtime` (per Module 06 UAT's own established precedent). Three real `main.execute()` invocations exercised the same dimension set against real human approval decisions. **Zero findings.**
- **Performance measurement** — the complete real Module 01→07 chain (`scan()` through `execute()`, including `preview()`) measured **40.116s** against `Tests/Large Batch/`'s 75 files, versus Module 06's own **40.122s** Module 01→06 baseline on the identical dataset — no measurable regression; `preview()`/`execute()` together added only 0.050s.
- A final independent Release Audit (`RELEASE_AUDIT.md`), re-run fresh after Integration Testing and UAT, confirming all 13 Pipeline Contract Verification checks, all 24 Architecture Decisions, all 10 Guarantees, all 7 Non-Guarantees, and all 8 Invariants — zero remaining Critical/High/Medium findings.
