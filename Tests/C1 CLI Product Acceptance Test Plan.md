# C1 (Real CLI Entry Point) — Product Acceptance Test (PAT) Plan

**Role:** Principal QA Engineer / Product Validation Lead. Not a code review — the repository's own source is treated as a black box; every scenario below was executed as a first-time user actually would, from a terminal, reading only what the CLI itself prints.
**Scope:** `python -m src.cli` end to end — installation-adjacent first run, help/discoverability, the nine subcommands, error handling, recovery, and the advertised human-approval workflow. Not a re-test of Module 01–08's own business logic (classification accuracy, naming templates, confidence formula) — those are each already independently validated and released; this PAT tests whether a person can actually *use* the finished pipeline through the new CLI.
**Method:** Every scenario below was actually executed, not desk-checked. A full copy of the repository was made to an isolated sandbox directory so nothing here touched the real project's `Database/`/`Runtime/`/`src/config/sources.yaml` (the same isolation discipline this project's own test suite uses, and the same lesson the Module 07 UAT test-isolation defect already taught it). Real sample files (`Samples/Invoices/`, `Samples/Images/`, `Samples/Documents/`) were copied into a scratch "Downloads" folder to exercise real scan/classify/name/score behavior. Where a scenario needs a pipeline state that can't be produced by a plain terminal invocation alone (a specific tier, a duplicate pairing) — because, as Scenario 3 itself demonstrates, this is not always possible from a plain terminal invocation — records were constructed directly and saved to the metadata store, the same fixture-construction technique this project's own automated tests already use; this is disclosed at each such scenario rather than presented as if the CLI produced it unaided.
**Date executed:** 2026-07-23.
**Environment note:** the execution sandbox used for this PAT has one filesystem quirk of its own (rejecting some file-deletion operations with `Operation not permitted`, matching an unrelated, pre-existing `.git/index.lock` restriction already observed in this same environment) — where this affected a scenario, it is called out explicitly and not counted as a CLI defect in its own right, though what it exposed about the CLI's error handling *is* counted (see Scenario 8).

---

## Validation-area coverage map

| Required validation area | Covered by scenario(s) |
|---|---|
| Installation | 1 |
| First run experience | 1, 2 |
| CLI usability | all |
| Help system | 1, 11 |
| Command discoverability | 1, 11 |
| End-to-end workflow | 3, 6 |
| Error messages | 2, 8, 9, 10, 12 |
| Recovery | 8, 9 |
| Undo | 9 |
| Reporting | 6 |
| Status command | throughout, esp. 2, 3, 9 |
| Configuration experience | 2, 10, 11 |

---

## Scenario 1 — Brand-new installation, first command

**Preconditions:** Fresh checkout. `Database/Metadata/metadata_store.json` is `[]`, `Runtime/Logs/action_log.jsonl` is empty, `src/config/sources.yaml` has `path: null` and `destination_root: null` — the project's actual real, current state, confirmed directly rather than assumed.

**Steps:** `python -m src.cli` (no arguments); `python -m src.cli --help`; `python -m src.cli status`; `python -m src.cli version`; `python -m src.cli config`.

**Expected behaviour:** A user with zero prior context can see what commands exist, get a plain-language description of what the tool does, and confirm nothing has happened yet — all without reading any documentation file.

**Expected CLI output:** A command list with one-line descriptions; a status view stating the store is empty; a version string; a configuration view showing the source path and destination are both unset.

**Actual result:**
```
$ python -m src.cli
usage: python -m src.cli [-h] {scan,run,preview,execute,undo,report,status,version,config} ...
Downloads Intelligence — classify, name, dedupe, and file your Downloads folder,
with a human approval step before anything moves. Nothing is ever deleted.
  scan       Identify new files in the configured source (Module 01).
  run        Run scan through confidence scoring (Modules 01-06)...
  ...
Note: scan/run classify and extract files without a live AI judgment provider
when run this way ... This is a known, disclosed limit, not a bug.
EXIT: 0
```
`status` correctly reports an empty store; `version` correctly reads `Pipeline Version 0.8.0` live from `Release/VERSIONS.md`; `config` correctly shows both the source path and `destination_root` as unset, with an explicit note that execution will block until `destination_root` is configured.

**Pass/Fail criteria:** PASS if a user can determine, from CLI output alone, what commands exist and that the tool is in a safe, untouched state. **PASS.** (Product-level observations — the "Note:" epilog only appearing on the *top-level* help, and the absence of any "what do I do first" pointer — are carried into the Product Acceptance Report, not scored as a plan failure.)

---

## Scenario 2 — Empty Downloads folder / missing configuration

**Preconditions:** Same fresh state as Scenario 1. `src/config/sources.yaml`'s `sources[0].path` is still `null` (the real, shipped default — nothing has been configured).

**Steps:** `python -m src.cli scan`; `python -m src.cli run`.

**Expected behaviour:** A clear, first-run-appropriate message telling the user their Downloads path isn't configured yet, and what to do about it.

**Expected CLI output:** Something in the shape of "Downloads path not configured — set `sources[0].path` in `src/config/sources.yaml`" with a normal, low-alarm exit.

**Actual result:**
```
$ python -m src.cli scan
Unexpected error: Source 'downloads' has no path set in config/sources.yaml — fill in the real Downloads folder path before scanning
EXIT: 1
```
The underlying message is accurate and even tells the user the exact fix — but it is prefixed with **"Unexpected error:"** and exits 1, identical to the framing and exit code a genuine internal bug would produce. `run` produces the byte-identical message (it calls `scan()` first).

**Pass/Fail criteria:** FAIL on framing — the message content is correct and actionable, but a first-run configuration gap (the single most likely first thing any new user will hit) is presented with the same severity and vocabulary as an unanticipated crash. Logged as Finding C1-PAT-1 (Product Acceptance Report).

---

## Scenario 3 — Mixed Downloads folder, full advertised workflow

**Preconditions:** A scratch "Downloads" folder containing: two real sample invoices (one an exact byte-for-byte duplicate of the other, renamed), one real sample image, one real sample resume, one zero-byte file, one `.crdownload` partial-download stub. `destination_root` unset (the real, shipped default at this point in the scenario).

**Steps:** `python -m src.cli run` (the CLI's own advertised "run the pipeline" command).

**Expected behaviour:** Files are discovered, classified by real content, deduplicated, named, and scored, ending with a mix of tiers reflecting genuine confidence in each classification — this is the tool's whole stated value proposition (README: "classify files by actual content, not extension").

**Expected CLI output:** A `scan` summary (6 seen, 4 discovered, 2 skipped with correct reasons — `.crdownload` and the zero-byte file), a `classify` summary, a `detect_duplicates` summary correctly flagging the one exact duplicate, a `suggest_naming` summary, and a `score_confidence` summary with a plausible tier mix.

**Actual result:** Scan, skip-reason labeling, and exact-duplicate detection all worked correctly and exactly as documented. But: `classify` reported **3 of 4 files fell back to Unknown** ("provider unavailable/invalid response") — only the image (a deterministic, non-judgment path) classified correctly. `score_confidence`'s final tier breakdown:
```
By tier:
  - review_required: 4
```
**All four files landed in `review_required`.** Zero `auto`, zero `approval_required`. `preview` and `execute` afterward correctly reflect this (nothing eligible to file), but the net result of running the CLI's flagship command against a realistic folder, exactly as documented, is that nothing is ever auto-filed and nothing is ever even offered for approval — every file needs the same manual attention it would have needed with no tool at all.

**Pass/Fail criteria:** PASS on mechanical correctness — every individual step did exactly what its own design says it should do, including honestly reporting the fallback rate in real time. **FAIL on product outcome** — the advertised workflow, run exactly as instructed from a terminal, cannot reach its own stated goal (auto-filing, or even a real approval queue) for any file whose category isn't deterministically inferable from raw bytes alone. Logged as Finding C1-PAT-2, the most significant finding in this PAT.

---

## Scenario 4 — Duplicate files

**Preconditions:** Same folder as Scenario 3 (contains one exact duplicate pair by construction).

**Steps:** Inspect the `detect_duplicates` step's own output from Scenario 3's `run`.

**Expected behaviour:** The duplicate is identified and routed to the duplicates archive location, not treated as two independent files needing separate approval.

**Expected CLI output:** One `[exact duplicate of <id>]` annotation; the naming step routes the duplicate to `~ARCHIVE~/Duplicates/`.

**Actual result:**
```
- sample_invoice_amazon_copy.pdf [exact duplicate of c9a823d2-89e1-4eaa-bcee-fd60c4e7a5c7]
...
- sample_invoice_amazon_copy.pdf -> ~ARCHIVE~/Duplicates/Unsorted_Sample_Invoice_Amazon_Copy.pdf
```
Correct, and legible without needing to consult any other document. **PASS.**

---

## Scenario 5 — Low-confidence files

**Preconditions:** Same folder as Scenario 3.

**Steps:** Inspect `score_confidence`'s output for the image file, the one record that had a real (non-Unknown) category.

**Expected behaviour:** A confidence score below the `auto` threshold is explained — the user can tell *why* it scored the way it did.

**Actual result:**
```
- sample_product_photo.jpg: 68 (review_required)
```
No hard floor applied (unlike the other three), but no per-deduction breakdown is shown in the terminal either — only the final number and tier. The deduction detail exists (`confidence_breakdown` in the metadata store, and in the action log's `details`) but the CLI itself never surfaces it anywhere a user would look — not in `run`'s own output, not in `preview`, not in `status`. **PASS on tier correctness, FAIL on explainability** — a user cannot answer "why 68 and not higher" from CLI output alone. Logged as Finding C1-PAT-3.

---

## Scenario 6 — `approval_required` files, full approve/edit/reject flow, plus reporting

**Preconditions:** Three hand-constructed, execution-eligible records (disclosed fixture setup, per this plan's Method section): one `approval_required` at confidence 85, one `approval_required` at confidence 88, one `auto` at confidence 97. `destination_root` set to a real, writable, existing directory.

**Steps:** `python -m src.cli preview`; `python -m src.cli execute` with scripted input: an invalid keystroke first, then `a` (approve) for the first record, then `e` (edit) with a new name and a blank (default) destination for the second; `python -m src.cli report`.

**Expected behaviour:** `preview` groups records by tier correctly. `execute` never applies a decision without an explicit, valid keystroke (Engineering Review finding F1). The edited file lands under its edited name; the approved file lands under its suggested name; the `auto` file lands with no prompt at all. `report` produces real output files.

**Actual result — `preview`:**
```
Auto (will execute without further input) — 1: ...
Needs your decision — 2: ...
```
Correct. **`execute`:** the invalid keystroke correctly re-prompted (`Please enter a, e, r, or s.`) with no default applied — F1 confirmed working live, not just in the automated test suite. All three files were genuinely, correctly moved: `Invoice_Acme_2026.pdf` (approved as-suggested), `Invoice_Beta_Renamed.pdf` (the edited name was actually applied), `Invoice_Gamma_2026.pdf` (auto, no prompt shown). Verified by inspecting the real destination folder, not just the printed summary. **The command itself then reported `"Unexpected error: [Errno 1] Operation not permitted: 'plan.json'"` and exited 1** — this occurred during post-completion cleanup (`Runtime/Temp/<batch>/plan.json` removal), after every file had already been correctly and permanently filed. Root cause is very likely this sandbox's own file-deletion restriction (see this plan's Environment note), not a defect in the CLI's execution logic — but the CLI gave no indication that the real work had actually succeeded; a user seeing this exact output would have every reason to believe nothing was filed. **`report`:** produced all four report files with no errors.

**Pass/Fail criteria:** PASS on F1 (verified live) and on filing correctness (verified against the real filesystem, independent of the CLI's own claims). **FAIL on outcome-reporting integrity** — a cleanup-stage failure after full, successful completion is reported identically to a failure that prevented completion. Logged as Finding C1-PAT-4 (the environment-specific trigger is disclosed and not itself scored; the exposed handling gap is).

---

## Scenario 7 — `review_required` files

**Preconditions:** Scenario 3's already-executed state (all four files landed `review_required`).

**Steps:** `python -m src.cli preview`; `python -m src.cli execute`.

**Expected behaviour:** `review_required` files are described clearly as needing manual attention and are never silently touched.

**Actual result:**
```
$ preview
Needs attention (never auto-filed) — 4: ...
$ execute
4 file(s) need attention and will NOT be filed (review_required) — run 'preview' for details.
...
Skipped (review_required or no decision yet): 4
```
Clear, correctly worded, correctly zero side effects. **PASS.**

---

## Scenario 8 — Misconfigured `destination_root`

**Preconditions:** `destination_root` set to a path that does not exist on disk (`/tmp/does_not_exist_at_all`). One or more eligible records present.

**Steps:** `python -m src.cli execute`.

**Expected behaviour:** A clear, actionable message identifying the misconfiguration and how to fix it.

**Actual result:**
```
$ execute
4 file(s) need attention and will NOT be filed (review_required) — run 'preview' for details.
Executed batch ... (4 eligible file(s)):
By tier:
  - review_required: 4
Executed: 0
Failed:    4
```
The real, accurate explanation — `"Batch blocked before any file was attempted: the destination library root '/tmp/does_not_exist_at_all' does not exist."` — **exists only in `Runtime/Logs/action_log.jsonl`**, a file no ordinary user would think to open. The terminal shows only `Failed: 4`, with no pointer to the log, no repeat of the actual reason, and no suggestion to check `config`/`status`.

**Pass/Fail criteria:** FAIL — a fully diagnosable, already-known-and-logged configuration error is surfaced to the user as an unexplained failure count. Logged as Finding C1-PAT-5 — the single highest-value fix identified in this PAT (a real, precise, already-written error message exists; it simply never reaches the terminal).

---

## Scenario 9 — Recovery and Undo after a misconfigured run is fixed

**Preconditions:** Continuing directly from Scenario 8 — the same batch, already logged as blocked/"Failed."

**Steps:** Correct `destination_root` to a real, writable directory; `python -m src.cli execute` again (same batch, no new scan); observe.

**Expected behaviour:** Once the real problem is fixed, re-running should reflect the corrected, current state.

**Actual result:** The second `execute` call **still reported `Failed: 4`**, even though `destination_root` was now valid, because the batch's action-log history from the first (blocked) attempt was still present and was re-counted alongside (in this case, in place of) the current run's true outcome. A completely fresh batch (new `scan`/`run`, never previously blocked) correctly reports `Skipped (review_required or no decision yet): 4` in the equivalent situation (Scenario 7) — confirming the tier-gate logic itself is correct, and the issue is specific to summarizing a *retried* batch.

Separately, `undo --last` was verified against Scenario 6's real, successfully-executed batch: correctly resolved the most recent `batch_id` without requiring the user to know or look it up, correctly reported all three outcomes as `undone`, and — verified directly against the filesystem, not just the printed summary — genuinely restored all three files to their original location.

**Pass/Fail criteria:** `undo --last` — PASS, fully verified. Retry-after-fix reporting — FAIL, logged as Finding C1-PAT-6 (related to, but distinct from, C1-PAT-5: this is about a *second* run's summary being contaminated by a *first* run's history, not about the first run's own message).

---

## Scenario 10 — Missing configuration during `execute` (fresh install, never configured, real records present)

**Preconditions:** Execution-eligible records exist (hand-constructed, per Method), `destination_root` still `null` (never configured at all, not merely wrong).

**Steps:** `python -m src.cli execute`.

**Expected behaviour:** Same class of clear, actionable message as Scenario 8.

**Actual result:** Identical shape to Scenario 8 — `Failed: N` in the terminal, the real reason (`"the destination library root is unset."`) only in the action log. Same finding, same fix (C1-PAT-5) covers both.

**Pass/Fail criteria:** FAIL, same root cause as Scenario 8 — not double-counted as a separate finding.

---

## Scenario 11 — Invalid command usage

**Preconditions:** Any state.

**Steps:** `python -m src.cli frobnicate`; `python -m src.cli undo` (no argument); `python -m src.cli undo <id> --last` (both); `python -m src.cli scan --foo` (unknown option on a real subcommand); `python -m src.cli execute --help`.

**Expected behaviour:** Clear "you made a usage mistake" messaging, distinct in tone from a real error, with the correct usage shown; exit code 2 throughout (distinct from 1, per the CLI's own documented exit-code scheme).

**Actual result:**
```
$ frobnicate
... error: argument command: invalid choice: 'frobnicate' (choose from 'scan', 'run', ...)   EXIT: 2
$ undo
... error: one of the arguments batch_id --last is required                                   EXIT: 2
$ undo abc --last
... error: argument batch_id: not allowed with argument --last                                EXIT: 2
$ scan --foo
usage: python -m src.cli [-h] {scan,run,preview,execute,undo,report,status,version,config} ...
... error: unrecognized arguments: --foo                                                       EXIT: 2
```
The `frobnicate`/`undo` cases are excellent — clear, correct, exit 2. **`scan --foo`'s error shows the *top-level* usage line**, not `scan`'s own — a user who made a mistake specific to `scan` is shown the full command list instead of `scan`'s own (empty) option list, which would have been more directly useful. `execute --help` produces complete, accurate, well-organized help.

**Pass/Fail criteria:** PASS overall (every invalid usage is caught, explained, and exits 2 — no crash, no silent wrong behavior). The `scan --foo` usage-string mismatch is a real but minor rough edge, logged as Finding C1-PAT-7 (Low).

---

## Scenario 12 — Non-interactive execution (scripted/Scheduled context)

**Preconditions:** One `approval_required`-tier record present, `destination_root` valid. This scenario specifically targets the project's own documented "Scheduled" execution mode (`README.md`: "same logic as Manual, triggered on a timer... instead of a request") — a context with no human present to type at a prompt.

**Steps:** `python -m src.cli execute < /dev/null` (stdin closed, simulating any non-interactive invocation — cron, a script, an SSH command with no PTY); then the same, with `--yes` added.

**Expected behaviour:** Either the CLI detects a non-interactive context and behaves sensibly (e.g. a clear message directing the operator to `--yes`), or, at minimum, the documented `--yes` escape hatch works cleanly.

**Actual result:**
```
$ execute < /dev/null
[1 of 1] eof-1  Invoice_Delta.pdf
          -> Finance/Invoice_Delta.pdf   (confidence 85, approval_required)
Approve as suggested / Edit / Reject / Skip remaining?  [a/e/r/s]: Unexpected error: EOF when reading a line
EXIT: 1
```
No detection, no guidance — a raw Python `EOFError` message, framed identically to an internal bug. `execute --yes < /dev/null` correctly avoided the prompt entirely (as designed), though it then hit the same cleanup-stage issue already disclosed in Scenario 6/Finding C1-PAT-4.

**Pass/Fail criteria:** FAIL — this project explicitly advertises Scheduled/unattended operation as a supported mode, and the most natural way to invoke `execute` from that context (without already knowing to add `--yes`) crashes with a low-level, unexplained error. Logged as Finding C1-PAT-8 — High severity given the direct conflict with an already-documented supported use case.

---

## Summary

| # | Scenario | Verdict |
|---|---|---|
| 1 | Brand-new installation, first command | PASS |
| 2 | Empty Downloads folder / missing configuration | FAIL (framing) |
| 3 | Mixed Downloads folder, full workflow | PASS (mechanics) / FAIL (product outcome) |
| 4 | Duplicate files | PASS |
| 5 | Low-confidence files | PASS (tier) / FAIL (explainability) |
| 6 | `approval_required` approve/edit/reject + reporting | PASS (correctness, F1) / FAIL (outcome reporting) |
| 7 | `review_required` files | PASS |
| 8 | Misconfigured `destination_root` | FAIL |
| 9 | Recovery + Undo | PASS (undo) / FAIL (retry reporting) |
| 10 | Missing configuration during `execute` | FAIL (same cause as 8) |
| 11 | Invalid command usage | PASS (minor rough edge) |
| 12 | Non-interactive / Scheduled execution | FAIL |

Every failure above is carried into the **Product Acceptance Report** (`Build-out/09 CLI & Product Interface/C1 Product Acceptance Report.md`) as a classified, numbered finding (C1-PAT-1 through C1-PAT-8), together with the command-by-command UX review the same task requires. No repository file was modified in the course of this PAT — every command above ran against an isolated sandbox copy.
