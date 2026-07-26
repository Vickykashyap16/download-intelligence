# C1 — Real CLI Entry Point — Implementation Audit (WP-9)

**Scope:** `src/cli.py` (new), `src/test_cli.py` (new), the one disclosed touch to `src/main.py` (the `eligible_for_execution_records()` rename), and the corresponding docstring update in `src/test_main.py`.
**Reference:** `C1 CLI Entry Point — Design Package.md` and `C1 CLI Entry Point — Engineering Review.md` (this folder). Implementation followed WP-1 through WP-8 of the approved Implementation Plan exactly; no scope expansion, no architectural changes, no module contract touched.
**Method:** Fresh, adversarial re-read of the actual diff against the approved design and against Engineering Review findings F1/F2/F3/F4/F6 (F5 required no code change, only confirmation) — not a restatement of the implementation's own commit messages.

---

## Design/review conformance

- **F1 (blank-input default removed) — confirmed in code, not just claimed.** `_prompt_decision()`'s `while True` loop has no branch that returns on empty/unrecognized input other than the explicit `"Please enter a, e, r, or s."` re-prompt; `test_prompt_decision_blank_input_reprompts_no_default` exercises three consecutive invalid responses (`""`, `"   "`, `"zzz"`) before a valid one, asserting the re-prompt text appears exactly three times.
- **F2 (rename rationale documented) — confirmed.** `eligible_for_execution_records()`'s docstring in `main.py` states both options considered (rename vs. importing the private name across the boundary) and why the rename was chosen; `Governance/ARCHITECTURE_DECISIONS.md` decision 32 carries the same reasoning as the permanent record.
- **F3 (severity reconciled) — confirmed.** Decision 32 classifies C1 as High on the existing scale; no "Product Enhancement" label appears in any file this implementation touched (verified by grep).
- **F4 (Build-out README description) — confirmed.** Root `README.md`'s folder tree and its "mapped 1:1 to the 8 numbered Build-out folders" line are both corrected to account for the new, non-pipeline-stage `09 CLI & Product Interface/` folder.
- **F6 (zero-approval_required test) — confirmed.** `test_collect_decisions_zero_approval_required_rows_prompts_nothing` asserts `input()` is never called and `{}` is returned when `approval_required` is empty.
- **F5 (staleness between prompt-loop and execute())** — no code change was ever required per the Engineering Review's own disposition; re-verified directly against the final code: `_cmd_execute()` never passes its own `records`/`rows` snapshot into `run_execute()` — only the `decisions` dict, keyed by `file_id`. `main.execute()` still calls `eligible_for_execution_records()` fresh, internally, exactly as it did before C1. Confirmed unchanged.

## Backward compatibility

Confirmed by direct inspection, not inference: `src/main.py`'s `if __name__ == "__main__":` block is byte-for-byte unchanged (still exactly `scan(); classify(); extract(); detect_duplicates(); suggest_naming(); score_confidence()`). No function in `src/pipeline/*.py`, `src/models/*.py`, or `src/storage/*.py` was modified — confirmed by `git status`, which shows only `src/main.py`, `src/test_main.py`, `src/cli.py` (new), `src/test_cli.py` (new), and documentation files touched. `eligible_for_execution_records()`'s four-condition filter body is identical to the pre-rename version; both of its own call sites (`preview()`, `execute()`) were updated in the same change, and both functions' behavior is confirmed unchanged by the full regression suite (every pre-existing Module 07 CLI test in `test_main.py` still passes against the renamed function).

## Finding — identified and corrected during this audit

**KeyboardInterrupt message overclaimed safety for one interrupt point it didn't actually cover.** The first complete draft of `_cmd_execute()` let any `KeyboardInterrupt` — from anywhere in the command, including from inside `run_execute()` itself — propagate to `main()`'s single, generic handler, which printed "Aborted — no files have been moved." That claim is true by construction for an interrupt during decision-collection (nothing has been handed to `execute()` yet), but is not true for an interrupt landing during `run_execute()`'s own execution — e.g. mid-batch, after some `auto`-tier files have already been moved but before the batch finishes. A user hitting Ctrl-C at that exact moment would have been told, incorrectly, that nothing moved.

**Severity:** Low-Medium. Not a safety defect — no file is filed incorrectly or without authorization, and the underlying `execute_batch()`/`ExecutionEngine` machinery this sits on top of is unaffected and already independently tested (Module 07's own release record). The defect is in the accuracy of a status message during a narrow, low-probability timing window (a user interrupting during the literal seconds a batch is being written to disk) — but this project's own standing discipline (`ARCHITECTURE_DECISIONS.md` decisions 18/19, "never guess, always disclose accurately") treats an inaccurate status message as a real finding, not a cosmetic one, so it is recorded and fixed here rather than waved through.

**Fix applied:** `_cmd_execute()` now catches `KeyboardInterrupt` locally, only around the `_collect_decisions_interactively()` call — the one point this design actually guarantees is a clean no-op — and prints the specific message there. `main()`'s generic handler (covering every other interrupt point: mid-scan, mid-`run_execute()`, etc.) now prints a message that does not repeat the "no files have been moved" claim. Both the module-level docstring and the inline comments at both call sites were updated to state this distinction precisely, so a future reader isn't left to rediscover it. One new regression test (`test_cmd_execute_keyboard_interrupt_during_run_execute_uses_generic_message`) simulates a `KeyboardInterrupt` raised from inside `run_execute()` after decision-collection has already completed cleanly, and asserts the generic (non-overclaiming) message is used instead. The existing `test_cmd_execute_keyboard_interrupt_never_calls_execute_batch` test (interrupt during `input()`) continues to pass unmodified, confirming the specific-message path still works for its own, narrower, correctly-scoped case.

No other finding rose to a level worth recording as a defect. Two points were checked and confirmed non-issues rather than left unexamined:

- The double read of `eligible_for_execution_records()` (once in `_cmd_execute()` to build the preview rows, once again inside `main.execute()` itself) is a minor, harmless redundancy, not a bug — already covered by the Engineering Review's F5 disposition, re-confirmed here against the final code rather than re-litigated.
- `--debug` is wired only on the `execute` subcommand's parser, matching the design's own explicit scoping ("execute --debug" only) — not a gap, a deliberate, disclosed limit.

## Test and regression results

`src/test_cli.py`: 41/41 passing, covering the parser (valid/invalid combinations), every thin-wrapper command, the interactive approval loop's every branch (approve/edit-both-fields/edit-one-field-defaulted/reject/skip-remaining/blank-input re-prompt/zero-approval_required rows), `--yes`, both real-filesystem end-to-end execute scenarios (approve moves the file, reject leaves it, auto-tier needs no prompt), both Ctrl-C cases (decision-collection vs. mid-`run_execute()`), `undo --last`'s resolution logic and both usage-error paths, `status`'s counts against an empty and a populated store, `version`/`config` against both the real files and a simulated-missing file, the renamed helper's public importability, and the Layer 3 exception handler including `--debug`'s re-raise.

Full project regression suite: **770/770 passing** (729 pre-existing + 41 new), run fresh as the final step of this audit, not carried over from an earlier pass. Zero failures, zero new skips, zero collection errors.

## Verdict

**No unresolved Critical/High/Medium findings.** One Low-Medium finding was identified and corrected within this same audit cycle, with a regression test added and the full suite re-confirmed green afterward — the same "find, fix, re-verify, document" pattern this project's Implementation Audits have followed for every prior module (e.g. Module 07's WP-7 `save_file_record()` correction). C1 is implementation-complete per the approved design and Engineering Review, with every review finding (F1, F2, F3, F4, F6) applied and F5 re-confirmed, plus one additional, self-identified correction beyond the original review's own scope.

Per the user's explicit instruction, this completes WP-1 through WP-9 of the approved Implementation Plan. No production code beyond C1's own approved scope was touched; no other module's contract, design, or release status changed.
