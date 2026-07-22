# Project Roadmap — Downloads Intelligence Pipeline

Pipeline build status, one page. For *feature* roadmap (Version 2/3 ideas, future capabilities), see the top-level `ROADMAP.md` — that document is scope, this one is progress.

```
Pipeline Version:     0.8.0
Last updated:         2026-07-20
```

## Released modules

| # | Module | Version | Status |
|---|---|---|---|
| 01 | Watch & Ingest | 1.0.1 | Released — patched (post-freeze correction #1, 2026-07-11; see `Release/Module01/RELEASE_NOTES.md`) |
| 02 | Classification | 1.0.1 | Released — patched (post-freeze correction, PT-002, 2026-07-23; see `Release/Module02/RELEASE_NOTES.md`) |
| 03 | Metadata Extraction | 1.0.0 | Released — **permanently frozen** |
| 04 | Duplicate & Version Detection | 1.0.1 | Released — patched (post-freeze correction #5, PT-003, 2026-07-23; see `Release/Module04/RELEASE_NOTES.md`) — **permanently frozen** architecturally (no Provider ever planned), still subject to post-freeze patches under `Governance/FROZEN_MODULE_CHANGE_POLICY.md` |
| 05 | Naming & Destination | 1.0.0 | Released |
| 06 | Confidence & Review | 1.0.0 | Released — **permanently frozen** |
| 07 | Preview, Approval & Execution | 1.0.0 | Released |
| 08 | Logging & Reporting | 1.0.0 | Released |

## Current module

None under original v1 implementation — all eight v1 modules remain individually released (Pipeline 0.8.0). Declaring Pipeline v1.0.0 itself — "all 8 modules built and passing end-to-end" — remains a separate, deliberate milestone decision for the project owner to make (`ARCHITECTURE_DECISIONS.md` decision 14), not automatically reached by Module 08's release. See "Expected pipeline completion" below.

**Current phase of work: Real-World Validation (v0.9.0), post-baseline design correction.** Since Module 08's release, the project moved through a Project Phase Review (`PROJECT_RETROSPECTIVE.md`, `TECHNICAL_DEBT_REGISTER.md`, `PRODUCT_ROADMAP.md`, `VERSION_09_PLAN.md`), then executed three real-world validation runs against genuine, uncurated content (`VALIDATION_LEDGER.md` Runs 001–003 — Run 001 blocked on an environment access gap; Run 002 executed 9 real files; Run 003 executed 36 real files with the framework's first real file execution). Findings were consolidated in `PATTERN_TRACKER.md` and tracked against the project's own pre-declared acceptance bar in `VALIDATION_PROGRESS.md`. An independent Project Review Board Report (`PROJECT_REVIEW_BOARD_REPORT.md`) then reviewed all of the above and recommended **Ready for Limited Production**, and Pipeline Version 0.8.0 was formally declared the project's **Validated Baseline** (`v0.8.0-validated-baseline`, see `Release/VERSIONS.md` "Validated Baselines"). Following the Review Board's recommendations: a read-only root-cause investigation closed PT-003's open precondition (see `VALIDATION_LEDGER.md`'s Post-Run 003 addendum), and **Design-phase work (not implementation) is now authorized and underway for PT-002 only** — `Build-out/02 Classification/Module 02 Post-Freeze Design Correction — PT-002.md`, governed by `Governance/FROZEN_MODULE_CHANGE_POLICY.md` since Module 02 is a Frozen, released module. No Module 01–08 source file has been modified during any of this — validation, root-cause investigation, and design-package preparation are all read-only/planning activities under this project's own lifecycle discipline (`ENGINEERING_STANDARD.md`: Design → Review → Freeze → Implementation, in order, each requiring separate explicit approval).

**Update, 2026-07-23 — Project Phase 4 begins.** PT-002's Design-phase work referenced above has since completed the full cycle (Design → Review → Implementation → Regression → Validation → Merge → Close) and is now CLOSED, a historical engineering record — `PT002_POSTMORTEM.md`, `ENGINEERING_CHANGE_PLAYBOOK.md` (the standing process this cycle produced for future changes). Module 02 is patched to `1.0.1` (`Release/VERSIONS.md`). The project has moved from single-finding engineering work into a Technical-Program-Management phase: a full backlog review across every remaining open item (`PATTERN_TRACKER.md`, `TECHNICAL_DEBT_REGISTER.md`, `VERSION_091_IMPLEMENTATION_PLAN.md`, `PRODUCT_ROADMAP.md`) consolidated into a single prioritized `PROJECT_BACKLOG.md`. PT-003 remains the only other Confirmed-Pattern engineering candidate from the v0.9.0 validation cycle, still unimplemented — see the backlog for its current priority.

**Update, 2026-07-23 — PT-003 closed (later same day).** PT-003, referenced immediately above as the remaining open Confirmed-Pattern candidate, has since completed the same full cycle (Design, 2 revisions → 2 rounds of independent review → Implementation → Regression (729/729) → Validation (`PT003_VALIDATION_REPORT.md`, PASS WITH NOTES) → Merge → Close) and is now CLOSED, a historical engineering record — `PT003_POSTMORTEM.md`. Module 04 is patched to `1.0.1` (`Release/VERSIONS.md`). As of this update, no `PATTERN_TRACKER.md` finding represents active, in-progress engineering work; the project's current phase remains Technical Program Management (`PROJECT_BACKLOG.md`, unaffected in its own prioritization by this closure beyond removing PT-003's row).

Module 08 (Logging & Reporting) is released at v1.0.0 (`Release/Module08/`). Its design completed four independent design review rounds (`Module 08 Design Review.md`), resolving four Medium findings (M1–M4), five Low and two Cosmetic findings (L1–L3, N1–N2, C1–C2), and two further Low citation-correction findings (N3–N4), converging on zero remaining findings of any severity, explicitly frozen 2026-07-14. The five Open Decisions carried forward at freeze (OD-1 through OD-5) were each resolved via a dedicated Architecture Decision (25–31) before or during the seven work packages (WP-1 through WP-7) that implemented the four report generators and CLI wiring, each work package independently audited on its own. An Independent Implementation Audit (RWP-A) passed with recommendations only; Integration Testing (`Tests/Module 08 Integration Test Plan.md`, RWP-B) ran a real harness against the full Module 01→08 chain and found zero defects; User Acceptance Testing (`Tests/Module 08 UAT Plan.md`, RWP-C) ran against real external folders and the real project `Database`/`Runtime` and passed with two disclosed, non-blocking observations. The Independent Release Audit and Pipeline Contract Verification gate (`Release/Module08/RELEASE_AUDIT.md`, RWP-D) then re-verified all 13 PCV checks, all 31 Architecture Decisions, and all Guarantees/Non-Guarantees/Invariants directly against real code — PASS, with one Low documentation-staleness finding found and resolved in the same pass. Module 08 released 2026-07-20 with zero Critical/High/Medium findings at any stage of its entire lifecycle — a genuine first among the eight modules. See `Release/Module08/RELEASE_SUMMARY.md` for the full record.

Module 07 (Preview, Approval & Execution) remains released at v1.0.0 (`Release/Module07/`). Its design was frozen 2026-07-12 after three independent design review rounds; all twelve implementation work packages plus WP-13's release-engineering package completed with full regression suite 568/568 and zero unresolved Critical/High/Medium findings from the implementation lifecycle itself. A first Release Audit found one blocking High finding — Integration Testing and UAT had never been performed against the real Module 01→07 chain — and, per this document's own "Non-negotiables" section below, stopped rather than certifying release-ready. Both stages were then executed: Integration Testing (`Tests/Module 07 Integration Test Plan.md`, 71/71 checks, zero findings) and UAT (`Tests/Module 07 UAT Plan.md`, real external folders, real live judgment, real project `Database`/`Runtime`, zero findings), plus the required performance measurement (40.116s/75 files, no regression against Module 06's 40.122s baseline). A Medium test-isolation defect in the regression suite itself was found, reported, and resolved before UAT began. The Release Audit was re-run fresh and certified Module 07 release-ready — all 24 Architecture Decisions, G1–G10, NG1–NG7, I1–I8, and all 13 Pipeline Contract Verification checks pass. See `Release/Module07/RELEASE_AUDIT.md` for the full record and `Release/VERSIONS.md` for the authoritative version ledger.

## Remaining modules

None. All eight v1 modules are released. See "Expected pipeline completion" below for the separate Pipeline v1.0.0 milestone decision.

## Major milestones

- ✅ Design phase complete for the whole pipeline (`Build-out/00–08`, pre-implementation).
- ✅ Module 01 (Watch & Ingest) shipped — first real code, permanent `file_id` model, action log established.
- ✅ Module 02 (Classification) shipped — Engine/Provider pattern established, live-Claude-judgment model proven end-to-end.
- ✅ Module 03 (Metadata Extraction) shipped — closed metadata taxonomy, structural redaction, four-tier timestamp hierarchy.
- ✅ **Engineering governance established** (`Governance/ENGINEERING_STANDARD.md`, `ARCHITECTURE_DECISIONS.md`, this document, `PIPELINE_CONTRACT_VERIFICATION.md`) — formalizing the process the first three modules were already built under, before Module 04 begins.
- ✅ Module 04 (Duplicate & Version Detection) shipped — first module to depend on `content_hash` for its actual stated purpose; fully deterministic, no provider.
- ✅ Module 05 (Naming & Destination) shipped — first consumer of Module 03's full metadata taxonomy; fully deterministic, no provider, the same architectural departure Module 04 established for itself. The `Rules/Naming Rules.md` field-name alignment flagged in `Release/Module03/KNOWN_LIMITATIONS.md` has been resolved (`Module 05 Design.md` §10).
- ✅ Module 06 (Confidence & Review) shipped — first consumer of `Rules/Confidence Rules.md`'s deduction formula against real `extracted_metadata`/`classification_signals` data; fully deterministic, no provider, the narrowest attack surface of any module built so far. UAT restarted at Run 2 after a Module 01 post-freeze correction; Release Audit resolved three genuine documentation/evidence findings across three restart cycles before converging clean.
- ✅ Module 07 (Preview, Approval & Execution) shipped — first module to actually move/rename files and implement undo; the pipeline's only filesystem-mutating stage. First Release Audit attempt correctly refused to certify on unit tests alone and named the missing Integration Testing/UAT as a blocking finding rather than certifying prematurely; both stages then ran clean (71/71 Integration Testing checks, zero UAT findings) against real external folders and the real project database, alongside a Medium test-isolation defect found and resolved in the regression suite itself. Release Audit re-run and certified release-ready.
- ✅ Module 08 (Logging & Reporting) shipped — Daily/Weekly Summary and Duplicate/Storage Report generation. The only module in the pipeline that owns zero `FileRecord` fields, introduces no new `Database/` structure, and adds no new action-log value; the only module with no disclosed gap between interactive and autonomous/unattended operation. Zero Critical/High/Medium findings at any stage of its entire lifecycle — a genuine first among the eight modules. Released at v1.0.0 (`Release/Module08/RELEASE_SUMMARY.md`).
- ⬜ **Pipeline v1.0.0** — all 8 modules built, tested, and passing end-to-end against a real Downloads folder. All eight modules are now individually released; this milestone itself remains a separate, deliberate declaration per `ARCHITECTURE_DECISIONS.md` decision 14, not automatically reached by Module 08's own release.

## Version milestones

| Pipeline Version | Meaning |
|---|---|
| 0.1.0 | Module 01 released |
| 0.2.0 | Module 02 released |
| 0.3.0 | Module 03 released |
| 0.4.0 | Module 04 released |
| 0.5.0 | Module 05 released |
| 0.6.0 | Module 06 released |
| 0.7.0 | Module 07 released |
| **0.8.0** | **Module 08 released (current)** |
| 1.0.0 | All 8 modules built and passing end-to-end — the deliberate, meaningful milestone (not an automatic function of module count) |

## Expected pipeline completion

All 8 modules are now individually built, tested, and released (Pipeline 0.8.0). Module 08's reporting logic — a new kind of read-only aggregation work this pipeline hadn't done before — completed its entire lifecycle (design, four review rounds, five Open Decisions resolved, WP-1 through WP-7, an integration audit, an Independent Implementation Audit, Integration Testing, UAT, and a Release Audit) with zero Critical/High/Medium findings at any stage, a genuine first among the eight modules. Declaring Pipeline v1.0.0 itself remains a separate, deliberate milestone decision for the project owner to make (`ARCHITECTURE_DECISIONS.md` decision 14), not an automatic consequence of every module being released.

## Non-negotiables carried into every remaining module

Never permanently delete anything; every action must be reversible; superseded versions/duplicates get archived, not deleted (`CLAUDE.md`). Every module follows the full lifecycle in `Governance/ENGINEERING_STANDARD.md` — design → review → freeze → implement → audit → integration test → UAT → audit → release — with no stage skipped and no finding fixed without explicit approval.
