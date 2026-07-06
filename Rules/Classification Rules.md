# Classification Rules

Living rules for how a file gets assigned a category. This is the thing to edit when classification behavior needs to change — the architecture/purpose of the classification step itself stays in `Build-out/02 Classification/02 Classification.md` and shouldn't need to change when these rules do.

## Categories (v1)
Invoice, Resume, Bank Statement, Contract, Document (generic), Image, Screenshot, Application, Archive, Video, Audio, Unknown.

**Document** is the catch-all for readable text-bearing files that don't match a more specific type (Invoice/Resume/Bank Statement/Contract) — e.g. a manual, certificate, letter, or personal note. **Unknown** is reserved strictly for files that couldn't be classified at all (unreadable, corrupted, no text, no matching signal whatsoever). Keeping these separate matters: Unknown routes to a literal `Unknown/` folder implying "we don't know what this is," while Document routes to `Documents/` because we *do* know what it is — it's just not one of the specific business categories.

## Pass 1 — extension / MIME (cheap, always run first)

| Extension(s) | Category |
|---|---|
| `.exe .dmg .pkg .msi` | Application |
| `.zip .rar .7z .tar .gz` | Archive |
| `.mp4 .mov .mkv .avi` | Video |
| `.mp3 .wav .m4a .flac` | Audio |
| `.png .jpg .jpeg .heic .webp` | Image → run Screenshot split (below) |
| `.pdf .doc .docx .txt .rtf` | → run Text deep pass (below) |
| anything else | Unknown (until deep pass says otherwise) |

## Screenshot vs. plain Image split
Treat as **Screenshot** if any of:
- Filename contains `Screenshot`, `Screen Shot`, `CleanShot`, `Snip`
- Image dimensions match a common device/screen resolution
- No camera EXIF data present (no lens/camera model tag)

Otherwise → **Image** (product photo, general picture, etc.).

## Text deep pass (PDF/DOCX/text-bearing files)
1. Extract text (first 1–2 pages is usually enough).
2. Claude reads the extracted text and classifies using these signals, in order:
   - **Invoice:** line items, totals, invoice number, "Bill To," tax lines (GST/VAT).
   - **Resume:** work history, education, skills sections, first-person career framing.
   - **Bank Statement:** account activity, transaction table, statement period, bank letterhead.
   - **Contract:** parties/counterparties, clauses, signature blocks, effective/termination dates.
   - **Document (generic):** readable, coherent text that doesn't match any of the above — e.g. a manual, certificate, letter, or note. This is the fallback *before* Unknown, not after it.
3. No extractable text (scanned image PDF) → render page as image, run the same classification via Claude vision instead of text (including the Document fallback).
4. Genuinely unreadable, unparseable, or no matching signal whatsoever (not even generic document text) → **Unknown**.

## Edge cases
- Multi-purpose PDF (e.g. invoice that's also a receipt) → pick the closer match; note the ambiguity (feeds a confidence deduction — see `Confidence Rules.md`).
- Password-protected PDF → can't read contents → Unknown, flagged "locked file, needs manual review."
- Non-English documents → still attempt classification; note detected language (feeds a confidence deduction).
- Resumes vs. cover letters → bucketed together as Resume for v1; split into subtypes only if this becomes noisy in practice.

Revision history: see `CHANGELOG.md`.
