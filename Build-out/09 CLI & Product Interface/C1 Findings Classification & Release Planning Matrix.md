# C1 — Findings Classification & Release Planning Matrix

**Role:** Technical Program Manager, working from the accepted Product Acceptance Report. This document classifies and prioritizes only — no fix is designed or proposed here, per explicit instruction.
**Inputs:** `Tests/C1 CLI Product Acceptance Test Plan.md` (findings C1-PAT-1 through C1-PAT-8), `C1 Product Acceptance Report.md` (findings U1–U10 plus four unlabeled Enhancement notes from the command-by-command challenge), `TECHNICAL_DEBT_REGISTER.md` (checked for every Category D candidate before assigning it), and `PRODUCT_READINESS_REVIEW.md`'s own Roadmap section (checked for the same reason — several named v0.9 items there, written before C1 existed, already describe work some of these findings would also satisfy; linking to them instead of minting a duplicate backlog entry is the same discipline the Technical Debt Register itself requires).

---

## Classification key

**Category**
- **A — Bug.** Something C1's own new code (`src/cli.py`) does is incorrect, not merely unclear. Fixable in isolation, no scope change.
- **B — UX Improvement.** The behavior underneath is correct; the presentation is confusing. Clarity only.
- **C — Product Enhancement.** A genuinely new capability or command-surface change, not a correction to something existing.
- **D — Existing Technical Debt.** The defect or gap predates C1 — it lives in `main.py`, in a pipeline module, or in a product-level decision already on record — and C1 either merely inherited it or made it newly reachable by a non-engineer. Linked to its existing tracking entry wherever one exists, rather than assigned a new ID.

**Effort:** XS (well under a day, one isolated change) · S (a day or so, one file, a handful of tests) · M (multiple files or a new command's worth of surface, its own test suite) · L (a new subsystem-sized addition).

**User impact / Engineering risk / Blocks release / Recommended target** are each a direct judgment call, explained per finding where the call isn't obvious.

---

## Findings from the PAT (`C1-PAT-#`)

### C1-PAT-1 — Missing source path framed as "Unexpected error," exit 1
**Category: A (Bug).** The underlying message (`main.py`'s `load_source_config()`, pre-existing) is accurate; the problem is entirely in `cli.py`'s own new Layer 3 handler, which has no way to distinguish a known, well-messaged, expected-at-first-run condition from a genuinely unanticipated one — both get the identical "Unexpected error" prefix and exit code. This is new-to-C1 behavior (no such framing existed before there was a CLI dispatch layer to apply it), and it's incorrect in the specific sense that it misrepresents severity, not merely worded badly.
**Effort:** S. **User impact:** High — this is the single most likely first real command a new user runs. **Engineering risk:** Low — isolated to one dispatch path. **Blocks release:** No, but high-value. **Target: v0.9.**

### C1-PAT-2 — `run` cannot produce `auto`/`approval_required` outcomes without a live provider
**Category: D — already tracked as `TECHNICAL_DEBT_REGISTER.md` TD-01** ("No autonomous production Classification/Metadata Extraction provider... a scheduled run with no human present... would silently degrade into a pile of low-confidence, unreviewed files"), and independently already named as the v1.0 roadmap item **C3/TD-01** in `PRODUCT_READINESS_REVIEW.md`. Not introduced by C1 — C1 only made this pre-existing, already-disclosed limitation reachable by a plain terminal user for the first time, which is why it surfaced in a *product* review even though it isn't a *C1* defect.
**Effort:** L (unchanged from TD-01's own existing scope — building or integrating an autonomous provider is a project-level undertaking, not a CLI fix). **User impact:** Critical — this is the tool's own core promise. **Engineering risk:** High (an autonomous provider is new AI-integration surface, not wiring). **Blocks release:** No — already carries its own "v0.9.0+ decision" framing in the register; this PAT doesn't change that calculus, it just adds fresh, concrete evidence to it. **Target: matches TD-01/C3's existing target, v1.0** (per `PRODUCT_READINESS_REVIEW.md`'s own roadmap — not reassigned here).

### C1-PAT-3 — No confidence-score breakdown ever shown in CLI output
**Category: D — not currently tracked.** `score_confidence()`'s own summary-printing logic predates C1 (`main.py`, written for Module 06's CLI wiring) and C1 never touches it — `run` just calls the function and lets its existing print statements execute unmodified. No existing Technical Debt Register entry covers this specific gap (checked directly — nothing in the summary table addresses confidence-breakdown display). **Recommend a new Technical Debt Register entry be opened for this rather than folding it into a C1 finding**, since the fix, if ever made, would as naturally live in `main.py`'s `score_confidence()` as in `cli.py`.
**Effort:** S. **User impact:** Medium. **Engineering risk:** Low. **Blocks release:** No. **Target: v0.95.**

### C1-PAT-4 — A cleanup-stage failure after a batch already succeeded is reported identically to total failure
**Category: A (Bug).** This is genuinely new C1 code: the try/except boundary that catches this is `cli.py`'s own `main()` dispatch handler, which didn't exist before there was a CLI to have one. The underlying batch execution (`execute_batch()`, pre-existing and independently tested) behaved correctly in every case observed; the incorrect thing is purely how the CLI's new outer layer classifies and reports what happened afterward.
**Effort:** S–M. **User impact:** High — directly risks a user distrusting or duplicating an already-successful operation. **Engineering risk:** Low (the boundary is well-understood and isolated; the specific trigger observed during the PAT was itself a sandbox artifact, not a reproducible defect, but the reporting gap it exposed is real regardless of trigger). **Blocks release:** No. **Target: v0.9.**

### C1-PAT-5 / C1-PAT-6 — Real diagnostic for a blocked batch never reaches the terminal; a retried batch shows stale counts
**Category: D — not currently tracked, but adjacent to `TECHNICAL_DEBT_REGISTER.md` TD-30** ("No config for `destination_root` beyond a single hardcoded value; no settings surface of any kind... blocking for distribution"). The specific summary-printing behavior at fault (`execute()`'s bare `Failed: N` count, and its read-back of *all* of a batch's log history rather than just the current invocation's) is `main.py` code from Module 07's own CLI wiring (WP-12), predating C1 by a wide margin — the same gap was already reachable, identically, by a live Claude session calling `execute()` directly before C1 ever existed. C1 didn't introduce it; C1 is what made it visible to a non-engineer for the first time. **No existing register entry covers the specific "batch-level error detail isn't surfaced" or "retried-batch history conflation" mechanics — recommend two new Technical Debt Register entries**, cross-referenced to TD-30 rather than treated as duplicates of it.
**Effort:** M. **User impact:** Critical — this was the PAT's single highest-value, most concrete, most fixable finding: a precise, correct, already-generated message exists and simply never reaches the person who needs it. **Engineering risk:** Low — the information already exists in the action log; nothing about producing it needs to be invented. **Blocks release:** Recommend yes, for v0.9 specifically — v0.9's own already-declared themes (`PRODUCT_READINESS_REVIEW.md`: "Configuration," "A real, complete CLI entry point") cannot be said to be delivered while their most likely failure mode reports itself unintelligibly. **Target: v0.9.**

### C1-PAT-7 — `scan --foo` shows the top-level usage string, not `scan`'s own
**Category: B (UX Improvement).** The behavior is `argparse`'s own documented default for subparser "unrecognized arguments" handling — not incorrect, just not maximally specific.
**Effort:** S. **User impact:** Low. **Engineering risk:** Low. **Blocks release:** No. **Target: v0.95.**

### C1-PAT-8 — Non-interactive `execute` crashes with a raw `EOFError`
Splits into two distinct findings with different origins, per the classification framework's own instruction to trace root cause precisely rather than bundle:

**C1-PAT-8a — the crash itself. Category: A (Bug).** The interactive prompt loop (`_prompt_decision()`'s `input()` calls) is entirely new C1 code with no pre-existing equivalent; it has no handling for a closed/exhausted stdin, so it surfaces a low-level Python exception through the same generic path as any other unanticipated error. This is incorrect behavior in new code, not a documentation or clarity gap.
**Effort:** XS–S. **User impact:** High — directly undermines an already-documented supported use case (Scheduled mode). **Engineering risk:** Low. **Blocks release:** No, but high-value given the direct conflict with an existing product claim. **Target: v0.9.**

**C1-PAT-8b — the deeper question of how a truly unattended run supplies any decision at all. Category: D — already tracked as `TECHNICAL_DEBT_REGISTER.md` TD-02** ("Human-approval delivery mechanism (OD-3) never resolved... a prerequisite for both real automation... and any real user interface"). Fixing 8a (making the crash clean) does not answer this — it only makes the *absence* of an answer clean instead of ugly. Not introduced by C1; C1's own interactive terminal prompt is, in fact, the first concrete (partial) resolution TD-02 has ever received, for the *attended* case specifically — the *unattended* case TD-02 also names remains exactly as open as it was before this session.
**Target: matches TD-02's existing "v0.9.0+ decision" framing** — not reassigned here.

---

## Findings from the command-by-command UX review (`U#`) and the four unlabeled Enhancement notes

### U1 — `run`'s name overpromises its own scope
**Category: B (UX Improvement).** Nothing about `run`'s behavior is wrong; its own two-line help description already states the boundary correctly. The gap is between the name's implied scope and the documented actual scope.
**Effort:** XS (a wording/messaging change) to S (an actual rename, which also has a switching cost against the muscle memory this session's own testing already built). **User impact:** High — this is the command most new users will reach for first. **Engineering risk:** Low. **Blocks release:** No. **Target: v0.9** — cheap enough, and high-value enough, to bundle with the other v0.9 CLI-clarity work rather than defer.

### U2 — Five of `run`'s six bundled stages have no individual CLI entry point
**Category: C (Product Enhancement).** Nothing is incorrect; this is new command surface (individual subcommands) that doesn't exist today. Not named in `PRODUCT_READINESS_REVIEW.md`'s existing roadmap under any other ID — genuinely new backlog.
**Effort:** M. **User impact:** Medium (mostly a power-user/debugging convenience — re-running one stage after fixing something upstream — rather than a first-run blocker). **Engineering risk:** Low (pure composition, matching C1's own established pattern). **Blocks release:** No. **Target: v0.95.**

### U3 — `status` and `config` substantially overlap
**Category: B (UX Improvement).** Both commands are individually correct; the redundancy is what's confusing.
**Effort:** S. **User impact:** Medium. **Engineering risk:** Low. **Blocks release:** No. **Target: v0.9** (cheap, and directly improves the same first-run clarity the other v0.9 items target).

### U4 — `version` only works as a subcommand, not the conventional `--version` flag
**Category: C (Product Enhancement)** — a new top-level flag is new surface, even though it's a small one.
**Effort:** XS. **User impact:** Medium (a convention mismatch a meaningful fraction of users will hit by habit). **Engineering risk:** Low. **Blocks release:** No. **Target: v0.9** — the cheapest item in this entire matrix relative to its value; no reason to defer it.

### U5 — No `init`/`configure` command
**Category: C (Product Enhancement) — directly satisfies `TECHNICAL_DEBT_REGISTER.md` TD-30** ("no settings surface of any kind... blocking for distribution") **and is a concrete implementation of the already-named v0.9 roadmap item H5, "Configuration (injectable Downloads path, destination root, tunable constants)"** in `PRODUCT_READINESS_REVIEW.md`. Not a new, uncounted backlog item — this finding is evidence in favor of work the roadmap had already scheduled, not a discovery of new scope.
**Effort:** M. **User impact:** Critical — the single highest-leverage item in this whole review; it would materially reduce the practical impact of C1-PAT-1, C1-PAT-5/6, and C1-PAT-8a at once by preventing the unconfigured state from being reached unguided in the first place. **Engineering risk:** Low–Medium (new interactive input handling and file writing, but scoped to two config values). **Blocks release:** Recommend yes for v0.9, consistent with H5 already being a named v0.9 theme. **Target: v0.9** (already effectively targeted, via H5).

### U6 — Raw UUIDs shown in `preview`/the approval prompt
**Category: B (UX Improvement).** The identifiers are correct and necessary internally; showing them to a human making an approve/edit/reject decision adds no decision-relevant value.
**Effort:** XS–S. **User impact:** Low. **Engineering risk:** Low. **Blocks release:** No. **Target: v0.95.**

### U7 — Inconsistent "needs a decision" phrasing across `status`/`preview`/`execute`
**Category: B (UX Improvement).** Pure wording consistency.
**Effort:** XS. **User impact:** Low. **Engineering risk:** Low. **Blocks release:** No. **Target: v0.95.**

### U8 — Zero worked examples anywhere in `--help` output
**Category: B (UX Improvement).** Every command's *description* is accurate; none show a concrete example invocation.
**Effort:** S. **User impact:** Medium — real discoverability value for a first-time user, cheap to add. **Engineering risk:** None (text-only). **Blocks release:** No. **Target: v0.9** (cheap enough to bundle with the other v0.9 clarity work).

### U9 — `report` prints only file paths, no inline content
**Category: C (Product Enhancement)** — surfacing generated content inline is new capability, not a wording fix; it requires reading and rendering what the report generators already produce, not just relabeling existing output.
**Effort:** M. **User impact:** Medium. **Engineering risk:** Low. **Blocks release:** No. **Target: v0.95.**

### U10 — Revisit the original design's deferral of a `validate`/`doctor` command
**Category: C (Product Enhancement).** Explicitly forward-looking, as the original design package itself framed it — this finding's only claim is that the earlier "not much to validate yet" reasoning (`C1 CLI Entry Point — Design Package.md` §3.1) has been partially overtaken by this PAT's own evidence (concrete, checkable pre-flight conditions now exist and were directly observed causing real confusion: C1-PAT-1, C1-PAT-5/6, C1-PAT-8a).
**Effort:** M. **User impact:** Medium (mitigating, not novel — most of its value is redundant with fixing U5/C1-PAT-5 directly; a `validate` command is a second, complementary door into the same underlying gap, not the only door). **Engineering risk:** Low. **Blocks release:** No. **Target: v0.95** (naturally sequenced after U5/the v0.9 configuration work it would validate).

### Unlabeled Enhancement — `scan` has no ad hoc path override
**Category: C (Product Enhancement).**
**Effort:** S. **User impact:** Medium (real trial-ability value for a first-time evaluator). **Engineering risk:** Low. **Blocks release:** No. **Target: v0.95.**

### Unlabeled Enhancement — `execute` has no per-file targeting
**Category: C (Product Enhancement).**
**Effort:** M. **User impact:** Low–Medium (niche; the interactive loop already lets a user reject/skip individual files within one session). **Engineering risk:** Low. **Blocks release:** No. **Target: Future.**

### Unlabeled Low — `undo`'s help text doesn't state its move-only scope
**Category: B (UX Improvement).**
**Effort:** XS. **User impact:** Low. **Engineering risk:** None. **Blocks release:** No. **Target: v0.95.**

---

## Release Planning Matrix

The official backlog for work after C1. Ordering within each release is priority order, highest first. Items already covered by an existing Technical Debt Register entry or Product Readiness Review roadmap item are cross-referenced rather than restated as new work.

### Hotfix
**None.** Nothing found in this review is a safety defect, a data-loss path, or an incorrect filing — every real file operation exercised in the PAT was independently verified against the filesystem and was correct. The live installation has also never processed real user data yet (`PRODUCT_READINESS_REVIEW.md` C2), so there is no in-production harm an out-of-band fix would be racing to stop. Everything below belongs in the normal release cadence.

### v0.9 — "Make it usable by a human, safely, once"
| Finding | Category | Effort | Blocks v0.9? |
|---|---|---|---|
| C1-PAT-5 / C1-PAT-6 (real diagnostic never reaches terminal; stale retry counts) | D (new TD entries recommended, adjacent to TD-30) | M | **Yes — recommended** |
| U5 (no `init`/`configure` command) | C (= existing roadmap item H5) | M | **Yes — recommended** |
| C1-PAT-1 (missing-config framed as "Unexpected error") | A | S | No |
| C1-PAT-4 (cleanup failure reported as total failure) | A | S–M | No |
| C1-PAT-8a (EOF crash on non-interactive `execute`) | A | XS–S | No |
| U1 (`run`'s name overpromises) | B | XS–S | No |
| U3 (`status`/`config` overlap) | B | S | No |
| U4 (no top-level `--version` flag) | C | XS | No |
| U8 (no worked examples in `--help`) | B | S | No |

*Also already on this release's own declared theme list, not restated as new findings here:* C2 (first real run against the live installation), H1/H2 (dependency/installer fix), TD-28 (README/ROADMAP staleness), H3/A2 (undo validation against real content), C4 (Human Review Queue).

### v0.95 — "Prove it, then make it durable"
| Finding | Category | Effort |
|---|---|---|
| C1-PAT-3 (no confidence breakdown shown) | D (new TD entry recommended) | S |
| C1-PAT-7 (`scan --foo` shows top-level usage) | B | S |
| U2 (individual pipeline-stage subcommands) | C | M |
| U6 (raw UUIDs in prompts) | B | XS–S |
| U7 (inconsistent "needs a decision" phrasing) | B | XS |
| U9 (`report` prints only paths) | C | M |
| U10 (revisit `validate`/`doctor`) | C | M |
| `scan` ad hoc path override | C | S |
| `undo` help text scope clarification | B | XS |

*Already on this release's own declared theme list:* H4/A4 (real-world validation at scale), M4 (performance at scale), M3 (log rotation), M1 (governance self-enforcement).

### v1.0 — "Make it a product"
| Finding | Category | Effort |
|---|---|---|
| C1-PAT-2 (`run` can't reach `auto`/`approval_required` without a live provider) | D (= existing TD-01 / roadmap item C3) | L |
| C1-PAT-8b (no unattended decision-supply mechanism) | D (= existing TD-02, "v0.9.0+ decision") — *listed here for completeness; its own target remains an open decision, not fixed to v1.0* | — |

### Future
| Finding | Category | Effort |
|---|---|---|
| `execute` per-file targeting | C | M |

---

## What this matrix deliberately does not do

It does not propose how any of the above should be fixed — no interaction design, no code shape, no file list. It does not reopen or re-litigate `PRODUCT_READINESS_REVIEW.md`'s own roadmap; where a finding matches an already-named item there (H5, C2, C3, C4, TD-28, H3/A2), this document links to it rather than creating a second, competing entry. It does not assign a new Technical Debt Register ID itself — three new entries are recommended (for C1-PAT-3, and for the two mechanics behind C1-PAT-5/6) but minting them is left to whoever next edits `TECHNICAL_DEBT_REGISTER.md`, consistent with that document being a living register this analysis feeds rather than duplicates.

**Waiting for approval before any implementation work is scoped from this matrix.**
