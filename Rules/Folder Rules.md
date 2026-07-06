# Folder Rules

Living rules for *where* a filed file ends up. Naming templates (how a file is renamed) live separately in `Rules/Naming Rules.md` — this doc is destinations only.

## v1 destination taxonomy — kept intentionally simple

Per the design review: start flat, expand only where it earns its keep.

```
Documents/
Finance/
Images/
  └── Screenshots/
Videos/
Audio/
Applications/
Archives/
Unknown/
```

## Category → folder mapping

| Category | Destination |
|---|---|
| Invoice | `Finance/` |
| Bank Statement | `Finance/` |
| Contract | `Documents/` |
| Resume | `Documents/` |
| Document (generic) | `Documents/` |
| Image / product photo | `Images/` |
| Screenshot | `Images/Screenshots/` |
| Application (installer) | `Applications/` |
| Archive | `Archives/` |
| Video | `Videos/` |
| Audio | `Audio/` |
| Unknown | `Unknown/` |

**Note on Audio:** the original 7-folder list from the design review didn't include a home for Audio, but Audio is already one of the v1 classification categories — without a folder it would always fall through to `Unknown/`, silently defeating the classifier. Adding a flat `Audio/` folder is the same low cost as `Videos/` (no subfolders, no extra taxonomy decisions), so it's included here. Flag if you'd rather fold Audio into `Documents/` or `Unknown/` instead.

## Documents/ — future subfolders (not built in v1)
Planned split once volume justifies it (tracked as a Version 2 item in `ROADMAP.md`): `Contracts/`, `Resumes/`, `Certificates/`, `Legal/`, `Manuals/`.

Do not pre-create these in v1 — an empty subfolder taxonomy with no files in it is exactly the over-engineering this review was trying to avoid. Add a subfolder only once enough files of that type have actually landed in `Documents/` to justify it.

## Overrides (these beat the normal mapping table)
- **Unknown category** → always `Unknown/`, regardless of confidence score.
- **Exact duplicate** → `~ARCHIVE~/Duplicates/`, never the normal destination.
- **Superseded version** → `~ARCHIVE~/Old Versions/`, never the normal destination.
- **`review_required` tier** (score < 80, see `Confidence Rules.md`) → **not moved at all**, regardless of category. The file stays in its original location; it's flagged in the batch preview and that day's `Runtime/Reports/Daily Summary/` entry instead. There is no dedicated "Review Required" folder in v1 — this was a deliberate simplification (see `CHANGELOG.md`) over inventing a 9th destination folder for something that's really a confidence outcome, not a category.

## Reminder
These destination folders live in the user's real, organized library (wherever they keep sorted files) — not inside this build vault.

Revision history: see `CHANGELOG.md`.
