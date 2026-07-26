# Product Readiness Review — Downloads Intelligence

**Date:** 2026-07-23 · **Branch:** `product-foundation` (from `v0.8.1`) · **Reviewer stance:** Principal Product Engineer / Staff Engineer / UX Engineer / QA Lead / TPM, combined, external and unsentimental.
**Scope:** review only. No code written, no files modified other than this one, no refactoring performed. Every finding below is backed by something directly read, run, or measured in this repository during this review — not restated from the project's own prior self-assessment.
**Verified baseline facts:** 729/729 tests passing. Git is genuinely clean (`v0.8.1` tagged, `product-foundation` branch, nothing uncommitted) — this is real and worth stating plainly, since it fixes a gap a prior audit in this same review chain flagged as the single biggest quiet risk in the project. No open Critical/High engineering defects. That much of the "Current State" header is accurate. Several other framings in it are not, and the rest of this document explains why.

---

## Ground truth this review is built on (not opinion)

- `python -m src.main` — the one documented way to run this software — executes `scan() → classify() → extract() → detect_duplicates() → suggest_naming() → score_confidence()` and **stops**. `preview()`, `execute()`, `undo()`, and `report()` are separate functions a caller must know to invoke manually, in the right order, with the right arguments. There is no `argparse`, no subcommands, no `--help`. This is not a CLI in any sense a user outside this exact chat-driven workflow would recognize.
- The project's real, live `Database/Metadata/metadata_store.json` — not a validation sandbox, the actual one `python -m src.main` would write to — contains **zero records**. Every one of the dozens of UAT runs, integration tests, and both real-world validation sessions ran against isolated, throwaway directories. This software has never processed a single file in its own real environment, not once, despite eight modules being individually "released."
- `README.md`, the first file anyone opens, still says: *"This is the design/build workspace... Nothing here touches a real Downloads folder until a full scan-to-execution path is built and tested"* — false since Module 08 shipped. This staleness was already named and prioritized (`TD-28`, `PROJECT_BACKLOG.md` Priority 0) and is still unresolved.
- The root `requirements.txt` pins `PyYAML` twice, to two different versions (`6.0.1` and `6.0.3`), in the same file. A second, entirely different `src/requirements.txt` also exists, unpinned, and still labeled *"scaffold stage — pin exact versions once modules are implemented and tested"* — they are.
- No `pyproject.toml`, `setup.py`, install script, or CI config exists anywhere in the repository.
- No log rotation exists anywhere in `src/` (`action_log.jsonl` grows forever by design — disclosed, unaddressed).
- 172 markdown files document a ~9,000-line codebase.

Everything below is organized around these facts, not around the project's own narrative of itself.

---

## Classified Findings

### CRITICAL

**C1 — There is no real, runnable entry point for a human.**
- **Problem:** The pipeline's only "automatic" path stops halfway (before preview/approval/execution/reporting), and the remainder requires calling internal functions directly, in the correct order, with hand-constructed arguments (e.g. `ApprovalDecision` objects). This is a Python library API, not an application.
- **Impact:** Nobody outside a live Claude session with source-level knowledge of `main.py` can currently operate this software. "Desktop application" is not an accurate description of the current state at any level.
- **Evidence:** `src/main.py` lines 818–824 (`if __name__ == "__main__":` block); no `argparse`/CLI framework anywhere in `src/`.
- **Recommended solution:** A real command surface — subcommands (`scan`, `preview`, `approve`, `execute`, `undo`, `report`, or a single `run` that chains them with a real pause-for-approval step) — built entirely from functions that already exist and are already tested. This is wiring, not new logic.
- **Estimated effort:** Small–Medium (days, not weeks — no new pipeline logic required).
- **Priority:** P0.
- **Risk if ignored:** Every other v0.9 goal (Human Review Queue, Undo validation, real-world validation at scale) is blocked behind this, because none of them can be exercised by anyone without reading source code first.
- **Update, 2026-07-23 — DELIVERED.** `python -m src.cli` now exists (`src/cli.py`, 9 subcommands: `scan`, `run`, `preview`, `execute`, `undo`, `report`, `status`, `version`, `config`), designed, reviewed, implemented, independently audited, and carried through a full Product Acceptance Test (verdict: **Accepted with Major Issues** — real, disclosed UX gaps remain, tracked in a dedicated Release Planning Matrix, but the finding itself — "nobody outside a live Claude session can operate this software" — is resolved). Full record: `C1_COMPLETION_REPORT.md`. This does not retroactively mark C2/C3/C4 below as resolved — each is addressed on its own terms.

**C2 — Zero real dogfooding: the live installation has never been used.**
- **Problem:** The actual `Database/`/`Runtime/` this software would use in real operation is empty. All validation evidence comes from segregated, disposable sandboxes.
- **Impact:** Every claim this project makes about being "released" or "production-ready" is true only in a lab sense. Nobody has confirmed the real, default configuration works end-to-end even once outside a controlled harness.
- **Evidence:** `Database/Metadata/metadata_store.json` = `[]`; `Runtime/Logs/action_log.jsonl` = 0 lines.
- **Recommended solution:** Once C1 is fixed, run it — once, deliberately, against a real (or realistically messy) Downloads folder, using the actual project paths, not a validation copy. This should be the very first thing that happens after C1 ships.
- **Estimated effort:** Small (a few hours, once C1 exists).
- **Priority:** P0 (sequenced immediately after C1).
- **Risk if ignored:** The gap between "tested in isolation" and "actually works when someone runs it" is exactly where products fail silently — path assumptions, permission issues, and first-run UX problems that no unit test catches.
- **Update, 2026-07-23 — still OPEN.** C1 is now delivered (above), which unblocks this, but does not itself satisfy it: C1's own Product Acceptance Test deliberately ran against an isolated QA sandbox copy of the repository (`/sessions/.../qa_sandbox/repo/`), never the real, mounted `Database/`/`Runtime/` — the same disciplined test-isolation this project has required since Module 07's own UAT test-isolation defect. `Database/Metadata/metadata_store.json` is still `[]`. This remains the recommended next action, sequenced immediately after C1's closure.

**C3 — No autonomous classification/metadata provider (TD-01).**
- **Problem:** Every judgment-dependent file (most real-world content) requires a live Claude session answering classification/extraction questions in real time. There is no standalone way to run this unattended.
- **Impact:** "Scheduled mode" is documented as supported but is not meaningfully usable — the moment it hits an ambiguous file with no live session present, that file silently becomes `Category.UNKNOWN` rather than being correctly classified. This is the single largest gap between "engine" and "product."
- **Evidence:** `TECHNICAL_DEBT_REGISTER.md` TD-01; confirmed structurally in `classify_batch()`'s provider-dependency design.
- **Recommended solution:** Do not build this next (see "What should never be built yet," below) — but name it clearly as the actual ceiling on this product's ambition until it's addressed.
- **Estimated effort:** Large (a genuine new subsystem, not a patch).
- **Priority:** P1 — sequenced deliberately after the v0.9/v0.95 foundation work, not before.
- **Risk if ignored:** None immediate — this is already correctly deferred. The risk is deferring it silently *after* v1.0 ships with an implicit promise of autonomy the software can't keep.

**C4 — No human-approval delivery mechanism (TD-02, Module 07's Open Decision OD-3).**
- **Problem:** `approval_required` and `review_required` files have no interface of any kind. A human's only way to review a batch is raw chat conversation or hand-editing JSON.
- **Impact:** The entire safety model this project is proudest of — "never act with full autonomy on uncertain calls" — currently has no real mechanism for the human half of that promise to happen conveniently. It works today only because every real session so far has had a Claude agent mediating it conversationally.
- **Evidence:** `TECHNICAL_DEBT_REGISTER.md` TD-02; `Module 07 Design.md` OD-3, never resolved; confirmed no reviewable artifact exists anywhere in `Runtime/`.
- **Recommended solution:** Start with the smallest thing that could work — a generated, human-editable file (e.g. a markdown or CSV table of pending decisions someone edits and re-feeds back in) — not a GUI. This is explicitly named in the project's own `PRODUCT_ROADMAP.md` as the right minimum bar, and that's correct.
- **Estimated effort:** Medium.
- **Priority:** P0, immediately after C1.
- **Risk if ignored:** Without this, every real batch requires an AI agent in the loop indefinitely — the product never becomes usable by someone without one.
- **Update, 2026-07-23 — partially resolved.** C1's `execute` command now includes a real interactive approval prompt (approve/edit/reject/skip per `approval_required` record) — a concrete, repeatable mechanism for the *attended* case, first resolution OD-3 has ever received. The *unattended* case this finding also names (a decision source with no human at a terminal) remains exactly as open as before; see `TECHNICAL_DEBT_REGISTER.md` TD-02.

### HIGH

**H1 — Dependency manifests are broken and contradictory.**
- **Problem:** `requirements.txt` pins `PyYAML` to two different versions in the same file; `src/requirements.txt` is a stale, unpinned duplicate that still describes itself as a pre-implementation scaffold.
- **Impact:** `pip install -r requirements.txt` has undefined/last-wins behavior on the duplicate pin; anyone reading `src/requirements.txt` instead gets no version guarantees at all. First install experience is broken today.
- **Evidence:** Direct read of both files, this session.
- **Recommended solution:** One authoritative, pinned `requirements.txt` at the root; delete or clearly mark `src/requirements.txt` as historical.
- **Estimated effort:** Trivial (minutes).
- **Priority:** P0 — cheapest real fix in this entire document.
- **Risk if ignored:** Embarrassing, avoidable first-run failure for anyone who actually tries to install this.
- **Update, 2026-07-26 — FIXED.** Found still present while writing the beta installation guide (post-Engineering-Freeze; fixable under the freeze's own "Critical/High only" rule) and confirmed as a genuine, currently-reproducing hard failure, not the "undefined/last-wins" behavior originally guessed — modern `pip` (22.0.2, tested directly) refuses to install two conflicting pins for the same package at all (`ResolutionImpossible`). Fixed by removing the stale `PyYAML==6.0.1` duplicate line, keeping `PyYAML==6.0.3`; confirmed a clean single-package install succeeds afterward. `src/requirements.txt` (the second, unpinned, self-described-as-stale manifest referenced in H2 below) was not deleted — deleting real project history isn't this vault's convention — but was given a clear header marking it historical/not-the-install-source-of-truth, pointing installers at the root file. Full regression suite 889/889, unaffected. See `CHANGELOG.md`'s matching 2026-07-26 entry.

**H2 — No packaging, installer, or CI.**
- **Problem:** No `pyproject.toml`/`setup.py`, no install script, no automated test/lint pipeline on push.
- **Impact:** "Install" today means manually cloning, guessing which requirements file to use, and running a bare Python module. Regressions are only caught if someone remembers to run pytest by hand.
- **Evidence:** Direct filesystem search, this session — none found.
- **Recommended solution:** A minimal `pyproject.toml` (even without PyPI publishing) plus a basic CI workflow (run pytest on push) — cheap, high-leverage, standard practice this project has otherwise held itself to a much higher bar than.
- **Estimated effort:** Small.
- **Priority:** P1.
- **Risk if ignored:** No safety net against silent regression once more than one person touches this code; every "729/729 passing" claim depends on someone remembering to run it by hand.

**H3 — Undo has never been tested against real, executed content.**
- **Problem:** `undo_batch()`/`undo_single_action()` are unit- and integration-tested, but never exercised against genuinely real, previously-executed files.
- **Impact:** The project's single most safety-critical reversibility guarantee — the entire justification for trusting `auto`-tier automation — is unverified in the one scenario that actually matters.
- **Evidence:** `PROJECT_BACKLOG.md` item A2, still Active/unresolved; `PROJECT_REVIEW_BOARD_REPORT.md` names this as a blocking precondition for any upgrade beyond "Limited Production."
- **Recommended solution:** Exactly what's already scoped — replay undo against Run 003's 14 real, already-executed files. Data already exists; no new dataset needed.
- **Estimated effort:** Small.
- **Priority:** P0 — cheap, already scoped, blocks a real trust claim.
- **Risk if ignored:** Every future "this is safe to trust" claim rests on an assumption, not evidence.

**H4 — Real-world validation evidence remains below the project's own declared bar.**
- **Problem:** 2 sessions, 1 calendar day, ~45 files, against a self-declared requirement of ≥3 sessions / ≥2 calendar weeks / ≥150 files.
- **Impact:** Confidence in real-world behavior (including the just-shipped PT-002/PT-003 fixes) rests on a genuinely thin, temporally narrow sample.
- **Evidence:** `VALIDATION_PROGRESS.md`, `REAL_WORLD_VALIDATION_PLAN.md` §9.
- **Recommended solution:** Schedule 1–2 more real sessions, spaced across calendar time, ideally against the *actual* live installation (closing C2 at the same time).
- **Estimated effort:** Small per session; the constraint is calendar time, not engineering effort.
- **Priority:** P1.
- **Risk if ignored:** Every quality claim beyond "worked twice in one day" remains unsupported.

**H5 — No configuration; everything is hardcoded.**
- **Problem:** 12 files independently compute their own project-root path; business-rule constants live in code, not a loadable config.
- **Impact:** A second user, or the same user pointing this at a different folder, cannot configure it without editing source.
- **Evidence:** `TECHNICAL_DEBT_REGISTER.md` TD-07/TD-29/TD-30; grep-confirmed 12 files this session.
- **Recommended solution:** A single injectable config (Downloads path, destination root, a handful of tunable constants) loaded once at startup.
- **Estimated effort:** Medium.
- **Priority:** P1.
- **Risk if ignored:** This tool remains permanently single-user, single-machine, single-folder — not a distributable product by definition.
- **Update, 2026-07-23 — DELIVERED (the destination-root/settings-surface half).** `python -m src.cli init` (guided wizard) and `config --set-source`/`--set-destination` now exist, designed, reviewed, implemented, and carried through a full Product Acceptance Test (verdict: **Accepted with Minor Issues** — four new Low/Recommended findings, TD-41 through TD-44, no Critical/High). Full record: `H5_COMPLETION_REPORT.md`. Narrower than this finding's original framing: `TD-07` (hardcoded business-rule constants) and `TD-29` (injectable base paths for a second install location) were deliberately excluded from H5's scope at design time and remain open.

### MEDIUM

**M1 — Governance process is not self-enforcing.**
- **Problem:** The 13-check Pipeline Contract Verification gate is documented as mandatory at Medium+ severity (`ENGINEERING_CHANGE_PLAYBOOK.md` §6) and was skipped on both of the two most recent Medium-severity changes (PT-002, then PT-003, the very next one after the rule was written specifically to prevent this).
- **Impact:** Written process does not equal followed process. Nothing currently forces the gate to run; it depends on whoever executes closure remembering to.
- **Evidence:** `Release/VERSIONS.md` 2026-07-23 entries, both self-disclosed.
- **Recommended solution:** Turn this from a documented expectation into a literal checklist item in the closure instructions, or a scripted check, not a paragraph someone has to recall.
- **Estimated effort:** Small.
- **Priority:** P2.
- **Risk if ignored:** A third consecutive skip would make the rule meaningless in practice, regardless of how well it reads.

**M2 — Documentation volume is itself a maintainability cost.**
- **Problem:** 172 markdown files for a 9K-line codebase; closing one 3-line code change (PT-003) touched eleven documents.
- **Impact:** Real drift already happened and was caught mid-review (a stale module-version table). Every future contributor faces a steep reading requirement before touching code, and every future change carries a large documentation-consistency tax.
- **Evidence:** Direct file count, this session; the stale table found and fixed during PT-003's own closure.
- **Recommended solution:** Not a rewrite — but consider consolidating the most-frequently-touched living documents (`VERSIONS.md`, `PATTERN_TRACKER.md`, `PROJECT_BACKLOG.md`, `PROJECT_ROADMAP.md`) into fewer, more authoritative sources before this scales further, and retire truly historical documents from the "must stay consistent" set explicitly.
- **Estimated effort:** Medium (a deliberate consolidation pass, not urgent).
- **Priority:** P2.
- **Risk if ignored:** Compounds with every future change; already the largest per-change overhead in the project.

**M3 — No log rotation.**
- **Problem:** `action_log.jsonl` grows unboundedly, by design, with no rotation or archival mechanism.
- **Impact:** Harmless today (real usage is zero, per C2); becomes a real problem after a year of actual use.
- **Evidence:** `TECHNICAL_DEBT_REGISTER.md` TD-05; no rotation code found anywhere in `src/`.
- **Recommended solution:** Simple date- or size-based rotation, deferred until real usage exists to size the problem against.
- **Estimated effort:** Small.
- **Priority:** P2 (v0.95, not urgent).
- **Risk if ignored:** Low near-term, real long-term.

**M4 — Unvalidated performance at real scale.**
- **Problem:** JSON storage with linear-scan lookups (`lookup_phash_matches`, `lookup_name_matches`, `find_by_current_path`) has only been exercised against small (tens to low hundreds of files) datasets.
- **Impact:** Unknown behavior at a real, multi-year Downloads folder's actual scale (potentially thousands of files).
- **Evidence:** `TECHNICAL_DEBT_REGISTER.md` TD-03/04/06.
- **Recommended solution:** A real performance test at 1,000+ files before promising anything beyond current scope; SQLite migration only if that test shows a real problem, not preemptively.
- **Estimated effort:** Small (the test); Large (the migration, if actually needed).
- **Priority:** P2.
- **Risk if ignored:** Unknown — could be fine, could degrade badly; the honest answer today is nobody knows.

**M5 — Two disclosed, real residual risks in the most recently shipped fix.**
- **Problem:** PT-003's correction carries two named, accepted trade-offs (R1: certain genuine version chains go undetected; R6: a narrow false-positive shape remains theoretically possible) plus a separate, unrelated, never-tested exposure in `resolve_precedence()` (a false version pairing on a non-`review_required` file would auto-archive without human review).
- **Impact:** All disclosed, none blocking, but all real and currently unmeasured against any dataset.
- **Evidence:** `PT003_POSTMORTEM.md` §8; `Release/Module04/KNOWN_LIMITATIONS.md`.
- **Recommended solution:** Fold into the next real-world validation pass (H4) rather than a dedicated cycle.
- **Estimated effort:** N/A (observation, not a task on its own).
- **Priority:** P2.
- **Risk if ignored:** Low — genuinely narrow, disclosed, and monitored.

### LOW

**L1 — Weekly Summary shows misleading all-zero totals for the current, still-open day.**
Correct behavior (the current UTC day is deliberately excluded from week-to-date rollup), confusing presentation. Already scoped in `PROJECT_BACKLOG.md` as trivial. **Effort:** Small. **Priority:** P3.

**L2 — Naming sanitization has a cosmetic Title_Case quirk** (`NDA` → `Nda`). Accepted, disclosed, no real-world complaint yet. **Effort:** Small. **Priority:** P3/Future.

**L3 — `Documents/` has no subfolder taxonomy.** Deliberate v1 scope boundary, correctly deferred. **Priority:** Future.

### FUTURE (correctly out of scope right now — listed for completeness, not urgency)

- Watch Folder / real-time daemon mode.
- Multi-source support (Desktop, Google Drive, OneDrive, Dropbox).
- Active learning from `Database/Learning/User Corrections.json` (captured since Module 07 shipped, never read back).
- SQLite migration (pending M4's actual evidence).
- Desktop GUI.

---

## What should NEVER be built (until its precondition is real)

- **A real-time Watch Folder daemon**, before Scheduled mode means anything. Building a background watcher to feed a pipeline that still silently degrades on any ambiguous file (C3) is solving the wrong layer of the problem first.
- **SQLite / storage migration**, before M4's own performance test shows an actual problem. This project has correctly resisted this so far; don't reverse that discipline without evidence.
- **Multi-source support**, before single-source (Downloads) has ever been run against its own real environment (C2) or configured for a second context (H5). Widening scope before the narrow case is proven is how half-finished breadth accumulates.
- **A general-purpose "AI judgment" provider** that does more than the narrowly-scoped classification/metadata fallback TD-01 actually calls for. The discipline this project has shown — deterministic where possible, judgment only where genuinely required — is a real strength; don't trade it for a bigger, vaguer autonomous system.
- **A full desktop GUI**, before the Human Review Queue (C4) proves out what the review interaction actually needs to look like. Building a GUI on top of an unproven interaction model risks building the wrong GUI.

---

## Roadmap

### v0.9 — Make it usable by a human, safely, once
- **A real, complete CLI entry point** (C1) — subcommands wrapping the existing, already-tested pipeline functions, including a real pause-for-approval step. No new pipeline logic.
- **Human Review Queue** (C4) — the smallest concrete artifact that replaces raw chat: a generated, human-editable file.
- **Configuration** (H5) — injectable Downloads path, destination root, tunable constants.
- **Dependency/installer fix** (H1, H2) — one authoritative `requirements.txt`, a minimal `pyproject.toml`, basic CI.
- **README/ROADMAP staleness fix** (TD-28) — trivial, do it in the same pass as C1.
- **Undo validation against real content** (H3, A2) — cheap, already scoped.
- **First real run against the live installation** (C2) — immediately once C1 exists.

### v0.95 — Prove it, then make it durable
- **Real-world validation to the project's own declared bar** (H4/A4) — ≥3 sessions, ≥2 calendar weeks, ≥150 files, including runs against the now-real live installation.
- **Performance validation at real scale** (M4) — 1,000+ files, decide on SQLite with evidence, not speculation.
- **Log rotation** (M3).
- **Governance self-enforcement fix** (M1) — make the PCV gate un-skippable, not just documented.
- **Metrics** — turn the existing Duplicate/Storage reports into a real trend view now that repeat real runs will exist to compare.

### v1.0 — Make it a product
- **Autonomous classification/metadata provider** (C3/TD-01) — the actual precondition for Scheduled mode meaning anything.
- **Desktop UI**, built on top of a Review Queue interaction model that's by now been proven out in v0.9/v0.95.
- **Release Candidate hardening** — a real data-handling/privacy policy (this tool reads the content of financial documents and contracts — that needs to exist before a second person's real folder is ever touched), crash reporting, a support channel.

---

## The single most important feature to build next

**A real, complete CLI entry point — one command surface that runs the full pipeline end-to-end, including a genuine pause for human approval, execute, and report — replacing the current partial, import-time-only chain.**

Not the Human Review Queue. Not configuration. Not the installer. Those all matter, and all sit right behind this in the v0.9 list — but every one of them is unreachable, untestable, and unusable without this first. You cannot build a meaningful review-queue interaction, validate undo against real content, run the first real end-to-end pass against the live installation, or even honestly demonstrate this software to a second person, when the only documented way to run it stops silently in the middle of the pipeline and leaves the rest as an exercise for someone reading the source.

It is also, deliberately, the cheapest possible high-leverage fix in this entire review: every function it needs already exists, is already tested, and is already correct. This is wiring, not invention — exactly the kind of change this review's own mandate says to prefer ("do NOT invent new architecture"). It carries essentially none of the risk that C3 (autonomous provider) or a GUI would carry, and it is the one change that makes every other item on this list — Review Queue, Undo validation, real dogfooding, the next real-world validation session — actually possible to do at all, instead of theoretically scoped.

If 60 days are all that's available: this is week one. Everything else on the v0.9 list becomes strictly easier, more testable, and more honest to build once it exists.

**Update, 2026-07-23 — this recommendation was acted on and is now closed.** C1 shipped, was reviewed, audited, and Product-Acceptance-Tested (verdict: Accepted with Major Issues); full record in `C1_COMPLETION_REPORT.md`. Its own PAT independently arrived at the same next-step logic this section already argued for: the single highest-leverage remaining item is **Configuration (H5)** — the PAT's U5 finding ("no `init`/`configure` command") is a concrete implementation of H5, and the PAT explicitly characterizes it as the item that would "materially reduce the practical impact of [three other findings] at once by preventing the unconfigured state from being reached unguided in the first place." That is the same "make everything else easier" logic this section applied to C1 itself. See `Build-out/09 CLI & Product Interface/C1 Findings Classification & Release Planning Matrix.md` (U5) for the full reasoning.

**Update, 2026-07-23 (later same day) — H5 is also now closed.** `init`/`config --set-*` shipped, were reviewed, audited, and Product-Acceptance-Tested (verdict: Accepted with Minor Issues, no Critical/High findings); full record in `H5_COMPLETION_REPORT.md`. With both C1 and C4's attended case (via C1's `execute` prompt) and H5 now delivered, this document's own C2 finding ("Zero real dogfooding," above) is the strongest-evidenced remaining Critical item — it was always sequenced as "the very first thing that happens after C1 ships," and is now doubly unblocked: a real CLI exists (C1) and a real, guided way to point it at an actual folder exists (H5), with no engineering work of any kind required to attempt it. See `H5_COMPLETION_REPORT.md`'s own recommendation for the full reasoning.

---

**Per the requested workflow: this is the end of Steps 1–3. No implementation has begun. Waiting for approval before proceeding.**
