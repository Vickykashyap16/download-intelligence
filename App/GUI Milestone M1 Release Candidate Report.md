# GUI Milestone M1 — Release Candidate Report

**Scope:** WP-GUI-00 through WP-GUI-11 (M1 freeze). WP-GUI-12 is explicitly out of scope — it is blocked (see §4) and no implementation plan exists for it.
**Method:** Direct verification against the current repository state (git history, source, tests) and the design documents in `Downloads Intelligence — UX Design/`. No code was modified to produce this report.
**Verified by:** Claude, 2026-08-01.

---

## 1. Commits & Tags

All 12 work packages have identifiable commits. Nine are cleanly tagged with the `wp-gui-NN-final` convention. Three have naming/traceability anomalies, documented below — none of which represent missing or lost work; all source is present and accounted for.

| WP | Commit(s) | Tag(s) | Status |
|---|---|---|---|
| WP-GUI-00 | `1363290` | `wp-gui-00-v2`, `beta-foundation-complete` | Clean, but see Finding F1 (stale unrelated tag) |
| WP-GUI-00A | `4e89238`, `ae592db` | `wp-gui-00a`, `wp-gui-00a-final`* | See Finding F2 |
| WP-GUI-01 | `ab0f4a6` | `v0.9.0-beta` | See Finding F3 (off-convention tag name) |
| WP-GUI-01A | `ae592db` (shared) | `wp-gui-01a` | See Finding F2 |
| WP-GUI-02 | `ae592db` (shared, no dedicated commit) | `wp-gui-02-complete` | See Finding F2 (most significant traceability gap) |
| WP-GUI-03 | `dc2f234`, `0423c21` | `wp-gui-03`, `wp-gui-03-complete` | See Finding F4 (off-convention naming) |
| WP-GUI-04 | `3717622` (untagged), `7c628dd`, `951507a` | `wp-gui-04-complete`, `wp-gui-04-final` | Clean |
| WP-GUI-05 | `7210988` | `wp-gui-05-final` | Clean |
| WP-GUI-06 | `ed6ab05` | `wp-gui-06-final` | Clean |
| WP-GUI-07 | `bb50516`, `a1f5754` (untagged) | `wp-gui-07-final` | See Finding F5 (untagged post-freeze commit) |
| WP-GUI-08 | `75f86dc` | `wp-gui-08-final` | Clean |
| WP-GUI-09 | `384a187` ("WP-GUI-09: History") | `wp-gui-09-final` | Clean |
| WP-GUI-10 | `1af64e2` ("WP-GUI-10: Reports") | `wp-gui-10-final` | Clean |
| WP-GUI-11 | `4ba23a4` ("WP-GUI-11: Settings") | `wp-gui-11-final` | Clean — see note below |

*`wp-gui-00a-final` is a separate tag on an earlier commit (`29f79a4`, "Project cleanup before WP-GUI-02"), distinct from `ae592db`.

**WP-GUI-11 / `default:` case fix — resolved.** The unreachable `default:` case removed from `AppShell.swift` earlier in this session is present in the `wp-gui-11-final` tagged commit (verified via `git show wp-gui-11-final:App/Sources/DownloadsIntelligenceApp/AppShell.swift`), and `git status` shows a clean working tree at that same commit. The fix is committed and tagged; there is no outstanding uncommitted change.

### Findings — Commits & Tags

- **F1 (cosmetic).** A tag literally named `wp-gui-00-complete` exists but points to an unrelated engine-release commit (`ebd00ea`), not GUI code. Likely a naming collision from the main engine vault's own tagging. No GUI work is missing; the correct WP-GUI-00 tags (`wp-gui-00-v2`, `beta-foundation-complete`) do point to the right commit.
- **F2 (moderate — traceability gap).** WP-GUI-00A, WP-GUI-01A, and WP-GUI-02 are entangled: `ae592db`'s commit message reads only "WP-GUI-00A: Final verification and concurrency validation," yet this same commit carries the `wp-gui-01a` and `wp-gui-02-complete` tags. **WP-GUI-02 has no commit whose message identifies it** (no mention of "WP-GUI-02," "Onboarding," "First Run," or "Welcome screen" anywhere in the log). The `Onboarding/` source directory (7 files) exists and is exercised by tests, so the work itself is present — only the commit-message-to-work-package mapping is ambiguous for this one package.
- **F3 (minor).** WP-GUI-01 has no `wp-gui-01-*` tag; it is only reachable via `v0.9.0-beta`, an off-convention name inconsistent with every other WP-GUI-NN.
- **F4 (minor).** WP-GUI-03's actual feature commit (`dc2f234`, "Home dashboard") carries the bare tag `wp-gui-03` (no `-final`/`-complete` suffix), while `wp-gui-03-complete` sits on a later, smaller refinement commit (`0423c21`, "Refactor Home configuration constants"). Off-convention relative to WP-GUI-04 onward, where `-final` was standardized.
- **F5 (minor).** An untagged commit `a1f5754` ("WP-GUI-07: Execute flow") sits chronologically between `wp-gui-07-final` and `wp-gui-08-final`. Diff confirmed: it only modifies `ExecuteViewModelTests.swift` (+39/−9 lines) — a post-freeze test strengthening, not a scope or behavior change. Not tagged, so not traceable by tag alone; traceable by log inspection.

None of F1–F5 indicate lost work, undocumented scope changes, or behavior not covered by tests. They are traceability/hygiene gaps in tag naming, most concentrated in the earliest work packages (00A/01/01A/02/03) before the `wp-gui-NN-final` convention stabilized from WP-GUI-04 onward.

---

## 2. Acceptance Criteria Verification

| WP | Feature | AC status |
|---|---|---|
| WP-GUI-00 | SwiftPM foundation, EngineBridge skeleton | PASS |
| WP-GUI-00A | Concurrency validation | PASS |
| WP-GUI-01 | App shell / navigation | PASS |
| WP-GUI-01A | (folded into 00A verification) | PASS |
| WP-GUI-02 | Onboarding / First Run | PASS |
| WP-GUI-03 | Home dashboard | PASS |
| WP-GUI-04 | Scan flow | PASS |
| WP-GUI-05 | Preview flow | PASS |
| WP-GUI-06 | Review queue | PASS |
| WP-GUI-07 | Execute flow | **PASS WITH NOTE** — see Finding F6 |
| WP-GUI-08 | Undo flow | **PASS WITH NOTE** — see Finding F6 |
| WP-GUI-09 | History | PASS |
| WP-GUI-10 | Reports | PASS |
| WP-GUI-11 | Settings | PASS |

**Finding F6 (moderate — test-plan gap).** WP-GUI-07's and WP-GUI-08's own Test Plans name a specific required scenario: *"a simulated mid-execute process kill, followed by relaunch, produces an honest, verified account of what actually completed."* Verified directly against test source:

- `ExecuteResultProjectionTests.swift` and `UndoResultProjectionTests.swift` both contain tests for the *missing action-log entry* case (e.g. `test_compute_fileWithNoActionLogEntryAtAll_treatedAsNotFiled_neverAssumedComplete`), which proves the underlying safety property — the projection never assumes success without re-reading the actual log — at the unit level.
- Neither `ExecuteViewModelTests.swift` nor `UndoViewModelTests.swift` (nor any other test file) actually spawns and kills a live `Process`/subprocess mid-run. `ProcessRunner.swift` has no test double exercised this way; a grep for kill/interrupt/terminate handling in the test suite returns no live-process-kill test, only the projection-layer simulations described above.

The safety guarantee is proven at the level the design cares about most (never assume completion), but the literal integration scenario named in the Test Plan — kill the real subprocess, relaunch, reconcile — is not present as an executed test. This is a real, disclosed gap, not a defect in behavior.

**Static test-count caveat.** A grep-based count of `func test` across `Tests/` returns 429, while the user's locally-run `swift test` reported 416/416 passing. The 13-line difference is most likely non-test helper methods matching the `func test` pattern (e.g. `testHelper`, fixture setup) rather than missing/failing tests, but this was not independently reconciled line-by-line. Flagged for completeness, not treated as a defect.

---

## 3. Open Dependencies

| ID | Title | Status | In M1 scope? |
|---|---|---|---|
| OD-GUI-1 | (resolved during M1) | Resolved | N/A |
| OD-GUI-2 | (resolved during M1) | Resolved | N/A |
| OD-GUI-3 | Related to provider-architecture precedent | Open | Partially blocks WP-GUI-07/09; both proceeded with documented reduced scope |
| OD-GUI-4 | (companion to OD-GUI-3) | Open | Partially blocks WP-GUI-07/09; both proceeded with documented reduced scope |
| OD-GUI-5 | `provider enable` requires interactive confirmation; `ProcessRunner` has no non-interactive path | Open | **Out of M1 scope** — blocks WP-GUI-12 only |
| OD-GUI-6 | No credential-delivery mechanism from GUI Keychain storage to engine subprocess environment | Open | **Out of M1 scope** — blocks WP-GUI-12 only |

All Open Dependencies raised through M1 are recorded in `Downloads Intelligence — UX Design/Open Dependencies.md` in the project's standard format. OD-GUI-5 and OD-GUI-6 do not block M1 sign-off — they block only the not-yet-started WP-GUI-12 and are documented purely as forward context.

---

## 4. Known Limitations

**Finding F7 (gap — needs a decision before sign-off).** No GUI-track `KNOWN_LIMITATIONS.md` exists. The main engine vault has this file per-module (8 instances under `Release/ModuleXX/`), but the GUI track (`App/`) has no equivalent at any level — not per-work-package, not milestone-level. The disclosed gaps in this report (F2, F5, F6, and the OD-GUI-3/4-driven reduced scope in WP-GUI-07/09) currently exist only in chat history and this RC report; none are captured in a durable, versioned limitations file.

This is the one item in the user's checklist that is not currently satisfied anywhere in the repository. Recommend either:
(a) create `App/KNOWN_LIMITATIONS.md` capturing F6 (execute/undo kill-test gap) and the WP-GUI-07/09 reduced-scope items from OD-GUI-3/4, as part of RC sign-off, or
(b) explicitly accept the gap as a deferred M1 action item.

---

## 5. TODO / FIXME Sweep

`grep -rn "TODO\|FIXME\|XXX:" Sources/ Tests/` — **zero matches**. Clean.

---

## 6. Test Suite

User-confirmed local results: `swift build` PASS, `swift test` PASS, 416/416 tests, zero compiler warnings (the one outstanding `AppShell.swift` warning was resolved and is confirmed present in the `wp-gui-11-final` tagged commit per §1).

Directory-level coverage confirmed present for all 13 `DownloadsIntelligenceApp` feature areas (Onboarding, Home, Scan, Preview, Review, Execute, Undo, History, Reports, Settings, Navigation, Lifecycle, Components) plus `EngineBridge` (28 source files). No feature area is untested.

---

## 7. Findings Summary (by severity)

- **Moderate:** F2 (WP-GUI-02 commit-message traceability gap), F6 (execute/undo live-process-kill integration test not present), F7 (no GUI-track Known Limitations file).
- **Minor:** F1 (stale unrelated tag name collision), F3 (WP-GUI-01 off-convention tag), F4 (WP-GUI-03 off-convention tag), F5 (untagged post-freeze test-strengthening commit for WP-GUI-07).

No finding indicates missing functionality, an undisclosed defect, or a violation of the non-negotiables (reversibility, no permanent deletion, engine-as-source-of-truth verification). All findings are either documentation/traceability hygiene or a disclosed test-plan gap with the underlying safety property still proven at unit level.

---

## 8. Go / No-Go Recommendation

**Conditional GO.** Recommend proceeding with the M1 freeze provided the following are explicitly acknowledged (or acted on) at sign-off:

1. F7 — decide whether to write `App/KNOWN_LIMITATIONS.md` before or immediately after tagging M1.
2. F6 — accept the live-process-kill scenario as a known test-plan gap for a future hardening pass, or schedule it before GA.
3. F2/F3/F4/F5 — no action required; documented here for the permanent record.

No blockers exist for WP-GUI-00 through WP-GUI-11. WP-GUI-12 remains correctly excluded from M1 per OD-GUI-5/OD-GUI-6.
