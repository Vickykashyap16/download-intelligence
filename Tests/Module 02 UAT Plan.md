# Module 02 (Classification) — UAT Plan

Real end-to-end acceptance test of Module 02, run the way an actual user would experience it: a realistic, external, Downloads-style folder scanned by Module 01 and then classified by Module 02 using **live Claude judgment as the real `ClassificationProvider`** — not `FakeClassificationProvider`. This is the one validation step the automated Integration Test Plan (`Tests/Module 02 Integration Test Plan.md`) explicitly could not cover (see its Section 8): whether live judgment actually produces correct categories on real, messy, varied files, not just whether the plumbing between `classify_batch()` → `ClassificationEngine` → provider works.

## Why this has to be live, not scripted

`ClaudeLiveClassifier.classify()` is a documented placeholder — it raises `NotImplementedError` by design, because the real "implementation" of judgment is Claude reasoning live during an agent-driven run, not a function body. Running `python3 -m src.main` as a detached subprocess would correctly (and safely) fall back every text/vision file to `Category.UNKNOWN` — that's the tested, expected behavior (M02-X04), not a bug, but it doesn't tell us anything about judgment *quality*. For this UAT, Claude reads each file that needs a deep pass and constructs the real `ProviderResponse` itself, exactly matching `ClaudeLiveClassifier`'s documented contract — the same thing that happens in a genuine production run.

## Test data

A new, external folder — `/tmp/uat_m02_downloads`, outside the project, not preserved after the run (ephemeral sandbox path, same convention as Module 01's UAT) — built to look like a real user's Downloads folder: 18 entries, deliberately mixing easy and hard cases:

| File | What it's really testing |
|---|---|
| `Amazon_Order_Invoice_2026.pdf` | Ordinary invoice, realistic filename |
| `inv_09234_multicur.pdf` | Messier invoice, multi-currency, terse filename |
| `Chase_Statement_June2026.pdf` | Bank statement |
| `NDA_signed_copy.pdf` | Contract |
| `user_manual_v3.txt` | Generic Document (not a business type) |
| `JordanPatel_Resume_2026.docx` | Resume, realistic filename |
| `Screen Shot 2026-07-04 at 3.42.11 PM.png` | Screenshot — realistic macOS filename marker |
| `IMG_4821.jpg` | Product/camera-style photo filename, no marker |
| `product_demo_final.mp4` | Video — deterministic, no judgment needed |
| `project_files.zip` | Archive — deterministic |
| `SomeApp_Installer.dmg` | Application — deterministic |
| `voice_memo.mp3` | Audio — deterministic |
| `download_error.pdf` | Malformed PDF (garbage bytes, real extension) — extraction failure path |
| `Confidential_Agreement.pdf` | Password-protected PDF — locked path |
| `facture_boulangerie.pdf` | Non-English (French) invoice — language signal + still needs a real category |
| `payment_confirmation.pdf` | Ambiguous invoice/receipt wording — tests judgment on a genuinely unclear case |
| `.DS_Store` | OS junk — should be skipped, never reach Module 02 |
| `movie_download.torrent` | Unsupported extension — should be skipped by Module 01, never reach Module 02 |

## Steps

1. **Module 01 (real scan):** Point at `/tmp/uat_m02_downloads` and run the actual `scan_source()`/`build_ingest_queue()` code (same functions `python3 -m src.main`'s `scan()` calls) against an isolated metadata store/action log so this run doesn't touch the project's real `Database/`/`Runtime/`. Confirm discovered/skipped counts reconcile against the table above (16 discoverable, 2 skipped).
2. **Live classification (real judgment):** For every discovered record that needs a deep pass (every text-bearing file above), Claude reads the file's actual extracted content and decides its real category and signals — the same reasoning a live production run would perform. These live judgments are wired into a `ClassificationProvider` implementation built for this run only (not `FakeClassificationProvider`'s canned-response pattern used in the Integration Test Plan) and passed into the real `classify_batch()`.
3. **Persist and inspect:** Confirm every file's final `category`/`classification_signals` against the "what it's really testing" column above, and that the deterministic files never triggered a provider call.
4. **Archive:** Save `metadata_store.json`, `action_log.jsonl`, a `terminal_output.txt`-equivalent transcript, and a `summary.md` verdict under `Runtime/UAT/Module02_UAT_<timestamp>/`, matching Module 01's UAT convention exactly.

## Expected outcomes

- 16 discovered, 2 skipped (`.DS_Store` → `system_file`, `.torrent` → `unsupported_extension`), matching Module 01's already-validated behavior.
- Every deterministic file (video/archive/application/audio) gets its category with zero provider calls.
- Every text-bearing file gets a real, judgment-based category matching what a person would call it, with the correct signals: `download_error.pdf` → Unknown/`extraction_failed`; `Confidential_Agreement.pdf` → Unknown/`locked=True`; `facture_boulangerie.pdf` → Invoice with `non_english_detected=True`/`detected_language="fr"`; `payment_confirmation.pdf` → a real category with `ambiguous` reflecting genuine judgment about whether it reads more like an invoice or a receipt; `Screen Shot ....png` → Screenshot; `IMG_4821.jpg` → Image or Screenshot depending on what the actual heuristic (not a human) determines, since it has no camera EXIF (same documented limitation as M02-F02).
- No unhandled exception; every file gets a category or a graceful fallback.

## Pass/Fail

Pass if every file's final classification is defensible against its real content when read directly, every signal set matches what's actually true about that file, and the run completes with no unhandled exception. A judgment call that a reasonable person could see differently (e.g. the ambiguous receipt/invoice) is not a failure by itself — what matters is that `ambiguous`/`multi_document_detected` signals are set accurately so Module 06 (Confidence & Review) can act on them later, not that every call is unanimous.
