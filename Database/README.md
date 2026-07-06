# Database

Persistent storage for the automation. Separated from `Build-out/` (which is documentation/spec, not data) and into three purpose-built subfolders so each grows independently and stays easy to query.

## `Metadata/`
Current-state record for every filed file — one entry per `file_id`, matching the schema in `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`. This answers "what do we know about this file right now."

**`metadata_store.json` is the complete, cumulative database of every file ever discovered — not a per-scan or per-batch snapshot.** Every run's `save_file_record()` call loads the entire existing store, upserts (by `file_id`) just the one record it's touching, and writes the full store back. Records from every prior batch stay in place; nothing gets reset or truncated between runs. `load_metadata_store()` always returns everything known, across the automation's whole lifetime.

v1 storage: a single `metadata_store.json` (array of records). SQLite migration is a Version 2 idea (see `ROADMAP.md`) if the flat file becomes slow to scan — no need to over-build this before there's real volume.

## `FileIndex/`
Fast lookup structures, optimized for one job: answering "have we seen this before."

- `hash_index.json` — SHA-256 → `file_id`, for exact-duplicate checks.
- `phash_index.json` — perceptual hash → `file_id` list, for near-duplicate image checks.
- `name_index.json` — normalized filename → `file_id` list, for version-chain grouping (see `04 Duplicate & Version Detection`).

## `History/`
Lineage over time — separate from current state because a file's *history* should survive even after it's archived/superseded.

- `version_history.json` — full chain per `version_group_id` (every version ever seen, its rank at the time, when it was superseded).
- `correction_history.json` (optional, later version) — longer-lived version of `Learning/User Corrections.json` if that file needs periodic archiving.

## `Learning/`
Passive capture of user corrections (edits/rejections during `07 Preview, Approval & Execution`) — not acted on in v1, just collected. See `Learning/README.md`. Grouped here with the rest of `Database/` because it's persistent structured data, same as `Metadata/`/`FileIndex/`/`History/`.

---

Nothing here yet — these are placeholders until the first real run. All subfolders start as plain JSON (see `ROADMAP.md` for the SQLite migration path).
