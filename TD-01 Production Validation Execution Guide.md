# TD-01 Production Validation Execution Guide

**Why this exists:** Phase 2 of `TD-01 Production Validation Plan.md` needs a real `ANTHROPIC_API_KEY` to make real calls to the Claude API. That key should never be pasted into this chat — it would sit in the conversation history/logs indefinitely, a real standing risk for a billing-enabled credential. Your own terminal doesn't have that problem: the key lives only in your local shell's environment for the duration of the run. This guide walks you through running Phase 2 locally, then bringing the (privacy-safe, structure-only) results back here for the final report.

**What this does and doesn't do:** the validation script only reads real files and writes to an isolated temp directory plus one small results file under this project's own `Runtime/Validation/`. **It never moves, renames, or modifies anything in your real Downloads folder**, and it never writes to the real `Database/`/`Runtime/Logs/` (verified in Step 5 below). The only real, persistent change it makes is to `src/config/sources.yaml`'s three TD-01 keys — via the sanctioned `provider enable`/`disable` commands only, never by hand-editing that file — and that change is reversed in Step 6.

---

## 1. One-time setup

Open Terminal and go to the project folder:

```bash
cd ~/Desktop/"Download Intelligence"
```

Confirm the `anthropic` SDK is installed (added to `requirements.txt` during TD-01 v0.9):

```bash
pip3 install -r requirements.txt
```

## 2. Set your API key — in this terminal session only

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

This only lives in this one terminal window's environment. It is never written to any file in this project, never logged, and you never need to tell me its value — I only ever need to know whether it's set, which the commands below will confirm without printing it.

## 3. Enable the provider — the sanctioned path

```bash
python3 -m src.cli provider enable
```

You'll see the mandatory disclosure text (what gets sent, that it costs real money) and a confirmation prompt — type `y` to proceed. This command will refuse cleanly (no config change) if `ANTHROPIC_API_KEY` isn't set or if something's wrong with the registry, so if it fails here, nothing has changed and it's safe to stop and tell me what it printed.

Confirm it worked, without ever printing your key:

```bash
python3 -m src.cli provider status
```

You should see consent on and both provider keys set to `claude`.

## 4. Run the validation

```bash
python3 "Tests/Provider Evaluation Harness/run_production_validation.py"
```

It will print the sampled dataset size, then an **estimated cost range** and ask you to confirm before making any real API call — read that number before typing `y`. (Add `-y` to skip the prompt only if you've already reviewed the estimate and are comfortable proceeding unattended.)

This will take a few minutes (dozens of real, sequential API calls — no concurrency, per the plan's rate-limit strategy) and will print a running sense of what's happening only at the end, similar to how `scan()` behaves — that's expected, not a hang.

When it finishes, it prints: actual cost, rate-limited file count, processing time, and the path to a `results.json` file under `Runtime/Validation/<timestamp>/`.

## 5. Verify isolation held

Quick sanity check that nothing touched the real store:

```bash
git status --porcelain Database/ Runtime/Logs/
```

This should print **nothing** (no changes) other than possibly `Runtime/Validation/<new folder>/` itself, which is expected and fine — that's the results file, not the real store.

## 6. Disable the provider and verify rollback

```bash
python3 -m src.cli provider disable
python3 -m src.cli provider status
```

Confirm `status` now shows consent off, back to today's exact default. This is the rollback verification the plan requires — please actually run both commands and note what they printed, not just assume it worked.

## 7. What to send back

1. The full terminal output from Step 4 (the validation script's printed summary — cost, rate-limited count, processing time).
2. The contents of `Runtime/Validation/<timestamp>/results.json` (paste it, or tell me the path and I can read it directly from the project folder). This file contains only structural facts — categories, tiers, confidence scores, field-presence counts, token counts — never raw file content, per this project's own `DATASET_GUIDELINES.md`.
3. Confirmation that Step 5's `git status` came back clean and Step 6's `provider status` showed consent off again.

I'll take it from there and produce the full validation report (pass/fail against S1–S3, Q1–Q4, C1–C2) from those results.

## 8. If something looks wrong

Stop and tell me rather than troubleshooting alone — especially:

- Any error message before the script finishes (paste it verbatim).
- `git status` in Step 5 showing changes to `Database/` or `Runtime/Logs/` (would mean isolation didn't hold — a real, reportable defect, not something to work around).
- `provider status` in Step 6 not showing consent off after running `provider disable`.
- The actual cost coming in noticeably higher than the pre-run estimate.

None of these should happen if the script is working as designed, but per this project's own established discipline (see `Local Scan Execution Guide.md`'s identical section), a first real run against a live API is exactly the kind of thing that surfaces something the sandboxed testing here couldn't — better to stop and report than to guess.
