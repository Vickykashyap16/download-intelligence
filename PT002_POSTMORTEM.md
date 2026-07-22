# PT-002 Postmortem — Screenshot Misclassification of Real Non-Screenshot Images

**Status:** PT-002 CLOSED / IMPLEMENTED / VALIDATED / MERGED, 2026-07-23.
**Purpose:** A single, self-contained narrative of PT-002 end to end — what was observed, why it happened, what was done, and what it means for how this project runs future engineering changes. Written after closure, from the complete record (`VALIDATION_LEDGER.md`, `PATTERN_TRACKER.md`, the design package, `PT002_VALIDATION_REPORT.md`), not from memory.

---

## 1. Original observation

Validation Run 002 (2026-07-20), the first real-content pipeline execution this project ever performed, classified 9 of 9 real scanned academic-document photos (a degree certificate and 8 mark sheets, `.jpg`) as `Screenshot`. Ground truth, established directly from the project owner's own description of the files and cross-referenced against `Rules/Classification Rules.md`'s own taxonomy, was `Document`. Zero of 9 matched. This was the first finding this project's real-world validation framework ever produced against genuine, non-synthetic content — `VALIDATION_LEDGER.md` VL-002-1.

## 2. Evidence collected

- **Run 002 (2026-07-20):** 9/9 real files, 0/9 correct, root cause confirmed directly against real, independently measured EXIF data (Pillow) — all 9 had zero camera-metadata tags. Classified as a **Single Observation** at this point, per this project's own standing rule that a finding isn't promoted to Confirmed Pattern from one run, no matter how many instances occurred within it.
- **Run 003 (2026-07-20):** a systematic, unbiased 43-file sample of the real Downloads folder — a materially different, non-overlapping dataset with far more content diversity. 18 of 19 real image-family files misclassified `Screenshot`; 6 of those 18 were individually opened and visually confirmed as genuinely non-screenshot content (a WhatsApp-shared personal photo, a product photo, a marketing banner, an AI-generated portrait, and both files in a separate false version-pairing). The one contrast case with genuine camera EXIF present correctly classified `Image` — a built-in positive control sharpening confidence that EXIF-absence, specifically, was the trigger.
- **Promotion:** two independent runs, two non-overlapping datasets, identical precisely-understood mechanism, materially wider real-world surface than first suspected (any photo shared through an EXIF-stripping channel, not just scans) → promoted to **Confirmed Pattern**, `PATTERN_TRACKER.md` PT-002, Confidence **High**.
- **Pre-existing disclosure:** `Release/Module02/KNOWN_LIMITATIONS.md` had already named this exact risk at original release (2026-07-06), including a live UAT contrast case, and explicitly called it "worth revisiting... if this proves too aggressive against real user photos." The project's own test suite also already carried a self-aware mismatch: a test named for detecting a product photo as `Image` that actually asserted `Screenshot`, with a docstring admitting the discrepancy. Both were confirmed, not created, by the real-world evidence — the defect was anticipated in spirit well before it was measured in practice.

## 3. Root cause

`Rules/Classification Rules.md`'s Screenshot-vs-Image split OR'd three conditions for `Screenshot`: filename marker, resolution match, and "no camera EXIF data present." The third condition is a negative signal that is not specific to screenshots — it's equally absent from scanned documents, product photography, marketing graphics, AI-generated images, and personal photos re-encoded by messaging apps. Because the three conditions were OR'd, the third alone was sufficient to force `Screenshot` regardless of what the other two concluded, and in practice it fired for nearly everything before the rule's own stated "Otherwise → Image" default was ever reached. Fully deterministic — the code implemented the rule exactly as written; the gap was in the rule's own definition of "Screenshot," not a coding error.

## 4. Design decision

Alternative A was selected: remove the "no camera EXIF" condition as an independent, sufficient trigger; `Screenshot` now requires filename-marker OR resolution-match only. Two alternatives were considered and rejected — extending the vision deep-pass to image extensions (rejected: would cross Module 03's frozen metadata-schema boundary, an architectural change) and a docs-only fix (rejected: insufficient given Confirmed Pattern severity). The selected design required no architectural change, stayed entirely within Module 02's `MODULE_CONTRACT.md` (the corrected function is an internal helper the contract's own text already discloses as free to change), and was independently verified compatible with all six downstream modules before implementation began. The design explicitly disclosed, rather than hid, a new trade-off: a genuine screenshot with neither a marker filename nor a matching resolution now defaults to `Image` — bounded and named, with a dedicated future regression test committed as part of the same design.

## 5. Implementation summary

`src/pipeline/classification.py`'s `classify_screenshot_or_image()` reduced from three OR'd conditions to two; the unused `has_camera_metadata` import removed (the function itself is untouched and remains correctly available). `Rules/Classification Rules.md` updated to match. One existing test corrected (its own docstring already flagged the mismatch it carried); four new tests added — three covering the real-world content shapes the validation runs actually found, one making the disclosed trade-off directly observable. Full regression suite: 720/720. Scope held exactly to Module 02; confirmed via grep and via full diff that no other module's code or contract was touched.

## 6. Validation summary

The original Run 002 and Run 003 datasets were reconstructed byte-for-byte (content-hash-verified against each run's own recorded evidence — Run 003 required copying 14 already-executed files back to their original pre-filing filenames using that run's own action log) and re-executed against the corrected code in fully isolated state. Result: 27 of 27 real-world PT-002 occurrences now correctly classify `Image`. A full before/after diff of every record in both runs found **zero unintended changes** anywhere else. Safety held identically — zero data loss, zero files newly reaching `auto`/`approval_required` as a side effect, all previously-executed files byte-verified after re-execution. Verdict: **PASS** (`PT002_VALIDATION_REPORT.md`).

## 7. Risks discovered

- **Disclosed, not new:** the trade-off named in the design (a genuine marker-less, resolution-unmatched screenshot now defaults to `Image`) was not exercised by either real-world dataset — it remains covered only by the dedicated unit test, not by real-world evidence either way. This is stated plainly in the Validation Report rather than presented as validated.
- **Scope boundary, correctly held:** Run 002's 9 files are genuinely scanned documents; after this fix they correctly leave `Screenshot` but land on `Image`, not the fully-correct `Document` — a separate, already-disclosed architecture gap (no route from image-family extensions to `Document`) that PT-002 was never designed to close. Naming this precisely, rather than letting "PASS" imply full correctness, was itself a risk-management decision made in the Validation Report.
- **Process risk, not product risk:** the 13-check Pipeline Contract Verification gate — the gate Module 01's own prior post-freeze patch used as part of its closure — was not separately re-run for this change. Real-world re-validation was judged sufficient for this specific, narrow, deterministic-logic change, but this is a process gap worth naming plainly (see `PT002_WORKFLOW_EVALUATION.md`), not quietly absorbed into "the fix is done."

## 8. Lessons learned

1. **Real-world validation found something years of synthetic testing and self-review had already suspected but never confirmed.** The original release's own `KNOWN_LIMITATIONS.md` and test suite both carried the seed of this defect from day one — real content was what turned "worth revisiting" into "confirmed, Medium severity, fix now."
2. **Requiring two independent, non-overlapping datasets before promoting Single Observation to Confirmed Pattern paid off directly.** It prevented over-reacting to Run 002's narrow content shape (scanned documents only) and, once Run 003 showed the same mechanism across much wider content (personal photos, marketing graphics, AI-generated images), produced a real-world-scope understanding the original framing didn't have.
3. **Reconstructing the exact original datasets for re-validation, rather than building fresh synthetic fixtures, is what let this closure claim "zero unintended changes" with actual evidence** instead of a plausible-sounding assertion — the full before/after diff is only meaningful because the inputs were provably identical.
4. **A disclosed trade-off is not the same as a validated one.** Naming the T4 trade-off in the design and then honestly reporting that real-world data never exercised it (rather than letting the PASS verdict imply otherwise) is the kind of precision this project's documentation has consistently rewarded.

## 9. Process improvements

- **Make the 13-check PCV gate a required step before closing any post-freeze correction**, not an optional one applied inconsistently between Module 01's patch (gate re-run) and Module 02's patch (gate not re-run). See `ENGINEERING_CHANGE_PLAYBOOK.md`.
- **Formalize dataset reconstruction-and-diff as the standard re-validation method** for any correction that has prior real-world evidence to compare against — it produced stronger, more falsifiable evidence here than a fresh validation run would have, at lower cost.
- **Standardize the postmortem step itself.** This is the first postmortem this project has produced; prior module corrections (Module 01, Module 05) had thorough `RELEASE_NOTES.md` addenda but no single narrative document pulling observation-through-lessons together in one place for future reference.

## 10. Time taken

Elapsed calendar time from first observation to closure: **2026-07-20 to 2026-07-23, 3 calendar days**, spanning several discontinuous working sessions rather than continuous effort — stated as elapsed time, not engineering-hours, since this project has no time-tracking mechanism and fabricating hour estimates would not be honest evidence.

| Phase | Date |
|---|---|
| First observation (Run 002) | 2026-07-20 |
| Confirmed Pattern (Run 003) | 2026-07-20 |
| Project Review Board acceptance; v0.8.0 validated baseline; Design authorized | 2026-07-20 |
| Design package completed and approved | 2026-07-20 |
| Implementation authorized, implemented, regression-tested (720/720) | 2026-07-23 |
| Post-implementation validation gate executed (PASS) | 2026-07-23 |
| Close-out (this document) | 2026-07-23 |

## 11. Evidence chain

Every claim in this postmortem traces to a specific, still-existing artifact — no step relies on memory or summary alone:

`VALIDATION_LEDGER.md` (VL-002-1, VL-003-1 — raw per-run findings) → `PATTERN_TRACKER.md` PT-002 (cross-run consolidation, Confirmed Pattern classification) → `PROJECT_REVIEW_BOARD_REPORT.md` (independent review, Design authorization) → `Build-out/02 Classification/Module 02 Post-Freeze Design Correction — PT-002.md` (design package) → `src/pipeline/classification.py` + `Rules/Classification Rules.md` (implementation) → `src/pipeline/test_classification.py` (regression tests, 720/720) → `PT002_VALIDATION_REPORT.md` (re-validation against reconstructed original datasets, verdict PASS) → `PATTERN_TRACKER.md`/`VALIDATION_LEDGER.md`/`TECHNICAL_DEBT_REGISTER.md`/`Release/VERSIONS.md`/`Release/Module02/RELEASE_NOTES.md` (closure). Each link in this chain was independently readable and checkable at the time it was produced — none was asserted without the artifact behind it existing first.

## 12. Why the change was successful

- **It was scoped by evidence, not intuition.** The selected design fixed exactly the mechanism two independent real-world runs confirmed, nothing more and nothing speculative.
- **It required no architectural change**, confirmed before implementation began by checking the proposed logic against `MODULE_CONTRACT.md`'s own disclosure and against every downstream module's already-defined behavior — this is why implementation could stay a single-function, two-file change.
- **It disclosed its own limits.** The design named the trade-off it introduced before writing any code; the validation report named what it didn't test rather than letting a PASS verdict overstate itself; this postmortem names the one process step (the PCV gate) that wasn't followed. Nothing here was hidden to make the outcome look cleaner than it was.
- **It was verified against reality twice** — once by unit tests exercising the corrected logic directly, and once by literally re-running the exact original real-world data that found the defect in the first place and confirming, with a full field-by-field diff, that the fix did what it was supposed to do and nothing else.
