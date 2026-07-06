# Module 01 UAT — Run 1 (2026-07-05, batch_id `2026-07-05_190028`)

First real user-acceptance test of Module 01, run exactly as an end user would: `src/config/sources.yaml` pointed at a temporary Downloads-like folder outside the project (`/tmp/uat_downloads`, not preserved — ephemeral sandbox path), executed via `python3 -m src.main`.

## Test data
12 entries in `/tmp/uat_downloads`: 7 realistic discoverable files (invoice PDF, two images, a resume docx, a zip, placeholder mp3/dmg), `.DS_Store`, a `.crdownload` partial download, a zero-byte failed download, an unsupported `.torrent`, and a subfolder (`Old Screenshots/`) containing one more file.

## Result
7 discovered, 5 skipped, 12 total — reconciles exactly. All `FileRecord` fields populated correctly (UUID4 `file_id`, 64-char SHA-256 `content_hash`, correct MIME types, later-module fields left `null`). Non-recursive scope correctly honored (nested file in `Old Screenshots/` never appears anywhere). See `metadata_store.json` and `action_log.jsonl` in this folder for full raw output; `terminal_output.txt` for exactly what printed to the console.

## Differences from expected behavior found (both fixed afterward — see CHANGELOG.md)

1. **Terminal output showed only discovered files, nothing about skips.** `main.py`'s `scan()` only printed `build_ingest_queue()`'s return value (discovered records only) — a real user had no visibility into the 5 skipped items or why, without manually opening `action_log.jsonl`. Fixed: `src/main.py` rewritten to print a full summary (total/discovered/skipped counts, skipped items with human-readable reasons, and the generated file locations).
2. **Skip reasons were too coarse.** `.DS_Store` (OS junk) and the `.crdownload` partial download both logged as the same generic reason, `"ignored_name"` — indistinguishable in the log. Fixed: split into specific reasons `system_file` and `temporary_download`, with `ignored_pattern` reserved for future pattern-based rules.

No defects found in the underlying scan logic itself during this run — both findings were CLI/observability gaps, not incorrect ingest behavior.
