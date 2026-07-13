# Module Contract — Module 07 (Preview, Approval & Execution)

The authoritative, tested statement of Module 07's INPUT/OUTPUT/guarantees/DOES NOT MODIFY (`ARCHITECTURE_DECISIONS.md` decision 15) — the only part of this module's design later modules (Module 08) may depend on. Internal architecture (`ExecutionEngine`'s private helpers, `execute_batch()`'s staging mechanics) is not part of this contract and may change freely as long as the behavior below holds. Traces to `Build-out/07 Preview, Approval & Execution/Module 07 Design.md` (frozen 2026-07-12) and its full WP-1–13 implementation record (`Module 07 Implementation Plan.md`). See `Release/DEPENDENCY_DIAGRAM.md` and `Release/VERSIONS.md` for this module's position in the pipeline and its current version.

**Status note:** this contract describes Module 07's implemented, tested behavior as of WP-13 (release engineering). It is written and verified before Integration Testing and UAT have been performed against the real Module 01→07 chain — see `RELEASE_AUDIT.md` for why that gap blocks this module's own release certification, distinct from whether this contract accurately describes the code that exists today (it does).

## INPUT

**Receives:** `List[FileRecord]` from Module 06, filtered to Module 07's own eligibility rule (Design §5): `status == "discovered"`, `category is not None`, `suggested_name is not None`, `confidence_score is not None` (i.e. `tier` populated), **and** `processed_at is None` (Module 07's own CLI-level idempotency addition, `needs_execution()`/§13A). Every field this filter and this module's logic depend on traces to an explicit upstream guarantee:

- `category`, `classification_signals` — Module 02's contract.
- `extracted_metadata` — Module 03's contract (read only for display purposes in `PreviewRow`; not directly, since `PreviewRow` doesn't carry it — Module 07 does not read `extracted_metadata` at all).
- `duplicate_of`, `version_rank` — Module 04's contract (`resolve_precedence()`'s own two non-`review_required` branches).
- `suggested_name`, `suggested_destination` — Module 05's contract.
- `confidence_score`, `confidence_breakdown`, `tier` — Module 06's contract (`tier` read directly, never a cached/precomputed value, at the trust boundary inside `evaluate_gate()`).

**Also receives (§5, §2):**
- An `ApprovalDecision` set (`Dict[str, ApprovalDecision]`, keyed by `file_id`) — one entry per record a human has actually decided on. Absent entries are treated as "not yet decided," never as consent. Module 07 does not produce this set itself (Open Decision OD-3, deliberately out of architectural scope) — `src/main.py`'s `execute(decisions=...)` accepts it as an external parameter, mirroring `classify(provider=...)`/`extract(provider=...)`'s "supplied by the live session" precedent.
- A resolved destination library root — read from `destination_root` in `src/config/sources.yaml` (Open Decision OD-1, `ARCHITECTURE_DECISIONS.md` decision 20), `null` until the user configures it.

## OUTPUT

**Produces / Guarantees:**
- Real filesystem moves/renames, performed only via `Path.rename()` (never copy-then-delete), for every record cleared by the tier gate (§13).
- `FileRecord.current_path`/`processed_at`/`approved_by`/`approved_at`/`reversible` — the five fields this module owns (`ARCHITECTURE_DECISIONS.md` decision 2). Written in exactly three places in the codebase: `ExecutionEngine.execute_file()` step 6 (the forward path), `reconcile_batch()`'s `REPAIRED` branch (crash recovery), and `undo_single_action()` (the reverse path) — each verified structurally by whole-file grep, never a fourth, undisclosed site.
- `Runtime/Logs/action_log.jsonl` entries for `move_rename` / `archive_duplicate` / `archive_superseded_version` / `error` / `reject` / `undo` — every mutating action immediately followed by its own log line (G2), never deferred or batched.
- `Database/Learning/User Corrections.json` entries for every edited or rejected suggestion, captured before execution (§10 step 2, G7) — passive capture only, never read back or auto-applied (NG6).
- `Runtime/Temp/<batch_id>/plan.json`, staged incrementally (one entry immediately before that record's own execution, `ARCHITECTURE_DECISIONS.md` decision 24) and cleared once the batch reaches a terminal state.
- CLI-facing functions `preview()`, `execute(decisions=None)`, `undo(batch_id)` in `src/main.py` (WP-12) — `preview()` is read-only; `execute()` performs real moves; `undo()` is a separate, manually-invoked reversal, never called automatically.

**Verified by:** `src/pipeline/test_execution.py` (188 tests), `src/models/test_execution.py` (13 tests), `src/storage/test_database.py`'s `log_user_correction()` coverage, `src/test_main.py` (13 tests) — see `TEST_RESULTS.md`.

## DOES NOT MODIFY

Every field owned by Modules 01–06, with one disclosed exception (`current_path`, listed under OUTPUT above — Module 01 initializes it at discovery, Module 07 keeps it truthful after a real move, per `FileRecord`'s own field comment). Specifically never written by Module 07: `file_id`, `source_id`, `original_name`, `original_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `category`, `classification_signals`, `extracted_metadata`, `suggested_name`, `suggested_destination`, `naming_signals`, `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals`, `confidence_score`, `confidence_breakdown`, `tier`, `batch_id`. `suggested_name`/`suggested_destination` in particular are read but never overwritten even when a human edits them at approval time (§8.1) — the edited values are executed, never written back onto Module 05's own fields.

Never writes `Runtime/Reports/*` (G9 — exclusively Module 08's). Never touches `Database/FileIndex/`, `Database/History/version_history.json` (undo's explicit non-goal, §15's closing bullet).

## Provider boundary (internal architecture, not part of the external contract)

Module 07 has no Provider of any kind (`ARCHITECTURE_DECISIONS.md` decision 22). The human-approval step is not a judgment call about what a file *is* (the kind of thing Modules 02/03's Engine/Provider pattern exists for); it is a decision by the file's owner about what should happen to it. `ApprovalDecision` is a plain data structure, not a class hierarchy or ABC — deliberately indifferent to how it was produced (Open Decision OD-3, still unresolved; `execute()`'s `decisions` parameter is the only surface this indifference requires).

## `review_required` is never executed, unconditionally (G3/I2)

The single most safety-critical guarantee this module makes: a record with `tier == "review_required"` is never moved or renamed, even if a forged or mistaken `ApprovalDecision` exists for it. Enforced structurally inside `evaluate_gate()`, checked first and absolutely, reading `tier` directly off the `FileRecord` passed in — never a cached/precomputed value from the preview stage. Re-verified directly at the CLI boundary (`src/test_main.py::test_execute_review_required_never_executes_even_with_a_forged_decision`) since WP-12 introduced the first external surface (`execute()`'s `decisions` parameter) through which a forged decision could plausibly arrive from outside this module's own control.

## Reversibility is the default, not an afterthought (G5/G1)

Every executed batch can be undone by replaying its own `move_rename`/`archive_duplicate`/`archive_superseded_version` log lines with `from`/`to` swapped, in reverse-chronological order — no trash folder, no backup copy, the log line *is* the undo mechanism. `reversible = false` is a narrow, explicit exception (a collision-suffixed move, or a move whose original location was inside `~ARCHIVE~/`) surfaced for human review, never silently attempted. No file is ever permanently deleted by any code path in this module, including every failure path (G1/I1).
