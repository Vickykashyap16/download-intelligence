# Downloads Intelligence

An AI-powered Downloads folder assistant that understands file *contents* (not just extensions) and files each new download into the right place — classified, renamed, deduped, and version-checked — with a human approval step before anything moves. Build type: **Automation** (run on-demand or scheduled with Claude in this folder; no `Source/` folder needed).

**Full project overview, problem statement, goals, folder structure, pipeline, execution modes, v1 scope, and roadmap: see `README.md`.** This file is operating instructions for Claude, not the project narrative — keep it lean and don't duplicate README content here.

## Key context for every session

- **Non-negotiables:** never permanently delete anything; every action must be reversible; superseded versions/duplicates get archived, not deleted.
- **Business rules live in `Rules/`, not here.** Classification, naming, folder routing, confidence scoring, and ignore patterns are all in `Rules/*.md` — edit there, not in this file or in `Build-out/`.
- **Confidence is points-based and auditable** (`Rules/Confidence Rules.md`), never an arbitrary AI-reported percentage. Tiers: 95–100 `auto` · 80–94 `approval_required` · below 80 `review_required` (left in place, flagged — no dedicated folder).
- **No code has been written yet.** The design phase is complete as of this writing (see `CHANGELOG.md` for the full decision history). Check `Important info.md` each session for anything else worth remembering.
- **This vault is the build/planning workspace**, not the user's real Downloads folder.

## Folder map (where things go)

- `Build-out/` — architecture spec, one numbered folder per pipeline step (00–08). Do the work for a piece inside its folder. Full description: `README.md`.
- `Governance/` — project-wide engineering process, not business rules or a single module's design: `ENGINEERING_STANDARD.md` (the lifecycle every module follows — design → review → freeze → implement → audit → test → release; §7A defines the mandatory Pipeline Contract Verification gate within that lifecycle, §4A points to the Frozen Module Change Policy), `ARCHITECTURE_DECISIONS.md` (the permanent record of every architectural decision made and why), `PROJECT_ROADMAP.md` (one-page pipeline build status — distinct from the top-level `ROADMAP.md`, which is feature scope, not build progress), `PIPELINE_CONTRACT_VERIFICATION.md` (the 13-check gate run at every module freeze — a sub-part of the release audit, not a separate audit), `FROZEN_MODULE_CHANGE_POLICY.md` (what happens if a defect is found in an already-frozen module), `DOCUMENT_GROWTH_POLICY.md` (when/how governance documents split as the pipeline grows), `GOVERNANCE_REVIEW.md` (the review history of this framework itself). Read `ENGINEERING_STANDARD.md` before starting any new module's design phase.
- `Rules/` — the living business rules: `Classification Rules.md`, `Naming Rules.md`, `Folder Rules.md`, `Confidence Rules.md`, `Ignore Rules.md`.
- `src/` — implementation code (Python). See `src/README.md` for the module layout.
- `Database/` — persistent storage: `Metadata/`, `FileIndex/`, `History/`, `Learning/` (`User Corrections.json`, passive capture only in v1). Empty until first real run.
- `Runtime/` — operational output: `Logs/action_log.jsonl` (machine-readable), `Reports/` (Daily/Weekly Summary, Duplicate/Storage Report), `Temp/` (in-flight batch state). Empty until first real run.
- `Samples/` — canonical example files (Invoices, Images, Videos, Documents).
- `Tests/` — executable validation datasets — see priority order in `Tests/README.md`.
- `ROADMAP.md` — Version 2/3/future plans.
- `CHANGELOG.md` — dated log of design decisions.
- `Important info.md` — key facts to check every session.
- `~ATTACHMENTS~/` — screenshots, images, misc files.
- `~ARCHIVE~/` — old versions, dead ends, replaced files.
- `Registry/`, `Logs/`, `Reports/`, `Learning/` (top-level) — all deprecated, superseded by `Database/` and `Runtime/`. Kept only because files can't be deleted from this workspace; ignore them.

## Working Rules

- **Logs:** manual logs written by user OR they can ASK claude to
- **Important info:** Store key facts about the user and project in `Important info.md`. Check it each session, and add to it when something worth remembering comes up.
- **Attachments:** Screenshots, images, and misc files go in `~ATTACHMENTS~/`.
- **Archive:** Old versions, dead ends, and replaced files go to `~ARCHIVE~/` — archive, don't delete.
- **Build-out:** Each numbered folder = one sub-system. Do the work for a piece inside its folder.
- **Rules:** Business rules (classification, naming, folder routing, confidence scoring, ignore patterns) live in `Rules/`, not in this file or in `Build-out/` — edit rules there without touching the architecture spec.
- **Separate chats:** Encourage the user to do random research or context-condensing in a separate Claude chat, and bring back only what matters.
