# Downloads Intelligence

An AI-powered Downloads folder assistant that understands what a file *is* — not just its extension — and files it away classified, renamed, deduplicated, and version-checked, with a human approval step before anything moves.

This is the design/build workspace for the project. It is not the real Downloads folder — the automation eventually acts on the user's actual OS Downloads folder, connected separately when it runs.

## Problem statement

Downloads folders accumulate messy, randomly-named files over time: duplicates, multiple versions of the same document, and a mix of invoices, resumes, screenshots, contracts, installers, and everything else, all dumped in one flat place. Finding anything later is hard, and cleaning it up manually is tedious enough that most people just don't.

## Goals

- Classify files by actual content, not extension.
- Generate clear, consistent filenames instead of leaving `IMG_8293.jpg` and `invoice(3).pdf`.
- Catch exact duplicates and near-duplicate images before they pile up.
- Detect version chains (`Resume_v8.pdf` vs. `Resume_v9.pdf`) and archive superseded copies instead of leaving both around.
- Route files to a sensible destination folder.
- Never act with full autonomy on uncertain calls — score every suggestion and require human approval below a threshold.
- Never delete anything, and keep every action reversible.

## Folder structure

```
Download Intelligence/
├── README.md              — this file: the human-facing overview
├── ROADMAP.md              — Version 1/2/3 and future ideas
├── CHANGELOG.md            — dated log of design decisions
├── CLAUDE.md                — operating instructions for Claude (not for humans)
├── Important info.md        — session-to-session memory for Claude
├── Build-out/                — architecture spec, one numbered folder per pipeline step
│   ├── 00 Pre-build context & examples/  — full spec (Pre-build context.md)
│   ├── 01 Watch & Ingest/
│   ├── 02 Classification/
│   ├── 03 Metadata Extraction/
│   ├── 04 Duplicate & Version Detection/
│   ├── 05 Naming & Destination/
│   ├── 06 Confidence & Review/
│   ├── 07 Preview, Approval & Execution/
│   └── 08 Logging & Reporting/
├── Rules/                    — the living business rules (edit these, not the spec, when behavior needs to change)
│   ├── Classification Rules.md
│   ├── Naming Rules.md
│   ├── Folder Rules.md
│   ├── Confidence Rules.md
│   └── Ignore Rules.md
├── src/                       — implementation code (see src/README.md)
├── Database/                 — persistent storage: Metadata/, FileIndex/, History/, Learning/ (User Corrections.json)
├── Runtime/                   — operational output: Logs/ (action_log.jsonl), Reports/ (Daily/Weekly Summary, Duplicate/Storage Report), Temp/ (in-flight batch state)
├── Samples/                   — canonical example files (Invoices, Images, Videos, Documents)
├── Tests/                      — executable validation datasets (Small Batch, Mixed Downloads, Duplicate Files, Corrupted Files, Large Batch)
├── ~ATTACHMENTS~/              — screenshots, images, misc files
├── ~ARCHIVE~/                  — old versions, dead ends, replaced files
└── Registry/, Logs/, Reports/, Learning/ (top-level) — deprecated, ignore (superseded by Database/ and Runtime/)
```

## High-level workflow

1. A new file lands in Downloads.
2. It's identified by type and, if needed, its contents are read by Claude to understand what it actually is.
3. Structured metadata gets pulled out (vendor, dates, amounts, names — whatever's relevant to that category).
4. It's checked against everything already filed for exact duplicates, near-duplicate images, and version chains.
5. A new filename and destination folder are suggested.
6. Everything gets a confidence score and a tier.
7. The whole batch is shown as a preview; the user approves, edits, or rejects.
8. Approved files are moved/renamed; nothing is ever deleted, and every action is logged so it can be undone.
9. A Daily Summary recaps what happened.

## Pipeline overview

```
New File → Watch Downloads → Identify file type → Understand contents (AI) →
Extract metadata → Detect duplicates/versions → Suggest filename → Suggest destination →
Show preview → User approval → Move/Rename → Generate logs & reports
```

Mapped 1:1 to the 8 numbered `Build-out/` folders — see each for the architecture, and the corresponding `Rules/` file for the actual business logic.

## Execution modes

| Mode | Status in v1 |
|---|---|
| **Manual** (default) | Fully supported — ask Claude to scan Downloads on demand. This is what v1 is built and tested around. |
| **Scheduled** | Supported — same logic as Manual, triggered on a timer via the `schedule` skill instead of a request. |
| **Watch Folder** | Documented, not built first — a real-time background watcher is a bigger engineering lift than the other two; see `ROADMAP.md`. |

## Version 1 scope

- Downloads is the only watched Source (multi-source is architected for, not built — see `ROADMAP.md`).
- Categories: Invoice, Resume, Bank Statement, Contract, Document (generic), Image, Screenshot, Application, Archive, Video, Audio, Unknown.
- Destination taxonomy is 8 flat top-level folders — no subfolders yet (`Rules/Folder Rules.md`).
- Confidence is a fixed, auditable point-deduction system, not an AI-reported percentage (`Rules/Confidence Rules.md`).
- Tiers: 95–100 `auto` · 80–94 `approval_required` · below 80 `review_required` (left in place, flagged — no dedicated folder).
- Storage is plain JSON (`Database/`), no SQLite yet.
- Implementation is underway in `src/` — see `src/README.md` for the module layout and what's built so far.

## Roadmap summary

Version 2 adds Scheduled mode in earnest, `Documents/` subfolder expansion once volume justifies it, and a possible SQLite migration. Version 3 adds real-time Watch Folder mode, additional sources (Desktop, Google Drive, OneDrive, Dropbox), and active learning from user corrections. Full detail: `ROADMAP.md`.

## How to use this project

**Right now (implementation phase):** `Build-out/` and `Rules/` are the design/spec docs; `src/` is the actual code, built one module at a time. Nothing here touches a real Downloads folder until a full scan-to-execution path is built and tested against `Tests/`.

**Once built:** ask Claude (in Manual mode, the v1 default) to scan Downloads. Claude will identify new files, classify and score them per the rules in `Rules/`, and present a batch preview. Approve, edit, or reject each suggestion; approved files get moved and renamed, everything else stays put. Check `Runtime/Reports/Daily Summary/` afterward for a recap, or `Runtime/Logs/action_log.jsonl` if you need to undo something.
