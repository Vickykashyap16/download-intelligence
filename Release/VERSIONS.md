# Version Ledger — Downloads Intelligence

Tracks the overall pipeline version and each module's independent version. This is the source of truth for both — update it every time a module is released or re-released.

## Current

**Pipeline Version: 0.3.0**

| Module | Version | Status |
|---|---|---|
| 01 — Watch & Ingest | 1.0.0 | Released |
| 02 — Classification | 1.0.0 | Released |
| 03 — Metadata Extraction | 1.0.0 | Released |
| 04 — Duplicate & Version Detection | — | Not started |
| 05 — Naming & Destination | — | Not started |
| 06 — Confidence & Review | — | Not started |
| 07 — Preview, Approval & Execution | — | Not started |
| 08 — Logging & Reporting | — | Not started |

## Versioning convention

- **Module Version** — standard semver (`MAJOR.MINOR.PATCH`), independent per module:
  - `PATCH` — bug fix within the module's current, frozen contract (e.g. the symlink fix would have been a patch release had this convention existed at the time).
  - `MINOR` — additive change that doesn't break the module's `MODULE_CONTRACT.md` (e.g. a new optional field, a new supported extension).
  - `MAJOR` — a change to the module's contract (its declared INPUT/OUTPUT/guarantees) that could require downstream modules to adapt.
- **Pipeline Version** — one number for the whole project's overall maturity. Bumped deliberately at meaningful milestones (e.g. "all 8 modules built and passing end-to-end" would justify `1.0.0`), not automatically derived from module versions.
- Modules evolve independently and at different paces. Illustrative example of where this goes (not the current state): `Pipeline 0.4.0` with `Module01 v1.0.0`, `Module02 v1.2.0`, `Module05 v0.9.0` — each module has iterated on its own schedule; the pipeline number reflects overall progress, not an average or maximum of the module numbers.
- Each module's own `MODULE_STATUS.md` (in `Release/ModuleNN/`) records its current version; this file is the cross-module ledger that ties them all together.

## History

- **2026-07-06** — Pipeline 0.3.0. Module 03 (Metadata Extraction) released at v1.0.0 — third module in the pipeline, frozen and feature-complete, production-ready for interactive Claude-assisted operation (no autonomous provider exists in v1 — see `Release/Module03/KNOWN_LIMITATIONS.md`). Zero implementation defects found during integration testing (4 test-harness bugs found and fixed instead); zero defects found during UAT; an independent implementation audit before integration testing found and resolved 2 Medium findings; an independent release audit before freeze found and resolved 3 Medium and 2 Low findings (see `Release/Module03/IMPLEMENTATION_AUDIT.md`/`RELEASE_AUDIT.md`). Modules 04–08 not yet started.
- **2026-07-06** — Pipeline 0.2.0. Module 02 (Classification) released at v1.0.0 — second module in the pipeline, frozen and feature-complete, production-ready for interactive Claude-assisted operation (no autonomous provider exists in v1 — see `Release/Module02/KNOWN_LIMITATIONS.md`). One defect found and fixed during integration testing (unwrapped image-read failures in `ClassificationEngine`); zero defects found during UAT; an independent release audit before freeze found and resolved 3 High and 3 Medium findings (see `Release/Module02/RELEASE_AUDIT.md`/`RELEASE_AUDIT_2.md`). Modules 03–08 not yet started.
- **2026-07-06** — Pipeline 0.1.0. Module 01 (Watch & Ingest) released at v1.0.0 — first module in the pipeline, frozen and production-ready. Modules 02–08 not yet started.
