# Real-World Validation Plan — Version 0.9.0

**Date:** 2026-07-20 · **Status:** Framework design — not yet executed
**Depends on:** `VERSION_09_PLAN.md` (the milestone this framework implements), `PROJECT_RETROSPECTIVE.md` / `TECHNICAL_DEBT_REGISTER.md` / `PRODUCT_ROADMAP.md` (Phase 1 findings this framework exists to test)
**Companion documents:** `METRICS_DEFINITION.md` (what gets measured), `DATASET_GUIDELINES.md` (what data is used and how it's protected), `BENCHMARK_SPECIFICATION.md` (how multiple datasets and multiple releases are compared), `VALIDATION_CHECKLIST.md` (how a non-developer actually runs this)

**This document is a framework, not an execution.** No production code is modified by anything below. No validation run has been performed yet. Everything here is designed so that when a real run does happen, it produces evidence in a consistent, comparable, auditable form — the same posture the project already applies to every module's UAT, extended to real-world data for the first time.

---

## 1. Why this framework exists

`PROJECT_RETROSPECTIVE.md` established that every one of the eight pipeline modules is independently audited, unit-tested, and released — and that none of them has ever run against a real, unstaged Downloads folder. Every UAT to date used a curated external test folder built specifically to exercise a feature, and every judgment-quality claim made so far carries the same disclosed caveat: *small sample, self-graded by the person who built the feature* (`TECHNICAL_DEBT_REGISTER.md` TD-19). This framework exists to close that gap properly — not with another curated test, but with the messy, unpredictable, high-stakes reality the product was built to solve, evaluated by the one person whose judgment about "is this correct" actually matters: the file owner, not the pipeline's builder.

This directly answers `Governance/ARCHITECTURE_DECISIONS.md` decision 14's own definition of Pipeline v1.0.0 — *"all 8 modules built, tested, and passing end-to-end against a real Downloads folder"* — which nothing to date has actually measured.

## 2. Guiding principles

- **The operator's judgment is ground truth, not the pipeline's.** Every prior UAT was graded by the implementer. Real-world validation inverts this: the person whose files these are decides what "correct" means, and the pipeline is scored against that — not the other way around.
- **Use the product as built.** Validation runs through the real CLI entry points (`src/main.py`), Manual mode, with a live human present exactly as the architecture assumes — not a special validation harness bolted on the side. If the real workflow is too awkward to use for validation, that is itself a finding (see `PRODUCT_ROADMAP.md` §4, the UX gap), not a reason to build a shortcut around it.
- **No code changes to pass validation.** This framework measures the engine that already exists. Findings get recorded, classified, and routed back through the project's existing Frozen Module Change Policy / audit process if a genuine defect is found — validation does not fix anything itself, per this milestone's own explicit scope boundary (`VERSION_09_PLAN.md` §4).
- **Evidence over impression.** Every claim this framework produces ("classification is accurate," "auto-tier is safe") must trace to a specific, countable measurement (`METRICS_DEFINITION.md`), not a general sense that a run "went well."
- **Privacy is not an afterthought.** Real Downloads folders contain real bank statements, contracts, and personal documents. `DATASET_GUIDELINES.md` governs this in detail; this plan never asks for raw sensitive content to be copied into project documentation.
- **Non-negotiables still apply.** Nothing in this framework overrides `CLAUDE.md`: never permanently delete anything, every action must be reversible, superseded files get archived. A validation run that violates either is not a "finding" — it's an immediate stop condition (§6).

## 3. What "validation" measures — the five questions

Every other section of this framework decomposes into answering these:

1. **Is it safe?** Does anything get lost, corrupted, or made unrecoverable? (Zero tolerance — see §6.)
2. **Is it correct?** Do classification, extraction, duplicate detection, naming, and destination routing match what the file owner would actually say is right?
3. **Is it well-calibrated?** Does the confidence tier actually predict correctness — specifically, is `auto` (which bypasses human review) ever wrong?
4. **Is it usable?** Does a real person reviewing a real batch find the experience workable, or does every batch turn into friction? (Feeds `PRODUCT_ROADMAP.md`'s UX track, not a pipeline defect by itself.)
5. **Does it hold up at real scale?** Do the accepted-at-test-scale trade-offs (`TECHNICAL_DEBT_REGISTER.md` TD-03–TD-06) actually matter once real, accumulated file counts are involved?

## 4. Process overview

```
Prepare (DATASET_GUIDELINES.md)
   → Establish ground truth (§5, below)
   → Run pipeline via real CLI, Manual mode, live human present
   → Operator reviews batch preview, records approve/edit/reject + reason
   → Score run against METRICS_DEFINITION.md
   → Classify any failures per §7's error taxonomy → file per §8's reporting format
   → Compare against BENCHMARK_SPECIFICATION.md's prior baselines (if any)
   → Check results against §9's acceptance criteria
   → Archive full evidence package (Runtime/Validation/<timestamp>/)
   → Report to project owner
```

Operator-facing steps are written out concretely, with no assumed engineering background, in `VALIDATION_CHECKLIST.md`. This document defines *what* each step means and why; the checklist defines *how* to actually do it.

## 5. Ground-truth methodology

Ground truth is the answer key validation scores the pipeline against — what category a file *actually* is, what its *actual* correct filename/destination would be, whether two files are *actually* duplicates. Establishing it well is the single most important design decision in this framework, because a bad answer key makes every downstream metric meaningless.

### 5.1 Why the existing approval workflow is the right foundation

Module 07's preview/approval/execution step already forces a human to look at every suggestion before it takes effect. This is not incidental to validation — it is validation, if the resulting decision is captured systematically. Every batch preview review already produces one of three outcomes per file, and each one is a ground-truth signal:

| Operator action | What it establishes |
|---|---|
| **Approved as-is** | The pipeline's suggestion (category, name, destination) matches ground truth. Treated as an implicit correctness confirmation. |
| **Edited before approving** | The pipeline's suggestion did *not* match ground truth; the operator's edited value *is* ground truth for that file. |
| **Rejected** | The pipeline's suggestion was unusable; ground truth is "do not file this the way suggested" — the specific reason is captured per §5.3. |

This means ground truth is captured for free, as a byproduct of using the product normally — no separate labeling exercise is required for the fields the approval step already covers (suggested name, suggested destination, and implicitly category, since an edit that changes destination often reflects a category disagreement).

### 5.2 Where the approval workflow doesn't reach — targeted supplemental checks

Three things the ordinary approval flow does not surface on its own, and which need a deliberate, lightweight supplemental check:

- **`auto`-tier files never get shown for review by design** (that's what `auto` means — see `Rules/Confidence Rules.md`). This is exactly the population validation most needs ground truth for, since an `auto` file that's actually wrong is the highest-severity possible finding (§7, §9). **Requirement: every `auto`-tier file in a validation run is spot-checked by the operator after the fact** — not as an approval gate (that would defeat the point of `auto`), but as a post-hoc correctness audit, sampled at 100% for the first several validation runs and re-evaluated for sampling rate only once auto-tier has a real track record.
- **Duplicate/version relationships are asserted, not obviously visible in a name/destination edit.** The operator confirms, for each file flagged as an exact duplicate, near-duplicate, or version-chain member, whether that's actually true — a short, explicit yes/no per flagged relationship, captured during batch review.
- **Extracted metadata fields aren't shown in the destination/filename edit path.** For a sample of files per category (not every file, to keep operator burden reasonable — see `VALIDATION_CHECKLIST.md` for the sampling instruction), the operator spot-checks the `extracted_metadata` values (vendor, date, amount, etc.) against the real document.

### 5.3 Capturing *why*, not just *that*

An edit or rejection alone tells you something was wrong; it doesn't tell you what class of error occurred, which is what `METRICS_DEFINITION.md` and the error taxonomy (§7) need to compute anything useful. When an operator edits or rejects a suggestion, they tag it with one reason from a short fixed list (mirroring the same "named, auditable, never a bare guess" philosophy the pipeline itself already applies to its own fallbacks, per `Governance/ENGINEERING_STANDARD.md` §13):

`wrong_category` · `wrong_or_missing_metadata` · `wrong_filename` · `wrong_destination` · `incorrect_duplicate_flag` · `missed_duplicate` · `incorrect_version_chain` · `tier_felt_wrong_for_this_file` · `other` (free text, kept short and non-sensitive per `DATASET_GUIDELINES.md`)

This tag is the join key between "the operator did something" and "the error taxonomy §7 classifies it as something specific."

### 5.4 Independence from the pipeline's builder

Every metric this framework produces is only as credible as its independence from confirmation bias. The operator establishing ground truth is the file owner reviewing their own real files for a purpose they actually care about (a clean Downloads folder) — not someone grading a feature they built. This is a genuine, structural improvement over every prior UAT's self-grading caveat, and it should be stated plainly in every validation report this framework produces, exactly as the self-grading limitation was stated plainly in every report before it.

## 6. Immediate stop conditions

Certain observations end the validation run immediately, regardless of remaining scope, and escalate straight to the project owner rather than being logged as an ordinary finding:

- Any file is deleted, lost, or its content altered/corrupted by the pipeline.
- An undo operation is attempted and does not fully restore the file to its prior location/name.
- The pipeline takes any action on a file without it having gone through the approval step (an `auto`-tier action is expected and fine; an unapproved `approval_required`/`review_required` action executing anyway is not).

These map directly to `CLAUDE.md`'s non-negotiables. A stop-condition event is filed per §8's format at Critical severity and the run does not continue against that dataset until the project owner has reviewed it.

## 7. Error taxonomy

Every observed discrepancy during validation is classified into exactly one of the categories below, each carrying the project's existing severity scale (`Governance/ENGINEERING_STANDARD.md` §14: Critical / High / Medium / Low / Cosmetic) as a *ceiling* — the actual severity of a specific instance can be lower than the ceiling, never higher.

| Category | Definition | Severity ceiling | Typical source signal |
|---|---|---|---|
| **Data-loss / irreversibility** | A file was lost, corrupted, or an undo failed to fully restore it | Critical | Stop condition, §6 |
| **Unauthorized action** | Any pipeline action taken without going through approval when approval was required | Critical | Action log vs. approval record mismatch |
| **Auto-tier misfile** | An `auto`-tier file (no human review, by design) turns out to be wrong on any dimension | High | §5.2 auto-tier spot-check |
| **Misclassification** | Wrong category, caught by the operator before or during approval | Medium (caught) | `wrong_category` tag |
| **Extraction error** | Wrong or missing metadata field, caught by spot-check | Medium (required field) / Low (optional field) | §5.2 metadata spot-check |
| **Duplicate/version error** | False positive (flagged as duplicate/version when not) or false negative (missed an actual duplicate/version) | Medium | `incorrect_duplicate_flag` / `missed_duplicate` / `incorrect_version_chain` tags |
| **Naming/destination error** | Suggested filename or folder needed operator correction | Low | `wrong_filename` / `wrong_destination` tags |
| **Tier miscalibration** | The assigned tier didn't match the file's actual correctness (e.g. a file needing heavy correction still scored into `approval_required` rather than `review_required`) | Medium | `tier_felt_wrong_for_this_file` tag, cross-checked against `confidence_breakdown` |
| **Reliability fault** | A crash, unhandled exception, or a batch that didn't complete | High (batch-halting) / Medium (single-file, contained) | CLI/terminal output, `error` action-log entries |
| **Performance degradation** | A batch or individual stage taking materially longer than the measured baselines in each module's own `TEST_RESULTS.md` | Low, unless it prevents completion | Wall-clock timing, §5 of `VALIDATION_CHECKLIST.md` |
| **Environment/infrastructure issue** | A problem attributable to the machine/OS/filesystem the validation ran on, not pipeline logic (e.g. the disclosed FUSE-mount cleanup gap, `TECHNICAL_DEBT_REGISTER.md` TD-21) | Informational unless reproduced on a normal filesystem, then re-classify | Direct reproduction attempt |
| **Usability friction** | Not a defect — an observed moment where the real workflow was confusing, slow, or unclear to a real user | Informational | Operator note during review, feeds `PRODUCT_ROADMAP.md` §4, not this pipeline's defect backlog |

Classification follows the same rule every audit in this project already follows: a failure is only attributed to the pipeline if it reproduces directly against real pipeline code, independent of the validation process itself (`Governance/ENGINEERING_STANDARD.md` §6.2) — an operator's own tagging mistake, for instance, is a validation-process note, not a pipeline defect.

## 8. Failure reporting format

Every finding — whether Critical or Informational — is recorded using this fixed template, one entry per finding, appended to that run's evidence package (`Runtime/Validation/<timestamp>/findings.md`, per `BENCHMARK_SPECIFICATION.md`'s archive convention):

```
### Finding <run-id>-<sequential-number>

- Date / batch_id:
- file_id (if applicable; never the raw filename or file content — see DATASET_GUIDELINES.md):
- Error taxonomy category (§7):
- Severity (Critical / High / Medium / Low / Cosmetic / Informational):
- What was expected (ground truth, per §5):
- What actually happened:
- Evidence (action-log line reference, confidence_breakdown, tier, timestamps — never raw file content):
- Suspected cause (if known; "unknown, needs investigation" if not):
- Disposition: [Open / Routed to project owner / Accepted as known limitation / Duplicate of TD-##]
- Linked technical debt item (if this matches an existing `TECHNICAL_DEBT_REGISTER.md` entry, cite it rather than re-describing it)
```

This mirrors the Item/Source/Severity structure already used throughout `TECHNICAL_DEBT_REGISTER.md` and every module's own Release Audit, deliberately — a finding from real-world validation should be exactly as easy to route into the project's existing governance process as a finding from any prior audit.

## 9. Acceptance criteria

These are the conditions under which the project owner would have grounds to declare Pipeline v1.0.0 per decision 14. Meeting them is not automatic — the project owner makes that call explicitly (`VERSION_09_PLAN.md` exit criteria) — but these are the evidence thresholds this framework is designed to produce before that conversation happens.

| # | Criterion | Threshold |
|---|---|---|
| A1 | Data-loss / unauthorized-action findings (§7) | Zero, across every run. Non-negotiable; any single instance blocks acceptance regardless of everything else. |
| A2 | Undo success rate | 100% of attempted undos fully restore the file, across every run. |
| A3 | Auto-tier correctness | 100% of spot-checked `auto`-tier files confirmed correct. Any confirmed auto-tier miss is a High-severity finding that blocks acceptance until root-caused (this is `Rules/Confidence Rules.md`'s entire premise being tested directly). |
| A4 | Evidence volume | At least 3 distinct real-world sessions (not one long run), spanning at least 2 calendar weeks, totaling at least 150 real files processed. Mirrors `VERSION_09_PLAN.md`'s own "sustained... not a single successful run" framing. |
| A5 | Classification / naming / destination acceptance rate | See `METRICS_DEFINITION.md` §2 for the exact formula; recommended starting threshold ≥ 85% approved-without-edit, explicitly tunable once real data exists (same "tuning note" posture as `Rules/Confidence Rules.md` itself). |
| A6 | Reliability | Zero batch-halting Reliability faults (§7) across every run; contained single-file faults are evaluated individually, not against a hard threshold. |
| A7 | Open Critical/High findings | Zero unresolved at the time acceptance is being considered — "unresolved" meaning neither fixed nor explicitly, visibly disposed of by the project owner, per the same standard every module release already applies (`Governance/ENGINEERING_STANDARD.md` §14). |

Any run that fails A1, A2, or A3 stops (§6) and is treated as a blocking finding requiring project-owner review before further validation continues — these three are safety criteria, not quality criteria, and are held to a different standard than A4–A7.

## 10. What this framework deliberately does not do

It does not modify, tune, or "fix" the pipeline to pass these criteria — that would invalidate the entire exercise (`VERSION_09_PLAN.md` §"what this milestone is not"). It does not build any new interface, provider, or automation — those are `PRODUCT_ROADMAP.md` future-track items this framework's findings are meant to *inform*, not preempt. It does not declare v1.0.0 itself — that remains the project owner's explicit decision, informed by, but not automated from, the evidence this framework produces.
