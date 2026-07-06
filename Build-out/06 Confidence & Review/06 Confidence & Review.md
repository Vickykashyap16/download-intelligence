# 06 Confidence & Review

## Purpose
Score how much to trust the full suggestion (category + name + destination + dedup call) and route accordingly.

*(The actual scoring formula — starting value, named deductions, tiers, hard floors — lives in `Rules/Confidence Rules.md`, kept separate so weights can be tuned without editing this architecture doc.)*

## Input
Everything produced by steps 02–05 for one file.

## Output
- `confidence_score` (0–100)
- `confidence_breakdown` — the list of named deductions that produced the score (for auditability)
- `tier`: `auto` / `approval_required` / `review_required`

## Tiers (from brief)
- **95–100 → `auto`.** Still shown in the preview, but pre-checked for one-click batch approval.
- **80–94 → `approval_required`.** Shown in preview, unchecked, user must confirm individually.
- **Below 80 → `review_required`.** The file is **left in its original location** — not moved, not renamed, not filed anywhere. It's clearly highlighted in the batch preview and in that day's `Runtime/Reports/Daily Summary/` entry as needing a look. No dedicated "Review Required" folder exists in v1 — see `Rules/Folder Rules.md`.

## Logic
Apply `Rules/Confidence Rules.md`: start at 100, subtract each applicable named deduction, clip to [0, 100], look up the tier, then apply hard floors (fuzzy match, multi-document file, unknown category, locked/corrupted file) which can only push the tier down, never up.

## Edge cases
- Any fuzzy/near-duplicate match always forces at least `approval_required`, regardless of the computed score.
- Unknown category always routes to `review_required` regardless of score.
