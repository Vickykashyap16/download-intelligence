# 04 Duplicate & Version Detection

## Purpose
Catch exact duplicates, near-duplicate images, and multi-version document chains before filing.

## Input
File + hash + metadata from prior steps; `Database/FileIndex/` (hash/phash/name indexes) and `Database/History/` (version lineage).

## Output
- `duplicate_of`: file_id if an exact duplicate exists, else null
- `version_group_id` + `version_rank` (`latest` / `superseded`) if part of a version chain

## Logic

### Exact duplicates
1. Compute SHA-256 of the file.
2. Compare against `Database/FileIndex/hash_index.json`.
3. Exact match → mark as duplicate, suggest: discard the new copy (moved to `~ARCHIVE~/Duplicates/`, never deleted), keep the existing filed copy.

### Near-duplicate images
- Perceptual hash (`imagehash`/pHash) comparison against recently-filed images in the same rough category.
- Close-but-not-exact match → flag as "possible duplicate," route to approval tier regardless of confidence score (never auto-resolve a fuzzy match).

### Version chains (documents)
1. Group candidate files by filename similarity (`rapidfuzz`/`difflib`) — e.g. `Resume_v8.pdf` and `Resume_v9.pdf` share a base name.
2. Determine order using, in priority: explicit version number in filename → file modified date → file created date.
3. Suggest: keep the latest as the "live" filed copy, move older versions to `~ARCHIVE~/Old Versions/` (never deleted).
4. Record all versions in the same `version_group_id` in `Database/History/version_history.json` so the full lineage stays traceable even after older versions are archived.

## Edge cases
- Same filename, genuinely different content (e.g. two different `invoice.pdf` downloads) → hash won't match, treat as unrelated files, not a version chain.
- Version chain where the "latest" filename is actually the older doc (numbering reset, typo) → flag lower confidence when version number and file dates disagree, force approval tier.
- User re-downloads a file they already filed weeks ago → exact hash match still works; suggest discarding the new copy.

## Open questions
- How far back should near-duplicate image comparison search (all filed images vs. last N)? Default: same suggested destination category, last 90 days — revisit once real volume is known.

## See also
Exact confidence deductions/hard floors for fuzzy matches and version conflicts: `Rules/Confidence Rules.md`.
