# Validation Checklist — Operator Instructions

**Date:** 2026-07-20 · **Status:** Framework design — ready to use once a validation run is approved
**Audience:** This checklist assumes no programming background. If you can use a chat app and follow a numbered list, you can run this. Anywhere this checklist says "ask Claude," it means typing a plain-English request in a normal conversation — never running a command yourself.
**Read first, once:** `REAL_WORLD_VALIDATION_PLAN.md` §1–§3 (skippable if you just want to get started — this checklist repeats everything you actually need to do)

---

## Before you start

- [ ] You have a real Downloads folder (yours, or one you have permission to use) that has **not** been specially cleaned up or prepared for this test. A tidy folder defeats the point — we want to see what really happens.
- [ ] You have some uninterrupted time — a first validation session usually takes 20–40 minutes for a small batch, more for a large one.
- [ ] You understand the one rule that can't be broken: **nothing is ever permanently deleted by this tool, and every action can be undone.** If anything ever seems to violate that, stop immediately and say so — see "If something seems wrong" at the end of this checklist.
- [ ] You've decided whether this is a **Live Validation run** (your real folder, one-time evidence) or a **Benchmark run** (a pre-built test dataset, repeatable). Most first-time operators want Live Validation — read Part A. If you were specifically asked to run the benchmark suite, skip to Part B.

---

## Part A — Live Validation (your real Downloads folder)

### Step 1: Start the session

Tell Claude something like: *"I want to run a real-world validation session on my Downloads folder, following the Real-World Validation Plan."* Claude will confirm which folder you mean and make sure it's pointed at your real Downloads folder, not the project's own test vault.

### Step 2: Do a dry look first (recommended, not required)

Ask Claude to **scan** the folder and show you what it *found* — this step only looks at files, it doesn't move or change anything yet. Take a moment to glance at the list. Does it look like your real Downloads folder? If something looks off (wrong folder, way fewer files than you expected), say so before continuing.

### Step 3: Run the pipeline up through the preview

Ask Claude to process the batch through to the **preview** step — this covers identifying file types, understanding content, pulling out details, checking for duplicates/versions, and suggesting names and folders, but still **stops before anything is actually moved.** Nothing on your computer changes during this step.

### Step 4: Review the batch — this is the most important step

Claude will show you a batch preview: every file, what it thinks the file is, what it wants to rename it to, where it wants to put it, and a confidence tier. For **each file**, decide one of three things:

- **✅ Looks right — approve it.**
- **✏️ Something's off — edit it** (tell Claude the correct category, name, or folder). When you do this, also tell Claude *why* it was wrong, using one of these short labels — this matters, it's how we track patterns, not just individual mistakes:
  `wrong category` · `wrong or missing details extracted` · `wrong filename` · `wrong destination folder` · `this isn't actually a duplicate` · `this actually is a duplicate and it was missed` · `this isn't actually the same document as a different version` · `the confidence tier feels wrong for this file`
- **❌ Reject it** — tell Claude not to file this one at all, and briefly why.

**A note on files marked "auto":** these are the ones the pipeline is confident enough about that it *won't* normally show you before filing them. For this validation session specifically, ask Claude to show you the auto-tier files too, after the fact, so you can double-check them. This is the single most important check in the whole session — an auto-tier file that turns out wrong is a serious finding, not a minor one.

**For duplicates and version chains:** if the pipeline flags two files as duplicates or as different versions of the same document, just confirm: is that actually true? A quick yes or no per flagged pair is enough.

**For a few files per category (not all of them):** spot-check the details the pipeline pulled out (like a vendor name or date) against the real file, just to make sure they're accurate. You don't need to do this for every single file — a handful is enough.

### Step 5: Let approved files move

Once you've reviewed everything, ask Claude to **execute** the approved actions. Files you approved get moved/renamed; anything you rejected or that needed review stays exactly where it was.

### Step 6: Test undo, at least once

Pick one file that was just moved and ask Claude to **undo** that specific action. Confirm the file is back exactly where and as it was before. This step matters even if everything else went perfectly — reversibility is the tool's most important promise, and it needs to be checked directly, not assumed.

### Step 7: Note how it felt to use

Before you move on, jot down (a sentence or two is fine): Did the review step feel manageable, or overwhelming? Was anything confusing? Did you feel like you understood why a file got the tier it did? This isn't graded — it's real signal about the experience, separate from whether the pipeline got things "right."

### Step 8: Wrap up the session

Ask Claude to **generate the reports** (Daily Summary, etc.) and to **archive this validation run's evidence.** Claude will handle saving the results — you don't need to find or move any files yourself.

### Step 9: Repeat, on a different day

One session is a start, not enough evidence on its own. Plan to repeat Steps 1–8 across **at least 3 separate real sessions, spanning at least 2 weeks**, so the evidence reflects real, varied conditions rather than one snapshot. New files will have accumulated naturally between sessions — that's expected and good.

---

## Part B — Benchmark Run (pre-built test dataset)

Use this instead of Part A only when specifically running the repeatable benchmark suite (`BENCHMARK_SPECIFICATION.md`), not for your own real folder.

- [ ] Ask Claude which benchmark scenario(s) to run (there are five: Finance-Heavy, Document Churn, Media-Heavy, Long-Neglected Backlog, Adversarial Mix) — usually "all of them" for a full release comparison.
- [ ] Ask Claude to run the pipeline against each scenario, the same way as Part A Steps 3–6, **except** you don't need to personally judge what's "correct" — each benchmark dataset already has a pre-recorded answer key, and Claude will score the run against it automatically.
- [ ] Ask Claude to record the results in the benchmark results ledger and tell you whether anything regressed compared to the last time this scenario was run.
- [ ] If Claude reports a regression, treat it the same as any other finding — see "If something seems wrong" below.

---

## If something seems wrong

Stop and say so plainly — you don't need the right technical words. In particular, **stop immediately and flag it clearly** if:

- A file seems to be missing, damaged, or its content looks different than before.
- Undo didn't fully restore a file.
- Something got moved or renamed that you never approved.

These three are treated as serious, top-priority issues — everything else (a wrong category, an awkward filename, a confusing report) is useful, ordinary feedback, not an emergency, and gets recorded as a normal finding.

## What happens to what you tell Claude

Everything you note during review gets written into a findings record automatically — you don't need to fill out any form yourself. Claude follows `DATASET_GUIDELINES.md`'s rule of writing down *what happened* (a file's category, its tier, whether it was edited) rather than the actual sensitive content of your files. You never need to read or write raw file content into any report.

## When you're done for now

After your third (or later) session, ask Claude for a summary of how things are looking across all your sessions so far — accuracy, whether anything unsafe happened, and what stood out. That summary is what eventually informs whether the project owner is ready to call this pipeline version proven, per `REAL_WORLD_VALIDATION_PLAN.md` §9 and `VERSION_09_PLAN.md`'s exit criteria — but that decision itself is not yours to make during a validation session; your job is just to use the tool honestly and say what actually happened.
