# Version 0.9.1 Implementation Plan

**Date:** 2026-07-20 · **Status:** Planning only — no production code has been touched or modified while producing this document, per explicit instruction.
**Source evidence:** `PATTERN_TRACKER.md` (cross-run consolidation) and `VALIDATION_LEDGER.md` (Run 001–003 detail), current as of Run 003.
**Governed by:** `Governance/ENGINEERING_STANDARD.md` (the module lifecycle any accepted candidate below would enter — Design → Review → Freeze → Implementation → Independent Audit → Integration Testing → UAT → Release Audit) and `Governance/FROZEN_MODULE_CHANGE_POLICY.md` (both candidate modules, 02 and 04, are Frozen/released at v1.0.0 — any accepted change is a post-freeze change, not fresh implementation).
**Scope of this document:** identify which validation findings qualify as engineering candidates, define what "fixed" would measurably mean for each, estimate risk and blast radius, and enumerate the regression coverage a future implementation would have to pass. It does not design a fix, does not write or modify code, and does not itself authorize implementation — under `FROZEN_MODULE_CHANGE_POLICY.md` §1, that requires separate, explicit project-owner approval per candidate, after this plan is reviewed.

**Status update, 2026-07-23:** Candidate C1 (PT-002) has since been designed, implemented, regression-tested, re-validated, and closed — see `PT002_POSTMORTEM.md` for the full record. This plan's own C1 section (§2) is now a historical account of what was proposed, superseded by what was actually approved and built; it is not rewritten, per this project's standing append-only convention. Candidate C2 (PT-003, §3) remains open and unimplemented — see `PROJECT_BACKLOG.md` for its current status and priority.

**Status update, 2026-07-23 (later same day):** Candidate C2 (PT-003) has since also been designed, independently reviewed (2 rounds), implemented, regression-tested, re-validated, and closed — see `PT003_POSTMORTEM.md` for the full record. This plan's own §3 is likewise now a historical account of what was proposed at candidate-selection time, superseded by what was actually approved and built (the approved design's corroborating-signal mechanism differs in some particulars from this section's own early sketch — see the design package itself, `Build-out/04 Duplicate & Version Detection/Module 04 Post-Freeze Design Correction — PT-003.md`, for the actual selected approach). Not rewritten, per the same append-only convention. Both candidates this plan identified are now closed; no `PATTERN_TRACKER.md` finding remains as active engineering work as of this update.

---

## 1. Candidate selection methodology

`PATTERN_TRACKER.md` currently holds 11 findings (PT-001 through PT-011). This plan includes a finding as an engineering candidate only if **all** of the following hold:

1. **Classification is Confirmed Pattern** — observed independently across 2 or more runs/datasets, per `PATTERN_TRACKER.md` §1's own definition. Single Observation findings are excluded regardless of how compelling the one occurrence looks, per this validation phase's standing instruction ("do not propose fixes after a single occurrence unless it is a Critical safety issue") — none of the current findings are Critical.
2. **Disposition is a genuine defect/gap in the released pipeline's own code or rules** — not User Expectation (matches already-documented, designed behavior), not Environment Issue (attributable to the validation session's tooling, not the product), and not a positive finding (nothing to fix).
3. **Root cause is directly confirmed against real code**, not merely inferred from a symptom — every candidate below traces to a specific rule/function, not a hypothesis.

Applying this filter to the current Pattern Tracker yields exactly **two** candidates: **PT-002** and **PT-003**. Every other finding is excluded — see §4 for the full accounting of why each one is out of scope for v0.9.1.

This is a short list by design. It reflects the evidence honestly: three runs, one of them blocked entirely, and just under 60 files processed in total, is enough to confirm two real, well-understood patterns and rule out treating nine other observations as engineering work — not enough to have discovered everything a mature pipeline eventually needs. `VALIDATION_PROGRESS.md` §5 already recommends the datasets that would either add new confirmed candidates or further characterize these two.

---

## 2. Candidate C1 — PT-002: Screenshot misclassification of real non-screenshot images

### Evidence summary
- **Confirmed across 2 independent runs, 2 non-overlapping datasets.** Run 002: 9/9 real scanned-document photos misclassified. Run 003: 6/6 directly visually-confirmed misclassifications across a materially more diverse content set (a real personal photo shared over WhatsApp, a product photograph, a marketing banner graphic, an AI-generated portrait, and both files in a false version-pairing) — plus 12 further files predicted, not confirmed, to follow the same pattern. One contrast case (`IMG_20211002_001030_Bokeh.jpg`, genuine camera EXIF) correctly classified `Image` in Run 003, isolating the trigger precisely.
- **Severity:** Medium in both runs — never reached `auto`/`approval_required` tier in either run (caught by the confidence system), so no incorrect file was ever actually filed. Confidence in root cause: High.

### Root cause (directly confirmed)
`Rules/Classification Rules.md` §"Screenshot vs. plain Image split": an image-family file (`.png .jpg .jpeg .heic .webp`) is treated as Screenshot if **any** of three conditions hold, one of which is "no camera EXIF data present (no lens/camera model tag)." There is no route back to `Image` (or to `Document`) once this condition fires — confirmed by direct code reading (`src/pipeline/classification.py`'s `classify_screenshot_or_image()`) and by real, independently measured EXIF data (Pillow) on 28 real files across both runs. The implementation faithfully executes the rule as written; this is a rule-completeness gap, not an implementation defect.

### Candidate engineering directions (not a design decision — for the future Design phase to evaluate)
Presented as options because selecting between them is exactly the work the Design phase (`ENGINEERING_STANDARD.md`) exists to do, with its own review cycle — not a decision this planning document should make unilaterally:

- **Option A — add a second, more specific signal before falling back to EXIF-absence.** E.g., dimension/aspect-ratio heuristics tuned for document-page proportions (already partially informed by the existing `_COMMON_SCREEN_RESOLUTIONS` precedent in `src/core/images.py`), or filename-pattern recognition for common AI-image-generator export conventions (`DALL·E`, `ChatGPT Image`, similar). Bounded, additive — likely stays within Module 02's existing two-category (Screenshot/Image) split.
- **Option B — extend Module 02's vision deep-pass to image-family extensions.** Text-bearing extensions already have a route to `Document`/`Resume`/etc. through the deep pass (`is_text_bearing()`); image-only files currently have no equivalent path even with a live provider available. This is the more structural fix — it would let a live-judgment provider actually distinguish "a photographed contract" from "a product photo" from "a real screen capture," which no EXIF-only heuristic ever could — but is a larger change to Module 02's decision flow and its provider-call volume/cost profile.
- **Option C — no code change; rule-documentation clarification only.** If review concludes the current binary Screenshot/Image split is an acceptable, disclosed simplification for v1 (the safety net already prevents any incorrect auto-filing), the smallest possible action is updating `Rules/Classification Rules.md` and `TECHNICAL_DEBT_REGISTER.md` TD-16 to reflect the now-confirmed, broader real-world scope, with no code change at all.

The Design phase must also determine whether the chosen option changes `Release/Module02/MODULE_CONTRACT.md`'s declared guarantees (Option A likely doesn't; Option B likely does, since it changes what "Screenshot" vs. "Image" vs. a text-bearing category means for a class of file, which affects the version-bump decision in §2.4 below).

### Measurable acceptance criteria (for whichever option is eventually approved and implemented)
1. **Regression-zero on existing Screenshot-positive controls:** every existing case that should classify `Screenshot` (`Rules/Classification Rules.md`'s own filename-marker and screen-resolution signals) continues to do so — 100% pass rate on the existing Screenshot-path unit tests (§5 below), unchanged.
2. **Real camera-photo contrast case still passes:** `IMG_20211002_001030_Bokeh.jpg`-class files (image-family, genuine camera EXIF present) continue to classify `Image` with 100% accuracy — the fix must not regress the one case that already works correctly.
3. **Held-out real-world accuracy improvement, measured on a fresh, unseen dataset** (not Run 002's or Run 003's own files, to avoid tuning to the evidence that motivated the fix): on a new sample of ≥30 real, non-screenshot, EXIF-less images spanning at least 3 of the content shapes already observed (scanned document photo, messaging-app-shared personal photo, product/marketing graphic), correct (non-`Screenshot`) classification rate must reach **≥85%**, with the specific misses disclosed and root-caused, not just tallied.
4. **No new false-negative on genuine screen captures:** a dedicated adversarial set of ≥10 real screenshots (application UI captures, browser captures) must still classify `Screenshot` at 100% — the fix must not overcorrect into misclassifying real screenshots as `Image`/`Document`.
5. **Downstream correctness, not just Module 02 in isolation:** for any file reclassified out of `Screenshot`, its Module 03 extraction, Module 05 naming, and Module 06 confidence-tier outcome must all be independently verified consistent with its new category's schema — a category fix that only changes the `category` field while every downstream field still reflects the old category would not satisfy this criterion.

### Risk estimate
**Medium risk, contained blast radius, but real dependency chain.** Module 02 is frozen at v1.0.0 with three direct downstream dependents that read `category`: Module 03 (extraction schema is keyed by category — `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` in `src/pipeline/metadata.py`), Module 05 (naming templates are keyed by category, `Rules/Naming Rules.md`), and Module 06/07 (confidence hard floors and folder routing both branch on category, `Rules/Confidence Rules.md`/`Rules/Folder Rules.md`). A change that moves files out of `Screenshot` into a different category changes what happens at every one of those later stages, not just at classification. This is expected and by design (the whole point of the fix), but it means the regression surface is pipeline-wide, not module-local — consistent with why `FROZEN_MODULE_CHANGE_POLICY.md` §5.2 requires confirming "every module downstream of the fixed one is unaffected." Likelihood of a clean, contained fix is high (the root cause is precisely understood); likelihood of the fix requiring a genuine contract change (new/renamed category, changed guarantee text) is moderate and depends on which option (§2.2 above) is selected — Option B carries materially higher contract-change risk than Option A.

### Regression tests that must be rerun
- **Module 02 unit suite in full**, with particular attention to the Screenshot-split tests already covering this exact code path: `test_needs_screenshot_split_true_for_image_extensions`, `test_classify_screenshot_or_image_detects_real_screenshot_by_resolution_and_name`, `test_classify_screenshot_or_image_detects_real_product_photo_as_image`, `test_classify_screenshot_or_image_filename_marker_wins_immediately`, `test_classify_screenshot_or_image_true_photo_with_camera_exif_and_odd_dimensions`, `test_engine_deterministic_screenshot` (`src/pipeline/test_classification.py`).
- **A new, permanent regression test** for the specific defect class, per `FROZEN_MODULE_CHANGE_POLICY.md` §5.3 — at minimum, a synthetic fixture reproducing "EXIF-less, non-screenshot real content" so the same gap cannot silently recur.
- **`test_module_contract_immutability_*`-style tests** (Module 02's own non-owned-field immutability guarantee) re-run to confirm the fix doesn't leak into fields it shouldn't touch.
- **Module 03/05/06/07 unit suites**, since their category-branching logic is exercised by whatever new category value(s) affected files now carry — `src/pipeline/test_metadata.py`, `test_naming.py`, `test_confidence.py`, `test_execution.py`.
- **`Tests/Module 02 Integration Test Plan.md` and `Tests/Module 02 UAT Plan.md`** scenarios re-run against the corrected code, scoped to the affected behavior per §5.2's "not a full repeat of the module's original test surface" allowance — but including at least one full Module 01→07 chain run to verify downstream correctness (acceptance criterion 5 above).
- **Full project-wide regression suite** (currently 716/716 passing, confirmed this session) must remain at 100%.
- **13-check Pipeline Contract Verification gate**, re-run for Module 02 specifically (`Governance/PIPELINE_CONTRACT_VERIFICATION.md`), per `FROZEN_MODULE_CHANGE_POLICY.md` §5.5.
- **A fresh Validation run** (this framework) against a new real-world sample, per acceptance criterion 3 — the existing Run 002/003 data cannot itself be used to certify the fix, since it's the data that motivated it.

---

## 3. Candidate C2 — PT-003: False-positive version-chain grouping

### Evidence summary
- **Confirmed across 2 independent runs, 2 non-overlapping datasets.** Run 002: 3/9 files (distinct academic mark-sheet documents, same institution/template, different grade levels) wrongly grouped into 3 separate false version chains. Run 003: 1 false pairing (`image (2).png` "superseded by" `image (42).png`) — two images with no shared subject matter, different file sizes, different hashes, a cleaner false positive with less obvious shared signal than Run 002's template-similarity case.
- **Severity:** Medium in both runs — the confidence safety net correctly withheld all filing action in every instance (0 files ever auto-archived as "superseded"); the risk is entirely in what the Duplicate Report *tells* a human reviewer, not in any unsafe automated action. Confidence in root cause: Medium (the effect is fully confirmed and reproducible in both runs; the specific triggering signal within Module 04's matching logic has not been isolated to a specific function/comparison in either run).

### Root cause (confirmed at the effect level; not yet isolated at the mechanism level)
Module 04 (`src/pipeline/duplicate_detector.py`) is fully deterministic with no provider layer (`Module 04 Design.md` §14, `Release/Module04/MODULE_CONTRACT.md`) — version-chain candidacy is driven by perceptual-hash distance (`_MAX_PHASH_DISTANCE = 5`, category-scoped since the post-freeze correction that resolved Run 001-era UAT-1) and/or filename-token parsing (`normalize_filename()`, `parse_version_token()`). Two runs have now produced false positives via what appear to be two different triggering paths — Run 002's grouped files share a real template (same institution's document layout) and filename tokens ("10th"/"12th"/"1st Semester" plausibly parsed as version-like); Run 003's grouped files share neither a template nor any filename-token similarity beyond both being named `image (N).png`, which is exactly the kind of generic, tool-assigned filename pattern common in real downloaded content. Which specific comparison(s) in `DuplicateDetectionEngine` produced the Run 003 pairing has not yet been traced to a specific line of matching logic — this is itself the first, necessary step of any future Design phase for this candidate, not something this plan asserts an answer to.

### Candidate engineering directions (not a design decision)
- **Option A — tighten the phash distance threshold and/or add a corroborating-signal requirement.** If perceptual-hash proximity between visually dissimilar images is the Run 003 driver, `_MAX_PHASH_DISTANCE = 5` may be too permissive for certain image categories, or version-chain candidacy may need to require phash proximity **and** some independent corroborating signal (filename-token match, close-in-time discovery, similar file size) rather than either signal alone.
- **Option B — add a live-judgment provider for version-chain confirmation, exactly as `Release/Module04/KNOWN_LIMITATIONS.md` already anticipated at release ("a future version could add a live-judgment provider if the deterministic signals prove insufficiently discriminating in practice — not built, and not needed, for v1").** This validation phase's evidence is a reasonable candidate trigger for revisiting that exact, pre-disclosed option — not a new idea introduced here.
- **Option C — no code change; disclosure and reporting-language change only.** If the Design phase determines the false-positive rate is an acceptable cost of a purely deterministic Module 04 (matching its own documented "no provider" design philosophy), the smallest action is softening the Duplicate Report's own language (`src/pipeline/reporting.py`) from an assertive "Superseded Version" framing to a more hedged "possible version relationship — review" framing, reducing the real-world risk (a user trusting the label and manually archiving a non-superseded file) without touching the matching logic itself.

Root-cause isolation (tracing Run 003's false pairing to a specific comparison in the matching logic) should happen **before** the Design phase selects between these options — Option A specifically cannot be responsibly scoped without it.

### Measurable acceptance criteria (for whichever option is eventually approved and implemented)
1. **Root cause isolated to a specific function/comparison** before any code change is designed — a precondition, not a post-fix criterion, given Confidence is currently only Medium.
2. **Regression-zero on Module 04's existing true-positive version-chain tests** — 100% pass rate, unchanged, on the existing version-chain unit tests (§5 below), so a fix for false positives doesn't cost real recall.
3. **False-positive rate reduction, measured on a fresh, unseen dataset:** on a new sample containing both (a) a same-template/similar-content-shape document series of at least 15 files (a positive-control-adjacent stress test for the exact Run 002 mechanism) and (b) at least 20 generically-named, visually-unrelated real image files (the exact Run 003 mechanism), the corrected logic must produce **0 false-positive version-chain groupings** on set (b) and **≤1 false positive per 15 files** on set (a) — a specific, falsifiable bar, not "fewer than before."
4. **A genuine positive control passes:** a dataset containing at least one real, true version chain (e.g., a document with 2–3 actually-sequential saved revisions) must still be correctly detected and correctly ranked (`latest`/`superseded`) — confirming the fix doesn't trade false positives for false negatives.
5. **Duplicate Report language remains honest regardless of which option is chosen** — if any residual false-positive risk remains post-fix (likely, since deterministic heuristics are inherently imperfect), the report's own framing must not overstate certainty beyond what the underlying signal actually supports.

### Risk estimate
**Medium-High risk if Option B is selected; Low-Medium if Option A or C.** Module 04 is frozen at v1.0.0 and its "no provider, fully deterministic, identical behavior in attended/unattended operation" property is an explicit, disclosed architectural decision (`Release/Module04/MODULE_CONTRACT.md` line 47) that later modules and the project's own automation/scheduling story may depend on. Option B (adding a provider) would be a genuine architectural departure from that decision — likely a contract change requiring the full breaking-change approval process (`ENGINEERING_STANDARD.md` §17), not just a patch, and would need explicit reconsideration of whether "identical behavior attended/unattended" remains true (it would not, for version-chain detection specifically, the same disclosed asymmetry Modules 02/03 already carry). Option A is a narrower, lower-risk parameter/logic change within the existing deterministic design. Option C carries the least code risk but does not address the underlying false-positive rate. Whichever option is chosen, the one disclosed side-effect Module 04 is permitted (`MODULE_CONTRACT.md` §"one disclosed exception" — updating a different, earlier-processed record's `version_group_id`/`version_rank`) is exactly the mechanism a false-positive fix would touch, so the existing immutability/side-effect tests are directly load-bearing for this candidate, not incidental.

### Regression tests that must be rerun
- **Module 04 unit suite in full**, with particular attention to: `test_engine_creates_new_version_group_for_first_time_pairing`, `test_engine_version_chain_scoped_categories_only`, `test_engine_version_conflict_when_token_and_date_disagree`, `test_engine_version_rank_by_token_only_when_date_unavailable_on_both`, `test_engine_version_rank_by_date_only_when_token_missing_on_one_side`, `test_engine_retains_only_single_best_scoring_version_candidate`, `test_needs_duplicate_detection_false_after_version_chain_formed_with_conflict`, `test_engine_exact_duplicate_short_circuits_version_chain_check` (`src/pipeline/test_duplicate_detector.py`).
- **A new, permanent regression test** reproducing the Run 003 false-positive pattern specifically (generically-named, visually/content-unrelated files with phash proximity but no true relationship) — Run 002's pattern (same-template, different-content documents) should also get a dedicated fixture if one doesn't already exist, since both are now confirmed, independent trigger shapes.
- **`test_module_contract_immutability_every_non_owned_field_byte_identical`** and **`test_module_contract_side_effect_exhaustively_verified_on_other_record`** — directly load-bearing for this candidate (see Risk estimate above), must pass unchanged.
- **`Tests/Module 04 Integration Test Plan.md` and `Tests/Module 04 UAT Plan.md`** scenarios re-run against the corrected code, scoped per §5.2's allowance, plus at least one new scenario covering the Run 003 false-positive shape specifically.
- **Full project-wide regression suite** (716/716 currently) must remain at 100%.
- **13-check Pipeline Contract Verification gate**, re-run for Module 04 (`Governance/PIPELINE_CONTRACT_VERIFICATION.md`).
- **A fresh Validation run** against a new real-world sample containing both false-positive-shape and true-version-chain content, per acceptance criteria 3–4 — again, Run 002/003's own data cannot certify a fix motivated by that same data.

---

## 4. Findings explicitly excluded from v0.9.1 scope

For completeness and to make the selection in §1 auditable, not just asserted:

| ID | Why excluded |
|---|---|
| PT-001 | Environment Issue — validation-session tooling, not the released pipeline's own code. Did not reproduce in Run 003; not yet a confirmed, ongoing pattern even in its own category. |
| PT-004 | Confirmed Pattern, but a **positive** finding (the safety gate holding correctly) — nothing to fix. Continued monitoring, not engineering work. |
| PT-005 | User Expectation — matches already-documented, designed fallback behavior exactly (`src/main.py`'s own docstring). Not a defect. |
| PT-006 | User Expectation — matches `ARCHITECTURE_DECISIONS.md` decision 27 exactly, already disclosed in `TECHNICAL_DEBT_REGISTER.md` TD-20 prior to this validation phase. Not a defect. |
| PT-007 | Single Observation (1 run), and a **positive** finding — real execution correctness confirmed, nothing to fix. Excluded on both counts. |
| PT-008 | User Expectation (matches `Rules/Naming Rules.md`'s documented fallback rule exactly) and Single Observation (1 run) — excluded on both counts, per this phase's standing single-occurrence rule. Valuable as quantified evidence for a future naming-template discussion, not as a v0.9.1 candidate. |
| PT-009 | Environment Issue — a FUSE-mount-specific failure in the validation sandbox, independently reproduced outside the pipeline entirely. Not the released pipeline's own defect. Also Single Observation. |
| PT-010 | Single Observation (1 run), and a **positive** finding — confirms an existing safety net works, nothing to fix. |
| PT-011 | User Expectation — explicitly disclosed as a deliberate WP-2 scope boundary in `generate_daily_summary()`'s own docstring. Not a defect. Single Observation as well. |

---

## 5. Sequencing and dependency between C1 and C2

C1 (Module 02) and C2 (Module 04) are architecturally independent — different modules, different code paths, no shared function or shared contract surface between the two candidate fixes themselves. They can be designed, reviewed, and implemented in either order or in parallel without blocking each other.

One real, disclosed interaction worth carrying into whichever Design phase(s) follow: C1's fix, if it moves files out of `Screenshot` into a richer category (e.g. `Document`/`Image` via Option B), changes the population of files Module 04 sees with that new category — which could change C2's own false-positive surface in ways neither candidate's acceptance criteria above currently account for alone. If both are implemented in the same release cycle, the Module 01→07 full-chain integration pass required by C1's acceptance criterion 5 should be run **after** both fixes land, not just after each individually, to catch any such interaction — a targeted addition to the regression plan above, not a reason to sequence one before the other.

---

## 6. What this plan does not do

- **Does not modify, draft, or prototype any production code.** No file under `src/` was touched while producing this document.
- **Does not itself authorize implementation.** Per `Governance/FROZEN_MODULE_CHANGE_POLICY.md` §1, a post-freeze change to a Frozen module requires explicit project-owner approval per finding, informed by — but separate from — this plan.
- **Does not select between the candidate options presented in §2.2/§3.2.** That choice belongs to each candidate's own future Design phase, which — per `ENGINEERING_STANDARD.md` — includes its own independent review before any freeze or implementation begins.
- **Does not treat "Confirmed Pattern" as "urgent."** Both candidates are Medium severity; neither blocks the pipeline's existing safety guarantees (A1/A6 in `REAL_WORLD_VALIDATION_PLAN.md` §9 held cleanly through both runs that produced this evidence). Sequencing v0.9.1 against continued validation evidence-gathering (per `VALIDATION_PROGRESS.md` §5) is a project-owner prioritization decision, not one this plan makes on its own.
