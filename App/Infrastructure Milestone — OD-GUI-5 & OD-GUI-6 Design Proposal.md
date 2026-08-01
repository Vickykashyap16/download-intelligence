# Infrastructure Milestone — Design Proposal: Resolving OD-GUI-5 & OD-GUI-6

**Status:** Design proposal only. No code written. Awaiting approval before implementation.
**Scope:** The smallest infrastructure change that closes OD-GUI-5 and OD-GUI-6, evaluated against four explicit constraints: backwards compatibility, no change to existing GUI behavior, Frozen Module Change Policy compliance, minimal public API surface.
**Non-goal:** This proposal does not implement WP-GUI-12 (AI Provider Settings) or any other GUI-visible feature. It makes a capability available for a future work package to consume; it does not consume it.

---

## 1. Policy framing

`Governance/FROZEN_MODULE_CHANGE_POLICY.md` §1 scopes itself to "a defect, gap, or inconsistency" discovered post-freeze — both OD-GUI-5 and OD-GUI-6 are explicitly framed as **gaps**, not defects: nothing in the current, frozen behavior is wrong. `provider enable` correctly prompts interactively today; `ProcessRunner` correctly inherits the ambient environment today. Both do exactly what they were designed and released to do. The gap is that neither exposes a capability a not-yet-built consumer (WP-GUI-12) will need.

Per §2, this places both findings at **Low severity**: "a real but minor gap... may be fixed via the lightweight patch path (§5) at the project owner's discretion." The user's decision to open an Infrastructure milestone now is exactly that discretion being exercised. Both proposed changes below are designed to land as a **MINOR version bump** under §5.1 — "adds new optional behavior without breaking the existing contract" — not a PATCH (nothing is being fixed) and not a MAJOR (no existing INPUT/OUTPUT/guarantee changes).

The same policy is written for modules 01–08 (the Python engine) by name, but OD-GUI-6 itself already extends this framing to `ProcessRunner.swift` as a frozen GUI-track module ("Recommended as a Frozen Module Change Policy review against `ProcessRunner.swift` specifically"). This proposal follows that established precedent rather than inventing a new process for the GUI track.

---

## 2. OD-GUI-5 — `provider enable -y`

### Smallest change

Three edits to `src/cli.py`, mirroring `execute`'s already-shipped `-y`/`--yes` precedent exactly:

1. **`provider_parser`'s `enable` subparser** (currently `src/cli.py` lines 278–280, which today defines zero arguments) gains one new `store_true` argument, `-y`/`--yes`, with help text explaining it skips the confirmation prompt because the caller has already collected consent through its own equivalent disclosure UI — matching `execute_parser`'s existing `-y` help text pattern (lines 172–179) word-for-word in spirit.
2. **`_cmd_provider(args)`** (line 581) passes `getattr(args, "yes", False)` through to `_provider_enable(yes=...)` instead of calling it with no arguments.
3. **`_provider_enable()`** (line 593) gains one new parameter, `yes: bool = False`. When `True`, the function still performs every existing check unchanged — the registered-provider check (line 596), the `ANTHROPIC_API_KEY` presence check (line 604), and printing `_PROVIDER_DISCLOSURE_TEXT` (line 613) — and only the `_confirm("Enable the Claude API provider?")` call (line 614) is skipped in favor of proceeding directly to the three `_write_config_value` calls (lines 618–620).

Disclosure is preserved even in the non-interactive path; only the interactive *confirmation step* is bypassed. This matches the exact scenario the Hi-Fi UI Specification §13 already assumes (a GUI screen that shows its own disclosure and collects its own confirmation before invoking the CLI) and does not weaken the engine's disclosure guarantee.

### Backward compatibility

The new parameter's default (`False`) reproduces today's exact code path with no observable difference: same prompt, same wording, same `input()` call, same behavior when stdin is closed (including the `EOFError` crash TD-41 already documents for a sibling command — this proposal does not touch that failure mode for the default path, only adds a way to avoid triggering it at all when `-y` is supplied). Every existing script, test, or terminal user invoking `provider enable` without `-y` sees byte-identical behavior.

### Public API surface change

One new optional CLI flag, additive to `provider enable`'s argv contract only. `_provider_enable()`'s signature gains one optional parameter with a default — not a breaking change to any caller, since its only current caller is `_cmd_provider()` itself (verified: no other call site exists in `src/`).

---

## 3. OD-GUI-6 — environment injection through `ProcessRunner`

### Smallest change

Confirmed during this review: **no Python-side change is required.** `src/providers/claude.py` line 95 already reads `ANTHROPIC_API_KEY` from `os.environ` unconditionally — the engine's contract already supports environment-delivered credentials; the gap is entirely that nothing on the Swift side can set that environment for one specific subprocess invocation. This narrows the change to three Swift files, each gaining one new optional parameter that threads through the existing call chain unchanged:

1. **`ProcessRunner.run(_:allowInteractive:)`** (`ProcessRunner.swift` line 92) gains a new parameter, `additionalEnvironment: [String: String] = [:]`. Inside the function body, immediately after constructing `process` (line 103) and before `process.run()` is reached, the process's environment is set to the current ambient environment (`ProcessInfo.processInfo.environment`) merged with `additionalEnvironment` taking precedence on key collision — preserving today's "inherit everything" behavior when the new parameter is omitted, since merging an empty dictionary over the ambient environment is a no-op.
2. **`EngineMutationGuard.run(_:via:allowInteractive:)`** (`EngineMutationGuard.swift` line 83) gains the same parameter and forwards it unchanged to `runner.run(command, allowInteractive:additionalEnvironment:)` at both call sites (lines 89 and 98).
3. **`EngineBridge.run(_:allowInteractive:)`** (`EngineBridge.swift` line 218) gains the same parameter and forwards it unchanged to `mutationGuard.run(...)`.

### The credential-in-logs constraint (OD-GUI-6's own flagged "unverified" item, now resolved by construction)

OD-GUI-6 explicitly flagged as unverified "whether the value should ever reach `GUILogger`." This review confirms it structurally cannot, without any new safeguard needing to be built:

- `CommandResult` (`CommandResult.swift`) carries exactly four pieces of data — `command` (an `EngineCommand`, i.e. argv only), `exitCode`, `standardOutput`, `standardError`. It has no field for process environment and none is proposed.
- `GUILogger.log(result:)` (`GUILogger.swift` line 25) receives only a `CommandResult`. It has no access to the `Process` object or its environment at all.
- `EngineCommand.description` (used in the one place a command is ever rendered to a log line) is derived from `argv` only (`EngineCommand.swift` lines 186–188) — `additionalEnvironment` is a sibling parameter to `command`, never merged into it.

So long as this proposal's implementation does not add `additionalEnvironment` to `CommandResult`, to any logging call, or to `EngineCommand` itself — and nothing in the three call sites above requires that — the credential is excluded from every logging path by the existing type boundaries, not by a new rule someone has to remember to follow.

### Backward compatibility

Default `[:]` at all three layers reproduces today's exact `Process.environment == nil` → full ambient-inheritance behavior (merging an empty dictionary changes nothing). All current call sites in `DownloadsIntelligenceApp` (Scan, Preview, Review, Execute, Undo, History, Reports, Settings — every existing `bridge.run(command)` call) are source-compatible with zero changes, since Swift default parameters do not require call sites to be touched.

### Public API surface change

One new optional parameter on three existing public methods, each defaulted to preserve exact current behavior. No new public type is introduced.

---

## 4. Why bundle both into one request

OD-GUI-6's own text recommends bundling ("a real Frozen Module Change Policy request would reasonably bundle them, since the same `provider enable -y` invocation is also the first real call site that would need the environment-injection capability"). Both changes are additive, both default to today's exact behavior, and both are prerequisites for the same eventual consumer (WP-GUI-12's Enable flow needs `-y` to avoid the EOF crash *and* `additionalEnvironment` to deliver the Keychain-retrieved key in the same invocation). Reviewing and versioning them together avoids two separate patch cycles touching adjacent code within the same milestone.

---

## 5. What this proposal does not do

- Does not modify `EngineCommand.swift` — `.provider(.enable)`'s `argv` and `requiresInteractiveInput` are untouched. A future GUI work package would need a corresponding `EngineCommand` change (e.g. `.provider(.enable(yes: Bool))`) to actually call the new flag; that is GUI-layer work, explicitly out of scope here.
- Does not implement Keychain storage, retrieval, or any UI. "Where the credential comes from" is entirely WP-GUI-12's concern; this proposal only makes it possible to deliver a credential once one exists.
- Does not change any of the 11 existing `EngineCommand` cases' observed behavior.
- Does not touch `GUILogger`, `FileGUILogger`, or `CommandResult`.

---

## 6. Governance paperwork this would require at implementation time

Per `FROZEN_MODULE_CHANGE_POLICY.md` §3 and §5, landing this (once approved) would require, alongside the code:

- A dated addendum to the C1 CLI's existing release record (`RELEASE_NOTES.md`, and `KNOWN_LIMITATIONS.md` if the `provider enable` non-interactive gap is currently listed there) — not a silent edit.
- A dated addendum to the WP-GUI-00 EngineBridge module's own release record for the `ProcessRunner`/`EngineMutationGuard`/`EngineBridge` signature additions.
- New dated entries in `CHANGELOG.md` for both changes.
- `Release/VERSIONS.md` updated with MINOR version bumps for both the CLI module and the EngineBridge module, with History entries explaining why.
- A targeted re-audit (not a full re-release cycle) confirming: the default-parameter paths are behaviorally identical to today, the new paths behave as designed, and every downstream consumer's existing test suite still passes at its pre-existing count (416/416 for the GUI test suite; the CLI's own regression suite for the Python side).
- A Pipeline Contract Verification gate re-run (`ENGINEERING_STANDARD.md` §7A) for the CLI module, since this is exactly the kind of frozen-module change that gate exists to catch drift from.
- `OD-GUI-5` and `OD-GUI-6` moved from **OPEN** to **Resolved** in `Open Dependencies.md`, with the resolving commit/tag cited, following the same format as the existing `OD-GUI-1` resolution entry.

None of this is performed as part of this proposal — it is listed so the size of the follow-on paperwork is visible before implementation is approved.

---

## 7. Recommendation

Both changes are small, additive, default-preserving, and independently verifiable against the constraints given: backwards compatible (verified via default-parameter analysis at every call site), no GUI behavior change (no GUI-layer file is touched), Frozen Module Change Policy-compliant (Low severity, owner-elected, MINOR bump path), and minimal public API surface (one optional parameter added to each of four existing methods across two languages; zero new public types).

Awaiting approval to proceed to implementation under this design.
