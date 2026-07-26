# H5 — Configuration Experience — Design Package

**Status:** Design Phase 1 — DESIGN ONLY, per explicit instruction. No code has been written, no repository file other than this new document (and its companion Engineering Review) has been touched.
**Origin:** `PRODUCT_READINESS_REVIEW.md` High finding H5 ("Configuration — injectable Downloads path, destination root, tunable constants"), named as a v0.9 roadmap item; independently rediscovered during C1's Product Acceptance Test as **U5** ("no `init`/`configure` command"), which the approved `Build-out/09 CLI & Product Interface/C1 Findings Classification & Release Planning Matrix.md` scored as the single highest-leverage item in the whole review and targeted at v0.9. Selected per the user's explicit instruction as the next work package, following C1's closure.
**Date:** 2026-07-23.
**Author role:** Software Architect (design phase only — per this project's established C1 precedent).
**Naming:** Tracked throughout as **H5**, its originating ID in `PRODUCT_READINESS_REVIEW.md` — not assigned a new ID, to avoid the exact duplicate-tracking risk this project's own Release Planning Matrix was built to prevent (U5, TD-30, and H5 are one and the same underlying gap, confirmed below, not three separate items).

---

## 1. Problem Statement

No configuration surface exists for this project's two required runtime settings — the Downloads source path and the destination library root (`destination_root`) — beyond hand-editing `src/config/sources.yaml` directly. Verified directly against the real, current code (`src/pipeline/watch_ingest.py`, `src/main.py`, `src/cli.py`), this produces three distinct, evidenced consequences:

1. **A raw, alarming crash on first run.** `load_source_config()` raises a plain `ValueError` when the source path is unset, the source is missing/disabled, or `execution_mode` isn't `manual`. Neither `main.scan()` nor `src/cli.py`'s `_cmd_scan`/`_cmd_run` catch it, so it propagates to `main()`'s outermost Layer 3 handler and prints `"Unexpected error: ..."` with exit code 1 — identical framing to a genuine bug. This is C1-PAT-1, found and evidenced during C1's Product Acceptance Test: *"a first-run, entirely expected 'you haven't configured this yet' condition is printed... with the same framing and severity signal as a genuine bug, despite the message content itself being accurate and actionable."*
2. **A second, closely related but distinct gap, found during this design's own repository impact analysis, not previously named:** if the source path *is* set but points to a folder that no longer exists (moved, renamed, a typo during manual editing), `scan_source()` raises `NotADirectoryError` — again uncaught by the CLI, again surfacing as the same generic `"Unexpected error"` framing. Not the same condition as (1) — "never configured" and "configured wrong" are different problems a user needs different guidance for — but currently indistinguishable at the CLI's output.
3. **No settings surface of any kind exists to prevent either condition in the first place.** `TECHNICAL_DEBT_REGISTER.md` TD-30 names this plainly: *"no config for `destination_root` beyond a single hardcoded value; no settings surface of any kind... blocking for distribution."* The only existing way to set either value today is opening `src/config/sources.yaml` in a text editor and hand-writing YAML — a bar this project's own C1 Product Acceptance Test already established most first-time users won't clear unguided.

## 2. Goals

- **G1.** Give a first-time user a guided, validated way to set the Downloads source path and `destination_root` without hand-editing YAML.
- **G2.** Replace today's generic, alarming crash (consequence 1 above) with a specific, actionable message pointing at the fix, for both the "never configured" and "configured wrong" cases (consequence 2).
- **G3.** Let an already-configured user change a single value without re-running a full wizard.
- **G4.** Validate configuration inputs at configuration time (does the path exist? is it a directory?) rather than only discovering a problem later, mid-run.
- **G5.** Never make it easier to lose or corrupt existing configuration than it is today (hand-editing a text file is trivially reversible with a text editor's own undo; this work package's guided path must be at least as safe).

## 3. Non-goals

Stated explicitly, per this project's disclosure discipline, rather than silently narrowed:

- **NG1 — Multi-source support (TD-11).** v1 has exactly one source (`source_id: downloads`). `init`/`config set` configure that one source only; adding a second source is out of scope and unrelated to this work package.
- **NG2 — Injectable base paths for `Database/`/`Runtime/` storage (TD-29).** A separate, larger architectural change (hardcoded `_PROJECT_ROOT`-relative constants in `storage/database.py`/`storage/runtime_io.py`) needed before packaging this as an installable app for a second user. Not touched here.
- **NG3 — "Tunable constants" from `Rules/*.md` (TD-07).** `PRODUCT_READINESS_REVIEW.md`'s original H5 finding bundled "tunable constants" into "Configuration" alongside the source/destination paths. Verified against `TECHNICAL_DEBT_REGISTER.md`: this is TD-07, a materially larger and different surface (business-rule constants hardcoded across four pipeline modules, not loaded dynamically from `Rules/`). Bundling it here would turn a small, high-leverage fix into a large, unbounded one — explicitly narrowed out, disclosed as a deliberate scope reduction from H5's original framing, not an oversight.
- **NG4 — A GUI or web settings page.** This is a CLI-only wizard (`init`) and a CLI flag extension (`config set`), consistent with `PRODUCT_READINESS_REVIEW.md`'s own roadmap sequencing (a real interface is explicitly sequenced *after* the automation/configuration gap, not before).
- **NG5 — `execution_mode` or `recursive` become configurable.** `load_source_config()` only supports `execution_mode: manual` today (raises otherwise); `recursive: false` is a disclosed, deliberate v1 boundary (TD-09). Neither is prompted for or writable by this work package — exposing a setting the rest of the pipeline can't actually honor would be worse than not exposing it at all.
- **NG6 — A non-interactive/scriptable `init` (e.g. `init --force --source=... --destination=...`).** Considered; deferred as a natural companion to H2 (packaging/installer), not required for the guided, human-driven first-run case this work package targets. See R4 in §10.
- **NG7 — Any change to `execute_batch()`'s own existing `destination_root`-unset handling.** Already correct (blocks and logs per-record, never crashes — verified in `src/main.py` §"`_load_destination_root()`"). This work package makes that state less likely to be *reached* unconfigured; it does not change what happens if it is.

## 4. User Stories

- As a first-time user, I want to run one command that asks me for my Downloads folder and my destination library folder, so I can start using the tool without opening a YAML file in a text editor.
- As a user who mistypes a path during setup, I want to be told immediately that the path doesn't exist, not discover it only when `execute` silently blocks every file.
- As a user running `scan`/`run` for the first time with no configuration, I want a specific, actionable message telling me to run `init` — not a message that looks like the tool crashed.
- As a user whose Downloads folder moved or was renamed after I configured it, I want a message that clearly says "this path doesn't exist" — distinct from "you never configured this" — so I know what actually needs fixing.
- As a user who already has a working configuration, I want to change one value (e.g. just `destination_root`) without re-answering questions I already answered correctly.
- As a user who runs `init` a second time by mistake, I want to be shown my current values and asked to confirm before anything is overwritten — not have a working configuration silently replaced.

## 5. Functional Requirements

- **FR-1.** A new `init` subcommand launches an interactive wizard prompting for the Downloads source path, then `destination_root`, in that order.
- **FR-2.** Each prompted path is validated (exists, is a directory) before being accepted. Invalid input re-prompts the same question — no silent default, no partial acceptance — mirroring C1's own Engineering Review finding F1 (`_prompt_decision()`'s "no implicit default" correction), applied here to path input instead of an approval decision.
- **FR-3.** `init` writes both values into `src/config/sources.yaml`, preserving every other existing key, comment, and blank line in the file exactly as it was (see §9, Recommended Architecture, for how).
- **FR-4.** `init` never silently overwrites an already-configured value. If `sources.yaml` already has a non-null value for either setting, `init` shows the current value and requires explicit confirmation (`y`/`n`, no default — same no-implicit-default discipline as FR-2) before replacing it.
- **FR-5.** `config` (existing, read-only today) gains a `set` form: `config set source <path>` and `config set destination <path>`, each validating and writing exactly one value via the same writer FR-3 uses, without touching the other value or launching the full wizard.
- **FR-6.** `scan` and `run` (both of which begin by calling `main.scan()`) must catch the two specific, already-enumerated exception types `load_source_config()`/`scan_source()` raise for a configuration problem (`ValueError` — not configured; `NotADirectoryError` — configured but the path doesn't exist) at the CLI dispatch layer, and print a distinct, actionable message for each: "not configured — run `init`" versus "configured path doesn't exist — run `init` or `config set source <path>` to fix it." Both cases exit 0 (§8, NFR-4/exit-code rationale), matching this project's established "an expected, already-understood precondition failure is not a program error" exit-code philosophy (C1 Design Package §3.5).
- **FR-7.** `--help` for `init` and `config set` states plainly what each command changes, and that hand-editing `src/config/sources.yaml` directly remains equally valid and is not being deprecated.
- **FR-8.** `init`/`config set` never write to any file other than `src/config/sources.yaml`. No `Database/`, `Runtime/`, or other `src/config/` file is touched.

## 6. Non-functional Requirements

- **NFR-1 (No new pipeline logic).** `init`/`config set` write exactly the two already-defined config keys (`sources[0].path`, `destination_root`) that already exist in `sources.yaml` today (`Governance/ARCHITECTURE_DECISIONS.md` decision 20). No new schema, no new key.
- **NFR-2 (Preserve file structure exactly).** `src/config/sources.yaml`'s existing comments are load-bearing documentation (cross-references to `ROADMAP.md`, `Module 07 Design.md` §11/§26, `Governance/ARCHITECTURE_DECISIONS.md` decision 20) — a naive `yaml.safe_load()` + `yaml.dump()` round-trip would silently discard all of them. This must not happen (§9 addresses how).
- **NFR-3 (Never silently overwrite).** Restates FR-4 as a hard non-functional constraint, not just a UX nicety — matches this project's non-negotiable "every action must be reversible" ethos as applied to configuration, not only to filed/moved files.
- **NFR-4 (Honest, not reassuring, output).** Every message states the real condition plainly — matches C1's own established NFR-4 exactly, extended here to configuration-error messages specifically.
- **NFR-5 (No new dependency).** `PRODUCT_READINESS_REVIEW.md` High finding H1 already flags this project's dependency manifest as broken/contradictory (PyYAML pinned twice to different versions in `requirements.txt`) and unresolved. Introducing a new third-party dependency (e.g. a comment-preserving YAML library) while H1 is open would compound an already-flagged problem rather than fix anything — this design must use only what's already imported (`PyYAML`, already used by `src/cli.py` and `src/pipeline/watch_ingest.py`) or the standard library.
- **NFR-6 (Backward compatible).** Hand-editing `sources.yaml` directly remains fully supported and unaffected; `init`/`config set` are additive convenience paths, not a replacement mechanism.

## 7. Repository Impact Analysis

### 7.1 What exists today — verified directly

- `src/config/sources.yaml` — read in full. Five keys: `sources` (one entry: `source_id`, `path: null`, `type`, `enabled`, `recursive: false`), `execution_mode: manual`, `destination_root: null`. Every value line has an adjacent explanatory comment.
- `src/pipeline/watch_ingest.py`'s `load_source_config()` — read in full. Raises `ValueError` in exactly four enumerated conditions: `execution_mode != "manual"`, source not found, source disabled, source has no `path`. Never returns a partial/best-effort result.
- `src/pipeline/watch_ingest.py`'s `scan_source()` — confirmed via direct read: raises `NotADirectoryError` if the configured path isn't a directory (line 365-366). A second, distinct failure mode from the above.
- `src/main.py`'s `scan()` — calls `load_source_config()` directly, no `try`/`except`. `src/cli.py`'s `_cmd_scan`/`_cmd_run` call `main.scan()` (aliased `run_scan`) with no `try`/`except` either — both exception types currently reach `main()`'s outermost Layer 3 handler.
- `src/cli.py`'s existing `_cmd_config` — read-only today, explicitly says so ("Editing is not yet supported from the CLI — edit `src/config/sources.yaml` directly"). This work package is what makes that line no longer true, and it must be removed/updated as part of this change.
- `src/main.py`'s `_load_destination_root()` — confirmed already correct and out of scope (NG7): returns `None`, never raises, if `destination_root` is unset; `execute_batch()`'s own `_validate_library_root()` handles that case per-record, not by crashing.
- No writer for `sources.yaml` exists anywhere in the codebase today — every existing reader (`load_source_config()`, `_cmd_config`, `_cmd_status`) only calls `yaml.safe_load()`. This is genuinely new capability, not a composition over an existing function — disclosed plainly, same as C1's own two new-logic additions (the interactive approval loop, `status`'s aggregation).

### 7.2 What does NOT change

- No change to any `Rules/*.md` business rule, any `src/pipeline/*.py` pipeline module, any `src/models/*.py`, `src/storage/*.py`, or any Module 01–08 contract/design document.
- No change to `load_source_config()`, `scan_source()`, or `_load_destination_root()` themselves — their existing raise/return behavior is correct and is *read*, not modified, by this work package's new exception handling in `src/cli.py`.
- `python -m src.main`'s direct-invocation behavior is unaffected — an unconfigured `python -m src.main` run still raises a raw traceback exactly as it does today; only `python -m src.cli`'s wrapping catches and reframes it (same boundary C1 itself already established and disclosed — the CLI is a wrapper, not a modification, of `main.py`'s own behavior).
- `execute_batch()`, `_validate_library_root()`, and every already-tested Module 07 execution-time check are untouched (NG7).

### 7.3 What DOES change

1. **New functions in `src/cli.py`:** a small, targeted config-writer (§9), `_cmd_init`, an extended `_cmd_config` (adding the `set` subform), and narrow exception handling wrapped around `_cmd_scan`/`_cmd_run`'s existing call to `run_scan()`.
2. **`src/config/sources.yaml` gains a new, opt-in write path** — not a structural change to the file's schema (no new key), a new way an existing key's value can be set.
3. **Documentation only:** `src/README.md`'s CLI command list, `src/cli.py`'s own `--help` text, `CHANGELOG.md` (at implementation time, not part of this design-phase deliverable).

Nothing else in the repository is touched.

### 7.4 Where this design package lives, and why

Same reasoning as C1's own §1.4: `init`/`config set` are CLI surface, not a new pipeline step — they extend the same `src/cli.py` file C1 created and live naturally alongside it. Placed in `Build-out/09 CLI & Product Interface/`, matching C1's own precedent exactly rather than opening a new numbered folder for what is, in code terms, an extension of the same file.

## 8. Architecture Options

**Option A — Full YAML round-trip via `yaml.safe_load()` + `yaml.dump()` (PyYAML, already a dependency).** Simplest possible implementation, reusing exactly the library already imported everywhere else in this codebase. **Rejected:** PyYAML's `dump()` does not preserve comments — the first `init`/`config set` invocation would silently discard every explanatory comment currently in `sources.yaml`, including direct cross-references to `ROADMAP.md` and `Governance/ARCHITECTURE_DECISIONS.md` decision 20. This is a real, disclosed documentation loss, not a cosmetic one — rejected on NFR-2 grounds.

**Option B — Comment-preserving YAML round-trip via `ruamel.yaml` (a new dependency).** Would solve Option A's comment-loss problem robustly and generalize to any future structural change to the file. **Rejected for now:** introduces a new third-party dependency while `PRODUCT_READINESS_REVIEW.md` High finding H1 (broken/contradictory `requirements.txt`) remains open and unaddressed — adding a new dependency into an already-flagged-broken manifest is worse timing than the problem it would solve is worth, per NFR-5. Not rejected forever: if a future work package resolves H1 and there's a second reason to need general comment-preserving YAML editing (e.g. NG1's multi-source support eventually landing), this becomes the right choice then.

**Option C — Targeted, line-level text replacement for exactly the two known scalar values (source path, `destination_root`), leaving every other line untouched.** Not a general YAML editor — a small, narrow function that finds the specific line matching the source's `path:` key (inside the `sources:` block, indentation-aware) or the top-level `destination_root:` key, and replaces only that line's value, leaving every comment, blank line, and every other key byte-for-byte identical. **Selected — see §9.**

**Option D — A CLI flag/argument on every invocation instead of a persisted setting (no config file write at all).** Already considered and rejected once, for the identical reason, in `Governance/ARCHITECTURE_DECISIONS.md` decision 20 (destination_root's own original design): forces re-supplying an absolute path on every invocation, a usability regression against this project's "configure once, run many times" pattern. Not reconsidered here — decision 20 already settled this question for `destination_root`, and the same reasoning applies identically to the source path.

## 9. Recommended Architecture

**Option C — targeted, line-level text replacement**, given `sources.yaml`'s confirmed small, stable, single-source shape (§7.1) and NFR-5's dependency constraint. Concretely:

- `_write_config_value(key_pattern: str, new_value: str) -> None` — a small helper in `src/cli.py` that reads `sources.yaml` as plain text (not YAML-parsed), finds the one line matching a specific, narrow regex for the target key (e.g. `^(\s*path:\s*).*$` scoped to appear after the `sources:` block's `- source_id: downloads` line, or `^(destination_root:\s*).*$` at the top level), replaces only that line's value (preserving the line's own leading whitespace and any inline comment structure it does *not* itself carry — both target lines' comments live on the line *above* them in the real file, confirmed by direct read, so this is not a concern in practice), and writes the file back.
- **Write-then-verify, not atomic temp+rename.** No file write anywhere else in this codebase (`storage/database.py`, `storage/runtime_io.py`) uses an atomic temp-file-plus-rename pattern — every existing write is a direct `write_text()` call. Matching that existing convention rather than introducing a new one, `_write_config_value()` writes directly, then immediately re-reads and `yaml.safe_load()`s the result, asserting the target key now equals the intended value. If the assertion fails (the regex matched the wrong line, or produced invalid YAML), the function reports a clear, specific failure — "the write may not have applied correctly, check `src/config/sources.yaml` directly" — rather than silently declaring success or attempting automatic recovery. This is a disclosed, deliberate proportionality choice, not an oversight: `sources.yaml` is a small, rarely-written, human-invoked config file, not the `execute()` hot path `plan.json` staging exists to protect (`Governance/ARCHITECTURE_DECISIONS.md` decision 24) — a lighter safety net than atomic rename is appropriate here, and is stated as a judgment call for Engineering Review to accept or overrule.
- `_cmd_init(args)` — reads current `sources.yaml` state first (reusing `_cmd_config`'s existing read logic); for each of the two settings, if a value is already set, shows it and requires an explicit `y`/`n` confirmation (no default, FR-4) before prompting for a replacement; prompts for a path, validates it (`Path(...).expanduser().resolve()`, checks `.is_dir()`), re-prompts on invalid input (no default, FR-2); writes via `_write_config_value()`; finally prints a confirmation summary reusing `_cmd_config`'s existing display formatting.
- `_cmd_config` extended with a `set` subform (`config set source <path>` / `config set destination <path>`) that validates and writes exactly one value via the identical `_write_config_value()` helper `_cmd_init` uses — one writer, two entry points, avoiding the duplicated-validation-logic risk this project's PT-002/PT-003 postmortems specifically warn about (the same reasoning C1's own Alternative D rejected duplicating `_eligible_for_execution_records()`'s filter).
- `_cmd_scan`/`_cmd_run` — both call a new small shared helper, `_run_scan_with_friendly_config_errors() -> Optional[int]`, which wraps the existing call to `run_scan()` in a `try/except` catching only `ValueError` and `NotADirectoryError` — the two specific, fully-enumerated exception types `load_source_config()`/`scan_source()` are confirmed (§7.1) to raise for a configuration problem — and returns an exit code (0, per FR-6) with a distinct, actionable message for each; returns `None` if `run_scan()` succeeded, so both callers know to continue (`_cmd_run` proceeds to `classify()`, etc.; `_cmd_scan` simply returns 0).

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **R1.** The targeted line-replacement writer corrupts `sources.yaml` if the file's structure ever drifts from the narrow shape it expects (e.g. hand-edited into a different indentation style). | Low | Medium (a broken config file, not a broken pipeline — `load_source_config()` would raise a clear YAML-parse error on the next read, not silently misbehave) | Write-then-verify (§9): every write is immediately re-parsed and checked; a mismatch is reported clearly, never silently accepted. |
| **R2.** Catching `ValueError` broadly in `_cmd_scan`/`_cmd_run` could misclassify a genuinely unrelated future `ValueError` (e.g. from code added later deeper in the call chain) as "not configured." | Low today, grows over time | Medium (a real bug reported with a misleading, too-reassuring message) | The catch wraps only the single call to `run_scan()`, not a broader scope; `load_source_config()`'s four raise conditions are fully enumerated and confirmed (§7.1) to be the only source of `ValueError` on this path today. Documented explicitly in the implementation (a comment noting this assumption) so a future contributor adding a fifth `ValueError`-raising branch to `load_source_config()` knows this CLI code depends on "every `ValueError` from this call is a configuration issue." |
| **R3.** Path validation at `init`/`config set` time (does it exist, is it a directory) doesn't guarantee the path stays valid later, at `execute` time (deleted, renamed, or unmounted in between). | Low-Medium | Low (already independently handled) | Not a new gap this work package introduces — `execute_batch()`'s own already-tested `_validate_library_root()` (NG7) is the real safety net at execution time; `init`'s validation is a first-run UX improvement only, explicitly not a substitute for it. |
| **R4.** No non-interactive `init` exists (NG6) — a future automated installer or CI/test-fixture setup can't script configuration without either hand-writing `sources.yaml` (already fully supported, NFR-6) or driving `init`'s prompts via simulated stdin. | Low | Low | Explicitly deferred, not overlooked — pairs naturally with H2 (packaging/installer) once that work begins; hand-editing remains a fully valid, unaffected path for any automated use today. |
| **R5.** New user-facing prompt/confirmation text drifts from C1's own already-established tone (`NFR-4`, "honest, not reassuring"), since it's authored in a separate work package. | Low | Low (a consistency, not a safety, issue) | All new prompt/message wording is explicitly modeled on C1's own §3.3/§3.6 precedent (word choice, structure, `[a/e/r/s]`-style explicit-no-default framing) — cited directly in this design rather than reinvented. |

No risk in this table rises to "could cause an unauthorized file move, data loss, or silent configuration corruption" without an accompanying, independently-testable mitigation — matching the bar this project's risk assessments (C1, PT-002, PT-003) have consistently held to.

## 11. Migration Strategy

Not a data migration in the schema sense — no new key is added to `sources.yaml` (both `sources[0].path` and `destination_root` already exist as keys today, per `Governance/ARCHITECTURE_DECISIONS.md` decision 20; this work package only adds a *guided way to set* them). Explicitly:

- Every existing `sources.yaml` — including the real, live, currently-`null` installation file — continues to load and behave exactly as today with zero interaction from this change. `init`/`config set` are opt-in, explicitly invoked commands; nothing about this work package runs automatically on any existing read path (`load_source_config()`, `_cmd_config`, `_cmd_status` are all unmodified read paths).
- No version bump, no schema flag, no backward-compatibility shim is required.

## 12. Testing Strategy

(For the implementation phase — not run yet; design-phase only, per the STOP POINT.)

- **T1.** `_write_config_value()`: writing a new source path, and separately a new `destination_root`, against a copy of the real `sources.yaml` produces a file that (a) parses correctly, (b) has exactly the target key changed, and (c) is byte-for-byte identical to the original in every other line, including every comment — the single highest-value test given this design's Option C architecture (§9's core claim).
- **T2.** `_write_config_value()`'s write-then-verify failure path: simulate a write that doesn't take effect (e.g. a monkeypatched read-back) and confirm a clear failure is reported, not silent success.
- **T3.** `_cmd_init`'s prompting, via simulated stdin: valid path accepted; nonexistent/non-directory path re-prompts (FR-2); already-configured value shown and requires explicit `y` before overwrite, and is left unchanged on `n` or blank (FR-4, no default).
- **T4.** `_cmd_config set source <path>` / `set destination <path>`: each changes exactly the targeted value; the other value and all comments are confirmed unchanged (reusing T1's byte-diff technique).
- **T5.** `_cmd_scan`/`_cmd_run` against an unconfigured `sources.yaml` (path unset): friendly "not configured — run init" message, exit 0, `run_scan()`'s own `ValueError` message still shown (not replaced, per NFR-4).
- **T6.** `_cmd_scan`/`_cmd_run` against a configured-but-nonexistent path: friendly, distinctly-worded "path doesn't exist" message, exit 0.
- **T7.** `_cmd_scan`/`_cmd_run` against a valid, fully-configured installation: unaffected — behaves exactly as it does today (a non-regression check specifically for R2).
- **T8.** Full project regression suite (770/770 as of C1's closure) passes at 100% after the change, confirming zero impact outside `src/cli.py`.

## 13. Rollback Strategy

Two distinct senses of "rollback," addressed separately:

- **Rollback of this code change:** `_write_config_value()`, `_cmd_init`, `_cmd_config`'s `set` form, and the `_run_scan_with_friendly_config_errors()` wrapper are new, additive functions entirely within `src/cli.py`. Rollback is deleting them and reverting `_cmd_config`/`_cmd_scan`/`_cmd_run` to their pre-change bodies — a single, small, fully-diffable revert. No `Database/`/`Runtime/` file, no other module, no schema is touched, so rollback carries zero risk to any persisted pipeline state.
- **Reversibility of a user's own configuration action (distinct from code rollback):** `init`/`config set` are not filing/moving actions — this project's `undo()` mechanism exists specifically to reverse `execute()`'s file moves and does not apply to configuration edits, and this work package does not extend it to. A configuration value set via `init`/`config set` is reversible exactly the way a hand-edit of `sources.yaml` always has been: run `init`/`config set` again, or edit the file directly (NFR-6). FR-4's overwrite-confirmation is the relevant safety property here, not a new undo capability — stated explicitly so this isn't mistaken for a gap.

## 14. Work Packages

(Implementation-phase plan, following this project's established WP-numbering convention — **not started**, per the STOP POINT.)

- **WP-1 — `_write_config_value()` targeted writer + write-then-verify.** The design's foundational, highest-risk-if-wrong piece (R1); built and tested in isolation first, mirroring C1's own "highest-consequence piece gets its own dedicated work package" precedent (C1 WP-4). Tests T1, T2.
- **WP-2 — `_cmd_init`: prompting, validation, overwrite-confirmation.** Tests T3.
- **WP-3 — Extend `_cmd_config` with the `set` subform.** Tests T4. Also removes/updates the now-inaccurate "Editing is not yet supported from the CLI" line (§7.1).
- **WP-4 — `_run_scan_with_friendly_config_errors()` wrapper for `_cmd_scan`/`_cmd_run`.** Tests T5, T6, T7.
- **WP-5 — `--help` text for `init` and `config set` (FR-7), top-level `--help` command list updated.**
- **WP-6 — Full regression suite + `src/README.md` documentation update.** Test T8; AC-1 through AC-8 verified together as a single acceptance pass.
- **WP-7 — Independent Implementation Audit**, matching every prior module's and C1's own post-implementation audit precedent.

## 15. Acceptance Criteria

- **AC-1.** `python -m src.cli init` against a freshly-unconfigured `sources.yaml` successfully sets both the source path and `destination_root` after validated prompting, and the resulting file parses correctly with every pre-existing comment line unchanged.
- **AC-2.** Running `init` a second time against an already-configured file shows the current values and requires explicit confirmation before overwriting either one; declining leaves the file unchanged.
- **AC-3.** `config set source <path>` / `config set destination <path>` each change exactly the targeted value, leaving the other value and every comment untouched.
- **AC-4.** `scan`/`run` against an unconfigured installation print a specific, actionable "not configured — run `init`" message and exit 0 — never the generic `"Unexpected error"` framing.
- **AC-5.** `scan`/`run` against a configured-but-nonexistent path print a distinctly-worded "path doesn't exist" message (not the same text as AC-4) and exit 0.
- **AC-6.** `scan`/`run`/`preview`/`execute`/`undo`/`report`/`status`/`version`/`config` (read) against a valid, fully-configured installation are unaffected — identical behavior to before this work package.
- **AC-7.** Full regression suite passes at 100%.
- **AC-8.** No file other than `src/config/sources.yaml` (via `_write_config_value()`) is ever written by `init`/`config set` — verified by asserting no mtime change on any `Database/`/`Runtime/`/`Release/` file across a run of each.

---

**STOP POINT, per explicit instruction: no implementation work package above has been started, no repository file other than this design document has been touched. This document, together with the separate Engineering Review, is the complete Phase 1 deliverable. Waiting for approval before any code is written.**
