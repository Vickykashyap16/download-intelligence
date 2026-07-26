# C2 — Sandbox Product Validation Report

**Date:** 2026-07-26
**Role:** Product Validation
**Source:** `/Users/vicky/Desktop/sample` (19 top-level items)
**Destination (configured, not written to):** `/Users/vicky/Desktop/Organized Downloads`
**Scope:** scan → classify → extract → detect_duplicates → suggest_naming → score_confidence → preview. No execute. No files moved, renamed, or deleted.

## Isolation note

This run used an isolated copy of `src/` in a scratch location, with its own empty `Database/`/`Runtime/`, configured with `source_path` pointed at the real sample folder (read-only access) and `destination_root` set to the value above. This keeps sandbox validation data out of the real production `Database/Metadata/metadata_store.json` (866 real records from your actual Downloads folder, fully preserved and untouched — confirmed via `git status` after this run: no changes to any real Database/Runtime file). The real production `sources.yaml` (source: `/Users/vicky/Downloads`) was never modified.

## Total files

19 items at the top level of the sample folder → **8 discovered**, 11 skipped.

Skipped (all correct per Ignore Rules, none are defects):
- 2 folders (`autoagent`, `50. Employees Delhi NCR Bank Database`) — v1 only scans the top level, not subfolders.
- 1 system file (`.DS_Store`).
- 8 unsupported extensions: `.xlsx` (×2), `.json`, `.csv`, `.zone`, one no-extension file (`hpkekeyconfig`), one non-standard-name file (`¢ 2`).

**Product note (not a defect):** `.xlsx`/`.csv`/`.json` are common Downloads-folder file types and are outside v1's `SUPPORTED_EXTENSIONS`. Worth a line in the roadmap if spreadsheet/data files are expected to be common in your real Downloads — not something to change during this validation.

## Category distribution (8 files)

| Category | Count |
|---|---|
| Unknown | 3 |
| Image | 2 |
| Application | 1 |
| Archive | 1 |
| Video | 1 |

## Confidence distribution

| Score | Count |
|---|---|
| 100 | 3 |
| 96 | 1 |
| 76 | 1 |
| 68 | 2 |
| (Archive, deterministic) 100 | 1 |

## Auto / approval / review counts

| Tier | Count |
|---|---|
| auto | 2 |
| approval_required | 0 |
| review_required | 6 |

No `approval_required` records in this dataset — not a defect, just this sample's composition (every non-auto file either landed in the Category.UNKNOWN hard floor or scored below 80).

## Duplicate summary

0 exact duplicates, 0 near-duplicates, 0 version chains. Correct — all 8 files are genuinely distinct content; nothing in this sample should have matched.

## Per-file evaluation

| File | Category | Correct? | Naming | Destination | Confidence/Tier | Notes |
|---|---|---|---|---|---|---|
| `1-11920857482.pdf34DSC.pdf` | Unknown | **Investigated — see Finding 1** | `Unknown/Unsorted_1-11920857482pdf34dsc.pdf` | Correct for Unknown | 100, review_required (hard floor) | 16-page Indian MCA corporate filing (Form INC-34, e-AOA). |
| `20250702_145416 (1).pdf` | Unknown | Correct | `Unknown/Unsorted_20250702_145416_1.pdf` | Correct for Unknown | 100, review_required (hard floor) | Single-page promotional/caption text — genuinely ambiguous, no clear category fits. |
| `54.+Event+Management+...zip` | Archive | Correct | `Archives/54_Event_Management_Organisers_Service_97000_2024-06-29.zip` | Correct | 100, auto | Deterministic by extension; date correctly pulled from file timestamp. |
| `5579374e-...jpeg` | Image | **Incorrect — see Finding 2** | `Images/Unknown_Description_Unknown_Variant.jpeg` | Wrong (should be Screenshot) | 68, review_required | Actual content: a phone-screen screenshot of a payment app (visible amount, bank account, card digits). |
| `_0b955623-...jpeg` | Image | Correct | `Images/Unknown_Description_Unknown_Variant_2.jpeg` | Correct | 68, review_required | AI-generated/rendered interior photo — genuinely a photo/image, not a screenshot. Collision suffix (`_2`) correctly applied since both jpegs fell back to the same generic name. |
| `_CRxKP2tWaffy2qC.mp4` | Video | Correct | `Videos/Crxkp2twaffy2qc_2026-07-23.mp4` | Correct | 96, auto | Missing optional duration/content_date only — expected without a vision/metadata provider. |
| `code.txt` | Unknown | **Investigated — see Finding 3** | `Unknown/Unsorted_Code.txt` | Correct for Unknown | 100, review_required (hard floor) | Content is a source-code directory tree, not a document. |
| `iTunes12.8.3 (1).dmg` | Application | Correct | `Applications/Itunes1283_1_Unknown_Version_Unknown_Platform.dmg` | Correct | 76, review_required | app_name correctly parsed from filename; version/platform correctly fell back (not derivable without deeper inspection). |

## Findings (root-caused, no code changes made)

### Finding 1 — Legal/corporate PDF classified Unknown
**Root cause:** TD-01 (no autonomous classification provider). `ClassificationEngine._classify_text_bearing()` correctly extracted real text from this PDF (`no_extractable_text: False`, confirms text was found) but text-bearing files require the judgment/deep pass to distinguish Document/Invoice/Contract/etc. — that pass only runs inside a live, interactively-driven Claude session (`ClaudeLiveClassifier` is a documented placeholder that raises `NotImplementedError` if called outside one). Run non-interactively (as this validation was, mirroring how your production `run` behaves from a terminal), every text-bearing file with real content falls back to `Category.UNKNOWN` — this is expected, disclosed behavior, not a defect. Manually reading the file confirms a live pass would very likely have classified this as `Document` (Form INC-34, Companies Act 2013 e-AOA filing).
**Disposition:** No fix — this is the known, already-tracked TD-01 limitation, not new.

### Finding 2 — Real screenshot classified as generic Image
**Root cause:** confirmed via `src/pipeline/classification.py`'s `classify_screenshot_or_image()` — the Screenshot/Image split is fully deterministic (filename markers `screenshot`/`screen shot`/`cleanshot`/`snip`, or exact match against a fixed list of common device/screen resolutions). This file's name is a random UUID (no marker) and its actual pixel dimensions are 590×1280 — not in `_COMMON_SCREEN_RESOLUTIONS`, almost certainly because a messaging app resized/re-encoded it before it reached the sample folder. This is the exact disclosed trade-off recorded in the PT-002 post-freeze correction (`classification.py`'s own docstring): removing the old "no camera EXIF" signal fixed a worse over-broad-Screenshot problem, at the cost of missing a genuine screenshot when it's been renamed and resized. Confirmed by direct visual inspection: the image is a payment-app call screen showing an amount, bank name, partial account number, and partial card number.
**Disposition:** No fix — this is PT-002's already-accepted, disclosed trade-off operating exactly as designed, not a new defect. Flagging because the content here is more sensitive than a typical screenshot (financial details), which raises the practical stakes of this known gap slightly — worth a mention in TECHNICAL_DEBT_REGISTER.md as a real example, not a code change.

### Finding 3 — Source code file classified Unknown
**Root cause:** `Category` has no code/source-file category in v1's taxonomy (`Invoice, Resume, Bank Statement, Contract, Document, Image, Screenshot, Application, Archive, Video, Audio, Unknown`). A directory-tree-shaped `.txt` file has nowhere correct to go even with a live judgment pass — `Unknown` is the closest available answer, not a misclassification.
**Disposition:** No fix — product-scope gap, not a defect. Could be a future roadmap candidate if source/code files are common in your real Downloads.

## Naming quality

Correct where fields were available (Archive, Video, Application app_name). Fallback naming (`Unknown_Description_Unknown_Variant`) is honest and clearly flagged (`naming_signals.fields_fell_back`) rather than fabricated — consistent with the "never invent, always disclose" design principle. Collision suffix logic worked correctly on the one case where it applied.

## Folder quality

`Archives/`, `Videos/`, `Images/`, `Applications/`, `Unknown/` — all correctly match `Rules/Folder Rules.md`'s category→folder mapping, including the Unknown-category override.

## False positives

None found — no file was placed in an incorrect *category-appropriate* folder given its assigned category.

## False negatives

- The screenshot misclassified as Image (Finding 2) is the one real false negative in this sample — a file that should have received Screenshot-specific handling and didn't.

## Unknown classifications

3 of 8 (37.5%). All three explained above: 2 are TD-01 (no live provider), 1 is a genuine taxonomy gap (no Code category). None are unexplained.

## Recommendations before execute

1. **Safe to proceed to execute on this sandbox dataset**, if you want to see Module 07's actual move/rename behavior next — nothing above blocks that; every tier/gate decision I checked matches design.
2. Do not treat the 2 Unknown PDFs' classifications as final — re-running `classify`/`extract` inside a live, interactively-driven Claude session (rather than a plain terminal invocation) would very likely resolve at least the legal-filing PDF to `Document`. This is a workflow choice, not a code fix.
3. Consider logging the sensitive-content screenshot case (Finding 2) as a concrete, real example under TECHNICAL_DEBT_REGISTER.md's existing Screenshot/Image entry, since it's a live illustration of an already-accepted trade-off rather than a new item.
4. If `.xlsx`/`.csv`/`.json` show up often in your real Downloads, consider whether v1's `SUPPORTED_EXTENSIONS` should be revisited on the roadmap — out of scope for this validation, noted for awareness only.

No code changes were made during this phase, per your instructions. Stopping here and awaiting your review/approval before any execute step.
