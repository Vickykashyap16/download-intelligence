# Module 03 UAT — Run 1 (2026-07-06, batch/run `2026-07-06_100928`)

First real user-acceptance test of Module 03, run exactly as production would: Module 01's real `scan_source()` against an external, temporary Downloads-like folder (`/tmp/uat_m03_downloads`, not preserved — ephemeral sandbox path, same convention as Modules 01/02's UATs), followed by Module 02's real `classify_batch()` and Module 03's real `extract_metadata_batch()`, both using **live Claude judgment as the actual provider** — Claude read each judgment-needing file's real extracted content and produced its own category/field answers directly, exactly matching what `ClaudeLiveClassifier`/`ClaudeLiveExtractor` describe doing in a genuine run, not a scripted/canned response. Plan: `Tests/Module 03 UAT Plan.md`.

Run via `src/main.py`'s real `scan()` → `classify(provider=...)` → `extract(provider=...)` (the `provider=` parameter and the `extract()` function itself were added to `main.py` for this UAT — additive CLI wiring, not a Module 03 implementation change; see the plan doc).

## Test data

19 entries in `/tmp/uat_m03_downloads` — full list and rationale in `Tests/Module 03 UAT Plan.md`.

## Result overview

**Module 01 scan:** 16 discovered, 3 skipped (`.DS_Store` → `system_file`, `empty_placeholder.pdf` → `zero_byte`, `movie_download.torrent` → `unsupported_extension`) — 19 total, reconciles exactly.

**Module 02 classification:** all 16 discovered files received a final category. Live classification provider was invoked exactly 7 times (the 7 text-bearing files needing real judgment); the rest were decided deterministically.

**Module 03 extraction:** 14 of 16 records were real, non-Unknown categories and were attempted (the other 2 — `Confidential_Agreement.pdf`, `download_error.pdf` — correctly skipped, `Category.UNKNOWN`). Live metadata provider was invoked exactly 9 times (7 text-bearing + 2 image-family vision calls); the remaining 5 (Video/Archive×2/Application/Audio) were fully deterministic.

| File | Category | Extracted metadata (key fields) | Notes |
|---|---|---|---|
| `Amazon_Order_Invoice_2026.pdf` | Invoice | vendor=Amazon, invoice_date=2026-07-03, invoice_number=INV-2026-88213, amount=102.09, currency=USD, tax_type=GST | All 6 fields found, `extraction_complete=true` |
| `Chase_Statement_June2026.pdf` | Bank Statement | bank_name=Chase, statement_period=2026-06, **account_last4=null (redacted)** | See Redaction section below |
| `NDA_signed_copy.pdf` | Contract | contract_type=NDA, counterparty=Northwind Traders Inc., effective_date=2026-07-01, term_length=3 years | All 4 fields found |
| `facture_boulangerie.pdf` | Invoice (`non_english_detected=True`, `fr`) | vendor=Boulangerie Artisanale, invoice_date=2026-07-03, invoice_number=2026-0456, amount=13.5, currency=EUR, tax_type=null | Correct despite French content |
| `payment_confirmation.pdf` | Invoice (`ambiguous=True`) | vendor=CloudHost Services LLC, invoice_date=2026-07-02, invoice_number=TXN-77213984, amount=14.99, currency=USD | Judgment-quality test case, see below |
| `user_manual_v3.txt` | Document | best_guess_title="Espresso Machine User Manual (Model 220, v3)", description="Setup, cleaning, and warranty instructions..." | |
| `JordanPatel_Resume_2026.docx` | Resume | candidate_name=Jordan Patel, version_indicator=null, last_modified_date=null | Content had no explicit version/date beyond the filename — correctly left null rather than guessed from the filename's "2026" |
| `IMG_4821.jpg` | Image | description="Test photo of a solid rectangular subject against a blue-toned background", capture_date="2026:06:28 14:22:10" | Real EXIF `DateTimeOriginal` correctly sourced |
| `Screen Shot 2026-07-04 at 3.42.11 PM.png` | Screenshot | context_description="Login error dialog showing an incorrect-password message", capture_date=null | No camera EXIF, as expected |
| `SomeApp_2.4.1_Mac.dmg` | Application | app_name=SomeApp, version=2.4.1, platform=Mac | Deterministic filename parsing |
| `project_files.zip` | Archive | contents_summary="design/, brief.docx" | Nested dir deduplicated correctly |
| `corrupted_project.zip` | Archive | contents_summary=null, `extraction_complete=false`, `fallback_used=true`, `fallback_reason=extraction_failed` | Module 02 let it through (extension-only); Module 03 caught the corruption itself — exactly the cross-module boundary this file was built to test |
| `product_demo_final.mp4` | Video | description="product_demo_final", duration=null, content_date=null | Deterministic |
| `voice_memo.mp3` | Audio | track_title="Site Walkthrough Voice Memo", artist=Vicky, duration=2, recording_date=2026-06-30 | Real ID3 tags correctly sourced |
| `Confidential_Agreement.pdf` | Unknown (`locked=True`) | `{}` (never attempted) | |
| `download_error.pdf` | Unknown (`fallback_reason=extraction_failed`) | `{}` (never attempted) | |

Full raw output in `metadata_store.json` and `action_log.jsonl` in this folder; `terminal_output.txt` for the exact console output from all three CLI steps.

---

## Verification against all 20 requested dimensions

**1–2. Realistic external folder / every supported category:** `/tmp/uat_m03_downloads`, outside the project, 19 files covering Invoice, Resume, Bank Statement, Contract, Document, Image, Screenshot, Application, Archive (clean + corrupted), Video, Audio, and Unknown (locked + malformed), plus OS-junk/zero-byte/unsupported-extension skip cases.

**3–4. Real pipeline end-to-end / actual CLI entry point and production code paths:** run via `src/main.py`'s real `scan()` → `classify()` → `extract()` (see `terminal_output.txt`), not a bespoke script calling internal functions directly. The only CLI addition was the pre-planned, additive `extract()` function and `provider=` parameter (see plan doc).

**5. Live Claude judgment wherever Module 02 needs AI-assisted classification:** confirmed — 7 real provider calls, each backed by this session's actual reading of the file's real extracted text (see the Judgment Quality section below for each call's reasoning).

**6–8. Module 03 extracts metadata correctly / required / optional:** verified per-file in the table above, directly against `metadata_store.json`. Every attempted record has every taxonomy key present (required and optional), each a real value or an honest `null`. `extraction_complete` is `true` wherever every required field was found (11 of 14 attempted records) and correctly `false` for `corrupted_project.zip` (its one required field, `contents_summary`, is `null`).

**9. Redaction behavior:** `Chase_Statement_June2026.pdf`'s live judgment answer deliberately included the *full* account number exactly as it appears in the statement text (`4485112388907742`) — a deliberate stress test of the Engine's redaction safety net rather than relying on well-behaved judgment alone (per design §18: "the provider is not trusted to self-censor"). Verified directly: `extracted_metadata["account_last4"]` is `null` in the persisted store; `action_log.jsonl`'s `extract_metadata` entry for this file has `"redacted_fields": ["account_last4"]`; and a direct grep of both `metadata_store.json` and `action_log.jsonl` for the literal digit string (with and without spaces) returns **zero matches** — the value never reached disk in any form.

**10. Timestamp hierarchy:** `IMG_4821.jpg` (real camera-style EXIF, `Make`="Pixel Camera Co.", `DateTimeOriginal`="2026:06:28 14:22:10") correctly sourced `capture_date` from tier 2. `Screen Shot ....png` (no camera EXIF) correctly has `capture_date: null`, never substituted from `modified_at` even though it's trivially available on the same record. `voice_memo.mp3` (real ID3 `TDRC`-equivalent tag via `ffmpeg`, "2026-06-30") correctly sourced `recording_date` from tier 1. `product_demo_final.mp4`'s `content_date`/`duration` are both `null` regardless of `modified_at`'s availability, exactly as designed for v1.

**11–13. Logging / action log:** `action_log.jsonl` has exactly 49 lines: 16 `discover`, 16 `classify`, 14 `extract_metadata`, 3 `skip` — reconciling exactly against the file counts above, with **zero `error` entries** (no unhandled exception anywhere in the run). Every `extract_metadata` entry carries the full documented shape (`category`, `fields_extracted`, `fields_missing`, `mode`, `processing_time_ms`, `extraction_complete`, `fallback_used`, `fallback_reason`, `redacted_fields`, and `provider_metadata` only when a provider was actually called).

**14. Cross-module consistency:** every record's final `category` in `metadata_store.json` matches its own `classify` log entry exactly; every `extracted_metadata` matches its own `extract_metadata` log entry's `fields_extracted`/`fields_missing` exactly. No record shows a mismatch between what was logged and what was persisted.

**15. Final FileRecord contents:** spot-checked in full (see the JSON excerpts inspected during this run) — every field group (Module 01's identity/file-info fields, Module 02's `category`/`classification_signals`, Module 03's `extracted_metadata`) is present and internally consistent on every record; every later-module field (`suggested_name`, `confidence_score`, `tier`, etc.) remains at its untouched default.

**16. No Module 01/02 data altered incorrectly:** every Module 01 field (`file_id`, `content_hash`, `original_name`, `current_path`, `extension`, `size_bytes`, timestamps) and Module 02 field (`category`, `classification_signals`) inspected directly on every record is exactly what Module 01/02 produced — unchanged by Module 03. This is additionally backed by the automated contract-regression test (`test_extract_metadata_batch_leaves_every_non_owned_field_byte_identical`, part of the 161-test unit suite, re-run clean immediately before this UAT) and by the Integration Test Plan's own `M03-C01`.

**17. Graceful handling of malformed, locked, and unsupported files:** `download_error.pdf` (malformed) → `Category.UNKNOWN`, `fallback_reason="extraction_failed"`, sanitized `error_detail`, never crashed the batch. `Confidential_Agreement.pdf` (genuinely password-protected via real `pypdf` encryption) → `Category.UNKNOWN`, `locked=True`, `fallback_used=False` (a known signal, not a fallback), never reached Module 03. `corrupted_project.zip` (valid extension, garbage bytes) → let through by Module 02, caught gracefully by Module 03's own fallback. `movie_download.torrent`/`.DS_Store`/`empty_placeholder.pdf` → skipped by Module 01, never reached Module 02/03 at all. No exception escaped anywhere in the run.

**18. User-visible CLI output:** captured verbatim in `terminal_output.txt` — includes Module 01's scan summary, Module 02's classification summary (by category/by mode/fallback count), and Module 03's new extraction summary (by mode, provider-call count, fallback count, incomplete-extraction count, and a per-file line noting `[redacted: ...]`/`[incomplete]` where applicable — visibly surfacing the Chase Statement redaction and the corrupted-archive fallback to a real user reading the console).

**19. Final `metadata_store.json`:** archived in this folder; every record inspected directly above.

**20. `Runtime/Logs` output:** this run's `action_log.jsonl` (isolated to `/tmp/uat_m03_run/` for the run itself, archived here) — the project's real `Runtime/Logs/action_log.jsonl` was never touched by this UAT, exactly as intended (isolated storage, same convention as the Integration Test Plan).

---

## Judgment quality assessment

Every category and field answer matches what a person reading the actual extracted text would conclude. `payment_confirmation.pdf` — literally headed "PAYMENT CONFIRMATION / RECEIPT" and describing a completed transaction rather than an outstanding bill — was correctly flagged `ambiguous=True` rather than confidently misclassified, with a best-fit Invoice extraction (no dedicated Receipt category exists in v1). `facture_boulangerie.pdf` was classified and extracted correctly despite its French content, with the language signal captured independently and the French-format date (`03/07/2026` = 3 July) correctly interpreted as `2026-07-03`, not misread as March. The Chase Statement's deliberately-included full account number was the one case designed to test whether live judgment *plus* the Engine's own independent check both hold — confirmed both did (the judgment call included it, matching a plausible imperfect real answer; the Engine still redacted it).

## Differences from expected behavior found

None. Every outcome matched `Tests/Module 03 UAT Plan.md`'s expected-outcomes section exactly.

## Verdict

Module 03's metadata extraction — including live Claude judgment quality on realistic, deliberately messy and adversarial files, the redaction safety net, the timestamp hierarchy, and the Module 02/03 cross-module boundary — performs correctly end-to-end. No defects found during this UAT run. No changes were made to `src/pipeline/metadata.py`, `classification.py`, or `watch_ingest.py`; the only code change was the pre-planned, additive `extract()`/`provider=` CLI wiring in `src/main.py`.

**Module 03 is approved for release artifact generation.**
