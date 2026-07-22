# Technical Debt Register — Downloads Intelligence

**Date:** 2026-07-20 · **As of:** Pipeline v0.8.0, all 8 v1 modules released
**Purpose:** Every deferred recommendation, known limitation, open decision, and disclosed observation recorded anywhere across Modules 01–08 — consolidated into one place, deduplicated, and categorized. Nothing below is a new finding; every item is traceable to a source document the project already produced during that module's own lifecycle. This register exists so future work picks items up deliberately instead of rediscovering them by accident.

Severity follows the project's own `Rules/Confidence Rules.md`-adjacent convention used throughout the Release Audits: **Critical/High** (none exist unresolved — every one found was fixed before its module released), **Medium** (none carried forward unresolved), **Low**, **Recommended**, **Informational/Cosmetic**. Every item in this register is Low or below — that is itself a meaningful fact about the engine's condition, not an oversight in this register.

**Update, 2026-07-23:** TD-16 is closed — see "Closed items" below. This register otherwise follows the same append-only convention as `Release/VERSIONS.md`/`PATTERN_TRACKER.md`: a closed item's row stays in the summary table (so its history and ID remain traceable) rather than being deleted.

---

## Summary table

| ID | Item | Category | Severity | Modules affected | Target |
|---|---|---|---|---|---|
| TD-01 | No autonomous production Classification/Metadata Extraction provider | AI / Automation | High-impact gap (not a defect) | 02, 03 | v0.9.0+ decision |
| TD-02 | Human-approval delivery mechanism (OD-3) never resolved | UX / Automation | High-impact gap (not a defect) | 07 | v0.9.0+ decision |
| TD-03 | `save_file_record()` O(N×M) read-modify-write cost | Performance | Low (accepted at v1 scale) | 02–07 | Optimize when volume grows |
| TD-04 | Plain JSON `Database/`, no SQLite | Infrastructure | Low (accepted at v1 scale) | cross-cutting | v2 (per `ROADMAP.md`) |
| TD-05 | `action_log.jsonl` grows unboundedly, never rotated | Infrastructure | Low | 08, cross-cutting | v2 |
| TD-06 | Linear-scan lookups (`find_by_current_path`, `lookup_phash_matches`, `lookup_name_matches`) | Performance | Low (accepted at v1 scale) | 01, 04 | Bundled with SQLite migration |
| TD-07 | Business-rule constants hardcoded in code, not loaded dynamically from `Rules/` | Architecture | Low (disclosed, consistent) | 02, 04, 05, 06 | Config-loader pass, any version |
| TD-08 | `Database/Learning/User Corrections.json` captured but never read or acted on | AI / Automation | Low (deliberate v1 boundary) | 02, 07, 08 | v3 active learning (`ROADMAP.md`) |
| TD-09 | Non-recursive scanning — only top level of Downloads seen | Scope | Low (deliberate v1 boundary) | 01 | Future, unvalidated |
| TD-10 | No Watch Folder (real-time) execution mode | Automation | Low (deliberate v1 boundary) | 01, cross-cutting | v3 (`ROADMAP.md`) |
| TD-11 | Single Source only — no Desktop/Google Drive/OneDrive/Dropbox | Scope | Low (deliberate v1 boundary) | 01 | v3 (`ROADMAP.md`) |
| TD-12 | Single destination-library root only | Scope | Low (deliberate v1 boundary) | 05, 07, cross-cutting | Future, not currently planned |
| TD-13 | Multi-document PDF splitting not implemented | Scope | Low (deliberate v1 boundary) | 03, 04 | v2 (`ROADMAP.md`) |
| TD-14 | `Documents/` flat folder, no subfolder taxonomy | Scope | Low (deliberate v1 boundary) | 05 | v2 (`ROADMAP.md`) |
| TD-15 | Corrupted-file hard floor incomplete for Archive/Audio/Application/Video | Reliability | Low (frozen-module boundary) | 02, 03, 06 | Requires Frozen Module Change Policy review |
| TD-16 | Screenshot classification heuristic false-positives on EXIF-stripped real photos | AI accuracy | **CLOSED 2026-07-23** (was: Low, disclosed, not a defect) | 02 | Resolved — see below |
| TD-17 | No Receipt category — receipt-worded docs default to Invoice | AI accuracy | Low | 02 | Future `Classification Rules.md` revision |
| TD-18 | Video `content_date`/`duration` always null (no tag-reading library) | Data completeness | Low (disclosed) | 03 | Future library adoption |
| TD-19 | Judgment-dependent categories validated against small, self-graded UAT batches only | Testing | Low (disclosed, not statistically meaningful) | 02, 03 | Larger/independent rating pass |
| TD-20 | Weekly Summary top-line shows all-zero on a day with real same-day activity | UX | Low (correct behavior, confusing presentation) | 08 | UX/copy pass |
| TD-21 | FUSE/sandbox filesystem blocked post-execution cleanup verification during UAT | Environment | Low (environment-specific, not reproduced as a defect) | 07, 08 | Re-verify on a real filesystem before real-world use |
| TD-22 | Four dead stub functions left in `execution.py` | Code hygiene | Cosmetic | 07 | Housekeeping pass |
| TD-23 | Manually-kept-in-sync action-vocabulary constants in `main.py` vs. `execution.py`, no drift-guard test | Code hygiene | Low | 07 | Add regression test |
| TD-24 | `_normalize_for_index()` / `normalize_filename()` duplicated logic, no shared-drift regression test | Code hygiene | Low | 04 | Housekeeping pass |
| TD-25 | Duplicated helper logic between daily/weekly summary generators (path helper, sibling lookup) | Code hygiene | Recommended | 08 | Housekeeping pass |
| TD-26 | Naive Title_Case naming with no acronym-preservation list (`"NDA"` → `"Nda"`) | UX polish | Low (accepted cosmetic cost) | 05 | Exceptions list, future |
| TD-27 | Module 01 has no `RELEASE_AUDIT.md`/`IMPLEMENTATION_AUDIT.md`/`RELEASE_SUMMARY.md` (structural gap vs. Modules 02–08 convention) | Documentation | Low | 01 | Backfill for consistency, optional |
| TD-28 | `ROADMAP.md` and `README.md` describe v1 as "design complete, not yet built" / "implementation underway" — stale since all 8 modules released | Documentation | Low (found during this review) | cross-cutting | Immediate housekeeping fix |
| TD-29 | No injectable base paths for `storage/database.py` / `storage/runtime_io.py` (hardcoded project-relative constants) | Infrastructure | Low | 01, cross-cutting | Needed before packaging as a real app |
| TD-30 | No config for `destination_root` beyond a single hardcoded value; no settings surface of any kind | Infrastructure / UX | Low today, blocking for distribution | 05, 07 | Required for v0.9.0+ if shipped beyond this vault |
| TD-31 | No retry / no secondary-provider fallback chain for Classification | Reliability | Low (intentional v1 choice) | 02 | Revisit alongside TD-01 |
| TD-32 | `MetadataExtractionRequest.mime_type` never populated by any code path | Code hygiene | Low | 03 | Needed only if a MIME-aware provider is built |
| TD-33 | `ClassificationResult.notes` vs. `ProviderMetadata.reasoning` — no documented guidance on which field a future provider should use | Documentation | Low | 02 | One-line design clarification |
| TD-34 | `duplicate_signals` records only the single best match per detection type, never multiple candidates | Data completeness | Low (intentional v1 limitation) | 04 | Schema change, future |
| TD-35 | No `review_required` auto-requeue — flagged files are never automatically revisited | UX / Automation | Low (deliberate scope boundary) | 07 | Consider for automation work |
| TD-36 | No protection against concurrent external changes to the destination library beyond a single pre-move re-check | Reliability | Low (appropriate for single-user tool today) | 07 | Revisit only if multi-process use is ever supported |
| TD-37 | No retroactive correction of an already-closed Daily Summary (OD-2, the one Module 08 Open Decision never resolved) | Data integrity | Low (deliberate default, disclosed) | 08 | Explicit future decision if it proves necessary |

---

## Detail by theme

### AI capability gaps (highest product relevance)

**TD-01 — No autonomous production Classification/Metadata Extraction provider.** This is, in the pipeline's own words, repeated verbatim in two separate modules' `KNOWN_LIMITATIONS.md`, *"the single largest gap between 'feature complete' and 'fully autonomous.'"* Every judgment-dependent file (ambiguous documents, screenshots, anything Category-uncertain) currently requires a live, in-session Claude conversation to classify — `ClaudeLiveClassifier` has no unattended equivalent. Run without a live session, every judgment file falls back to `Category.UNKNOWN`, which in turn drives it toward `review_required` in Module 06's scoring. This single gap is the reason Scheduled mode, despite being marked "Supported" in `README.md`'s execution-modes table, has never actually been proven end-to-end: a scheduled run with no human present to make judgment calls would silently degrade into a pile of low-confidence, unreviewed files rather than the clean automation the mode implies.

**TD-19 — Judgment quality validated on small, self-graded samples.** Modules 02 and 03 each validated their live-judgment path against a single UAT batch (8 and 9 judgment calls respectively), graded by the same person who built the feature. Both `KNOWN_LIMITATIONS.md` files say this plainly: *"should not be read as statistically meaningful validation... at scale."* This matters more once TD-01 is addressed — an automated provider needs a real accuracy baseline to be trusted, and one doesn't yet exist.

### Automation gaps

**TD-02 — The approval delivery mechanism was never decided.** Module 07's Open Decision OD-3 — *how* a human's `ApprovalDecision`s actually reach the system (an interactive chat table, a generated markup file the user edits, something else) — was explicitly left unresolved at freeze and never revisited. Core batch logic is deliberately indifferent to it, which was the right call for building the engine, but it means there is today no defined, repeatable interaction pattern for approval outside of an ad hoc Claude conversation. This is a prerequisite for both real automation (TD-01/TD-10) and any real user interface (see `PRODUCT_ROADMAP.md`).

**TD-10/TD-11 — Watch Folder mode and multi-source support** are both architected for (the "Source" concept already generalizes) but not built. Both are explicitly Version 3 items in `ROADMAP.md`, deferred as "a bigger engineering lift... only worth building once daily/on-demand scans prove too slow in practice" — a condition that has not yet been tested, because the pipeline has never run against a real folder (see `PROJECT_RETROSPECTIVE.md` §3).

### Infrastructure / scale debt

TD-03 through TD-06 are all variations on the same accepted trade-off: JSON-file storage and linear scans are simple, auditable, and fast enough at v1's tested volumes (tens of files per batch), and every module that touches them re-discloses the cost per `Governance/ARCHITECTURE_DECISIONS.md` decision 11's explicit requirement. None of these are urgent. All of them become urgent at the same inflection point — real, sustained daily use accumulating hundreds or thousands of records — which is precisely the condition `PRODUCT_ROADMAP.md` recommends testing for next.

TD-29/TD-30 are a different flavor of infrastructure debt: hardcoded paths and a single-value destination root are fine for a hand-run vault, but are blocking issues the moment this needs to be packaged as something a second user could install and configure. These are flagged here because they are easy to miss — they read as "not urgent" from an engineering-debt lens but are load-bearing for the Distribution track in `PRODUCT_ROADMAP.md`.

### Scope boundaries deferred by design (not defects)

TD-08, TD-09, TD-12, TD-13, TD-14 are all deliberate v1 boundaries the project chose consciously and documented at design time — recursive scanning, active learning, multi-document splitting, `Documents/` subfolders, and a single destination root. None of these were discovered as gaps during testing; all were named up front in `ROADMAP.md` or the relevant module's Design.md. They're included here for completeness and because several of them (TD-08 especially) become more valuable, not less, once TD-01 is resolved and the system starts accumulating real correction data worth learning from.

### Known, accepted quality gaps

TD-15 (the corrupted-file hard floor) is the one item in this register that spans a genuine cross-module contract gap: Module 06 can only apply its strongest confidence penalty to categories where Modules 02/03 already produce a body-content-validity signal, which is 7 of 11 categories. Every module involved disclosed this identically and independently: fixing it requires reopening an already-frozen module's contract, which is explicitly a `Governance/FROZEN_MODULE_CHANGE_POLICY.md` decision, not something correctable in place. It is listed as Low severity because no released module's own scope was violated — but it is worth flagging to the project owner explicitly, since "flag but don't fix" was the right call at each module's own release and remains a standing, cross-cutting decision no one has revisited since.

### Documentation and housekeeping

TD-22 through TD-28 are small, disclosed, non-blocking cleanup items — dead code, duplicated helper logic, stale cross-references — of the kind every module's own Release Audit already found, classified as Low/Cosmetic, and explicitly declined to fix in order to avoid touching a certifying release for a non-defect. TD-28 is new: this review found `ROADMAP.md` and `README.md` still describe v1 as "not yet built," which was accurate through most of the project's life but has been false since Module 08's release. Because these are user-facing (not governance) documents, this is worth a quick fix independent of any larger roadmap decision — see the recommendation in `PRODUCT_ROADMAP.md` §7.

### Closed items

**TD-16 — Screenshot classification heuristic false-positives on EXIF-stripped real photos. Closed 2026-07-23.** Real-world validation (`PATTERN_TRACKER.md` PT-002, Confirmed Pattern across Runs 002/003) confirmed this disclosed risk was broader and more consequential than this register's original "Low, revisit if reported in practice" framing assumed — it affected 27 of 27 real image-family files across both validation datasets, not an edge case. Designed (`Build-out/02 Classification/Module 02 Post-Freeze Design Correction — PT-002.md`), implemented (`src/pipeline/classification.py`), regression-tested (720/720), and re-validated against the original real-world datasets (`PT002_VALIDATION_REPORT.md`, PASS) under `Governance/FROZEN_MODULE_CHANGE_POLICY.md`'s post-freeze change process. Module 02 patched `1.0.0` → `1.0.1`. Full narrative: `PT002_POSTMORTEM.md`.

**Explicitly not closed by this fix** — kept open here rather than folded into TD-16's closure, since it is a distinct, broader gap TD-16's fix was never scoped to address: image-family files (`.jpg`/`.png`/etc.) still have no route to `Category.Document` even when their true content is a scanned document (only Screenshot/Image are reachable from that extension family) — visible in Run 002's 9 files, which now correctly avoid `Screenshot` but land on `Image`, not `Document`. Not yet given its own TD number; worth doing if a future validation run confirms it's common enough to prioritize.

---

## What this register deliberately does not contain

No Critical, High, or unresolved Medium finding exists anywhere in this register — every one found during eight modules' worth of independent audits was fixed before its module's release, per the project's own non-negotiable gate. This register is a list of accepted trade-offs and disclosed gaps, not a defect backlog. That distinction matters for how the roadmap documents that follow should be read: the engine does not need to be fixed before product work begins. It needs to be *used*.
