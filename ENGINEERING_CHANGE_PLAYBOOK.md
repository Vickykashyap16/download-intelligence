# Engineering Change Playbook

**Status:** Standard process for every future engineering change to this project, effective 2026-07-23. Derived from PT-002 — the first change to go through observation-to-close end to end with a full evidence trail (`PT002_POSTMORTEM.md`, `PT002_WORKFLOW_EVALUATION.md`) — but written to be generic, the same way `Governance/FROZEN_MODULE_CHANGE_POLICY.md` is generic to every module rather than named to Module 01's or Module 02's own patches.
**Relationship to existing governance:** This document does not replace or duplicate `Governance/ENGINEERING_STANDARD.md` (the original nine-stage module-build lifecycle) or `Governance/FROZEN_MODULE_CHANGE_POLICY.md` (the policy for post-freeze defects). It operationalizes them for the specific, recurring case this project now has real experience with: a defect or gap found in an already-released module, from first observation through to close. Where this playbook and `FROZEN_MODULE_CHANGE_POLICY.md` overlap, this document is the practical checklist; that document remains the authoritative policy statement it elaborates.

---

## 1. The standard lifecycle

Every engineering change — a post-freeze correction, and any future change type this project takes on — passes through the same ten stages, in order:

1. **Observation** — a finding is recorded with real evidence, not fixed on sight.
2. **Pattern** — the finding is classified: Single Observation, Confirmed Pattern, Environment Issue, or User Expectation. Only a Confirmed Pattern (or an Environment/User-Expectation item promoted for an unrelated reason) proceeds toward a fix.
3. **Root Cause** — the mechanism is directly measured against real code and real data, not inferred from the symptom alone.
4. **Design** — a design package proportional to the change's severity (§3 below), always including root cause, alternatives considered, the selected approach, risk assessment, compatibility analysis, regression impact, test plan, acceptance criteria, and rollback strategy.
5. **Review** — an independent pass over the design before implementation is authorized, scaled to severity (§3).
6. **Implementation** — the smallest change that satisfies the approved design; scope confirmed held (diff review) before regression begins.
7. **Regression** — full project-wide unit test suite, 100% pass rate required, always run before AND after implementation.
8. **Validation** — confirmation the fix behaves correctly against real-world evidence when real-world evidence exists to validate against (§4 below defines the trigger).
9. **Merge** — the fix is folded into the module's authoritative version record and technical release documentation.
10. **Close** — every required tracking document is updated (§6), and for Medium severity or above, a postmortem is written.

A stage does not begin until the prior stage is explicitly approved. This mirrors `ENGINEERING_STANDARD.md` §1's own rule for original module builds — post-freeze changes are not a lighter-weight process by default, only a narrower-scoped one.

## 2. Required gates

| Gate | Requirement |
|---|---|
| Observation → Pattern | At least one independent, reproducible occurrence, backed by real evidence (not a hypothetical). |
| Pattern → Root Cause | Classification is **Confirmed Pattern** (2+ independent, non-overlapping occurrences) before any fix is proposed — a Single Observation is recorded and held, never fixed from one data point, regardless of severity-looking symptoms. Environment Issues and User Expectations are exempt from this gate (they aren't pipeline defects) but still require the same evidence rigor to classify correctly. |
| Root Cause → Design | Root cause is directly measured against real code/data (reproducible in principle by a third party re-running the same measurement), not asserted from correlation alone. |
| Design → Review | The design package (§3) is complete; if the proposed design requires an architectural change, this is stated explicitly and escalated rather than proceeding. |
| Review → Implementation | Explicit project-owner approval of the design, following the review pass. |
| Implementation → Regression | The diff is confirmed scoped to exactly what the design specified — no unapproved scope creep, verified by grep/diff, not by memory. |
| Regression → Validation | 100% pass rate on the full suite. Any failure stops the process and is reported, not silently investigated-and-fixed inline. |
| Validation → Merge | The validation trigger (§4) is satisfied and produces a PASS or PASS WITH NOTES verdict. A FAIL stops the process. |
| Merge → Close | Version ledger and release documentation are updated and internally consistent (checked, not assumed). |
| Close → done | Every document in the closure checklist (§6) is updated; for Medium+ severity, a postmortem exists. |

## 3. Required design-package depth, by severity

Severity uses the existing shared scale (`ENGINEERING_STANDARD.md` §14 / `FROZEN_MODULE_CHANGE_POLICY.md` §2). PT-002's design package used one fixed ten-section template regardless of size — appropriate for its own Medium severity, but the workflow evaluation found this would be disproportionate for a smaller change. Going forward:

- **Critical/High:** full package (all ten sections), plus at least one independent review round with findings tracked to resolution before approval — same rigor as an original module design.
- **Medium:** full package (all ten sections; this is what PT-002 used), one independent review pass.
- **Low:** a short-form package — Problem Statement, Root Cause, Selected Design (alternatives may be summarized in a sentence rather than each given a full subsection), Regression Impact, Test Plan. No separate review round required; the project owner's approval of the short-form package doubles as the review.
- **Cosmetic:** no design package — fixed in place per `FROZEN_MODULE_CHANGE_POLICY.md` §2's existing rule, documented in the affected file's own change history.

## 4. Required validation — trigger criteria

Regression testing (§1 stage 7) is always required, at every severity. Real-world re-validation (re-executing prior real-world datasets, or gathering new ones, and diffing results) — the most valuable and most expensive stage PT-002 went through — is required when **any** of the following hold, and optional (at the project owner's discretion) otherwise:

- The finding was itself discovered via real-world validation (as PT-002 was) and prior real-world datasets exist to re-run.
- Severity is Critical, High, or Medium.
- The fix touches classification, confidence scoring, duplicate/version detection, or execution/filing logic — the categories of change most likely to have effects only visible against real, uncurated content rather than synthetic fixtures.

When real-world re-validation is triggered, it must, at minimum: reconstruct or gather a dataset with clear evidence of fidelity (byte-for-byte hash verification against original content where reusing prior data, as PT-002 did), execute the real pipeline code (not a simulation of it) in isolated state, and produce a full before/after diff — not a summary — of every affected record, explicitly reporting anything that changed outside the fix's intended scope.

## 5. Required testing, approvals, and evidence — summary

- **Testing:** full regression suite before and after implementation (100% required both times); new permanent regression tests for the specific defect class (never a one-time manual check); real-world validation per §4's trigger.
- **Approvals:** project owner approval at three points minimum — after Design (before Review... or before Implementation if Review is skipped per §3's Low/Cosmetic path), after Implementation (before Regression proceeds to Merge), and at Close. No stage's findings are auto-applied; this mirrors `ENGINEERING_STANDARD.md` §1's own rule.
- **Evidence:** every claim in every stage traces to an artifact that still exists and is independently checkable — a log file, a diff, a measured metric, a hash comparison — never a bare assertion. This is the property that made PT-002's evidence chain (`PT002_POSTMORTEM.md` §11) auditable end to end, and is non-negotiable regardless of how small a change seems.

## 6. Merge criteria

A fix is ready to merge when:

- Regression is 100% passing.
- Validation (§4) produced PASS or PASS WITH NOTES, with any NOTES explicitly disclosed (not glossed over) in the technical record.
- The diff is confirmed scoped to exactly the approved design (no other module's code, contract, or behavior touched, verified not assumed).
- The **13-check Pipeline Contract Verification gate** (`Governance/PIPELINE_CONTRACT_VERIFICATION.md`) has been re-run against the fixed module for Medium severity and above. **This was skipped for PT-002 and is the single clearest process gap the workflow evaluation found** (`PT002_WORKFLOW_EVALUATION.md` §1, §2) — inconsistent with Module 01's own prior patch, which did run it. Going forward this gate is mandatory at Medium+ severity, not discretionary.
- Version bump determined per `Release/VERSIONS.md`'s convention (PATCH/MINOR/MAJOR) and confirmed against the module's actual `MODULE_CONTRACT.md`, not assumed from the fix's apparent size.

## 7. Close criteria — the closure checklist

Closing a change requires updating, and cross-checking for consistency, this exact document set (naming them explicitly closes the "six uncoordinated documents" gap the workflow evaluation found):

1. The finding's entry in its tracking document (e.g. `PATTERN_TRACKER.md`) — mark disposition (CLOSED/IMPLEMENTED/VALIDATED/MERGED or equivalent) with a dated note, never by deleting or rewriting the original finding.
2. The originating evidence ledger (e.g. `VALIDATION_LEDGER.md`) — a dated closure addendum, following its own append-only convention.
3. `TECHNICAL_DEBT_REGISTER.md`, if the finding has a TD entry — close it with a dated note; explicitly name anything the fix did *not* resolve rather than letting closure imply total resolution.
4. `Release/VERSIONS.md` — version bump and a dated History entry summarizing the full Design→Review→Implementation→Regression→Validation→Close chain in one place.
5. The affected module's `Release/ModuleNN/RELEASE_NOTES.md` — a "Post-freeze correction #N" addendum matching the established format (severity, discovered-by, root cause, fix, scope, regression tests added, verification performed, version ledger note).
6. The affected module's `Release/ModuleNN/KNOWN_LIMITATIONS.md`, if the fix resolves a previously-disclosed limitation — mark resolved (strikethrough + note), don't delete the original text.
7. A postmortem (`<FindingID>_POSTMORTEM.md` or equivalent), for Medium severity and above, covering: original observation, evidence collected, root cause, design decision, implementation summary, validation summary, risks discovered, lessons learned, process improvements, time taken, evidence chain, and why the change succeeded (or didn't).

A change is not considered Closed until every applicable item above is updated and a final read-through confirms they agree with each other (same category severity stated consistently, same version number cited everywhere, same verdict language) — not assumed consistent because each was correct individually at the time it was written.

## 8. What this playbook deliberately does not change

- It does not lower the evidence bar `REAL_WORLD_VALIDATION_PLAN.md`/`PATTERN_TRACKER.md` already established for promoting a finding to fixable status.
- It does not shorten `FROZEN_MODULE_CHANGE_POLICY.md`'s severity-based re-release requirements — it makes one of them (the PCV gate) explicitly non-optional in practice, where the policy already required it in principle.
- It does not introduce a new severity scale, versioning convention, or freeze definition — all three already exist (`ENGINEERING_STANDARD.md` §9, §14, §15) and are reused here without modification.
