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

## Evaluation order when more than one override could apply (Module 07 Design.md §11A)

The four bullets above are listed by topic, not by precedence — a single record can only ever match one of them, but the *order they're checked in* matters and is fixed:

1. **`review_required` tier** — checked first, absolute, no exception. If a record is `review_required`, nothing else below is even evaluated; the record is left completely unchanged.
2. **Exact duplicate** (`duplicate_of is not None`) — checked only if step 1 didn't apply.
3. **Superseded version** (`version_rank == "superseded"`) — checked only if steps 1–2 didn't apply.
4. **Normal category → folder mapping** (the table above) — applies only if none of the above did.

This means a record that is *simultaneously* `review_required` and an exact duplicate is never filed to `~ARCHIVE~/Duplicates/` — it is left in place, exactly like any other `review_required` record. `review_required` is the one absolute exception; it is never overridden by anything, including a human's own later decision (a `review_required` record is never even offered for approval in the first place — Module 07 Design.md §13).

**Human edits at approval time (`Governance/ARCHITECTURE_DECISIONS.md` decision 23):** when a human explicitly edits a suggested destination during Module 07's approval step (`ApprovalDecisionType.APPROVE_WITH_EDIT`), that edited destination is honored even for an exact-duplicate or superseded-version record — i.e. a human can file a correctly-flagged duplicate/old-version file somewhere other than `~ARCHIVE~/` if they choose to. This is the one exception to "never the normal destination" above, and it applies only to an explicit, logged, reversible human choice — never to Module 05's own automatic mapping, which still always routes to `~ARCHIVE~/` for these two cases. A `review_required` record has no destination to edit in the first place (step 1 above), so this exception can never apply to one.

## Reminder
These destination folders live in the user's real, organized library (wherever they keep sorted files) — not inside this build vault.

Revision history: see `CHANGELOG.md`.
