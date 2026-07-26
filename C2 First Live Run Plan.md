# C2 — First Live Run Plan

**Status:** Planning only. **Nothing in this document has been executed. No real file has been touched.** `src/config/sources.yaml` remains unconfigured (`path: null`, `destination_root: null`), and the real `Database/Metadata/metadata_store.json` (`[]`) and `Runtime/Logs/action_log.jsonl` (0 lines) are unchanged — verified by direct read at the time this plan was written, not assumed.
**Role:** Product Validation Lead, per the user's explicit instruction. This document exists to let you decide, with full information, whether and how to authorize C2 — not to talk you into it.
**Scope note:** the user's own last answer already set the default for when this does run: **scan + preview only, no execute**, reviewed before any further step. Everything below is written against that plan, with the full execute path also described for completeness, clearly marked as a separate, later, separately-authorized decision.

---

## 1. What would happen, step by step, if you authorize this

**Step 0 — Configuration (a one-time setup, itself non-destructive).** `python -m src.cli init` would ask for two paths: your real Downloads folder, and a destination folder for organized files. Both get validated (must exist, must be a directory) and written to `src/config/sources.yaml` — a project text file, not your personal data. This step touches nothing outside that one YAML file.

**Step 1 — `scan` (read-only).** Reads the top level only of your configured Downloads folder — **not** subfolders (a deliberate v1 limitation, `Rules/Ignore Rules.md`: "no recursive subfolder scanning"). Records each file's name, size, timestamps, and a content hash into the project's own `Database/Metadata/metadata_store.json`. Nothing in your Downloads folder is renamed, moved, or modified. Files matching ignore patterns (e.g. `.crdownload`, `.DS_Store`, zero-byte files) are skipped, not flagged as errors.

**Step 2 — `run` (classify → extract → detect_duplicates → suggest_naming → score_confidence, all read-only).** Reads file *content* (not just extension) to guess a category, extracts metadata, checks for duplicates/version chains against what's already in the metadata store, suggests a name and destination folder, and computes a confidence score with a full, auditable breakdown (`Rules/Confidence Rules.md`). Still nothing moves. Every one of these steps writes only to the project's own `Database/`, never to your Downloads folder or the destination folder.

**Step 3 — `preview` (read-only).** Shows, without doing anything, what *would* happen: which files would auto-file, which need your approval, which are flagged for manual review and would be left alone. **This is the recommended stopping point for the first run** — you'd read this output before deciding whether to proceed to Step 4 at all.

**Step 4 — `execute` (real, mutating — a separate, later decision, not part of this first pass).** Only if and when you separately authorize it: moves/renames real files according to the tier each one landed in (below). This is the only step that touches your actual filesystem outside the project folder.

**Step 5 — `report` (read-only).** Generates Daily/Weekly Summary and Duplicate/Storage reports into the project's own `Runtime/Reports/` — text describing what happened, doesn't touch your files.

## 2. Safety checks that actually exist (verified against real code, not restated from documentation)

- **Three-tier gate, based on an auditable point score** (`Rules/Confidence Rules.md`): 95–100 → `auto` (files without a prompt); 80–94 → `approval_required` (you approve/edit/reject/skip each one individually — `execute`'s interactive loop has no default; blank or invalid input just re-prompts, never silently approves); below 80 → `review_required`.
- **`review_required` is never executed, unconditionally** — the module contract calls this "the single most safety-critical guarantee this module makes." It's enforced by reading the tier directly off the record at the moment of execution, not trusting an earlier decision, and is specifically tested against a forged approval decision for a `review_required` record to confirm it still refuses.
- **Hard floors override the score** — an unknown category, a near-duplicate/fuzzy match, a multi-document file, a locked/unreadable file, or a corrupted file are all forced to `review_required` (or at best `approval_required` for near-duplicates) regardless of what the point math alone would say.
- **No file is ever permanently deleted, by any code path, including every failure path** — this is stated as an explicit, tested guarantee (G1/I1), not just a design intention. Exact duplicates go to `~ARCHIVE~/Duplicates/`, superseded versions go to `~ARCHIVE~/Old Versions/` — archived, not removed.
- **Real moves use `Path.rename()` only, never copy-then-delete** — there's no window where both a copy and the original exist that a crash could resolve incorrectly, and no separate delete step that could fail independently of the move.
- **A `--yes` flag exists that skips the approval prompts entirely for `approval_required` records** (auto-approving them as suggested). This first run should **not** use `--yes` — the whole point of a first real pass is to actually look at what the system proposes before any of it happens unattended.

## 3. Rollback / undo — what it is, precisely, and its real limitation

`undo <batch_id>` (or `undo --last`) reverses every `move_rename`/`archive_duplicate`/`archive_superseded_version` log entry for that batch, **in reverse-chronological order**, by replaying each one with `from`/`to` swapped. There is no trash folder and no separate backup copy — **the action log entry itself is the undo mechanism.** A record marked `reversible: false` (a narrow, explicit case — a collision-suffixed move, or a move whose original location was inside `~ARCHIVE~/`) is skipped with zero side effects rather than silently attempted, and is surfaced for you to handle by hand.

**The real limitation, stated plainly rather than glossed over:** undo has been unit- and integration-tested, but **has never once been exercised against real, previously-executed content** — this is a still-open item in this project's own backlog (`PROJECT_BACKLOG.md` A2 / `PRODUCT_READINESS_REVIEW.md` H3), and it's the project's own words that call this "the entire justification for trusting `auto`-tier automation... unverified in the one scenario that actually matters." Undo depends entirely on the action log being intact and on your destination folder not having been independently reorganized between execute and undo. It is not a substitute for a real backup.

## 4. What to back up before you ever authorize Step 4 (execute)

Because undo is log-replay, not an independent backup, and because it's never been proven against real files: **before authorizing any real execute run, make an independent copy of your Downloads folder** (Time Machine, a manual copy to an external drive, or even just `cp -R ~/Downloads ~/Downloads-backup-<date>`) that exists completely outside this pipeline's own reach. This is the actual safety net if undo behaves unexpectedly on its first real-world exercise — not a replacement for undo, a backstop underneath it.

## 5. Recommended staged authorization sequence

1. **Authorize Step 0–3 only** (configure, scan, run, preview) — fully read-only, nothing to back up first, nothing irreversible. This alone would already resolve C2's own stated goal ("has this software ever processed a single real file") for the read-only half of the pipeline, and would produce a real preview of what execute *would* do, which you can review at your own pace.
2. **Review the preview output together** — how many files, what categories, what the tier breakdown looks like, whether anything looks obviously wrong (e.g. an unexpected number of `Unknown` categories — a known, disclosed gap, `TECHNICAL_DEBT_REGISTER.md` TD-01, since there's no autonomous classification provider yet and every judgment-dependent file needs a live decision).
3. **Only then, separately, decide whether to authorize Step 4 (execute)** — after a real backup exists, ideally starting with a small, low-stakes subset of what `auto`/`approval_required` produced rather than the full batch, given undo's own untested status against real content.
4. **Try `undo` for real, on at least one executed file, before considering the run "validated."** This is the only way A2/H3 (undo against real content) ever gets closed, and this run is the first real opportunity to do it.

## 6. Known, disclosed limitations worth knowing before you look at real output

- **No autonomous classification provider (TD-01).** Any file that needs real judgment (most ambiguous documents, screenshots, anything not deterministically inferable from raw bytes) needs a live decision in this session to classify correctly; without one, it falls back to `Unknown`, which routes to `review_required`. Previous real-world testing runs (documented in this project's own validation records) found the *majority* of a realistic folder landing in `review_required` for exactly this reason — a real first run may look similar, and that's expected behavior, not a bug.
- **Two historical classification bugs (PT-002, screenshot false-positives; PT-003, false-positive version-chain grouping) were found in earlier real-world testing and have since been fixed and re-validated** — but only against two prior real-world datasets, not this specific real folder.
- **The CLI has known, disclosed UX rough edges** (from C1's and H5's own Product Acceptance Tests) — a blocked/failed batch's precise reason can be buried in the log rather than the terminal (TD-38/TD-39), and a few wording inconsistencies exist. None of these affect what actually happens to your files, only how clearly it's explained back to you in the terminal.

## 7. Pre-authorization checklist

Before you say "go" on even Step 0–3:

- [ ] You've decided which real folder is the source (your actual `~/Downloads`, or a different real folder).
- [ ] You've decided (or want me to create) a real destination folder for organized files.
- [ ] You understand Step 0–3 is fully read-only and reversible by definition (nothing has moved).
- [ ] You understand Step 4 (execute) is a separate, later, explicitly-authorized decision — not part of this first pass.

Before you separately say "go" on Step 4 (execute), later:

- [ ] An independent backup of the real source folder exists, outside this pipeline's reach.
- [ ] You've reviewed the actual `preview` output from Step 3 and it looks reasonable.
- [ ] You're planning to test `undo` on at least one real executed file as part of calling this run "validated."
- [ ] You're comfortable that a real folder may produce a lot of `review_required`/`Unknown` results given TD-01 (no autonomous provider) — this is expected, not a failure of the run.

---

**No further action will be taken until you tell me which source/destination folders to use and confirm you want to proceed with Step 0–3 (read-only). Step 4 (execute) requires its own separate go-ahead, later, after you've seen the preview.**
