# Project Backlog — Downloads Intelligence

**Date:** 2026-07-23 · **Prepared by:** Project Phase 4 (Technical Program Management review, following PT-002's close — see `CHANGELOG.md`).
**Purpose:** A single, priority-ordered view of every remaining open item across the project — `PATTERN_TRACKER.md`'s findings, `TECHNICAL_DEBT_REGISTER.md`'s 36 remaining items, `PRODUCT_ROADMAP.md`'s track-level gaps, and `VALIDATION_PROGRESS.md`'s open acceptance criteria — superseding the scattered per-document "next steps" framing each of those documents used individually. Nothing in this document authorizes implementation, redesigns architecture, or modifies production code; it is a planning and prioritization artifact only.
**Ordering principle:** Strictly by engineering value and evidence — how well-understood the item is (Evidence level), how much it would cost to address (Effort), how much could go wrong (Risk), and how much it's actually worth doing (value, folded into Priority). A cheap, well-evidenced, high-value item outranks an expensive, speculative one regardless of which document it originally came from or how severe its label sounds.
**PT-002:** Closed, implemented, validated, merged — archived as a historical engineering record (`PT002_POSTMORTEM.md`). It does not appear below; it is not open work.
**PT-003:** Closed 2026-07-23, implemented, validated (PASS WITH NOTES), merged — archived as a historical engineering record (`PT003_POSTMORTEM.md`). It does not appear below either; it is not open work. This document is otherwise unchanged from its original 2026-07-23 prioritization — PT-003's closure removes it from the list, it does not trigger a re-prioritization of anything else below.

---

## 1. Scoring methodology

- **Status:** Closed (done, no further action) · Active (open, actionable now) · Blocked (open, but cannot proceed until an external condition changes — e.g. calendar time, an environment fix) · Deferred (open, intentionally not being worked yet, by project-owner or documented design choice).
- **Evidence level:** Observation (a gap or idea, not yet investigated in depth) · Confirmed Pattern (recurs across independent instances/runs) · Root Cause Known (the mechanism is directly understood, not inferred) · Design Ready (a reviewed/approved design package exists) · Implementation Ready (design approved, only build work remains).
- **Effort:** Small (hours to a couple days, single function/file) · Medium (a focused multi-file change or a full post-freeze correction cycle, PT-002-sized) · Large (new architecture, a new subsystem, or a cross-cutting migration).
- **Risk:** Low (contained, easily reversible) · Medium (real blast radius or a genuine trade-off) · High (architectural, safety-relevant, or hard to reverse).

---

## 2. Priority 0 — Do next (trivial cost, real and immediate value)

| ID | Item | Status | Evidence | Effort | Risk |
|---|---|---|---|---|---|
| TD-28 | `ROADMAP.md`/`README.md` still describe v1 as "design complete, not yet built" — false since Module 08's release. Actively misleading to any reader. | Active | Observation (confirmed stale by direct read) | Small | Low |
| TD-20 | Weekly Summary shows all-zero on the current day despite real same-day activity — correct behavior, confusing presentation. A short copy/UX clarification closes the gap between "correct" and "not confusing." | Active | Root Cause Known (`ARCHITECTURE_DECISIONS.md` decision 27) | Small | Low |
| A2 (undo validation) | Test `undo_batch()` against Run 003's 14 real, already-executed filed files — the first opportunity this project has had to validate undo against genuine, non-synthetic executed content. Data already exists; no new dataset needed. | Active | Observation (undo mechanics unit/integration-tested; never exercised against real filed content) | Small | Low |

**Why these lead:** all three are cheap enough that deliberation costs more than doing them, and each closes a real, currently-open gap (a misleading public-facing doc, a confusing-but-correct report, and an entire untested acceptance criterion, A2) with no design work required first.

---

## 3. Priority 1 — Next real engineering cycle

| ID | Item | Status | Evidence | Effort | Risk |
|---|---|---|---|---|---|
| TD-02 | No defined approval-review mechanism (Module 07's Open Decision OD-3) — every batch review happens through ad hoc chat. Does not need to be a GUI; needs to be *something* concrete. Already identified in `PRODUCT_ROADMAP.md` as bundled into the v0.9.0 milestone. | Active | Root Cause Known (need well understood; no concrete mechanism designed) | Medium | Low–Medium (a UX/process decision, reversible) |
| A4 (validation evidence volume) | `REAL_WORLD_VALIDATION_PLAN.md`'s own acceptance bar (≥3 sessions, ≥2 calendar weeks, ≥150 files) remains unmet — 2 sessions, 1 calendar day, ~45 files so far. The single largest remaining gap to a stronger release-readiness recommendation than "Ready for Limited Production." | **Blocked** — not on effort, on elapsed calendar time; no amount of same-day work substitutes for it. | Observation (the gap and its bar are both precisely defined) | Small (per session) | Low |
| TD-21 | FUSE-mount cleanup failure (the PT-009 mechanism) has never been re-verified on a normal, non-sandboxed filesystem — root cause is fully understood and independently reproduced, but only inside this validation environment. | Blocked — requires a real-filesystem session, naturally bundled with the next A4 validation run. | Root Cause Known | Small | Low |
| PT-001 | Real-Downloads-folder file-access gap between the file-reading and code-execution tool grants (Run 001). Did not reproduce in Run 003, but not yet closed without a second independent confirmation. | Blocked — same reason as above, only confirmable during a live session with a freshly-connected folder. | Observation | Small | Low |

**Why these are next:** PT-003 (formerly the lead item here) closed 2026-07-23 via its own full engineering cycle — see `PT003_POSTMORTEM.md`; it no longer appears in this table. Of what remains, TD-02 unblocks a real product gap at moderate, contained cost — the strongest-evidenced actionable item left at this priority tier. The three Blocked items cost nothing to schedule now and should simply be attached to the next real-world validation session rather than treated as separate initiatives.

---

## 4. Priority 2 — Planned, real value, larger or cross-cutting

| ID | Item | Status | Evidence | Effort | Risk |
|---|---|---|---|---|---|
| TD-19 | Judgment-dependent classification/extraction has only been validated against small, self-graded batches (8–9 judgment calls per module) — not statistically meaningful at scale, and never independently rated. | Deferred | Observation | Medium–Large | Low |
| TD-15 | Confidence's corrupted-file hard floor only applies to 7 of 11 categories (Archive/Audio/Application/Video lack a body-content-validity signal from Modules 02/03). A genuine cross-module contract gap, not a single module's oversight. | Deferred — explicitly requires a `FROZEN_MODULE_CHANGE_POLICY.md` review since it spans multiple frozen modules' contracts. | Root Cause Known | Medium | Medium (reopens more than one frozen contract) |
| TD-29 / TD-30 | No injectable base paths (hardcoded project-relative constants) and no real destination-root configuration beyond a single hardcoded value. Low-impact today; blocking the moment this needs to run for a second user or be packaged at all. | Deferred | Root Cause Known | Medium | Medium (touches path-handling in every module) |
| TD-01 | No autonomous production Classification/Metadata Extraction provider — the single largest named gap in two modules' own release documentation, and the reason Scheduled mode has never been proven functional. High product value, but this is a product/business decision (per `PRODUCT_ROADMAP.md` §9, deliberately sequenced after v1.0.0 is declared), not a ready-to-schedule engineering task. | Deferred | Root Cause Known (need fully understood; no provider design exists yet) | Large | Medium (safety net already holds via existing fallback; real behavior/cost change) |

---

## 5. Priority 3 — Backlog, defer until a trigger condition (scale, volume, or a second user)

| ID | Item | Status | Evidence | Effort | Risk |
|---|---|---|---|---|---|
| TD-03 / TD-04 / TD-06 | JSON-file storage, whole-store read-modify-write, and linear-scan lookups — fine at v1's tested volumes; genuinely unknown (not just theoretically risky) at real, sustained real-world volume. | Deferred, explicitly "optimize when volume grows" | Root Cause Known | Large (TD-04 specifically, a real migration) | Medium (data-migration risk) |
| TD-05 | `action_log.jsonl` grows unboundedly, never rotated. | Deferred, v2 | Observation | Small | Low |
| TD-08 | `Database/Learning/User Corrections.json` captured since Module 07 shipped, never read back — real product value (active learning), but a deliberate v1 boundary and a genuine behavior-changing feature, not a bug fix. | Deferred, v3 | Observation (data already collected — readiness is higher than a typical Observation item, but the *feature* itself doesn't exist) | Large | Medium |
| TD-17 | No Receipt category — receipt-worded documents default to Invoice, handled correctly via the `ambiguous` signal today. | Deferred | Observation | Small–Medium | Low |
| TD-18 | Video `content_date`/`duration` always null — no tag-reading library adopted yet. | Deferred | Observation | Medium | Low |
| TD-22 – TD-27 (bundle) | Code hygiene: dead stub functions, manually-synced action-vocabulary constants, duplicated normalization/helper logic, naive Title_Case naming, Module 01's missing release-audit backfill. All Low/Cosmetic, all "fix opportunistically if touched anyway," per `PRODUCT_ROADMAP.md`'s own explicit recommendation. | Deferred | Observation | Small each | Low |
| TD-31 – TD-37 (bundle) | No retry/secondary-provider fallback for Classification, unpopulated `mime_type` field, undocumented `notes`/`reasoning` field-usage guidance, `duplicate_signals` single-best-match-only limitation, no `review_required` auto-requeue, no concurrent-external-change protection, no retroactive Daily Summary correction. All Low, all intentional v1-scope choices already disclosed at their originating module's own release. | Deferred | Observation | Small–Medium each | Low |

---

## 6. Priority 4 — Long-tail, explicitly sequenced last

| ID | Item | Status | Evidence | Effort | Risk |
|---|---|---|---|---|---|
| TD-09 / TD-10 / TD-11 / TD-12 / TD-13 / TD-14 (bundle) | Deliberate v1 scope boundaries, already named in `ROADMAP.md` before any testing began: non-recursive scanning, Watch Folder mode, multi-source support, single destination root, multi-document PDF splitting, `Documents/` subfolder taxonomy. None discovered as gaps during testing — all consciously deferred at design time, several explicitly conditioned on "once daily/on-demand scans prove too slow in practice," a condition never yet tested. | Deferred, v2/v3 by design | Observation | Large (most items) | Low–Medium |
| UX / Interface build-out | No graphical interface, no settings surface, no onboarding, no dashboard rendering for the existing well-built Daily/Weekly/Duplicate/Storage reports. The single largest gap relative to "a real product," and a track no module's own Design phase was ever scoped to address. | Deferred — explicitly sequenced after the automation gap (TD-01/TD-02) per `PRODUCT_ROADMAP.md` §9. | Observation | Large | Medium |
| Distribution & Commercial readiness | No installer, no packaging, no update channel, no pricing/licensing/privacy policy, no support channel — this tool reads the content of a user's financial/personal documents and has no written data-handling policy yet. | Deferred — deliberately last; wasted effort before the engine is proven useful even to its own owner, per `PRODUCT_ROADMAP.md` §7/§8. | Observation | Large | Medium (privacy/legal exposure is real once a second user is involved, even though the work itself is not urgent today) |

---

## 7. Milestone decision points (not scored — belong to the project owner, not this backlog)

- **Pipeline v1.0.0 declaration** (`Governance/ARCHITECTURE_DECISIONS.md` decision 14): "all 8 modules built, tested, and passing end-to-end against a real Downloads folder" — a judgment call about whether enough real-world evidence (A4, above) has accumulated, not an automatic consequence of module count or elapsed time.
- **Whether to pursue TD-01 (autonomous provider) at all**, and on what timeline — a product-direction decision this backlog surfaces evidence for but does not make.

## 8. Reviewed, no engineering action required

For completeness — every `PATTERN_TRACKER.md` finding was reviewed for this backlog, not only the ones that produced an item above:

- **PT-004, PT-007, PT-010** — positive findings (safety gate, real-execution correctness, corrupted-file handling all confirmed working). Nothing to fix; continued spot-checking during future real-world runs is the only ongoing action, already covered by existing validation practice.
- **PT-005, PT-006, PT-008, PT-011** — User Expectation findings; all match already-documented, designed behavior exactly. No defect. PT-008's quantified naming-fallback edit-rate data is retained as evidence for a possible future naming-template discussion, not as an open item in its own right.

## 9. Summary

Two items (§2) are worth doing immediately, before anything else, purely on cost/value grounds. **Update, 2026-07-23 (later same day):** PT-003 — originally this section's lead item, the strongest-evidenced real defect remaining at the time this backlog was written — completed the full engineering-change lifecycle `ENGINEERING_CHANGE_PLAYBOOK.md` formalizes (design, 2 rounds of independent review, implementation, regression, validation, merge, close) the same day this backlog was produced, and is now closed (`PT003_POSTMORTEM.md`); it no longer appears in §3. Of what remains, TD-02 is now the strongest-evidenced actionable item at that priority tier. Three items are Blocked on calendar time or a live session, not on engineering effort, and should be scheduled together rather than pursued independently. Everything else is real, disclosed, and none of it is urgent — the engine's Core track has nothing outstanding above Low severity, and the largest remaining gaps (autonomous AI, a real interface, distribution) are product-scale initiatives this project has already, correctly, chosen not to start until the evidence above justifies them. **No reprioritization of the remaining backlog was performed as part of PT-003's closure** — that remains a separate, future decision for the project owner.
