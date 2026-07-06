# 01 Watch & Ingest

## Purpose
Detect new files landing in a watched source and hand off a clean, stable file list to Classification.

## Input
A **Source** — a configured folder to watch. v1 ships with exactly one Source configured (the OS Downloads folder), but the step is designed around a Source concept rather than hardcoding "Downloads," so later versions can add more sources (Desktop, Documents, Google Drive, OneDrive, Dropbox, or any other watched folder) without redesigning this step or anything downstream. Downstream steps (02–08) only ever see a file path + its metadata — they don't know or care which Source it came from.

```json
// Source config shape (v1 has exactly one entry)
{ "source_id": "downloads", "path": "/Users/.../Downloads", "type": "local_folder", "enabled": true }
```

## Output
A queue of "ready to process" files — each a confirmed-complete, non-temporary file path, tagged with its `source_id`.

## Logic
1. Detect new/changed files in the enabled Source(s).
2. Filter out noise per `Rules/Ignore Rules.md` (partial downloads, OS junk, zero-byte files, already-indexed files).
3. Debounce: wait until file size is stable across two checks (avoids grabbing a half-written file).
4. Push each confirmed file onto the processing queue with: path, source_id, size, created/modified time, detected extension.

## Execution modes (v1 supports three; Manual is default)

| Mode | How it triggers | v1 status |
|---|---|---|
| **Manual** (default) | User asks Claude to "scan Downloads now" | Fully supported — this is what v1 is built and tested around |
| **Scheduled** | Runs on a cadence via the `schedule` skill (e.g. daily at 8am) | Supported — same scan logic as Manual, just triggered on a timer instead of a request |
| **Watch Folder** | A standing background process watches for filesystem events in real time (e.g. via `watchdog`/`chokidar`) | Documented, not built first — see trade-off note below |

### Trade-off: why Watch Folder isn't the v1 default
A real-time watcher needs a long-running background process, OS-level file permissions, and crash/restart handling — a meaningfully bigger lift than Manual or Scheduled, which just run a scan when asked. Building that before the core classify → name → file pipeline is even proven would be solving a harder problem before the easier one is validated. Sequencing (Manual → Scheduled → Watch Folder) is tracked in `ROADMAP.md`.

## Edge cases
- Zero-byte files (failed downloads) → skip, log as skipped.
- Files that reappear with the same name after being moved (re-download) → treat as new, let Duplicate Detection catch it.
- Permission errors reading a file → log as error, leave in place, don't crash the batch.

## Open questions
- None outstanding — execution mode and ignore rules were the two open items here, now resolved (see `Rules/Ignore Rules.md` and the table above).
