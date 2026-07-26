# C1 — Real CLI Entry Point — Engineering Review

**Subject:** `C1 CLI Entry Point — Design Package.md` (this same folder), dated 2026-07-23.
**Role:** Independent design review, per `ENGINEERING_CHANGE_PLAYBOOK.md` §3's required-review discipline, applied here to a Product Enhancement rather than a defect correction (§1.5 of the design under review already discloses this scope stretch — reviewed on its own terms below).
**Method:** Fresh adversarial read of the design package against the real, directly-verified state of `src/main.py`, `src/pipeline/execution.py`, `src/models/execution.py`, and `src/config/sources.yaml` — not a re-statement of the design's own claims.

---

## Findings

### F1 — Medium-High. The interactive approval loop's "blank input defaults to approve" behavior undercuts the human-approval gate it exists to implement.

§3.3 step 3 specifies: `Approve as suggested / Edit / Reject / Skip remaining? [a/e/r/s, default a]:` — pressing Enter with no input is treated identically to typing `a`. In a batch of, say, twelve `approval_required` files, a user can clear the entire batch by pressing Enter twelve times without ever having to form an explicit judgment about any single row. This is not the same failure mode as the design's own rejected "blanket auto-approve flag" (Alternative C, §4.2) — it still shows each row — but it produces functionally the same outcome under ordinary human behavior (fatigue, a fast Enter-key habit built from other CLIs) without anyone deciding that outcome should be possible.

This matters specifically here because `CLAUDE.md`'s non-negotiable is "never act with full autonomy on uncertain calls," and the entire reason `approval_required` exists as a tier is that these are the uncertain calls. A UI that makes zero-judgment bulk approval one keystroke-habit away from every row is a real, if easily overlooked, erosion of that guarantee — smaller than Alternative C, but the same shape of problem.

**Recommendation:** remove the default. Every row requires an explicit `a`/`e`/`r`/`s` keystroke; blank input (or any other unrecognized input) re-prompts, exactly as already specified for genuinely invalid input. This is a one-line change to §3.3/§3.6's help text and to WP-4's implementation, not a redesign — flagged as a required change before implementation, not a blocking architectural problem.

### F2 — Medium. The `_eligible_for_execution_records` rename (§1.3 item 2, §4.2 Alternative D) is presented as necessary; it is a choice.

Python's leading-underscore convention only suppresses `from module import *` — an explicit `from src.main import _eligible_for_execution_records` works with no change to `src/main.py` at all. The design's own Alternative D correctly rejects *duplicating* the filter logic, but doesn't weigh the option of importing the private name as-is, which would eliminate the design's only non-additive touch to already-shipped code entirely, at the cost of `src/cli.py` depending on a name `src/main.py` marks as internal.

This is a real trade-off, not a defect in the design — but the design package should present it as a decision to make explicitly rather than as a foregone conclusion. Given this project's own stated preference for minimal, disclosed touches over convenience, and that the rename is genuinely tiny and zero-behavior-change, my recommendation is to proceed with the rename as designed — but the design package should be corrected to say "we choose to rename, over the zero-touch alternative of importing the private name, because X," not "the rename is required."

**Recommendation:** Non-blocking. Amend §1.3 item 2's framing when the design is next touched; does not change WP-1's actual scope.

### F3 — Medium. "Product Enhancement — High" (§1.5) is a new severity label, invented for this change, not reconciled with the existing scale.

`ENGINEERING_STANDARD.md` §14 / `FROZEN_MODULE_CHANGE_POLICY.md` §2 already define a severity scale (Critical/High/Medium/Low/Cosmetic) used consistently across every prior tracking document (`PATTERN_TRACKER.md`, `TECHNICAL_DEBT_REGISTER.md`, `VERSIONS.md`, every `RELEASE_NOTES.md`). The design under review invents a sibling label rather than either (a) picking the closest existing tier and stating why, or (b) proposing a formal scale extension. Left as-is, this will surface as a consistency problem at whatever future point this change is tracked/closed alongside PT-002/PT-003-style entries — exactly the kind of "severity doesn't agree everywhere" gap this project's own closure checklists (`ENGINEERING_CHANGE_PLAYBOOK.md` §7) are designed to catch, arriving here one step earlier, at design time instead of close time.

**Recommendation:** Before implementation, either drop the invented label and classify this change using the existing scale directly (my own read: closest fit is **High** — new user-facing capability, touches the system's operational entry point, but zero pipeline-logic risk), or, if a distinct "feature work" track is genuinely wanted going forward, make that a short, explicit governance decision (a one-paragraph `ARCHITECTURE_DECISIONS.md` entry), not an ad hoc label introduced inside one design document.

### F4 — Low. `Build-out/README.md`'s own description of the `Build-out/` folder ("architecture spec, one numbered folder per pipeline step") is not literally accurate once `Build-out/09 CLI & Product Interface/` exists, and the design package doesn't update it.

The design's own §1.4 argues the Module 07/08 precedent justifies folder 09 despite not being a content-transformation "pipeline step" — a reasonable argument, and I accept the placement — but the README line describing the folder should be updated to match reality once this exists (e.g., "...one numbered folder per pipeline step or cross-cutting interface layer"), the same way this project has consistently kept its own folder-map documentation synchronized with what's actually there.

**Recommendation:** Fold into whichever work package touches `src/README.md` (WP-8 already touches documentation); a one-line addition to the same pass, not a separate work package.

### F5 — Low, confirmatory. Staleness between prompt-loop start and final `execute()` call is already safe by construction — verified directly, not assumed.

Read `execute()` in full again for this review: `records = _eligible_for_execution_records()` (soon `eligible_for_execution_records()`) is called fresh, inside `execute()` itself, at the moment `execute()` actually runs — not passed in from the CLI's earlier `preview_batch()` snapshot. `decisions` is a plain `Dict[str, ApprovalDecision]` keyed by `file_id`; any decision collected for a file that is no longer eligible by the time `execute()` runs (e.g. filed by a concurrent process in the minutes a human spent reading prompts) is simply never looked up, since `execute_batch()` iterates the freshly-loaded `records`, not the `decisions` dict's own keys. No new risk here. No action needed — noted so this was checked, not overlooked, consistent with this project's own "verify, don't assume" standard.

### F6 — Low. Add an explicit test case for the zero-`approval_required`-rows path.

§4.6's T3 covers "all-approve," "edit," "reject," "skip-remaining," and "Ctrl-C mid-loop," but not the case where `approval_required` is empty (an all-`auto`, or `auto`-plus-`review_required`-only batch) — the loop should visit zero rows and proceed straight to `main.execute(decisions={})`, printing only the up-front `auto`/`review_required` counts. Worth a named test case so this isn't only implicitly covered by "the loop naturally does nothing if there's nothing to iterate."

**Recommendation:** Add to T3's list at implementation time. Does not change the design.

---

## Findings NOT raised, and why (to state the boundary of this review explicitly)

- **Whether `execute -y`'s name is a good choice at all**, versus e.g. `--no-prompt`: considered, not raised as a finding — `-y`/`--yes` is a well-established convention (`apt`, `npm`, `git`) and the design's §3.6 help text already carries the burden of correcting the "means approve everything" assumption explicitly. A naming bikeshed, not an engineering risk.
- **Whether a markup-file approval mode should be built now instead of deferred** (§4.2 Alternative B): the design's own reasoning for deferring it — a two-command feature disproportionate to C1's stated scope — is sound and not second-guessed here.
- **Whether `validate` should be built now** (§3.1): the design's reasoning (nothing meaningful to validate until H5 exists) is verified independently against the same evidence (a null `destination_root`, a `sources.yaml` that already fails loudly via a normal Python exception if malformed) and is correct.

---

## Recommendation

**APPROVE WITH CHANGES.**

F1 is the one finding that should block implementation as designed — it is the single place this design could quietly weaken the project's own non-negotiable human-approval guarantee, and the fix is small (remove one default, require an explicit keystroke). F2/F3 are judgment calls that should be made explicitly rather than left as unexamined defaults, but neither requires new engineering work to resolve — a paragraph of amended reasoning in each case. F4/F6 are trivial additions to already-planned work packages. F5 required no change, only verification, which this review performed directly.

None of these findings touch the design's core architecture (`src/cli.py` as a thin composition layer, the interactive-loop mechanics apart from F1's default, the exit-code scheme, or the WP decomposition) — the underlying design is sound and matches this project's established composition-over-modification discipline. Recommend the project owner either (a) approve implementation on the condition F1 is applied as specified during WP-4, with F2/F3/F4/F6 tracked as small follow-up notes, or (b) request a revised design package incorporating all six findings before implementation begins, matching the PT-003 precedent for how a design revision cycle is normally handled here.

**Per the STOP POINT instruction: no code has been written. This review, together with the Design Package, completes Phase 1. Waiting for approval before implementation begins.**
