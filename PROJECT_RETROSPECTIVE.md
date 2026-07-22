# Project Retrospective — Downloads Intelligence, Pipeline v0.8.0

**Date:** 2026-07-20
**Scope:** Module 01 (Watch & Ingest) through Module 08 (Logging & Reporting) — the complete v1 engine.
**Purpose:** A phase-boundary review, written at the moment engineering work stops and product work begins. This document looks backward only; forward-looking decisions live in `PRODUCT_ROADMAP.md` and `VERSION_09_PLAN.md`.

---

## 1. What was built

Downloads Intelligence is an eight-stage pipeline that turns a flat, messy Downloads folder into a classified, renamed, deduplicated, version-checked, human-approved, and fully logged filing system. Every stage is real, working Python code, not a design document:

| # | Module | What it does | Version | Status |
|---|---|---|---|---|
| 01 | Watch & Ingest | Discovers new files, waits for write-stability, builds the permanent `file_id`/`FileRecord` model | 1.0.1 | Released |
| 02 | Classification | Determines what a file *is* (11-category taxonomy) — deterministic rules first, live-Claude-judgment fallback for ambiguous content | 1.0.0 | Released |
| 03 | Metadata Extraction | Pulls structured fields (vendor, dates, amounts, names) out of classified content | 1.0.0 | Released, permanently frozen |
| 04 | Duplicate & Version Detection | Catches exact duplicates (content hash), near-duplicate images (perceptual hash), and version chains (`Resume_v8` vs. `v9`) | 1.0.0 | Released, permanently frozen |
| 05 | Naming & Destination | Generates a consistent filename and suggests a destination folder per category | 1.0.0 | Released |
| 06 | Confidence & Review | Scores every suggestion with an auditable, points-based deduction system and assigns a tier | 1.0.0 | Released, permanently frozen |
| 07 | Preview, Approval & Execution | Shows the batch for human approval, moves/renames approved files, logs everything reversibly, supports undo | 1.0.0 | Released |
| 08 | Logging & Reporting | Turns the cumulative log into human-readable Daily/Weekly Summaries and Duplicate/Storage Reports | 1.0.0 | Released |

**By the numbers, as of this release:**

- **~20,200 lines of source code** (`src/`), of which roughly **11,350 lines are tests** — the test suite is larger than the implementation it verifies.
- **716 automated unit tests, 716 passing** — zero known failures, zero skipped, at the moment of every module's release.
- **67 dated `CHANGELOG.md` entries** documenting every design decision, correction, and release across the project's lifetime.
- **9 Governance documents, 32 Build-out design documents, 70 Release documents, 15 Test plans, 5 Rules documents** — the process-documentation footprint is, by a wide margin, larger than the code it governs.
- **31 recorded Architecture Decisions**, each with a stated rationale and consequence, none silently reversed.
- **Zero Critical or High findings** reached a released module without being fixed before release. **Zero Critical/High/Medium findings of any kind** were found at any stage of Module 08's entire lifecycle — the cleanest release record of the eight.

## 2. How it was built

Every one of the eight modules passed through the same nine-stage lifecycle defined in `Governance/ENGINEERING_STANDARD.md`: **Design → independent Design Review → Freeze → Implementation → Independent Implementation Audit → Integration Testing → User Acceptance Testing → Independent Release Audit + Pipeline Contract Verification → Release.** No module skipped a stage, and no stage was self-certified — every design, every implementation, and every release was independently re-verified against real code or a real running system before being signed off, per the project's standing rule that findings are classified by severity and never fixed without explicit approval.

This discipline caught real problems before they shipped: a contradiction in Module 06's confidence formula stopped implementation mid-stream; Module 04's UAT was restarted from Run 1 after a design gap in perceptual-hash category scoping was found; Module 07's first Release Audit attempt correctly refused to certify on unit tests alone and named the missing Integration Testing/UAT as a blocking finding rather than rubber-stamping; a Module 01 post-freeze defect was found, patched, and re-verified against the Frozen Module Change Policy rather than silently edited. The project's own history file (`CHANGELOG.md`) and its "never rewrite history" convention mean this record is auditable end to end — every correction is visible as a dated addendum, not a retroactive edit.

The trade-off is explicit and worth naming plainly: this is an extraordinarily well-verified **engine**, built at a pace and rigor more typical of a safety-critical or compliance-driven system than a personal productivity tool. That rigor is why the retrospective below can make confident, evidence-backed claims about what works — but it also means the project has spent eight modules' worth of effort on correctness and almost none on the experience of actually using the thing day to day.

## 3. What "done" actually means here

Every module is released, tested, and audited — but **released** in this project means "independently verified against its own written contract," not "running against a real Downloads folder in daily use." Per `CLAUDE.md`: *"This vault is the build/planning workspace, not the user's real Downloads folder."* No module in this pipeline has ever processed a real, unstaged, everyday Downloads folder. Every UAT run to date used a purpose-built external test folder with curated realistic files, not the messy, unpredictable reality the product is meant to solve.

This is not a criticism of the engineering process — building and proving the engine against controlled conditions first, before pointing it at irreplaceable real files, is the right order of operations for a tool whose first non-negotiable rule is "never permanently delete anything." But it does mean the project has not yet answered its own founding question: does this actually make someone's Downloads folder better? That question is the subject of `PRODUCT_ROADMAP.md`.

## 4. Strengths worth carrying forward

- **Reversibility is real, not aspirational.** Every move is logged with enough detail to undo it; there is no delete path anywhere in the pipeline. This is the single most trust-critical property of a tool that touches a user's real files, and it was verified end-to-end in Module 07's UAT, not just asserted in design.
- **Confidence scoring is auditable.** A user (or a future support engineer) can trace exactly why a file scored 82 instead of 95 — it is a deduction list, not an opaque AI-reported percentage. This will matter enormously for user trust once real people are looking at real scores.
- **Ownership boundaries are unusually clean.** Module 08, for instance, owns zero `FileRecord` fields and modifies nothing — verified, not assumed, during its Release Audit. This kind of discipline is why the pipeline has stayed maintainable through eight modules without needing a rewrite.
- **The documentation is the project's real asset.** Every disclosed limitation, deferred decision, and accepted risk is written down, dated, and attributed. This retrospective and the technical debt register that follows it were possible to write faithfully *because* the project kept this record — most projects at this stage have far less to go on.

## 5. Where the story changes from here

Modules 01–08 answered "can this pipeline classify, file, and report on downloads correctly and safely?" — and the answer, independently verified eight times over, is yes. The next phase asks a different question entirely: "will a real person actually use this, and does it make their life better?" That question cannot be answered by more unit tests or another independent audit. It requires running the thing for real, watching where it's annoying, and building the parts of a *product* — interface, autonomy, distribution, trust signals — that an engine alone does not provide.

See `PRODUCT_ROADMAP.md` for the gap analysis and prioritized plan, `TECHNICAL_DEBT_REGISTER.md` for every open item consolidated from eight modules' worth of disclosed limitations, and `VERSION_09_PLAN.md` for the recommended next milestone.
