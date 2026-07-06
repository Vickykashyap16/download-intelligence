# 05 Naming & Destination

## Purpose
Turn category + metadata into a human-friendly filename and a suggested destination folder.

*(Naming templates live in `Rules/Naming Rules.md`; destination folder taxonomy and routing rules live in `Rules/Folder Rules.md` — this note covers the architecture/logic that applies them, not the business rules themselves.)*

## Input
Category + extracted metadata + duplicate/version info.

## Output
- `suggested_name` (with original extension preserved)
- `suggested_destination` (folder path relative to the filed library root)

## Logic
1. Look up the naming template for the file's category (see `Rules/Naming Rules.md`).
2. Fill the template from extracted metadata. Any field that's missing is either omitted cleanly from the template or replaced with a safe fallback (e.g. "Unknown_Vendor") — never left as a raw blank or placeholder token.
3. Sanitize: strip special characters, collapse spaces to underscores, enforce Title_Case, cap length (~80 chars).
4. Check for filename collisions in the destination folder → append `_2`, `_3`, etc. rather than overwrite.
5. Map category → destination folder per `Rules/Folder Rules.md`. Version chains and duplicates route to `~ARCHIVE~/` subfolders instead of the normal destination (per 04).

## Edge cases
- Category is Unknown → keep the original filename, prefix `UNSORTED_`, destination is always `Unknown/` regardless of confidence.
- Multiple missing metadata fields → still generate a best-effort name, but this should already be pulling the confidence score down (see 06).

## Open questions
- Final folder taxonomy and naming style are the user's call (taste) — treat `Rules/Naming Rules.md` and `Rules/Folder Rules.md` as first drafts to react to, not locked decisions.
