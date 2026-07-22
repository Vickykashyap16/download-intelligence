# Module 02 Post-Freeze Design Correction — PT-002 (Screenshot Misclassification)

**Status:** Design phase only. Not reviewed, not frozen, not implemented. No `src/` file has been modified in producing this document.
**Governed by:** `Governance/FROZEN_MODULE_CHANGE_POLICY.md` — Module 02 is Frozen and released at v1.0.0 (`Release/VERSIONS.md`), so this is a post-freeze change, not fresh implementation. This document is the design package that policy's §5 process requires before any implementation may begin.
**Authorized by:** `PROJECT_REVIEW_BOARD_REPORT.md` §7/§8, following its review of `PATTERN_TRACKER.md`/`VALIDATION_LEDGER.md`'s PT-002 finding and `VERSION_091_IMPLEMENTATION_PLAN.md`'s candidate selection. Explicitly scoped to **design only** — implementation requires separate, explicit future approval per the same policy.
**Does not modify:** `src/pipeline/classification.py`, `src/core/images.py`, `src/core/exif.py`, or any other production code. Every code excerpt below is quoted from the real, current, unmodified file for reference, not proposed as a diff to apply now.

---

## 1. Problem Statement

`Rules/Classification Rules.md`'s "Screenshot vs. plain Image split" classifies an image-family file (`.png`/`.jpg`/`.jpeg`/`.heic`/`.webp`) as **Screenshot** if *any* of three conditions hold:
1. Filename contains a screenshot marker (`Screenshot`, `Screen Shot`, `CleanShot`, `Snip`).
2. Image dimensions match a common device/screen resolution.
3. No camera EXIF data is present (no lens/camera model tag).

Otherwise, the rule's own text says, the file is **Image** ("product photo, general picture, etc.").

Condition 3 is a negative signal — absence of camera EXIF — and in practice it fires for far more than screenshots. Camera EXIF is also absent from product photography exported by design/editing tools, marketing graphics, AI-generated images, and ordinary personal photos re-encoded or stripped of metadata by messaging apps (WhatsApp, and similar). Because the three conditions are OR'd, condition 3 alone is sufficient to force `Screenshot`, regardless of what conditions 1 and 2 conclude — and conditions 1/2 essentially never fire for this kind of file, since none of it looks like a filename-marked or resolution-matched screen capture. In practice, condition 3 swallows almost everything before the rule's own stated "Otherwise → Image" default is ever reached.

**Real-world evidence (`PATTERN_TRACKER.md` PT-002, Confirmed Pattern, 2 independent runs):**
- Run 002 (`VALIDATION_LEDGER.md` VL-002-1): 9/9 real scanned academic-document photos misclassified `Screenshot`. Filenames matched no screenshot marker; dimensions matched no common resolution; all 9 independently measured (Pillow) to have zero camera-EXIF tags.
- Run 003 (`VALIDATION_LEDGER.md` VL-003-1): 6/6 directly visually-confirmed misclassifications across a materially more diverse real content set — a personal photo shared over WhatsApp (EXIF stripped by the sharing app, not a scan), a product photograph (`chair.png`), a marketing banner graphic, an AI-generated portrait, and both files in a separate false version-pairing (PT-003). A further 12 files were classified `Screenshot` under the same mechanism but not individually opened (disclosed as inferred, not confirmed, in `VALIDATION_LEDGER.md`). The one contrast case in Run 003 with genuine camera EXIF present (`IMG_20211002_001030_Bokeh.jpg`) correctly classified `Image` — isolating condition 3, specifically, as the trigger.

**This was already a disclosed, anticipated risk, not a surprise.** `Release/Module02/KNOWN_LIMITATIONS.md` (written at original release, before any real-world validation) states: *"Confirmed against both a synthetic test sample and a live UAT file (`IMG_4821.jpg`, camera-style filename, no EXIF) — both landed on Screenshot. Not a code defect; the heuristic is implemented exactly as designed. Worth revisiting the OR-condition weighting if this proves too aggressive against real user photos."* Real-world validation is exactly the "if this proves too aggressive" test that document called for — and, per the evidence above, it has.

**Even the project's own committed test suite already flags this.** `src/pipeline/test_classification.py`'s `test_classify_screenshot_or_image_detects_real_product_photo_as_image` asserts `== Category.SCREENSHOT` for a synthetic product-photo fixture, and its own docstring says so explicitly: *"even though a human would call it a product photo. This is a known heuristic limitation with synthetic test data, not a code defect."* The test's own name and its own assertion already disagree with each other — a small, precise, pre-existing signal that this behavior was recognized as wrong in spirit well before real-world evidence confirmed it in practice.

**Severity:** Medium, per `PATTERN_TRACKER.md`/`VERSION_091_IMPLEMENTATION_PLAN.md` — never resulted in an incorrect automated filing in either run (caught by the confidence system every time), but real, reproducible, and with genuine downstream cost: lost distinguishing detail in generated names, naming-collision suffixes (14 of 36 files in Run 003 collided on the generic `Screenshot_Unknown_Context_Unknown_Date` template), and a Duplicate Report false pairing (PT-003) whose two files were only compared at all because both had been routed into `Screenshot`.

---

## 2. Root Cause Analysis

Directly confirmed against real, unmodified code (`src/pipeline/classification.py`) and real, independently measured data (Pillow EXIF reads) across both validation runs — not inferred from the symptom alone.

```python
def classify_screenshot_or_image(path: str) -> Category:
    if _looks_like_screenshot_filename(Path(path).name):
        return Category.SCREENSHOT
    if matches_screen_resolution(get_dimensions(path)):
        return Category.SCREENSHOT
    if not has_camera_metadata(path):
        return Category.SCREENSHOT
    return Category.IMAGE
```

- `has_camera_metadata()` (`src/core/exif.py`) checks for exactly four tags: `{"Make", "Model", "LensModel", "FocalLength"}`. Its own docstring already frames this correctly as *"one of the Screenshot vs. Image signals"* — the design problem is not in this function (it does exactly what it says), but in how `classify_screenshot_or_image()` weights its absence.
- For every real misclassified file in both runs, the first two conditions were independently confirmed false (no marker filename, no resolution match), and `has_camera_metadata()` was independently confirmed false (Pillow re-measurement, 28 real files across both runs). The third `if` is what returned `Category.SCREENSHOT` in every case.
- The function is **fully deterministic** and never involves `ClassificationProvider` — confirmed by `needs_screenshot_split()`/`classify_by_extension()`'s routing in `ClassificationEngine.classify_file()`: image-family files return from the `needs_screenshot_split(path)` branch before `is_text_bearing(path)` is ever checked, so no live-judgment provider is consulted for any `.jpg`/`.png`/etc. file, regardless of provider availability. This means the defect is not provider-quality-dependent and reproduces identically in every deployment mode (interactive or unattended).
- **This is a rule-completeness gap, not an implementation defect.** The code faithfully executes `Rules/Classification Rules.md`'s three-condition OR exactly as written. The gap is that the rule's own third condition is weighted as independently sufficient when it is, in reality, only weak negative evidence — true of a screenshot, but also true of a large and (per Run 003) diverse class of real, non-screenshot content.

---

## 3. Design Alternatives

Three alternatives were considered, corresponding to the three options `VERSION_091_IMPLEMENTATION_PLAN.md` §2 already named without selecting between them. Restated and evaluated here with the specific goal of finding the smallest change that resolves the confirmed evidence without requiring an architectural change.

### Alternative A — Remove condition 3 as an independent trigger; default to `Image` per the rule's own already-stated intent
Screenshot requires condition 1 (filename marker) **or** condition 2 (resolution match). If neither holds, classify `Image` — exactly matching `Rules/Classification Rules.md`'s own header text ("Otherwise → Image (product photo, general picture, etc.)"), which the current three-condition implementation currently fails to reach in most real-world cases.
- **Preserves architecture:** yes — a pure logic change inside one existing deterministic function; no new category, no provider involvement, no schema change.
- **Resolves the confirmed evidence:** yes, directly — every real misclassified file in both runs failed conditions 1 and 2, so removing 3 as an independent trigger routes all of them to `Image`, matching their real ground truth in every directly-confirmed case.
- **New risk introduced, disclosed rather than hidden:** a genuine screenshot with neither a marker filename nor a resolution matching `_COMMON_SCREEN_RESOLUTIONS` (e.g., cropped, resized, or renamed before reaching Downloads) would now default to `Image` instead of `Screenshot` — a new potential false negative on the Screenshot side that does not currently occur, since condition 3 currently catches it. This trade-off is real and is evaluated explicitly in §5 (Risk Assessment) and bounded by a new acceptance criterion (§9) and regression test (§8), not waved away.

### Alternative B — Extend Module 02's vision deep-pass to image-family extensions
Give image-family files a path to the provider-based deep pass that text-bearing extensions already have, so a live-judgment provider can distinguish "a photographed contract" from "a product photo" from "a real screen capture" using actual content understanding.
- **Preserves architecture:** **no.** This crosses out of Module 02's own frozen boundary in at least two ways: (1) Screenshot/Image currently have no metadata-extraction schema for real document content (`src/pipeline/metadata.py`'s `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` only define `context_description`/`capture_date` for Screenshot and `description`/`variant`/`capture_date` for Image — neither has a path to real document fields) — already flagged as a structural observation during Run 002 (`VALIDATION_LEDGER.md` VL-002-2: *"Screenshot's extraction schema has no path to real document content even with a provider"*), meaning this option cannot be scoped to Module 02 alone without also reopening Module 03's frozen contract; (2) it materially changes Module 02's provider-call volume/cost profile for an entire new class of file, a behavior change big enough to warrant its own dedicated design review, not a narrow post-freeze correction.
- **Disposition:** rejected for this design package specifically, on architectural-preservation grounds — not rejected as a bad idea in general. Recorded as a legitimate future direction if Alternative A's real-world results (once implemented and measured) prove insufficient. Not eliminated from `TECHNICAL_DEBT_REGISTER.md` TD-01/TD-16's longer-term discussion.

### Alternative C — No code change; documentation/reporting-language correction only
Leave the classification logic untouched; only clarify `Rules/Classification Rules.md`'s prose and/or soften the Duplicate/Daily Summary reports' framing.
- **Preserves architecture:** trivially yes (no change at all).
- **Resolves the confirmed evidence:** no — the real misclassification rate, the naming-collision cost, and the false version-pairing this feeds into (PT-003) would all remain exactly as measured. Given PT-002 is now Confirmed Pattern with directly-isolated root cause (not a single occurrence or an ambiguous signal), a documentation-only response does not match the evidentiary weight of the finding.
- **Disposition:** rejected — insufficient given current evidence, though it remains available as a fallback if Alternative A's own regression testing (§8) surfaces an unacceptable new false-negative rate on genuine screenshots.

---

## 4. Selected Design

**Alternative A.** `classify_screenshot_or_image()`'s decision logic changes from:

> Screenshot if (filename marker) **or** (resolution match) **or** (no camera EXIF); otherwise Image.

to:

> Screenshot if (filename marker) **or** (resolution match); otherwise Image.

Camera-EXIF presence/absence is no longer, by itself, sufficient to route a file to either category. This is the smallest change that resolves every directly-confirmed misclassification in both validation runs, requires no new category, no provider involvement, no cross-module schema change, and brings the implementation into alignment with `Rules/Classification Rules.md`'s own already-written "Otherwise → Image" default — which the current three-condition implementation was, in effect, failing to honor.

**What does not change:** `_looks_like_screenshot_filename()`, `matches_screen_resolution()`, `_COMMON_SCREEN_RESOLUTIONS`, `has_camera_metadata()`, `read_exif()` — none of these functions themselves change. `has_camera_metadata()` remains available and correctly implemented; it is simply no longer consulted as an independent, sufficient trigger inside `classify_screenshot_or_image()`. (Whether it should be repurposed as a corroborating/tie-break signal in a future iteration is a legitimate open question, deliberately not decided here — see §7's Compatibility Analysis note on this function's continued existence.)

**Rules document change required, not a contract change:** `Rules/Classification Rules.md`'s "Screenshot vs. plain Image split" section needs its third bullet ("No camera EXIF data present…") removed from the OR list. This is a business-rule edit, governed the same way every other `Rules/*.md` change has been in this project's history (e.g. Module 05's whitespace-to-underscore correction, Module 04's phash category-scoping correction) — not a `MODULE_CONTRACT.md` change, since `Rules/Classification Rules.md` is explicitly *"the thing to edit when classification behavior needs to change"* (its own header text) and sits outside the module contract's INPUT/OUTPUT/guarantee surface.

---

## 5. Risk Assessment

| Risk | Likelihood | Impact | Notes |
|---|---|---|---|
| New false negative: a genuine screenshot with no marker filename and non-standard/cropped dimensions now defaults to `Image` | Unmeasured — no current evidence either way; this is a real, disclosed trade-off, not a hidden one | Medium if it occurs — a real screenshot filed as `Image` uses the wrong naming template and destination folder (`Images/` instead of `Images/Screenshots/`), though it remains fully reversible (undo) and never bypasses the confidence/review safety net any more than the current defect does | Directly bounded by acceptance criterion 4 (§9) and regression test T4 (§8) before implementation may proceed |
| Regression on the one existing test whose assertion currently encodes the defect (`test_classify_screenshot_or_image_detects_real_product_photo_as_image`) | Certain — this test's assertion must change | Low — the change is expected, disclosed, and precisely scoped to one test (§6/§8) | Not a risk to ship-quality; a necessary, anticipated consequence of the fix working |
| Downstream naming/folder-mapping surprise for reclassified files | Low | Low | Both `Screenshot` and `Image` already have fully defined `Rules/Naming Rules.md` templates and `Rules/Folder Rules.md` destinations (`Images/Screenshots/` vs. `Images/`) — reclassifying a file only changes which already-existing, already-tested template/destination applies, introducing no new naming or folder logic |
| Confidence-scoring surprise for reclassified files | None identified | — | `Rules/Confidence Rules.md` contains no Screenshot- or Image-specific deduction — confirmed by direct search of the rules document, which returned no category-specific scoring branches for either category. Category-independent signals (`ambiguous`, hard floors, etc.) are unaffected by which of these two categories a file lands in |
| Cross-module contract breakage | None identified | — | See §6 (Compatibility Analysis) |
| Provider-call volume/cost change | None | — | Alternative A never touches the provider boundary — image-family files still never reach `ClassificationProvider` under either the old or new logic |

**No Critical or High risk identified.** The one real, disclosed risk (new false-negative surface on non-standard screenshots) is a quality trade-off, not a safety risk — a misfiled screenshot is fully reversible and still subject to the same confidence/review gate every other classification result passes through.

---

## 6. Compatibility Analysis

**`Release/Module02/MODULE_CONTRACT.md` — no change required.**
- INPUT: unaffected — `classify_batch()`'s accepted input shape (`List[FileRecord]`, `status == "discovered"`) does not change.
- OUTPUT/Guarantees: unaffected in shape — `category` remains a `Category` enum member (still either `SCREENSHOT` or `IMAGE`, just possibly a different one of the two for the same file than before), `classification_signals` remains fully populated. The contract makes no guarantee about *which* category a given file receives, only that a real, valid one is always produced — so this change is fully within the existing guarantee text, not a revision of it.
- DOES NOT MODIFY: unaffected — this change touches no field Module 02 is barred from touching.
- The contract's own explicit disclosure already anticipates changes at exactly this layer: *"`ClassificationEngine` and `ClassificationProvider` are implementation details free to change... without constituting a breaking change to this contract, as long as `classify_batch()`'s INPUT/OUTPUT/guarantees hold."* `classify_screenshot_or_image()` sits inside that same free-to-change internal layer — it is a pure deterministic helper the Engine calls, not part of the contract surface itself.

**Downstream modules — no contract or schema change required for any of them:**
- **Module 03 (Metadata Extraction):** both `Screenshot` and `Image` already have defined `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` entries (`src/pipeline/metadata.py`). A file moving from one to the other simply extracts against the other category's already-existing schema — no new field, no schema edit.
- **Module 04 (Duplicate & Version Detection):** both categories are already members of `_NEAR_DUPLICATE_CATEGORIES` and `_VERSION_CHAIN_CATEGORIES` (`src/pipeline/duplicate_detector.py`) — no change to which categories Module 04 scopes its checks to.
- **Module 05 (Naming & Destination):** both categories already have defined naming templates (`Rules/Naming Rules.md`) and folder destinations (`Rules/Folder Rules.md`: `Images/` for Image, `Images/Screenshots/` for Screenshot) — confirmed by direct inspection of both rules documents. No new template or destination needs to be authored.
- **Module 06 (Confidence & Review):** confirmed via direct search of `Rules/Confidence Rules.md` that no Screenshot- or Image-specific deduction exists — scoring is unaffected by which of the two a file lands in.
- **Module 07 (Preview, Approval & Execution) / Module 08 (Logging & Reporting):** both operate on whatever category/destination earlier modules already resolved; neither has category-specific logic for Screenshot/Image.

**Version-bump classification (`Release/VERSIONS.md`'s own convention):** **PATCH.** The change stays entirely within Module 02's existing, frozen `MODULE_CONTRACT.md` — no new optional behavior is added (ruling out MINOR) and no guarantee text changes (ruling out MAJOR). Consistent with `FROZEN_MODULE_CHANGE_POLICY.md` §5.1's PATCH criterion ("the fix stays entirely within the module's existing, frozen `MODULE_CONTRACT.md`").

**No architectural change is required by this design.** Per this phase's explicit instruction to stop and report rather than proceed if one were needed: none was found. The three-layer architecture (`classify_batch()` → `ClassificationEngine` → `ClassificationProvider`), the safety model (confidence hard floors, human-approval gate, reversible execution), and every cross-module contract remain exactly as they are today.

---

## 7. Regression Impact Analysis

**Direct impact — `src/pipeline/test_classification.py`'s existing Screenshot-split tests, evaluated individually against the proposed logic change:**

| Existing test | Current behavior | Under proposed logic | Impact |
|---|---|---|---|
| `test_classify_screenshot_or_image_detects_real_screenshot_by_resolution_and_name` | Filename/resolution both match a real screenshot fixture → `SCREENSHOT` | Condition 1 or 2 still fires → `SCREENSHOT`, unchanged | **None** — passes unmodified |
| `test_classify_screenshot_or_image_detects_real_product_photo_as_image` | No marker, no resolution match, no EXIF (synthetic fixture) → asserts `SCREENSHOT`, **with the test's own docstring already saying this is wrong** | Conditions 1 and 2 both false → falls to new default → `IMAGE` | **Must change** — assertion updates from `Category.SCREENSHOT` to `Category.IMAGE`; docstring's now-resolved caveat removed. This is the one test whose current assertion directly encodes the defect this design corrects. |
| `test_classify_screenshot_or_image_filename_marker_wins_immediately` | Marker filename ("My Screenshot 2026.png"), no EXIF → `SCREENSHOT` | Condition 1 still fires → `SCREENSHOT`, unchanged | **None** — passes unmodified |
| `test_classify_screenshot_or_image_true_photo_with_camera_exif_and_odd_dimensions` | No marker, uncommon resolution, real EXIF present → `IMAGE` (already, via the old condition-3 negative check evaluating false) | Conditions 1 and 2 both false → falls to new default → `IMAGE`, same outcome via a different path | **None** — passes unmodified, same assertion |
| `test_engine_deterministic_screenshot` | Marker filename ("My Screenshot.png") → `SCREENSHOT` via the Engine | Condition 1 still fires → `SCREENSHOT`, unchanged | **None** — passes unmodified |

**Net direct impact: exactly one existing test requires a change**, and that change is a correction of an assertion the test's own author already flagged as not matching real-world intent — not a new gap being introduced.

**Indirect impact — modules that consume `category` downstream, evaluated for whether any of their own committed tests assume a fixed Screenshot/Image split behavior:**
- `src/pipeline/test_metadata.py`, `test_naming.py`, `test_confidence.py`, `test_duplicate_detector.py`, `test_execution.py`, `test_reporting.py`: none of these construct their own fixtures via `classify_screenshot_or_image()` — every reviewed test in these files that needs a Screenshot- or Image-category `FileRecord` constructs one directly with `category=Category.SCREENSHOT`/`Category.IMAGE` already set, rather than deriving it from real image content through the classification path. This design change cannot regress any of them, since none of them exercise the function being changed.
- Confirmed by the full regression suite currently passing at **716/716** (re-run this session, 2026-07-20, prior to any change) — the baseline this design's own future implementation must not regress below, less the one intentionally-updated assertion above (716/716 remains the target after the fix, not 715 or 717).

**No integration-test or UAT-level committed assertion was found that depends on the specific old three-condition behavior** — `Tests/Module 02 Integration Test Plan.md` and `Tests/Module 02 UAT Plan.md` were reviewed for Screenshot/Image-specific scenarios; none assert a specific outcome for an EXIF-less, non-marker, non-resolution-matched image (the exact case this design changes), meaning no already-certified integration/UAT scenario needs re-litigating — though see §8 for what new coverage is required going forward.

---

## 8. Test Plan (for a future Implementation phase — no test code written here)

A future implementation must, at minimum:

1. **T1 — Update the one directly-affected unit test.** `test_classify_screenshot_or_image_detects_real_product_photo_as_image`'s assertion changes to `Category.IMAGE`; its docstring's caveat is removed and replaced with a note that this is now the corrected, intended behavior (mirroring how Module 04/05's own post-freeze corrections updated their test docstrings, per project precedent).
2. **T2 — Add a new regression test class for the specific defect**, per `FROZEN_MODULE_CHANGE_POLICY.md` §5.3's requirement that a post-freeze fix add "a new, permanent regression test... so the same class of gap cannot recur silently." At minimum: a synthetic fixture representing each real-world content shape directly confirmed in validation (a non-screenshot scan-shaped image, a product-photo-shaped image, a personal-photo-shaped image with EXIF stripped) — each asserting `Category.IMAGE` under the new logic.
3. **T3 — Re-run every existing Screenshot-split test** (§7's table) and confirm all pass unmodified except T1.
4. **T4 — A dedicated adversarial test for the disclosed new risk (§5):** construct a synthetic "screenshot-shaped" fixture with a generic filename and non-standard/cropped dimensions (no marker, no resolution match, no EXIF — i.e., exactly the shape of file this design newly routes to `Image`) and evaluate whether this represents an acceptable trade-off in practice. This test does not have a predetermined "correct" assertion baked in by this design package — its purpose is to make the disclosed trade-off visible and measurable, not to assume the trade-off is fine.
5. **T5 — Full regression suite**, target: 716/716 (the confirmed current baseline) with T1's single intentional change, plus T2's new tests, all passing.
6. **T6 — `test_module_contract_immutability_*`-style tests** (Module 02's own non-owned-field guarantees) re-run to confirm no field outside `category`/`classification_signals` is touched by the change.
7. **T7 — 13-check Pipeline Contract Verification gate** (`Governance/PIPELINE_CONTRACT_VERIFICATION.md`), re-run for Module 02, per `FROZEN_MODULE_CHANGE_POLICY.md` §5.5.
8. **T8 — A fresh real-world validation run** (this project's own Real-World Validation Framework) against a new, unseen sample — not Run 002's or Run 003's own data, since that data motivated this fix and cannot also certify it — to measure real-world accuracy improvement per acceptance criterion 3 below.

---

## 9. Acceptance Criteria

Restated and finalized from `VERSION_091_IMPLEMENTATION_PLAN.md` §2's candidate criteria, now specific to the Selected Design (Alternative A):

1. **Zero regression on existing Screenshot-positive controls.** Every existing test that currently asserts `Category.SCREENSHOT` for a marker-filename or resolution-matched fixture continues to pass unmodified (§7's table, rows 1/3/5) — 100%.
2. **The one currently-defect-encoding test is corrected, not merely deleted.** `test_classify_screenshot_or_image_detects_real_product_photo_as_image` asserts `Category.IMAGE` after the fix, with its docstring reflecting the corrected behavior.
3. **Held-out real-world accuracy, measured on a fresh, unseen dataset** (T8): on a new sample of ≥30 real, non-screenshot, EXIF-less images spanning at least 3 of the content shapes directly confirmed in Run 002/003 (scanned-document photo, messaging-app-shared personal photo, product/marketing graphic), correct (non-`Screenshot`) classification rate ≥85%, with any misses individually root-caused, not just tallied.
4. **The disclosed new-risk trade-off (§5) is measured, not assumed.** T4's adversarial test result is reported explicitly as part of implementation sign-off — if it reveals a materially high real-world rate of genuine screenshots losing correct classification, that finding must be brought back to a fresh Design review before release, not silently accepted.
5. **Full regression suite at 716/716**, plus T2's new permanent regression tests, all passing.
6. **Zero Critical/High/Medium findings** from a dedicated, targeted Independent Implementation Audit of this specific change, per `FROZEN_MODULE_CHANGE_POLICY.md` §5.2's "confirm the fix resolves the specific finding, confirm it doesn't introduce a new contract violation" requirement.
7. **All 13 Pipeline Contract Verification checks pass** for Module 02 (T7).
8. **Downstream correctness confirmed, not just Module 02 in isolation** — for at least one reclassified file (Screenshot → Image), the full Module 01→07 chain is exercised and its Module 03 extraction, Module 05 naming, and Module 06 confidence-tier outcome are each independently verified consistent with the new category's schema, per `VERSION_091_IMPLEMENTATION_PLAN.md` §2's original acceptance criterion 5.

---

## 10. Rollback Strategy

**Pre-implementation (current state):** no rollback needed — no code has changed.

**If implemented and a regression is found before release:** per `FROZEN_MODULE_CHANGE_POLICY.md`'s own discipline, a post-freeze change is never released without passing every acceptance criterion above first — a failed criterion blocks release rather than triggering a rollback of already-shipped behavior. This is the primary rollback mechanism: catch it before it ships.

**If implemented, released, and a regression is found afterward** (e.g., T4's disclosed trade-off proves worse in practice than anticipated, discovered via a future validation run): because this is a PATCH-level, single-function, single-condition-removal change with a fully reversible git/version history (the prior three-condition logic is exactly what exists today, fully specified in §2 above), rollback is a direct, symmetric revert: restore the third OR condition (`if not has_camera_metadata(path): return Category.SCREENSHOT`) to `classify_screenshot_or_image()`, restore `Rules/Classification Rules.md`'s third bullet, and restore T1's original assertion. No data migration is required for a rollback — `FileRecord.category` values already assigned under the corrected logic are not automatically retroactively changed by a code rollback (consistent with this project's standing "never silently rewrite already-processed records" discipline, e.g. Module 01's own re-scan-preservation correction) — any such retroactive correction would be its own separate, explicitly-approved decision, not an automatic side effect of rolling back the code.

**Monitoring signal for whether a rollback is ever warranted:** future validation runs' `PATTERN_TRACKER.md` entries — specifically, a new Confirmed Pattern of genuine screenshots being misfiled as `Image` (the disclosed §5 risk materializing at a real, meaningful rate) would be the trigger for revisiting this decision, exactly as PT-002 itself was originally surfaced.

---

## Summary

This design requires **no architectural change**. It is a single-function, single-condition-removal correction confined entirely to `classify_screenshot_or_image()` plus a matching text edit to `Rules/Classification Rules.md`, stays within Module 02's existing, frozen `MODULE_CONTRACT.md` (PATCH-level), requires no change to any downstream module's schema, template, or scoring logic, and directly resolves every real, directly-confirmed misclassification in both validation runs. One disclosed, honestly-bounded new risk (a possible new false-negative surface on non-standard screenshots) is carried forward as an explicit acceptance criterion and regression test rather than hidden. No implementation has been performed. This document is ready for Review under `Governance/ENGINEERING_STANDARD.md`'s standard lifecycle, pending separate, explicit project-owner authorization to proceed past Design.
