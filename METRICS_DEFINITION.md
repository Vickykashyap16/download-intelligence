# Metrics Definition — Real-World Validation

**Date:** 2026-07-20 · **Status:** Framework design — no metric has been measured yet
**Companion to:** `REAL_WORLD_VALIDATION_PLAN.md` (§3 names the five questions these metrics answer; §5 defines the ground truth these metrics are computed against), `BENCHMARK_SPECIFICATION.md` (how these numbers get compared across datasets and releases)

Every metric below follows `Rules/Confidence Rules.md`'s own stated philosophy, applied to validation instead of scoring: **a number without a formula and a source isn't a metric, it's an impression.** Each metric states exactly what it counts, exactly what it divides by, and exactly which field in the real data model (`Build-out/08 Logging & Reporting/Metadata & Log Schema.md`) it's computed from.

---

## 1. Reading this document

- **Numerator/denominator metrics** are reported as a percentage, always alongside the raw counts (e.g. "42/45, 93.3%") — a bare percentage without the underlying N is not an acceptable way to report any metric in this framework, since 3/3 and 300/315 are both "100%... ish" but mean very different things about how much evidence backs the claim.
- **Every metric is reported per pipeline stage first, then rolled up** — an aggregate "the pipeline is 91% accurate" number is not useful on its own; the framework needs to know *where* the 9% is.
- **Every metric is computed only from the ground truth established per `REAL_WORLD_VALIDATION_PLAN.md` §5** — never from the pipeline's own self-reported confidence score, which is exactly the thing being evaluated.
- **Metrics involving categories are always broken out per category** (Invoice, Resume, Bank Statement, Contract, Document, Image, Screenshot, Application, Archive, Video, Audio, Unknown) wherever the sample size per category makes that meaningful — a pipeline that's excellent at Invoices and poor at Contracts should never be hidden inside one blended average.

---

## 2. Correctness metrics

### 2.1 Classification Accuracy

```
Classification Accuracy = (files where operator-confirmed category == pipeline-assigned category) / (total files with an established ground-truth category)
```

Source: `category` field vs. the operator's approve/edit signal (`REAL_WORLD_VALIDATION_PLAN.md` §5.1). An approved-as-is file counts as a match; an edit tagged `wrong_category` counts as a miss. Reported overall and per category. Files still `Unknown` after processing are tracked separately (§2.5) rather than folded into this metric, since `Unknown` is a disclosed fallback state, not a wrong classification per se.

### 2.2 Metadata Extraction Accuracy

```
Field Accuracy (per category) = (spot-checked fields matching the real document) / (total spot-checked fields for that category)
Field Completeness (per category) = (required fields populated, non-null) / (total required fields for that category)
```

Source: `extracted_metadata` vs. the operator's spot-check (`REAL_WORLD_VALIDATION_PLAN.md` §5.2) for Accuracy; `extracted_metadata` directly (no spot-check needed to detect a null) for Completeness. Required-field lists per category per `Build-out/03 Metadata Extraction/Module 03 Design.md` §7. Reported separately — a field that's present but wrong is a different problem than a field that's silently missing, and conflating them (as a single "quality" score would) hides which one is actually occurring.

### 2.3 Naming & Destination Acceptance Rate

```
Naming Acceptance Rate = (files where suggested_name approved without edit) / (total files reaching the naming stage)
Destination Acceptance Rate = (files where suggested_destination approved without edit) / (total files reaching the naming stage)
```

Source: `suggested_name` / `suggested_destination` vs. the operator's edit signal, tagged `wrong_filename` / `wrong_destination` respectively (`REAL_WORLD_VALIDATION_PLAN.md` §5.3). Reported separately from each other (a good filename with a bad destination suggestion is a real, distinct signal) and separately per category, since naming templates are category-specific (`Rules/Naming Rules.md`).

### 2.4 Duplicate & Version Detection Precision and Recall

```
Precision = (flagged relationships confirmed true by operator) / (total relationships flagged by the pipeline)
Recall    = (flagged relationships confirmed true by operator) / (total relationships the operator confirms actually existed in the batch)
```

Source: `duplicate_of` / `version_group_id` assignments vs. the operator's per-relationship yes/no confirmation (`REAL_WORLD_VALIDATION_PLAN.md` §5.2). Recall requires the operator to know about a real duplicate/version relationship the pipeline *missed* — realistically this is only fully knowable for relationships the operator happens to notice, so Recall is reported as a lower bound, explicitly labeled as such, not a precise measurement. Precision has no such limitation (every flagged relationship is checkable) and should be weighted more heavily in any overall read of this metric pair.

### 2.5 Unknown-Category Rate

```
Unknown Rate = (files classified as Unknown) / (total files processed)
```

Source: `category` field directly. Not a correctness metric by itself (a genuinely unclassifiable file *should* land here), but tracked because a high or rising Unknown Rate on real data is the most direct, measurable signal of `TECHNICAL_DEBT_REGISTER.md` TD-01 (no autonomous judgment provider) actually mattering in practice, versus remaining a theoretical concern.

## 3. Safety and calibration metrics

### 3.1 Auto-Tier Correctness

```
Auto-Tier Correctness = (spot-checked auto-tier files confirmed fully correct) / (total spot-checked auto-tier files)
```

Source: `tier == "auto"` files vs. the mandatory post-hoc spot-check (`REAL_WORLD_VALIDATION_PLAN.md` §5.2, sampled at 100% until auto-tier has a track record). This is the single most important metric in this document — `auto` means "no human ever looks at this before it moves," so a miss here is not "one bad classification," it's the pipeline having silently filed a real file incorrectly with nobody watching. See `REAL_WORLD_VALIDATION_PLAN.md` §9 (A3) for the acceptance threshold this feeds.

### 3.2 Tier Miscalibration Rate

```
Miscalibration Rate (per tier) = (files in that tier tagged tier_felt_wrong_for_this_file OR requiring correction inconsistent with that tier's expected reliability) / (total files in that tier)
```

Source: `tier` and `confidence_breakdown` vs. the operator's `tier_felt_wrong_for_this_file` tag and the correctness metrics above, cross-referenced. Reported per tier: an `approval_required` file that needed heavy correction is expected occasionally (that's what the tier is for); a `review_required` file that turned out perfectly correct every time might mean the scoring is more conservative than necessary — both directions are worth knowing, not just the unsafe one.

### 3.3 Confidence Score Distribution

Not a pass/fail metric — a histogram of `confidence_score` values and `confidence_breakdown` deduction frequency across all processed files, per category. This is the direct evidence base for `Rules/Confidence Rules.md`'s own "Tuning note," which explicitly anticipates adjusting deduction weights "after the first few real batches once you can see which deductions actually cause the most approval-tier routing" — this metric is what makes that tuning evidence-based instead of guesswork, the first time real data has existed to compute it from.

## 4. Reliability and performance metrics

### 4.1 Reliability Fault Rate

```
Batch-Halting Fault Rate = (batches that did not complete) / (total batches attempted)
Contained Fault Rate     = (files causing a per-file error/fallback that did not halt the batch) / (total files processed)
```

Source: CLI/terminal output and `error` action-log entries. Distinguished per §7's error taxonomy in `REAL_WORLD_VALIDATION_PLAN.md` — a batch-halting fault is far more severe than a contained one, and the two must never be blended into one "error rate."

### 4.2 Throughput

```
Files per Second (per stage) = files processed by that stage / wall-clock seconds for that stage
```

Source: direct timing during a real run, compared against each module's own measured baseline in its `TEST_RESULTS.md` (e.g. Module 07's 40.116s/75 files, Module 08's 0.5436s/2,000 records for reporting). Reported per stage, not just end-to-end, so a slowdown can be attributed to a specific module rather than "the pipeline got slower" — and explicitly checked against `TECHNICAL_DEBT_REGISTER.md` TD-03/TD-04/TD-06's accepted-at-test-scale assumptions, since real accumulated volume is exactly the condition those items flagged as eventually mattering.

### 4.3 Reversibility Verification Rate

```
Reversibility Rate = (attempted undos that fully restored the file) / (total undos attempted)
```

Source: direct comparison of file state before the original move and after the undo. This must equal 100% in every run — see `REAL_WORLD_VALIDATION_PLAN.md` §6/§9 (A2). There is no acceptable partial value for this metric; it exists to be checked, not tuned.

## 5. Usability metrics (informational, not pass/fail)

These feed `PRODUCT_ROADMAP.md`'s User Experience track, not the acceptance criteria in `REAL_WORLD_VALIDATION_PLAN.md` §9 — a poor result here is a product-design signal, not a pipeline defect.

### 5.1 Review Burden

```
Edit Rate = (files requiring any edit before approval) / (total files shown for review)
Review Time per Batch = wall-clock time from preview shown to all decisions recorded
```

Source: operator approve/edit/reject signal; operator-reported timing (`VALIDATION_CHECKLIST.md` instructs the operator to note start/end time per batch review). A consistently high Edit Rate combined with long Review Time is the concrete evidence behind `PRODUCT_ROADMAP.md` §4's claim that no real review surface exists yet beyond raw chat — this metric is what would turn that claim from an assertion into a measurement.

### 5.2 Operator-Reported Friction

Not a formula — a running log of Informational findings tagged `usability_friction` (§7 of `REAL_WORLD_VALIDATION_PLAN.md`), collected verbatim (redacted per `DATASET_GUIDELINES.md`) rather than forced into a number, because the whole point of this metric is to capture the specific moments a quantitative metric would miss.

## 6. How metrics roll up into acceptance

`REAL_WORLD_VALIDATION_PLAN.md` §9 references several of these metrics directly (A3 = §3.1, A5 = §2.1/§2.3, A6 = §4.1). Every other metric in this document is diagnostic, not gating — it exists to explain *why* an acceptance criterion passed or failed, and to give the project owner a fuller picture than pass/fail alone. A validation report that only states the acceptance-criteria verdict without the full metric breakdown behind it does not meet this framework's evidentiary bar.

## 7. What is deliberately not measured here

This document does not define classification-model quality in the abstract (precision/recall against a labeled ML-style test set) — that framing doesn't fit a system whose "model" is a live human-in-the-loop Claude session, not a static classifier. It does not attempt to measure "user satisfaction" as a survey score — §5.2's qualitative friction log is a deliberately better fit than a synthetic Likert number for a single-operator validation phase. Both would be reasonable to add once the product has more than one real user; neither is needed, or honest, to add yet.
