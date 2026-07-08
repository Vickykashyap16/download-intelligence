# Module 04 Design — Independent Architecture Review

Independent review of `Module 04 Design.md`, performed from the posture of a senior software architect who did not write it, per the current lifecycle stage (`ENGINEERING_STANDARD.md` §3) and this project's established review discipline (Critical/High/Medium/Low/Cosmetic, `ENGINEERING_STANDARD.md` §14). No changes have been applied. Nothing below has been auto-fixed.

## Findings

### F1 (Medium) — Batch processing order is unspecified; no deterministic tie-break for simultaneous version arrivals

**Explanation:** §7's workflow processes "each record," and §10 resolves version-chain rank by comparing version tokens and dates across group members — but the design never states what order records are processed *within* a single batch, nor what happens if two records that would form a version chain arrive in the *same* batch with no clear date/token winner (e.g. two files with identical `modified_at` and no parseable version token, or a batch containing `v8` and `v9` together rather than across separate runs). Because the side-effect update (§7 step 3) depends on which record is processed "first," an unspecified iteration order means the outcome (`version_rank` assignment) could differ across runs of the same input, which conflicts with the deterministic-only premise of §14.

**Trade-off:** Defining a strict processing order (e.g., stable-sort by `discovered_at` then `file_id`) costs nothing architecturally but must be stated explicitly, or two engineers implementing this design could reasonably build different, equally "correct" behavior.

**Smallest acceptable fix:** Add one sentence to §7: process records within a batch in a stable, defined order (e.g., `discovered_at` ascending, `file_id` as final tie-break), and if version-token and date signals are exactly tied between two simultaneously-arriving candidates, apply the same final tie-break (e.g., lexicographic `file_id`) purely for determinism — not correctness, just so re-running the same batch twice always yields the same answer.

### F2 (Medium) — `lookup_name_matches()`'s existing stub signature has no category parameter, contradicting the design's own stated scoping mechanism

**Explanation:** §9 and §16 both state that version-chain candidates must "share the same category," and §16 says this is enforced by "requiring category agreement at lookup time" performed by the *caller*, "since the caller already has each candidate's full record available for a category check." But this means every `lookup_name_matches()` call returns candidates across *all* categories, and the caller must then fetch each candidate's full `FileRecord` just to discard the wrong-category ones — exactly the kind of full-record-fetch-per-candidate cost §20 elsewhere argues the whole `FileIndex/` design exists to avoid. The inefficiency is real, if likely small at v1 volumes, but the bigger issue is that this reveals a genuine mismatch between what the design *wants* the index to do (scoped lookup) and what the already-existing stub signature *can* do (unscoped lookup) — and the design doesn't acknowledge the mismatch, just quietly routes around it.

**Trade-off:** The stub (`storage/database.py`) is unimplemented — changing its signature costs nothing today, but this design currently treats it as fixed and works around it instead of questioning whether it should change.

**Smallest acceptable fix:** Either (a) explicitly accept the post-hoc-filtering cost in §16/§20 as a stated, deliberate v1 trade-off (one sentence, no signature change), or (b) propose extending the stub to `lookup_name_matches(normalized_name, category)` before implementation begins, since nothing has been built against the old signature yet. Either is acceptable; the design should pick one on the record rather than leaving the tension unstated.

### F3 (Low) — No handling for two pre-existing version groups later discovered to be the same chain

**Explanation:** §7 step 3 covers "join an existing group" and "create a new group," but not the case where a new record matches candidates that *already belong to two different, pre-existing `version_group_id`s* (e.g., a file discovered late turns out to bridge two chains that were built independently because the connecting file arrived out of order). The design has no merge behavior defined for this.

**Trade-off:** This is a genuinely rare case at realistic Downloads-folder volumes, but "rare" isn't "impossible," and an undefined merge path means an implementer will invent one ad hoc if it's ever hit.

**Smallest acceptable fix:** One sentence: if a new record's candidates span two existing `version_group_id`s, treat it as a known edge case deferred to manual review (flag via `duplicate_signals`, do not attempt an automatic group merge) rather than silently picking one group — consistent with the design's existing "flag, don't guess" philosophy (§14, §21).

### F4 (Low) — `duplicate_signals`'s flat structure can only represent one match, not several

**Explanation:** §17's proposed `DuplicateSignals` (`exact_duplicate`, `fuzzy_duplicate`, `phash_distance`, `version_conflict`) assumes exactly one relevant match per record. If a future need arises to surface *multiple* near-duplicate candidates to a human reviewer (e.g., "this image is similar to three other files, not one"), this shape can't hold it without a breaking change.

**Trade-off:** Building a list-based structure now would be speculative — the original brief doesn't ask for multi-candidate surfacing, and `Rules/Confidence Rules.md`'s existing deductions only need a boolean/distance, not a full candidate list. Over-building this now would itself be the kind of unnecessary complexity this project's governance explicitly warns against.

**Smallest acceptable fix:** No structural change now — just add one disclosure sentence to §17 noting this is a single-best-match design, and that surfacing multiple candidates would require a schema change, so a future reader doesn't mistake the omission for an oversight.

### F5 (Low) — "Same category" ambiguity for Image vs. Screenshot grouping

**Explanation:** §9/§10 require version-chain (and, by extension, near-duplicate) candidates to share the same `category`, but never states whether `Image` and `Screenshot` — two distinct `Category` values that are nonetheless closely related in practice (a screenshot is a kind of image) — are treated as the same bucket for this purpose, or must match exactly.

**Trade-off:** Treating them as equivalent could catch more real version chains/near-duplicates (e.g., a screenshot re-saved and later reclassified as a plain image); treating them as strictly separate is simpler and avoids one more judgment call, at the cost of missing some real matches.

**Smallest acceptable fix:** One clarifying sentence in §9: for v1, `category` must match exactly (Image only groups with Image, Screenshot only with Screenshot) — simplest possible rule, explicitly stated rather than left implicit.

### F6 (Cosmetic) — Action-log name `detect_duplicates` undersells that the same action also covers version detection

**Explanation:** §18 proposes a single `detect_duplicates` action-log type whose `details.match_type` can be `"version"` — meaning an action literally named for duplicates is also this module's sole vehicle for reporting version-chain detections. A future reader scanning action-log types for "what logs version-chain activity" wouldn't find it under an intuitive name.

**Trade-off:** A single action type is simpler than two (`detect_duplicates` + `detect_versions`) and this module's per-file work is a single pass regardless of what it finds — splitting the action type would add an unnecessary distinction where a `match_type` field already communicates the same information.

**Smallest acceptable fix:** Rename the action type to `detect_duplicates_and_versions`, or add one sentence to §18 explicitly noting the name covers both purposes by design. Either resolves the naming-clarity gap; no behavior change either way.

### F7 (Cosmetic) — Pipeline-ordering assumption (Module 04 runs before Module 07's execution) is never explicitly stated

**Explanation:** §24 describes what Module 07 does with Module 04's output, implying Module 04 always finishes before Module 07 acts — but no section states this ordering assumption outright, or what Module 04 should do if a record's `current_path` no longer exists by the time it's processed (e.g., a re-run after a manual file move outside the pipeline).

**Trade-off:** At v1, the pipeline is a strictly ordered sequence of modules with no concurrent execution, so this is likely a non-issue in practice — but it's asserted nowhere.

**Smallest acceptable fix:** One sentence in §3 or §23: Module 04 assumes strictly sequential pipeline execution (it never runs concurrently with Module 07) and does not re-validate `current_path` existence — consistent with every earlier module's own assumptions, just not yet written down for this one.

## Findings not raised (checked, no issue found)

- **Duplicated responsibilities:** none found — the near-duplicate/version-chain distinction (§8) is a genuinely different responsibility split from Modules 01–03, and the "signal vs. fact" framing (§8, §13) avoids the kind of overlap the governance framework's own F1 finding had to resolve.
- **Contract violations:** none found — every field Module 04 claims to own is either already reserved (`duplicate_of`/`version_group_id`/`version_rank`) or explicitly flagged as a proposed addition (`duplicate_signals`), and the one non-in-place-mutation behavior (§7 step 3) is disclosed prominently rather than buried.
- **Unnecessary complexity (Engine/Provider):** the opposite finding would be more apt — §14's decision to omit a Provider layer entirely is a *reduction* in complexity relative to Modules 02/03's pattern, and the reasoning given is sound, not a shortcut.

## Severity Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 2 (F1, F2) |
| Low | 3 (F3, F4, F5) |
| Cosmetic | 2 (F6, F7) |

## Disposition (first pass)

Seven findings, none Critical or High. No changes have been applied. Awaiting your decision on which findings to apply now, defer, or decline — and, separately, your confirmation on the seven open items `Module 04 Design.md` itself already flagged as pending (its own closing section: category scope, similarity/distance thresholds, the no-provider decision, the `duplicate_signals` field addition, the new action-log type, and the `Rules/` relocation question).

Design Refinement has not begun. No implementation code has been written.

---

## Second independent review

Scope of change since the first pass: exactly one addition — a new clarification in §5 (Module Contract) and a new §11A stating that hashing-algorithm/parameter changes are a storage/index migration event governed by `Frozen Module Change Policy`, not a Module Contract concern. Nothing else in `Module 04 Design.md` was touched; F1–F7 below were not applied. Per this project's established discipline (re-verify the whole document, not just the stated delta), the full document was re-read, not just the new section.

### Assessment of the new §5/§11A addition

Sound, and correctly modeled on `Governance/ARCHITECTURE_DECISIONS.md` decision #15 ("a module's internal architecture... is never part of the contract"). Two small, new Cosmetic observations, not blocking:

**G1 (Cosmetic)** — §5 and §11A each independently assert "hashing algorithms/this migration requirement are not part of the Module Contract." Not a contradiction, but a minor restatement — §11A could simply cross-reference §5's statement instead of re-deriving it. Smallest fix: one clause in §11A pointing back to §5 rather than restating the claim.

**G2 (Cosmetic)** — §11A names "a deliberate migration or complete index rebuild" as the required response to an algorithm change but doesn't note that a full rebuild's cost scales with total historical file count — a real, if minor, operational fact worth one sentence, consistent with how §20 already discloses other scaling costs. Smallest fix: one clause noting rebuild cost is proportional to accumulated file history, cross-referencing §20.

Neither finding affects the substance of the clarification itself; both are documentation-polish items.

### Status of F1–F7 (first pass)

Unchanged — none were applied, so none are resolved. Restated for a single source of truth:

| Finding | Severity | Status |
|---|---|---|
| F1 — batch processing order / tie-break unspecified | Medium | Open |
| F2 — `lookup_name_matches()` lacks category parameter | Medium | Open |
| F3 — no merge path for two pre-existing version groups | Low | Open |
| F4 — `duplicate_signals` can't hold multiple matches | Low | Open |
| F5 — Image vs. Screenshot "same category" ambiguity | Low | Open |
| F6 — action-log name doesn't reflect version detection | Cosmetic | Open |
| F7 — pipeline-ordering assumption unstated | Cosmetic | Open |
| G1 — §5/§11A restate the same contract-exclusion claim | Cosmetic | Open (new) |
| G2 — §11A doesn't note rebuild cost scales with history size | Cosmetic | Open (new) |

No new Critical, High, or Medium findings beyond the carried-over F1/F2.

## Severity Summary (second pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 2 (F1, F2) |
| Low | 3 (F3, F4, F5) |
| Cosmetic | 4 (F6, F7, G1, G2) |

## Disposition (second pass)

**Module 04 is not yet eligible for freeze.** Two Medium findings (F1, F2) remain open — neither has been approved or applied. Per your own stated gate ("only declare frozen if no Critical, High, or Medium findings remain"), freeze cannot be declared this pass.

The hashing-algorithm/Module-Contract clarification you requested is in place and sound (subject to the two new Cosmetic polish items, G1/G2). Everything else from the decision table you reviewed last turn — including F1 and F2, the two Medium items actually blocking freeze — is still awaiting your approval before it can be applied. No changes beyond the one requested clarification have been made.

---

## Third independent review — first principles, assuming nothing prior is resolved

Scope: all of F1–F7 have now been applied to `Module 04 Design.md`, along with the confirmed decisions on the seven original open items. This review does not treat any earlier finding as settled by virtue of "being addressed" — each is re-verified against the actual current text, and the whole document was re-read fresh, not diffed against memory of the prior version.

### H1 (High) — §7 step 3's "single best match" rule and its "cross-group conflict" rule directly contradict each other

**Explanation:** §7 step 3 reads: normalize the filename, call `lookup_name_matches(normalized_name, category)`, "score candidates via filename similarity (§10), **keeping only the single best-scoring candidate** (§17, F4) — any other candidates above the threshold are discarded, not retained as alternatives." The very next clause then says: "if the above-threshold candidates span two or more *different* existing `version_group_id`s" — i.e., the cross-group-conflict check (F3) requires inspecting the group membership of *multiple* above-threshold candidates. But those other candidates were just discarded one sentence earlier, before this check could ever run. As written, by the time the cross-group check executes, there is only ever one surviving candidate — it can never "span two or more different `version_group_id`s," because every other candidate that might belong to a different group has already been thrown away. F3's entire resolution mechanism, as specified, describes a check on data the design has already deleted. This is not a wording nitpick — an implementer cannot build this as written; the two sentences describe mutually exclusive data flows.

**Impact:** F3's confirmed behavior (flag, don't merge, leave the record unassigned pending review) can never actually trigger, because the precondition for detecting it (seeing more than one candidate's group membership) is designed out of existence one step earlier. Every actual cross-group scenario would instead silently fall through to whatever the single surviving candidate's group happens to be — exactly the silent, ungoverned merge F3 was written to prevent.

**Trade-off:** None — this isn't a case of competing goods, it's an internal contradiction that needs reconciling, not a judgment call.

**Smallest acceptable fix:** Reorder step 3's internal sequence rather than change any policy: first, gather *all* above-threshold candidates from `lookup_name_matches()` and check whether they span more than one distinct `version_group_id` (the cross-group check, F3) — before any discarding happens. Only if they do *not* span multiple groups (i.e., they already agree, or none has a group yet) does the design collapse to the single best-scoring candidate (F4) to determine `version_rank` against. This preserves both confirmed decisions exactly as intended — F4's guarantee is about what's ultimately *retained in `duplicate_signals`*, not about how many candidates may be *inspected* en route to that decision — it just requires stating the order correctly, which the current text does not.

### Carried over from the second review (not addressed this round, not new)

**G1 (Cosmetic)** — §5 and §11A each still independently assert "not part of the Module Contract" rather than one cross-referencing the other. Unchanged from the second review; still open.

**G2 (Cosmetic)** — §11A still doesn't note that a full index rebuild's cost scales with historical file count. Unchanged from the second review; still open.

### New, this pass

**G3 (Cosmetic)** — §9's first bullet contains a visible self-correction left in the prose: "regardless of `category`** (including `None`... no — `content_hash` is only `null` when..." reads as an unedited first-draft aside rather than settled documentation. Doesn't affect meaning (the correction is accurate), but a document heading toward freeze should state its conclusion cleanly rather than show its work. Smallest fix: delete the "(including `None`... no —" aside and state the conclusion directly ("in practice this means every category, including `Category.UNKNOWN`, since `content_hash` is only `null` when `status == "unreadable"`, and such records are filtered upstream").

### Findings not raised (checked, no issue found this pass)

- F1, F2, F5, F6, F7 — each re-verified against the current text independently (not assumed from the prior pass): F1's deterministic order is stated and consistent with the new determinism guarantee in §5; F2's `lookup_name_matches(normalized_name, category)` signature is consistent everywhere it's referenced (§6, §7, §16); F5's exact-category-match rule is stated once and not contradicted elsewhere; F6's rename is applied consistently in every section (verified via a full-document scan, no stray `detect_duplicates` references remain); F7's sequential-execution assumption is stated and doesn't conflict with anything in §7 or §21.
- The `version_conflict` dual-boolean design (one field for two conflict types, distinguished only in the log) is a legitimate, already-approved simplification — re-checked and not re-raised as a new finding, since it is sound on its own terms independent of H1's sequencing bug.

## Severity Summary (third pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 1 (H1) |
| Medium | 0 |
| Low | 0 |
| Cosmetic | 3 (G1, G2, G3) |

## Disposition (third pass)

**Module 04 architecture is not frozen.** One High finding (H1) remains: §7 step 3 describes an internally contradictory sequence that would make F3's cross-group-conflict detection unimplementable as written. Per your explicit instruction, I am stopping and reporting this rather than declaring freeze.

Recommended next step: approve H1's smallest-acceptable-fix (reorder step 3 so all above-threshold candidates are checked for cross-group membership before collapsing to the single best match), after which a fourth pass should re-verify specifically that fix plus re-confirm G1–G3 remain the only outstanding (Cosmetic, non-blocking) items.

---

## Fourth independent review — first principles, H1 applied

Scope: H1's approved fix has been applied to §7 step 3 (the four-sub-step sequence: collect all candidates → inspect for cross-group membership → if conflicted, flag and stop → else, select single best and continue). This review re-reads the entire document fresh, as if by a different engineer, and does not treat H1 as resolved merely because a fix was applied — its actual text was re-verified, and every other section was re-scanned rather than assumed unaffected by the change.

### H1 verification: resolved

The new §7 step 3 sequence is internally consistent. All above-threshold candidates are now collected before any cross-group check, and the single-best-match selection (F4) happens only *after* confirming no conflict — exactly reconciling the two previously-contradictory rules. Re-checked against §17 (single-best-match limitation, `version_conflict` dual meaning), §18 (`conflict_type` values), and §22's test bullets — all consistent with the corrected sequence. No remaining trace of the original contradiction.

### M1 (Medium) — "distinct existing `version_group_id`" doesn't say whether an ungrouped candidate counts as a "distinct" group

**Explanation:** §7 step 3.2 (as corrected by H1) reads: "whether the collected candidates, taken together, already belong to more than one distinct existing `version_group_id`." In the common case where a version chain is being created for the *first* time, one candidate will already have a `version_group_id` (or none of them will) while a newly-arriving candidate has `version_group_id = null`. As written, it is not explicit whether `null` counts as a "distinct" value alongside a real UUID. Read too literally, a candidate set of `[null, "abc-123"]` could be mis-implemented as "two distinct values → cross-group conflict" — which would be wrong: this is the single most common, entirely ordinary case (an existing ungrouped file being matched against a new one for the first time), not a conflict at all. The word "existing" is likely intended to exclude `null`, but the document doesn't say so explicitly, and this is exactly the kind of implicit-inference gap the rest of the document (and this project's whole review discipline) otherwise refuses to leave to a reader's assumption.

**Impact:** If implemented per a literal reading, nearly every *first-time* version-chain creation (the primary case §9's whole feature exists for) could be misclassified as a cross-group conflict — the feature would rarely, if ever, successfully create a new `version_group_id`, since the very first pairing almost always involves at least one still-ungrouped candidate.

**Trade-off:** None — this is an under-specification, not a competing design choice.

**Smallest acceptable fix:** Add one clarifying clause to step 3.2: "a candidate with no `version_group_id` (`null`) is not itself a distinct group and never counts toward this check — the conflict exists only when two or more candidates carry two or more different *non-null* `version_group_id` values."

### M2 (Medium) — `name_index.json`'s described shape (exact-key dict) doesn't support the fuzzy matching §10 requires, and §16 never says `lookup_name_matches()` performs a scored scan

**Explanation:** §16 describes `Database/FileIndex/name_index.json` as `{ "<normalized_name>": ["<file_id>", ...] }` — a dict keyed by exact normalized name — and, unlike the parallel `phash_index.json` bullet (which explicitly states "`lookup_phash_matches()` must scan for any key within the max distance, not just an exact key match... a linear or bucketed scan over existing entries, not a single dict access"), §16 never states the equivalent for `lookup_name_matches()`. But §10's entire similarity-matching design is built on `rapidfuzz.fuzz.ratio()` scoring with a threshold of 90 out of 100 — explicitly *not* requiring an exact match (a score of 90–99 covers near-but-not-identical normalized names, e.g. a typo'd rename that doesn't collapse to the same string after normalization). A literal exact-key dict lookup could only ever return candidates whose normalized name is byte-identical to the input's — it could never surface a 92-scoring near-match with a different normalized string, which is precisely the case `rapidfuzz` exists to catch. As written, it's unclear whether `lookup_name_matches()` is meant to (a) do an exact-key dict lookup only (in which case §10's fuzzy-scoring design is largely moot — most of its stated purpose could never be exercised), or (b) scan every entry in `name_index.json` and score each one, the same way `phash_index.json`'s lookup already explicitly does. This is the same category of gap as the (resolved) F2/H1 issues — a described data structure and a described algorithm that don't obviously fit together — just not yet caught because it's a step removed from those two.

**Impact:** If an implementer builds `lookup_name_matches()` as a literal dict-key lookup (the natural reading of `name_index.json`'s described shape), the core "near-duplicate filename" version-chain feature would silently degrade to "exact-normalized-name matching only" — functionally present but far weaker than designed, with no test likely to catch it unless the test fixtures happen to include a non-identical-but-similar filename pair.

**Trade-off:** None — again an under-specification, not a considered choice.

**Smallest acceptable fix:** Add one sentence to §16's `name_index.json` bullet, mirroring the `phash_index.json` bullet's existing language: `lookup_name_matches(normalized_name, category)` scans every same-`category` entry in `name_index.json` and scores each stored normalized name against the input via `rapidfuzz.fuzz.ratio()` (§10), returning every `file_id` whose score clears the threshold — not a single exact-key dict access. (A future performance optimization, same as `phash_index.json`'s, is out of scope for this design per §20/§27.)

### Carried over, still open (not addressed this round, not new)

- **G1 (Cosmetic)** — §5 and §11A still independently restate "not part of the Module Contract" rather than one cross-referencing the other.
- **G2 (Cosmetic)** — §11A still doesn't note that a full index rebuild's cost scales with historical file count.
- **G3 (Cosmetic)** — §9's first bullet still contains the unedited "(including `None`... no —" self-correction aside.

### Findings not raised (checked, no issue found this pass)

- F1–F7 re-verified once more against the current text (not assumed carried from the third pass): all remain correctly resolved and internally consistent with each other and with the corrected §7 step 3.
- The rest of §16 (`hash_index.json`, `version_history.json` shapes) — re-checked for the same "structure vs. algorithm" mismatch that produced M2; neither shows the same gap (`hash_index.json`'s exact-key lookup correctly matches `content_hash`'s exact-equality semantics; `version_history.json`'s append/update shape is consistent with §7's description of when it's written).

## Severity Summary (fourth pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 (H1 resolved) |
| Medium | 2 (M1, M2) |
| Low | 0 |
| Cosmetic | 3 (G1, G2, G3) |

## Disposition (fourth pass)

**Module 04 architecture is still not frozen.** H1 is resolved, but this fresh pass — reviewing the whole document again rather than only the changed section — found two new Medium findings (M1, M2), both under-specifications in the version-chain matching logic that could cause real functional problems if implemented literally, and both fixable with one clarifying sentence each. Per your instruction, stopping and reporting rather than declaring freeze.

---

## Fifth independent review — first principles, M1 and M2 applied

Scope: M1's fix (§7 step 3.2, defining that `null` never counts as a distinct existing version group) and M2's fix (§16's `name_index.json` bullet, clarifying candidate-retrieval-then-fuzzy-scoring) are both applied. This review re-reads the complete document again, does not limit itself to the two changed spots, and treats every earlier finding — including H1, F1–F7, and the confirmed decisions — as unverified until re-checked against the current text.

### M1 verification: resolved

§7 step 3.2 now explicitly states that `null` is "unassigned, not a group of its own," that conflict requires "two or more candidates carry two or more *different, non-null* `version_group_id` values," and that "every candidate is unassigned, or at most one non-null `version_group_id` appears among them" proceeds normally. This directly closes the gap: the common first-time-pairing case (one ungrouped candidate, one new file) can no longer be misread as a cross-group conflict. Re-checked against step 3.4's join/create logic (still consistent) and §17's dual-meaning description (still accurate, no contradiction).

### M2 verification: resolved

§16's `name_index.json` bullet now states plainly that it "is a candidate-retrieval index, not the fuzzy matcher itself," that "an exact-key lookup into it is not sufficient," and that `lookup_name_matches()` "performs candidate retrieval... followed by fuzzy similarity evaluation... returning only those clearing the threshold." This directly resolves the ambiguity between the described data structure and §10's fuzzy-matching algorithm.

### L1 (Low) — §20's performance description now inconsistent with M2's clarification

**Explanation:** §20's first bullet groups `lookup_hash()` and `lookup_name_matches()` together as "targeted index lookups" contrasted against the O(N×M) full-store-scan problem — phrasing that reads as though both are equally fast, dict-style O(1) lookups. But `lookup_hash()` genuinely is a single dict access, while `lookup_name_matches()`, per M2's own new clarification in §16, performs "candidate retrieval... followed by fuzzy similarity evaluation" — a scan-and-score operation much closer in character to `lookup_phash_matches()` (which §20's *second* bullet already, correctly, describes as unable to be "a simple dict lookup"). §20 doesn't yet reflect that `lookup_name_matches()` belongs with the second bullet's category, not the first's.

**Impact:** Informational/documentation-accuracy only — §16 (the authoritative section for this function's actual behavior) is already correct after M2, so this doesn't leave genuine behavioral ambiguity the way M1/M2 did. But an implementer skimming only §20's performance framing, without cross-referencing §16, could underestimate `lookup_name_matches()`'s real cost profile.

**Smallest acceptable fix:** Move (or cross-reference) `lookup_name_matches()` into §20's second bullet alongside `lookup_phash_matches()`, since both now share the same "scan same-scope entries, score each" performance profile — leaving §20's first bullet to describe only `lookup_hash()`'s true O(1) case.

### L2 (Low) — §22's test strategy doesn't explicitly commit to a regression test for M1's null-doesn't-count case

**Explanation:** §22 commits to a "Cross-group conflict handling (F3)" test covering the *positive* case (candidates spanning two existing groups → conflict flagged). It does not commit to the *negative* case M1 exists to protect: one unassigned (`null`) candidate plus one non-null-group candidate (or all-`null` candidates) must proceed as ordinary version-chain creation, not be misflagged as a conflict. Since M1's whole finding was that this exact scenario was the single most common real-world case at risk, its absence from the named test list is a real, if small, completeness gap.

**Smallest acceptable fix:** Add one bullet to §22: "M1 regression: a candidate set containing one unassigned (`null`) `version_group_id` and one non-null `version_group_id` (or all `null`) proceeds as ordinary version-chain creation/joining, never a `cross_group` conflict."

### Carried over, still open (unchanged this round)

- **G1 (Cosmetic)** — §5 and §11A still independently restate "not part of the Module Contract."
- **G2 (Cosmetic)** — §11A still doesn't note that a full index rebuild's cost scales with historical file count.
- **G3 (Cosmetic)** — §9's first bullet still contains the unedited "(including `None`... no —" self-correction aside.

### Findings not raised (checked, no issue found this pass)

- F1–F7 and H1 re-verified once more against the current text (not assumed carried from any prior pass) — all remain correct and mutually consistent.
- Considered, not raised: a record that hits the cross-group-conflict path keeps `duplicate_of`/`version_group_id`/`version_rank` all `null`, meaning it will be re-examined (and potentially re-logged) on every subsequent batch run until the underlying groups are manually resolved. This falls out naturally from the existing "only process once, based on field state" idempotency rule already used by every earlier module, and re-flagging an unresolved conflict on every run is arguably the *correct* behavior (staying visible until resolved) rather than a defect — not raised as a finding, but noted here for transparency since it was seriously considered.
- Re-checked `hash_index.json` and `version_history.json` once more for the same "structure vs. algorithm" mismatch class that produced M2 — neither shows it.

## Severity Summary (fifth pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 2 (L1, L2) |
| Cosmetic | 3 (G1, G2, G3) |

## Disposition (fifth pass) — Module 04 architecture is frozen

No Critical, High, or Medium findings remain. Per your stated gate, this pass clears the bar for freeze.

**Module 04 (Duplicate & Version Detection) architecture is frozen**, effective this pass. Five Low/Cosmetic items remain, explicitly not blocking, listed separately as carried-forward, non-required housekeeping:

- L1 (Low) — §20's performance framing should regroup `lookup_name_matches()` with the scan-based lookups, not the O(1) ones.
- L2 (Low) — §22 should name an explicit regression test for M1's null-doesn't-count case.
- G1 (Cosmetic) — §5/§11A's redundant "not part of contract" restatement.
- G2 (Cosmetic) — §11A's missing rebuild-cost-scales-with-history note.
- G3 (Cosmetic) — §9's unedited self-correcting aside.

Per `Governance/ENGINEERING_STANDARD.md`'s lifecycle, this closes the Design → Independent Architecture Review → Design Refinement → Design Freeze sequence for Module 04's architecture. Implementation (the next lifecycle stage) has not begun and does not begin without your explicit instruction, consistent with the standing "do not skip or merge phases" directive.

---

## Owner acceptance

The project owner has reviewed the fifth pass's disposition and accepted L1, L2, G1, G2, and G3 as documented, non-blocking technical debt — recorded here exactly as they stand, with no further documentation polish applied at this stage. **Module 04 (Duplicate & Version Detection) architecture is officially frozen.** `Module 04 Design.md` is not to be modified further except under the Frozen Module Change Policy. The lifecycle proceeds to Implementation.

---

## Post-freeze correction (implementation-discovered defect, 2026-07-08)

While implementing §7 step 3's first-time-group-creation sub-step, a real contradiction surfaced between §4/§5 (Module Contract — disclosed the one side-effect exception as `version_rank` only) and §7's own plain language ("mint a new `version_group_id` **shared between** this record and the matched candidate," which requires the matched candidate's `version_group_id` to be set too). None of the five prior review passes caught this — it was found only when actually trying to build the step faithfully, exactly the scenario the project owner's standing instruction ("if implementation exposes an architectural defect, stop immediately and report it") anticipated.

Reported to the project owner rather than resolved unilaterally. Two options were presented: broaden the disclosed exception to cover both fields (smallest change, matches §7's actual, already-approved mechanics), or keep the contract narrow and defer joining to some future reprocessing pass (no design-doc change, but no guarantee a real version chain ever actually gets joined promptly). **The project owner selected the first option.** `Module 04 Design.md` §4, §5, §7, and §22 have been amended accordingly — the side-effect exception now covers `version_group_id` and/or `version_rank` (never any other field), with an inline note at §7 marking exactly what changed and why. No other mechanic changes: a candidate that already belongs to a group is unaffected by this correction (its `version_group_id` didn't change before, still doesn't); this only affects the specific first-time-pairing case that was previously impossible to implement as written.

This does not reopen Module 04's freeze or require a sixth full independent architecture review — it is a narrow, disclosed correction to one already-identified implementation blocker, applied with the project owner's explicit sign-off, consistent with how a defect discovered after freeze is handled under this project's change-management discipline. Implementation continues from here.

---

## Post-freeze corrections #2 and #3 (Independent Implementation Audit findings H1 and M1, 2026-07-08)

The Independent Implementation Audit (`Module 04 Implementation Audit.md`, first pass) found one High and three Medium findings. Two of them — H1 and M1 — required a design correction under the Frozen Module Change Policy before implementation could proceed; both are recorded here, mirroring `Module 04 Design.md`'s own §7/§10 amendments.

**H1 (idempotency) → Post-freeze correction #2:** the idempotency check §7 originally froze (`duplicate_of`/`version_group_id`/`version_rank` all `None`) does not detect "already processed" for the single most common real outcome — a record where Module 04 ran and correctly found nothing. Confirmed empirically: the same never-changing, genuinely-unique record was run through `detect_duplicates_batch()` twice and produced two action-log entries instead of one. Root cause: the check used three *outcome* fields that can legitimately all stay `None` after a fully successful run, instead of `duplicate_signals` — the one field §5/§17 already guarantee is always populated once Module 04 has touched a record, regardless of outcome. Corrected `§7` to key "already processed" off `duplicate_signals is not None`, with one narrow, precisely-identifiable exception preserved without any new field: a record in the unresolved cross-group-conflict state (`duplicate_signals.version_conflict == True` and `version_group_id is None` — exactly and only the step-3.3 outcome) remains eligible for re-examination on every run, exactly matching the fifth review pass's own explicit, deliberate decision that this specific state should stay visible rather than be silently skipped. Verified by exhaustive case analysis that no other outcome produces that same field combination, so the exception cannot misfire. Does not touch the Module Contract (§5) or change any field's final value — only which records are internally selected for processing.

**M1 (candidate tie-break) → Post-freeze correction #3:** an implementation-time tie-break (prefer an already-grouped candidate over an ungrouped one when two or more candidates score identically on filename similarity) had been added silently during implementation-phase bug-fixing, with no basis in §10's frozen text and no report to the project owner — a process gap, since this is the same category of under-specification as F1/M1/M2 from the architecture-review stage, which were correctly escalated, and as the version_group_id/version_rank gap earlier in this same implementation pass, which was also correctly escalated. This one was not. Corrected by formally adding the rule to §10 (prefer a candidate with a non-`null` `version_group_id` on a tie, since joining an established group is always at least as correct as minting a redundant new one) rather than reverting to undefined, iteration-order-dependent behavior — the smallest fix that both removes the undocumented-policy problem and preserves the already-tested, sensible behavior.

Neither correction reopens the full five-pass architecture review or requires a sixth independent pass — both are narrow, disclosed corrections to implementation-audit-discovered gaps, applied under the same Frozen Module Change Policy mechanism as the first post-freeze correction. A second independent implementation audit follows, from first principles, assuming nothing from the first pass is resolved merely because a fix was documented.

---

## Post-freeze correction #4 (design-completeness gap, discovered during UAT, 2026-07-08)

Module 04 UAT's first real run (`Tests/Module 04 UAT Plan.md`, Finding UAT-1) surfaced a real, reproducible defect: Image and Screenshot records were cross-flagged as near-duplicates of each other, contradicting §9's own "confirmed" F5 decision that Image and Screenshot are strictly separate categories "for both near-duplicate and version-chain grouping."

**Before invoking the Frozen Module Change Policy, the project owner requested an independent verification** of whether this was genuinely an implementation defect or a design defect, re-reading `Module 04 Design.md`, this review document, both Implementation Audit passes, and the actual implementation from first principles. That verification found:

- §9's F5 bullet unambiguously requires category-scoping for *both* detection types.
- But §7 step 2, §11, and §16 — the sections that actually specify the near-duplicate mechanism — never mention category scoping at all, in direct contrast to how thoroughly the version-chain half of the same requirement is wired through those same layers (`lookup_name_matches(normalized_name, category)` is explicit at every layer; `lookup_phash_matches(phash, max_distance)` never gained the equivalent treatment).
- This review's own **finding F5** (below, in the original architecture-review record) is the origin of the ambiguity: it explicitly named the near-duplicate half as uncertain ("§9/§10 require version-chain, **and, by extension, near-duplicate**, candidates to share the same `category`... never states whether Image and Screenshot... must match exactly") and its recommended fix — "one clarifying sentence in §9" — was applied to §9 only. The sibling finding **F2** (`lookup_name_matches()` needing a real fuzzy scan) received full mechanism-level follow-through into §16; F5's near-duplicate half never did.
- Both Implementation Audit passes checked that near-duplicate detection is scoped to the Image/Screenshot category *group* (i.e., never runs for Invoice/Resume/etc.) but never re-checked F5's finer claim that Image and Screenshot are mutually exclusive *within* that group — because the one existing regression test for F5 (`test_engine_image_and_screenshot_never_group_with_each_other`) only ever exercised the version-chain half.

**Conclusion (accepted by the project owner):** this is a design-completeness gap — an already-confirmed decision (§9/F5) that was never fully propagated into its own mechanism sections, the same way its sibling decision (F2) was — not an implementation defect. The implementation faithfully built exactly what §7/§11/§16 specified; no section of the frozen design ever instructed an implementer to scope `lookup_phash_matches()` by category.

**Correction applied:** §7 step 2, §11, and §16 are amended so `lookup_phash_matches()` is category-scoped, mirroring `lookup_name_matches()`'s existing treatment exactly (candidate `file_id`s cross-referenced against their stored `category` via the metadata store; no change to `phash_index.json`'s own key/value shape). §20's performance note and §22's test-strategy list are updated to match. Full text: `Module 04 Design.md`, post-freeze correction #4.

This does not reopen the full five-pass architecture review — it is a narrow, disclosed correction to a gap this review's own F5 finding already named but did not fully resolve, applied under the same Frozen Module Change Policy mechanism as corrections #1–#3. A fresh, targeted design review (scoped to this correction, verifying no remaining internal contradiction) follows before re-freeze; implementation of the corresponding code change follows the re-freeze, not the other way around.

### Targeted design review of correction #4 (2026-07-08)

Scope: verify the correction (§7 step 2, §11, §16, §20, §22 amendments in `Module 04 Design.md`) is internally consistent with the rest of the frozen document — not a re-review of the whole design.

Checked section-by-section: §6 (internal architecture — `lookup_phash_matches()`'s signature extension now listed alongside `lookup_name_matches()`'s), §9 (F5's original "confirmed" text needed no change — it was always correct; only the mechanism sections lagged it), §10 (unaffected — filename-similarity matching, not perceptual-hash matching), §11 (near-duplicate description now explicitly category-scoped, with a corrected note on the "both index lookups avoid a full-store scan" claim, which — accurately, and true of `lookup_name_matches()` even before this correction — needed a caveat that category cross-referencing still performs one *targeted* metadata-store read), §16 (phash_index bullet now mirrors the name_index bullet's category-parameter treatment sentence-for-sentence, without changing either index's on-disk shape), §17 (`DuplicateSignals` — no new field needed, since category is cross-referenced via the metadata store, not stored redundantly, the same choice already made for name-based matching), §20 (performance note extended to disclose the added metadata-store cross-reference cost, matching this review's own earlier L1 finding's logic), §22 (test strategy gained the missing near-duplicate F5 test, and the existing F5 bullet now explicitly names both halves), §26 (edge-case bullet 1 already correctly scoped "near-duplicate/version-chain... category scoping is load-bearing" — no change needed, already consistent with the correction), §27–28 (no conflict).

**No remaining internal contradiction found.** The correction is fully and consistently propagated everywhere the original gap could have resurfaced. **Module 04 Design.md, as corrected, is re-frozen as of this entry.** Implementation of the minimal corresponding code change (`lookup_phash_matches()`'s signature, `_check_near_duplicate()`'s call site, and the new regression test) follows from this re-freeze, per the Frozen Module Change Policy, not the other way around. A fresh Independent Implementation Audit follows the code change, from first principles, per the same discipline used after corrections #2/#3.
