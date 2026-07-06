# Confidence Rules

Every confidence score must be explainable: a starting value plus a list of named deductions, not an arbitrary AI-generated percentage. This doc is the single source of truth for how the number is computed — store the full breakdown on the file's metadata record (`confidence_breakdown`, see `Metadata & Log Schema.md`) so any score can be audited later.

## Formula

```
score = 100
        − sum(applicable deductions below)
score = clip(score, 0, 100)
tier   = lookup(score)          # see Tiers, below
tier   = apply_hard_floors(tier) # hard floors can only push the tier DOWN, never up
```

## Deductions

| Signal | Deduction | Notes |
|---|---|---|
| Classification was ambiguous between two plausible categories | −15 | e.g. invoice-that's-also-a-receipt |
| No extractable text/content — classified from filename only | −30 | low-confidence guess |
| Each missing **required** metadata field for the category | −8 (max −30 total) | required fields defined per category in `Build-out/03 Metadata Extraction/Module 03 Design.md` §7 |
| Each missing **optional** metadata field | −2 (max −10 total) | |
| Naming template had to fall back to a placeholder value (e.g. `Unknown_Vendor`) | −10 per fallback used | |
| Near-duplicate / fuzzy image match found | −20 | also triggers a hard floor, see below |
| Version chain where filename version number and file date disagree | −25 | conflicting signals about which is "latest" |
| Non-English content detected | −10 | still attempted, just less certain |
| Locked / password-protected file | −40 | usually enough alone to force review |

## Tiers (unchanged from the original brief)

| Score | Tier |
|---|---|
| 95–100 | `auto` |
| 80–94 | `approval_required` |
| < 80 | `review_required` |

## Hard floors (override the math — a good score can't buy its way past these)

- **Unknown category** → always `review_required`.
- **Near-duplicate / fuzzy match** → never `auto`, at most `approval_required` — a fuzzy match should never silently self-resolve.
- **Multi-document file** detected (e.g. a batch invoice export) → always `review_required`.
- **Locked / unreadable file** → always `review_required`.
- **Corrupted file** (fails to open/parse at all) → always `review_required`.

## Worked example

`invoice.pdf` classified as Invoice with clear text, but missing `invoice_number` (required) and using a fallback vendor name:

```
100
 − 8   (missing required field: invoice_number)
 − 10  (naming fallback used: vendor)
────
 82  → tier: approval_required
```

Stored breakdown: `{"missing_required_field:invoice_number": -8, "naming_fallback:vendor": -10}` → total 82.

## Why points-based instead of an AI-reported percentage
An AI-reported "I'm 92% confident" number can't be audited or tuned — you can't tell why it moved from one run to the next. A fixed deduction table means every score is reproducible, every deduction is individually adjustable, and the Daily Summary can say *exactly* why a file needed approval instead of just showing a number.

## Tuning note
Start with the deductions above; expect to adjust specific weights (not the overall approach) after the first few real batches once you can see which deductions actually cause the most approval-tier routing.

Revision history: see `CHANGELOG.md`.
