# H5 (Configuration Experience) — Product Acceptance Test (PAT) Plan

**Role:** Principal QA Engineer / Product Validation Lead. Not a code review — the repository is treated as a black box; every scenario below was executed as a real user would, from a terminal, reading only what the CLI itself prints. No repository file was modified in the course of this PAT.
**Scope:** `python -m src.cli init` and `python -m src.cli config --set-source`/`--set-destination`, plus the friendly `scan`/`run` messages H5 added for the unconfigured/misconfigured cases.
**Method:** A full copy of the real project was made to an isolated sandbox (`qa_sandbox_h5/repo`, plus two fresh re-copies used later in this PAT to guarantee a genuinely unconfigured starting state), completely separate from both the real mounted project folder and from C1's own PAT sandbox — same isolation discipline as C1's PAT, itself grounded in the Module 07 UAT test-isolation lesson. Commands were run for real, with piped stdin for the interactive wizard and, for the one scenario that specifically requires it, a real pseudo-terminal (Python's `pty` module) so a genuine `SIGINT` could be delivered mid-prompt exactly as a terminal's own Ctrl-C would.
**Date executed:** 2026-07-23.
**Environment note:** this sandbox's mount rejects some deletion/permission operations on already-created directories (`chmod`/`rm`/`rmdir` all returned `Operation not permitted` in several attempts, on directories this session itself had just created) — the same class of environment quirk C1's own PAT disclosed for its sandbox. Two sub-cases below (permission-denied source path; a configured path later removed from disk) could not be freshly, independently reproduced live in this environment as a result. This is disclosed at each affected scenario rather than silently assumed passing; it is not counted as a product defect.

---

## Scenario 1 — First-time user (fresh checkout, no configuration, no documentation)

**Preconditions:** Fresh sandbox copy of the real project. `src/config/sources.yaml` confirmed, by direct read, to start with `path: null` and `destination_root: null` — the actual shipped state, not a synthetic one.

**Steps:** `python -m src.cli init`, answering only the two prompted values (no flags, no prior reading of any documentation file).

**Expected behaviour:** A user with zero context can complete setup end to end from the wizard's own on-screen text alone.

**Actual result:**
```
Downloads Intelligence setup

Downloads source path: <typed path>
Downloads source path set to /.../fake_home/Downloads.

destination_root: <typed path>
destination_root set to /.../fake_home/OrganizedFiles.

Setup complete. Run 'python -m src.cli config' to review, or 'python -m src.cli scan' to get started.
```
Exit code: 0. `src/config/sources.yaml` verified afterward, byte-for-byte: both values written to the correct lines, every other line and comment preserved exactly except the one already-disclosed exception (the stale "filled in at runtime" comment dropped from the `path:` line once a real value exists — confirmed present before, absent after, nothing else on that line changed).

Two real observations, not scored as failures here (carried to the Product Acceptance Report): the second prompt's label is the raw config key `destination_root` rather than a plain-English phrase, inconsistent with the first prompt's "Downloads source path"; and the captured (piped) transcript shows the prompt label and its confirmation running together with no visual gap — traced to this being a non-interactive stdin capture (no terminal echo), not a real interactive-session issue (see Scenario 5).

**Pass/Fail criteria:** PASS if a first-time user can complete setup using only the wizard's own text. **PASS.**

---

## Scenario 2 — Existing user updates source and destination

**Preconditions:** Sandbox already configured (from Scenario 1).

**Steps (2a — via `init`, overwrite path):** `python -m src.cli init` again, confirming replacement (`y`) for both settings with two new paths. **Steps (2b — via flags):** `python -m src.cli config --set-source <new path>` alone.

**Expected behaviour:** Only the two (2a) or one (2b) intended line(s) in `sources.yaml` change; everything else — including the other setting — is untouched.

**Actual result (2a):**
```
Current Downloads source path: /.../fake_home/Downloads
Replace it? [y/n]: y
Downloads source path set to /.../fake_home/NewDownloads.

Current destination_root: /.../fake_home/OrganizedFiles
Replace it? [y/n]: y
destination_root set to /.../fake_home/NewLibrary.
```
Real `diff` of `sources.yaml` before/after showed exactly two changed lines — the `path:` line and the `destination_root:` line — nothing else.

**Actual result (2b):** `config --set-source` printed `Downloads source path set to /.../fake_home/AnotherDownloads.` followed by the full current configuration. Real `diff` showed exactly one changed line (`path:`); `destination_root` (just set in 2a) was untouched.

**Pass/Fail criteria:** PASS if, in both modes, only the intended value(s) change. **PASS**, verified by direct diff both times, not by trusting the CLI's own printed confirmation.

---

## Scenario 3 — Invalid paths

**Preconditions:** Configured sandbox from Scenario 2.

**Steps and actual results, each run for real:**

| Case | Command | Actual result |
|---|---|---|
| Non-existent path, via `init` | `init`, replace-confirmed, then a bad path | `'<path>' does not exist or is not a directory. Try again.` — loops correctly, never accepts the bad value (see Scenario 4 for how this run ended) |
| Non-existent path, via flag | `config --set-source <missing>` | `'<path>' does not exist or is not a directory. Nothing was changed.` Exit 0. Verified: file unchanged. |
| File instead of directory | `config --set-source <a real file>` | Identical message and behavior to the row above — a plain file is correctly rejected, not accepted as a "directory." Exit 0. |
| Permission problems | `config --set-source <chmod 000 dir>` | **Not independently exercised** — this sandbox refused the `chmod 000` needed to construct the case (`Operation not permitted`, this PAT's disclosed environment limitation). Not scored pass or fail; see Product Acceptance Report. |
| Relative path | `config --set-source ../fake_home/RelativeDir` (run from the repo root) | Accepted and correctly resolved to its full absolute path before being written — confirmed by reading the resulting `path:` line, which contains no `..` or relative segment. |
| Spaces | `config --set-source "/.../fake_home/My Downloads"` | Accepted; written and read back correctly, confirmed via `grep`. |
| `#`, `:`, `'`, `"` in the path itself | `config --set-source ".../Down#loads: Archive's \"copy\""` | Accepted; `sources.yaml` shows the value correctly quoted/escaped by PyYAML (`'.../Down#loads: Archive''s "copy"'`); `config`'s own read-back displays the clean, unescaped value; the file re-parses correctly with `yaml.safe_load()` afterward. |
| Unicode + emoji | `config --set-source ".../Téléchargements_日本語_📁"` | Accepted; written, read back, and re-parsed correctly. The raw file stores the value as escaped codepoints (`\xE9`, `日`, `\U0001F4C1`) rather than literal UTF-8 characters — valid, lossless YAML, but not human-legible if the file is opened directly. Not a correctness defect; carried to the Report as a Low finding. |

**Pass/Fail criteria:** PASS if every invalid case is rejected with a clear, actionable message and no partial write, and every valid-but-unusual case (relative/spaces/special characters/unicode) is accepted and written correctly. **PASS** for every case actually exercised; permission-denied is undetermined in this environment, not failed.

---

## Scenario 4 — Recovery

**Preconditions:** Configured sandbox.

**Steps and actual results:**

- **Genuine Ctrl-C (real `SIGINT`, delivered via a real pseudo-terminal, mid-`Replace it? [y/n]` prompt, before any write):** `Aborted. Run 'status' to check the current state.`, exit code 3. `sources.yaml` confirmed byte-identical to before. This is C1's own pre-existing generic `KeyboardInterrupt` handler, unmodified by H5, and it works correctly for `init` with no `init`-specific code needed. Checked, not assumed: `status`'s own output does include a Configuration section, so its suggestion is genuinely useful here, not a mismatched pointer.
- **EOF (stdin closed mid-prompt, e.g. Ctrl-D or a fully non-interactive invocation that runs out of scripted input):** `Unexpected error: EOF when reading a line`, exit code 1 — the same generic, technical framing used for a genuine internal bug, not a friendly, actionable message. See Report finding H5-PAT-3.
- **Invalid input, then successful retry, within one `init` run:** one bad path correctly re-prompted (`Try again.`); the next, valid path was accepted and written; declining (`n`) to replace the second setting correctly left it completely untouched. Real `diff` showed exactly one changed line.
- **Comment/formatting preservation, full run on a genuinely fresh, never-touched copy:** a brand-new sandbox copy's `sources.yaml` was diffed line-by-line against the same file after a complete, successful `init`. Every line was identical except the two intended value lines (and the one disclosed, deliberate comment removal on the `path:` line) — full `diff -u` output captured and reviewed directly, not sampled.

**Pass/Fail criteria:** PASS if aborting never leaves a partial/corrupted write, invalid input never derails the session, and comments/formatting survive. **PASS** on all four sub-cases exercised; the EOF-framing observation is a real quality finding, not a safety failure (no file was ever corrupted or left in an inconsistent state under any recovery path tested).

---

## Scenario 5 — CLI UX review

**Steps:** captured real `--help` output for the top-level parser, `init`, and `config`.

**Findings:**
- Discoverability: `init` and `config`'s new flags both appear directly in top-level `--help`'s command list with accurate one-line descriptions — a user running only `--help` would find the right command without prior knowledge. **Good.**
- `init --help` and `config --help` are both fully self-contained: they state exactly what gets validated, what file gets written, and what happens on a value that's already set — a user could reasonably run either `--help` instead of the command itself and know what to expect. **Good.**
- Zero worked examples in either help text (e.g. no sample invocation with a real-looking path) — consistent with the same gap C1's own PAT already logged for the rest of the CLI (U8); H5 does not close it. **Carried forward, not new.**
- `destination_root` used as a user-facing prompt label instead of a human-readable phrase (first raised in Scenario 1). **Real finding**, confirmed by reading `_cmd_init`'s two `_init_one_setting()` call sites directly: `"Downloads source path"` vs. the literal string `"destination_root"`.
- The prompt/confirmation-text run-together observed in Scenario 1's piped transcript was traced to the capture method, not the design: `input(f"{label}: ")` prints no trailing newline by design (so a real terminal echoes the user's typed answer on the same line), and the following `print(f"{label} set to ...")` begins on the next line only once Enter is pressed. In a genuine interactive terminal session, the user's own keystroke echo separates the two visually; a piped/non-interactive invocation has no such echo, which is what produced the run-together appearance here. **Confirmed non-issue for real interactive use**, not a wording defect.
- Error messages throughout (`does not exist or is not a directory`, `Try again`, `Nothing was changed`) are plain-English, consistent in tone with each other, and consistently actionable — no jargon, no raw exception text on any expected-input path (the one exception is the EOF case, already logged as H5-PAT-3).

**Pass/Fail criteria:** PASS if prompts/help/errors are clear and consistent enough that a user would not need external documentation for the core flows. **PASS**, with the findings above carried to the Report.

---

## Scenario 6 — Verify H5 resolves C1-PAT-1, TD-30, and the first-run onboarding gap

**Steps:** re-ran the exact C1-PAT-1 repro (unconfigured `scan`/`run`) against a genuinely fresh, unconfigured sandbox copy.

**Actual result:**
```
$ python -m src.cli scan
Source 'downloads' has no path set in config/sources.yaml — fill in the real Downloads folder path before scanning
Run 'python -m src.cli init' to configure a Downloads source, or edit src/config/sources.yaml directly.
EXIT: 0
```
Direct comparison against C1-PAT-1's own logged actual result (`"Unexpected error: Source 'downloads' has no path set..."`, exit 1): the `"Unexpected error:"` prefix is gone, the exit code is now 0 (a normal, expected-precondition exit, not a crash-shaped one), and — the specific gap C1-PAT-1 and TD-30 both named — the message now names a concrete next step (`init`) that exists and works, rather than only pointing at hand-editing a YAML file. **C1-PAT-1 is directly resolved, evidenced by this repro, not by re-asserting the Implementation Report's own claim.**

TD-30 ("no settings surface" from the CLI) is resolved by the same evidence as Scenarios 1, 2, and 5: `init` and `config --set-source`/`--set-destination` are real, working, discoverable commands.

The first-run onboarding experience is directly evidenced by Scenario 1: a user with a genuinely fresh checkout completed setup using only the wizard's own printed text, with no documentation file read at any point in this PAT's execution of that scenario.

**Pass/Fail criteria:** PASS if direct, fresh repro evidence (not restated claims) shows all three resolved. **PASS.**

---

## Summary

| # | Scenario | Verdict |
|---|---|---|
| 1 | First-time user | PASS |
| 2 | Existing user updates both settings | PASS |
| 3 | Invalid paths | PASS (permission-denied undetermined — environment limitation) |
| 4 | Recovery | PASS (EOF-framing quality finding, not a safety failure) |
| 5 | CLI UX review | PASS (findings carried forward) |
| 6 | C1-PAT-1 / TD-30 / onboarding resolution | PASS |

Findings H5-PAT-1 through H5-PAT-4 are carried into `H5 Configuration Experience — Product Acceptance Report.md` (this folder's sibling document, `Build-out/09 CLI & Product Interface/`) as classified findings, alongside the final recommendation. No repository file was modified in the course of this PAT.
