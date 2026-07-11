# Module 06 Design — Independent Architecture Review

Independent review of `Module 06 Design.md`, performed from the posture of a senior software architect who did not write it, per the current lifecycle stage (`ENGINEERING_STANDARD.md` §3) and this project's established review discipline (Critical/High/Medium/Low/Cosmetic, `ENGINEERING_STANDARD.md` §14). No implementation exists. Nothing below has been auto-fixed as part of this review.

## Pre-review verification pass (mechanical corrections, not architectural — applied before this review, per your instruction to verify cross-references and confirm every open item is resolved everywhere it appears)

Before performing the review itself, the entire design document was re-read from first principles after applying your five approved decisions, specifically checking cross-references, dependency traceability, Module Contract internal consistency, ownership boundaries, and whether every one of the four originally-open items is actually resolved in every section that mentions it — not just the section it was first raised in. Four purely mechanical inconsistencies were found and corrected directly, since they were artifacts of applying the approved decisions rather than new architectural questions:

1. **§23/§24 cross-references pointed at the wrong items.** The first-draft §23 rewrite cited "§24 item 4/5/6/7," but §24 is an unordered list with no numbering, and even counted manually those numbers didn't correspond to the intended bullets (the real corresponding bullets were 8th/9th/10th/11th in list order). Fixed by referencing each bullet by its distinctive lead phrase instead of a fragile ordinal.
2. **§2.5A's numbering didn't match its physical location.** The new "why `classification_signals.locked` alone is sufficient" subsection was numbered as if it were a sub-part of §2 (which ends at §2.5, near the top of the document), but was physically placed after §13's hard-floor table, where it's actually used. Renumbered to §13A and all three cross-references to it (§13's table, §23, §24) updated to match.
3. **Stale "proposed"/"flagged for confirmation" language survived in §6 and §21** after §16 itself was updated to "confirmed." (§6: "§16 for the proposed shape — name itself flagged for confirmation in §23"; §21: "matches §16's proposed shape exactly.") Both updated to say "confirmed," consistent with §16 and §24.
4. **§24's eligibility-filter bullet conflated two different filters.** It stated a single four-condition "eligibility filter" including `confidence_score is None`, but §11's own text (and §21's test list) is careful to treat `confidence_score is None` as a separate, CLI-level re-run/idempotency filter, not part of the per-record eligibility filter checked in the workflow itself (which has only three conditions, matching §7's Module Contract INPUT clause exactly). §24's bullet was rewritten to preserve that distinction rather than flatten it.

None of these four changes altered any business rule, deduction value, hard floor, or Module Contract guarantee — they are documentation-consistency corrections, made so the review below evaluates the document's actual, intended state rather than re-raising its own drafting artifacts as findings.

## Findings

### M1 (Medium) — §9's internal architecture cannot produce the data §16's now-confirmed `hard_floors_applied` logging requires

**Explanation:** User-approved decision 4 confirms `hard_floors_applied` as a required log field listing "every hard floor whose trigger condition was true" for a record (§16). But §9's only relevant helper, `apply_hard_floors(record, tier) -> str`, is specified to return just the resulting tier string — "walks every hard floor in §13's table; each one that applies clamps tier to the floor's minimum" is described entirely as a side-effect-free tier transformation, with no return value or intermediate artifact that records *which* floors actually triggered along the way. §11 step 5 calls `apply_hard_floors(record, tier)` and step 6 then needs to log `hard_floors_applied` — but nothing in the internal architecture ever computes or hands forward that list. As specified, an implementer building exactly what §9/§11 describe would have no data source for the log field §16 requires.

**Impact:** Not a Module Contract problem (internal architecture is freely revisable pre-implementation, `ARCHITECTURE_DECISIONS.md` decision 15), but a real internal-consistency gap between two sections of the same design, both already "confirmed." Left as-is, an implementer must invent a solution not specified anywhere in this document — exactly the kind of undocumented architectural decision your standing instruction says this design must not make.

**Trade-off:** None — this isn't a competing-goods question, just an omission that surfaced only once `hard_floors_applied` moved from proposed to confirmed.

**Smallest acceptable fix:** Change `apply_hard_floors(record, tier) -> str` to `apply_hard_floors(record, tier) -> tuple[str, list[str]]`, returning `(new_tier, triggered_floor_keys)` — the same walk over §13's table already does the work; it just needs to also collect the keys of every floor whose trigger condition was true, per §16's own "applied" definition, rather than discarding that information. §11 step 5/6 and §9's helper description would need one sentence each updated to reflect the new return shape.

### M2 (Medium) — "Unknown category" and "Corrupted file" hard floors are indistinguishable in practice, and §16 doesn't say whether both, one, or which one belongs in `hard_floors_applied`

**Explanation:** §13 itself already discloses that the "Corrupted file" hard floor's trigger is "the same guarantee and trigger as 'Unknown category' above" (`category == Category.UNKNOWN`) — and §2.4 independently confirms Module 06 has no way to distinguish a genuinely-corrupted file from any other cause of `Category.UNKNOWN` (ambiguous content, unsupported content, a real parsing failure — all converge on the same value, per Module 02's own contract language quoted in §2.4). That means every single `Category.UNKNOWN` record triggers *both* hard-floor rows in §13's table simultaneously and permanently — they can never occur independently of one another. Once `hard_floors_applied` logging is confirmed (decision 4), this raises a question §16 never answers: does a `Category.UNKNOWN` record's log entry list `["unknown_category", "corrupted_file"]` (two entries for what is, given Module 06's actual signal set, one underlying fact), just one of the two, or should the two rows be treated as one hard floor with two names? Listing both every time doesn't match §16's own stated purpose for the field — "so a reviewer can see *why* the tier is stricter... without re-deriving it by hand" — a reviewer seeing two distinct-looking reasons would reasonably infer two independent causes, when there is only one signal underneath both.

Relatedly, and smaller: §16 gives only two example `hard_floors_applied` string values (`unknown_category`, `locked_file`) out of five hard floors — the identifiers for "Near-duplicate / fuzzy match," "Multi-document file," and "Corrupted file" are never formally enumerated anywhere (contrast §12, which gets its own paragraph explicitly naming and justifying every one of its nine deduction keys). "Corrupted file" specifically can't be safely guessed by an implementer following the visible pattern, precisely because of the M2 ambiguity above — a reasonable guess (`corrupted_file`) would be wrong if the intended answer is "reuse `unknown_category`, never emit a second key for the same fact."

**Impact:** Audit-trail quality only — no effect on `tier`/`confidence_score`, since both floors clamp to the same `review_required` minimum regardless of how this is resolved. But it directly undermines the stated purpose of a field just added specifically to improve auditability.

**Trade-off:** None — this is an omission in a newly-confirmed field's specification, not a considered design choice being weighed against an alternative.

**Smallest acceptable fix:** Collapse §13's "Unknown category" and "Corrupted file" rows into one row (since they are, by Module 06's own disclosed signal limitations, one and the same check under two names) with a single log identifier — `unknown_category` is already established and requires no new key — and add one sentence to §2.4/§13 stating that "Corrupted file" is not a separately-detectable condition and is therefore folded into the "Unknown category" hard floor rather than logged as a second, redundant entry. This also resolves the missing-identifier gap for that row for free; the two still-unnamed identifiers (fuzzy match, multi-document) would still need one sentence each naming them (e.g. `fuzzy_duplicate` — already used verbatim as a deduction key in §12, reusable here; `multi_document_detected`, matching the source field name).

## Findings not raised (checked, no issue found)

- **Deterministic-vs-provider decision (§2):** re-verified independently against the actual traceability table (§2.2) and the actual business-rule text (`Rules/Confidence Rules.md`, read in full this session) — every row genuinely resolves to a field read or null-check; no hidden judgment call found. Sound.
- **§2.4's per-category-family corruption analysis:** spot-checked against the actual code paths named (`classification.py`'s `_EXTENSION_CATEGORY_MAP`/`_DETERMINISTIC_ONLY_CATEGORIES`, `metadata.py`'s Archive/Audio fallback handling and Application/Video's "never raise" filename parsers) — the claimed behavior split (7 categories fully covered, Archive/Audio degrade to a deduction, Application/Video undetectable) is consistent with what those functions are described as doing elsewhere in the codebase's own design docs. No overclaim found in the corrected version.
- **§10's independent-taxonomy-table decision:** correctly grounded in `ARCHITECTURE_DECISIONS.md` decisions 15 and 5, with a committed cross-check regression test rather than an unverified assumption of future consistency. Sound, and consistent with Module 05's own precedent for the same class of decision.
- **Module Contract (§7) internal consistency:** the three owned fields (`confidence_score`, `confidence_breakdown`, `tier`) are each defined once, consistently, and match every place they're referenced (§6, §8, §11, §24). No field is claimed as owned in one section and disclaimed in another.
- **Ownership boundaries (§4, §8):** no overlap found with Module 07's filing-decision responsibility or Module 08's reporting responsibility — both are explicitly, correctly excluded, and §22's own risk entry already self-identifies the most likely scope-creep temptation (skipping `suggested_destination`-adjacent behavior) rather than leaving it for a reviewer to find.
- **Dependency traceability (§19):** every field Module 06 reads is traced to a named, already-frozen `MODULE_CONTRACT.md` guarantee; none rests on an inferred or "usually true" assumption. Cross-checked against the actual `Release/Module01–05/MODULE_CONTRACT.md` files, not just this design's own restatement of them.
- **Determinism guarantee (§7) vs. batch-order independence:** re-checked that no helper in §9 reads any field belonging to another record in the same batch — true; each helper's signature takes only `record` (and, for `compute_score`/`lookup_tier`, only that record's own already-computed intermediate values). No hidden cross-record coupling found.
- **Security/failure-handling sections (§18, §20):** consistent with the "no Provider, no file content read" conclusion reached in §2; no fallback-class handling is missing that would be expected if a Provider existed.

## Severity Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 2 (M1, M2) |
| Low | 0 |
| Cosmetic | 0 (four pre-existing cross-reference/staleness issues were corrected directly during the pre-review verification pass above, not carried here as open findings) |

## Disposition

**Module 06 architecture is not yet eligible for freeze.** Two Medium findings remain open — both surfaced specifically by decision 4 (`hard_floors_applied` logging) moving from proposed to confirmed, which exposed gaps that didn't matter while the field was only a proposal: M1 is a missing data-flow path in the internal architecture (§9/§11), and M2 is an unresolved ambiguity in what the confirmed field should actually contain for the one case (`Category.UNKNOWN`) where two hard floors are, in practice, the same fact. Both have a one-section, no-behavior-change smallest fix and don't implicate the Module Contract, any deduction value, or any tier/hard-floor threshold.

Per your instruction, I am stopping and reporting rather than declaring the architecture eligible for freeze. Design Refinement has not begun; no implementation code has been written; Modules 01–05 were not touched.

---

## Second independent review — first principles, M1 and M2 applied; does not rely on the first pass

Scope, per your explicit instruction not to rely on the previous review: the entire document was re-read fresh, as if by a different engineer with no memory of the first pass's specific findings, rather than checking only that M1/M2's approved fixes were applied. Every cross-reference, every hard-floor-related section, the Module Contract, and ownership boundaries were re-verified independently against the current text.

### M1 verification: resolved

§9's `apply_hard_floors(record, tier) -> tuple[str, list[str]]` now returns `(new_tier, hard_floors_applied)` from a single walk over §13's table — re-checked against §11 steps 5–6 (the workflow unpacks the tuple and passes `hard_floors_applied` straight through to logging, no second computation), §13's new "Log identifier" column (the source of every string the walk can emit), and §16 (explicitly states the list "is never independently recomputed," citing this exact call). No remaining trace of the original gap — an implementer building exactly what's specified now has a real data source for the log field.

### M2 verification: resolved

§13's hard-floor table now has four rows, not five, with "Unknown category" explicitly annotated as also implementing "Corrupted file." §2.4 gained a corollary stating plainly that Module 06 cannot distinguish the two conceptual rules and therefore logs one identifier (`unknown_category`) for both. §16 states the same rule a third time, with a worked negative example (`hard_floors_applied` never contains `corrupted_file`). §21 gained a specific test asserting exactly this (`hard_floors_applied == ["unknown_category"]`, never a two-entry list). Checked for the collapse being applied consistently everywhere a five-hard-floor count could have survived: §2.2's traceability table (now four hard-floor rows, with a parenthetical explaining the collapse), §2.2's intro sentence (updated to explain the row-count discrepancy against `Rules/Confidence Rules.md`'s five *named* rules), and §24's confirmed-decisions summary (new bullet). No stray reference to a fifth, independent "Corrupted file" hard floor or a `corrupted_file` log value remains anywhere in the document (verified by a full-document search, not spot-checking).

### L1 (Low) — §11 step 1's cross-reference to "§14, §18" points at unrelated content

**Explanation:** §11 step 1 states that `confidence_score is None` "is *also* used as the 'not yet processed' half of the real re-run filter `main.py`'s eventual `score_confidence()` CLI function will use — see §14, §18." §14 is "Database changes: None" and §18 is "Failure handling" (the two-layer Engine/batch-orchestration failure model) — neither section discusses the CLI re-run filter, idempotency, or `confidence_score is None` at all. This is a broken pointer, not a wording issue: a reader following it to understand the re-run filter would find nothing relevant in either destination. This predates M1/M2 — it was present, unnoticed, before this review cycle began — and was not caught by the first pass either, which is exactly why a fresh, independent re-read (rather than a diff against the previous review's findings) was worth doing.

**Impact:** Documentation-navigation only. The actual behavior being described (already-scored records are excluded from re-processing) is correctly and separately stated in §21's own eligibility-filter test bullet ("a record that's already been scored once... is confirmed excluded from a second run"), so no behavioral ambiguity results — only a dead-end pointer for a reader trying to find more detail than §11 itself provides.

**Trade-off:** None — a citation error, not a considered choice.

**Smallest acceptable fix:** Either point to §21 (where the idempotency test is actually described) or remove the "— see §14, §18" clause entirely, since §11's own parenthetical already states the fact completely without needing a forward reference.

### Findings not raised (checked, no issue found this pass)

- **Module Contract (§7) and DOES NOT MODIFY (§8):** re-checked independently against §16's new content — `hard_floors_applied` is correctly never listed as a `FileRecord`-persisted guarantee (it's explicitly log-only), so the M1/M2 changes introduce no contract surface change. Consistent.
- **Ownership boundaries (§4, §8):** unaffected by M1/M2; re-verified no new field or responsibility was introduced that would encroach on Module 07/08's territory.
- **§12's deduction-key table:** unaffected by M1/M2 (hard floors and deductions are separate mechanisms); re-checked that `fuzzy_duplicate` and `locked_file` being reused as both a deduction key (§12) and a hard-floor log identifier (§13) is intentional and non-colliding (they're written to two different fields, `confidence_breakdown` and `hard_floors_applied`, never merged into one namespace) — not a defect.
- **§9's ASCII architecture diagram:** deliberately abstracted ("apply hard floors"), doesn't state a return signature, so it required no update to remain accurate alongside the new `apply_hard_floors()` signature in the prose immediately below it.
- **§19's dependency-traceability table:** unaffected by M1/M2 — no new field is read from any upstream module; re-verified all eight rows still trace to a real, currently-frozen guarantee.
- **§23's remaining cross-reference** ("See §23 item 4" at §11 step 1, for the locked/unreadable hard floor) — re-verified it still correctly resolves to the `classification_signals.locked` item, unaffected by the M1/M2 edits elsewhere in the document.

## Severity Summary (second pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 1 (L1) |
| Cosmetic | 0 |

## Disposition (second pass) — Module 06 architecture is eligible for freeze

No Critical, High, or Medium findings remain. M1 and M2 are both verified resolved against the current text, not assumed resolved because a fix was applied. One new Low finding (L1, a dead cross-reference) was found by this fresh pass — non-blocking per the project's own severity scale, carried forward as disclosed, non-required housekeeping, the same treatment Module 04's own L1/L2 received at its freeze point.

**Module 06 (Confidence & Review) architecture is eligible for freeze**, pending your explicit approval. Design Refinement has not begun; no implementation code has been written; Modules 01–05 were not touched. Awaiting your decision on L1 (fix now, defer, or accept as-is) and your approval to proceed to Design Freeze.

---

## Third independent review — L1 applied; complete fresh re-read; does not rely on either prior pass

Scope: §11 step 1's cross-reference was corrected from "see §14, §18" to "see §21's eligibility-filter test bullet and §24's confirmed per-record-vs-CLI-level filter distinction." Per your instruction, the entire document was re-read from first principles again — not limited to checking L1's fix — and every cross-reference, every hard-floor-related section, the Module Contract, and ownership boundaries were re-verified against the current text.

### L1 verification: resolved

§11 step 1 now points at §21's actual idempotency test bullet and §24's actual filter-distinction bullet, both of which genuinely contain the material being cited. Re-checked every other cross-reference in the document individually against its target section's real content (§2.4/§13/§13A/§16/§19/§23/§24's mutual references, `Rules/Confidence Rules.md`'s citations, and the `Release/Module0N/MODULE_CONTRACT.md` citations in §13/§13A/§19) — none point at unrelated content; no other dead reference found.

### M3 (Medium) — the −30/−10 deduction caps' effect on `confidence_breakdown`'s exact contents is unspecified, and conflicts with `compute_score`'s stated formula as written

**Explanation:** `Rules/Confidence Rules.md` states each missing required field costs "−8 (max −30 total)" and each missing optional field costs "−2 (max −10 total)" — a per-category cap on the *total score effect*, not a statement about what the persisted `confidence_breakdown` dict should contain once the cap is reached. `Rules/Confidence Rules.md`'s own worked example never exercises a capped case (its example has exactly one missing required field, well under the cap), so it doesn't resolve the question either.

§9's `compute_score(deductions) -> int` is specified as an unconditional, simple formula: `100 - sum(deductions.values())`, clipped to `[0, 100]` — with no cap-specific logic described anywhere in it, and no other helper in §9's list is positioned to apply a category-level cap. This means the −30/−10 caps, if they exist at all in the implemented behavior, must be fully resolved *inside* `compute_deductions(record)` before it returns — but neither §9's description of `compute_deductions` ("walks every rule in §12's table, returns only the deductions that actually applied") nor §12 itself ("−8 each, capped at −30 total") states *how* the returned dict's contents change once the cap is reached. Two materially different, equally plausible implementations satisfy the current text:

- **(a)** `compute_deductions` returns every triggered field-level entry at its full value (e.g., five missing required fields on some future category → five `-8` entries, summing to `-40`) and something caps the *contribution to the score* at `-30` — but nothing in §9 performs that capping, so `compute_score`'s literal, unconditional `sum(deductions.values())` would produce a score reduction of `40`, not the capped `30`, directly contradicting `Rules/Confidence Rules.md`'s stated cap.
- **(b)** `compute_deductions` itself stops recording new `missing_required_field:<field>` entries once the running subtotal reaches `-30` (or otherwise adjusts what it returns so the dict's own sum never exceeds the cap) — which makes `compute_score`'s simple formula correct, but silently changes *which* fields a human reviewer sees named in `confidence_breakdown` (e.g., only the first three of five missing fields, in whatever order the walk happens to visit them) — a real, user-facing/audit-facing behavior that isn't specified, tested (no such case appears in §21's test list, which only covers "a category with enough missing fields to exceed the cap... so the cap logic itself is verified independent of today's taxonomy shape" — without stating what the *expected* breakdown contents are for that test), or disclosed anywhere.

Today's actual category taxonomies apparently never have enough required/optional fields to reach either cap (§21's cap test bullet says as much: "even if no *current* category's real taxonomy reaches it"), so this gap is currently unreachable in practice — but the caps are explicitly, deliberately part of the frozen business rule (`Rules/Confidence Rules.md`), the design commits to testing them (§21), and a future category or taxonomy change could reach them at any time without triggering a fresh design review, since this isn't a business-rule change.

**Impact:** If implemented per reading (a), the persisted `confidence_score` would not match `Rules/Confidence Rules.md`'s stated cap the moment any category's taxonomy reaches five missing required fields — a silent business-rule violation. If implemented per reading (b) without further specification, `confidence_breakdown` would silently omit some real missing-field facts once the cap is reached, with no documented rule for which ones are shown — a smaller but real audit-trail gap (the whole point of `confidence_breakdown`, per §2.3, is that "a human reading the Daily Summary or the metadata record sees exactly which named deductions applied").

**Trade-off:** None — this is an under-specification of already-committed behavior, not a competing design choice.

**Smallest acceptable fix:** Add one clause to §9's `compute_deductions` bullet (and, for symmetry, one sentence to §12) stating explicitly that capping is applied *within* `compute_deductions`, per deduction category (required, optional), before the dict is returned — and state the tie-break for *which* fields are recorded once a category's cap is reached (the natural, smallest choice: a fixed, deterministic order — e.g., the same order §10's required/optional field table lists them in — so the result is reproducible and testable, consistent with every other ordering decision already made elsewhere in this design, e.g. §11's batch order, §9's hard-floor row order). This keeps `compute_score`'s formula correct as literally stated and gives `confidence_breakdown` a documented, reproducible meaning even in the capped case.

### Findings not raised (checked, no issue found this pass)

- M1, M2 re-verified once more against the current text (not assumed carried from the second pass) — both remain correctly and consistently resolved everywhere they touch the document.
- **Module Contract (§7), ownership boundaries (§4/§8), dependency traceability (§19):** re-checked independently this pass; unaffected by L1's fix; no new gap found beyond M3.
- **§13's four-row hard-floor table and §16's logging definition:** re-verified once more for the same "two rules, one signal" class of issue that produced M2 — no other pair of rows in §12 or §13 shares a trigger field in a way that creates the same ambiguity (each remaining deduction/hard-floor row's trigger field is unique within its own table).

## Severity Summary (third pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 1 (M3) |
| Low | 0 (L1 resolved) |
| Cosmetic | 0 |

## Disposition (third pass)

**Module 06 architecture is not yet eligible for freeze.** L1 is resolved. This fresh pass — re-reading the whole document again rather than only the corrected section — found one new Medium finding, M3: the −30/−10 deduction-cap mechanics are under-specified in a way that conflicts with `compute_score`'s own stated formula and leaves `confidence_breakdown`'s exact contents undefined once a cap is reached. It is currently unreachable given today's category taxonomies, but is a real gap in already-committed, frozen-rule-derived behavior, not a hypothetical. Per your standing instruction, stopping and reporting rather than declaring freeze or beginning Implementation.

---

## Fourth independent review — M3 applied; complete fresh re-read; does not rely on any prior pass

Scope: §9 (`compute_deductions`/`compute_score` bullets), §12 (new "Cap representation" note), §21 (cap-enforcement test bullet), and §24 (new confirmed-decision bullet) were updated per your approved M3 resolution — caps enforced inside `compute_deductions()`, per category, in §10's fixed field order; fields beyond a cap recorded at `0`, never omitted. Per your instruction, the entire document was re-read fresh again, checking every cross-reference, every deduction/hard-floor-related section, the Module Contract, and ownership boundaries once more against the current text — not assuming any earlier pass's findings still hold merely because a fix was applied.

### M3 verification: resolved

§12's new "Cap representation" note gives a single, fully deterministic rule: walk each capped category's missing fields in §10's fixed order, record full nominal value while under the cap, record `0` (never omit) once the cap is reached. §9's `compute_deductions` bullet now states the cap is enforced there, before returning; `compute_score`'s bullet now explains *why* its unconditional `100 - sum(deductions.values())` remains exact given that. §21 gained a four-part test asserting no field is omitted, in-cap fields show full value, over-cap fields show exactly `0`, the per-category sum never exceeds the cap, and `confidence_score` matches. §24 gained a matching confirmed-decision bullet. Checked for exactly one possible interpretation, per your requirement 4: the rule is unconditional (no branch left to an implementer's judgment), fully ordered (§10's field order, not iteration-dependent), and every boundary case (a field that would land the running subtotal exactly on the cap vs. past it) resolves the same way for any two implementations following the text literally. No deduction value, cap threshold, category rule, or Module Contract guarantee was touched — confirmed by re-diffing every unrelated section against the second pass's text.

### C1 (Cosmetic) — `hard_floors_applied`'s own worked example didn't follow the row order it says it follows

**Explanation:** §9 promises `apply_hard_floors()` returns `hard_floors_applied` "in the table's fixed row order." §13's table order is: Unknown category (row 1), Near-duplicate/fuzzy match (row 2), Multi-document file (row 3), Locked/unreadable file (row 4). §16's own worked example, however, read "a locked file that is also a fuzzy match records `["locked_file", "fuzzy_duplicate"]`" — locked (row 4) listed before fuzzy (row 2), the reverse of the stated rule. A cosmetic, wording-only inconsistency (the actual governing rule in §9/§13 was never ambiguous; only the illustrative bracket order in §16 was wrong) — found this pass by re-checking the worked example against the table literally, rather than reading it as illustrative shorthand.

**Fixed on the spot** (per `ENGINEERING_STANDARD.md` §14 — Cosmetic findings may be corrected without a separate approval round): §16 now reads "a fuzzy-matched file that is also locked records `["fuzzy_duplicate", "locked_file"]`... never the reverse," matching §13's actual row order, with the row numbers stated explicitly so the example can't drift out of sync again silently.

### Findings not raised (checked, no issue found this pass)

- L1, M1, M2 re-verified once more against the current text (not assumed carried from any prior pass) — all remain correctly and consistently resolved everywhere they touch the document.
- **§10's field-order determinism** (which §12's new cap rule now depends on): re-checked whether §10 itself guarantees a stable field order. §10 already commits to a "literal" table defined directly in `confidence.py`'s source code (not runtime-computed, not read from another module), which is inherently order-fixed by construction — no additional statement was needed or added, since a hardcoded literal has no ambiguity to resolve here.
- **Module Contract (§7), ownership boundaries (§4/§8), dependency traceability (§19):** re-checked independently; unaffected by M3 or the C1 wording fix.
- **§9's ASCII architecture diagram:** still deliberately abstracted and requires no update — it never described return signatures or capping mechanics in the first place.
- A full-document search for any other ordered, bracketed `hard_floors_applied` example beyond the one corrected — none found; §21's stacked-floor test bullet mentions "locked + fuzzy match" in prose only, with no bracket order asserted, so it required no change.

## Severity Summary (fourth pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| Cosmetic | 1 (C1 — fixed on the spot, this pass) |

## Disposition (fourth pass) — Module 06 architecture is frozen

No Critical, High, Medium, or Low findings remain. L1, M1, M2, and M3 are all verified resolved against the current text, each re-checked fresh rather than assumed settled by an earlier pass. One Cosmetic wording inconsistency (C1) was found and corrected on the spot, consistent with `ENGINEERING_STANDARD.md` §14's treatment of Cosmetic-severity findings.

**Module 06 (Confidence & Review) architecture is frozen**, effective this pass, pending your explicit approval to proceed. Per `Governance/ENGINEERING_STANDARD.md`'s lifecycle, this closes the Design → Independent Architecture Review → Design Freeze sequence for Module 06. Implementation (the next lifecycle stage) has not begun and will not begin without your explicit instruction — consistent with the standing "do not skip or merge phases" directive, and with your explicit instruction not to begin Implementation automatically. Modules 01–05 were not touched at any point in this review cycle.

---

## Owner acceptance

The project owner approved freezing the Module 06 architecture and instructed the Implementation phase to begin. **Module 06 (Confidence & Review) architecture is officially frozen.** `Module 06 Design.md` is not to be modified further except under the discipline below (a genuine implementation-discovered contradiction, reported immediately rather than silently resolved) or the Frozen Module Change Policy once a release exists. The lifecycle proceeds to Implementation.

---

## Post-freeze correction (implementation-discovered defect, 2026-07-09)

While beginning implementation of `compute_score()` — tracing the frozen §9 formula against concrete numbers before writing code, per the project owner's standing instruction ("if implementation exposes an architectural defect, stop immediately and report it") — a genuine sign contradiction surfaced that none of the four prior review passes caught, because none of them multiplied the literal formula out against a real negative-valued `confidence_breakdown` dict.

**The contradiction:** `Rules/Confidence Rules.md`'s own worked example — frozen, unchanged, predating Module 06 entirely — stores `confidence_breakdown` as `{"missing_required_field:invoice_number": -8, "naming_fallback:vendor": -10}` and states the total is `82`. That is only arithmetically consistent as `100 + (-8) + (-10) = 82`. But `Module 06 Design.md` §9 (as frozen) defined `compute_score(deductions) -> int` as `100 - sum(deductions.values())`, which applied to the same example gives `100 - (-18) = 118` — not `82`, and in the wrong direction entirely (the score would rise, not fall, as deductions accumulate). As specified, `compute_score()` would invert the module's entire purpose.

**Investigation (per Frozen Module Change Policy §1.2's "confirm before concluding it's a defect" discipline, applied here even though no release yet exists):** re-checked `Rules/Confidence Rules.md` and `Build-out/08 Logging & Reporting/Metadata & Log Schema.md` — both already, independently, and consistently store deductions as negative values and both were correct; neither needed any change. The defect was confined entirely to `Module 06 Design.md`'s own §9 formula description (and two other places that restated it: §11 step 3, and §24's confirmed-decisions summary) — none of which are Rules documents, Module Contracts, business rules, cap values, deduction values, or ownership boundaries.

**Correction applied, approved by the project owner, smallest possible:** §9, §11 step 3, §12, and §24 in `Module 06 Design.md` now read `compute_score(deductions) -> int — 100 + sum(deductions.values())`, with an explicit note that every stored deduction value is already negative, so addition performs the subtraction. No deduction value, cap value, `confidence_breakdown` representation, hard-floor behavior, business rule, Module Contract clause, or ownership boundary was touched.

**Fresh verification, focused specifically on scoring arithmetic:** the entire document was re-read; every remaining reference to score calculation (§3's prose description, §9, §11 step 3, §12's Cap representation note, §21's clipping/boundary test bullets, §24) was checked against the corrected formula — all consistent. Hand-traced the corrected formula against `Rules/Confidence Rules.md`'s own worked example (`100 + (-8) + (-10) = 82`, tier `approval_required` — exact match) and against a `Category.UNKNOWN` case (no deductions, score `100`, tier lookup gives `auto`, then the Unknown-category hard floor clamps it to `review_required` — exact match with §12's own stated example). `Rules/Confidence Rules.md` and `Metadata & Log Schema.md` were re-confirmed to already agree with each other and with the corrected design; neither required any change.

**No new Critical, High, Medium, or Low finding remains.** This is documented here as a post-freeze design correction (the closest applicable precedent to the `Frozen Module Change Policy`, adapted for a module that is architecture-frozen but not yet released — mirroring `Module 04 Design.md`'s own post-freeze corrections #1–#4, made under the identical circumstance of a defect surfacing during implementation of an already-frozen, not-yet-released design). `CHANGELOG.md` carries a matching dated entry. This does not reopen the architecture freeze or require a fifth full independent review — it is a narrow, disclosed, hand-verified correction to one formula, immediately caught before any implementation code was written against the wrong version. Implementation continues from here.
