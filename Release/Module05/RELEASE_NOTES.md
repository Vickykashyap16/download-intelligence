# Release Notes — Module 05 (Naming & Destination)

```
Pipeline Version:  0.5.0
Module Version:    1.0.0
Date:              2026-07-09
Status:            Frozen, approved, feature-complete
```

See `Release/VERSIONS.md` for how Pipeline Version and Module Version relate (each module versions independently; the pipeline number tracks overall project maturity, not a function of module numbers).

**Deployment model, stated plainly:** like Module 04, and unlike Modules 02/03, there is no provider of any kind (`Module 05 Design.md` §17). Every decision Module 05 makes (which template applies, filling it from already-extracted fields, string sanitization, within-batch collision suffixing, category-to-folder lookup, override precedence) is a computation over already-structured data. Module 05 is Production Ready for both interactive Claude-assisted operation and unattended/scheduled operation identically — there is no judgment-dependent behavior that degrades or falls back differently between the two. See `MODULE_CONTRACT.md`'s "Provider boundary" section.

This is the fifth module of the Downloads Intelligence pipeline. It takes every `FileRecord` Module 04 has processed (`status == "discovered"`, including `Category.UNKNOWN`) and computes a human-readable `suggested_name` and a `suggested_destination` folder, using the confirmed per-category naming templates (`Rules/Naming Rules.md`) and folder routing rules (`Rules/Folder Rules.md`), including Module 04's exact-duplicate/superseded-version overrides. It never moves or renames a real file — that remains reserved for Module 07 — and never touches the filesystem or the real destination library in any way.

## Features implemented

- Per-category filename template filling from `extracted_metadata`, using the confirmed real field mappings (`Module 05 Design.md` §10/§11) for all twelve categories, including `Category.UNKNOWN` (unlike Module 03, which skips it).
- Whitelist-only sanitization (`sanitize_filename()`): internal whitespace converts to `_` before the whitelist filter runs (post-freeze correction #1 — see "Bugs fixed" below), letters/digits/underscore/hyphen pass through, everything else is stripped; naive per-underscore-segment Title_Case (`str.capitalize()`, e.g. "NDA" → "Nda", an explicitly accepted cosmetic cost); iterative longest-segment truncation enforcing the ~80-character soft cap without ever leaving a stray or doubled underscore.
- Within-batch filename collision resolution (`_2`/`_3` suffixing), keyed on `(destination, name)` so identical names at different destinations never collide — real-filesystem collision detection against the destination library is explicitly out of scope for this module (§9), deferred to Module 07's execution-time authoritative check.
- Destination resolution (`resolve_destination()`) — category → folder mapping (`Rules/Folder Rules.md`) with Module 04's `duplicate_of`/`version_rank` override precedence taking effect regardless of category, mirroring Module 04's own "exact-duplicate detection runs regardless of category" precedent. Takes no `tier` parameter — confirmed dropped from the pre-existing scaffold stub's signature, since `tier` (Module 06's output) does not exist yet at Module 05's position in the strict linear pipeline; the "don't move a `review_required` file" gate is deferred to Module 07's execution-time check.
- New `NamingSignals` dataclass (`src/models/naming.py`), mirroring `ClassificationSignals`/`DuplicateSignals`'s established pattern — records which template fields fell back to a placeholder value, using the field's real taxonomy name (never a synthetic label), for Module 06's future `-10`-per-fallback deduction to consume.
- Deterministic, defined batch-processing order (`discovered_at` ascending, `file_id` lexicographic tie-break, identical to Module 04's own established order) so re-running the same batch, or the same batch in a different input order, always produces the same result, including which record receives a collision suffix.
- Fully deterministic — no Provider layer at all, the same architectural departure Module 04 established for itself (§17).
- CLI wiring (`src/main.py`'s `suggest_naming()`) — filters to discovered, classified, not-yet-named records (correctly including `Category.UNKNOWN`), runs `suggest_naming_and_destination_batch()`, and prints a summary (fallback count, collision count, per-override counts) read back from the action log.

## Bugs fixed

One post-freeze design correction was applied during this module's lifecycle, approved by the project owner and documented inline in `Build-out/05 Naming & Destination/Module 05 Design.md` with a dated, non-destructive addendum (see `CHANGELOG.md` for the full stage-by-stage history):

- **Post-freeze correction #1 (discovered during UAT, Finding UAT-1 — Medium; independently confirmed a design-completeness gap, not an implementation defect).** `sanitize_filename()`'s whitelist-only character filtering stripped internal whitespace entirely rather than converting it to `_`, so real, multi-word field values (vendor names, counterparties, candidate names, titles) lost their word boundaries — `"Northwind Traders"` → `"Northwindtraders"` — affecting 8 of 17 (47%) real files discovered during the UAT run that found it. The implementation faithfully matched the frozen design's own §12 text; the specific, high-impact consequence for multi-word real-world content was simply never separately weighed during the original design review. Fixed: whitespace now converts to a single `_` before the whitelist filter runs, as an explicit new first step; every other confirmed §12 rule is unchanged.

Five findings (3 Medium, 2 Low) plus one Cosmetic observation were also found and resolved during the first Independent Implementation Audit, before Integration Testing began — see `IMPLEMENTATION_AUDIT.md`:
- `naming_signals.fields_fell_back` recording synthetic, non-taxonomy field names for Video/Resume's fallback cases (M1) — fixed to record real field names.
- `_truncate_longest_segment()`'s single-pass truncation not guaranteeing the ~80-character cap when overflow exceeded the single longest segment's own length, and able to leave a stray/doubled underscore (M2) — fixed to be iterative, with empty segments dropped before the final join.
- Five categories missing committed fallback-path test coverage (M3) — nine tests added, closing every gap.
- A weak, hedged test assertion on a fully deterministic outcome (L1) — fixed to the single correct assertion.
- Duplicated override-detection logic between `resolve_destination()` and `NamingEngine.suggest_file()` with no drift guard (L2) — the duplication was removed entirely via a shared `_determine_override()` helper.

Four Medium findings plus one Cosmetic finding were found and resolved during the final Release Audit — all documentation-completeness or missing-evidence gaps, no behavioral or contract defect; see `RELEASE_AUDIT.md`.

## Breaking changes

None. This is the fifth module in the pipeline; Modules 01, 02, 03, and 04's contracts are unaffected — Module 05 only ever reads their fields, never rewrites them (see `MODULE_CONTRACT.md`). `suggested_name`/`suggested_destination` already existed as reserved, unpopulated `FileRecord` fields since Module 01's schema was first drafted; this release is the first to actually populate them. `naming_signals` is a genuinely new field, additive only. Unlike Module 04, Module 05 has no disclosed side effect on any other record — its within-batch collision handling reads other records in the same batch but never writes to them.

## Improvements

- Design-phase process at the same rigor as Modules 02–04: an explicit twelve-item architectural decision review, followed by a fresh independent design review that found and resolved one Medium finding (`naming_signals`'s contract precision) before freeze.
- Independent Implementation Audit performed three times: the first pass found 3 Medium + 2 Low + 1 Cosmetic findings (fallback field-name accuracy, truncation correctness, missing committed test cases, a weak test assertion, duplicated override logic, a type-annotation inaccuracy), all resolved and re-verified clean on the second pass; the third pass verified post-freeze correction #1's fix from first principles, including mutation testing to confirm the new regression tests are genuinely load-bearing.
- Integration Testing (`Build-out/05 Naming & Destination/Module 05 Integration Test Plan.md`) ran a real five-module batch across nine sections (functional, cross-module contract, collision handling, override behavior, determinism, serialization, logging, CLI orchestration, regression) — zero implementation defects, all cases passing on first execution.
- UAT ran twice: an initial run stopped immediately on discovering a genuine, real finding (Finding UAT-1) rather than continuing or auto-fixing, per the standing instruction; a full restart from Run 1, after the design-correction cycle, completed cleanly and additionally verified idempotency and a dedicated 13-case adversarial sanitization pass not reached by the original run — archived at `Runtime/UAT/Module05_UAT_2026-07-09_041725/`.
- A real, measured performance number was obtained post-audit (Release Audit finding F3): 75 synthetic files through the real Module 01→05 chain in **39.711 seconds**, recorded in `Build-out/05 Naming & Destination/Module 05 Integration Test Plan.md`'s Performance addendum.
- A final independent Release Audit (`RELEASE_AUDIT.md`) covering all 13 `Governance/PIPELINE_CONTRACT_VERIFICATION.md` checks plus a qualitative review, performed twice (first pass found 4 Medium + 1 Cosmetic documentation/evidence gaps; second pass, after remediation, found all 13 checks passing and no Critical/High/Medium finding remaining) before this release package was generated.
