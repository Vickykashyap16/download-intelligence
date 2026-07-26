# C1 Completion Report — Real CLI Entry Point

**Status:** CLOSED, 2026-07-23 · **Date:** 2026-07-23 · **Scope:** C1 only (`PRODUCT_READINESS_REVIEW.md` Critical finding C1)

---

## Objectives achieved

Deliver a real, runnable command-line entry point so the pipeline is operable by someone without source-level knowledge of `main.py` — replacing the prior state, where the only documented run path (`python -m src.main`) executed six stages and stopped, leaving `preview()`, `execute()`, `undo()`, and `report()` reachable only by hand-calling internal functions. That objective is met: `python -m src.cli` now provides a full command surface, including a genuine human pause-for-approval step, built entirely from composition over already-tested pipeline functions (no new pipeline logic). The Product Acceptance Test confirmed the core problem — "nobody outside a live Claude session can operate this software" — is resolved, while surfacing real, disclosed UX gaps that do not block this conclusion.

## Scope delivered

`src/cli.py`: 9 subcommands — `scan`, `run`, `preview`, `execute` (`-y`/`--yes`, `--debug`), `undo` (`batch_id` or `--last`), `report`, `status`, `version`, `config`. `execute`'s interactive approval loop is the first concrete resolution of Module 07's Open Decision OD-3 for the attended case: one prompt per `approval_required` record (approve / edit / reject / skip), no implicit default — blank or unrecognized input re-prompts (Engineering Review finding F1). Exit codes: 0 (completed, including "nothing to do"), 1 (unanticipated error, Layer 3), 2 (usage error), 3 (user aborted). Full lifecycle: Design Package → Engineering Review → Implementation (WP-1–WP-9) → Implementation Audit, then Product Validation: PAT Plan (12 scenarios) → Product Acceptance Report → Findings Classification & Release Planning Matrix. All in `Build-out/09 CLI & Product Interface/` and `Tests/`.

## Files added/modified

- **Added:** `src/cli.py` (~440 lines), `src/test_cli.py` (41 tests).
- **Modified:** `src/main.py` — one disclosed, zero-behavior change: `_eligible_for_execution_records()` renamed to public `eligible_for_execution_records()` (both call sites updated), documented in `Governance/ARCHITECTURE_DECISIONS.md` decision 32. `src/test_main.py` — one docstring reference updated to match.
- **Untouched:** every other module's source, contract, and design document; `python -m src.main`'s six-stage chain and `__main__` block, byte-for-byte.
- **Documentation:** `src/README.md`, root `README.md`, `Governance/ARCHITECTURE_DECISIONS.md` (decision 32), `Governance/PROJECT_ROADMAP.md`, `Release/VERSIONS.md`, `TECHNICAL_DEBT_REGISTER.md` (TD-38/39/40 added; TD-01/TD-02 status notes), `PROJECT_BACKLOG.md`, `PRODUCT_READINESS_REVIEW.md`, `CHANGELOG.md`.

## Tests added

41 new tests in `src/test_cli.py`: parser validation for all 9 subcommands; every thin-wrapper command; `_prompt_decision()`'s every branch (approve, edit-both-fields, edit-one-field-defaulted, reject, skip, blank/invalid re-prompt — F1); `_collect_decisions_interactively()`'s tier filtering, skip-remaining, and the zero-`approval_required`-rows case (F6); real end-to-end `execute` scenarios with actual filesystem verification (approve moves the file, reject leaves it, `auto`-tier needs no prompt, `--yes` never prompts); two distinct Ctrl-C tests (during decision-collection vs. during `execute()` itself — the WP-9 audit's own regression test); `undo --last` resolution and both usage-error paths; `status` counts (empty and populated store); `version`/`config` against real files and a simulated-missing file; the Layer 3 exception handler and `--debug`'s re-raise; and `eligible_for_execution_records()`'s public importability.

## Final regression results

**770/770 passing** (729 pre-existing + 41 new), confirmed by a fresh run at closure time. Zero regressions to any Module 01–08 code.

## Product Acceptance verdict

**Accepted with Major Issues** (`Build-out/09 CLI & Product Interface/C1 Product Acceptance Report.md`). The CLI works correctly and is usable by a first-time user for the core scan → preview → approve → execute → undo → report workflow; the "Major Issues" qualifier reflects real, disclosed UX friction (buried error diagnostics, missing configuration surface, inconsistent terminology, no worked examples) rather than any correctness defect — no data-loss, unauthorized-action, or incorrect-filing finding was produced by any of the 12 executed scenarios.

## Known deferred work

Full detail and scoring: `Build-out/09 CLI & Product Interface/C1 Findings Classification & Release Planning Matrix.md` (now the official post-C1 backlog).

- **v0.9 (recommended blockers):** U5/H5 — no `init`/`configure` command (highest-leverage single item); TD-38/TD-39 — a blocked batch's real diagnostic never reaches the terminal, and a retried batch shows stale counts (both pre-existing `main.py` behavior C1 made newly visible). Also targeted at v0.9: C1-PAT-1 (`run`'s name overpromises scope), C1-PAT-4 (cleanup-stage failure reported identically to total failure), C1-PAT-8a (non-interactive `execute` crashes with raw `EOFError`), U1/U3/U4/U8 (naming, `status`/`config` overlap, `--version` flag, missing `--help` examples).
- **v0.95:** TD-40 (no confidence-score breakdown shown), C1-PAT-7 (subcommand-specific usage strings), U2/U6/U7/U9/U10 (individual-stage subcommands, raw UUIDs in prompts, phrasing consistency, inline report content, a `validate`/`doctor` command).
- **v1.0 (unchanged targets, cross-referenced not duplicated):** C1-PAT-2 = TD-01 (no autonomous classification/metadata provider); C1-PAT-8b = TD-02 (unattended approval-decision delivery remains unresolved — the attended case is now resolved by this module).
- **Future:** per-file `execute` targeting.

## Lessons learned

Composition-over-modification held completely: the entire CLI was built from already-tested functions with one disclosed, zero-behavior rename as the sole touch to shipped code. Treating Product Validation as a distinct phase — separate from Engineering Review, run by a "first-time user" mandate rather than a code-correctness mandate — surfaced real findings (buried diagnostics, missing configuration) that a code-level audit alone would not have framed as user-facing problems. Root-cause attribution mattered: two findings (C1-PAT-5/6) were initially miscategorized as new C1 bugs before tracing them to pre-existing Module 07 logic; re-attributing them to Category D avoided overstating C1's own defect count and correctly routed them as new Technical Debt Register entries instead. The isolated QA sandbox (a full repository copy, never the real mounted `Database`/`Runtime`) let PAT scenarios run real commands with real side effects without repeating Module 07's own UAT test-isolation defect.
