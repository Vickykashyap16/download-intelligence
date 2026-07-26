# C1 (Real CLI Entry Point) — Product Acceptance Report

**Role:** Principal QA Engineer / Product Validation Lead — reviewing the CLI as a product, not as code. No repository file's production code was read for this report; every judgment below is based on what the CLI actually printed to a terminal during the companion `Tests/C1 CLI Product Acceptance Test Plan.md`, executed in full first.
**Scope:** the nine-command surface `python -m src.cli` exposes. Not a re-litigation of Module 01–08's own business logic, which is out of scope here exactly as it was out of scope for the PAT.
**Inputs:** `Tests/C1 CLI Product Acceptance Test Plan.md` (12 executed scenarios, findings C1-PAT-1 through C1-PAT-8) plus the command-by-command challenge below (findings U1 through U10).

---

## Part 1 — Command-by-command challenge

Every command answered against the same four questions: would a new user understand it, is the name right, does it belong, is anything missing.

### `scan`
Understandable — matches the common "scan" vocabulary of antivirus/network tools. Name is correct. Belongs (it's Module 01's own, real, single-purpose operation). **Missing:** no way to point it at an ad hoc folder for a quick trial (`scan /path/to/folder`) — a user has to go edit `src/config/sources.yaml` before they can try the tool on anything, which is a real barrier to "just see what this does" (Enhancement).

### `run`
This is the command every new user will reach for first, and its name is the strongest naming problem on the whole surface. "Run" is the generic verb every CLI tool uses to mean "do the thing" — `npm run`, `terraform run`, `make run`. A reasonable person typing `python -m src.cli run` against their real Downloads folder would expect their files to end up organized. What actually happens (Scenario 3) is six read-only-to-the-source-folder analysis stages, stopping deliberately short of ever touching a file — a genuinely good safety decision, but one the name does nothing to communicate. Nothing in the command's one-line help ("Run scan through confidence scoring... Does not preview, execute, or move anything") is wrong, but a user has to already be reading closely to catch it. **Recommendation: rename, or rename the mental model around it** — something like `analyze` or `scan-all` states the actual boundary; if `run` is kept, its own two-line help description already carries the right words, it just needs to survive being skimmed. Additionally: does it belong as the *only* way to reach 5 of the 6 stages it bundles? See U2 below — a real, separate gap.

### `preview`
Understandable (mirrors "dry run," a widely recognized pattern). Correctly named. Belongs. **Missing:** no filtering (e.g. show only the tier a user cares about); minor, given batch sizes observed so far are small (Enhancement).

### `execute`
Reasonably understandable, though "execute" reads more like a programming term than the domain language this project otherwise uses everywhere else ("file," "organize," "approve"). A name like `apply` or `file` would sit closer to the product's own vocabulary (`README.md`'s own framing: "approves... files get moved and renamed"). Belongs — this is the command the entire tool exists to lead up to. **Missing:** no per-file targeting (`execute --only <file_id>`) — the only choices today are "prompt for every `approval_required` record" or "skip all of them" (`-y`); a user who wants to file just the one file they're sure about still has to sit through the full prompt loop for everything else in the batch (Enhancement, moderate value).

### `undo`
Understandable, correctly named, belongs. Its own help text ("Reverse a previous execute batch") doesn't state the one real scope limit worth knowing — it reverses move-type actions only, not a recorded decline — a small but real documentation gap, not a functional one (Low).

### `report`
Understandable, correctly named, belongs. The real gap, found in testing (Scenario 6): it prints four file *paths* and nothing else. A user runs `report` expecting to learn something and instead has to go open a Markdown file themselves to find out anything at all — for a command whose entire purpose is "tell me what happened," printing zero of that information inline is a real product gap (Medium).

### `status`
The best-designed command on the surface — new, purpose-built for C1, and it reads exactly the way a first-time user would want a "what's going on" command to read. One real gap connects directly to the PAT's most damaging finding (C1-PAT-5/6): `status` knows the destination_root and could trivially check whether it exists and is writable, and could look back at the most recent batch's own action-log entries for unresolved `error` actions — right now it does neither, so the one command explicitly designed to answer "what's my current state" doesn't mention the one thing most likely to be wrong (Medium — and the natural home for C1-PAT-5's fix).

### `version`
Understandable, correctly named, belongs. **The mechanism is wrong for the convention it's imitating.** Every CLI tool a typical user has ever touched (`git --version`, `python --version`, `node --version`) answers this via a top-level flag, not a subcommand — habit alone means a meaningful fraction of users will type `python -m src.cli --version` and get an argparse error instead of an answer. **Recommend adding `--version` as a top-level flag** (can coexist with the `version` subcommand; no reason to remove either).

### `config`
Understandable, correctly named, belongs, and its own "editing not yet supported" disclosure is exactly the right kind of honesty. **But it substantially duplicates `status`.** Confirmed directly, side by side: `status`'s own "Configuration:" section already prints source path, `destination_root`, and execution mode — the exact three fields most users will ever care about from `config`. `config` additionally shows `source_id`/`type`/`enabled`/`recursive` — internal-facing fields a typical user has no reason to inspect. **This is a real "should these be merged" case**, per the user's own explicit question: either fold `config`'s few genuinely extra fields into `status`'s existing Configuration block and retire `config` as a separate command, or clearly differentiate the two (e.g. `status` = "what's happening," `config` = "everything in the YAML file, verbatim, for debugging") and say so in both commands' help text, since right now nothing distinguishes them for a user deciding which to run (Medium).

### Missing from the surface entirely
No `init`/`configure` command. This is the single highest-leverage gap this review found — every one of the PAT's configuration-related failures (C1-PAT-1, C1-PAT-5, C1-PAT-8, and Scenario 10) traces back to the same root cause: a brand-new user has no CLI-guided way to set `sources.yaml`'s path and `destination_root` before their first real command, and every failure mode downstream of that (a scary "Unexpected error," a buried real diagnostic, a raw `EOFError`) is a symptom of the same missing first step. A short interactive `init`/`configure` command — "What's your Downloads folder? What folder should organized files go to?" — writing straight into `src/config/sources.yaml`, would resolve the practical impact of four separate findings at once (High — see the recommendation below).

---

## Part 2 — Classified findings

Findings from the PAT plan (`C1-PAT-#`) and from Part 1's command challenge (`U#`), consolidated and classified.

| ID | Finding | Severity |
|---|---|---|
| **C1-PAT-2** | `run`, invoked exactly as documented against a realistic folder, cannot produce a single `auto` or `approval_required` outcome for any file whose category needs real judgment — every such file lands `review_required`, with no exception demonstrated. The tool's core stated value (classify by content, auto-file with confidence gating) is unreachable from a plain terminal invocation. | **Critical** |
| **C1-PAT-5 / C1-PAT-6** | A real, precise, already-generated diagnostic for a blocked batch (missing or invalid `destination_root`) exists only in `Runtime/Logs/action_log.jsonl` and never reaches the terminal; the summary just says `Failed: N`. A retried batch after the fix compounds this by still showing stale `Failed` counts from the earlier, blocked attempt. | **Critical** |
| **U5** | No `init`/`configure` command — the single highest-leverage fix, since it would materially reduce the practical impact of C1-PAT-1, C1-PAT-5/6, and C1-PAT-8 at once by preventing the unconfigured state from being reached unguided in the first place. | **High** |
| **U1** | `run`'s name promises more than it does — the most likely first real command a user types doesn't communicate its own "stops before filing anything" boundary. | **High** |
| **C1-PAT-4** | A cleanup-stage failure occurring *after* a batch has already completed successfully is reported identically to a failure that prevented completion (`"Unexpected error"`, exit 1) — a user has no way to tell "nothing happened" from "everything happened, then something harmless broke" without independently checking the filesystem. | **High** |
| **C1-PAT-8** | Non-interactive `execute` (the natural shape of the project's own documented Scheduled-mode use case) crashes with a raw, unexplained `EOFError` unless the operator already knows to add `-y`. | **High** |
| **C1-PAT-1** | A first-run, entirely expected "you haven't configured this yet" condition is printed as `"Unexpected error: ..."` with exit code 1 — same framing and severity signal as a genuine bug, despite the message content itself being accurate and actionable. | **Medium** |
| **C1-PAT-3** | No confidence-score breakdown is ever shown anywhere in CLI output — a user can see the number and the tier but never *why*. | **Medium** |
| **U2** | Five of `run`'s six bundled stages (`classify`/`extract`/`detect_duplicates`/`suggest_naming`/`score_confidence`) have no individual CLI entry point — only `scan` is separately reachable. | **Medium** |
| **U3** | `status` and `config` substantially duplicate each other's content with no stated reason to prefer one over the other. | **Medium** |
| **U4** | `version` only works as a subcommand; the near-universal `--version` top-level flag convention is absent. | **Medium** |
| **U8** | Zero worked examples anywhere in `--help` output, top-level or per-command. | **Medium** |
| **U9** | `report` prints four file paths and nothing else — no inline content, no headline numbers. | **Medium** |
| **C1-PAT-7** | `scan --foo` (an invalid option on a real subcommand) shows the top-level usage string instead of `scan`'s own. | **Low** |
| **U6** | Raw UUIDs (`file_id`) are shown in `preview`/the approval prompt with no evident value to a human decision. | **Low** |
| **U7** | Inconsistent phrasing for "needs a decision" across `status` ("Awaiting your decision"), `preview` ("Needs your decision"), and `execute` ("need your decision"). | **Low** |
| **U10** | The original design's deferral of a `validate`/`doctor` command (`C1 CLI Entry Point — Design Package.md` §3.1, "not much to validate yet") should be revisited — this PAT found concrete, checkable pre-flight conditions (source path exists, `destination_root` exists and is writable, stdin is a TTY before prompting) that didn't exist as a case for `validate` when that call was made. | **Enhancement** |
| — | `scan`: no ad hoc path override for a quick trial run. | **Enhancement** |
| — | `execute`: no per-file targeting; the only granularity is "prompt for everything" or "skip everything unattended." | **Enhancement** |
| — | `undo`'s help text doesn't state its move-only scope. | **Low** |

**Not found:** any finding involving an unauthorized file move, a data-loss path, an incorrect filing, or a safety-property violation. Every scenario in the PAT that reached a real filesystem outcome was verified directly against the filesystem, not just against the CLI's own printed claim, and in every such case the actual file operations were correct. Every finding above is about clarity, honesty of in-the-moment communication, and command surface design — not about the tool doing the wrong thing.

---

## Recommendation

**Accepted with Major Issues.**

Not Rejected: the underlying mechanics are sound. Every real file operation observed across twelve executed scenarios — approvals, edits, rejections, auto-tier filing, duplicate archiving, and undo — was independently verified against the filesystem and was correct every time, including the one case (C1-PAT-4) where the CLI's own status message was misleading about an operation that had, in fact, already succeeded. Engineering Review finding F1 (no default on the approval prompt) was confirmed working live, not just in the automated suite. This is a well-built, safe foundation.

Not merely Accepted or Accepted with Minor Issues: two Critical and four High findings is a substantial list, and one of them (C1-PAT-2) goes to the product's own core promise — the command every new user is told to run cannot, on its own, produce the classify-then-auto-file-or-approve experience the whole project exists to deliver, for any file that isn't deterministically identifiable from raw bytes. That specific finding is a restatement, at the product-UX layer, of an already-known and already-disclosed limitation (`TECHNICAL_DEBT_REGISTER.md` TD-01) rather than a new defect C1 introduced — but a Product Acceptance review has to score what a user actually experiences, and what a user actually experiences is a tool that, run exactly as documented, files nothing and approves nothing. The other Critical finding (C1-PAT-5/6) is not a pre-existing limitation at all — it's a genuine, C1-specific gap: a precise, already-written, already-logged diagnostic message simply never reaches the terminal, which is a concrete and comparatively cheap fix, not an architectural one.

None of the findings above require redesigning anything this session has already built. They cluster into a short list of real, well-scoped fixes: surface the action log's own error detail in `execute`'s summary instead of a bare "Failed" count (closes C1-PAT-5/6 and materially softens C1-PAT-1/8 too); distinguish a cleanup-stage failure from a real one (C1-PAT-4); add an `init`/`configure` command (U5, the single highest-leverage item); reconsider `run`'s name or strengthen how its boundary is communicated (U1); and resolve the `status`/`config` overlap (U3) and the `version` flag convention (U4). This is implementation work, not a fresh design cycle — appropriately, it is not proposed here.

**Per the explicit instruction: no implementation work is proposed. Waiting for approval before any of the above is scoped into a work plan.**
