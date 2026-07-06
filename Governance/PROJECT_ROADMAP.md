# Project Roadmap — Downloads Intelligence Pipeline

Pipeline build status, one page. For *feature* roadmap (Version 2/3 ideas, future capabilities), see the top-level `ROADMAP.md` — that document is scope, this one is progress.

```
Pipeline Version:     0.3.0
Last updated:         2026-07-06
```

## Released modules

| # | Module | Version | Status |
|---|---|---|---|
| 01 | Watch & Ingest | 1.0.0 | Released |
| 02 | Classification | 1.0.0 | Released |
| 03 | Metadata Extraction | 1.0.0 | Released — **permanently frozen** |

## Current module

None in progress. Module 03 is frozen; Module 04 has not yet begun (`Governance/ENGINEERING_STANDARD.md` and this roadmap are being established first, at the project owner's direction, before Module 04's design phase starts).

## Remaining modules

| # | Module | Status |
|---|---|---|
| 04 | Duplicate & Version Detection | Not started |
| 05 | Naming & Destination | Not started |
| 06 | Confidence & Review | Not started |
| 07 | Preview, Approval & Execution | Not started |
| 08 | Logging & Reporting | Not started |

## Major milestones

- ✅ Design phase complete for the whole pipeline (`Build-out/00–08`, pre-implementation).
- ✅ Module 01 (Watch & Ingest) shipped — first real code, permanent `file_id` model, action log established.
- ✅ Module 02 (Classification) shipped — Engine/Provider pattern established, live-Claude-judgment model proven end-to-end.
- ✅ Module 03 (Metadata Extraction) shipped — closed metadata taxonomy, structural redaction, four-tier timestamp hierarchy.
- ✅ **Engineering governance established** (`Governance/ENGINEERING_STANDARD.md`, `ARCHITECTURE_DECISIONS.md`, this document, `PIPELINE_CONTRACT_VERIFICATION.md`) — formalizing the process the first three modules were already built under, before Module 04 begins.
- ⬜ Module 04 (Duplicate & Version Detection) — first module to depend on `content_hash` for its actual stated purpose.
- ⬜ Module 05 (Naming & Destination) — first consumer of Module 03's full metadata taxonomy; will need to resolve the `Rules/Naming Rules.md` field-name alignment flagged in `Release/Module03/KNOWN_LIMITATIONS.md`.
- ⬜ Module 06 (Confidence & Review) — first consumer of `Rules/Confidence Rules.md`'s deduction formula against real `extracted_metadata`/`classification_signals` data.
- ⬜ Module 07 (Preview, Approval & Execution) — first module to actually move/rename files and implement undo.
- ⬜ Module 08 (Logging & Reporting) — Daily/Weekly Summary and Duplicate/Storage Report generation.
- ⬜ **Pipeline v1.0.0** — all 8 modules built, tested, and passing end-to-end against a real Downloads folder.

## Version milestones

| Pipeline Version | Meaning |
|---|---|
| 0.1.0 | Module 01 released |
| 0.2.0 | Module 02 released |
| **0.3.0** | **Module 03 released (current)** |
| 0.4.0 | Module 04 released (projected) |
| 0.5.0 | Module 05 released (projected) |
| 0.6.0 | Module 06 released (projected) |
| 0.7.0 | Module 07 released (projected) |
| 0.8.0 | Module 08 released (projected) |
| 1.0.0 | All 8 modules built and passing end-to-end — the deliberate, meaningful milestone (not an automatic function of module count) |

## Expected pipeline completion

No fixed calendar date — each module has taken roughly one working session (design through release) at the pace observed for Modules 01–03, with each module's real audit/testing burden growing modestly as the pipeline grows (more upstream contracts to verify against). At the observed pace, 5 remaining modules suggests the pipeline is roughly five module-cycles from v1.0.0, but this is a rough extrapolation, not a committed date — each module's actual design complexity varies (Module 07's undo/execution logic and Module 08's reporting are both expected to be more involved than Module 04's).

## Non-negotiables carried into every remaining module

Never permanently delete anything; every action must be reversible; superseded versions/duplicates get archived, not deleted (`CLAUDE.md`). Every module follows the full lifecycle in `Governance/ENGINEERING_STANDARD.md` — design → review → freeze → implement → audit → integration test → UAT → audit → release — with no stage skipped and no finding fixed without explicit approval.
