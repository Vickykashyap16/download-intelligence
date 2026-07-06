# Module 03 (Metadata Extraction) — Integration Test Plan

Validates the complete interaction between `src/pipeline/watch_ingest.py` (Module 01), `src/pipeline/classification.py` (Module 02), and `src/pipeline/metadata.py` (Module 03) — real files, real batches, run through `scan_source()` → `classify_batch()` → `extract_metadata_batch()` end-to-end — against `Build-out/03 Metadata Extraction/Module 03 Design.md` (frozen), both design reviews, the Module 01/02 Module Contracts, `Rules/*`, and the implementation audit (`Module 03 Implementation Audit.md`), before Module 03 is allowed to proceed to UAT.

Existing unit tests (`src/pipeline/test_metadata.py`, 57 passing; `src/core/test_archive.py`, `src/core/test_media.py`, 11 passing) already cover Module 03's own functions and Engine decision branches in isolation. This plan is the complementary **integration-level** pass: real files from `Samples/`/`Tests/`, real three-module batches, a routing fake provider standing in for live Claude judgment exactly as the design's Test Strategy (§20) specifies, and real pass/fail results — not just asserted in pytest in isolation from Modules 01/02.

**Datasets used:** `Samples/*` (Invoices, Documents, Images, Videos — reused unchanged), `Tests/Small Batch/`, `Tests/Mixed Downloads/`, `Tests/Corrupted Files/`, `Tests/Large Batch/`, `Tests/Module 02 Classification/` (all reused, not rebuilt). **New dataset built for this plan:** `Tests/Module 03 Metadata/` — a real ID3-tagged MP3 and a real untagged MP3 (both genuine audio, generated via `ffmpeg`), a real EXIF-bearing JPEG (genuine camera-style metadata via Pillow), a multi-entry/nested-directory ZIP, a corrupted-but-valid-extension ZIP (to exercise the Module 02/Module 03 boundary specifically), and two realistically-named installer files (`Zoom_6.1.2_Mac.pkg`, `Slack_4.36.140_Win.dmg`) — the categories/fields the design's own §20 flagged as needing real representative fixtures that didn't already exist (a real tagged audio file, a nested archive, realistic installer names).

Test IDs map directly to this plan's 20 required sections: `F` functional, `C` cross-module contract, `MC` metadata correctness, `RO` required/optional validation, `PR` privacy/redaction, `TS` timestamp hierarchy, `DET` deterministic extraction, `AI` AI-assisted extraction, `X` failure, `CORR` corrupted file, `LOCK` locked file, `UNS` unsupported metadata, `MIX` mixed batch, `PERF` performance, `SEC` security, `DB` database, `LOG` logging.

**Because `ClaudeLiveExtractor.extract()`/`ClaudeLiveClassifier.classify()` are documented placeholders** (fulfilled live by Claude during a real agent-driven run, not autonomous code), every case needing a text/vision judgment answer uses a routing fake provider configured with a canned response that mirrors what live Claude judgment would plausibly return for that specific real file. This proves the plumbing (Engine → provider boundary → persistence/logging, and the full Module 01 → 02 → 03 handoff) works correctly end-to-end. It does not, and cannot, validate the *quality* of live Claude's actual judgment calls — that is UAT's job (§20 of the design), not this plan's.

---

## 1. Functional scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-F01 | Full Module01→02→03 chain over a mixed-category real folder | `Tests/Small Batch/` | Every discovered, non-Unknown record ends with a non-empty `extracted_metadata`; nothing crashes across Archive/Application/Video/Audio/Image/Invoice/Resume/Document in one batch. |
| M03-F02 | Invoice deep-pass, real PDF | `Samples/Invoices/sample_invoice_amazon.pdf` | `category == Invoice`; `vendor == "Amazon"`; `amount == 1499.00`. |
| M03-F03 | Resume deep-pass, real DOCX | `Samples/Documents/sample_resume_jordan_patel.docx` | `category == Resume`; `candidate_name == "Jordan Patel"`. |
| M03-F04 | Bank Statement deep-pass, real PDF | `Samples/Documents/sample_bank_statement_chase.pdf` | `category == Bank Statement`; `bank_name == "Chase"`; valid `account_last4` passes through. |
| M03-F05 | Contract + generic Document deep-pass | `sample_contract_nda.pdf`, `sample_generic_document_manual.txt` | Both classify and extract correctly (`counterparty`, `best_guess_title`). |
| M03-F06 | Image capture_date (deterministic) + vision description, real EXIF | `Tests/Module 03 Metadata/photo_with_exif.jpg` | `category == Image` (real camera `Make` tag beats the Screenshot heuristic); `capture_date` from EXIF; `description` from the vision call. |
| M03-F07 | Screenshot vision-only, real PNG | `Samples/Images/sample_screenshot_login_error.png` | `category == Screenshot`; `context_description` populated. |
| M03-F08 | Archive contents_summary, nested directory, real ZIP | `Tests/Module 03 Metadata/richer_archive.zip` | `invoices/` listed once (deduplicated), not once per nested file; `photo.jpg`/`readme.txt` present. |
| M03-F09 | Application filename parsing, realistic installer names | `Zoom_6.1.2_Mac.pkg`, `Slack_4.36.140_Win.dmg` | `app_name`/`version`/`platform` all parsed correctly for both. |
| M03-F10 | Video filename-derived description, real MP4 | `Samples/Videos/sample_product_demo.mp4` | `description` = filename stem; `duration`/`content_date` both `null`. |
| M03-F11 | Audio, real tagged + real untagged MP3 | `Tests/Module 03 Metadata/real_tagged_track.mp3`, `real_untagged_track.mp3` | Tagged file's `track_title`/`artist`/`recording_date` from real ID3 tags; untagged file falls back to filename for `track_title`, `recording_date` stays `null`. |

## 2. Cross-module contract validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-C01 | Module 03 changes only `extracted_metadata` | `Tests/Small Batch/` (full 3-module chain) | Every other `FileRecord` field Module 01/02 populated is byte-identical before/after `extract_metadata_batch()`. |
| M03-C02 | Module 02's `Category.UNKNOWN` records are never attempted | `Tests/Module 02 Classification/password_protected_contract.pdf` | `category == Unknown`, `locked == True`; `extracted_metadata == {}`; no `extract_metadata` log entry. |
| M03-C03 | Module 01's `status == "unreadable"` records are never attempted | Synthetic unreadable record | `category` stays `None`; `extracted_metadata == {}` after both `classify_batch()` and `extract_metadata_batch()`. |
| M03-C04 | `category` survives a real disk round-trip as a real enum | `Samples/Invoices/` (save → `load_metadata_store()` → extract) | Reloaded records' `category` is a real `Category` member, not a string; extraction still proceeds correctly. |

## 3. Metadata correctness

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-MC01 | Closed-taxonomy field dropped end-to-end | Invoice + a provider answer including `"ssn"` | `ssn` absent from `extracted_metadata` and from the raw on-disk store. |
| M03-MC02 | Numeric field type persists correctly through a real save/reload | Invoice `amount` | Reloaded value `== 1499.00`, still a `float`. |
| M03-MC03 | Boolean value rejected end-to-end (implementation audit F1 re-verified) | Invoice, provider returns `vendor: True` | `vendor` is `null`; sibling field (`invoice_date`) unaffected. |

## 4. Required vs. optional metadata validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-RO01 | `extraction_complete` true despite missing optional fields | Invoice, only `vendor`+`invoice_date` returned | Log entry's `extraction_complete == true`; `fields_missing` lists the four optional fields. |
| M03-RO02 | `extraction_complete` false when a required field is missing | Invoice, only `amount` returned | `is_extraction_complete()` and the log entry both `false`. |
| M03-RO03 | A zero-optional-field category's completeness depends only on its required field | `richer_archive.zip` | `optional_fields(Archive) == ()`; completeness `true` once `contents_summary` is found. |

## 5. Privacy / redaction validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-PR01 | Over-long account number redacted end-to-end | Bank Statement, provider returns a 16-digit `account_last4` | `account_last4 == null` in memory *and* on disk; the literal digit string never appears in `metadata_store.json` or `action_log.jsonl`; `redacted_fields == ["account_last4"]`. |
| M03-PR02 | Valid 4-digit value passes through unredacted | Bank Statement, `account_last4: "4321"` | Value preserved; `redacted_fields == []`. |
| M03-PR03 | A field entirely outside the taxonomy (`ssn`, `phone`) never reaches disk | Resume, provider returns extra prohibited fields | Neither key nor value appears anywhere in the raw store file. |

## 6. Timestamp hierarchy validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-TS01 | Real EXIF photo → tier-2 `capture_date` | `photo_with_exif.jpg` | `capture_date` exactly matches the embedded `DateTimeOriginal`. |
| M03-TS02 | No-EXIF photo never substitutes tier-4 | `Samples/Images/sample_product_photo.jpg` | `capture_date` stays `null` even though `modified_at` is trivially available on the same record. |
| M03-TS03 | Real tagged audio → tier-1 `recording_date` | `real_tagged_track.mp3` | `recording_date == "2024-03-01"` (the real embedded tag). |
| M03-TS04 | Real untagged audio never substitutes tier-4 | `real_untagged_track.mp3` | `recording_date` stays `null`. |
| M03-TS05 | Video never has a tier-1/3 source in v1 | `sample_product_demo.mp4` | `content_date`/`duration` both `null`, regardless of `modified_at`'s availability. |

## 7. Deterministic extraction scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-DET01 | Archive never calls the provider | `richer_archive.zip`, provider that raises if called | Extraction succeeds; provider never invoked. |
| M03-DET02 | Application never calls the provider | Both installer fixtures, same raising provider | `app_name` parsed correctly; provider never invoked. |
| M03-DET03 | Audio never calls the provider | `real_tagged_track.mp3`, same raising provider | Real tags read correctly; provider never invoked. |
| M03-DET04 | Video never calls the provider | `sample_product_demo.mp4`, same raising provider | `description` parsed from filename; provider never invoked. |

## 8. AI-assisted extraction scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-AI01 | Text-bearing request shape, real extracted text | `sample_invoice_amazon.pdf` | `mode == "text"`; real extracted text contains "AMAZON"; `fields_requested` == the category's full field set. |
| M03-AI02 | Image-family vision request excludes the deterministic field | `photo_with_exif.jpg` | `mode == "vision"`; `capture_date` never appears in `fields_requested`. |
| M03-AI03 | Scanned/no-text PDF routes to vision, real rendering | Synthetic no-text-but-renderable PDF (via `reportlab`) | `mode == "vision"`; `extracted_text is None`; vision-mode request sent. |

## 9. Failure scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-X01 | Provider unavailable isolated to one file | `Tests/Small Batch/` with a raising provider | Invoice's fields all `null`; sibling deterministic-only file (`archive.zip`) unaffected. |
| M03-X02 | Corrupted archive (valid `.zip` extension) — Module 02 lets it through, Module 03 catches it | `corrupted_looking_archive.zip` | `category == Archive` (Module 02 never opens the file); `contents_summary == null`, `fallback_reason == "extraction_failed"` (Module 03's own catch). |
| M03-X03 | Outer safety net still real defense-in-depth | Monkeypatched unanticipated internal failure | Batch completes; `error` log entry written; no crash. |
| M03-X04 | Real `ClaudeLiveExtractor` placeholder degrades safely | `sample_invoice_amazon.pdf`, no fake | `fallback_used == True`, `fallback_reason == "provider_exception"`; batch completes. |

## 10. Corrupted file scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-CORR01 | Malformed PDF → Module 02 Unknown → Module 03 skips | `Tests/Corrupted Files/malformed_not_a_real.pdf` | `category == Unknown`; no `extract_metadata` entry at all. |
| M03-CORR02 | Truncated image handled without crash | `Tests/Corrupted Files/truncated_mid_write.jpg` | Whatever category Module 02 assigns, Module 03 doesn't crash; only attempts extraction if the category is real. |
| M03-CORR03 | Corrupted-but-valid-extension ZIP (cross-referenced from X02) | `corrupted_looking_archive.zip` | Same result as X02. |
| M03-CORR04 | Zero-byte file never reaches Module 02/03 at all | `Tests/Corrupted Files/zero_byte.pdf` | Skipped by Module 01 (`reason == "zero_byte"`); never appears in Module 02/03's input. |

## 11. Locked file scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-LOCK01 | Password-protected PDF never attempted by Module 03 | `Tests/Module 02 Classification/password_protected_contract.pdf` | `category == Unknown`, `locked == True`; `extracted_metadata == {}`; no log entry. |

## 12. Unsupported metadata scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-UNS01 | Out-of-taxonomy field dropped (cross-ref MC01) | Invoice + `ssn` | Same result as MC01. |
| M03-UNS02 | Boolean value rejected (cross-ref MC03) | Invoice + `vendor: True` | Same result as MC03. |
| M03-UNS03 | A zero-optional-field category never requests an optional field | `richer_archive.zip` | Archive's own provider call count is zero (verified independently of other files in the same batch that do legitimately call the provider). |

## 13. Mixed batch scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-MIX01 | Realistic messy folder, full chain | `Tests/Mixed Downloads/` | Subfolder never recursed into; `.crdownload`/zero-byte/unsupported-extension files never reach Module 02 or 03 at all (confirmed at the Module 01 layer); Resume/Invoice classify and extract correctly alongside the noise. |
| M03-MIX02 | Every category group in one batch, no cross-contamination | `Tests/Small Batch/` | Archive/Invoice/Resume/Video/Audio(corrupted-placeholder) each get their own correct, independent outcome — one file's fallback never leaks into another's. |

## 14. Performance scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-PERF01 | Large-batch throughput baseline | `Tests/Large Batch/` (75 files) | Informational baseline; fails only if the run hangs, errors, or takes unreasonably long. |

## 15. Security scenarios

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-SEC01 | Archive listing never decompresses entry contents | A zip with a corrupted-content (but validly-named) entry | `contents_summary` lists the name correctly; no attempt to read the corrupt content ever occurs. |
| M03-SEC02 | Redacted value never persisted anywhere (cross-ref PR01) | Same as PR01 | Same result. |
| M03-SEC03 | Adversarial field value (quotes/newline/tab) safe in the action log | Screenshot, `context_description` with adversarial characters | Log line parses as valid JSON; value round-trips exactly. |

## 16. Database validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-DB01 | Full round trip, classification + metadata together | `Samples/Invoices/` | Reloaded record has a real `Category` enum and the correct `extracted_metadata`. |
| M03-DB02 | Cumulative store not disturbed by a later, unrelated batch | A pre-seeded earlier record + a new Invoice batch | The earlier record's `extracted_metadata` is untouched; store length reflects both batches. |

## 17. Logging validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M03-LOG01 | Full per-file lifecycle: discover → classify → extract_metadata | `Samples/Invoices/` | Exactly those three actions, in that order, same `file_id`/`batch_id`. |
| M03-LOG02 | `extract_metadata` entry shape complete across every mode | `Tests/Small Batch/` | Every entry has all documented keys; `provider_metadata` present only when a provider was actually called. |
| M03-LOG03 | No `Runtime/Reports/*` writes | `Tests/Small Batch/` | Reports directory never created by Module 03. |

## 18. Regression validation

| ID | Objective | Method | Expected result |
|---|---|---|---|
| M03-REG01 | Full existing unit suite still passes | `pytest src/ -q` | All unit tests pass, no new failures introduced by this integration pass or its new fixtures. |
| M03-REG02 | Module 01/02 unaffected in isolation | `pytest src/pipeline/test_watch_ingest.py src/pipeline/test_classification.py -q` | Same pass count as before Module 03 existed. |
| M03-REG03 | No Module 01/02 source file modified during this pass | File mtime comparison | All Module 01/02 source files' mtimes predate this integration-testing session. |

---

## 19. Expected outputs

For a real batch run through `scan_source()` → `classify_batch()` → `extract_metadata_batch()`, a correct Module 03 integration produces: every record Module 01 discovered and Module 02 assigned a real, non-`Unknown` category gets a fully key-complete `extracted_metadata` dict (every taxonomy field present, each a real value or an honest `null`) and exactly one `extract_metadata` action-log entry; every record Module 02 left at `Category.UNKNOWN`/`None`, or that Module 01 marked `unreadable`, or that Module 01 filtered out before Module 02 ever saw it (unsupported extension, zero-byte, ignored pattern, temporary download, symlink, subfolder) is left completely untouched by Module 03, with no `extract_metadata` log entry; the provider is invoked only for categories with at least one judgment-dependent field, and only for exactly the fields still outstanding after the deterministic pass; no prohibited field, and no redacted value, is ever observable in `extracted_metadata`, `metadata_store.json`, or `action_log.jsonl`; a single file's failure at any layer never aborts the batch; and every field outside `extracted_metadata` that Module 01/02 populated is byte-identical before and after Module 03 runs.

## 20. Pass/fail criteria

Each case above passes only if every assertion in its expected result holds simultaneously against the real implementation — not a partial match. The plan as a whole passes if every executable case passes and the regression suite (§18) shows no new failures. A failure is classified as a genuine implementation defect only if it reproduces against `src/pipeline/metadata.py` (or its Module 01/02 dependencies) directly, independent of the test harness itself — a bug in the test's own fixture routing or assertion is a test-authoring error, corrected in the harness, not counted as a Module 03 defect (see Execution Results below for the four such corrections made during this pass).

---

## Execution Results (run against the real code, 2026-07-06)

All 59 planned cases across sections 1–17 were implemented as real, executable pytest functions and run against the real `src/pipeline/metadata.py`, `src/pipeline/classification.py`, and `src/pipeline/watch_ingest.py`, using isolated `Database`/`Runtime` paths per test so nothing touched the project's real store or logs. Section 18 (Regression) was executed separately via the shell against the project's real unit suite.

**First pass: 55 of 59 executed cases passed; 4 failed.** Every one of the 4 failures was investigated by reproducing it in isolation directly against the Engine/module functions (bypassing the test harness) before concluding anything about the implementation. All 4 were confirmed to be **defects in this plan's own test harness, not in Module 03, Module 02, or Module 01**:

1. **M03-F02 through M03-F05, M03-C02 (initially failing category assignment):** the harness's `RoutingClassificationProvider.classify()` returned a bare `ClassificationResult` instead of the real provider contract's `ProviderResponse(result=..., metadata=...)` wrapper — `ClassificationEngine.classify_file()`'s outer safety net correctly caught the resulting shape mismatch and silently left `category` at its default `None`, which is exactly the resilience behavior Module 02's own design specifies (a single unanticipated failure must never crash the batch). **Fixed in the harness** by wrapping the routed `ClassificationResult` in a real `ProviderResponse`. This also explains why M03-C02 initially pointed at the wrong fixture (`permission_locked.pdf`, an OS-level-unreadable file — Module 01's `status="unreadable"` scenario, already covered by C03) instead of the intended Module-02-decides-Unknown scenario; corrected to use `Tests/Module 02 Classification/password_protected_contract.pdf`.
2. **M03-UNS03:** asserted the *entire* batch's provider-request list was empty, but `Tests/Module 03 Metadata/` also contains a real EXIF photo that legitimately calls the provider for its own judgment field — corrected to scope the assertion to Archive's own request only.
3. **M03-MIX01:** assumed `mystery_file.xyz` would reach `classify_batch()` as `Category.UNKNOWN`. Verified directly that Module 01's real `SUPPORTED_EXTENSIONS` list doesn't include `.xyz` at all, so it's filtered out at the Module 01 layer itself (`reason: "unsupported_extension"`) and never reaches Module 02 or Module 03 in a genuine `scan_source()` run. Corrected the assertion to match this verified, correct behavior.
4. **M03-SEC03:** `next(e for e in log if e["action"] == "extract_metadata")` grabbed the *first* `extract_metadata` entry in the batch (alphabetically, `sample_product_photo.jpg`, which has no canned route and so has an empty `fields_extracted`), not the screenshot entry the test actually meant to check. Corrected to filter for the specific file.

**Re-execution after all four harness corrections: 59 of 59 passed.**

Two additional test-harness adjustments (not defects, not counted above) were needed purely for run-time practicality: Module 01's deliberate `is_stable()` sleep (0.5s per file, real production behavior for detecting in-progress downloads) was monkeypatched to a no-op for this suite only, since dozens of real static fixtures would otherwise make the run take minutes for no diagnostic benefit.

### Regression validation (§18) results

- **M03-REG01:** `pytest src/ -q` → **161/161 passed** (unchanged from before this integration pass; no new fixtures or harness code live under `src/`).
- **M03-REG02:** `pytest src/pipeline/test_watch_ingest.py src/pipeline/test_classification.py -q` → **61/61 passed**, identical to their standalone counts prior to any Module 03 work.
- **M03-REG03:** `ls -la --time-style=full-iso` on every Module 01/02 source file confirmed all modification times predate this integration-testing session (last touched during their own respective implementation/audit work, all at or before 12:37 on 2026-07-06); only `src/pipeline/metadata.py` (Module 03's own file, from the prior audit-remediation pass) is newer. No Module 01/02 source was modified during this pass — consistent with finding zero implementation defects.

### Performance (§14) — measured, not estimated

- **M03-PERF01:** `Tests/Large Batch/` (75 files) through the full classify→extract chain (fake provider, near-zero simulated latency) completed in **0.280 seconds**. Well within the informational baseline; no algorithmic concern.

### Conclusion

Zero implementation defects were found. All 59 integration test cases pass against the real Module 03 implementation and its real Module 01/02 dependencies; the full regression suite (161 unit tests) and the isolated Module 01/02 re-run (61 tests) both pass unchanged; no Module 01/02 source file was touched. Per the standing instruction not to modify Module 03's implementation absent a genuine defect, **no implementation changes were made** — only this plan's own test-harness code was corrected during development, as documented above.

**Module 03 is approved for User Acceptance Testing.**
