# Version 0.9.0 Plan — Real-World Validation

**Date:** 2026-07-20 · **Status:** Proposed, awaiting project owner approval to begin
**Depends on:** `PROJECT_RETROSPECTIVE.md` (what exists), `TECHNICAL_DEBT_REGISTER.md` (what's deferred), `PRODUCT_ROADMAP.md` §9–10 (why this milestone, not another one)

## Goal

Answer the question the engineering phase structurally could not answer: **does Downloads Intelligence actually make a real Downloads folder better, run the way it's really used, not the way a test fixture assumes?** This milestone is deliberately not a feature-building phase. It produces evidence, not code, and that evidence is what should determine everything the project builds next.

## Why this is v0.9.0 and not v1.0.0

`Governance/ARCHITECTURE_DECISIONS.md` decision 14 defines Pipeline v1.0.0 as all 8 modules "passing end-to-end against a real Downloads folder" — a sustained, proven claim, not a single successful run. v0.9.0 is the run (or runs) that generates the evidence v1.0.0 will be declared on top of. Declaring v1.0.0 remains the project owner's own explicit decision, per that same decision record, and should happen only after this milestone's findings are reviewed — not automatically when it completes.

## What this milestone is not

It is not a UI-building phase, not the autonomous-AI-provider work, not a distribution or packaging effort. Per `PRODUCT_ROADMAP.md` §10, those are all real future needs, but building any of them now would mean guessing at requirements instead of observing them. If this milestone's findings show one of those tracks is more urgent than expected, that's a valid outcome — but it's a decision for after the evidence exists, not before.

## Scope

### 1. Real-world Manual-mode run (the core deliverable)

Run the full pipeline — scan, classify, extract, detect duplicates/versions, name, score, preview, approve, execute, report — against a real, unstaged Downloads folder, exactly as Manual mode is architected: a human present, in a live Claude session, reviewing and approving each batch. Not a synthetic test folder built to exercise a feature; whatever is actually accumulated there.

Suggested approach, lowest-risk first:
- Start with a **read-only dry run** if one is available (scan + classify + score, preview only, no execute) to see what the pipeline *would* do before it moves anything real, given the project's own non-negotiable that every action must be reversible and nothing is ever deleted — begin cautiously anyway.
- Run a small first batch through to actual execution, and verify undo works against real files before trusting a larger batch.
- Scale up over subsequent sessions, not all at once — the goal is observation over multiple real batches, not a single stress test.

### 2. Observe, don't assume — the questions this run needs to answer

- **Classification quality on real content:** does the live-judgment path handle a real, varied mix of files as well as the small curated UAT batches suggested? This is the direct test of TD-19's disclosed statistical-validity gap.
- **Confidence tier distribution:** in practice, what fraction of real files land in `auto` vs. `approval_required` vs. `review_required`? If review-required is too high, that's a signal the scoring or the AI-capability gap (TD-01) needs attention sooner than planned.
- **Scale behavior:** does JSON storage and linear-scan lookup performance (TD-03, TD-04, TD-06) actually degrade noticeably at a real accumulated-file count, or was that concern always going to be moot at this user's actual volume?
- **The approval experience:** reviewing a batch through raw chat, as it stands today — is it actually workable, or does it immediately demand the minimal review-artifact fix flagged in `PRODUCT_ROADMAP.md` §9? This is the fastest possible validation of TD-02/OD-3.
- **Naming and destination quality:** do the generated filenames and folder suggestions actually match what the user would have done by hand? This is the part of the pipeline `TECHNICAL_DEBT_REGISTER.md` has the least real-world signal on.
- **Anything that breaks.** Real files are messier than any test fixture — unusual extensions, unusually large files, permission quirks, content the classifier has never seen. Log every surprise, whether or not it causes a failure.

### 3. Fix the two cheapest, highest-leverage items alongside the run

These aren't new engineering — they're both already-identified, near-zero-cost corrections that directly serve this milestone's goal:

- **Correct the stale scope language** in `README.md` and `ROADMAP.md` (`TECHNICAL_DEBT_REGISTER.md` TD-28) — both still describe v1 as "design complete, not yet built," which has been inaccurate since Module 08 released and would confuse anyone reading them during this validation phase.
- **Define a minimal, concrete review artifact** for approval (closing part of TD-02) — even a simple generated batch-preview file the user reads and edits before confirming, rather than pure conversational back-and-forth. This does not need to be a UI; it needs to exist so the real-world run has something repeatable to evaluate.

### 4. Explicitly out of scope for v0.9.0

- Any change to Modules 01–08's core logic (unless the real-world run surfaces an actual defect, in which case it follows the same Frozen Module Change Policy / audit process every prior correction has used — not an ad hoc fix).
- The autonomous AI provider (TD-01) — a real future need, not this milestone's job.
- Any graphical interface, packaging, or distribution work.
- Scheduled or Watch Folder mode.

## Deliverable

A findings report (structure mirrors this project's existing UAT-plan convention — real run, real observations, disclosed issues classified by severity) covering: what was scanned, what the pipeline did with it, where it matched expectations, where it didn't, tier distribution observed, any defects found and their disposition, and — critically — an evidence-based recommendation on what v1.x should prioritize first, replacing the current guess-based sequencing in `PRODUCT_ROADMAP.md` §9 with real signal.

## Exit criteria

- At least one real Downloads folder has been run through the full pipeline to actual execution and reversed via undo at least once, successfully.
- The two cheap fixes in scope item 3 are complete.
- A findings report exists and has been reviewed by the project owner.
- The project owner has made an explicit go/no-go call on declaring Pipeline v1.0.0, informed by this milestone's evidence rather than by module count alone.
