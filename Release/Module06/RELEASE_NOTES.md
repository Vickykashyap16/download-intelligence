# Release Notes — Module 06 (Confidence & Review)

```
Pipeline Version:  0.6.0
Module Version:    1.0.0
Date:              2026-07-11
Status:            Frozen, approved, feature-complete
```

See `Release/VERSIONS.md` for how Pipeline Version and Module Version relate (each module versions independently; the pipeline number tracks overall project maturity, not a function of module numbers).

**Deployment model, stated plainly:** like Modules 04/05, there is no provider of any kind (`Module 06 Design.md` §2, confirmed across four independent Design Review passes). Every decision Module 06 makes — every deduction, every hard floor, every tier lookup — is a direct field read or null-check against an already-computed upstream signal, never a new judgment call. Module 06 is Production Ready for both interactive Claude-assisted operation and unattended/scheduled operation identically. See `MODULE_CONTRACT.md`'s "Provider boundary" section.

This is the sixth module of the Downloads Intelligence pipeline. It takes every `FileRecord` Module 05 has processed and computes a `confidence_score` (0–100), a `confidence_breakdown` (the named deductions that produced it), and a `tier` (`auto` | `approval_required` | `review_required`) that Module 07 will use to decide whether a file may be filed automatically, filed after a one-click confirmation, or must be left untouched pending human review. It never re-examines file content, never moves or renames a file, and never writes to `Runtime/Reports/`.

## Features implemented

- `score_confidence_batch()` (batch orchestration: deterministic `discovered_at`/`file_id` ordering, per-record eligibility filter, persistence, logging) → `ConfidenceEngine` (per-file decision-making: `compute_deductions()` → `compute_score()` → `lookup_tier()` → `apply_hard_floors()`).
- All nine of `Rules/Confidence Rules.md`'s deductions: `ambiguous_classification` (−15), `no_extractable_text` (−30), `missing_required_field:<field>` (−8 each, capped −30), `missing_optional_field:<field>` (−2 each, capped −10), `naming_fallback:<field>` (−10 each), `fuzzy_duplicate` (−20), `version_conflict` (−25), `non_english_content` (−10), `locked_file` (−40).
- All four hard floors (five business-rule names, one merged pair — see below): `unknown_category` (also implements "Corrupted file" — one trigger, one identifier), `fuzzy_duplicate`, `multi_document_detected`, `locked_file` — each clamping `tier` down only, never up, applied after the arithmetic tier lookup.
- `compute_score(deductions) -> int` = `100 + sum(deductions.values())`, clipped to `[0, 100]` — every stored deduction value is already negative, so addition performs the subtraction (see "Bugs fixed" below for the post-freeze correction that established this).
- Independently-defined required/optional field taxonomy (matching, never importing, `pipeline/metadata.py`'s real constants), cross-checked by a dedicated regression test.
- The −30/−10 deduction caps enforced inside `compute_deductions()` itself, per category, in a fixed field order: full nominal value while under the cap, `0` — never omitted — once the cap is reached, so `confidence_breakdown` stays fully truthful and auditable even when capped.
- `apply_hard_floors()` returns `(new_tier, hard_floors_applied)` from a single walk over the four-row hard-floor table — the tier-clamping decision and the `hard_floors_applied` log field are two views of the same computation, never independently derived.
- No new `FileRecord` fields or Signals dataclass needed — `confidence_score`/`confidence_breakdown`/`tier` already existed as reserved plain-type fields since Module 01's schema was first drafted; this release is the first to actually populate them.
- CLI wiring (`src/main.py`'s `score_confidence()`) — filters to discovered, classified, named, not-yet-scored records, runs `score_confidence_batch()`, and prints a per-file score/tier summary plus a tier-count breakdown.

## Bugs fixed

One post-freeze design correction and one documentation-completeness correction cycle were applied during this module's lifecycle, all documented inline with dated, non-destructive addenda (see `CHANGELOG.md` for the full stage-by-stage history):

- **Post-freeze design correction (discovered before any implementation code was written, 2026-07-09).** `Module 06 Design.md` §9 (as frozen) defined `compute_score(deductions) -> int` as `100 - sum(deductions.values())`, which — traced against `Rules/Confidence Rules.md`'s own worked example (`{"missing_required_field:invoice_number": -8, "naming_fallback:vendor": -10}` → `82`) — gives `118`, not `82`, inverting the module's entire scoring direction. Corrected to `100 + sum(deductions.values())` in all four places the formula was restated (§9, §11, §12, §24), with an explicit note that stored deduction values are already negative. No deduction value, cap value, hard-floor behavior, or business rule was touched.
- **Documentation-completeness correction (discovered during the Module 06 Release Audit, 2026-07-11): no written record of the Independent Implementation Audit existed anywhere,** despite the stage having actually occurred (`test_confidence.py`'s own docstrings cite two of its findings by name). Reconstructed from surviving evidence — see `IMPLEMENTATION_AUDIT.md` — with two Medium findings (M1: the design-committed "every deduction simultaneously" test was missing; M2: the design-committed determinism test only checked log order, not output values), both resolved, both tests present and passing in the current suite.
- **Documentation-completeness correction (discovered during the Module 06 Release Audit, 2026-07-11): `Release/VERSIONS.md`'s Module 06 status row was stale,** still reading "Not started" despite Module 06 having completed Design, four Design Reviews, Implementation, Implementation Audit, Integration Testing, and a full UAT restart. Corrected: Status column updated, a new dated History entry appended (not an edit to the existing Module 01 entry — history preserved).
- **Missing-evidence correction (discovered during the Module 06 Release Audit's PCV Check 12, 2026-07-11): no measured performance number existed for Module 06.** Resolved exactly per Module 05's own Release Audit Finding F3 precedent: a real 75-file `Tests/Large Batch/` measurement through the real Module 01→06 chain, isolated storage, instant fixed-answer fake providers for Modules 02/03. Measured **40.122 seconds**, versus Module 05's own 39.711-second baseline for the same dataset through Module 01→05 — a +1.0% difference, no order-of-magnitude regression. No implementation code was changed to obtain this measurement.

Two Medium findings were found and resolved during the reconstructed Independent Implementation Audit itself (see `IMPLEMENTATION_AUDIT.md`, both design-committed §21 test-coverage gaps, not behavioral defects):
- The "every deduction simultaneously" test §21 committed to was missing — added (`test_all_nine_deduction_rules_simultaneously_with_cap_enforcement`).
- The determinism test §21 committed to only checked log-line order, not output values — added (`test_batch_deterministic_order_reversed_input_produces_byte_identical_field_values`).

Separately, a genuine Critical defect was found in **Module 01** (not Module 06) during Module 06's own UAT idempotency check — see "Breaking changes" below and `Release/Module01/RELEASE_NOTES.md`'s "Post-freeze correction #1" for the full record.

## Breaking changes

**None to Module 06's own contract.** This is the sixth module in the pipeline; Modules 01–05's contracts are unaffected by Module 06's own work — Module 06 only ever reads their fields, never rewrites them (see `MODULE_CONTRACT.md`). `confidence_score`/`confidence_breakdown`/`tier` already existed as reserved, unpopulated `FileRecord` fields since Module 01's schema was first drafted; this release is the first to actually populate them.

**Note on a dependency's own breaking-adjacent change:** Module 06's UAT discovered a genuine, Critical, pre-existing defect in the already-released Module 01 (re-scanning an already-processed file silently discarded every downstream module's work). This was resolved as **Module 01's own** post-freeze correction under `Governance/FROZEN_MODULE_CHANGE_POLICY.md` — a PATCH-level release (`v1.0.0` → `v1.0.1`) that clarified, rather than broke, Module 01's existing "never touches downstream fields" guarantee. It is not a Module 06 breaking change; it is disclosed here because Module 06's own UAT is what surfaced it. See `Release/Module01/RELEASE_NOTES.md`.

## Improvements

- Design-phase process at the same rigor as Modules 02–05: an explicit architectural decision review (deterministic vs. provider-derived, §2), followed by four independent Design Review passes that found and resolved 3 Medium findings (M1: hard-floor logging data flow; M2: Unknown category/Corrupted file identifier collision; M3: deduction-cap representation) and 1 Low (a dead cross-reference) before freeze, plus 1 Cosmetic fixed on the spot.
- Independent Implementation Audit (reconstructed record, `IMPLEMENTATION_AUDIT.md`) found and resolved 2 Medium test-coverage gaps against the design's own §21 commitments.
- Integration Testing (`Tests/Module 06 Integration Test Plan.md`) ran a real six-module batch across 8 sections (functional, logging, serialization, CLI wiring, CLI-level idempotency, cross-module contract, determinism, regression) — 22/22 cases passed, zero implementation defects, two harness-authoring errors found and corrected (not module defects).
- UAT ran twice: Run 1 stopped immediately on discovering a genuine, real, Critical defect — in Module 01, not Module 06 — per the standing instruction; a full restart from Run 1 (a genuine rebuild, not a resume), after Module 01's post-freeze correction, completed cleanly and additionally verified idempotency (the exact scenario Run 1 failed on) and correct downstream-field reset on genuine content change.
- A real, measured performance number was obtained during the Release Audit (PCV Check 12): 75 synthetic files through the real Module 01→06 chain in **40.122 seconds**, a +1.0% difference against Module 05's own 39.711-second baseline.
- A final independent Release Audit (`RELEASE_AUDIT.md`) covering all 13 `Governance/PIPELINE_CONTRACT_VERIFICATION.md` checks plus a qualitative review, performed across three restart cycles (each surfacing and resolving one genuine documentation/evidence finding) before converging on a clean, thirteen-of-thirteen pass with zero Critical/High/Medium/Low findings remaining.
