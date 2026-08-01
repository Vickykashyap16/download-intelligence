# WP-GUI-12 — Dependency Re-Verification and Implementation Plan

**Status:** Verification complete, no blockers found. Implementation plan below. No code written. Awaiting approval.
**Date:** 2026-08-01.

---

## 1. Re-Verification of OD-GUI-5 and OD-GUI-6

Verified against the current repository state — commit `8fbb275` ("INFRA-01: Provider CLI modernization"), tagged `infra-01-final`, working tree clean, Python regression suite green (15/15 provider tests, full suite unaffected).

**OD-GUI-5 — `provider enable` interactive-only.** RESOLVED.
- `src/cli.py`'s `enable` subparser now defines `-y`/`--yes` (`store_true`), confirmed present at the tagged commit.
- `_cmd_provider()` passes `getattr(args, "yes", False)` into `_provider_enable(yes=...)`.
- `_provider_enable(yes: bool = False)`: when `yes=True`, `_PROVIDER_DISCLOSURE_TEXT` still prints, and only the `_confirm()` call is skipped. Confirmed via direct read of the tagged commit's `src/cli.py`, lines 613–625.
- Default path (`yes` omitted) is byte-identical to pre-INFRA-01 behavior — verified by the retained passing test `test_provider_enable_without_yes_flag_still_prompts`.

**OD-GUI-6 — no credential-delivery mechanism.** RESOLVED.
- `ProcessRunner.run(_:allowInteractive:additionalEnvironment:)` merges `additionalEnvironment` over `ProcessInfo.processInfo.environment` (precedence to the injected value), applied only when non-empty. Confirmed present at the tagged commit.
- `EngineMutationGuard.run(_:via:allowInteractive:additionalEnvironment:)` and `EngineBridge.run(_:allowInteractive:additionalEnvironment:)` both forward it unchanged. Confirmed present at the tagged commit, full three-layer chain intact.
- Structural leak-safety still holds: `CommandResult` carries only `command`/`exitCode`/`standardOutput`/`standardError`; `GUILogger.log(result:)` receives only a `CommandResult`. No code path exists for `additionalEnvironment` to reach a log. Unchanged since the design proposal.
- No Python-side change was needed or made — `src/providers/claude.py` line 95 already reads `ANTHROPIC_API_KEY` from `os.environ` unconditionally, confirmed unchanged.

**Conclusion: both OD-GUI-5 and OD-GUI-6 are fully resolved in the current codebase. No blocker requiring a further engine or infrastructure change exists.** Proceeding to the implementation plan below.

*(One transient artifact during this re-verification: an early check of the `infra-01-final` tag briefly showed it pointing at the pre-INFRA-01 commit with the actual changes still uncommitted — almost certainly a sync-timing snapshot caught mid-commit on your end, since a follow-up check moments later showed the tag correctly pointing at the real `8fbb275` commit with everything present and clean. Re-verified twice more since; the current state is stable and consistent. Noted only for completeness, not as a finding.)*

---

## 2. New Findings From This Verification (not blockers — implementation-planning items)

Three things surfaced that weren't visible before INFRA-01 landed, none of which require another engine change or stop this plan:

1. **`EngineCommand.swift` still has no way to express `provider enable -y`.** `.provider(.enable)`'s `argv` is fixed at `["provider", "enable"]` and `requiresInteractiveInput` unconditionally returns `true` for it. Without extending this case, WP-GUI-12 cannot actually reach the new CLI flag — invoking `.provider(.enable)` today would still hit the EOF crash, flag or no flag. This is a small, additive change to a frozen WP-GUI-00 file (same shape as the already-shipped `.execute(yes: Bool, debug: Bool)` case), included as Step 0 below rather than raised as a new Open Dependency, since it's resolvable entirely within WP-GUI-12's own scope with no cross-module gap.
2. **No live network check exists anywhere in `provider enable`.** `_provider_enable()` never contacts the Claude API — it only checks that `ANTHROPIC_API_KEY` is set locally. The Hi-Fi UI Spec §13 (Offline state) and the Test Plan's "offline-enable-attempt test" both assume enabling can genuinely fail due to network unavailability. Today, nothing in the engine would ever produce that failure. This needs a design decision — see §4 below — before Step 5.
3. **`EngineConfiguration` already exposes everything needed to read current status.** `classification_provider`, `extraction_provider`, and `ai_provider_consent` are already parsed fields (`EngineConfiguration.swift` lines 113–115), reachable via the existing `EngineBridge.readConfiguration()` — the same call `SettingsViewModel` already uses for folder settings. No new artifact reader is needed for the off/on status itself. Confirmed no existing Keychain/Security-framework code exists anywhere in the app (`grep` for `Keychain`/`SecItem`/`import Security` returns nothing) — the credential store is being built from scratch, as expected.

---

## 3. Implementation Plan

Following this project's established WP-GUI test-first pattern (pure model → model tests → ViewModel → ViewModel tests → SwiftUI views → wiring → final regression + milestone report), and its existing no-`NavigationLink` idiom (every other multi-screen flow in this app — Review Queue/Detail, Scan/Preview — uses local view-model state to switch between conditional views, not push navigation; AI Provider Settings follows the same pattern rather than introducing a new one).

**Step 0 — `EngineCommand` extension (frozen-file, additive only).**
Change `.provider(.enable)` to `.provider(.enable(yes: Bool))` (or add a sibling case), mirroring `.execute(yes: Bool, debug: Bool)`'s exact existing shape. Update `argv` to append `-y` when `yes == true`, and `requiresInteractiveInput` to return `!yes` for this case (identical pattern to `.execute`). This is the only step touching a file outside `DownloadsIntelligenceApp`; keep the diff to exactly this, no other changes to `EngineCommand.swift`.

**Step 1 — Pure model: `AIProviderSettingsProjection`.**
Derives the screen's entire display state from `EngineConfiguration` (current on/off status) plus a local `hasShownDisclosure: Bool` flag: status text/badge, whether "Enable" is reachable (never `true` until disclosure has rendered — Hi-Fi §13's hard structural rule), and success/error/offline presentation. Test-first, per project convention.

**Step 2 — `AIProviderSettingsProjectionTests`.**
Cover: Enable never reachable pre-disclosure; correct status derivation for on/off/unknown-config-error states; offline/error presentation shaping.

**Step 3 — `KeychainCredentialStore` (new, in `DownloadsIntelligenceApp`, not `EngineBridge`).**
A narrow wrapper around `Security`'s generic-password APIs (`SecItemAdd`/`SecItemCopyMatching`/`SecItemDelete`/`SecItemUpdate`) for exactly one credential (service + account identifying the Anthropic API key). No third-party dependency needed — `Security` is a system framework. Placed in the app target rather than `EngineBridge` since it's local OS credential storage, not engine-subprocess concern — the two are deliberately kept separate, matching this project's existing "GUI log vs. action log" separation discipline.

**Step 4 — `KeychainCredentialStoreTests`.**
Uses a distinct test-only service identifier (never the real one) with teardown deletion after every test, so tests never leave real state behind and never collide with anything a real run might store.

**Step 5 — `AIProviderSettingsViewModel`.**
Orchestrates: load current status via `EngineBridge.readConfiguration()`; track disclosure-shown state; on Enable — read the entered credential, store it via `KeychainCredentialStore`, then call `bridge.run(.provider(.enable(yes: true)), additionalEnvironment: ["ANTHROPIC_API_KEY": credential])`; on Disable — call `bridge.run(.provider(.disable))` (already fully functional, no changes needed there); map results into the projection's success/error/offline states. **Depends on the design decision in §4 below for exactly what "offline" detection means here.**

**Step 6 — `AIProviderSettingsViewModelTests`.**
Fixture-driven (new `ProviderSettingsEngineProject` fixture, matching the `HistoryEngineProject`/`UndoingEngineProject` precedent) plus a fake `KeychainCredentialStore` test double, so tests never touch the real OS Keychain.

**Step 7 — SwiftUI views: `AIProviderSettingsView`.**
Off state (explanation → disclosure → Enable) and on state (confirmation → Disable), per Hi-Fi §13's exact content/layout/state spec — single column, disclosure text never smaller or less prominent than body content, no excitement-oriented iconography, quiet (non-celebratory) success confirmation.

**Step 8 — Wire into Settings.**
Add a third row/section to `SettingsView` (the "future work package can add a third selector entry additively" comment already anticipates this) that switches `SettingsSectionView`'s local state to show `AIProviderSettingsView` instead of the folder/about content — same conditional-state pattern used elsewhere, no new navigation primitive introduced.

**Step 9 — Accessibility pass.**
Per Hi-Fi §13.8: full disclosure text read before Enable is announced reachable (never truncated for speech); focus moves to the updated status statement after toggling; status badge always paired with its text label.

**Step 10 — Security review of credential storage** (explicitly named in the work package's own Risks and Test Plan, not deferred).
A dedicated check — not just unit tests — confirming the credential never appears in `sources.yaml`, `UserDefaults`, the GUI log, or anywhere else on disk in plaintext; confirming `KeychainCredentialStore` is the only write path; confirming `additionalEnvironment`'s existing leak-safety (§1 above) still holds once this is the first real caller supplying it.

**Step 11 — Full regression + milestone report.**
`swift build` / `swift test`, verify all Acceptance Criteria, deliver milestone report per the established format.

---

## 4. One Design Decision Needing Your Confirmation Before Step 5

The Hi-Fi spec and Test Plan both name an "offline-enable-attempt" scenario the engine cannot produce today (§2, finding 2). Two ways to actually satisfy it:

- **Option A (recommended):** the GUI itself makes one direct, minimal validation call to Anthropic's API (not through the engine subprocess) immediately before writing the credential and calling `provider enable -y` — confirming the key is both reachable and valid, and showing the Offline/Error state honestly if it isn't. This is a new network call, but it's still within "the one feature this application would ever make a network call for" (Architecture §16) — it's part of enabling AI-assisted classification, just performed by the GUI rather than by `_provider_enable()`. No engine change needed.
- **Option B:** treat the AC/Test Plan item as satisfied by the *next* real engine network call (the first `classify`/`extract` invocation after enabling) rather than at enable-time itself, and adjust the on-screen wording so "Enable" no longer implies an immediate connectivity check. This changes the literal Hi-Fi spec text and is a smaller, more conservative build, but doesn't match "an offline-enable-attempt test" as written.

I'd recommend Option A and have written Step 5 assuming it, but wanted this named explicitly rather than decided silently, since it's the one place this plan makes a call the spec itself left ambiguous.

---

## 5. Recommendation

No blockers. Ready to proceed on your approval, starting at Step 0.
