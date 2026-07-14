# Project Roadmap — Downloads Intelligence Pipeline

Pipeline build status, one page. For *feature* roadmap (Version 2/3 ideas, future capabilities), see the top-level `ROADMAP.md` — that document is scope, this one is progress.

```
Pipeline Version:     0.7.0
Last updated:         2026-07-13
```

## Released modules

| # | Module | Version | Status |
|---|---|---|---|
| 01 | Watch & Ingest | 1.0.1 | Released — patched (post-freeze correction #1, 2026-07-11; see `Release/Module01/RELEASE_NOTES.md`) |
| 02 | Classification | 1.0.0 | Released |
| 03 | Metadata Extraction | 1.0.0 | Released — **permanently frozen** |
| 04 | Duplicate & Version Detection | 1.0.0 | Released — **permanently frozen** |
| 05 | Naming & Destination | 1.0.0 | Released |
| 06 | Confidence & Review | 1.0.0 | Released — **permanently frozen** |
| 07 | Preview, Approval & Execution | 1.0.0 | Released |

## Current module

**Module 08 (Logging & Reporting) — Design Frozen — Not Implemented.** Status updated from "Not started" to "Design Frozen — Not Implemented (frozen 2026-07-14)." Module 08's design (`Build-out/08 Logging & Reporting/Module 08 Design.md`) completed four independent design review rounds (`Module 08 Design Review.md`), resolved four Medium findings (M1–M4), five Low and two Cosmetic findings (L1–L3, N1–N2, C1–C2), and two further Low findings (N3–N4, both mis-cited Architecture Decision references) across three corrective/cleanup/citation-correction passes, converging on zero remaining Critical/High/Medium/Low findings and zero unresolved Cosmetic findings. The project owner explicitly approved freezing the design, distinct from the review itself — see `Module 08 Design Review.md`'s "Freeze Record (2026-07-14)" section and `CHANGELOG.md`'s matching entry for full detail. No implementation code exists; Modules 01–07 remain untouched and permanently frozen. The five Open Decisions (OD-1 through OD-5) and two required documentation follow-ups (§25) are carried forward unresolved. Implementation requires its own separate, explicit future approval (Implementation Planning, then WP-0) before it begins.

Module 07 (Preview, Approval & Execution) remains released at v1.0.0 (`Release/Module07/`). Its design was frozen 2026-07-12 after three independent design review rounds; all twelve implementation work packages plus WP-13's release-engineering package completed with full regression suite 568/568 and zero unresolved Critical/High/Medium findings from the implementation lifecycle itself. A first Release Audit found one blocking High finding — Integration Testing and UAT had never been performed against the real Module 01→07 chain — and, per this document's own "Non-negotiables" section below, stopped rather than certifying release-ready. Both stages were then executed: Integration Testing (`Tests/Module 07 Integration Test Plan.md`, 71/71 checks, zero findings) and UAT (`Tests/Module 07 UAT Plan.md`, real external folders, real live judgment, real project `Database`/`Runtime`, zero findings), plus the required performance measurement (40.116s/75 files, no regression against Module 06's 40.122s baseline). A Medium test-isolation defect in the regression suite itself was found, reported, and resolved before UAT began. The Release Audit was re-run fresh and certified Module 07 release-ready — all 24 Architecture Decisions, G1–G10, NG1–NG7, I1–I8, and all 13 Pipeline Contract Verification checks pass. See `Release/Module07/RELEASE_AUDIT.md` for the full record and `Release/VERSIONS.md` for the authoritative version ledger.

## Remaining modules

| # | Module | Status |
|---|---|---|
| 08 | Logging & Reporting | Design Frozen — Not Implemented |

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
- ⬜ Module 08 (Logging & Reporting) — Daily/Weekly Summary and Duplicate/Storage Report generation. **Design Frozen — Not Implemented (2026-07-14)**; implementation not yet begun.
- ⬜ **Pipeline v1.0.0** — all 8 modules built, tested, and passing end-to-end against a real Downloads folder.

## Version milestones

| Pipeline Version | Meaning |
|---|---|
| 0.1.0 | Module 01 released |
| 0.2.0 | Module 02 released |
| 0.3.0 | Module 03 released |
| 0.4.0 | Module 04 released |
| 0.5.0 | Module 05 released |
| 0.6.0 | Module 06 released |
| **0.7.0** | **Module 07 released (current)** |
| 0.8.0 | Module 08 released (projected) |
| 1.0.0 | All 8 modules built and passing end-to-end — the deliberate, meaningful milestone (not an automatic function of module count) |

## Expected pipeline completion

No fixed calendar date — each module has taken roughly one working session (design through release) at the pace observed for Modules 01–03, with each module's real audit/testing burden growing modestly as the pipeline grows (more upstream contracts to verify against). At the observed pace, 1 remaining module (08) suggests the pipeline is roughly one module-cycle from v1.0.0, but this is a rough extrapolation, not a committed date — Module 08's reporting logic is a new kind of read-only aggregation work this pipeline hasn't done before, so its actual complexity is not yet well-calibrated against the modules built so far.

## Non-negotiables carried into every remaining module

Never permanently delete anything; every action must be reversible; superseded versions/duplicates get archived, not deleted (`CLAUDE.md`). Every module follows the full lifecycle in `Governance/ENGINEERING_STANDARD.md` — design → review → freeze → implement → audit → integration test → UAT → audit → release — with no stage skipped and no finding fixed without explicit approval.
