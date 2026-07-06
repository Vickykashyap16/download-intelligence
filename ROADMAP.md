# Roadmap

Where future-facing decisions that used to be scattered across `Rules/Folder Rules.md`, `Build-out/01 Watch & Ingest.md`, `Database/Learning/README.md`, and `Database/README.md` now live in one place. Nothing below is a v1 commitment — v1 scope is fixed and described in `README.md`.

## Version 1 (current — design complete, not yet built)
- Manual execution mode only (on-demand scan, triggered by asking Claude)
- Single Source: the Downloads folder
- Flat 8-folder destination taxonomy — no `Documents/` subfolders yet
- Points-based, auditable confidence scoring with hard floors (`Rules/Confidence Rules.md`)
- `review_required` files left in place, flagged in the preview and Daily Summary — no dedicated folder
- JSON-based `Database/` (Metadata/FileIndex/History) — no SQLite
- Passive correction logging (`Database/Learning/User Corrections.json`) — collected, not acted on
- Full audit trail: `Runtime/Logs/action_log.jsonl` + `Runtime/Reports/` (Daily/Weekly Summary, Duplicate/Storage Report)

## Version 2 (next, once v1 is proven)
- **Scheduled execution mode**, fully wired — cheap follow-on to Manual (same scan logic, triggered by the `schedule` skill on a timer instead of on request).
- **`Documents/` subfolder expansion** (`Contracts/`, `Resumes/`, `Certificates/`, `Legal/`, `Manuals/`) once real volume in `Documents/` justifies splitting it — see `Rules/Folder Rules.md` for the planned subfolder names.
- **SQLite migration** for `Database/` if the flat JSON files get slow to scan — see `Database/README.md`.
- **Multi-document PDF splitting** — a batch invoice export is currently flagged for manual review rather than auto-split into separate records.
- **Per-person/per-company subfolders** for Resumes/Contracts if a flat `Documents/` gets crowded.

## Version 3 (later)
- **Watch Folder execution mode** — a real-time background daemon. Deliberately deferred from v1: a bigger engineering lift than Manual/Scheduled (long-running process, OS permissions, crash recovery), only worth building once daily/on-demand scans prove too slow in practice.
- **Multi-source support** — Desktop, Google Drive, OneDrive, Dropbox, or any other watched folder. The architecture already supports this (the "Source" concept in `Build-out/01 Watch & Ingest/01 Watch & Ingest.md`); v3 is when a second Source actually gets configured.
- **Active learning** from `Database/Learning/User Corrections.json` — using accumulated corrections to adjust classification/naming/destination defaults automatically, instead of just logging them for later.

## Future ideas (exploratory, not committed)
- Recursive subfolder scanning inside Downloads (v1 only scans the top level — see `Rules/Ignore Rules.md`).
- A simple search/query interface over `Database/Metadata/` (e.g. "find all invoices from Amazon in June").
- Size-based ignore rules, if very large files (multi-GB video/disk images) turn out to slow down a scan meaningfully.

These are unvalidated ideas, not commitments — revisit once v1 is running and real pain points are known.
