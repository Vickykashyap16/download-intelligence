# Ignore Rules

What Watch & Ingest should skip entirely — never queued, never logged as processed, never shown in a batch preview.

## Ignored by extension/suffix (in-progress or partial downloads)
`.crdownload`, `.part`, `.tmp`, `.download`, `.!ut` (uTorrent), `.opdownload`

Recorded in the action log / `SkippedEntry` as reason **`temporary_download`**.

## Ignored OS/system junk
`.DS_Store`, `Thumbs.db`, `desktop.ini`, `Icon\r`, `.localized`

Recorded in the action log / `SkippedEntry` as reason **`system_file`**.

A third reason, **`ignored_pattern`**, is reserved in the code for any future ignore
rule that's neither an exact filename match nor a suffix match (e.g. a wildcard/regex
pattern) — no rule in this document currently produces it. Added during the Module 01
UAT review so the reason taxonomy has somewhere to grow without another rename; both
categories above used to collapse into one generic `ignored_name` reason, which meant
a user reading the action log couldn't tell an OS junk file from a still-downloading
one.

## Ignored by state
- Zero-byte files (failed/incomplete downloads) → skip, note as skipped in that day's `Runtime/Reports/Daily Summary/` entry, don't error.
- Files still changing size between two checks (mid-write) → wait, re-check next pass, don't queue yet.
- Files already present in `Database/FileIndex/hash_index.json` under their current path (already filed, nothing changed) → skip, don't re-queue.

## Ignored by size (configurable, off by default in v1)
No size floor/ceiling in v1 — process everything that passes the checks above. Revisit only if very large files (e.g. multi-GB video/disk images) turn out to slow down a scan meaningfully.

## Source scope (v1)
Only the top level of the configured source folder (Downloads) is scanned in v1 — no recursive subfolder scanning. Revisit if the user routinely nests files in subfolders inside Downloads before this automation gets to them.

## Ignored: symlinks
Any symlink found directly inside the source folder is skipped unconditionally, whether it points to a file or a directory. A symlink can point anywhere on disk, including well outside the watched folder — following it would mean hashing, recording, and (once later modules move files) potentially relocating whatever it actually points to, without the user ever having put that file in Downloads themselves. Not a v1 requirement to support following symlinks in any form, so nothing is lost by skipping them outright. Revisit only if a real workflow needs it.

Revision history: see `CHANGELOG.md`.
