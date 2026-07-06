# Module 02 (Classification) — Integration Test Plan

Validates `src/pipeline/classification.py` (`classify_by_extension`, `needs_screenshot_split`, `classify_screenshot_or_image`, `is_locked`, `detect_non_english`, `ClassificationEngine`, `classify_batch`) and the parts of `src/storage/database.py` it depends on (typed-field (de)serialization), against `Build-out/02 Classification/Module 02 Design.md` (frozen) and `Rules/Classification Rules.md`, before Module 02 is allowed to depend on Module 01 output in a real run and before Module 03 begins.

Existing unit tests (`src/pipeline/test_classification.py`, 44 passing; `src/core/test_pdf.py`, `test_text.py`, `test_images.py`, `test_exif.py`, 24 passing; `src/models/test_classification.py`, 6 passing; `src/storage/test_database.py`, 2 passing) cover individual functions and the Engine's decision branches in isolation, mostly with synthetic `tmp_path` fixtures. This plan is the complementary **integration-level** pass: real files (`Samples/`, `Tests/`), real batches run through `classify_batch()` end-to-end, a `FakeClassificationProvider` standing in for live Claude judgment exactly as the design's Test Strategy (§16) specifies, and real pass/fail results — not just asserted in pytest.

Datasets used: `Samples/*` (canonical single examples, reused from Module 01), `Tests/Small Batch/`, `Tests/Mixed Downloads/`, `Tests/Corrupted Files/`, `Tests/Large Batch/`, `Tests/Edge Cases/` (all reused, not rebuilt — per design §16's "reuse the Module 01 datasets"), plus one new folder built for this plan: `Tests/Module 02 Classification/` (password-protected PDF, non-English/French invoice, ambiguous invoice/receipt, simulated multi-document PDF, scanned/vision-mode PDF, a second resume).

Test IDs: `F` functional, `B` boundary, `E` edge case, `X` failure scenario, `P` performance, `S` security.

Because `ClaudeLiveClassifier.classify()` is a documented placeholder (fulfilled live by Claude during a real agent-driven run, not autonomous code), every case below that needs a text/vision deep-pass answer uses `FakeClassificationProvider` configured with a canned response that mirrors what live Claude judgment would plausibly return for that file — this proves the plumbing (Engine → provider boundary → Module 02 persistence/logging) works correctly end-to-end. It does not, and cannot, validate the *quality* of live Claude's actual judgment calls — that can only be observed during a real UAT run (Task 70), not simulated here.

---

## 1. Functional test cases

### M02-F01 — Deterministic classification across all extension-mapped categories
- **Objective:** Confirm every extension in `_EXTENSION_CATEGORY_MAP` (Application/Archive/Video/Audio) is classified correctly without ever calling the provider.
- **Test data:** `Tests/Small Batch/` (`archive.zip`, `audio_clip.mp3`, `video_clip.mp4`, `installer_mac.dmg`, `installer.pkg`).
- **Steps:** Build `FileRecord`s (`status="discovered"`) for each file, run `classify_batch(records, provider=FakeClassificationProvider())`.
- **Expected result:** Each record's `category` matches its extension's mapped `Category`; `classification_signals` is a default (all-False) `ClassificationSignals`; provider's `received_requests` stays empty for all five.
- **Pass/Fail:** Pass if every category matches exactly and the provider was never invoked.

### M02-F02 — Screenshot vs. Image split on real Samples images
- **Objective:** Confirm the deterministic Screenshot-vs-Image heuristic produces the right answer on real (not synthetic-in-test) sample files.
- **Test data:** `Samples/Images/sample_screenshot_login_error.png`, `Samples/Images/sample_product_photo.jpg`.
- **Steps:** Run both through `classify_batch()`.
- **Expected result:** The screenshot sample classifies as `Category.SCREENSHOT`. The product photo also classifies as `Category.SCREENSHOT` under the current heuristic — **expected, not a defect** (it's synthetic/Pillow-generated with no camera EXIF, so the "no camera EXIF" OR-condition correctly fires; see `src/pipeline/test_classification.py`'s matching unit test and `KNOWN_LIMITATIONS.md`).
- **Pass/Fail:** Pass if both results match the heuristic's actual documented behavior (not necessarily human intuition).

### M02-F03 — Text deep-pass success: real invoice via simulated Claude judgment
- **Objective:** Confirm a text-bearing PDF with extractable text reaches the provider with the right request shape, and the provider's answer is correctly validated, persisted, and logged.
- **Test data:** `Samples/Invoices/sample_invoice_amazon.pdf`.
- **Steps:** `FakeClassificationProvider` configured to return `category="Invoice"`; run through `classify_batch()`.
- **Expected result:** `record.category == Category.INVOICE`; the provider received a `ClassificationRequest` with `mode == "text"` and non-`None extracted_text`; `classification_signals.no_extractable_text is False`; the `classify` log entry's `details["mode"] == "text"` and `details["provider_metadata"]["provider_name"]` is present.
- **Pass/Fail:** Pass if all of the above hold together.

### M02-F04 — Resume classification (DOCX text extraction) via simulated judgment
- **Objective:** Confirm `.docx` text extraction feeds the provider correctly and a Resume answer round-trips through persistence.
- **Test data:** `Samples/Documents/sample_resume_jordan_patel.docx`, `Tests/Module 02 Classification/resume_alex_rivera.docx`.
- **Steps:** `FakeClassificationProvider` returns `category="Resume"` for both; run through `classify_batch()`.
- **Expected result:** Both records get `category == Category.RESUME`; both provider requests have `mode == "text"` with real extracted text (names/skills present in the text sent).
- **Pass/Fail:** Pass if both files classify correctly and the extracted text is non-empty and plausible.

### M02-F05 — FileRecord field boundary: Module 02 populates its fields only
- **Objective:** Confirm `classify_batch()` writes exactly `category` and `classification_signals`, and leaves every later-module field (`suggested_name`, `confidence_score`, `tier`, `suggested_destination`, `duplicate_of`, `extracted_metadata`, etc.) untouched at its Module-01 default.
- **Test data:** `Tests/Small Batch/invoice.pdf` (reused from Module 01's plan).
- **Steps:** Build the record fresh (Module-01-shaped defaults), run through `classify_batch()` with a fake provider returning `category="Invoice"`, inspect every field.
- **Expected result:** `category` and `classification_signals` are populated; `suggested_name`, `suggested_destination`, `confidence_score`, `tier`, `duplicate_of`, `extracted_metadata` (`{}`), and all other Module 03+ fields remain `None`/default exactly as Module 01 left them.
- **Pass/Fail:** Pass only if the populated/untouched field sets match exactly with no unexpected side effects.

### M02-F06 — Action log entry shape completeness
- **Objective:** Confirm every `classify` action-log entry contains the full detail set the frozen design's logging expansion requires (§4 of the refinement round): category, signals, mode, processing time, fallback fields, provider metadata when applicable.
- **Test data:** One deterministic file (`archive.zip`) and one deep-pass file (`Samples/Invoices/sample_invoice_amazon.pdf`).
- **Steps:** Run both through `classify_batch()`, read back both `classify` log lines.
- **Expected result:** Both entries have `category`, `signals` (a full dict matching `ClassificationSignals` fields), `mode`, `processing_time_ms` (int ≥ 0), `fallback_used` (bool), `fallback_reason` (present, `None` when not used). The deep-pass entry additionally has `provider_metadata` with `provider_name`/`model`; the deterministic entry has no `provider_metadata` key at all (not even `null`).
- **Pass/Fail:** Pass if both entries match this shape exactly.

### M02-F07 — Unreadable (Module 01) records pass through completely untouched
- **Objective:** Confirm a record Module 01 marked `status="unreadable"` is never sent to the Engine and never gets a `classify` log entry.
- **Test data:** A synthetic record with `status="unreadable"` (mirrors `Tests/Corrupted Files/permission_locked.pdf`'s real Module 01 outcome).
- **Steps:** Include this record in a batch alongside normal discovered records; run `classify_batch()`.
- **Expected result:** `record.category is None`, `record.classification_signals is None` (both stay exactly as Module 01 left them — the deliberate None-vs-Unknown distinction, design §11); no log entry for this file_id at all; the other records in the same batch classify normally.
- **Pass/Fail:** Pass if the unreadable record is fully untouched and doesn't affect its batch-mates.

---

## 2. Boundary conditions

### M02-B01 — Password-protected PDF never reaches the provider
- **Objective:** Confirm a locked PDF is recognized deterministically and never triggers a provider call.
- **Test data:** `Tests/Module 02 Classification/password_protected_contract.pdf`.
- **Steps:** Run through `classify_batch()` with a fake provider that would raise if called.
- **Expected result:** `category == Category.UNKNOWN`; `classification_signals.locked is True`; `fallback_used is False` (locked is a known signal, not a fallback — see design §11); provider never invoked.
- **Pass/Fail:** Pass if all three hold and the provider's `received_requests` stays empty.

### M02-B02 — Non-English document signal detection
- **Objective:** Confirm a French-language PDF correctly sets `non_english_detected`/`detected_language` while still reaching the provider for its category answer.
- **Test data:** `Tests/Module 02 Classification/facture_non_anglaise.pdf`.
- **Steps:** `FakeClassificationProvider` returns `category="Invoice"`; run through `classify_batch()`.
- **Expected result:** `classification_signals.non_english_detected is True`; `classification_signals.detected_language == "fr"`; `category == Category.INVOICE` (the language signal doesn't block classification — it's informational only, per design).
- **Pass/Fail:** Pass if both the signal and the category are correct simultaneously.

### M02-B03 — Ambiguous invoice/receipt signal passthrough
- **Objective:** Confirm a provider-reported `ambiguous=True` flows through to `ClassificationSignals.ambiguous` unchanged.
- **Test data:** `Tests/Module 02 Classification/ambiguous_invoice_receipt.pdf`.
- **Steps:** `FakeClassificationProvider` returns `category="Invoice", ambiguous=True`; run through `classify_batch()`.
- **Expected result:** `classification_signals.ambiguous is True`; `category == Category.INVOICE` still assigned (ambiguity is a signal for later confidence scoring, not a reason to withhold a category — design §9/§11).
- **Pass/Fail:** Pass if the signal and category are both set as described.

### M02-B04 — Multi-document signal passthrough
- **Objective:** Confirm a provider-reported `multi_document_detected=True` flows through correctly.
- **Test data:** `Tests/Module 02 Classification/multi_invoice_batch.pdf` (two invoice-like pages in one file).
- **Steps:** `FakeClassificationProvider` returns `category="Invoice", multi_document_detected=True`; run through `classify_batch()`.
- **Expected result:** `classification_signals.multi_document_detected is True`; `category == Category.INVOICE`.
- **Pass/Fail:** Pass if the signal is set and the category is assigned.

### M02-B05 — Vision-mode fallback path for a scanned/image-only PDF
- **Objective:** Confirm a PDF with no extractable text but a renderable page correctly routes to `mode="vision"` and the provider receives a vision-mode request.
- **Test data:** `Tests/Module 02 Classification/scanned_no_text.pdf`.
- **Steps:** `FakeClassificationProvider` returns `category="Document"`; run through `classify_batch()`.
- **Expected result:** `record.category == Category.DOCUMENT`; `classification_signals.no_extractable_text is True`; the log entry's `details["mode"] == "vision"`; the provider's received request has `mode == "vision"` and `extracted_text is None`.
- **Pass/Fail:** Pass if all of the above hold.

### M02-B06 — Large batch classification correctness
- **Objective:** Confirm a batch well beyond typical daily volume classifies every file correctly with no dropped or duplicated records.
- **Test data:** `Tests/Large Batch/` (75 files across 8 extensions — pdf/jpg/png/docx/txt/zip/mp3/mp4). Note: this dataset's `.jpg`/`.png`/some `.pdf` fixtures are synthetic placeholder bytes (random text), not real image/PDF content — inherited from Module 01's dataset, which never needed real content since it only hashes bytes.
- **Steps:** Build discovered records for all 75, run through `classify_batch()` with a fake provider returning a fixed `category="Document"` for any request it receives (text-bearing files only).
- **Expected result:** All 75 records get a non-`None` `category` (a real category or `Category.UNKNOWN` — never left blank); deterministic extensions (zip/mp3/mp4) never reach the provider; no record is skipped or duplicated.
- **Pass/Fail:** Pass if the count and category assignment reconcile exactly across all 75. **First execution found a genuine defect here — see Section 10.**

---

## 3. Edge cases

### M02-E01 — Unicode/emoji filename
- **Objective:** Confirm a file with emoji/Unicode characters in its name classifies normally and logs without corruption.
- **Test data:** `Tests/Edge Cases/invoice_📄_north_star_—_v2.pdf`.
- **Steps:** `FakeClassificationProvider` returns `category="Invoice"`; run through `classify_batch()`.
- **Expected result:** Classifies successfully as `Category.INVOICE` (or `Unknown` if the file has no extractable text — either way, no exception); the action log line parses as valid JSON with the Unicode name preserved wherever it appears.
- **Pass/Fail:** Pass if no exception is raised and the log line is valid JSON.

### M02-E02 — Very long filename
- **Objective:** Confirm a near-filesystem-limit filename doesn't break path handling anywhere in the classification path.
- **Test data:** `Tests/Edge Cases/` 200-character-stem `.txt` file.
- **Steps:** Run through `classify_batch()` with a fake provider.
- **Expected result:** No exception; record gets a `category` (Unknown or a real category depending on content); log entry written successfully.
- **Pass/Fail:** Pass if no exception is raised and a log entry exists.

### M02-E03 — Malformed-but-extension-matching PDF (extraction failure)
- **Objective:** Confirm a `.pdf` file that isn't really a valid PDF structure (Module 01 discovered it fine, since Module 01 only hashes bytes) is handled as `extraction_failed`, not a crash.
- **Test data:** `Tests/Corrupted Files/malformed_not_a_real.pdf`.
- **Steps:** Run through `classify_batch()`.
- **Expected result:** `category == Category.UNKNOWN`; `fallback_used is True`; `fallback_reason == "extraction_failed"`; provider never invoked; batch continues normally for any other files alongside it.
- **Pass/Fail:** Pass if all of the above hold and no exception escapes `classify_batch()`.

### M02-E04 — Unsupported-by-Rules extension recognized by Module 01
- **Objective:** Confirm a file Module 01 discovered (has a real extension) but that Module 02's Rules don't map to any category becomes Unknown without a crash.
- **Test data:** `Tests/Mixed Downloads/mystery_file.xyz`.
- **Steps:** Run through `classify_batch()`.
- **Expected result:** `category == Category.UNKNOWN`; `mode == "deterministic"`; provider never invoked.
- **Pass/Fail:** Pass if the result matches exactly.

---

## 4. Failure scenarios

### M02-X01 — Provider unavailable
- **Objective:** Confirm a provider that raises `ProviderUnavailableError` degrades to Unknown with the correct fallback reason, without aborting the batch.
- **Test data:** `Samples/Invoices/sample_invoice_amazon.pdf`, alongside a normal deterministic file in the same batch.
- **Steps:** `FakeClassificationProvider(raises=ProviderUnavailableError(...))`; run both files through `classify_batch()`.
- **Expected result:** The invoice's `category == Category.UNKNOWN`, `fallback_used is True`, `fallback_reason == "provider_exception"`; the deterministic file in the same batch still classifies correctly (the failure is isolated to the one file that needed the provider).
- **Pass/Fail:** Pass if both files' outcomes are correct.

### M02-X02 — Provider returns an unrecognized category string
- **Objective:** Confirm the Engine's validation boundary correctly rejects a nonsense category and falls back rather than persisting garbage into `FileRecord.category`.
- **Test data:** `Samples/Invoices/sample_invoice_messy_multicurrency.pdf`.
- **Steps:** `FakeClassificationProvider` returns `category="TotallyMadeUpCategory"`; run through `classify_batch()`.
- **Expected result:** `category == Category.UNKNOWN`; `fallback_used is True`; `fallback_reason == "invalid_response"`.
- **Pass/Fail:** Pass if the invalid string never reaches persistence as a real category.

### M02-X03 — File vanishes between Module 01's scan and Module 02 running
- **Objective:** Confirm one file's unexpected failure never aborts the whole batch.
- **Test data:** A record pointing at a path that doesn't exist (simulating deletion after Module 01's scan), alongside a normal file.
- **Steps:** Run both through `classify_batch()`.
- **Expected result (as fixed — see Section 10):** The vanished file degrades gracefully to `Category.UNKNOWN` with `fallback_reason == "unreadable_content"` and a real `classify` log entry (not just an `error` entry) — `ClassificationEngine` now wraps the image-split path the same way it already wrapped the text-bearing path. The normal file in the same batch still classifies correctly.
- **Pass/Fail:** Pass if the batch completes, the vanished file gets a graceful fallback classification, and the healthy file's result is unaffected.
- **X03b (added after the fix):** confirm the outer safety net in `classify_batch()` is still real defense-in-depth, not dead code, by forcing a failure the Engine could never anticipate (an internal routing function raising) — expect an `error` log entry and no crash.

### M02-X04 — Misconfigured run with the real ClaudeLiveClassifier placeholder
- **Objective:** Confirm that if `classify_batch()` is ever invoked outside a live Claude-driven session (so `ClaudeLiveClassifier`'s placeholder actually executes as code), the system degrades safely to Unknown for every text/vision file rather than crashing the run.
- **Test data:** `Samples/Invoices/sample_invoice_amazon.pdf` plus one deterministic file, using the real `ClaudeLiveClassifier()` (no fake).
- **Steps:** Run both through `classify_batch()` with the default provider.
- **Expected result:** The invoice falls back to `Category.UNKNOWN` with `fallback_reason == "provider_exception"`; the deterministic file still classifies correctly; no exception escapes.
- **Pass/Fail:** Pass if the batch completes safely and only the provider-dependent file is affected — this is the expected, by-design behavior when running this module outside a live session (see `src/main.py`'s `classify()` docstring), not a defect.

---

## 5. Performance tests

### M02-P01 — Large batch classification timing
- **Objective:** Get a baseline for classification throughput at a volume well above typical daily Downloads usage, isolating Module 02's own overhead from any real network/API latency (which doesn't exist in v1 — `ClaudeLiveClassifier` has none).
- **Test data:** `Tests/Large Batch/` (75 files).
- **Steps:** Time `classify_batch()` end-to-end with `FakeClassificationProvider` (near-zero simulated latency) against an isolated metadata store/action log.
- **Expected result:** Completes in well under a few seconds at this volume — no per-file sleep exists in Module 02 (unlike Module 01's deliberate stability-check delay), so throughput should be dominated by PDF/DOCX parsing cost, not artificial waits.
- **Pass/Fail:** Informational baseline — fail only if the run hangs, errors, or takes an unreasonable amount of time (e.g. >30s) for 75 files, which would indicate a real algorithmic problem (e.g. repeated file re-reads) worth flagging.
- **Known caveat:** This measures Module 02's own code path only. A real run's actual wall-clock time is dominated by how long live Claude judgment takes per file, which cannot be measured here — that's a UAT-level observation (Task 70), not a unit-testable performance number.

---

## 6. Security considerations

### M02-S01 — No code execution risk from file contents
- **Objective:** Confirm nothing in Module 02 executes or interprets file contents in a way that untrusted bytes could exploit.
- **Analysis:** The only content-touching operations are `pdfplumber`/`pypdf` (structured PDF parsing, no macro/JS execution), `python-docx` (structured XML parsing), and `langdetect` (pure statistical text analysis) — no archive extraction, no shelling out, no `eval`/`exec` anywhere in the classification path. `Tests/Corrupted Files/malformed_not_a_real.pdf` (M02-E03) and the encrypted PDF (M02-B01) both exercise malformed/adversarial-shaped input without any code execution risk.
- **Pass/Fail:** Pass — confirmed by code review and by M02-E03/M02-B01 completing without incident.

### M02-S02 — Provider boundary is a real trust boundary, not just documentation
- **Objective:** Confirm a provider can't inject an arbitrary/malicious value into `FileRecord.category` — the Engine's `_validate_category()` must be an actual enforced boundary, not just a design intention.
- **Test data:** Same as M02-X02, plus an adversarial string with unusual characters (e.g. `category="'; DROP TABLE--"`).
- **Steps:** `FakeClassificationProvider` returns the adversarial string as `category`; run through `classify_batch()`.
- **Expected result:** `Category(raw_category)` raises `ValueError` (the string isn't a real enum member), so the Engine falls back to `Category.UNKNOWN` exactly as with any other invalid response — no injection is possible because `Category` is a closed enum, not a free-form field that reaches storage or a query.
- **Pass/Fail:** Pass if the adversarial string is rejected identically to an ordinary invalid string, with no special-case behavior either way.

### M02-S03 — Action log JSON safety for adversarial provider metadata
- **Objective:** Confirm a provider's free-text `reasoning` field (design §17 already flags this as containing potentially sensitive/arbitrary text) can't corrupt `action_log.jsonl` if it contains quotes, newlines, or control characters.
- **Test data:** `FakeClassificationProvider` configured with `ProviderMetadata(reasoning='Contains "quotes", a\nnewline, and \t a tab.')` against `Samples/Invoices/sample_invoice_amazon.pdf`.
- **Steps:** Run through `classify_batch()`, then read back the log line and confirm it parses as valid JSON with the reasoning text intact.
- **Expected result:** `json.loads()` succeeds on the log line; `entry["details"]["provider_metadata"]["reasoning"]` equals the original string exactly (Python's `json` module escapes these characters correctly on write).
- **Pass/Fail:** Pass if the line parses and the round-tripped string matches exactly.

---

## 7. Expected outputs summary

For any batch of Module-01-discovered records run through `classify_batch()`, a correct Module 02 run produces:
- Every `status == "discovered"` record gets a `category` (`Category` enum member, never `None`, never a raw string) and a `classification_signals` (`ClassificationSignals`, never `None`).
- Every `status != "discovered"` record (Module 01's `unreadable` files) is left completely untouched — `category` and `classification_signals` both stay `None`.
- Exactly one `classify` action-log entry per successfully-processed file, with the full detail set (category, signals, mode, processing_time_ms, fallback_used, fallback_reason, provider_metadata when applicable) — or one `error` entry for a file that raised unexpectedly (outer safety net).
- The provider is invoked only for text-bearing files that need a deep pass and have extractable content or a renderable page — never for deterministic-extension files, screenshot/image-split files, locked files, or files with genuinely no content.
- No unhandled exception under any single-file failure — a bad file is isolated to its own `error` log entry; the rest of the batch completes.

---

## 8. Scenarios that cannot be fully validated until later modules exist

- **Real live-Claude judgment quality:** Every deep-pass case here uses `FakeClassificationProvider` with a canned answer chosen to match what real judgment would plausibly say. This validates the *plumbing*, not whether live Claude actually gets ambiguous or messy real-world files right — that requires a real UAT run (Task 70) where Claude itself performs the classification live.
- **Confidence-score interplay:** `confidence_score`/`confidence_tier` remain `None` after Module 02 — whether the overall pipeline behaves correctly at the 95/80 tier thresholds depends on Module 06 and can't be exercised here.
- **Naming/destination correctness:** `suggested_name`/`destination_path` are Module 05/06 concerns; this plan only confirms Module 02 leaves them untouched (M02-F05), not that later modules use `category`/`classification_signals` correctly once they exist.
- **Provider-metadata-driven provider comparison:** The design's observability goal (comparing providers over time via `ProviderMetadata`) can't be meaningfully validated with only one provider (`ClaudeLiveClassifier`) in existence — there's nothing to compare against yet.
- **True vision-mode rendering quality:** M02-B05 confirms the deterministic *routing* to vision mode and that a renderable page is required — it does not validate that a real vision-capable judgment call over the rendered image would produce a good answer, since `ClassificationRequest` doesn't carry image bytes to a fake provider in a way that's meaningfully different from the text case (see the design's documented gap on this in Module 02 Design.md).

---

## 9. Gaps identified during this review (not defects — recommendations only)

- **Screenshot heuristic false-positive on synthetic photos** (M02-F02): confirmed, already documented in `src/pipeline/test_classification.py` and flagged for `KNOWN_LIMITATIONS.md` — not re-litigated as a new finding here, just re-confirmed at the integration level.
- **Vision-mode request contract has no image bytes field** (M02-B05 / Section 8): a known, already-documented design gap (see `_extract()`'s docstring in `classification.py` and Module 02 Design.md) — not a defect surfaced by this plan, just re-confirmed still present.
- No other gaps identified going in. Everything else planned above had real test data in place and was ready to execute. (One genuine defect was found *during* execution — see Section 10, not this pre-execution gap list.)

---

## 10. Execution results (run against the real code, 2026-07-06)

Every test case above was executed for real against `src/pipeline/classification.py` and its dependencies (isolated `Database`/`Runtime` paths per run, so nothing touched the project's real store or logs). Full output available in this session's tool history; execution script preserved alongside this plan's supporting artifacts.

**First pass: 25 of 26 executed cases passed; M02-B06 failed.** After investigating and fixing the underlying defect (below), **re-execution: 26 of 26 passed**, plus one additional regression case (X03b) added to confirm the fix didn't remove real defense-in-depth.

| Section | Cases | Result |
|---|---|---|
| Functional (F01–F07) | 7 | 7 PASS |
| Boundary (B01–B06) | 6 | 6 PASS (B06 failed first pass, fixed, re-run PASS) |
| Edge (E01–E04) | 4 | 4 PASS |
| Failure (X01–X04, +X03b) | 5 | 5 PASS |
| Performance (P01) | 1 | measured, see below |
| Security (S01–S03) | 3 | 3 PASS |

Also re-ran the complete unit suite (`pytest src/ -v`) after the fix: **90/90 passing** (89 pre-existing + 1 new: `test_classify_batch_outer_safety_net_still_covers_truly_unanticipated_failures`, replacing the renamed `test_classify_batch_gracefully_falls_back_for_a_vanished_image_file`).

### Defect found and fixed: unwrapped image-read failures in `ClassificationEngine.classify_file()`

**Finding (M02-B06, first execution):** Running the full `Tests/Large Batch/` dataset (75 files) through `classify_batch()` left 20 of 75 files (all the `.jpg`/`.png` fixtures) with `category == None` instead of a real category — each produced an `error` action-log entry (`"cannot identify image file..."`) rather than a `classify` entry. Investigation confirmed the cause: `Tests/Large Batch/`'s image fixtures are synthetic placeholder bytes (random text), not real image content — inherited from Module 01's dataset, which never needed real image bytes since it only hashes files. `ClassificationEngine.classify_file()`'s image-split branch (`classify_screenshot_or_image()`, which opens the file via PIL for dimensions/EXIF) had no try/except around it — unlike the text-bearing branch, which already wrapped `is_locked()`/`_extract()` in a shared try/except. This meant any file that reaches the image-split branch with unreadable/non-image content raises all the way out of `classify_file()`, caught only by `classify_batch()`'s outer safety net — leaving the file completely unclassified rather than gracefully falling back to `Category.UNKNOWN`, unlike every other known failure mode in the Engine.

This is a genuine implementation defect, not a design gap: the frozen design's fallback strategy (§11) intends for the Engine to own graceful degradation for *any* classification failure it can anticipate, with the batch-level catch reserved for truly unanticipated failures. A corrupted or incomplete image download — plausible in a real Downloads folder (a browser crash mid-write, a truncated transfer) — would have hit this exact gap in production.

**Fix applied:** `classify_file()`'s image-split branch now wraps `classify_screenshot_or_image()` in a try/except, mirroring the existing text-bearing pattern. On failure, it returns a graceful `EngineResult` with `category=Category.UNKNOWN`, `fallback_used=True`, `fallback_reason="unreadable_content"` — a small, documented extension of the fallback_reason vocabulary, exactly like `"extraction_failed"` was already flagged as one during implementation. See `src/pipeline/classification.py` (`ClassificationEngine.classify_file()`) and `CHANGELOG.md` (2026-07-06 entry).

**Re-verification:** M02-B06 re-run — all 75 files now get a non-`None` category (real category or `Category.UNKNOWN`), zero `error` log entries for image files. `test_classify_batch_outer_safety_net_still_covers_truly_unanticipated_failures` (new) confirms `classify_batch()`'s outer catch is still real defense-in-depth by forcing a failure the Engine could never anticipate (an internal routing function raising directly) — it still isolates that failure to an `error` log entry without crashing the batch.

### Performance — measured, not estimated
- **M02-P01:** A full run of `Tests/Large Batch/` (75 files) with `FakeClassificationProvider` (near-zero simulated latency) took **0.25 seconds**. Module 02 has no deliberate per-file delay (unlike Module 01's stability-check sleep), so this is dominated purely by PDF/DOCX parsing cost — well within the informational baseline. A real run's actual wall-clock time will be dominated by how long live Claude judgment takes per file, which this baseline can't measure (see Section 8).

### Conclusion
One genuine defect was found and fixed during this integration pass (unwrapped image-read failures in `ClassificationEngine.classify_file()`) — found, root-caused, fixed, and re-verified within this same session, following the same discipline used for Module 01's symlink defect during its validation pass. After the fix, all 26 planned integration cases pass, the full unit suite (90/90) passes, and no further gaps were identified. Module 02's classification logic is ready to proceed to UAT (Task 70).
