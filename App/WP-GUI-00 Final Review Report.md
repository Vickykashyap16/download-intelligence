# WP-GUI-00 — Engine Bridge Foundation: Final Review Report

**Date:** 2026-07-27 · **Scope:** `App/Sources/EngineBridge/` (25 source files) and `App/Tests/EngineBridgeTests/` (14 test files, 141 test methods) · **Status:** WP-GUI-00 complete, all five internal sub-tasks (#577–#581) delivered and approved in sequence.

This report is an independent-style review of the finished work package, written the way this project's prior Independent Implementation Audits were written for the Python engine's modules — evaluating what was actually built against what was specified, not re-describing the build log.

---

## 1. Architecture review

The implementation matches `GUI Architecture Specification.md` §3's central constraint exactly: nothing in `App/Sources/EngineBridge/` imports, links, or embeds any Python code. Every engine interaction is one of two kinds — a subprocess invocation (`ProcessRunner`, via `/usr/bin/env python3 -m src.cli <argv>`) or a direct read of an on-disk artifact the engine already produces (`ConfigurationReader`, `ActionLogReader`, `MetadataStoreReader`, `ReportsReader`, `EngineVersionReader`). This is the process-boundary model specified in §3 and §8, implemented literally rather than approximated.

The layering is exactly the one WP-GUI-00 asked for and nothing more: `EngineCommand` (typed command vocabulary) → `ProcessRunner` (mechanics) → `EngineMutationGuard` (sequencing policy) → `EngineBridge` (the one public facade). The four artifact readers and `EngineVersionReader` sit beside `ProcessRunner`, not underneath it — they are independent read paths into the filesystem, which is the correct shape given the real engine's own architecture (a CLI process and a set of on-disk artifacts it maintains, not a single API surface). `EngineBridge`'s constructor is the only place all nine collaborators are wired together; no other type in the package references more than the one or two collaborators it actually needs.

No new engine capability was assumed anywhere. The one real, disclosed gap found during implementation — `provider enable` having no non-interactive flag in the real CLI — was documented in `EngineCommand.requiresInteractiveInput`'s doc comment as a future, separately-authorized change for WP-GUI-12 to inherit, not worked around or silently accommodated.

## 2. Separation of responsibilities review

Each of the nine collaborators has exactly one reason to change:

| Component | Owns |
|---|---|
| `EngineCommand` | The CLI's argument vocabulary and which commands are interactive/mutating |
| `ProcessRunner` | Subprocess lifecycle: launch, stdin closure, concurrent stdout/stderr capture, exit-code classification |
| `EngineMutationGuard` | The single-mutation-slot sequencing rule only |
| `ConfigurationReader` / `ActionLogReader` / `MetadataStoreReader` / `ReportsReader` | Parsing exactly one real artifact format each |
| `EngineVersionReader` | Parsing `VERSIONS.md` |
| `VersionCompatibilityChecker` | Range comparison only — no file I/O, no knowledge of paths |
| `FileGUILogger` | GUI-local diagnostic logging and rotation, with zero knowledge of any engine artifact path |
| `EngineBridge` | Orchestration and the version-gate sequencing — no parsing, no subprocess code, no rotation logic of its own |

`EngineBridge.swift`'s own doc comment states the test this review applied literally: search the file for parsing, comparison, subprocess, or file-I/O logic, and none should be found. That held up — every method is version-gate-then-delegate. The one piece of logic every gated read method shares (check compatibility, then read, log on failure) is factored into a single private helper (`withVersionGate`) rather than repeated five times, satisfying the "no duplicated business logic" requirement literally, not just in spirit.

`ArtifactParseIssue` is the one deliberately shared type between two otherwise-independent readers (`ActionLogReader`, `MetadataStoreReader`) — justified because both readers solve the identical sub-problem (isolate one bad entry in a collection without losing the rest) and would otherwise have invented two incompatible ad hoc error-reporting shapes for the same concept.

## 3. Error handling review

`EngineBridgeError` is a single, closed, exhaustively-documented error type (10 cases) covering every failure mode actually reachable in this package: refused interactive invocation, mutation-slot contention, process launch failure, missing project root, unreadable/missing artifacts, and the two version-incompatibility directions. No component throws a raw `Error` or a bare `String` anywhere in the public surface.

Two deliberate, documented asymmetries are the correct behavior, not inconsistency:

- **Per-collection tolerance vs. whole-file failure.** `ActionLogReader` and `MetadataStoreReader` isolate one malformed line/record into `issues` and keep every healthy entry; `ConfigurationReader` fails the whole file on any decode error. This matches the real shape of each artifact — thousands of independent records vs. one small, holistically-meaningful settings file — and is documented as a deliberate choice in both readers' doc comments, not an oversight.
- **Missing-file semantics differ by artifact**, and correctly so: a missing action log or metadata store is a normal empty state (mirroring the real engine's own `read_action_log_entries()` behavior and a legitimate fresh-install condition); a missing config file or `VERSIONS.md` is a distinct, actionable "not configured" / "cannot verify compatibility" state and throws.

The GUI logger's failure handling is the one place errors are intentionally *not* propagated: `GUILogger.log` is non-throwing by protocol design, and `FileGUILogger` swallows every internal filesystem failure into `lastFailureReason` rather than surfacing it. This is correct given the explicit requirement that a diagnostic log must never become something a real feature depends on — verified by `FileGUILoggerTests`' two dedicated failure-handling tests, including recovery after the obstruction is removed.

One area that is intentionally underspecified for a reason: `EngineBridgeError.description` gives short, technically-accurate messages, not the polished, plain-language copy `Desktop Implementation Blueprint.md` §8/§12 describes for the actual Error State screen. That mapping is correctly out of scope here — it belongs to whichever future work package builds the Error State component — but is worth naming explicitly so it isn't mistaken for already having been done.

## 4. Thread safety review

Three concurrency-relevant types exist, and each uses the right tool for what it actually protects:

- **`ProcessRunner`** — an `actor`, but its real safety property is structural, not just actor isolation: stdout/stderr are read via `async let` concurrently with waiting for process exit (via `terminationHandler` + a continuation, never the blocking `waitUntilExit()`), which is what avoids the classic pipe-buffer deadlock. This was verified empirically, not just by inspection — `test_status_capturesLargeOutputWithoutDeadlocking` writes 100KB through the fixture process specifically to exercise this path.
- **`EngineMutationGuard`** — an `actor` whose entire correctness argument rests on one property: the check-and-set of `mutationInFlight` contains no `await` between the two operations, so no interleaving is possible. This is documented in the type itself and verified with real, overlapping subprocesses (not simulated timing) in `EngineMutationGuardTests`.
- **`FileGUILogger`** — an `actor` because rotation is a multi-step filesystem sequence (check size, shift backups, move current) that must not interleave across concurrent log calls.

The four artifact readers and `EngineVersionReader`/`VersionCompatibilityChecker`/`ConfigurationReader` are plain `Sendable` structs, deliberately not actors, because they hold no mutable state and perform one self-contained synchronous read per call — making them actors would have added isolation overhead with no corresponding safety benefit. `EngineBridge` itself is an actor, which is required because it holds and coordinates actor-isolated collaborators, but it introduces no additional mutable state of its own beyond its `let`-only collaborator references.

No data race is possible through any public API in this package. No mutable state exists in any type that isn't either actor-isolated or immutable.

## 5. Test coverage summary

141 test methods across 14 files. Breakdown by concern:

- **Unit tests for pure logic** (no process, no filesystem beyond fixture reads): `EngineCommandTests` (26), `CommandResultTests` (7), `SemanticVersionTests` (13), `VersionCompatibilityCheckerTests` (9).
- **Integration tests against a real subprocess** (a fixture Python CLI standing in for the engine, never the real `Download Intelligence` checkout): `ProcessRunnerTests` (18, including the deadlock-avoidance and interactive-stdin-EOF cases), `EngineMutationGuardTests` (8, including two tests that start a real ~0.3s subprocess and assert real-time exclusion).
- **Artifact reader tests against fixture data**: `ConfigurationReaderTests`, `ActionLogReaderTests`, `MetadataStoreReaderTests`, `ReportsReaderTests`, `EngineVersionReaderTests` (26 combined), each covering the happy path, missing-file behavior, and at least one malformed-input case.
- **GUI logger tests**: `FileGUILoggerTests` (9) — creation, append ordering, rotation under a deliberately tiny configured threshold, two failure-injection cases, and one integration case proving the action log is untouched.
- **Facade end-to-end tests**: `EngineBridgeTests` (16) — every scenario named in this task's testing requirements (read-only flow, mutating flow, concurrency-guard integration through the facade, version failure for both "too new" and "missing" cases, artifact read flow, missing-artifact handling via a dedicated "configured but never scanned" fixture, logger integration, failure propagation, and a final proof that none of the above ever touches the real action log).

Three fixture "engine" projects were built to support this without ever touching the real, live `Database/`/`Runtime/` data: `FakeEngineProject` (populated, realistic data, including deliberately malformed entries), `EmptyEngineProject` (nothing configured or run yet), `ConfiguredButFreshEngineProject` (configured and version-compatible, but never scanned), and `IncompatibleEngineProject` (a real, readable config and data, but a fixture engine version outside the tested range — specifically to prove the version gate blocks *before* any of that readable data is touched).

**Coverage gap, disclosed rather than hidden:** none of this has been executed. There is no Swift/Xcode toolchain in this sandbox (confirmed via `which swift xcodebuild` early in WP-GUI-00). Every "test passes" statement in this report and in the five prior milestone check-ins is a claim about what the test *asserts and should verify*, not a confirmed, observed result. Running `swift test` on your machine is the step that actually closes this gap, and until that happens, WP-GUI-00's own Definition of Done ("every item in the Acceptance Criteria has passed, with results recorded") is not fully satisfiable by me alone.

## 6. Technical debt introduced

- **No compiled/executed verification (see above).** The single largest source of risk in this entire work package. Mitigated by unusually defensive design (strict typing throughout, no force-unwraps, exhaustive switches, deliberate avoidance of Swift APIs with ambiguous `Substring` vs. `String` availability after one such issue was caught by inspection) — but defensive design is not a substitute for a green test run.
- **`EngineBridgeError.description` is diagnostic-quality, not user-facing-quality** (see §3). Acceptable for this stage; will need a real copy pass when the Error State screen work package consumes it.
- **`FileGUILogger`'s rotation policy numbers (5MB / 5 backups) are reasonable defaults, not a researched or product-approved retention policy.** `GUI Architecture Specification.md` §15 asks for "a reasonable retention window" without numbers; these are configurable, not hardcoded assumptions baked in without a way to change them, but they haven't been reviewed by anyone as *the* right numbers.
- **`VersionCompatibilityChecker`'s real min/max values are not set anywhere yet** — by design (see the type's own documentation), but this means no real build of this facade is actually usable end-to-end until some future work package (most naturally WP-GUI-01, at application-shell construction time) makes that release-configuration decision explicitly.
- **No diagnostic-bundle assembly** (`Desktop Implementation Blueprint.md` §13's "assemble a diagnostic bundle referencing the GUI log, the crash log, and the relevant portion of the action log") — correctly out of scope for WP-GUI-00, not attempted, but worth naming as a known gap rather than letting it go unrecorded.

None of the above are defects in the sense of "built wrong against the spec." They are scope edges, honestly disclosed, exactly where WP-GUI-00's own Scope line drew them.

## 7. Refactoring recommended before WP-GUI-01

None required. Specifically considered and rejected:

- Splitting `EngineBridge.swift` into smaller files — at ~230 lines with one method per concern, it is not large enough to justify fragmenting a single cohesive facade.
- Introducing a protocol for the artifact readers to unify their interface — rejected because their four `read()` signatures are already genuinely different shapes (a config object, a records-plus-issues result, an entries-plus-issues result, an optional report), and forcing a shared protocol would either lose that precision or require associated types that add complexity without a corresponding present need.
- Pre-building a diagnostic-bundle assembler or a richer `EngineBridgeError`-to-user-copy mapping now — both would be scope expansion into future work packages' territory, which this task's own requirements explicitly prohibit ("do not introduce duplicated business logic," and by extension, do not pre-build logic that belongs to a screen that doesn't exist yet).

The one real action item is not a refactor: **set real values for `minimumSupportedEngineVersion`/`maximumSupportedEngineVersion`** the first time this facade is actually constructed for a running application (naturally, WP-GUI-01's application-shell construction step) and **compile and run the test suite** before treating any of the above as confirmed rather than well-reasoned.

## 8. Production readiness assessment

As a foundation layer for GUI work to build on: **ready, pending compilation.** The architecture matches every governing document with no deviation requiring a decision from you, no engine modification of any kind, and no scope expansion beyond WP-GUI-00's own stated boundaries. The design is defensive by construction — forward-compatible enum fallback cases, per-entry error isolation where the real data shape calls for it, and a non-throwing logger that cannot itself become a point of failure — which is the right posture for a layer every future screen will depend on.

As a *verified* deliverable: not yet — see §5 and §6. This is a gate on confirmation, not a gate on design quality.

## 9. Go / No-Go recommendation for starting WP-GUI-01

**Conditional Go.** Recommend proceeding to WP-GUI-01 (Application Shell & Shared Component Library) only after:

1. You run `swift build` and `swift test` in `App/` and confirm all 141 tests pass.
2. Any failures found are reported back for correction before WP-GUI-01 begins building on top of this foundation — per the standing instruction that WP-GUI-00 must be "completely finished, tested, and approved" first.

If both build and test suite are clean, there is no architectural or design reason to delay WP-GUI-01. If failures surface, they are far cheaper to fix now, against a foundation layer with no dependents yet, than after WP-GUI-01's shell and shared components have started consuming this facade's API.
