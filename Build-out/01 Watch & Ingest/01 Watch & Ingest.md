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

## Post-freeze correction #1 (2026-07-11) — re-scan of an already-processed file must not discard Modules 02–06's work

**Discovered by:** Module 06 UAT's idempotency check (`Tests/Module 06 UAT Plan.md`, Finding UAT-1) — the first real invocation in this project's history to call `scan()` a second time against a store already carrying real Module 02–06 output for the scanned files.

**What this section clarifies (the original design/contract were never wrong on this point — they were silent on it):** `Release/Module01/MODULE_CONTRACT.md`'s DOES NOT MODIFY guarantee ("Module 01 never sets or touches any of the following... on every record it produces") already applies, unqualified, to a re-scan of a file Module 01 has seen before — its Guarantees section already states `file_id` is "stable across re-scans of a file that hasn't moved," confirming re-scanning is an anticipated operation, not an edge case outside this document's scope. What was never stated is *how* that guarantee is upheld across a re-scan, and the implementation's answer (before this correction) was to construct an entirely new `FileRecord`, which — combined with `storage/database.py`'s `save_file_record()` whole-object-replace upsert — silently reset every downstream-owned field to its default on every re-scan, changed content or not. This section makes the intended behavior explicit for both re-scan sub-cases, precisely enough for a future audit to check the implementation against it:

- **Re-scan, same `current_path`, `content_hash` unchanged:** the existing `FileRecord` is updated in place for Module 01's own fields only (`current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `status`, `error`, `batch_id`) — no downstream-owned field (Modules 02–07's, per `MODULE_CONTRACT.md`'s DOES NOT MODIFY list) is read, written, or otherwise referenced by this operation. `file_id`, `source_id`, `original_name`, `original_path`, `discovered_at` remain exactly as first assigned, per the existing Guarantees section.
- **Re-scan, same `current_path`, `content_hash` changed** (a file genuinely edited in place, or a different file landing at the same name): Module 01's own fields are updated the same way, and every downstream-owned field is reset to its `FileRecord` dataclass default (`None` / empty dict / empty list, matching first-discovery shape exactly). This is a deliberate exception to "never touch," scoped only to this one condition, for a specific reason: Modules 02–06's own eligibility filters (`category is None`, `extracted_metadata == {}`, `suggested_name is None`, `confidence_score is None`, `duplicate_signals is None`) are the *only* mechanism anywhere in this pipeline that ever re-selects a record for processing — none of them, and nothing else in the architecture, checks `content_hash` for staleness. A record whose downstream fields were instead *preserved* after a real content change would never again be eligible for reprocessing by any existing or currently-planned module — not delayed, permanently stuck presenting analysis of content that no longer exists on disk. Resetting to default is what lets a changed file re-enter the exact same, already-correct pipeline a first-discovery file uses; it is not a new mechanism, and it does not require any change to Modules 02–06.
- Either way, the pre-existing `content_changed_since_last_scan` action-log detail (`_process_entry()`) continues to surface which branch a given re-scan took, for auditability — unchanged by this correction.

**Not addressed by, or in scope of, this correction:** anything about *when* Modules 02–06 next run relative to a given `scan()` call — there is no guarantee of that today (Manual mode only, no locking or batch-staging mechanism currently implemented — see `Release/Module01/KNOWN_LIMITATIONS.md`), and this correction does not change that.

See `CHANGELOG.md` for the corresponding dated entry and `Release/Module01/MODULE_CONTRACT.md` for the matching Guarantees/DOES NOT MODIFY clarification.

**Design correction review (2026-07-11, single targeted round, per `Governance/FROZEN_MODULE_CHANGE_POLICY.md`):** re-read this section and the matching `MODULE_CONTRACT.md` clarification fresh, independent of having just written them. Findings:
- The two documents state the identical two-branch behavior with no contradiction between them.
- Matches the approved correction exactly: unchanged re-scan preserves all downstream fields via in-place update of Module 01's own fields only; changed-content re-scan resets downstream fields so the record re-enters Modules 02–06's existing null-based eligibility filters, requiring no change to any of those five modules.
- Scope confirmed minimal: nothing here requires a change to `save_file_record()` or any other part of `storage/database.py` — the correction is fully expressible as "which fields does `build_file_record()` touch," which is entirely within Module 01's own function.
- `content_hash` is a pure SHA-256 of file bytes (`core/hashing.py`'s `sha256_file()`); a metadata-only touch (e.g. `mtime` changing without the bytes changing) does not change it, so the "unchanged" branch — not the destructive reset branch — is what actually fires for the common case of a file simply sitting in place, confirming this correction is not merely trading one over-eager reset condition for a different one.
- One residual, non-blocking note for whenever Module 07 is designed: the reset-on-content-change branch is inferred to never apply to a record Module 07 has already executed/moved, because `current_path` moves outside the watched source folder at that point (per this document's own stated intent for that field) and a later scan of the source folder would no longer match it via `find_by_current_path()` — a new file landing at the old path would get a fresh identity instead. This inference relies on Module 01's own documented intent for `current_path`, not on Module 07's own design (which doesn't exist yet) — flagged for explicit reconfirmation when Module 07 is designed, not treated as a blocking contradiction now.
- No Critical, High, Medium, or Low finding. Approved to proceed to implementation.
