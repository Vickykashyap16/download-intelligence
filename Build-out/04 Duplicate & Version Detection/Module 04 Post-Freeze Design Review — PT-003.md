# Module 04 Post-Freeze Design Review — PT-003 (Round 1)

**Status update, 2026-07-23:** the design package has been revised in response to every finding below (see the "Design Revision Summary" section at the top of `Module 04 Post-Freeze Design Correction — PT-003.md`). A second, independent review pass of the revised design has been performed and recorded in `Module 04 Post-Freeze Design Review — PT-003 (Round 2).md`. This document is retained as the historical record of the first review round and is not edited further.

**Reviewed document:** `Module 04 Post-Freeze Design Correction — PT-003.md` (this folder), dated 2026-07-23.
**Purpose:** the independent review pass required by `ENGINEERING_CHANGE_PLAYBOOK.md` §3 for a Medium-severity post-freeze correction. This review is deliberately adversarial — its job is to find real problems with the design, not to confirm it. Per the user's explicit instruction, it specifically probes for: edge cases, regressions, architectural impacts, contract changes, performance impacts, and simpler alternatives.
**Constraint maintained:** no code was written, run, or modified to produce this review. Every finding below is reasoned from the design document's own stated logic and from the code excerpts it quotes, not from new empirical measurement — where a finding would benefit from empirical confirmation, that is stated explicitly as a follow-up, not treated as already resolved.

---

## 1. Edge Cases

### Finding E1 (Medium — the review's central finding). The identical-normalized-name branch reintroduces the same class of flaw the design is fixing, just at a different degenerate point.

The Selected Design's condition 2 is satisfied by *either* an identical normalized name *or* an explicit version token. Look closely at the identical-name branch: if two normalized names are identical, `fuzz.ratio()` between them is trivially 100, which already clears the existing `>= 90` threshold on its own. **The identical-name branch does not add a new, independent corroborating signal — it is a subset of condition 1 that the design is treating as automatically sufficient.**

That would be fine if an identical normalized filename were strong evidence of a genuine version relationship. It often is — but not always, and the design package's own root cause section already identifies the failure mode that breaks this assumption: **generic, template-style filenames.** Two completely unrelated files can easily share an identical normalized name with no version relationship at all: two different vendors' invoices both saved as `invoice.pdf`; two unrelated contracts both saved as `contract.pdf`; two different scans both saved as `scan.pdf` or `img.pdf`. `normalize_filename()` strips only extension, a recognized version token, and separator runs — it does nothing to distinguish "identical because it's a re-download of the same document" from "identical because the name is generic and the user (or their scanner, or their browser) never customized it." Category scoping (both PDFs, category Document, category Invoice, etc.) does not help — that is exactly the condition already required before the corroborating check even runs.

This is not a hypothetical corner case; it is arguably a **more common** real-world shape than the tokened-suffix case the design's own two confirmed instances used, since generic default filenames (`document.pdf`, `image.png`, `scan.pdf`, `receipt.pdf`) are extremely common in real Downloads folders — a claim consistent with the design package's own §2 Suspected finding S2 about generic/tool-assigned naming patterns being under-represented in the two validation datasets. **The design package's Test Plan (§9) does not include a single fixture exercising this exact scenario** — every new test (T1–T4) either confirms the two already-known false-positive shapes are fixed, or confirms the token branch, or confirms the identical-name branch fires *positively* with no adjacent test checking whether that positive is itself sometimes wrong.

**This does not mean the identical-name branch is a bad idea** — an exact filename match plus matching category is genuinely useful signal in the common case (an actual re-download or re-save). But treating it as unconditionally sufficient, with no secondary check at all, is the same reasoning error PT-003 exists to correct, relocated rather than eliminated.

**Recommended change:** add a lightweight secondary corroborating check specific to the identical-name branch — the cheapest defensible option is a file-size proximity check (both files' already-available size metadata) or a discovery-date proximity check, either of which is plausible evidence that two identically-named files are actually related, versus two unrelated files that happen to share a generic name. This does not need to be elaborate; even a coarse check narrows the exposure meaningfully. Absent that, at minimum the design should explicitly disclose this as an accepted residual risk with the same rigor §7/§9/§11 already give R1 — right now it is not named anywhere in the design package's Risk Assessment, Test Plan, or Acceptance Criteria.

### Finding E2 (Low). Category-boundary near-misses are not addressed and are outside this design's stated scope, but the design package doesn't say so explicitly.

`_VERSION_CHAIN_CATEGORIES` requires exact category match. A file that could plausibly be either of two categories (the exact ambiguity PT-002 addressed for Screenshot/Image) could, in principle, fail to be compared against its true counterpart if the two ended up differently categorized for unrelated reasons — this is a pre-existing property of Module 04's design, not something PT-003 introduces or worsens. Not a defect in this design. Flagged only because the design package doesn't explicitly note that its fix operates entirely *inside* a single category bucket and has no interaction with cross-category miscategorization risk (a natural question a reader familiar with PT-002 would ask). Recommend one sentence added to §6 (Compatibility Analysis) noting this explicitly, for completeness, not because it changes anything.

### Finding E3 (Informational). Case sensitivity and unicode normalization of the "identical name" check are unspecified.

The design says "the two normalized names are identical" but doesn't state whether `normalize_filename()`'s lowercasing (mentioned in the Root Cause Analysis, §3 of the design package) is the only normalization applied, or whether unicode-equivalent but byte-different names (e.g. NFC vs NFD accented characters) would be treated as identical or not. Almost certainly inherited, unchanged behavior from the existing `normalize_filename()` — not a new risk this design introduces — but worth a one-line confirmation at implementation time rather than an assumption.

---

## 2. Regressions

### Finding R1 (informational, not a defect). The design's own regression coverage claim (§8) is reasonable but incomplete in one specific way tied to E1.

Every existing test enumerated in §8 is stated to use either an explicit token or an identical base name — the design package treats "identical base name" fixtures as unambiguously safe regression coverage. Given E1, at least one of those existing fixtures should be re-read (not just re-run) at implementation time to confirm it represents a *genuine* version-chain scenario and not, coincidentally, a generic-name fixture that happens to pass today only because nothing has yet challenged it the way E1 describes. This is a low-cost verification step, not a new test to write.

### Finding R2 (none identified). No regression risk found in the near-duplicate path, Module 06, Module 07, or Module 08's own logic.

The design package's Compatibility Analysis (§6) directly reads the relevant downstream code (`compute_deductions()`, `resolve_precedence()`, `generate_duplicate_report()`) rather than asserting compatibility from architecture alone — this reviewer independently re-traces the same logic and reaches the same conclusion: none of these functions branch on *how* a version-chain candidate was accepted, only on the resulting `version_group_id`/`version_rank` values, which are unaffected in shape by this change. No further regression risk identified here.

---

## 3. Architectural Impacts

**None identified beyond what the design package already discloses.** The change is confined to a single acceptance condition inside one function's candidate-filtering step; it does not add a new module, a new Provider, a new data field, or a new inter-module contract. The design package's own explicit "what this does not do" statement (§5) is accurate as far as this review can independently verify from the quoted code.

One observation worth recording rather than a finding requiring change: this is now the **second** post-freeze correction in this project (after PT-002) that turns out, on close inspection, to be "tighten an acceptance condition that was previously too permissive." That is a pattern, not a coincidence, and is worth a forward-looking note (see §6, Simpler Alternatives, and the recommendation below) rather than treating each occurrence as an isolated one-off.

---

## 4. Contract Changes

**None identified; PATCH determination is independently verified as correct**, for the same reason the design package states: `Release/Module04/MODULE_CONTRACT.md` makes no precision/recall guarantee on `version_group_id`/`version_rank`, only a determinism guarantee, and this change is itself a pure, deterministic function of already-available inputs — it does not threaten the determinism guarantee. No `MODULE_CONTRACT.md` text requires updating beyond a version-history entry, consistent with PT-002's own precedent.

One point the design package should make more explicit rather than a disagreement: PATCH-level changes still change *output* for some inputs (that is the entire point of the fix) — "PATCH" here tracks the *contract text*, not "no output changes at all." This is implicit in the design package's own reasoning but stating it plainly would preempt a reasonable objection from a future reader unfamiliar with this project's PATCH/MINOR/MAJOR convention (`Governance/FROZEN_MODULE_CHANGE_POLICY.md`).

---

## 5. Performance Impacts

**None identified.** Independently confirmed: both `normalize_filename()` and `parse_version_token()` are already invoked elsewhere in the same code path for other purposes (rank assignment), so the added condition reuses existing computation rather than introducing new work in the common case. The design package's own R5 assessment ("Negligible") is not challenged by this review.

---

## 6. Simpler Alternatives

### Finding S1 (Medium — process finding, not a design defect). The design package's Alternatives Considered section (§4) does not evaluate "raise the similarity threshold" as its own distinct option, even though it's the most obvious simpler alternative a reviewer would reach for first.

The confirmed false-positive scores are 93.3, 91.3, 91.3, and 94.7 — all clustered just above the current 90 threshold. A reasonable first question is: would simply raising `_NAME_SIMILARITY_THRESHOLD` (e.g., to 95 or higher) have prevented all four instances without adding a second condition at all? Based on the scores quoted in the design package's own Evidence Summary, raising the threshold to 95 would **not** have prevented the 96.7-adjacent... — checking precisely: 94.7 > threshold would need to exceed 94.7, meaning a threshold at or above 95 would catch all four (93.3, 91.3, 91.3, 94.7 all fall below 95). So a pure threshold increase to ~95–96 is at least superficially plausible as a simpler, one-constant, zero-new-branching fix.

**Why this reviewer does not think a pure threshold raise should replace the selected design**, but the design package should say so explicitly rather than silently skipping the comparison: a threshold raise degrades precision uniformly across every possible filename pair, including genuine near-miss version chains that have nothing to do with the confirmed failure mode (e.g., a legitimately-renamed document with a small typo fix between versions) — it is a blunter instrument than a corroborating-signal requirement, and it has no principled stopping point (today's four instances cluster below 95, but nothing guarantees a future instance won't score 96 or 97; the corroborating-signal approach doesn't depend on where these particular instances happened to land). This is very likely the right call — but the design package should show this reasoning explicitly, the same way it explicitly walked through and rejected Options A1/B/C/D. As written, a threshold-only fix is never named as an alternative at all, which is a gap in the document's own stated rigor standard, not a flaw in the underlying decision.

**Recommended change:** add "Option E — raise `_NAME_SIMILARITY_THRESHOLD`" to §4, with the reasoning above (or better reasoning, if empirical testing during implementation suggests otherwise), so the rejection is on the record rather than implicit.

---

## 7. Additional Observation (not requested by the four categories above, recorded for completeness)

The design package's own §7 (Risk Assessment, R2) surfaces a real safety-relevant architectural gap in `resolve_precedence()` — non-`review_required` tier files are not exempted from automatic `"superseded_version"` archival. The design package correctly declines to fix this itself (it's a Module 07 concern, out of scope for a Module 04 patch) but currently only "records" it in prose. Given this project's own established discipline (every other significant out-of-scope finding in this project's history — PT-002's Document-routing gap, TD-16's remainder — was given an explicit tracking artifact, not just a mention), **this finding should be given a Technical Debt Register entry or a new Pattern Tracker candidate before this design package is considered fully closed-out**, even though it doesn't block approval of the PT-003 fix itself. Recommended as a follow-up action, not a blocking condition.

---

## 8. Summary of Findings

| ID | Area | Severity | Blocking? |
|---|---|---|---|
| E1 | Edge case | **Medium** | Yes — recommend addressing before implementation |
| E2 | Edge case | Low | No |
| E3 | Edge case | Informational | No |
| R1 | Regression | Informational | No |
| R2 | Regression | None | No |
| — | Architectural | None (process note only) | No |
| — | Contract | None (clarity suggestion only) | No |
| — | Performance | None | No |
| S1 | Simpler alternative | **Medium** (documentation completeness) | Yes — recommend addressing before implementation |
| — | R2 tracking gap | Process | No (recommended follow-up, not blocking) |

---

## 9. Recommendation

**APPROVE WITH CHANGES.**

The underlying root cause analysis is sound, directly evidenced (both runs' mechanisms independently confirmed at High confidence), and correctly scoped to a single, small, PATCH-level fix — the same discipline this project's PT-002 correction demonstrated. No Critical or High-severity finding was identified: no architectural, contract, or performance concern blocks this design, and the near-duplicate path, Module 06, Module 07, and Module 08 are all correctly and independently verified as unaffected.

Two Medium findings should be addressed before implementation begins, not after:

1. **E1** — the identical-normalized-name branch needs its own corroborating check (size or date proximity, at minimum), or an explicit, disclosed residual-risk statement with matching Test Plan and Acceptance Criteria coverage equal to what R1/U3 already receive. As written, this branch is exposed to a plausible, arguably-common false-positive shape (generic default filenames) that the design's own root-cause reasoning would predict, and the design package does not test for it.
2. **S1** — the Alternatives Considered section should explicitly evaluate and reject a pure threshold increase, so the chosen design's advantage over the simplest possible fix is on the record rather than assumed.

Neither finding invalidates the selected design's core approach; both are refinements the same design can absorb without a rethink. Recommend the design package author (or whoever picks this up at implementation time) update §4 and §5/§7/§9/§11 of the design package to close E1 and S1, after which this reviewer would expect a straightforward APPROVE on re-review — no second full adversarial pass should be needed unless the E1 fix introduces new logic complex enough to warrant one.

**Per the user's explicit instruction, no implementation work begins as a result of this review.** These are recommendations for the design package to incorporate before an implementation cycle is authorized, not code changes made now.
