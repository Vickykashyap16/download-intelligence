# Module 04 Post-Freeze Design Correction — PT-003 (False-Positive Version-Chain Grouping)

**Status:** Design phase only. Not implemented. No `src/` file has been modified in producing this document.
**Revision:** 2 (2026-07-23) — revised in response to the independent design review (`Module 04 Post-Freeze Design Review — PT-003.md`, Round 1), which returned **APPROVE WITH CHANGES**. See the Design Revision Summary immediately below for exactly what changed and why. The original Round 1 findings (E1, S1) are both addressed in this revision; that review document is left as the historical record of Round 1 and is not rewritten. A second, independent review of this revision (`Module 04 Post-Freeze Design Review — PT-003 (Round 2).md`) returned **APPROVE**. This design package is approved; implementation has not begun and requires separate authorization.
**Governed by:** `Governance/FROZEN_MODULE_CHANGE_POLICY.md` — Module 04 is Frozen and released at v1.0.0 (`Release/VERSIONS.md`), so this is a post-freeze change, not fresh implementation. Process followed per `ENGINEERING_CHANGE_PLAYBOOK.md` §3 (Medium-severity tier: full ten-section package, one independent review pass — now in its second pass following the requested revision).
**Authorized by:** `PROJECT_BACKLOG.md` §3 ("Priority 1 — Next real engineering cycle"), approved by the project owner for a design-only cycle. Scope: PT-003 only. Explicitly not authorized: implementation, architectural redesign, or any change to PT-002/Module 02 (already closed).
**Does not modify:** `src/pipeline/duplicate_detector.py`, `src/storage/database.py`, or any other production code. Every code excerpt below is quoted from the real, current, unmodified file for reference.

---

## Design Revision Summary

This section lists every change made to this document in response to the Revision 1 independent design review, in the order the review raised them. Nothing below this section describes work that has been implemented — it describes what changed in the design itself.

1. **Resolved E1 (Medium — identical-normalized-name branch exposed to generic-filename false positives).** The reviewer found that the original Selected Design's identical-name branch added no real corroborating value (an identical name already trivially satisfies the existing `fuzz.ratio() >= 90` condition) and was itself exposed to the exact class of false positive PT-003 exists to fix — two unrelated files sharing a generic default filename (`invoice.pdf`, `image.jpg`, `document.pdf`). **Change made:** §6 (Selected Design) now requires the identical-name branch to also pass a size-proximity check — confirmed, via a fresh read of `src/models/file_record.py` line 36, that `size_bytes: Optional[int]` is already a captured field on every `FileRecord`, so this uses existing metadata with no new extraction work. The revised §6 explains precisely why this narrows the gap, and explicitly discloses what it does not close (see §6's "Residual risk" subsection and the new `size_bytes is None` edge case).
2. **Resolved S1 (Medium — no dedicated evaluation of a threshold raise as a simpler alternative).** **Change made:** new §5, "Rejected Alternatives," added between Alternatives Considered (§4) and Selected Design (§6, renumbered from §5). It evaluates raising `_NAME_SIMILARITY_THRESHOLD` directly against the four confirmed scores (93.3, 91.3, 91.3, 94.7) and explains, using that evidence, why a threshold raise is rejected in favor of the corroborating-signal approach.
3. **Risk Assessment (now §8, renumbered from §7):** added R6 (residual risk that a size-proximity check does not eliminate — coincidental generic-name-plus-similar-size collisions) and R7 (the `size_bytes is None` edge case, and how the revised design behaves when it occurs).
4. **Regression Impact (now §9, renumbered from §8):** added a note that the revised identical-name branch requires review of any existing fixture that relies on identical-name matching without size data, and confirmed no existing test fixture in `src/pipeline/test_duplicate_detector.py`'s Module 08 §8 (Revision 1) list omits size — this must still be verified at implementation time, not assumed.
5. **Test Plan (now §10, renumbered from §9):** added T9 (generic-name, dissimilar-size pair — must NOT group), T10 (generic-name, similar-size pair with no version token — the honest ambiguous case, outcome reported not presumed "correct"), T11 (identical name, `size_bytes is None` on one or both sides — must NOT group via the size-proximity path, since proximity cannot be evaluated without both sizes).
6. **Validation Plan (now §11, renumbered from §10):** added a step to check whether either real validation dataset (Run 002, Run 003) contains any generic-filename file pairs, to ground E1's real-world exposure empirically rather than by argument alone, and to specifically re-measure R6/R7 against real data during re-validation.
7. **Acceptance Criteria (now §12, renumbered from §11):** added criteria requiring T9/T10/T11 to pass/be measured, and requiring the Validation Plan's new generic-filename check to be performed and its result reported explicitly (not silently skipped if no such pair exists in either dataset).
8. **Rollback Plan (now §13, renumbered from §12):** no substantive change — the rollback mechanics are unaffected by adding one additional condition to one branch; renumbered only.
9. **Alternatives Considered (§4):** left unchanged in content — S1's fix is the new dedicated §5, not a rewrite of §4's existing Option A/B/C/D comparison, which the review did not challenge.
10. **Evidence Summary, Root Cause Analysis (§2, §3):** unchanged — the review did not challenge the evidence or root cause findings themselves, only the design's response to them.
11. **Zero-byte edge case (added during the round-2 re-evaluation, not part of the original E1/S1 findings):** the round-2 reviewer identified that the size-proximity formula in §6 is undefined (division by zero) when both files are zero-byte. §6 now documents the required special-case handling explicitly, and §10 adds T12 to test it. This is a small, mechanical correction folded directly into this revision rather than triggering a third design cycle.

---

## 1. Problem Statement

`Rules/` has no dedicated business-rule document for Module 04 (a deliberate, disclosed choice — Module 04's matching parameters live as code constants, `TECHNICAL_DEBT_REGISTER.md` TD-07). Its behavior is defined directly in `src/pipeline/duplicate_detector.py`: for any category in `_VERSION_CHAIN_CATEGORIES` (Invoice, Resume, Bank Statement, Contract, Document, Image, Screenshot), `_check_version_chain()` treats two files as version-chain candidates whenever `lookup_name_matches()` returns a hit — which happens whenever `rapidfuzz.fuzz.ratio()` between their normalized filenames scores **≥ 90** (`_NAME_SIMILARITY_THRESHOLD`, `src/storage/database.py`), scoped only by matching `category`. No other signal is required or checked before candidacy is established.

This single-signal threshold is too permissive for a specific, now twice-confirmed real-world shape: filenames sharing a generic template or tool-assigned prefix, differing only in a trailing number or ordinal word (`"Mark Sheet 10th"` vs `"Mark Sheet 12th"`; `"image (2)"` vs `"image (42)"`). Edit-distance similarity between such names is high — often ≥ 90 — even though the files are genuinely unrelated documents, not sequential versions of one another. Because no corroborating signal (an explicit version token, an identical base name, file-size proximity, temporal proximity) is required, the threshold alone drives a false "version chain" grouping.

**Real-world evidence (`PATTERN_TRACKER.md` PT-003, Confirmed Pattern, 2 independent runs, mechanism now directly confirmed in both):**
- Run 002 (`VALIDATION_LEDGER.md` VL-002-3): 3 of 9 real academic mark-sheet photos wrongly grouped into 3 separate false version chains (10th/12th grade, 1st/4th semester, 2nd/3rd semester mark sheets) — distinct records, same institution's template.
- Run 003 (`VALIDATION_LEDGER.md` VL-003-2): `image (2).png` (a portrait photograph) and `image (42).png` (an unrelated delivery-truck advertisement mockup) flagged as a version chain — no shared subject matter, different file sizes, different content hashes.

**Severity:** Medium, per `PATTERN_TRACKER.md`/`VERSION_091_IMPLEMENTATION_PLAN.md` — never resulted in an incorrect automated filing in either run observed to date (the affected files in both runs happened to also land `review_required` for unrelated reasons — see §2/§8 for why this is a fact about the evidence gathered, not a property the architecture actually guarantees). Real, reproducible cost: the Duplicate Report states, in assertive language, that one file is a "Superseded Version" of another when it is not — a false signal a human reviewer could act on by manually archiving a file that was never actually superseded.

**This document's scope is narrower than the underlying question "should Module 04's matching be more precise in general."** It addresses exactly the one mechanism both runs' evidence isolates — the pure-filename-similarity path — not a general redesign of Module 04's matching architecture.

---

## 2. Evidence Summary

Per `ENGINEERING_CHANGE_PLAYBOOK.md` §1 stage 1–3 gates, every claim below is classified explicitly as **Confirmed**, **Suspected**, or **Unknown** — nothing is asserted at a higher confidence than its actual evidentiary basis supports.

### Confirmed (directly measured against real code and real data)

| # | Finding | Evidence |
|---|---|---|
| C1 | Run 003's false pairing (`image (2).png`/`image (42).png`) is driven exclusively by `_check_version_chain()`'s filename-similarity check. | `fuzz.ratio("image (2)", "image (42)")` = **94.7**, above the 90 threshold, measured directly (`VALIDATION_LEDGER.md`, Post-Run 003 addendum, 2026-07-20). |
| C2 | Run 003's pairing is **not** driven by the near-duplicate/perceptual-hash path. | Measured phash distance = **36**, far above `_MAX_PHASH_DISTANCE = 5`. |
| C3 | Run 003's pairing carries no explicit version token on either side. | `parse_version_token()` returns `None` for both `"image (2)"` and `"image (42)"`. |
| C4 | Run 002's three false pairings are driven by the **identical mechanism** — filename similarity alone, no corroborating signal. | Directly measured (2026-07-23): `fuzz.ratio()` = 93.3 / 91.3 / 91.3 across the three pairs, all above 90; `parse_version_token()` = `None`/`None` for all six filenames; phash distances = 26 / 8 / 6, all above the 5 threshold. |
| C5 | Neither run's false-pairing instances would have resulted from an identical normalized-filename match. | `"mark sheet 10th"` ≠ `"mark sheet 12th"`; `"1st semester"` ≠ `"4th semester"`; `"2nd semester"` ≠ `"3rd semester"`; `"image (2)"` ≠ `"image (42)"` — all four pairs are near-but-not-identical after normalization. |
| C6 | The confidence-scoring stage applies **no deduction specific to an ordinary (non-conflicting) version-chain grouping.** | Direct code read, `src/pipeline/confidence.py` `compute_deductions()`: only `fuzzy_duplicate` and `version_conflict` (a *cross-group* conflict, a different, rarer condition) carry a deduction. |
| C7 | `resolve_precedence()` (`src/pipeline/execution.py`) routes `version_rank == "superseded"` to automatic archival (`~ARCHIVE~/Old Versions/`) for **any** record that is not itself `review_required`. | Direct code read: check order is `review_required` → `exact_duplicate` → `superseded_version` → `normal`, no additional gate on the `superseded_version` branch. |
| C8 | Archival under `"superseded_version"` moves the file to `~ARCHIVE~/Old Versions/`, not a permanent delete, and is logged and undoable like any other move. | Direct code read, `resolve_destination_path()`. |
| C9 | In both runs observed to date, every falsely-paired file happened to also be `review_required` for reasons unrelated to the pairing itself (Screenshot/Image misclassification, pre-PT-002 fix). | Direct data read: all 3 Run 002 pairs and both Run 003 files carried `tier == "review_required"` at the time of each run. |
| C10 *(new this revision)* | `FileRecord` already captures `size_bytes: Optional[int]` for every discovered file. | Direct code read, `src/models/file_record.py` line 36. The `Optional` qualifier means a size-proximity corroborating check must explicitly handle the case where one or both sides lack a value — addressed in §6/§8 (R7) below, not assumed away. |

### Suspected (plausible, consistent with available evidence, not independently isolated to the same rigor as the above)

| # | Finding | Basis |
|---|---|---|
| S1 | The false-positive rate for this mechanism, in a full/typical real Downloads folder, is higher than either single run's small sample suggests. | Two runs, 4 total instances across 45 files with version-chain-eligible categories — too small a sample for a defensible rate estimate. |
| S2 | Generic, tool-or-browser-assigned filename patterns (`"image (N).ext"`, sequential scan/photo naming) are a materially larger share of real Downloads content than either curated validation dataset fully represents. | Inferred from the diversity already seen — plausible, not confirmed at scale. |
| S3 *(new this revision)* | Filenames that are identical (not just similar) and generic (`invoice.pdf`, `document.pdf`, `scan.pdf`) are a plausible, real-world source of false version-chain candidacy distinct from S1/S2's near-miss-similarity shape. | Raised by the Revision 1 review (Finding E1) as a logical consequence of the same root cause (generic naming) applied to the identical-name case rather than the near-miss case. Not yet confirmed against either validation dataset — see §11's new validation step. |

### Unknown (not investigated; explicitly not assumed)

| # | Question | Why it matters |
|---|---|---|
| U1 | Does Module 04 correctly detect a **genuine** version chain (true positive) at all, under real-world conditions? | No run to date has contained one — `VALIDATION_PROGRESS.md` §4 names this as still-needed. |
| U2 | Is the false-positive rate materially different for other version-chain-eligible categories (Invoice, Resume, Bank Statement, Contract)? | Both confirmed instances are Image/Screenshot-category; absence of evidence for other categories is not evidence of absence. |
| U3 | Would the corroborating-signal requirement (§6) measurably reduce recall on a genuine version chain that uses neither an explicit version token nor an identical filename? | No such case exists in either run's real data to test against. Disclosed, not resolved, in §8/§11. |
| U4 *(new this revision)* | How often, in real data, do two genuinely unrelated files share both an identical generic filename **and** a similar size (defeating the size-proximity corroboration)? | Not measured. Named explicitly as R6 in §8 — a residual risk, not eliminated by this revision, only narrowed. |

---

## 3. Root Cause Analysis

`_check_version_chain()` (`src/pipeline/duplicate_detector.py`) calls `lookup_name_matches(normalized_name, category)` (`src/storage/database.py`), which scans every stored normalized filename in `Database/FileIndex/name_index.json` and includes a candidate whenever:

```python
if fuzz.ratio(normalized_name, stored_name) < _NAME_SIMILARITY_THRESHOLD:
    continue
for file_id in file_ids:
    if category_by_file_id.get(file_id) == category:
        matches.append(file_id)
```

`normalize_filename()` strips only the file extension, a recognized trailing version token (`_v2`, `_final`, etc.), and separator runs — it does **not** strip arbitrary trailing numbers, ordinals, or parenthetical content. `fuzz.ratio()` is a pure Levenshtein-style edit-distance similarity score. For two filenames sharing a long common prefix (an institution's document template; a generic tool-assigned base name) and differing only in a short numeric/ordinal suffix, the edit distance is small relative to string length, so the score routinely clears 90 even though the differing suffix is exactly what distinguishes two genuinely different documents.

No second signal is consulted before this candidacy becomes a version-chain grouping. **The Revision 1 review's Finding E1 identified a second, related instance of this same root cause:** when two normalized names are *identical* rather than merely similar, `fuzz.ratio()` trivially returns 100, which also clears the threshold — but an identical name is itself frequently a *symptom of genericness* (a default, tool-assigned, or never-customized filename), not necessarily evidence of a version relationship. The original Selected Design's identical-name branch, by treating exact-name-match as unconditionally sufficient, inherited the same "similarity alone is not evidence of relationship" gap it was meant to close for the near-miss case.

**This is a rule-completeness gap, identical in shape to PT-002's root cause:** the code faithfully implements the design as specified; the gap is that the design never required a second, corroborating signal — genuinely independent of filename shape — before treating filename evidence (whether near-miss-similar or identical) as sufficient evidence of a version relationship.

---

## 4. Alternatives Considered

**Option A — Require a corroborating signal alongside filename similarity, before a candidate pair is accepted into a version-chain group.** Two sub-variants were evaluated:
  - **A1 (rejected as insufficiently precise):** Require `fuzz.ratio() >= 90` **and** a minimum phash proximity. Rejected because C2/C4 directly confirm phash distance was nowhere near the near-duplicate threshold in any of the 4 confirmed instances — this condition would not have prevented any of the observed false positives. Phash proximity is the right corroborating signal for the *near-duplicate* path, not for filename-only version-chain candidacy.
  - **A2 (selected, revised in §6):** Require `fuzz.ratio() >= 90` **and** a corroborating signal independent of filename-similarity-shape alone. Directly targets the actual mechanism confirmed in §2/§3.

**Option B — Add a live-judgment provider to adjudicate ambiguous version-chain candidates.** Pre-disclosed as a future possibility in Module 04's own release documentation (`Release/Module04/KNOWN_LIMITATIONS.md`). **Rejected for this cycle.** A genuine architectural departure — Module 04's `MODULE_CONTRACT.md` explicitly guarantees output identical whether run live or unattended; adding a provider would end that property for version-chain detection specifically, a contract change requiring the full breaking-change approval process (`ENGINEERING_STANDARD.md` §17), not a patch-level correction. Four confirmed instances, all explainable by a much smaller, non-architectural fix, do not justify that escalation.

**Option C — Soften the Duplicate Report's "Superseded Version" language, without changing the matching logic.** Addresses the *consequence*, not the *cause*. Also lives in a different module: the "Superseded Version"/"Related To" language is `src/pipeline/reporting.py` (Module 08), not Module 04 — confirmed by direct code read. Combining a Module 04 fix and a Module 08 language change in one post-freeze correction would violate this project's scope-discipline precedent. **Not selected.** Named as a real, separate, out-of-scope finding for a future backlog item (see §14).

**Option D — No code change; document the confirmed, broader real-world scope in `KNOWN_LIMITATIONS.md`/`TECHNICAL_DEBT_REGISTER.md` only.** Rejected — two independent runs' worth of Confirmed Pattern evidence, with a precisely understood mechanism and a small, well-scoped fix available, exceeds the bar this project's own `VERSION_091_IMPLEMENTATION_PLAN.md` set for "worth fixing now."

---

## 5. Rejected Alternatives

*(New section, added in response to Revision 1 review Finding S1.)*

This section evaluates, explicitly and on the record, the simplest alternative fix a reviewer would reach for first — raising the similarity threshold — rather than adding a corroborating-signal condition at all.

### Option E — Raise `_NAME_SIMILARITY_THRESHOLD`

**The proposal:** since all four confirmed false-positive scores (93.3, 91.3, 91.3, 94.7) cluster just above the current threshold of 90, raising the constant to somewhere in the 95–96 range would, on the evidence gathered so far, have prevented every one of them without adding any new branching logic — a single-constant, zero-new-code change.

**Why this is rejected in favor of the selected corroborating-signal design:**

1. **No principled stopping point.** The four confirmed scores happen to cluster in the 91.3–94.7 range, but nothing about the underlying mechanism guarantees future instances will stay below any particular new threshold. A generic template name differing only by a two-digit suffix (as in Run 002's mark-sheet pairs) can easily score in the high 90s depending on the base name's length — the fix would then need to be raised again, indefinitely chasing whatever the next observed instance happens to score, rather than addressing why filename similarity alone is being treated as sufficient evidence.
2. **A threshold raise degrades precision uniformly, including for cases that have nothing to do with the confirmed failure mode.** Every candidate pair in the system — not just the generic-template shape this pattern actually involves — becomes harder to match. A genuine version chain with a small, legitimate rename (a typo fix, a minor date correction in the filename) that happens to score just under the new, higher bar would now go undetected, a cost with no offsetting benefit for those cases, since they were never the source of the false positives being fixed.
3. **It discards signal that's already available for free.** `parse_version_token()` is already computed elsewhere in the same function for rank assignment; an explicit version token is a structural, intentional signal a filename similarity score can never provide (a user or tool that writes `_v2` is stating a version relationship directly, not something a fuzzier metric should need to approximate). A pure threshold raise ignores this signal entirely.
4. **It does not address the identical-name branch's own exposure (Finding E1) at all.** An identical name always scores 100 regardless of where the threshold is set — raising the threshold to 96, 99, or even 100 does nothing to distinguish "two unrelated files that happen to share a generic name" from "two genuine versions of the same document." Any fix that relies solely on the similarity score, at any threshold, cannot close E1's gap; only a signal independent of the filename-similarity score itself (§6) can.

**Conclusion:** a pure threshold raise is simpler to implement but strictly weaker — it is calibrated to today's four known instances rather than to the actual mechanism, it costs precision uniformly across unrelated cases, and it cannot address the identical-name exposure the review separately identified. The corroborating-signal approach (§6) is retained as the selected design.

---

## 6. Selected Design (Revised)

**Option A2, revised to close Finding E1.** `_check_version_chain()`'s underlying candidate lookup gains a second, corroborating condition. Precisely stated:

A candidate pair (the record being processed, and a same-category stored name) is accepted as a version-chain candidate only if **both**:

1. `fuzz.ratio(normalized_name, stored_name) >= _NAME_SIMILARITY_THRESHOLD` (unchanged — the existing, already-tuned similarity bar), **and**
2. At least one of:
   - `parse_version_token()` returns a non-`None` result for **at least one** of the two original filenames (unchanged from Revision 1 — an explicit, intentional version marker is a strong, structural signal on its own and needs no further corroboration), **or**
   - the two normalized names are **identical**, **and** a size-proximity check passes: `min(size_a, size_b) / max(size_a, size_b) >= _VERSION_SIZE_PROXIMITY_RATIO` (proposed value: **0.5**, i.e. the smaller file is no less than half the size of the larger — equivalently, no more than a 2× size difference), **and** both `size_a` and `size_b` are non-`None` (see the `size_bytes is None` handling below).

If condition 2 is not met, the pair is not treated as a version-chain candidate, regardless of how high the `fuzz.ratio()` score is.

**Why the revised identical-name branch closes Finding E1's gap:** an identical normalized filename alone is not, by itself, evidence of a version relationship — it is equally consistent with "genuine re-save of the same document" and "two unrelated files that happen to share a generic, uncustomized name." The size-proximity check adds a signal that is *independent* of the filename entirely: it is derived from file content, which the two candidate scenarios systematically differ on. Two unrelated documents sharing a generic name — a different vendor's invoice, a different scanned page count, a different photo's resolution and compression — will, in the large majority of realistic cases, differ in byte size by a wide margin, because their *content* is unrelated, not just their name. Genuine version pairs (an edited resave, an appended page, a corrected total) typically stay within a narrower size band, because most of the underlying content is unchanged between versions. Requiring both conditions together means the identical-name branch is no longer accepting filename evidence alone — it is accepting filename evidence *corroborated by* a content-derived signal, matching the same standard already applied to the explicit-token branch (which relies on structural filename evidence that isn't reducible to a similarity score) and to the phash-based near-duplicate path (which never uses filename evidence as its sole basis at all).

**`size_bytes is None` handling (addresses C10/R7):** `size_bytes` is an `Optional[int]` field — not guaranteed to be populated for every record. If either side's `size_bytes` is `None`, the size-proximity check cannot be evaluated and is treated as **failing** (conservative default: the pair does *not* qualify via the identical-name branch in this case). This mirrors the project's existing safety posture of defaulting to *not* asserting a relationship when evidence is incomplete, rather than defaulting to asserting one. A pair in this state can still qualify via the explicit-token branch if applicable; if not, it simply does not form a version-chain group — the same outcome as if the names had not been identical at all, which is the safe direction to fail in.

**Zero-byte edge case (identified during the round-2 re-evaluation of this design):** the stated formula `min(size_a, size_b) / max(size_a, size_b)` is undefined when both sizes are `0` (division by zero). Two zero-byte files sharing an identical normalized name are, in fact, the one case where "identical size" is unambiguous rather than merely proximate — the implementation must special-case `max(size_a, size_b) == 0` to evaluate as passing (ratio treated as `1.0`) rather than raising or silently defaulting either way. This is stated explicitly here so it is a documented design requirement, not an implementation-time surprise.

**Residual risk, explicitly disclosed, not eliminated (see §8 R6):** this check narrows, but does not eliminate, Finding E1's exposure. Two genuinely unrelated files could still, in principle, share both a generic identical name and a coincidentally similar size. This is judged materially rarer than the unconstrained identical-name case the review flagged, but it is not zero, and is carried forward as a named residual risk rather than an implicitly resolved one.

**What this revision does not do:** it does not touch the near-duplicate/perceptual-hash path, `_MAX_PHASH_DISTANCE`, `_NAME_SIMILARITY_THRESHOLD`'s numeric value, `normalize_filename()`, or `parse_version_token()` themselves. It adds exactly one new proposed constant (`_VERSION_SIZE_PROXIMITY_RATIO`) and one new conditional check, scoped only to the identical-name branch.

**Disclosed trade-off carried over from Revision 1, unchanged (U3):** a genuine version chain whose members share neither an identical normalized name nor a recognized version token would still not be detected. No such case exists in any real data gathered to date; this remains a real, bounded, disclosed possibility — see §8 and §12.

---

## 7. Compatibility Analysis

- **`MODULE_CONTRACT.md`:** unaffected. The contract makes no precision/recall guarantee on `version_group_id`/`version_rank`, only a determinism guarantee and field-ownership guarantees. `_check_version_chain()`'s internal acceptance logic remains an implementation detail free to refine without a contract-level breaking change, directly analogous to PT-002's own reasoning.
- **Determinism guarantee:** preserved. `size_bytes` is a stable, already-captured field (not recomputed at match time), so the added condition remains a pure function of already-available inputs — no new randomness, no new external state, no change to the fixed processing order the determinism guarantee depends on.
- **Downstream modules:**
  - **Module 05 (Naming)** and **Module 06 (Confidence)** — unaffected; both already handle `version_group_id`/`version_rank` being `null` as the common case, and this change only affects which pairs reach a non-null state, not the shape of the state itself.
  - **Module 07 (Execution)** — `resolve_precedence()`'s `"superseded_version"` branch is unaffected in its own logic; this change reduces how often that branch is *reached* for a false pairing (including, now, the generic-identical-name case), it does not change what happens when it is reached.
  - **Module 08 (Reporting)** — unaffected in its own logic; this change reduces how often a false pairing (of either shape) reaches the report at all. The report-language concern (Option C, §4) remains open and is not addressed by this design.
- **PT-002 interaction:** unchanged from Revision 1's analysis — PT-002 moved both members of Run 003's confirmed pair together across the Screenshot→Image reclassification, so category scoping was unaffected by PT-002 in that instance; this design's fix is independent of category value entirely.
- **Version bump determination:** **PATCH**, unchanged from Revision 1. No `MODULE_CONTRACT.md` guarantee text changes; no existing guarantee is weakened; the new behavior narrows an unstated, unguaranteed matching heuristic rather than altering a documented contract.

---

## 8. Risk Assessment

| # | Risk | Severity | Disposition |
|---|---|---|---|
| R1 | Reduced recall on a genuine version chain lacking both an identical name and an explicit version token (U3). | Medium — real, plausible, currently unmeasured. | Disclosed, not eliminated. Named as an Acceptance Criterion (§12) requiring a genuine positive-control test before this design may be considered validated. |
| R2 | A false version-chain pairing reaching `auto` or `approval_required` tier would be automatically archived to `~ARCHIVE~/Old Versions/` without human review — `resolve_precedence()` does not exempt non-`review_required` tiers from the `"superseded_version"` branch. Neither confirmed instance to date has actually reached this outcome (C9), but this is a fact about the two samples gathered, not an architectural guarantee. | **High realized-consequence, Low-so-far-observed-likelihood.** Independent of which fix is selected — a property of `resolve_precedence()`, not of `_check_version_chain()`'s matching precision. | This design reduces how often this scenario can be reached, by reducing false-positive candidacy in the first place (now covering both the near-miss and identical-name shapes) — but does not close the gap architecturally. Any archival remains reversible (C8), not a data-loss risk, but a real trust/UX risk if it occurred unnoticed. Recommended as its own future backlog item (§14), not resolved here. |
| R3 | Report-language over-assertiveness ("Superseded Version," Option C, §4) is not addressed by this design and remains present for whatever false-positive residual rate remains. | Low-Medium | Disclosed as explicitly out of scope. Recommended future backlog candidate. |
| R4 | The corroborating-signal logic could have an edge case not anticipated by the two confirmed instances (e.g. an unrecognized version-token format). | Low | Inherited from the existing implementation, not introduced by this fix. |
| R5 | Performance: an added boolean condition inside an already-executing per-candidate loop. | Negligible | `size_bytes` is a stored field read, not a computed value — no new I/O, no new external call. |
| R6 *(new this revision, resolves E1's residual)* | The size-proximity check narrows but does not eliminate the generic-identical-name false-positive exposure: two unrelated files could coincidentally share both a generic name and a similar size (e.g. two different but similarly-sized `document.pdf` files). | Low-Medium, judged materially lower than the pre-revision exposure but not zero; unmeasured against real data (U4). | Disclosed explicitly, not silently treated as resolved. §11's validation plan adds a step to check for this shape in real data; §12's acceptance criteria requires the result to be reported either way. |
| R7 *(new this revision)* | `size_bytes` is `Optional[int]` — a record with a missing size cannot pass the size-proximity check under any circumstance, meaning the identical-name branch would never fire for such a record even if a genuine version relationship exists. | Low | Deliberately conservative default (§6) — treated as a bounded extension of R1's existing recall trade-off, not a new category of risk. Should be measured at implementation time (how often is `size_bytes` actually `None` in practice) to confirm this is rare, not common. |

---

## 9. Regression Impact

- **Existing Module 04 unit tests requiring re-verification, not change:** `test_engine_creates_new_version_group_for_first_time_pairing`, `test_engine_version_chain_scoped_categories_only`, `test_engine_version_conflict_when_token_and_date_disagree`, `test_engine_version_rank_by_token_only_when_date_unavailable_on_both`, `test_engine_version_rank_by_date_only_when_token_missing_on_one_side`, `test_engine_retains_only_single_best_scoring_version_candidate`, `test_needs_duplicate_detection_false_after_version_chain_formed_with_conflict`, `test_engine_exact_duplicate_short_circuits_version_chain_check` (`src/pipeline/test_duplicate_detector.py`). **Revised note:** each of these fixtures was originally read as using either an explicit token or an identical base name (Revision 1, §8). Any fixture relying on the *identical-name* branch specifically must now also be checked, at implementation time, for whether its fixture data includes matching `size_bytes` values — if any such fixture omits size data (or uses mismatched sizes) it will need updating to reflect the revised condition, not merely re-run unchanged. This is a concrete, itemized follow-up for implementation, not assumed clean.
- **`test_module_contract_immutability_every_non_owned_field_byte_identical` and `test_module_contract_side_effect_exhaustively_verified_on_other_record`** — unaffected; this design touches candidacy, not the side-effect mechanism.
- **`lookup_name_matches()`'s own existing unit tests** (`src/storage/test_database.py`) — function signature and category-scoping unchanged; internal accept/reject condition changes, same follow-up as above applies if any fixture uses identical names.
- **Full project-wide regression suite** — currently 720/720 (post-PT-002); must remain at 100%, plus new tests below.
- **No Module 01/02/03/05/06/07/08 test file is expected to require a change** — confirmed via direct read of every downstream consumer (§7).

---

## 10. Test Plan

- **T1 (positive control, addresses R1):** a synthetic fixture reproducing an organically-worded, non-tokened rename (e.g. `"Meeting Notes.docx"` → `"Meeting Notes Updated.docx"`) — assert whichever outcome the corrected logic actually produces, making R1's trade-off directly observable.
- **T2 (regression, reproduces Run 002's confirmed shape):** synthetic fixtures for same-template, differing-ordinal-suffix filenames, no version token — assert **no** version-chain group forms.
- **T3 (regression, reproduces Run 003's confirmed shape):** synthetic fixtures for a generic-tool-incrementing filename pattern, no version token — assert **no** version-chain group forms.
- **T4 (positive control, identical-name path):** two same-category fixtures with an identical normalized name, no explicit token, and **similar sizes** (within the proposed 2× ratio) — assert a version-chain group **does** form.
- **T5 (existing, re-run):** every test listed in §9's first bullet, individually re-verified as described.
- **T6 (existing, module-contract immutability):** both tests listed in §9's second bullet.
- **T7:** full project-wide regression suite, target 720/720 baseline plus all new tests, all passing.
- **T8:** `Governance/PIPELINE_CONTRACT_VERIFICATION.md`'s 13-check gate, re-run for Module 04 — required per `ENGINEERING_CHANGE_PLAYBOOK.md` §6.
- **T9 *(new, resolves E1):*** two same-category fixtures with an identical, generic normalized name (e.g. `"invoice"`, `"document"`, `"scan"`) and **dissimilar sizes** (outside the 2× ratio) — assert **no** version-chain group forms, directly testing the E1 scenario the review raised.
- **T10 *(new, resolves E1, honest ambiguous case):*** two same-category fixtures with an identical, generic normalized name and **similar sizes**, representing the R6 residual (two unrelated files that coincidentally look related by both signals) — assert whichever outcome the corrected logic actually produces, and report it plainly as a known, accepted ambiguity rather than presenting it as a "correct" result either way, mirroring T1's own methodology.
- **T11 *(new, resolves R7):*** two same-category fixtures with an identical normalized name where `size_bytes` is `None` on at least one side — assert **no** version-chain group forms via the identical-name branch (confirms the conservative-default handling in §6).
- **T12 *(new, added during round-2 re-evaluation, resolves the zero-byte edge case):*** two same-category fixtures with an identical normalized name and `size_bytes == 0` on both sides — assert the size-proximity check evaluates as passing (does not raise, does not default to failing) and a version-chain group forms, confirming the special-case handling documented in §6.

---

## 11. Validation Plan

Per `ENGINEERING_CHANGE_PLAYBOOK.md` §4, real-world re-validation is **triggered** for this change: it originated from real-world validation, prior real-world datasets exist to re-run, severity is Medium, and the fix touches duplicate/version detection logic directly.

1. **Re-execute Run 002 and Run 003 against the corrected code**, using the same dataset-reconstruction-and-diff method PT-002's own validation used — byte-for-byte reconstruction of both original datasets, full before/after diff of every record.
2. **Confirm the specific prediction:** all 4 previously-confirmed false pairings no longer form a version-chain group, and no other record's classification, tier, naming, or duplicate/version relationship changes as a side effect.
3. **Address U1/R1 directly:** actively seek or construct at least one genuine, real version-chain scenario as part of this validation pass. If none can be found, report that absence explicitly.
4. **Safety re-confirmation (R2):** explicitly verify, on the re-validation data, whether any record affected by this change's logic reaches `auto` or `approval_required` tier.
5. **Generic-filename check *(new this revision, addresses S3/R6/U4):*** scan both reconstructed real datasets for any pair of same-category files sharing an identical normalized filename (a direct check for the E1 scenario occurring in real, not just synthetic, data). For any such pair found, report both its `fuzz.ratio()` outcome under the revised logic and its actual size relationship — this is the empirical grounding S3/R6/U4 currently lack. If no such pair exists in either dataset, report that absence explicitly rather than treating it as confirmation the risk doesn't matter.

---

## 12. Acceptance Criteria

1. **Zero regression** on every existing Module 04 test (§9) and the full project-wide suite (720/720 baseline, T7).
2. **T2/T3 pass:** both confirmed real-world false-pairing shapes no longer form a version-chain group.
3. **T1/T4/T9/T10/T11 measured, not assumed:** each of these positive/negative controls, including the two new E1-specific tests, is run and its actual outcome reported plainly, whichever way it resolves.
4. **Real-world re-validation (§11) reproduces zero false pairings** on the reconstructed original datasets, with a full before/after diff confirming no unintended changes.
5. **R2 (auto-tier archival exposure) is explicitly re-measured** against the re-validation data.
6. **U1 (genuine version-chain recall) is either confirmed against a real positive control, or its continued absence is explicitly reported.**
7. **S3/R6/U4 (generic-filename real-world exposure) is explicitly checked** via §11 step 5, and its result — whether such a pair was found or not — is reported in the validation report, not silently omitted.
8. **13-check PCV gate (T8), zero unresolved Critical/High/Medium findings.**
9. **Downstream chain verified:** at least one full Module 01→08 chain run against re-validation data confirms Modules 05/06/07/08 handle the corrected output with no unexpected branch reached.

---

## 13. Rollback Plan

- **Pre-implementation:** no rollback needed — nothing has been built yet.
- **Post-implementation, pre-merge:** implementation is blocked from merging if regression or validation finds a problem; findings are reported per `ENGINEERING_CHANGE_PLAYBOOK.md` §2's gates. No partial/silent merge.
- **Post-merge:** a direct, symmetric code revert — restore the single-condition acceptance logic, remove both the token-branch and size-proximity conditions added across both revisions. Fully mechanical given the change's small, well-isolated surface area. No data migration is implied: `version_group_id`/`version_rank` values already written under the corrected logic would not automatically retroactively change on rollback — any group formed or *not* formed during the corrected logic's live window would need case-by-case review if rollback occurs after real use, matching PT-002's own rollback plan.
- **Monitoring signal:** a future `PATTERN_TRACKER.md` entry showing either (a) the false-positive mechanism recurring despite this fix, (b) a confirmed real version chain going undetected (R1/R7 materializing), or (c) a generic-identical-name-plus-similar-size false positive occurring in real use (R6 materializing) — any of these would trigger a future correction cycle, not an emergency rollback on its own.

---

## 14. Summary

This design closes both mechanisms behind PT-003's false version-chain pairings — the near-miss-similarity shape (both confirmed runs) and the identical-generic-name shape (identified during independent review, Finding E1) — with a small, contract-safe addition to Module 04's existing matching logic, using only already-captured metadata (`size_bytes`). It also surfaces two findings beyond its own scope that deserve separate attention, both recommended as future backlog items rather than folded into this design or silently dropped: `resolve_precedence()`'s lack of a non-`review_required`-tier exemption for `"superseded_version"` (R2), and the Duplicate Report's over-assertive "Superseded Version" language, which lives in Module 08 (R3/Option C). Two disclosed residual risks remain even after this revision — reduced recall on non-tokened, non-identical genuine renames (R1) and a narrower-but-nonzero exposure to coincidental generic-name-plus-similar-size false positives (R6) — both carried forward explicitly rather than presented as fully resolved.
