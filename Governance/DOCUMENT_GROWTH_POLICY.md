# Governance Document Growth Policy

Referenced by `Governance/ENGINEERING_STANDARD.md` §22A. Governs how the documents in `Governance/` (and, by the same principle, any other living project document that accumulates entries over time, such as `CHANGELOG.md` or `Release/VERSIONS.md`) stay navigable as the pipeline grows from 3 frozen modules today toward 8, plus whatever Version 2/3 work follows. Generic by design — this policy doesn't name a specific document's current length, only the thresholds and mechanics for handling growth in any of them.

## 1. When a governance document should be split

A document is split only when it demonstrably impairs finding a section within a few seconds of scanning — not preemptively, and not on a fixed size/entry-count trigger alone. Concretely, treat a split as due when **any** of the following becomes true, checked at each module's release (as part of `ENGINEERING_STANDARD.md` §8's release process):

- A reader (the project owner or a future Claude session) has to read past unrelated content more than once in a session to find a section they were looking for.
- A single document's entries span genuinely unrelated concerns that happen to have accumulated in one place for historical reasons rather than by design (e.g. if `ARCHITECTURE_DECISIONS.md` started mixing data-model decisions with UI/reporting decisions once Module 08 exists — a plausible future seam, not a current one).
- A document's length makes it impractical to re-read in full during an independent review of it (the standard this project already holds itself to for every audit — "assume nothing is correct, re-verify directly" only works if the document is actually re-readable in one sitting).

When a split is due, prefer splitting **by concern** (e.g. a future `ARCHITECTURE_DECISIONS_DATA_MODEL.md` / `ARCHITECTURE_DECISIONS_PROVIDERS.md`) over splitting by module number or by date — concern-based splits stay useful to a reader looking for "why is X shaped this way," while module- or date-based splits only help a reader who already knows when a decision was made.

## 2. How cross-references are maintained

- **Numbering only ever grows.** A new decision in `ARCHITECTURE_DECISIONS.md` gets the next sequential number (20, 21, ...); a new section in `ENGINEERING_STANDARD.md` gets appended, or — when it belongs logically beside an existing section rather than at the end — inserted as a lettered sub-section of the nearest relevant number (e.g. `§4A`, `§7A`, `§22A`, matching the precedent already established in `Module 03 Design.md`'s own `§7A`/`§9A` additions). Existing entries and sections are never renumbered, and no gap left by a removed entry is ever reused for a new, unrelated one.
- **Every cross-reference names a specific section number or document, never "see above" or "see the relevant section."** This is what makes a broken cross-reference (like this framework's own F2 finding) mechanically findable by grep rather than only by a human noticing something reads oddly.
- **When a document is split**, every existing cross-reference that pointed into the now-split document is updated at the same time as the split itself, not left dangling for a later pass to discover — the split is not considered complete until a full grep sweep for the old document's filename confirms zero remaining stale references.
- **A split document leaves a short pointer behind at its original location** stating what it was split into and why (the same "don't silently disappear content" principle `03 Metadata Extraction.md` follows as a superseded-but-not-deleted pointer to `Module 03 Design.md`), so a reader following an old memory of "this used to be one file" isn't left with a dead end.

## 3. How archives are handled

Consistent with the project's own non-negotiable (`CLAUDE.md`: never permanently delete anything, archive don't delete): a governance document is never deleted, even after a split or a major restructure. Superseded content moves to `~ARCHIVE~/` (mirroring how `Runtime/UAT/` results and the Module 03 release-cleanup archive were preserved rather than deleted) with a short `README.md` in the archive folder explaining what it is, when it was superseded, and what replaced it — the same pattern already established in `~ARCHIVE~/Module03_release_cleanup_2026-07-06/`.

A correction to a genuine error (a wrong cross-reference, a factual mistake) is fixed in place, without archiving the pre-correction version separately — archiving exists to preserve superseded *content and decisions*, not every incremental wording fix. The distinction: if a future reader would benefit from seeing what the document used to say (a real decision changed), archive it; if the old text was simply wrong and no one would ever want to see the wrong version again (a broken cross-reference, a typo), just fix it.

## 4. How historical decisions remain discoverable

- `ARCHITECTURE_DECISIONS.md`'s entries are never rewritten to look like they were obvious from the start (stated in that document's own header) — a decision that's later revised gets a **new**, dated entry explaining what changed and why, with the original entry left in place and a note added to it pointing forward to the newer entry. This preserves the actual history of reasoning, not just the current conclusion.
- `CHANGELOG.md` remains the chronological, dated narrative of *when* each decision/change happened, independent of `ARCHITECTURE_DECISIONS.md`'s organization-by-topic — the two documents answer different questions ("what do we currently believe and why" vs. "what happened, in order") and neither substitutes for the other.
- If `ARCHITECTURE_DECISIONS.md` is ever split by concern (§1), each resulting document keeps a one-line index at the top of `Governance/` (or a new `Governance/README.md`, if one becomes warranted) so a reader doesn't need to know in advance which specific file a given historical decision lives in.
- No governance document is ever reorganized silently — a restructure of `Governance/` itself follows the same review discipline as everything else in this framework: proposed, reviewed, approved, and logged in `CHANGELOG.md`, not applied ad hoc.
