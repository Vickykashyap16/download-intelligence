# 02 Classification

*(Quick-reference summary. Full pre-implementation design — Module Contract, AI provider abstraction, alternatives, risks, formal architecture review — lives in `Module 02 Design.md` in this same folder. That document is the one currently under review; this file will be trimmed/kept lean once the design is frozen and implementation begins, per the same pattern used for Module 01.)*

## Purpose
Turn a raw file into a category: Invoice, Resume, Bank Statement, Contract, Document (generic), Image, Screenshot, Application, Archive, Video, Audio, or Unknown.

`Document` is the catch-all for readable files that don't match a more specific business type; `Unknown` is reserved for files that couldn't be classified at all. See `Rules/Classification Rules.md` for the full distinction.

*(The actual classification heuristics — extension/MIME mapping, screenshot detection, document deep-pass signals, edge cases — live in `Rules/Classification Rules.md`, kept separate so the rules can be tuned without editing this architecture doc.)*

## Input
One queued file from Watch & Ingest.

## Output
`category` + a raw confidence signal for that classification (feeds into `06 Confidence & Review` / `Rules/Confidence Rules.md`).

## Logic (see `Rules/Classification Rules.md` for the actual rules applied)
1. Cheap pass first — extension/MIME type.
2. Screenshot vs. plain Image split.
3. Document deep pass for text-bearing files (Claude text or vision classification).
4. Anything that doesn't confidently fit a category → Unknown.

Revision history: see `CHANGELOG.md`.
