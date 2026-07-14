# Module 08 (Logging & Reporting) — Implementation Plan

**Status: PLANNING ONLY. No implementation code has been written.** This document decomposes the frozen `Module 08 Design.md` (frozen 2026-07-14, see `Module 08 Design Review.md`'s "Freeze Record (2026-07-14)") into small, independently reviewable implementation work packages, per the project owner's explicit instruction. Every work package below is derived strictly from an existing, frozen design section — no architectural redesign, no feature addition, no scope expansion beyond what §0–§25 of the frozen design already specify. Where a work package's scope is ambiguous, the ambiguity is resolved by quoting the exact design section it traces to, not by inventing new behavior.

Per the project owner's explicit instruction, this document stops after planning: no code is written, no work package is begun (including WP-0), and Modules 01–07 remain untouched.

---

## 0. How these work packages were derived

Each package maps to one design section or one tight cluster of design sections. §9's single-layer, four-function architecture (`generate_daily_summary()`, `generate_weekly_summary()`, `generate_duplicate_report()`, `generate_storage_report()`) is the primary organizing spine — one work package per report-generation function, preceded by a shared foundational package and followed by a lifecycle/CLI-wiring package and a documentation package, mirroring `Module 07 Implementation Plan.md`'s own precedent shape (foundational primitives → per-function packages → integration/CLI wiring → documentation) at a scale appropriate to Module 08's much simpler architecture (one layer, not two or three; four sibling functions with no forward dependency chain among most of them, unlike Module 07's tightly-sequenced six-step `ExecutionEngine`).

**A genuine pre-existing scaffold discrepancy was found while preparing this plan, and is called out here rather than silently designed around — corrected in this revision (resolves Implementation Plan Review Round 1 findings F1 and F3; see `Module 08 Implementation Plan Review.md`).** `src/pipeline/reporting.py`'s existing scaffold stub already declares `write_daily_summary(batch, records)`, `write_weekly_summary()`, `write_duplicate_report()`, `write_storage_report()` — the exact same four names and signatures already scaffolded, separately, in `src/storage/runtime_io.py` (both files pre-date this design). The frozen design's own §9 names these functions `generate_daily_summary(date)`, `generate_weekly_summary(week)`, `generate_duplicate_report()`, `generate_storage_report()` — a different prefix *and* a different signature shape than either pre-existing scaffold uses: §5 is explicit that Daily Summary/Duplicate Report are "not a `List[FileRecord]` handed in by a caller the way every earlier module receives one," so the pre-existing `write_daily_summary(batch, records)` signature cannot represent the real, date-scoped aggregation this design requires, and none of the three zero-parameter stubs has a `week` parameter either. The discrepancy is a genuine signature mismatch, not merely a naming one — the first round of this plan understated this, and the correction below states the real scope.

**Two resolution options were compared** (`Module 08 Implementation Plan Review.md`'s Round 2 correction):

- **Option A — retain and re-sign.** Keep `runtime_io.py`'s four `write_*()` functions as the module's raw-I/O layer, correct their signatures to the shape the corrected architecture actually needs (each takes whatever scoping parameter its `generate_*()` counterpart takes — `date`, `week`, or none — plus the already-rendered Markdown content, and returns the path written, preserving the pre-existing `-> str` contract), and have each `generate_*()` function call the correspondingly-named `write_*()` function to persist its output.
- **Option B — leave inert, build fresh.** Leave `runtime_io.py`'s four `write_*()` stubs exactly as they are (permanently unreachable, `NotImplementedError`), and give each `generate_*()` function its own new, independently-named persistence logic (either inlined or under new function names), never calling the old stubs at all.

**Option A is chosen**, for reasons that hold across every dimension considered:

1. **Frozen design alignment** — the design does not mandate a specific internal split (§9 only fixes the four public `generate_*()` signatures), so neither option conflicts with it directly. But §5 already establishes that `generate_*()` calls into `storage/runtime_io.py`/`storage/database.py` primitives for its *reads* (`read_action_log_entries()`, `load_metadata_store()`); Option A extends that same, already-designed read-side shape symmetrically to the write side. Option B has no basis in the design for where its new write-side functions should live instead.
2. **Modules 01–07 architecture alignment** — every module so far keeps business logic in `pipeline/*.py` and raw I/O in `storage/*.py`, thin wrappers connecting the two (`log_move()`/`log_error()`/`log_decline()` over `append_action_log()`, Module 07 WP-6). Option A matches this exactly. Option B would either duplicate the storage-boundary split under new names (redundant) or collapse raw I/O into `reporting.py` itself (a new, unprecedented departure from the storage/pipeline split every prior module observes).
3. **Architecture Decisions alignment** — decisions 11/12 establish `storage/*.py` as the project's raw-I/O boundary, and decision 12's own reasoning explicitly rejects introducing redundant mechanism/surface for a single value with no corresponding benefit (the same reasoning decision 20 applies when rejecting a new config file). Option B's "new functions, old ones left dead in the same file" is exactly this kind of avoidable surface duplication.
4. **Long-term maintainability** — Option A leaves exactly one, canonical, live set of Reports-writing functions. Option B leaves four permanently dead, identically-named-in-purpose, `NotImplementedError`-raising functions sitting beside their real replacements forever (this project's disclosed convention, matching the `undo_batch()` precedent below, is to never delete a superseded stub — so Option B's dead functions would not even be removed later).
5. **API clarity** — one `write_daily_summary()` per report type (Option A) is unambiguous. Two same-purpose functions per report type, one live and one permanently dead (Option B), is not.
6. **Migration complexity** — comparable total effort (both require writing four real persistence bodies), but Option A reuses already-reserved names/locations, avoiding an extra "where do the new functions live and what do we call them" decision Option B introduces.
7. **Risk of future confusion** — Option B's dead-but-present stubs are a real hazard in a project with this one's own history of stub/scaffold staleness (§0.6 above is itself a correction for exactly this class of drift): a future session could mistake the dead stub for unfinished work and "complete" it, or call it by mistake. Option A eliminates this risk entirely — there is nothing dead left to be confused about.
8. **Consistency with previous module evolution — corrected precedent.** The first round of this plan cited `Module 07 Implementation Plan.md` WP-9/WP-10 for a "stub in file A superseded by a function in file B" precedent; on inspection (`Module 08 Implementation Plan Review.md` finding F3) that precedent actually appears at WP-11 (`undo_batch()`), and WP-9/WP-10 do not establish it. More importantly, WP-11's case is not the closest analogy: `runtime_io.py`'s pre-existing `undo_batch(batch_id)` stub was superseded because the *real* logic needed to live in `pipeline/execution.py` for a structural reason (undo is "the exact functional inverse of WP-7's `ExecutionEngine`," which lives there, and needs direct access to WP-7's own helpers) — an architectural-placement mismatch, not a signature mismatch (the two `undo_batch(batch_id)` signatures actually agree). Module 08's situation has no such placement conflict — `runtime_io.py` is exactly where Module 08's raw Reports/ I/O primitives belong, matching every other module's storage-boundary convention — the problem is purely that the pre-existing signatures don't fit. That makes **WP-10** (`log_user_correction()`, "filling in the pre-existing, already-scaffolded stub" in place, no supersession, no dead code) the more apt precedent, not WP-11. Option A — correct the signature, fill in the existing, correctly-placed stub — is what WP-10's actual precedent recommends once the right analogy is used.

This reconciliation (signature correction plus body implementation) is WP-1's own first task, below. `src/pipeline/reporting.py`'s pre-existing `write_*()`-named, incorrectly-signed stubs (which the corrected design calls `generate_*()` at the orchestration layer, per §9) are replaced by the newly-added, correctly-named, correctly-signed `generate_*()` functions — not merely renamed, since `reporting.py`'s own stubs share `runtime_io.py`'s stale batch-shaped signature and must be replaced by the real `generate_*(date)`/`generate_*(week)`/`generate_*()` shape, not preserved under a new name.

**A second genuine pre-existing scaffold problem was found in the same file:** `src/pipeline/reporting.py`'s `finalize_batch()` and `write_action_log()` stubs both describe responsibilities the frozen design explicitly confirms Module 08 does not have (§0.6: *"Modules 01 through 07 already write all of that themselves"* — the metadata store, FileIndex, History, and the action log are each written by the module that owns the relevant field, never by a centralized post-batch reporting step). `write_action_log()` is now fully dead in concept — no module needs a centralized action-log writer, since every module since Module 01 already calls `append_action_log()` directly itself. This is the same required follow-up `Module 08 Design.md` §0.6/§25 item 1 already names — WP-1 performs that correction as its second task, below.

**Relationship to `Governance/ENGINEERING_STANDARD.md`'s Implementation Audit (§7):** the per-package review/regression/merge cadence below is a finer-grained internal implementation discipline operating *within* lifecycle stage 4 ("Implementation," §1). It does not replace the single, formal, mandatory Independent Implementation Audit (§7) that still occurs exactly once, after WP-7 is complete, before Integration Testing begins — identical to the process every one of Modules 01–07 actually followed.

---

## 1. Pre-implementation blocking prerequisite

### WP-0 — Resolve Open Decisions OD-1, OD-3, OD-5

- **Objective:** obtain the project owner's explicit, recorded confirmation of the three Open Decisions the frozen design's own risk assessment names as blocking: *"Implementation should not begin until at least OD-1, OD-3, and OD-5 are resolved"* (`Module 08 Design.md` §24).
- **Owned responsibilities:** none (no code). A dated confirmation record, appended to `Module 08 Design.md` §22 as a new subsection (never-rewrite-history convention — existing OD text unedited, mirroring `Module 07 Design.md` §26's own WP-0 addendum).
- **Dependencies:** none — first step.
- **Files expected to change:** `Module 08 Design.md` (one new, dated, append-only addendum only). No production code.
- **Acceptance criteria:** OD-1 (Duplicate/Storage Report persistence shape), OD-3 (report-generation trigger), and OD-5 (day-boundary rule) each have an explicit project-owner decision recorded.
- **Required tests:** none.
- **Rollback strategy:** not applicable — no code exists to roll back.
- **Implementation risk:** Low (no code produced). Real risk is schedule risk: WP-3/WP-5 block on OD-1, WP-6 blocks on OD-3, WP-2/WP-4 block on OD-5.

**Note on OD-2 and OD-4's narrower blocking scope.** Per §24, OD-2 and OD-4 are *"more contained and could plausibly be resolved during implementation planning instead."* OD-2 does not block WP-2 at all — NG2 (§0.2) already establishes the current default (no retroactive correction), so WP-2 proceeds under that default; OD-2 only matters if a future decision changes it. OD-4 **is** a real blocker for WP-5 specifically (data source shape).

---

## 2. Work package catalog

### WP-1 — Scaffold reconciliation & foundational aggregation primitives

- **Objective:** resolve the scaffold discrepancies above (Option A), and implement shared, pure helpers every report-generation function needs.
- **Owned responsibilities:**
  1. **`reporting.py`:** add `generate_daily_summary(date)` / `generate_weekly_summary(week)` / `generate_duplicate_report()` / `generate_storage_report()` stubs, replacing the pre-existing, incorrectly-signed `write_*()`-named stubs (§0, Option A) — not a rename, since the old stubs' `batch`/`records`-shaped signature does not carry over. Correct or retire `finalize_batch()`/`write_action_log()`'s stale docstrings (default: retire, do not repurpose — the smaller, lower-risk option). **Also correct the file-level module docstring (lines 1–21)** — it currently states Module 08 is "Responsible for: Writing the action log... Generating batch summaries (the per-run rollup that feeds into a Daily Summary)," both descriptions of the superseded, per-batch-triggered architecture §0.6 retires; replace with a short, accurate statement of the real, read-only, time/signal-scoped aggregation shape (§1/§9). (Resolves Implementation Plan Review Round 1 finding F4 — this file-level staleness is the same class of gap as `finalize_batch()`/`write_action_log()`'s, just not previously named as in-scope.)
  2. **`runtime_io.py` — only the two functions whose output location is fully determined without OD-1 (corrected in this revision, resolves Implementation Plan Review Round 2 finding F5):** fully implement `write_daily_summary(date, content: str) -> str` and `write_weekly_summary(week, content: str) -> str` — both take their `generate_*()` counterpart's own scoping parameter plus the already-rendered Markdown `content`, write it to the exact path `Module 08 Design.md` §6 already fixes (`summary_YYYY-MM-DD.md` / `summary_YYYY-Www.md`), and return the path written as `str` (preserving the pre-existing return-type contract). These become the module's raw-I/O layer for these two report types, called once each by `generate_daily_summary()`/`generate_weekly_summary()` — neither package writes to `Runtime/Reports/` directly.
  3. **`runtime_io.py` — `write_duplicate_report()`/`write_storage_report()`: signature correction only, body deferred to WP-3/WP-5.** OD-1 has not resolved whether these two report types are a single, continuously-updated file (no scoping parameter needed) or dated snapshots (which would need one) — Design §11 states this shape is "genuinely open." WP-1 corrects only the smallest OD-1-agnostic piece of the signature — `write_duplicate_report(content: str) -> str` / `write_storage_report(content: str) -> str`, i.e. content in, path written out, with no scoping parameter assumed either way — and leaves the body raising `NotImplementedError`. **WP-3 and WP-5 — which already carry the OD-1 dependency — are responsible for finalizing each function's real signature (adding a scoping parameter if OD-1 requires one) and implementing its body**, as part of their own existing scope (see their entries below, updated in this revision). WP-1 does not depend on OD-1 as a result — it touches these two functions only enough to remove their stale `batch`/`records`-shaped signature, not to decide their real one.
  4. The data-derived "as of" marker helper (§7).
  5. Shared action-log filters (by calendar day, by signal type).
  6. A malformed-line-safe wrapper over `read_action_log_entries()` (§12 Layer 1).
- **Dependencies:** WP-0 only insofar as OD-5 shapes exactly how "day" is applied at the G6-enforcement point (WP-2/WP-4), not this package's own generic grouping logic. **Explicitly not dependent on OD-1** (F5's fix) — the two OD-1-shaped functions are only minimally touched here (stale-signature removal), never finalized.
- **Files expected to change:** `src/pipeline/reporting.py` (stub replacement, `finalize_batch()`/`write_action_log()` docstrings, module-level docstring); `src/storage/runtime_io.py` (`write_daily_summary()`/`write_weekly_summary()` fully implemented; `write_duplicate_report()`/`write_storage_report()` given only a minimal, OD-1-agnostic signature, body left as `NotImplementedError`); new shared helpers (in `reporting.py` or a new `src/core/reporting_helpers.py`, an implementation-time judgment call).
- **Acceptance criteria:** `write_daily_summary()`/`write_weekly_summary()` each accept their `generate_*()` counterpart's scoping parameter plus rendered content, write to the exact §6-fixed path, and return that path as `str`; `write_duplicate_report()`/`write_storage_report()` each accept `content: str` and return `str`, with no scoping parameter assumed and their body still explicitly `NotImplementedError` (proving WP-1 did not prematurely decide OD-1's outcome); no `generate_daily_summary()`/`generate_weekly_summary()` call writes to `Runtime/Reports/` directly (both go through WP-1's now-complete functions); "as of" marker correct for distinct/tie/empty cases; calendar-day filter buckets by the entry's own `timestamp`, not wall-clock "today"; malformed-line wrapper never raises, always returns an accurate count; `reporting.py`'s module-level docstring contains no reference to Module 08 writing the action log or being triggered per-batch; zero write of any kind beyond `write_daily_summary()`/`write_weekly_summary()`'s own now-real `Runtime/Reports/` writes, exercised only by this package's own direct tests (not yet called by any `generate_*()` function, which is WP-2/WP-4's own scope).
- **Required tests:** `pipeline/test_reporting.py` — marker, day-filter, malformed-line-wrapper, zero-write immutability; `storage/test_runtime_io.py` — `write_daily_summary()`/`write_weekly_summary()` each write their `content` argument verbatim to the expected, fully-known path and return that path, called directly (not yet wired to a `generate_*()` caller, which is WP-2/WP-4's own scope); `write_duplicate_report()`/`write_storage_report()` each raise `NotImplementedError` when called (a deliberate, asserted placeholder test — proves WP-1 left these two genuinely unfinished rather than silently guessing at OD-1's outcome).
- **Rollback strategy:** delete/revert the new `generate_*()` stubs, `write_daily_summary()`/`write_weekly_summary()`'s new implementations, the minimal `write_duplicate_report()`/`write_storage_report()` signature edits, and the module-level docstring edit; restore original `finalize_batch()`/`write_action_log()` docstrings if retirement is reverted. Zero blast radius (first real code package) — nothing outside `reporting.py`/`runtime_io.py` depends on the old signatures, since they were never implemented (`NotImplementedError`).
- **Implementation risk:** Low-Medium — `write_daily_summary()`/`write_weekly_summary()`'s signature and target path are both fully fixed by the frozen design (§6), leaving only mechanical implementation risk; `write_duplicate_report()`/`write_storage_report()`'s risk is deliberately deferred to WP-3/WP-5, where OD-1's real answer will actually be known.

**Status (2026-07-14): WP-1 implemented, tested, and independently audited — awaiting explicit approval before WP-2 begins.** Implemented exactly as scoped above: `reporting.py`'s four `generate_*()` stubs replace the old `write_*()`-named ones; `finalize_batch()`/`write_action_log()` retired (deleted, not repurposed — the smaller, lower-risk option); the module-level docstring corrected (no reference to Module 08 writing the action log or being triggered per-batch). `runtime_io.py`'s `write_daily_summary()`/`write_weekly_summary()` fully implemented (real path per §6, verified against a real, sandboxed `tmp_path` filesystem — never mocked); `write_duplicate_report()`/`write_storage_report()` given only the minimal, OD-1-agnostic signature, body left as `NotImplementedError`, directly tested to confirm they still are. Shared primitives (`read_action_log_entries_safe()`, `compute_as_of_marker()`, `filter_entries_by_day()`, `filter_entries_by_action()`) added to `reporting.py` (the disclosed judgment call between `reporting.py` and a new `core/reporting_helpers.py`, resolved in favor of `reporting.py` — none of these are reused outside Module 08, unlike `core/`'s existing cross-module helpers). Tests: `pipeline/test_reporting.py` + `storage/test_runtime_io.py`, 39/39 passing. Full regression suite: 607/607 (568 pre-existing + 39 new), including a direct check that no real `Database/`/`Runtime/` file was touched. No frozen module (01–07) modified — confirmed via `git status`, only `reporting.py`/`runtime_io.py` changed among existing `.py` files, plus 2 new test files. Independent implementation audit: zero Critical/High/Medium findings; one Low (the new filter/marker functions access `entry["timestamp"]` by direct indexing rather than `.get()`, which would raise `KeyError` on a syntactically-valid-but-wrong-shape log line — unreachable under `append_action_log()`'s own real, unconditional behavior, but a disclosed inconsistency against `filter_entries_by_action()`'s own more defensive `.get("action")`); one Cosmetic (the `runtime_io.py` section-header comment cites decision 25 as if it governs all four `write_*()` functions, though it only actually bears on two of them). Neither finding fixed — reported per instruction, awaiting explicit direction.

### WP-2 — `generate_daily_summary(date)`

- **Objective:** implement the Daily Summary exactly as `Metadata & Log Schema.md`'s worked example specifies (§3, §6).
- **Owned responsibilities:** loads action log (via WP-1's wrapper) + metadata store, filters to `date`, aggregates every count/per-file row per §3, renders the fixed template, writes via WP-1's already-complete `runtime_io.write_daily_summary()`. Implements §12 Layer 1's day-scoped cases and G6/OD-5's closed-period rule.
- **Dependencies:** WP-1; OD-5 (day-boundary rule). Does not require OD-2 (implemented under NG2's default).
- **Files expected to change:** `reporting.py` (`generate_daily_summary()`) only. **(Corrected in this revision — resolves Implementation Plan Review Round 2 finding F5's knock-on effect: `runtime_io.py`'s `write_daily_summary()` is now fully implemented by WP-1 itself; this package only calls it, it does not modify it.)**
- **Acceptance criteria:** matches the worked example field-for-field; every figure traces to a real source (G3/I5); byte-identical re-run (G5); a closed day is never silently rewritten (G6/I6); zero write.
- **Required tests:** aggregation correctness; empty-day handling; malformed-line resilience visible in output; G6/day-boundary test; idempotency; zero-write immutability.
- **Rollback strategy:** delete/revert `generate_daily_summary()`'s body, reverting `reporting.py`'s own stub to WP-1's placeholder. WP-1's `write_daily_summary()` in `runtime_io.py` is unaffected either way (this package only calls it, never modifies it).
- **Implementation risk:** Medium — most field-heavy report type, but fully constrained by an already-committed worked example.

**Status (2026-07-14): WP-2 implemented, tested, and independently audited — approved and committed (`module08-dev`, commit `59db7b8`).** Implemented exactly as scoped above: `generate_daily_summary()` loads via WP-1's `read_action_log_entries_safe()`/`filter_entries_by_day()`/`filter_entries_by_action()`, cross-references `storage.database.load_metadata_store()` (§5's explicit dual-source statement), and writes via WP-1's already-complete `runtime_io.write_daily_summary()` — no other file touched, confirmed via `git diff` against the WP-1 commit (only `reporting.py`/`test_reporting.py` changed). Counts derived per §13's own explicit per-module citations (`score_confidence` entries for auto/approval-required/review-required, per the Module 06 row; `suggested_name`/`suggested_destination` for per-file rows, per the Module 05 row). Closed-day protection (G6/I6) implemented per `ARCHITECTURE_DECISIONS.md` decision 27, via a read-only, disclosed reach into `runtime_io._RUNTIME_REPORTS_PATH` rather than a new `runtime_io.py` public accessor, to keep the file-touch footprint to `reporting.py` alone. Tests: `pipeline/test_reporting.py`, 51/51 passing (25 new WP-2 tests covering aggregation, empty-day, malformed-line disclosure, closed-day protection, idempotency, zero-write). Full regression suite: 634/634, confirmed no real `Database/`/`Runtime/` file touched. Independent implementation audit: zero Critical/High/Medium findings; two Low (the closed-day check's private-attribute reach into `runtime_io._RUNTIME_REPORTS_PATH`; the malformed-line disclosure line's wording differs from §12's own illustrative example phrasing, same fact conveyed). Both accepted and recorded, not fixed — four accepted Low findings total across WP-1/WP-2.

### WP-3 — `generate_duplicate_report()`

- **Objective:** implement the Duplicate Report over every duplicate/version-signal-bearing record (§3), per OD-1's resolved shape.
- **Owned responsibilities:** loads metadata store, filters to signal-bearing records, categorizes by outcome (archived/kept/overridden), cross-references `detect_duplicates_and_versions` entries, renders, writes via `runtime_io.write_duplicate_report()`. **Also finalizes `write_duplicate_report()` itself (corrected in this revision — resolves Implementation Plan Review Round 2 finding F5): WP-1 leaves it with only a minimal, OD-1-agnostic signature (`content: str -> str`) and a `NotImplementedError` body; this package adds whatever scoping parameter OD-1's actual resolution requires (none, if a single current-state file; a date-like parameter, if dated snapshots) and implements the real body**, since this package is the first (and only) one that actually knows OD-1's resolved shape.
- **Dependencies:** WP-1; OD-1 (persistence shape — now also determines this package's own finalization of `write_duplicate_report()`'s signature, not only its G6 acceptance criteria and aggregation logic).
- **Files expected to change:** `reporting.py`, `runtime_io.py` (`write_duplicate_report()`'s signature finalization and body).
- **Acceptance criteria:** every signal-bearing record appears exactly once, correctly categorized; traceable to real log/store data; zero direct FileIndex/History read (§8); G6 compliance matches OD-1; `write_duplicate_report()`'s finalized signature and body match whichever OD-1 outcome was actually confirmed, with no leftover `NotImplementedError` path.
- **Required tests:** categorization correctness (all three categories); exclusion of non-signal records; traceability cross-check; shape-specific G6 test; zero-write immutability; `write_duplicate_report()`'s own direct test (writes `content` — plus any new scoping parameter — to the correct, OD-1-resolved path and returns it).
- **Rollback strategy:** delete/revert `generate_duplicate_report()` and `write_duplicate_report()`'s finalized signature/body, reverting the latter to WP-1's minimal, OD-1-agnostic placeholder. No other package depends on this one.
- **Implementation risk:** Medium — contingent on OD-1; aggregation logic itself is Low risk.

**Status (2026-07-14): WP-3 implemented, tested, and independently audited — approved and committed (`module08-dev`, commit `705625c`).** Implemented exactly as scoped above: `generate_duplicate_report()` reads the full action log (via WP-1's `read_action_log_entries_safe()`) and metadata store, includes only `duplicate_of`-bearing and `version_rank == "superseded"` records (a "latest"-ranked sibling is referenced only as another row's "Related To" value, never given its own row), categorizes each by the last chronological disposition action (archived/kept/overridden by user, per `Runtime/Reports/README.md` and `ARCHITECTURE_DECISIONS.md` decision 23), and writes via `runtime_io.write_duplicate_report()`, finalized this package per decision 25 — no scoping parameter needed, signature unchanged from WP-1, only the body implemented. No other file touched beyond `reporting.py`/`runtime_io.py` and their test files, confirmed via `git diff` against the WP-2 commit. Tests: `pipeline/test_reporting.py` + `storage/test_runtime_io.py`, 92/92 passing (36 new WP-3 tests covering all three disposition categories including undo/last-action-wins edge cases, exclusion of ordinary and "latest"-ranked records, traceability, always-overwritten behavior, empty state, as-of-marker scoping, malformed-line disclosure, zero-write). Full regression suite: 660/660, confirmed no real `Database/`/`Runtime/` file touched. Independent implementation audit: zero Critical/High/Medium findings; one Low (the "Kept" category folds three distinct real states — still pending, explicitly rejected, reversed via undo — into one label, a necessary consequence of the frozen design's own fixed three-category vocabulary, not a defect). Five accepted Low findings total across WP-1/WP-2/WP-3.

### WP-4 — `generate_weekly_summary(week)`

- **Objective:** roll up already-written Daily Summaries (§9), including the narrow missing-day disambiguation exception (§5/§12's L1 fix).
- **Owned responsibilities:** reads the week's Daily Summary files, rolls up trends, and — for a missing day — consults the raw action log (WP-1's day filter) solely to distinguish "no activity" from "generation failed" (never to re-derive figures), rendering the distinction visibly. Writes via WP-1's already-complete `runtime_io.write_weekly_summary()`.
- **Dependencies:** WP-1, WP-2 (real output format); OD-5.
- **Files expected to change:** `reporting.py` (`generate_weekly_summary()`) only. **(Corrected in this revision — resolves Implementation Plan Review Round 2 finding F5's knock-on effect: `runtime_io.py`'s `write_weekly_summary()` is now fully implemented by WP-1 itself; this package only calls it, it does not modify it.)**
- **Acceptance criteria:** correct ISO week filename/date range, including a year-boundary test; quiet-day vs. failed-generation always visibly distinguished; only closed Daily Summaries rolled up; the action-log exception used solely for disambiguation, never recomputation.
- **Required tests:** multi-day roll-up against real WP-2 fixtures; both disambiguation sub-cases; ISO year-boundary case; determinism; zero-write immutability.
- **Rollback strategy:** delete/revert `generate_weekly_summary()`'s body, reverting `reporting.py`'s own stub to WP-1's placeholder. WP-1's `write_weekly_summary()` in `runtime_io.py` and WP-2 are both unaffected either way.
- **Implementation risk:** Medium-High — disambiguation logic and ISO week arithmetic are both genuinely new territory with no prior-module precedent.

### WP-5 — `generate_storage_report()`

- **Objective:** implement the Storage Report (§3) per OD-4's resolved data source.
- **Owned responsibilities:** **if OD-4 → metadata-store-only:** aggregates existing `size_bytes` by folder/category, no new dependency. **If OD-4 → real filesystem measurement:** additionally walks the destination library, degrading a symlink loop/unreadable subfolder/permission error to an honest "could not measure" note (§12 philosophy extended), never a crash or fabricated size. Writes via `runtime_io.write_storage_report()`, shaped by OD-1 identically to WP-3. **Also finalizes `write_storage_report()` itself (corrected in this revision — resolves Implementation Plan Review Round 2 finding F5): WP-1 leaves it with only a minimal, OD-1-agnostic signature (`content: str -> str`) and a `NotImplementedError` body; this package adds whatever scoping parameter OD-1's actual resolution requires and implements the real body**, mirroring WP-3's own identical finalization of `write_duplicate_report()`.
- **Dependencies:** WP-1; OD-1 and OD-4 (the only package blocked on two Open Decisions). OD-1 now also determines this package's own finalization of `write_storage_report()`'s signature, not only its G6 acceptance criteria.
- **Files expected to change:** `reporting.py`, `runtime_io.py` (`write_storage_report()`'s signature finalization and body); if filesystem measurement is chosen, a new small helper (`src/core/` or colocated) plus a `KNOWN_LIMITATIONS.md` disclosure at release time (`ENGINEERING_STANDARD.md` §18).
- **Acceptance criteria:** every figure traces to a real source; adversarial filesystem cases never crash or fabricate (if applicable); zero file-content read, only folder/size metadata (§18); G6 matches OD-1; `write_storage_report()`'s finalized signature and body match whichever OD-1 outcome was actually confirmed, with no leftover `NotImplementedError` path.
- **Required tests:** aggregation correctness; adversarial filesystem suite against a real `tmp_path` fixture (if applicable); shape-specific G6 test; zero-write immutability; `write_storage_report()`'s own direct test (writes `content` — plus any new scoping parameter — to the correct, OD-1-resolved path and returns it).
- **Rollback strategy:** delete/revert `generate_storage_report()`, `write_storage_report()`'s finalized signature/body (reverting the latter to WP-1's minimal, OD-1-agnostic placeholder), and any new helper. WP-1 unaffected.
- **Implementation risk:** **High if OD-4 → real filesystem measurement** (first read-only structural filesystem dependency of its kind, no exact precedent). **Low-Medium if OD-4 → metadata-store-only** (structurally near-identical to WP-3).

### WP-6 — Report generation lifecycle & CLI wiring

- **Objective:** implement §10's five-step lifecycle over WP-2 through WP-5, wired per OD-3's resolved trigger.
- **Owned responsibilities:** if OD-3 → explicit CLI step: a new `report()` function in `main.py` invoking the requested `generate_*()` function(s), printing a CLI summary (§10 step 5). If OD-3 → auto-hook after `execute()`: an additive call site inside `execute()` (Module 07's own function) — never editing its existing logic. Layer 2's outer safety net (§12) implemented at this orchestration layer.
- **Dependencies:** WP-2, WP-3, WP-4, WP-5; OD-3.
- **Files expected to change:** `main.py` (new function or additive call site only); `test_main.py`.
- **Acceptance criteria:** matches OD-3's resolved shape exactly; Layer 2 demonstrated to isolate one report type's failure from the others (and, if auto-hook, from `execute()`'s own completed work, G4/I4); CLI summary matches project convention.
- **Required tests:** per-report-type CLI invocation; forced single-function failure isolated by Layer 2; if auto-hook, a forced failure confirmed not to block/roll back `execute()`.
- **Rollback strategy:** delete/revert the new function or call site. WP-2–WP-5 remain independently valid and callable.
- **Implementation risk:** Low-Medium (explicit-CLI-step shape); Medium (auto-hook shape — touches a frozen module's own file additively, requiring a dedicated regression check that Module 07's CLI behavior is unchanged).

### WP-7 — Implementation-time documentation & schema updates

- **Objective:** complete §25's required follow-ups (items 1, 2, 4) and §16's closing cross-check.
- **Owned responsibilities:** confirm `finalize_batch()`/`write_action_log()`'s disposition is documented (§25 item 1); an explicit recorded decision on `Database/Learning/` read access (§25 item 2); a corrected `Release/DEPENDENCY_DIAGRAM.md` "Notes" sentence (§25 item 4); a cross-check of `Metadata & Log Schema.md`'s "Reports" section against OD-1's resolution (§16).
- **Dependencies:** WP-0 (OD-1); sequenced after WP-1 through WP-6.
- **Files expected to change:** `Release/DEPENDENCY_DIAGRAM.md`; `Metadata & Log Schema.md`. (`reporting.py`'s module-level and function-level docstrings are now WP-1's own explicit scope, §0/WP-1 above — resolves Implementation Plan Review Round 1 finding F4's ambiguity; no docstring work remains for this package.) No frozen-module file touched.
- **Acceptance criteria:** every §25 item verifiably closed; no stale/contradictory text remains.
- **Required tests:** none directly; verified later by PCV check 6.
- **Rollback strategy:** revert the specific edits. No code affected.
- **Implementation risk:** Low implementation risk, High consequence-if-skipped — this exact gap class has recurred twice already in this project's history (Module 02/03's own schema-doc gaps).

---

## 3. Dependency graph (text form)

```
WP-0 (OD-1/OD-3/OD-5; OD-2/OD-4 deferred to their own packages)
  ├─ OD-1 ──▶ WP-3, WP-5
  ├─ OD-3 ──▶ WP-6
  └─ OD-5 ──▶ WP-2, WP-4

WP-1 (scaffold reconciliation + foundational primitives)
  ├──▶ WP-2 (generate_daily_summary)
  │      └──▶ WP-4 (generate_weekly_summary — reads WP-2's output)
  ├──▶ WP-3 (generate_duplicate_report)
  └──▶ WP-5 (generate_storage_report — also needs OD-4)

WP-2, WP-3, WP-4, WP-5 ──▶ WP-6 (lifecycle orchestration + CLI wiring)

WP-0 (OD-1), WP-1..WP-6 ──▶ WP-7 (doc/schema updates)
```

No work package modifies any frozen-module file, with one narrow, disclosed exception: if OD-3 resolves toward the auto-hook shape, WP-6 adds a call site inside `execute()` — additive only, covered by a dedicated regression check. Every other arrow is one-directional and read-only.

---

## 4. Highest-risk work packages

- **WP-5 (`generate_storage_report()`) — High risk, conditional on OD-4.** If real filesystem measurement is chosen, this is the first read-only structural filesystem dependency this pipeline has introduced at report time — a genuinely new adversarial-input class with no earlier-module precedent. Should not start until OD-4 is resolved; test plan should use a real, sandboxed filesystem, never mocked, mirroring `Module 07 Implementation Plan.md` WP-5's own precedent for a first-of-its-kind filesystem interaction.
- **WP-4 (`generate_weekly_summary()`) — Medium-High risk.** Missing-day disambiguation and ISO week-numbering arithmetic (especially year-boundary weeks) are both genuinely new, easy-to-miss-a-subtle-bug territory.

Two further packages warrant a brief note:
- **WP-1** is conceptually simple but carries outsized consequence-risk if the reconciliation is left half-done — review should explicitly check it was completed cleanly, not just that new functions work.
- **WP-2** is the most field-heavy report type, so has the largest field-mapping surface area, but is otherwise Low-Medium risk given the already-committed worked example.

---

## 5. Cross-cutting standards applying to every work package

Per `Governance/ENGINEERING_STANDARD.md` §5/§6.1/§19:

- Implement exactly what the frozen design specifies — no drift into §4's reserved-for-later responsibilities (FileRecord enrichment, active learning, log rotation, a query/search interface, any UI/dashboard beyond Markdown).
- Every new function covered by isolated `pytest` tests (`tmp_path`/`monkeypatch`), never real `Database/`/`Runtime/` paths.
- Full project-wide unit suite re-run after every package, 100% pass required.
- Every already-frozen module's isolated suite re-confirmed unchanged after every package — verified directly, not inferred. Especially load-bearing for WP-6 if the auto-hook shape is chosen.
- A package is not merged until implemented, independently reviewed, regression-tested, and explicitly approved.
- Every zero-write guarantee (G1/G2, I1–I3) verified by an explicit immutability test in every package touching `FileRecord`/the metadata store (WP-1 through WP-5), simplified per §0.3 to "assert no `FileRecord` field and no `Database/*` file changes at all."

---

## 6. Recommended implementation order

1. **WP-0** — resolve OD-1/OD-3/OD-5 (OD-2/OD-4 deferred to WP-2/WP-5).
2. **WP-1** — scaffold reconciliation & foundational primitives.
3. **WP-2** — `generate_daily_summary()` (requires OD-5).
4. **WP-3** — `generate_duplicate_report()` (requires OD-1; may run in parallel with WP-2/WP-4).
5. **WP-4** — `generate_weekly_summary()` (requires WP-2's real output and OD-5).
6. **WP-5** — `generate_storage_report()` (requires OD-1 and OD-4; highest-risk — do not rush).
7. **WP-6** — lifecycle orchestration & CLI wiring (requires WP-2 through WP-5 and OD-3).
8. **WP-7** — implementation-time documentation & schema updates.

WP-3 has genuine scheduling flexibility (depends only on WP-1 and OD-1). Every other package's position is fixed by a real functional dependency. This order defers the two highest-risk pieces (WP-4, WP-5) until the machinery they build on already exists and is already reviewed — the same sequencing principle `Module 07 Implementation Plan.md` applied deferring its own highest-novelty package (WP-8) until WP-7 existed.

---

## 7. Verification that this plan matches the frozen Module 08 Design exactly

Checked section by section against `Module 08 Design.md`:

- **§3/§4** — all five named responsibilities map to WP-2 through WP-5 plus WP-1's helpers; none of §4's five reserved responsibilities appears in any work package.
- **§5/§9** — each report type's input source in WP-1 through WP-5 traces exactly to §5's per-report-type statement; no package reads a source §5 doesn't name for that report type.
- **§7** — WP-1's "as of" marker and every downstream package's acceptance criteria implement §7's chosen option (D) only; no package reintroduces the rejected wall-clock option (B).
- **§8** — every "files expected to change" list contains only `reporting.py`, `runtime_io.py`, `main.py` (WP-6 only, additive), and documentation files — never a `Database/*` file, never the action log, never a Modules 01–07-owned implementation file.
- **§10** — WP-6's five owned steps map one-to-one, in order, to §10's five numbered steps.
- **§11/OD-1/OD-5** — WP-2's day-boundary/G6 enforcement and WP-3/WP-5's OD-1-dependent persistence logic trace directly to §11's stated tensions; no invented persistence shape.
- **§12** — all five Layer 1 cases are each assigned to a specific package (WP-1, WP-2, WP-4, WP-6's Layer 2); no invented sixth case.
- **§16/§18/§19** — no new action-log value introduced (§16); WP-5's conditional filesystem dependency is the only new dependency, exactly matching §18's own disclosure; §19's performance measurement is correctly left out of this plan as a Release-stage deliverable, not an implementation package.
- **§22** — OD-1 through OD-5 each mapped to exactly the work package(s) §24 identifies; no Open Decision is resolved by this plan itself.
- **§25** — all three still-open follow-up items are assigned to WP-1/WP-7; item 3 was already promoted to OD-5 by the frozen design and is handled via WP-0, not re-listed as a separate follow-up.

No work package requires modifying `Module 08 Design.md` itself except WP-0's own explicitly-scoped, append-only addendum.

---

## 8. Consistency review

### 8.1 Against the frozen Module 08 Design

No contradiction found beyond §7 above. One point disclosed explicitly: this plan's own WP-1 discovery (the `reporting.py`/`runtime_io.py` naming duplication, and `write_action_log()`'s staleness) is new information not present in `Module 08 Design.md` itself — a pre-existing scaffold fact the design's own `generate_*()` naming (§9) already resolves correctly by being more specific than either pre-existing stub set. Disclosed here as a planning-stage finding, not silently designed around; does not require reopening the frozen design.

### 8.2 Against Modules 01–07

- `src/pipeline/reporting.py` — owned by Module 08 alone; safe to modify freely.
- `src/storage/runtime_io.py` — the four functions this plan touches are already explicitly comment-marked "Module 08 (Logging & Reporting) territory," distinct from Modules 01/07's own functions in the same file (`append_action_log()`, `read_action_log_entries()`, `stage_batch_temp()`/`clear_batch_temp()`/`write_batch_plan()`/`read_batch_plan()`, `undo_batch()`), untouched by any package above.
- `src/main.py` — WP-6 is the only package touching this file, and only additively; every existing function (`scan()` through `undo()`) remains untouched in its own logic, matching `ENGINEERING_STANDARD.md` §11's "no retroactive edit of an earlier frozen module's own logic" rule.
- No package reads a field before its owning module has populated it — Module 08 sits last in the strict linear chain (`Release/DEPENDENCY_DIAGRAM.md`), so every field WP-2 through WP-5 read is already fully populated by the time Module 08 runs.

### 8.3 Against Architecture Decisions

Cross-checked directly against `Governance/ARCHITECTURE_DECISIONS.md`:
- **Decision 3** (ownership boundaries, contract-first) — every package's scope is drawn from the frozen contract, never code-first invention.
- **Decision 11** (metadata store philosophy) — WP-1 through WP-5 reuse the existing `load_metadata_store()`, introducing no new read pattern; consistent with §19's already-disclosed cost split.
- **Decision 16** (frozen module policy) — WP-6's narrow, additive touch to `execute()` (only if OD-3 → auto-hook) is checked against this decision's discipline: additive, not a modification of Module 07's own frozen logic, explicitly called out as the one stated exception rather than folded into a blanket "no frozen module touched" claim.
- **Decision 17** (dependency chain, strictly linear) — this plan's ordering is consistent with Module 08 sitting last in the chain; no non-linear dependency introduced.
- **Decision 20** (destination library root configuration) — WP-5's conditional dependency, if chosen, reuses the existing `destination_root` configuration Module 07 already reads, per §5 of the frozen design. **(Corrected in this revision — resolves Implementation Plan Review Round 1 finding F2; the original text mis-cited this as "Decision 18," which is actually "Error handling philosophy.")**
- No new Architecture Decision is required by this plan itself. If OD-1/OD-3/OD-4/OD-5's eventual resolutions warrant a new numbered decision (mirroring Module 07's own OD-1/OD-2 → decisions 20/21), that is WP-0's own outcome to produce, not pre-empted here.

### 8.4 Against governance documents

- **`ENGINEERING_STANDARD.md` §5** — verified via §7 above; no redesign, no scope expansion found.
- **`ENGINEERING_STANDARD.md` §18** (new dependencies named and justified before implementation) — WP-5's conditional filesystem-walk dependency is named and justified here, contingent on OD-4, exactly as this section requires; the frozen design's own §18 already named this exact possibility, so it is not "discovered mid-implementation."
- **`ENGINEERING_STANDARD.md` §19** (regression policy) — restated in §5 above for every package.
- **`Governance/PROJECT_ROADMAP.md`** — this plan does not change Module 08's current status ("Design Frozen — Not Implemented"); WP-0 is not begun, so no status update is warranted here.
- **`Governance/FROZEN_MODULE_CHANGE_POLICY.md`** — not invoked; no package proposes a change to an already-frozen module's contract, and WP-6's one narrow additive exception does not alter any contract, guarantee, or existing behavior of Module 07.

**No inconsistency was found in any of the four checks**, beyond the one pre-existing scaffold discrepancy already disclosed in §0 and §8.1, which this plan resolves at the planning level only.

---

## 9. Revision log

**Round 2 correction (this revision) — resolves `Module 08 Implementation Plan Review.md` Round 1 findings F1–F4:**

- **F1 resolved** — §0, WP-1: the scaffold discrepancy is now stated as a genuine signature mismatch (not merely naming), and WP-1's scope now explicitly includes correcting `runtime_io.py`'s four `write_*()` signatures to a concrete, measurable shape (scoping parameter + rendered content in, written path out).
- **F3 resolved** — §0: Option A (retain and re-sign the existing `write_*()` stubs) is chosen over Option B (leave them inert, build fresh) after an explicit eight-dimension comparison. The precedent citation is corrected from Module 07's WP-9/WP-10 to WP-10 alone, with WP-11's `undo_batch()` case explicitly distinguished (an architectural-placement mismatch, not present here) rather than relied on.
- **F2 resolved** — §8.3: "Decision 18" corrected to "Decision 20" (the actual destination-library-root-configuration decision; Decision 18 is "Error handling philosophy").
- **F4 resolved** — WP-1, WP-7: `reporting.py`'s module-level docstring is now explicitly assigned to WP-1 (alongside the two function-level docstrings it already covered), removing the ambiguity in WP-7's prior "if not already closed by WP-1" hedge.

No work package's dependency graph, Open Decision assignment, or overall package structure changed as a result of these corrections — only WP-1's own scope/acceptance-criteria/risk text, WP-7's file list, and §8.3's citation.

**Round 3 correction — resolves `Module 08 Implementation Plan Review.md` Round 2 finding F5:**

- **F5 resolved** — WP-1's ownership of `runtime_io.py`'s four `write_*()` functions is now split by what OD-1 actually gates: WP-1 fully implements `write_daily_summary()`/`write_weekly_summary()` (both fully determined by the frozen design today — §6 fixes their exact path pattern), and gives `write_duplicate_report()`/`write_storage_report()` only the smallest OD-1-agnostic signature correction, explicitly leaving their body (and any additional scoping parameter OD-1 turns out to require) to WP-3/WP-5 — the two packages that already carry the OD-1 dependency and are the first to actually know its resolved shape. WP-2's and WP-4's "Files expected to change" no longer list `runtime_io.py`, since WP-1 now fully owns those two functions and neither package modifies them. WP-1's own "Dependencies" line is unchanged (still OD-5 only) and is now accurate — it no longer implicitly depends on OD-1.

No work package's dependency graph or Open Decision assignment changed as a result of this correction — WP-3 and WP-5 already carried the OD-1 dependency before this fix; they now simply also own finalizing one `runtime_io.py` function's real signature and body each, which does not add a new inbound or outbound arrow to §3's dependency graph. Rollback strategies for WP-1, WP-2, WP-3, WP-4, and WP-5 were each updated to reflect the new split precisely.

---

*End of implementation plan. No code has been written. No work package has been started, including WP-0. Per the project owner's explicit instruction, this document stops here, awaiting explicit approval before WP-0 (or any subsequent work package) begins.*
