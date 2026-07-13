# Project Roadmap — Downloads Intelligence Pipeline

Pipeline build status, one page. For *feature* roadmap (Version 2/3 ideas, future capabilities), see the top-level `ROADMAP.md` — that document is scope, this one is progress.

```
Pipeline Version:     0.6.0
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

## Current module

**Module 07 (Preview, Approval & Execution) — implementation complete (WP-1–13); Release Audit BLOCKED.** Module 06 is released (`Release/Module06/`). Module 07's design was frozen 2026-07-12 after three independent design review rounds. All twelve implementation work packages (WP-1–12: foundational data structures through CLI wiring) plus WP-13's documentation follow-ups and release-engineering package are now complete — full regression suite 568/568, zero unresolved Critical/High/Medium findings from the implementation lifecycle itself (`Release/Module07/IMPLEMENTATION_AUDIT.md`). A formal Release Audit was performed and found one blocking High finding: **Integration Testing and UAT have never been performed against the real Module 01→07 chain**, a hard requirement under this document's own "Non-negotiables" section below — no measured performance number exists either (PCV check 12). The audit stopped at this finding rather than certifying release-ready; Module 07 is not yet released (still version `—`). See `Release/Module07/RELEASE_AUDIT.md` for the full record and `Release/VERSIONS.md` for the authoritative version ledger.

## Remaining modules

| # | Module | Status |
|---|---|---|
| 07 | Preview, Approval & Execution | Implementation Complete (WP-1–13) — Release Audit BLOCKED (Integration Testing/UAT pending) |
| 08 | Logging & Reporting | Not started — blocked on Module 07's own release |

## Major milestones

- ✅ Design phase complete for the whole pipeline (`Build-out/00–08`, pre-implementation).
- ✅ Module 01 (Watch & Ingest) shipped — first real code, permanent `file_id` model, action log established.
- ✅ Module 02 (Classification) shipped — Engine/Provider pattern established, live-Claude-judgment model proven end-to-end.
- ✅ Module 03 (Metadata Extraction) shipped — closed metadata taxonomy, structural redaction, four-tier timestamp hierarchy.
- ✅ **Engineering governance established** (`Governance/ENGINEERING_STANDARD.md`, `ARCHITECTURE_DECISIONS.md`, this document, `PIPELINE_CONTRACT_VERIFICATION.md`) — formalizing the process the first three modules were already built under, before Module 04 begins.
- ✅ Module 04 (Duplicate & Version Detection) shipped — first module to depend on `content_hash` for its actual stated purpose; fully deterministic, no provider.
- ✅ Module 05 (Naming & Destination) shipped — first consumer of Module 03's full metadata taxonomy; fully deterministic, no provider, the same architectural departure Module 04 established for itself. The `Rules/Naming Rules.md` field-name alignment flagged in `Release/Module03/KNOWN_LIMITATIONS.md` has been resolved (`Module 05 Design.md` §10).
- ✅ Module 06 (Confidence & Review) shipped — first consumer of `Rules/Confidence Rules.md`'s deduction formula against real `extracted_metadata`/`classification_signals` data; fully deterministic, no provider, the narrowest attack surface of any module built so far. UAT restarted at Run 2 after a Module 01 post-freeze correction; Release Audit resolved three genuine documentation/evidence findings across three restart cycles before converging clean.
- 🔒 Module 07 (Preview, Approval & Execution) — implementation complete (WP-1–13, 2026-07-13), Release Audit BLOCKED on missing Integration Testing/UAT. First module to actually move/rename files and implement undo. Release engineering package generated (`Release/Module07/`); not yet released.
- ⬜ Module 08 (Logging & Reporting) — Daily/Weekly Summary and Duplicate/Storage Report generation.
- ⬜ **Pipeline v1.0.0** — all 8 modules built, tested, and passing end-to-end against a real Downloads folder.

## Version milestones

| Pipeline Version | Meaning |
|---|---|
| 0.1.0 | Module 01 released |
| 0.2.0 | Module 02 released |
| 0.3.0 | Module 03 released |
| 0.4.0 | Module 04 released |
| 0.5.0 | Module 05 released |
| **0.6.0** | **Module 06 released (current)** |
| 0.7.0 | Module 07 released (projected) |
| 0.8.0 | Module 08 released (projected) |
| 1.0.0 | All 8 modules built and passing end-to-end — the deliberate, meaningful milestone (not an automatic function of module count) |

## Expected pipeline completion

No fixed calendar date — each module has taken roughly one working session (design through release) at the pace observed for Modules 01–03, with each module's real audit/testing burden growing modestly as the pipeline grows (more upstream contracts to verify against). At the observed pace, 2 remaining modules suggests the pipeline is roughly two module-cycles from v1.0.0, but this is a rough extrapolation, not a committed date — each module's actual design complexity varies (Module 07's undo/execution logic and Module 08's reporting are both expected to be more involved than Module 04's).

## Non-negotiables carried into every remaining module

Never permanently delete anything; every action must be reversible; superseded versions/duplicates get archived, not deleted (`CLAUDE.md`). Every module follows the full lifecycle in `Governance/ENGINEERING_STANDARD.md` — design → review → freeze → implement → audit → integration test → UAT → audit → release — with no stage skipped and no finding fixed without explicit approval.
