# GUI Milestone M1 — Release Candidate Audit

**Scope:** WP-GUI-00 through WP-GUI-11. WP-GUI-12 is intentionally excluded — blocked by OD-GUI-5 and OD-GUI-6.
**Method:** Direct verification against current repository state (git history, source, tests, design docs). Read-only — no code modified, no new features proposed.
**Date:** 2026-08-01.

---

## 1. Completed Milestones

All twelve work packages are implemented and traceable to commits:

| WP | Feature | Tag | Status |
|---|---|---|---|
| WP-GUI-00 | SwiftPM foundation / EngineBridge skeleton | `wp-gui-00-v2`, `beta-foundation-complete` | Complete |
| WP-GUI-00A | Concurrency validation | `wp-gui-00a`, `wp-gui-00a-final` | Complete |
| WP-GUI-01 | App shell / navigation | `v0.9.0-beta` | Complete (off-convention tag — see §5) |
| WP-GUI-01A | Folder validation | `wp-gui-01a` | Complete |
| WP-GUI-02 | Onboarding / First Run | `wp-gui-02-complete` | Complete (commit message ambiguity — see §5) |
| WP-GUI-03 | Home dashboard | `wp-gui-03`, `wp-gui-03-complete` | Complete |
| WP-GUI-04 | Scan flow | `wp-gui-04-final` | Complete |
| WP-GUI-05 | Preview flow | `wp-gui-05-final` | Complete |
| WP-GUI-06 | Review queue | `wp-gui-06-final` | Complete |
| WP-GUI-07 | Execute flow | `wp-gui-07-final` | Complete (test-plan note — see §4) |
| WP-GUI-08 | Undo flow | `wp-gui-08-final` | Complete (test-plan note — see §4) |
| WP-GUI-09 | History | `wp-gui-09-final` | Complete |
| WP-GUI-10 | Reports | `wp-gui-10-final` | Complete |
| WP-GUI-11 | Settings | `wp-gui-11-final` | Complete |

User-confirmed: `swift build` PASS, `swift test` PASS, 416/416 tests, zero compiler warnings. The previously outstanding `AppShell.swift` unreachable-`default:` warning is resolved and verified present in the `wp-gui-11-final` tagged commit — the fix is committed, not just applied locally.

All 13 feature directories under `Sources/DownloadsIntelligenceApp/` (Onboarding, Home, Scan, Preview, Review, Execute, Undo, History, Reports, Settings, Navigation, Lifecycle, Components) plus `EngineBridge` (28 source files) have corresponding, non-trivial test coverage.

---

## 2. Open Dependencies

| ID | Title | Status | Blocks |
|---|---|---|---|
| OD-GUI-1 | — | Resolved within M1 | — |
| OD-GUI-2 | — | Resolved within M1 | — |
| OD-GUI-3 | Provider-architecture precedent gap | Open | Partial — WP-GUI-07/09 proceeded with documented reduced scope |
| OD-GUI-4 | Companion to OD-GUI-3 | Open | Partial — WP-GUI-07/09 proceeded with documented reduced scope |
| OD-GUI-5 | `provider enable` requires interactive confirmation; `ProcessRunner` has no non-interactive channel to supply it (`src/cli.py` `_confirm()` at line 614 calls Python's `input()`; `provider_parser`'s `enable` subparser has no `-y`/`--yes` bypass, unlike `execute`) | Open | WP-GUI-12 only, out of M1 |
| OD-GUI-6 | No mechanism for `ProcessRunner` to deliver a Keychain-retrieved credential to the engine subprocess environment (`ProcessRunner.run` never sets `Process.environment`; `src/providers/claude.py` line 95 reads only `ANTHROPIC_API_KEY` from the ambient environment) | Open | WP-GUI-12 only, out of M1 |

All six are recorded in `Downloads Intelligence — UX Design/Open Dependencies.md` in the project's standard format. OD-GUI-5/6 do not block M1 sign-off; they exist purely as forward context for the next engine-side milestone (§8).

---

## 3. Known Limitations

**Gap:** no GUI-track `KNOWN_LIMITATIONS.md` exists. The main engine vault maintains this file per module (8 instances under `Release/ModuleXX/`); the GUI track (`App/`) has no equivalent at any level. The limitations that do exist today — the WP-GUI-07/08 test-plan gap (§4), the WP-GUI-07/09 reduced-scope items stemming from OD-GUI-3/4, and the tag-hygiene items in §5 — are currently recorded only in chat history and in this audit, not in a durable, versioned file.

This is the one item on the audit checklist not currently satisfied anywhere in the repository, and should be closed (by writing `App/KNOWN_LIMITATIONS.md`) or explicitly accepted as deferred before M1 sign-off.

---

## 4. Acceptance Criteria Not Fully Satisfied

One substantive gap, confirmed by direct test-source inspection:

WP-GUI-07's and WP-GUI-08's own Test Plans name a required scenario — *a simulated mid-execute process kill, followed by relaunch, produces an honest, verified account of what actually completed.* Verified:

- `ExecuteResultProjectionTests.swift` and `UndoResultProjectionTests.swift` both test the *missing action-log entry* case at the projection layer (e.g. `test_compute_fileWithNoActionLogEntryAtAll_treatedAsNotFiled_neverAssumedComplete`), proving the core safety property — never assume completion without re-reading the actual log — at unit level.
- No test file in the suite spawns and kills a live `Process`. A targeted search for kill/interrupt/terminate handling across `ExecuteViewModelTests.swift`, `UndoViewModelTests.swift`, and `ProcessRunner.swift` itself found no live-subprocess-kill integration test.

The safety guarantee holds at the level the architecture cares about most, but the literal scenario named in the Test Plan is not exercised as a real integration test. Everything else reviewed (WP-GUI-00 through WP-GUI-11) has no unmet acceptance criteria identified.

---

## 5. Remaining Architectural Risks

- **No cancellation path once an engine subprocess is running.** `ProcessRunner.run()` (`Sources/EngineBridge/ProcessRunner.swift`) awaits process exit via `withCheckedThrowingContinuation` resumed only by `Process.terminationHandler` — there is no `Task.checkCancellation()` inside that continuation and no API to request early termination of the child process. Verified in `ScanViewModel.swift`: its `pollTask` (the progress-polling loop) is cancellable, but the underlying `await bridge.run(.run)` call is not — cancelling the poll loop stops the GUI from checking progress, it does not stop the engine. If a `scan` or `run` invocation hangs (network stall inside a provider call, infinite loop, etc.), the GUI has no way to recover short of the user force-quitting the app.
- **No invocation timeout.** Consistent with the above: `Configuration` and `run()` expose no timeout parameter. A hung engine process blocks that command indefinitely.
- **Interactive-command / credential-injection gap (OD-GUI-5, OD-GUI-6).** Already tracked as Open Dependencies, but structurally these are the same root cause: `ProcessRunner` was designed only for non-interactive, environment-inheriting invocations, and neither interactive prompts nor per-invocation environment injection were part of its original contract. Any future GUI work package needing either capability will hit the same wall WP-GUI-12 did.
- **`python3` resolution is environment-dependent.** `Configuration.pythonInvocation` defaults to `["python3"]`, resolved via `/usr/bin/env` — correct for portability, but means GUI behavior is silently dependent on whichever `python3` is first on the invoking user's `PATH` (system, Homebrew, pyenv shim, or a venv). No version/dependency check occurs at the `ProcessRunner` layer before invocation; `EngineBridge`'s separate version-compatibility check (WP-GUI-00) is the only guard against drift, and it fires after a process has already been spawned.
- **Tag/commit traceability is inconsistent for the earliest work packages** (WP-GUI-00A/01/01A/02/03), with WP-GUI-02 in particular having no commit whose message identifies it (its only tag, `wp-gui-02-complete`, points to a commit named "WP-GUI-00A: Final verification..."). Low technical risk (the `Onboarding/` source and its tests are present and passing) but a real audit/bisect risk if a defect ever needs to be traced back to exactly when WP-GUI-02 landed.

None of these are defects in current behavior — swift test passes 416/416 and the engine-as-source-of-truth verification pattern is intact everywhere it was checked. They are gaps in resilience (hang/cancel handling) and traceability, not correctness.

---

## 6. TODO / FIXME / HACK in Production Code

`grep -rn "TODO\|FIXME\|XXX:\|HACK" Sources/` — **zero matches.** Clean across both `EngineBridge` and `DownloadsIntelligenceApp` targets.

---

## 7. Opportunities for Simplification

- **`ProcessRunner.launchAndAwaitExit` duplicates its cleanup loop.** The `for handle in handlesToClose { handle.closeFile() }` loop appears twice — once on the success path after `process.run()` succeeds, once identically in the `catch` block (`ProcessRunner.swift` lines 182–184 and 187–189). A small `defer`-based or shared-helper refactor could collapse this to one copy. Low risk, cosmetic.
- **Five parallel "Projection" pure-model types** (`ExecuteResultProjection`, `UndoResultProjection`, `HistoryProjection`, `ReportsProjection`, `ReviewQueueProjection`) all follow the same shape: reconcile a requested/expected state against a freshly re-read engine artifact and derive a display-safe result that never assumes success. This is the intended, deliberate repetition of one architectural pattern (engine-as-source-of-truth) rather than accidental duplication, and each has its own domain-specific reconciliation rules — but it may be worth a follow-up review to check whether a shared "never assume completion" primitive could reduce boilerplate across the five, now that the pattern has been implemented five times and its shape is fully known. This was not diffed line-by-line in this audit and should be treated as a hypothesis to investigate, not a confirmed duplication.
- **Tag convention cleanup.** Standardizing on the `wp-gui-NN-final` convention that's been consistent from WP-GUI-04 onward — e.g., by adding equivalent forward-pointing tags for WP-GUI-00A/01/01A/02/03 rather than rewriting history — would remove the need for footnotes like the ones in §1/§5 in every future audit.

---

## 8. Recommendation for the Next Engineering Milestone

Not a new feature: **an engine-side milestone to close OD-GUI-5 and OD-GUI-6**, which is the prerequisite for resuming WP-GUI-12 (AI Provider Settings). Concretely, per the evidence already gathered during WP-GUI-12 dependency verification:

1. Add a non-interactive bypass to `provider enable` (e.g. `-y`/`--yes`, mirroring the existing precedent on `execute_parser`) so `_confirm()` in `src/cli.py` can be skipped programmatically.
2. Add an optional `additionalEnvironment: [String: String]` parameter to `ProcessRunner.run(_:allowInteractive:)` (and a pass-through on `EngineBridge.run`) so a Keychain-retrieved credential can be delivered to the subprocess without ever being written to disk.

Both changes are scoped as engine/EngineBridge work, not GUI work, and both are already fully specified with file:line evidence in `Open Dependencies.md` (OD-GUI-5, OD-GUI-6). Until they land, WP-GUI-12 should remain blocked rather than worked around.

As a secondary, lower-priority track alongside that engine milestone: close the §3 Known Limitations gap and the §5 cancellation/timeout risk, since both are cross-cutting concerns that any future work package (including WP-GUI-12 once unblocked) would otherwise inherit.
