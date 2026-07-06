# Naming Rules

Living rules for how a file gets renamed. This is the thing to edit when naming style needs to change — the architecture of the naming/destination step stays in `Build-out/05 Naming & Destination/05 Naming & Destination.md` and shouldn't need to change when these templates do. Destination folder taxonomy lives separately in `Rules/Folder Rules.md`.

Draft to react to, not a locked spec — adjust freely once real example files are in hand (see `Samples/`).

## General filename rules
- `Title_Case_With_Underscores` — no spaces, no special characters.
- Dates always in `YYYY-MM-DD` format.
- Always preserve the original file extension.
- Max ~80 characters.
- Never overwrite on collision — append `_2`, `_3`, etc.
- Missing fields get a safe fallback (`Unknown_Vendor`, `Unknown_Date`), never left blank.

## Templates by category

| Category | Template | Example |
|---|---|---|
| Invoice | `{DocSubtype}_{Vendor}_{Date}.{ext}` | `GST_Invoice_Amazon_2026-07-05.pdf` |
| Resume | `Resume_{CandidateName}_{VersionOrDate}.{ext}` | `Resume_Jordan_Patel_v9.pdf` |
| Bank Statement | `{BankName}_Statement_{Period}.{ext}` | `Chase_Statement_2026-06.pdf` |
| Contract | `{ContractType}_{PartyName}_{EffectiveDate}.{ext}` | `NDA_Acme_Corp_2026-07-01.pdf` |
| Document (generic) | `{BestGuessTitle}_{DateIfKnown}.{ext}` | `User_Manual_Espresso_Machine.pdf` |
| Image / Product photo | `{Description}_{Variant}.{ext}` | `Coffee_Table_Black.jpg` |
| Screenshot | `Screenshot_{ContextDescription}_{Date}.{ext}` | `Screenshot_Login_Error_2026-07-05.png` |
| Application (installer) | `{AppName}_{Version}_{Platform}.{ext}` | `Zoom_6.1_Mac.pkg` |
| Archive | `{ContentsSummary}_{Date}.{ext}` | `Project_Photos_2026-07-05.zip` |
| Video | `{Description}_{Date}.{ext}` | `Product_Demo_2026-07-05.mp4` |
| Audio | `{TrackTitle}_{Artist}.{ext}` (fallback: `{Description}_{Date}`) | `Interview_Draft_2026-07-05.mp3` |
| Unknown | `UNSORTED_{OriginalName}.{ext}` | `UNSORTED_file2384.dat` |

## Open questions for the user
- Do resumes/contracts need per-person or per-company subfolders once volume grows, or is a flat folder fine for v1? (Current answer: flat for v1 — see `Rules/Folder Rules.md`; per-entity subfolders are a `ROADMAP.md` idea, not a v1 commitment.)

Revision history: see `CHANGELOG.md`.
