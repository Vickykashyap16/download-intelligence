# Pipeline Dependency Diagram

Downloads Intelligence is a strictly linear v1 pipeline — each module depends on the one before it and feeds the one after. See each module's `MODULE_CONTRACT.md` (in `Release/ModuleNN/`, added starting with Module 01) for exactly what's guaranteed at each handoff, and `Release/VERSIONS.md` for how each module's version relates to the pipeline's.

```
Module01 — Watch & Ingest
      │
      ▼
Module02 — Classification
      │
      ▼
Module03 — Metadata Extraction
      │
      ▼
Module04 — Duplicate & Version Detection
      │
      ▼
Module05 — Naming & Destination
      │
      ▼
Module06 — Confidence & Review
      │
      ▼
Module07 — Preview, Approval & Execution
      │
      ▼
Module08 — Logging & Reporting
```

## Notes

- **Strictly linear in v1.** No module skips ahead or writes back into an earlier module's owned fields — enforced in practice by each module's `MODULE_CONTRACT.md` "Does NOT modify" list, not just by convention.
- **Module08 (Logging & Reporting) writes throughout the run, not only at the end.** The action log (`Runtime/Logs/action_log.jsonl`) receives entries starting with Module 01's own `discover`/`skip`/`error` actions. This diagram shows the primary `FileRecord` enrichment order — which module is responsible for filling in which fields — not literal call/execution order.
- **Multi-source support (`ROADMAP.md` Version 3)** would fan into Module 01 from multiple configured Sources (Desktop, Google Drive, etc.); it doesn't change anything downstream of Module 01 in this chain.
- Update this diagram if a future version introduces branching or parallel stages — it's deliberately drawn as a single chain because that's still true today.
