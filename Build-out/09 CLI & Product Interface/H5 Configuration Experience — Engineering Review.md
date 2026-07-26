# H5 — Configuration Experience — Engineering Review

**Subject:** `H5 Configuration Experience — Design Package.md` (this same folder), dated 2026-07-23.
**Role:** Independent design review, per `ENGINEERING_CHANGE_PLAYBOOK.md` §3's required-review discipline, applied to a Product Enhancement rather than a defect correction (the design under review discloses this scope stretch in the same way C1's own design did, but — see F2 below — does not carry through C1's own §1.5 severity-classification step).
**Method:** Fresh adversarial read of the design package against the real, directly-verified state of `src/config/sources.yaml`, `src/pipeline/watch_ingest.py`, `src/main.py`, `src/cli.py`, and `requirements.txt`/`src/requirements.txt` — not a re-statement of the design's own claims.

---

## Findings

### F1 — Medium. The targeted-write architecture (Option C) has no plan for YAML special characters in the value being written, and the failure mode this produces is confusing rather than actionable.

§9's `_write_config_value()` performs raw text/regex substitution, not a real YAML serialization of the new value. YAML syntax rules mean an unquoted scalar followed by ` #` starts a comment, and a colon followed by a space (`: `) inside an unquoted scalar can be parsed as a new mapping key. A `destination_root` or Downloads path containing either character — not exotic on a real filesystem (macOS folder names like `"Archive #2"` or `"Client: Acme"` are entirely ordinary) — would be silently truncated or misparsed the moment it's substituted into the file as raw text.

The design's own write-then-verify step (§9) does catch this before declaring success — the re-read would show a truncated value that doesn't match what was intended, so no corrupted config is ever left in a state the tool thinks is valid. That containment is real and correctly designed. But the resulting user-facing message ("the write may not have applied correctly, check `src/config/sources.yaml` directly") gives no indication of *why* — a user with a `#` in a legitimately-named folder would be told to go check a file by hand with no clue what to look for.

**Recommendation:** Serialize the replacement *value* through PyYAML's own scalar-quoting logic before substitution — e.g. `yaml.safe_dump({"_": new_value}).split(": ", 1)[1].strip()` or equivalent — so any value requiring quoting is quoted correctly, while still only ever touching the single target line (Option C's core property is preserved; only the value-formatting step changes). This closes the gap without reopening the Option B (`ruamel.yaml`) dependency question at all. Non-blocking for approving the overall architecture, but should be resolved during WP-1, not discovered later.

### F2 — Medium. No severity classification is stated anywhere in this design package — a gap this project's own C1 review already flagged once, for the same design's own precedent.

C1's Design Package included an explicit §1.5 ("Severity / process-fit classification"), and C1's own Engineering Review (F3) criticized that section for inventing a new label rather than using the existing scale — settling, after review, on **High**. `ENGINEERING_CHANGE_PLAYBOOK.md` §3 requires design-package depth to be justified by severity in the first place. This design package produces full-package depth (matching C1's own Medium/High tier) but never states, anywhere, what severity justifies that depth or where H5 sits on the existing Critical/High/Medium/Low/Cosmetic scale. This isn't a cosmetic omission — a reader arriving at this document without the surrounding conversation has no way to confirm the review rigor applied here is proportionate, the same gap C1's own F3 finding described as a real, recurring risk ("will surface as a consistency problem at whatever future point this change is tracked/closed").

**Recommendation:** Add an explicit classification before implementation begins. My own read, applying the existing scale directly (not inventing a new one, learning C1's own F3 lesson): **High** — same tier as C1 itself, for the same underlying reason (new, user-facing capability with real product leverage; zero pipeline-logic risk; the only genuinely new code is a small, self-contained config writer). Should be added as its own numbered subsection, matching C1's own §1.5 structure, not left implicit.

### F3 — Low-Medium. The design doesn't specify whether `init`/`config set` write the user's raw input or a resolved absolute path — and the one place downstream behavior is checked (`_load_destination_root()`) doesn't resolve relative paths itself.

`src/main.py`'s `_load_destination_root()` does `Path(destination_root)` with no `.resolve()` call (confirmed by direct read). If a relative path were ever written to `destination_root` (e.g. a user types `../library` at the `init` prompt), its meaning would depend on the working directory the pipeline happens to be invoked from at run time — not fixed at configuration time. §9 says `init`'s validation step calls `.resolve()` internally to check `.is_dir()`, but doesn't say the *resolved* (absolute) path is what actually gets written back via `_write_config_value()` — as written, the design is ambiguous between "validate the resolved path, write the user's original typed text" and "write what was validated." Only the latter is safe.

**Recommendation:** State explicitly in §9/FR-3 that `_write_config_value()` always receives and writes the fully resolved, absolute path (`Path(user_input).expanduser().resolve()`), never the raw typed string — closes the ambiguity with a one-sentence addition, no architectural change.

### F4 — Low. The line-matching algorithm for `_write_config_value()` is specified in prose ("scoped to appear after the `sources:` block's `- source_id: downloads` line") but not precisely enough to rule out a false match.

With exactly one source and a known-stable file (verified directly, §7.1 of the design), a naive "first line matching `path:`" regex would work correctly today — but the design's own prose already gestures at wanting to be more careful than that ("indentation-aware," "scoped to appear after...") without stating the actual matching rule precisely enough for an implementer to be confident they've built what was intended, or for this review to confirm it's correct. A stray comment line containing the literal text `path:` (none exists today, confirmed by direct read of the real file, but nothing prevents one being added later) would be a realistic way for a future edit to silently break this.

**Recommendation:** Before WP-1, state the exact rule precisely — e.g. "the first line, after the line containing `- source_id: downloads`, whose stripped content matches `^path:\s*.*$` at 4-space indentation" — as pseudocode or a regex literal, not prose description. Small, mechanical fix; doesn't change the chosen architecture.

### F5 — Low. `config set`'s argparse shape (a sub-subcommand under `config`, vs. flags like `--set-source`) is never specified.

§5 (FR-5) and §9 both write `config set source <path>` in prose, implying `set` is itself a second-level subcommand nested under `config`'s own subparser — a shape none of C1's existing 9 subcommands use (every one is a single-level subparser off the top-level parser). This is a legitimate, buildable argparse pattern (nested subparsers), but the design doesn't confirm this is the intended shape versus, say, `config --set-source <path> --set-destination <path>` flags on the existing `config` subcommand — a materially different, and arguably simpler, implementation with no new subparser nesting to introduce.

**Recommendation:** Decide and state explicitly before WP-3. My own preference, stated as a recommendation rather than a blocking objection: flags on the existing `config` subcommand (`config --set-source <path>`) — avoids introducing the project's first nested-subparser pattern for a single, narrow use, consistent with C1's own "smallest change that satisfies the requirement" discipline. Either is buildable; the design should pick one rather than leaving it implicit in inconsistent-looking prose.

### F6 — Low, confirmatory-with-a-caveat. FR-6's exit-0 choice reuses C1's own precedent, but not C1's own disclosed caveat about it.

Verified directly: C1's Design Package §3.5 does establish "ran to completion, including an expected blocked/nothing-to-do outcome, exits 0" as this project's precedent, and this design's FR-6 correctly cites and reuses it. But C1's §3.5 also carries a disclosed, unresolved open question directly on point: exit 0 regardless of outcome "may be unsatisfying for future scripted/scheduled use, where a caller might want a non-zero signal that 'nothing actually got filed.'" A "not configured yet" condition is exactly this shape of case — H5's FR-6 inherits C1's precedent without inheriting or re-stating C1's own caveat about it, which reads as slightly more settled than the precedent it's built on actually is.

**Recommendation:** Non-blocking — carry C1's own disclosed caveat forward with a one-line note in FR-6 or §8, rather than presenting exit 0 as a fully settled question this design newly confirms. Doesn't change the recommended behavior (exit 0 remains correct for the interactive/attended case this design targets); only the framing needs a small addition.

---

## Findings NOT raised, and why (to state the boundary of this review explicitly)

- **Whether Option C (targeted line-replacement) over Option B (`ruamel.yaml`) was the right call at all:** independently re-verified, not just accepted — `requirements.txt` was re-read directly for this review and does still show `PyYAML` double-pinned to two different versions (`6.0.1` and `6.0.3`), confirming `PRODUCT_READINESS_REVIEW.md` H1 remains open and unresolved as of this review. NFR-5's reasoning (don't add a new dependency into an already-broken manifest) holds under direct re-check, not just on the design's own say-so.
- **Whether NG3 (excluding TD-07's "tunable constants") is a legitimate scope narrowing from H5's original framing, or a way of quietly shrinking the finding:** considered, not raised — `TECHNICAL_DEBT_REGISTER.md` was independently checked and TD-07 is confirmed to be a materially different, larger surface (constants hardcoded across four pipeline modules, not the two config values this design addresses). The narrowing is disclosed, not hidden, and correctly scoped.
- **Whether the write-then-verify safety net (§9) is sufficient without atomic temp-file-plus-rename:** considered, not raised as a blocking finding — the design's own reasoning (no existing write anywhere in this codebase uses atomic rename; a rarely-invoked, human-initiated config write is a different risk profile than `execute()`'s hot path) was independently checked against `storage/database.py`/`storage/runtime_io.py` and confirmed accurate. A reasonable, disclosed proportionality call, not an oversight.
- **Whether `init` should validate that the source path and `destination_root` aren't the same directory (or nested inside one another):** a real, plausible footgun (filing output back into the folder being scanned), but not raised as a required finding here since nothing in the existing, already-shipped pipeline (Module 01/05/07) currently guards against this either — flagging it would be introducing new scope beyond what this design set out to fix, not reviewing what's in front of this review. Worth a note for the project owner to consider adding to FR-2's validation step, but not treated as a blocking gap in this design.

---

## Recommendation

**APPROVE WITH CHANGES.**

None of F1–F6 touch the design's core architecture (a targeted, comment-preserving text writer over a full YAML round-trip; the interactive-wizard-plus-`config set` split; the narrow, specific-exception-type catch in `_cmd_scan`/`_cmd_run`) — the underlying approach is sound, correctly reasoned against real, re-verified constraints (H1's still-open dependency problem, the real file's actual shape, the existing codebase's write conventions), and consistent with this project's established composition-over-modification and disclosed-proportionality discipline. F1 and F2 are the two findings worth resolving before implementation begins: F1 because it's a concrete correctness gap in the one genuinely new piece of logic this design introduces, and F2 because it's a process-consistency gap this project has already, once, specifically flagged as worth catching at design time. F3–F5 are small, mechanical clarifications. F6 is a framing note, not a behavior change.

Recommend the project owner either (a) approve implementation on the condition F1 and F2 are resolved during WP-1 and before implementation respectively, with F3–F6 tracked as small follow-up notes folded into the relevant work packages, or (b) request a revised design package incorporating all six findings before implementation begins, matching the C1 and PT-003 precedents for how a design revision cycle is normally handled here.

**Per the STOP POINT instruction: no code has been written, no repository file other than this review and its companion design package has been touched. This review, together with the Design Package, completes Phase 1. Waiting for approval before implementation begins.**
