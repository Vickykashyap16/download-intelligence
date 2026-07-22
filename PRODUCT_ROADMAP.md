# Product Roadmap — Downloads Intelligence

**Date:** 2026-07-20 · **As of:** Pipeline v0.8.0, all 8 v1 modules released
**Purpose:** Where `ROADMAP.md` describes *feature* scope for the engine (Version 2/3 pipeline capabilities) and `Governance/PROJECT_ROADMAP.md` tracks *build* progress module-by-module, this document is the first to ask the product question directly: what stands between the engine that exists today and something a real person could actually rely on. It consolidates the gap analysis requested for this phase review and the `TECHNICAL_DEBT_REGISTER.md` items into one prioritized plan.

**Relationship to existing roadmap documents:** This document does not replace `ROADMAP.md` — it widens the lens. `ROADMAP.md`'s Version 2/3/Future-ideas content (Scheduled mode, `Documents/` subfolders, SQLite, Watch Folder, multi-source, active learning) is carried forward here under **Automation** and **Infrastructure**, not duplicated with new numbering. `Governance/PROJECT_ROADMAP.md` remains the authoritative build-progress ledger and version history. Recommended follow-up: once product work begins, point `ROADMAP.md` at this document rather than maintaining two forward-looking lists (see §7).

---

## 1. The honest gap: engine vs. application

Every module from 01 through 08 is released, independently audited, and covered by 716 passing tests. None of that answers a different question: **could a non-technical person install this today, point it at their real Downloads folder, and get value from it without a live Claude conversation?** The honest answer is no, and it isn't close. What exists is a very well-verified *library* — invokable through a chat session, operating on a curated test vault — not yet a *product*. The seven sections below break down exactly what's missing, organized the way the review was requested: by track, not by module.

## 2. Core Engine — Completed

This is the one track with nothing outstanding at Critical/High/Medium severity. Discovery, classification, metadata extraction, duplicate/version detection, naming, destination routing, confidence scoring, preview/approval/execution with undo, and reporting are all implemented, tested, and independently released. The only work remaining here is the accepted, low-severity debt already cataloged in `TECHNICAL_DEBT_REGISTER.md` (TD-03 through TD-06, TD-15 through TD-19, TD-22 through TD-26) — none of it blocking, all of it either "fix when it matters at scale" or "fix during a housekeeping pass." **Recommendation: leave the engine alone.** The single greatest risk to this track's integrity right now is scope creep disguised as polish — see §6.

## 3. Infrastructure — Partial

What exists: JSON-based persistent storage (`Database/`), an append-only action log, a reports directory, a working test/sample dataset structure. What's missing before this can run as a real, standalone product:

- **No injectable configuration.** Base paths, the destination-library root, and business-rule constants are hardcoded (TD-07, TD-29, TD-30). A second user, or even this same user pointing the tool at a different folder, cannot configure it without editing source.
- **No scale headroom validated.** JSON storage and linear-scan lookups (TD-03, TD-04, TD-06) are fine at test volumes; nobody has run this against the number of files a real Downloads folder accumulates over months. This is genuinely unknown, not just theoretically risky — see §5's recommended validation step.
- **No log lifecycle management.** `action_log.jsonl` (TD-05) grows forever. Harmless at test scale; a real problem after a year of real use.
- **No packaging.** There is no installer, no versioned build artifact, no update mechanism — "the product" today is a folder of Python source a Claude session imports and runs.

## 4. User Experience — Largest Gap

This is, by a wide margin, the least-built track relative to what a "desktop application" implies, and it is the track the entire engineering phase was structurally unable to address — UX wasn't in scope for any of the eight modules' Design documents. Concretely, today:

- **There is no graphical interface of any kind.** Every interaction — scanning, reviewing a batch, approving or editing suggestions, reading a report — happens through a live Claude conversation and CLI-style commands in `main.py`. There is no window, no menu bar presence, no notification when new files arrive.
- **The approval mechanism itself was never designed.** Module 07's OD-3 (TD-02) was explicitly left open: there is no defined way for a user to review and approve a batch except through ad hoc chat. A real product needs *some* concrete review surface — even a generated, human-editable file would be a start — and right now there isn't one.
- **Reports are markdown files, not a dashboard.** The Daily/Weekly Summary and Duplicate/Storage Report are well-designed, well-tested markdown documents (Module 08's actual strength), but nothing renders them, links them together, or notifies the user they're ready.
- **No settings surface.** Changing a business rule today means hand-editing a file in `Rules/`. That's appropriate for this project's build phase; it is not appropriate for anyone who isn't the person who built the pipeline.
- **No onboarding.** Nothing walks a new user through connecting their real Downloads folder, understanding what the tool will and won't do, or building initial trust before the first real batch runs.

## 5. AI Capabilities — Partial, with one structural gap

The deterministic parts of the pipeline (exact-hash duplicates, naming templates, confidence deductions) work unattended today. The judgment-dependent parts do not:

- **No autonomous classification/metadata provider exists (TD-01).** This is the single item named as the largest gap in two separate modules' own release documentation. Every ambiguous file needs a live Claude session to classify. This is the real reason Scheduled mode is "supported" in name only — automating a scan without a human present to make judgment calls would currently degrade quietly into a pile of `Category.UNKNOWN` files.
- **No validated accuracy baseline.** The judgment path has been tested against small, self-graded batches (TD-19) — real, but not enough to make a confidence claim to an actual user.
- **No learning loop.** `Database/Learning/User Corrections.json` has captured every human correction since Module 07 shipped and nothing has ever read it back (TD-08). This is low-hanging fruit precisely because the data collection was already built.

## 6. Automation — Not Yet Real

Manual mode (a human explicitly asking Claude to scan) is the only mode proven end-to-end. Scheduled mode exists nominally (triggered via the `schedule` skill) but has never been run for real, and would run directly into the AI-capability gap in §5 the moment it hit an ambiguous file. Watch Folder mode (a real-time background daemon) isn't built at all, and per `ROADMAP.md` was deliberately deferred as "a bigger engineering lift... only worth building once daily/on-demand scans prove too slow in practice" — a claim nobody has tested yet, because the tool has never run against real, continuous Downloads activity.

## 7. Distribution — Nonexistent

There is no path today from "this repository" to "a thing a second person could install." No installer, no packaged app, no update channel, no icon or branding, no store or landing-page presence, no cross-platform verification (everything to date has run inside this specific sandboxed vault environment — including one disclosed, unresolved FUSE-mount filesystem quirk, TD-21, that has never been reproduced or ruled out on a normal filesystem). This track has zero work done because nothing prior to this review asked the question.

## 8. Commercial Readiness — Nonexistent

No pricing or licensing model, no terms of service or privacy policy, no documented data-handling posture (worth flagging plainly: this tool reads the *content* of a user's financial documents, contracts, and personal files — that needs an explicit, written policy before it touches a second person's real folder), no support channel, no error/crash reporting, no legal review. None of this blocks continued engine work or even the recommended next milestone below, but all of it blocks ever shipping this to someone who isn't the project owner.

---

## 9. Consolidated, prioritized roadmap

### v0.9.0 — Prove it, don't build more of it

The engine has never been run against a real, uncontrolled Downloads folder. Every test to date used a curated dataset built specifically to exercise a feature. Before any further engineering investment, the highest-value, lowest-cost next step is **real-world validation**: point Manual mode at an actual Downloads folder, in Manual mode, with a human present exactly as the current architecture assumes, and observe what happens. This delivers real user value immediately (a genuinely messy folder gets cleaned up) using zero new code, and it is the only way to find out whether the accepted-at-v1-scale assumptions in `TECHNICAL_DEBT_REGISTER.md` (§ Infrastructure/scale debt) hold up outside a test fixture. Full detail in `VERSION_09_PLAN.md`.

Bundled into the same milestone, because they're cheap and directly serve the validation goal:
- Fix the stale "not yet built" language in `README.md`/`ROADMAP.md` (TD-28) — a two-minute fix, and it's actively misleading to leave it as-is now that all 8 modules are released.
- Define — even minimally — a concrete approval-review artifact (closing TD-02/OD-3) so the real-world run has *something* better than raw chat to review a batch against. This does not need to be a GUI; it needs to exist.
- Housekeeping-pass the Cosmetic/Recommended items in `TECHNICAL_DEBT_REGISTER.md` (TD-22 through TD-27) opportunistically, only if they're touched anyway — not as dedicated work.

### v1.0.0 — The milestone the project already defined for itself

`Governance/ARCHITECTURE_DECISIONS.md` decision 14 and `Governance/PROJECT_ROADMAP.md` both already define Pipeline v1.0.0 as *"all 8 modules built, tested, and passing end-to-end against a real Downloads folder"* — not a new feature milestone, a **proof** milestone. v0.9.0's real-world run is the prerequisite; v1.0.0 is declaring it sustained and successful across enough real batches (weeks, not one run) that the project owner is willing to call the v1 engine done, not just released. This is a judgment call for the project owner to make explicitly, not an automatic consequence of elapsed time or module count, exactly as decision 14 already states.

### Future releases (v1.x / v2.0+) — Where product work actually begins

Once v1.0.0 is declared, the roadmap forks into the tracks with real remaining scope:

- **Close the automation gap (§5/§6):** an autonomous classification/metadata provider (TD-01), which is the prerequisite for Scheduled mode meaning anything and for Watch Folder mode being worth building at all.
- **Build the smallest real interface** that replaces raw chat for review/approval — this is where TD-02's mechanism decision graduates into an actual UI, and where reports stop being markdown files nobody's notified about.
- **Infrastructure hardening for a second user:** injectable config (TD-29/TD-30), a real destination-root setting, SQLite if real volumes justify it (TD-04).
- **`ROADMAP.md`'s existing Version 2/3 content** (Scheduled mode in earnest, `Documents/` subfolders, multi-source, active learning) — unchanged, still valid, sequenced after the gaps above rather than before them.
- **Distribution and commercial readiness (§7/§8)** — deliberately last. Packaging and a privacy policy are wasted effort on a product that hasn't yet been proven useful to even its own owner.

## 10. Recommended next milestone — by user value, not engineering interest

If the next unit of work were chosen by what's most *interesting* to build, it would probably be the autonomous AI provider (§5) or a real UI (§4) — both are genuinely bigger, more novel engineering problems than anything left in the engine. But neither has been validated as the right thing to build yet, because **the tool has never been used for its actual purpose.** Building a UI for an approval flow nobody has stress-tested, or an autonomous provider to remove a human who's never actually reviewed a real batch, risks solving problems that turn out not to be the real ones.

The highest-value next step is the one with the least engineering glamour and the most direct user payoff: **run Downloads Intelligence, in Manual mode, against a real Downloads folder, and let what actually happens — not what the design documents predicted — drive what gets built next.** This is v0.9.0, detailed in `VERSION_09_PLAN.md`.
