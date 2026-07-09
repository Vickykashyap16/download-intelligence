# Naming Rules

Living rules for how a file gets renamed. This is the thing to edit when naming style needs to change — the architecture of the naming/destination step stays in `Build-out/05 Naming & Destination/05 Naming & Destination.md` and shouldn't need to change when these templates do. Destination folder taxonomy lives separately in `Rules/Folder Rules.md`.

Draft to react to, not a locked spec — adjust freely once real example files are in hand (see `Samples/`).

## General filename rules
- `Title_Case_With_Underscores` — internal spaces become underscores (not dropped), no special characters. (Corrected 2026-07-09 — see `Build-out/05 Naming & Destination/Module 05 Design.md` §12 "Post-freeze correction #1": the original wording, "no spaces," was implemented as "spaces are stripped," which silently ran multi-word values together, e.g. `"Northwind Traders"` → `"Northwindtraders"`. The convention's own name — `..._With_Underscores` — always implied spaces become separators, not that they vanish; the rule text now says so explicitly.)
- Dates always in `YYYY-MM-DD` format.
- Always preserve the original file extension.
- Max ~80 characters.
- Never overwrite on collision — append `_2`, `_3`, etc.
- Missing fields get a safe fallback (`Unknown_Vendor`, `Unknown_Date`), never left blank.

## Templates by category

Templates below are current as of Module 05's implementation (2026-07-09) — five were revised from their original draft form once cross-checked against Module 03's real, frozen metadata taxonomy; see `Build-out/05 Naming & Destination/Module 05 Design.md` §10/§29 for the full rationale behind each change. Fallback behavior (what fills a slot when the underlying field is missing) is also specified there (§11) — this table shows only the shape.

| Category | Template | Example |
|---|---|---|
| Invoice | `{Vendor}_{InvoiceNumber}_{Date}.{ext}` (falls back to `{Vendor}_{Date}` when `InvoiceNumber` is absent — an optional enrichment, omitted rather than placeholder-filled) | `Amazon_INV123_2026-07-05.pdf` |
| Resume | `Resume_{CandidateName}_{VersionOrDate}.{ext}` (`VersionOrDate` = version indicator if present, else last-modified date, else `Unknown`) | `Resume_Jordan_Patel_v9.pdf` |
| Bank Statement | `{BankName}_Statement_{Period}.{ext}` | `Chase_Statement_2026-06.pdf` |
| Contract | `{ContractType}_{Counterparty}_{EffectiveDate}.{ext}` | `NDA_Acme_Corp_2026-07-01.pdf` |
| Document (generic) | `{BestGuessTitle}_{DateIfKnown}.{ext}` | `User_Manual_Espresso_Machine.pdf` |
| Image / Product photo | `{Description}_{Variant}.{ext}` | `Coffee_Table_Black.jpg` |
| Screenshot | `Screenshot_{ContextDescription}_{Date}.{ext}` | `Screenshot_Login_Error_2026-07-05.png` |
| Application (installer) | `{AppName}_{Version}_{Platform}.{ext}` | `Zoom_6.1_Mac.pkg` |
| Archive | `{ContentsSummary}_{Date}.{ext}` (`Date` has no dedicated Archive field — always the file's filesystem-modified date) | `Project_Photos_2026-07-05.zip` |
| Video | `{Description}_{Date}.{ext}` (`Date` — no video-tag library approved in v1, so always the file's filesystem-modified date) | `Product_Demo_2026-07-05.mp4` |
| Audio | `{TrackTitle}_{Artist}.{ext}` (falls back to `{TrackTitle}_{RecordingDate}` when `Artist` is absent, falls back further to `{TrackTitle}` alone when `RecordingDate` is also absent) | `Interview_Draft.mp3` |
| Unknown | `UNSORTED_{OriginalName}.{ext}` | `UNSORTED_file2384.dat` |

## Open questions for the user
- Do resumes/contracts need per-person or per-company subfolders once volume grows, or is a flat folder fine for v1? (Current answer: flat for v1 — see `Rules/Folder Rules.md`; per-entity subfolders are a `ROADMAP.md` idea, not a v1 commitment.)

Revision history: see `CHANGELOG.md`.
