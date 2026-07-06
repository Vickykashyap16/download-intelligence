# 03 Metadata Extraction

## Purpose
Pull the structured fields out of a file that later steps (naming, destination, dedup) depend on.

## Input
File + its category from Classification.

## Output
A category-specific metadata object (see field sets below), merged into the file's metadata JSON record (see `08 Logging & Reporting` for full schema).

## Fields by category
- **Invoice:** vendor, invoice number, invoice date, amount, currency, tax type (e.g. GST/VAT if present)
- **Resume:** candidate name, version indicator (if present in filename/content), last-modified date
- **Bank Statement:** bank name, account (last 4 digits only — never store full account numbers), statement period
- **Contract:** contract type, counterparties, effective date, term length if stated
- **Document (generic):** best-guess title/subject, document date if present, one-line description of what it is
- **Image/Product photo:** dominant subject/description (via Claude vision), color/variant if identifiable
- **Screenshot:** context description (Claude vision summary of what's on screen), capture date
- **Application (installer):** app name, version, platform (Win/Mac)
- **Archive:** best-effort contents summary (list top-level entries without fully extracting)
- **Video / Audio:** title/description if derivable from filename or embedded tags, duration, capture/creation date
- **Unknown:** whatever generic file metadata is available (created/modified date, size) — no category-specific fields

## Logic
1. Route to the right extractor based on category.
2. Text-bearing docs → Claude structured extraction (prompt returns JSON matching the field set above).
3. Images → Claude vision + EXIF (`Pillow`/`exifread`) for capture date/camera data where present.
4. Never fabricate a field — if a field can't be found, leave it null rather than guessing. Missing key fields should lower confidence (see 06).

## Privacy note
Bank statements: extract only what's needed for filing/search (bank name, period). Do not extract or log full account numbers, balances, or transaction line items.

## Edge cases
- Scanned/low-quality images → Claude vision may return partial fields; mark fields uncertain rather than omitting the attempt.
- Multi-invoice PDFs (batch invoice exports) → v1 treats the whole file as one record; flag as "multi-document" for manual review rather than trying to auto-split.
