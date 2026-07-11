# Module 06 (Confidence & Review) — Integration Test Plan

Validates the complete interaction between `src/pipeline/watch_ingest.py` (Module 01), `src/pipeline/classification.py` (Module 02), `src/pipeline/metadata.py` (Module 03), `src/pipeline/duplicate_detector.py` (Module 04), `src/pipeline/naming.py` (Module 05), and `src/pipeline/confidence.py` (Module 06) — real files, real batches, run through `scan_source()` → `classify_batch()` → `extract_metadata_batch()` → `detect_duplicates_batch()` → `suggest_naming_and_destination_batch()` → `score_confidence_batch()` end-to-end, invoked through the real `src/main.py` CLI functions (`scan()`/`classify()`/`extract()`/`detect_duplicates()`/`suggest_naming()`/`score_confidence()`), against `Build-out/06 Confidence & Review/Module 06 Design.md` (frozen, including the post-freeze `compute_score()` sign correction), the Module 01–05 Module Contracts, `Rules/Confidence Rules.md`, and the fresh Independent Implementation Audit (Module 06 Design Review.md's audit trail, M1–M3 all resolved and re-verified), before Module 06 is allowed to proceed to UAT.

Existing unit tests (`src/pipeline/test_confidence.py`, 53 passing; 350 across the full `src/` suite) already cover Module 06's own functions and every deduction/hard-floor/cap/logging/determinism/idempotency case named in the design's §21 Test Strategy in isolation, using synthetic `FileRecord`s constructed directly. This plan is the complementary **integration-level, black-box** pass: real files from `Tests/`, real six-module batches, routing fake providers standing in for live Claude judgment (Modules 02/03 only — Module 06 itself has no provider, §2) exactly as Module 03/04/05's own Integration Test Plans established as precedent, and real, black-box-inspected persisted output — Module 06 exercised only as a consequence of the real upstream pipeline's real output, never called directly against hand-built in-memory objects (`score_confidence_batch()`/`ConfidenceEngine` are never invoked directly anywhere in this plan's harness — only `main.score_confidence()`), and no pipeline stage skipped or shortcut.

**Datasets used — 13 real files, all reused unchanged from Modules 02/04/05's own `Tests/` fixtures; no new files created for this plan:**
- `Tests/Module 05 Naming/Invoice_Alpha.pdf` — clean invoice, every field present (baseline `auto`-tier case).
- `Tests/Module 05 Naming/Invoice_MissingVendor.pdf` — missing required field + naming fallback (reproduces `Rules/Confidence Rules.md`'s own worked example end-to-end).
- `Tests/Module 02 Classification/ambiguous_invoice_receipt.pdf` — real Module 02 `ambiguous=True` signal.
- `Tests/Module 02 Classification/facture_non_anglaise.pdf` — real Module 02 deterministic `langdetect` non-English signal.
- `Tests/Module 02 Classification/multi_invoice_batch.pdf` — real Module 02 `multi_document_detected=True` signal (hard floor, no deduction).
- `Tests/Module 02 Classification/password_protected_contract.pdf` — real Module 02 deterministic locked-PDF detection (`category` stays `Unknown`, `classification_signals.locked=True` — stacks two hard floors).
- `Tests/Module 02 Classification/scanned_no_text.pdf` — real Module 02 vision-mode / `no_extractable_text=True` signal.
- `Tests/Module 02 Classification/resume_alex_rivera.docx` — missing optional fields + naming fallback stacking to `review_required` via arithmetic alone (no hard floor).
- `Tests/Module 05 Naming/Mystery_File.txt` — `Category.UNKNOWN` (fake-provider-routed), no locked signal — isolates the `unknown_category` hard floor alone.
- `Tests/Duplicate Files/product_photo_v1.jpg` / `product_photo_v2.jpg` — real Module 04 perceptual-hash near-duplicate pair.
- `Tests/Module 04 Duplicates/Contract_v1.pdf` / `Contract_v2.pdf` — real Module 04 version-chain pair, metadata-routed with a reversed `effective_date`-vs-token relationship to reproduce a genuine `date_token_disagreement` (see harness-correction note in Execution Results).

Test IDs map to this plan's sections: `F` functional (confidence/tier/hard-floor outcomes), `LOG` logging, `SER` serialization, `CLI` CLI wiring, `IDEM` CLI-level idempotency, `C` cross-module Module Contract, `DET` determinism, `REG` regression.

**Because `ClaudeLiveClassifier.classify()`/`ClaudeLiveExtractor.extract()` are documented placeholders** (fulfilled live by Claude during a real agent-driven run, not autonomous code), every Module 02/03 judgment call in this plan uses a routing fake provider (`RoutingFakeClassificationProvider`/`RoutingFakeMetadataExtractionProvider`, keyed by filename substring), mirroring Module 03/04/05's own Integration Test Plan precedent exactly. **Module 06 itself has no provider at all (design §2 — fully deterministic, confirmed across four Design Review passes) and needed no fake; it uses its real, unmodified implementation throughout.** This proves the plumbing — the real Module 01→02→03→04→05→06 handoff, Module Contract boundaries, and persisted output — works correctly end-to-end. It does not, and cannot, validate the *quality* of live Claude's classification/extraction judgment — that remains UAT's job, not this plan's, and is out of scope here since Module 06's own behavior does not depend on judgment quality (it only consumes whatever category/signals/fields it's handed, deterministically).

`main.py`'s real `scan()` reads its source folder from `load_source_config()`; `main.load_source_config` is monkeypatched to return the isolated test source folder's path — the same category of test-only isolation as monkeypatching the `Database`/`Runtime` path constants, not a shortcut around any pipeline stage (every line of every CLI function's own real logic still executes against real files).

---

## 1. Functional scenarios (real six-module batch, Run A)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M06-F01 | Clean file, every field present → `auto` tier, zero deductions | `Invoice_Alpha.pdf` | `confidence_breakdown == {}`; `confidence_score == 100`; `tier == "auto"`. |
| M06-F02 | Missing required field + naming fallback reproduces `Rules/Confidence Rules.md`'s own worked example exactly, end-to-end | `Invoice_MissingVendor.pdf` | `confidence_breakdown == {"missing_required_field:vendor": -8, "naming_fallback:vendor": -10}`; `confidence_score == 82`; `tier == "approval_required"`. |
| M06-F03 | Ambiguous-classification deduction, sourced from a real Module 02 signal | `ambiguous_invoice_receipt.pdf` | `confidence_breakdown == {"ambiguous_classification": -15}`; `confidence_score == 85`; `tier == "approval_required"`. |
| M06-F04 | Non-English-content deduction, sourced from a real Module 02 deterministic `langdetect` signal (not fake-provider-supplied) | `facture_non_anglaise.pdf` | `confidence_breakdown == {"non_english_content": -10}`; `confidence_score == 90`. |
| M06-F05 | No-extractable-text deduction, sourced from a real Module 02 vision-mode routing signal | `scanned_no_text.pdf` | `confidence_breakdown == {"no_extractable_text": -30}`; `confidence_score == 70`; `tier == "review_required"`. |
| M06-F06 | Missing optional fields + naming fallback stack to drive `tier` to `review_required` via arithmetic alone, no hard floor involved | `resume_alex_rivera.docx` | `confidence_breakdown` has 2 `missing_optional_field:*` (-2 each) + 2 `naming_fallback:*` (-10 each); `confidence_score == 76`; `tier == "review_required"`. |
| M06-F07 | `version_conflict` deduction, sourced from a real Module 04 date/token-disagreement signal | `Contract_v1.pdf`/`Contract_v2.pdf` | `Contract_v1.pdf` (token-loser, unaffected): `confidence_score == 100`. `Contract_v2.pdf` (where Module 04 detects and records the conflict): `confidence_breakdown == {"version_conflict": -25}`; `confidence_score == 75`; `tier == "review_required"`. |
| M06-F08 | `fuzzy_duplicate` deduction + hard floor, sourced from a real Module 04 perceptual-hash signal — asymmetric by Module 04's own Module Contract (no disclosed side effect on any other record for near-duplicates, only for version chains) | `product_photo_v1.jpg`/`product_photo_v2.jpg` | Only the later-processed record (`product_photo_v2.jpg`) gets `duplicate_signals.fuzzy_duplicate == True`; its `confidence_breakdown` includes `"fuzzy_duplicate": -20` and its `hard_floors_applied` includes `"fuzzy_duplicate"`. `product_photo_v1.jpg` shows neither. |
| M06-F09 | `multi_document_detected` hard floor overrides a decent arithmetic score (no corresponding deduction exists for this rule per `Rules/Confidence Rules.md`) | `multi_invoice_batch.pdf` | Arithmetic score `90` (from an incidental real non-English deduction) would lookup to `approval_required`, but `hard_floors_applied == ["multi_document_detected"]` clamps `tier` to `"review_required"`. |
| M06-F10 | Locked file: Module 02's real, contract-documented outcome for a locked PDF is `category == Category.UNKNOWN` *and* `classification_signals.locked == True` simultaneously — stacks two hard floors in fixed table order | `password_protected_contract.pdf` | `confidence_breakdown == {"locked_file": -40}`; `confidence_score == 60`; `hard_floors_applied == ["unknown_category", "locked_file"]` (table order, M1); `tier == "review_required"`. |
| M06-F11 | `Category.UNKNOWN` in isolation (no locked signal) → `unknown_category` hard floor alone, never a second `corrupted_file` identifier (M2) — and confirms classification-signal-sourced deductions are **not** category-gated (only the required/optional field-taxonomy deductions are, since `Category.UNKNOWN` has no taxonomy entry) | `Mystery_File.txt` | `hard_floors_applied == ["unknown_category"]` exactly; `confidence_breakdown == {"non_english_content": -10}` (a real, incidental Module 02 signal on this record, stacking correctly on top of the hard floor); `confidence_score == 90`; `tier == "review_required"`. |

**Cap enforcement** is not independently re-derived at integration level: this dataset's real category taxonomy tops out at 3 required fields / 4 optional fields per category (`Rules/Confidence Rules.md` cites `Build-out/03 Metadata Extraction/Module 03 Design.md` §7), which cannot reach the −30/−10 caps through genuine missing-field content alone. Cap enforcement (including the exact boundary, and both caps enforced independently) is already exhaustively covered at the unit level (`test_confidence.py`'s `test_capped_field_deductions_*`, `test_required_and_optional_caps_are_independent`, and `test_all_nine_deduction_rules_simultaneously_with_cap_enforcement` — the Implementation Audit's M1 fix) — not re-built here, per Module 04's own `M04-DET02` precedent of citing "not re-built here, see existing unit tests" when integration-level re-derivation would require artificially inflating the taxonomy rather than reflecting real content.

## 2. Logging

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M06-LOG01 | Exactly one `score_confidence` entry per eligible file | All 13 Run-A records | 13 `score_confidence` log entries, one per file. |
| M06-LOG02 | `score_confidence` action-log `details` shape matches Design.md §16 exactly | `Invoice_MissingVendor.pdf`'s log entry | Keys are exactly `confidence_score`, `confidence_breakdown`, `tier`, `hard_floors_applied`, `processing_time_ms` — no `fallback_used`/`provider_metadata` (no Provider, §16). |
| M06-LOG03 | Full six-stage per-file lifecycle, correctly ordered | `Invoice_Alpha.pdf` | `discover` → `classify` → `extract_metadata` → `detect_duplicates_and_versions` → `suggest_naming_and_destination` → `score_confidence`, same `file_id`, in that exact order. |

## 3. Serialization

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M06-SER01 | `confidence_score`/`confidence_breakdown`/`tier` round-trip as real `int`/`dict`/`str` through a genuine disk write/reload, for every record in a real batch | All 13 Run-A records, freshly reloaded via `load_metadata_store()` | Every scored record's three fields have the correct real Python types — never a `dict`/`None` masquerading as the wrong type after a JSON round trip. |
| M06-SER02 | A second, independent reload from disk reproduces byte-identical confidence fields | `Invoice_MissingVendor.pdf`, reloaded fresh a second time | `confidence_breakdown`/`confidence_score` match the first reload exactly. |

## 4. CLI wiring

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M06-CLI01 | Real `main.score_confidence()`'s printed tier-count summary matches the real persisted data exactly | Run A's full 13-file batch | Printed `By tier:` counts (`auto: 2, approval_required: 4, review_required: 7`) match a fresh, independent tally of the real persisted `tier` field across all 13 records. |

## 5. CLI-level idempotency

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M06-IDEM01 | A second real `main.score_confidence()` invocation, no new discoveries | Called again immediately after Run A | Prints `"Nothing to score..."`; zero new `action_log.jsonl` lines. |
| M06-IDEM02 | Every record's confidence fields are unchanged after the second invocation | Same as above | `confidence_score`/`confidence_breakdown`/`tier` identical to their Run-A values for all 13 records. |

## 6. Cross-module Module Contract validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M06-C01 | Module 06 changes only its three owned fields, verified exhaustively (every field programmatically compared, not spot-checked) on real, fully multi-module-populated records | A snapshot of all 13 records taken immediately before `score_confidence()` runs, compared field-by-field against the same 13 records immediately after | Every field except `confidence_score`/`confidence_breakdown`/`tier` is byte-identical before/after, across all 13 real records — not just one hand-picked record. |
| M06-C02 | Confirm Module 06 actually did its job (a control check — otherwise C01 would trivially pass if `score_confidence()` did nothing) | Same snapshot pair | At least one record's `confidence_score` actually changed from its pre-Module-06 default (`None`). |

## 7. Determinism

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M06-DET01 | Real CLI re-run (`main.score_confidence()`, never `score_confidence_batch()` called directly) against the exact same pre-Module-06 state, but with the on-disk record array order fully reversed | The pre-`score_confidence()` snapshot from Run A, written to a fresh isolated store with its JSON array reversed, then scored via a real second `main.score_confidence()` call (Run B) | `confidence_score`/`confidence_breakdown`/`tier`/`hard_floors_applied` byte-identical to Run A for every one of the 13 records, confirming §7's determinism guarantee holds at real CLI/storage-order scale, not just in a synthetic unit-level pair. |

## 8. Regression validation

| ID | Objective | Method | Expected result |
|---|---|---|---|
| M06-REG01 | Full existing unit suite still passes | `pytest src/ -q` | All unit tests pass, no new failures introduced by this integration pass. |
| M06-REG02 | No Module 01–05 source file modified during this pass | `git diff --stat` (content-based, not mtime) | No `pipeline/watch_ingest.py`, `pipeline/classification.py`, `pipeline/metadata.py`, `pipeline/duplicate_detector.py`, or `pipeline/naming.py` change present. |
| M06-REG03 | No Module 06 source file modified during this pass either (zero defects found → no fix needed) | Same `git diff` check | `pipeline/confidence.py` shows only the implementation + Implementation-Audit-driven test additions already applied and independently re-audited before this session began — no new edits. |

---

## 9. Expected outputs

For a real batch run through `scan_source()` → `classify_batch()` → `extract_metadata_batch()` → `detect_duplicates_batch()` → `suggest_naming_and_destination_batch()` → `score_confidence_batch()`, a correct Module 06 integration produces: every `status == "discovered"` record with a real category and a suggested name ends with a real `int` `confidence_score` in `[0, 100]`, a real `dict` `confidence_breakdown` (empty only when genuinely no deduction applied), and a real `tier` string; every deduction traces to an actual upstream Module 02/03/04/05 signal, never a fabricated one; the four hard floors correctly clamp `tier` downward only, in fixed table order, and the "Unknown category"/"Corrupted file" business rules collapse to the single `unknown_category` identifier even when a record also carries an independent, incidental classification-signal deduction on top of the hard floor; a hard floor can override a decent arithmetic score, and can also coexist with an arithmetic score already at or below the floor's own minimum without changing the outcome; the same batch, read from storage in a different on-disk order, always produces byte-identical per-record output through the real CLI; every field outside Module 06's three owned fields is byte-identical before and after Module 06 runs, across the real six-module pipeline; and a second CLI invocation with no new files does nothing and logs nothing.

## 10. Pass / fail criteria

Each case above passes only if every assertion in its expected result holds simultaneously against the real implementation — not a partial match. The plan as a whole passes if every executable case passes and the regression suite (§8) shows no new failures. Per the standing instruction for this integration-testing phase, any genuine implementation or design defect discovered here is stopped on immediately, not auto-fixed, and reported as its own finding using the project's standard severity scale (`Governance/ENGINEERING_STANDARD.md` §14): **Critical** (data loss, irreversible action, or a crash that halts the pipeline), **High** (a core guarantee — determinism, idempotency, Module Contract, or a designed scoring/hard-floor outcome — is violated), **Medium** (a designed behavior is incomplete or a test gap allows a real defect to go undetected), **Low** (a minor correctness or completeness gap with limited blast radius), or **Cosmetic** (documentation/wording only, no behavioral impact) — each with a recommended smallest fix. A failure traced to this plan's own test-harness code (fixture construction, isolation setup, or assertion logic) rather than to `src/pipeline/confidence.py` or its Module 01–05 dependencies is a harness-authoring error, corrected in the harness and disclosed in Execution Results, not counted as a Module 06 finding — the same distinction Module 03/04/05's own Integration Test Plans draw.

---

## Execution Results (run against the real code, 2026-07-11)

All sections above were implemented as a real, executable Python harness (not a permanent pytest file — mirroring Module 03/04/05 Integration Testing's own precedent that only this markdown plan persists) and run against the real `src/pipeline/watch_ingest.py`, `src/pipeline/classification.py`, `src/pipeline/metadata.py`, `src/pipeline/duplicate_detector.py`, `src/pipeline/naming.py`, `src/pipeline/confidence.py`, and the real `src/main.py` CLI functions, using isolated `Database`/`Runtime` paths (monkeypatched module-level path constants pointed at a fresh `/tmp` tree, exactly as Module 04/05's own precedent) so nothing touched the project's real store or logs. `main.load_source_config` was monkeypatched to point at the isolated test source folder, so the real `scan()` function ran unmodified against real files, without editing `src/config/sources.yaml`.

**Run A (primary, 13 files), executed via the real CLI functions in sequence — `main.scan()` → `main.classify(provider=fake_cls)` → `main.extract(provider=fake_meta)` → `main.detect_duplicates()` → `main.suggest_naming()` → `main.score_confidence()`:**

```
Scored 13 file(s):
  - Contract_v1.pdf: 100 (auto)
  - Contract_v2.pdf: 75 (review_required)
  - Invoice_Alpha.pdf: 100 (auto)
  - Invoice_MissingVendor.pdf: 82 (approval_required)
  - Mystery_File.txt: 90 (review_required) [hard floor: unknown_category]
  - ambiguous_invoice_receipt.pdf: 85 (approval_required)
  - facture_non_anglaise.pdf: 90 (approval_required)
  - multi_invoice_batch.pdf: 90 (review_required) [hard floor: multi_document_detected]
  - password_protected_contract.pdf: 60 (review_required) [hard floor: unknown_category, locked_file]
  - product_photo_v1.jpg: 88 (approval_required)
  - product_photo_v2.jpg: 68 (review_required) [hard floor: fuzzy_duplicate]
  - resume_alex_rivera.docx: 76 (review_required)
  - scanned_no_text.pdf: 70 (review_required)

By tier:
  - approval_required: 4
  - auto: 2
  - review_required: 7
```

**22 of 22 planned integration cases passed on final execution.** Two issues surfaced during harness development — **both confirmed to be defects in this plan's own test harness, not in Module 06 or any of Modules 01–05** — following the same reproduce-in-isolation-before-concluding-anything discipline Module 03/04's own Integration Test Plans established:

1. **Initial `Contract_v1.pdf`/`Contract_v2.pdf` construction produced no `version_conflict` at all.** These two files were originally built during Module 04's own Integration Testing with deliberately reversed filesystem mtimes (relative to their filename version tokens) to force a `date_token_disagreement`. Investigated directly: `git checkout` does not preserve original mtimes, so both files now carry near-identical checkout-time mtimes on disk — the mtime-based half of the original engineering was lost. Further investigation (reading `duplicate_detector.py`'s `_determine_rank()`/`best_available_date()` directly) confirmed the real comparison uses `extracted_metadata`'s category-appropriate date field (`effective_date` for Contract) *before* ever falling back to filesystem mtime — so the fake metadata provider's own `effective_date` values, not file mtimes, are what actually needed to disagree with the filename token. **Fixed in the harness** by setting `Contract_v1.pdf`'s fake `effective_date` newer than `Contract_v2.pdf`'s, deliberately reversed against the filename tokens (`v1` < `v2` numerically) — re-execution correctly produced `conflict_type: "date_token_disagreement"` and a real `version_conflict` deduction on `Contract_v2.pdf`, exactly as Module 04's own `M04-F06` precedent describes.
2. **M06-CLI01 initially failed with a hardcoded, stale expected tier-count dict** (`{"auto": 3, ...}`), written before the `Contract_v1.pdf`/`Contract_v2.pdf` fix above changed the real, correct tier distribution. The real printed CLI summary and the real persisted data already agreed with each other throughout — only this plan's own hardcoded assertion was stale. **Fixed in the harness** by updating the expected dict to `{"auto": 2, "approval_required": 4, "review_required": 7}`, matching both the real CLI output and the real persisted data.

**Re-execution after both harness corrections: all 22 planned cases passed**, covering every section of this plan:

- **§1 Functional (F01–F11):** all 9 of Module 06's deduction rules and all 4 hard floors were exercised through real, upstream-produced signals — none fabricated by this harness beyond the routing fake providers' own category/field answers (which stand in only for Modules 02/03's live-judgment layer, never for Module 06's own logic). Two organic, unplanned confirmations worth noting explicitly:
  - **F08** confirmed Module 04's real near-duplicate behavior is *asymmetric* — only `product_photo_v2.jpg` (the later-processed file, per `discovered_at`/`file_id` order) receives `duplicate_signals.fuzzy_duplicate == True`; `product_photo_v1.jpg` never does. This is fully consistent with Module 04's own frozen `MODULE_CONTRACT.md` ("No disclosed side effect on any other record" for near-duplicates — only version-chain relationships get the one documented cross-record side effect, scoped to `version_group_id`/`version_rank` only). Module 06 correctly and faithfully reads whatever Module 04 actually sets, on exactly the record it's set on — no Module 06 defect, and no Module 04 defect relative to its own current contract; noted here only because an earlier Module 04 Integration Test Plan session's prose (`M04-F04`) described the outcome as symmetric ("both records"), which does not match the current, frozen contract text or this session's real, reproduced result.
  - **F11** confirmed a subtle, previously only unit-tested point now holds at real multi-module integration scale: `Category.UNKNOWN` records are excluded from the *required/optional field* deductions (no taxonomy entry, §12) but are **not** exempt from the *classification-signal* deductions (ambiguous/no-extractable-text/non-English/locked) — `Mystery_File.txt` genuinely triggered Module 02's real, deterministic `langdetect` non-English signal on its own real (60-byte) content, and Module 06 correctly stacked that `-10` deduction on top of the `unknown_category` hard floor, exactly as §12/§13 specify.
- **§2 Logging (LOG01–LOG03):** all 13 real `score_confidence` log entries confirmed present with the exact §16 detail shape; `Invoice_Alpha.pdf`'s full six-stage lifecycle confirmed in exact order from the real, persisted `action_log.jsonl`.
- **§3 Serialization (SER01–SER02):** all 13 records, freshly reloaded via `load_metadata_store()` from real on-disk JSON (a genuine save→reload round trip, not an in-memory shortcut), confirmed to carry real `int`/`dict`/`str` types; a second independent reload reproduced byte-identical values.
- **§4 CLI wiring (CLI01):** real `main.score_confidence()`'s printed tier-count summary matched the real persisted data exactly (see harness-correction #2 above).
- **§5 CLI-level idempotency (IDEM01–IDEM02):** a second real `main.score_confidence()` invocation printed `"Nothing to score..."`, added zero new action-log lines, and left every record's confidence fields unchanged.
- **§6 Module Contract (C01–C02):** all 13 real, fully multi-module-populated records' non-owned fields (every field, programmatically compared via a full pre/post snapshot diff — not spot-checked, not limited to one hand-picked record) confirmed byte-identical before/after Module 06 ran; confirmed Module 06 actually changed the three fields it owns on at least one record, ruling out a trivial pass.
- **§7 Determinism (DET01):** the real pre-Module-06 state was written to a fresh isolated store with its on-disk record order fully reversed, then scored via a second real `main.score_confidence()` call — every one of the 13 records' `confidence_score`/`confidence_breakdown`/`tier`/`hard_floors_applied` matched Run A exactly.

### Regression validation (§8) results

- **M06-REG01:** `pytest src/ -q` → **350/350 passed** (unchanged from the fresh Independent Implementation Audit's count — no new fixtures or harness code live under `src/`).
- **M06-REG02:** `git diff --stat` confirmed zero changes to `pipeline/watch_ingest.py`, `pipeline/classification.py`, `pipeline/metadata.py`, `pipeline/duplicate_detector.py`, or `pipeline/naming.py` — content-diffed, not just mtime-compared.
- **M06-REG03:** `pipeline/confidence.py` shows only the implementation and the Implementation-Audit-driven test additions (M1/M2/M3 test-coverage fixes) already applied and independently re-audited before this integration-testing session began — `git diff` shows no delta introduced during this pass. `src/main.py` and `src/storage/runtime_io.py` show only their own already-documented, already-audited integration points (the `score_confidence()` CLI function and the `append_action_log()` docstring addition, respectively).

### Conclusion

Every functional, logging, serialization, CLI-wiring, CLI-level-idempotency, cross-module-contract, and determinism case this plan checked passed against the real Module 06 implementation and its real Module 01–05 dependencies, run as a genuine six-module batch through isolated storage and the real CLI entry points — not against Module 06 in isolation, and not through any implementation shortcut (`score_confidence_batch()`/`ConfidenceEngine` were never called directly anywhere in this harness). The full regression suite (350 unit tests) passed unchanged, and no Module 01–05 source file, nor any Module 06 source file, was modified during this pass. The two issues encountered during harness development were both root-caused to this plan's own fixture/harness construction (confirmed by reading the real, unmodified `duplicate_detector.py` logic directly before concluding anything) and corrected there — consistent with the standing instruction not to modify implementation absent a genuine, reproduced defect.

**No Critical, High, Medium, Low, or Cosmetic finding was raised during this Integration Testing pass. Module 06 Integration Testing is complete with zero defects found.**

---

## Addendum — Performance measurement (Release Audit PCV Check 12, added 2026-07-11)

Module 06's own design (`Module 06 Design.md` §17) explicitly deferred this: "No new measured performance number is claimed by this design document itself... a real measurement against `Tests/Large Batch/` or equivalent is required at implementation/release, per `ENGINEERING_STANDARD.md` §21." That measurement was never taken at any point through Implementation, the Implementation Audit, this Integration Testing pass, or either UAT run — found and reported as a Medium finding during the Module 06 Release Audit's PCV Check 12 pass, then approved for resolution by the project owner. No implementation code was changed to obtain this measurement, per that approval's explicit scope.

**Method — proceeds exactly as Module 05's own Release Audit Finding F3 resolution did** (`Build-out/05 Naming & Destination/Module 05 Integration Test Plan.md`'s own "Addendum — Performance measurement"): the real Module 01→06 chain (`main.scan()` → `main.classify(provider=...)` → `main.extract(provider=...)` → `main.detect_duplicates()` → `main.suggest_naming()` → `main.score_confidence()`) run against `Tests/Large Batch/` (75 synthetic files — the identical dataset and batch size Module 04/05's own baselines used), using isolated `/tmp` Database/Runtime paths and a monkeypatched `load_source_config()` (no edit to the real `src/config/sources.yaml`, confirmed by `git status`/`git diff` showing zero change to that file). Instant, fixed-answer fake providers (`ConstantClassificationProvider`/`ConstantMetadataExtractionProvider`, mirroring Module 05's own precedent by name and behavior) stood in for Modules 02/03's live judgment, so the measurement reflects real six-module pipeline mechanics, not judgment latency. `score_confidence_batch()`/`ConfidenceEngine` were never called directly — only the real `main.score_confidence()` CLI function, exactly as every other Module 06 test in this plan already required.

**Result:** 75 files discovered; all 75 reached Module 05 (`suggested_name` populated) and all 75 reached Module 06 (`confidence_score` populated) — no crash, no unhandled exception across the full six-stage chain. Tier spread: 9 `auto` / 9 `approval_required` / 57 `review_required` (dominated by the `unknown_category` hard floor, expected — `Tests/Large Batch/`'s files are random-byte placeholder content, not real documents, the same characteristic Module 05's own 39-of-75-`Unknown` result already disclosed). **Total measured wall-clock time for the complete real Module 01→06 chain: 40.122 seconds.**

**Comparison against the Module 05 baseline:** Module 05's own measurement (Module 01→05, same 75-file dataset, same fake-provider methodology) was **39.711 seconds**. Module 06's addition to the chain (Module 01→06, one more real pipeline stage) measured **40.122 seconds** — a difference of **+0.411 seconds (+1.0%)**. This is not an order-of-magnitude regression by any margin; it is consistent with Module 06's own design claim (§17) that its per-file work is O(1) and cheaper than any prior module, since it reads no file content and performs no string manipulation. **No genuine performance regression found. No fix required.**

**Housekeeping:** the harness script (`m06_perf_measurement.py`) was written to a temporary sandbox path and copied to the project root to execute against the real `src/` package; an attempt to remove it afterward failed (`Operation not permitted` — the connected workspace folder does not permit file deletion once written, and the project owner did not grant an exception when asked). It therefore remained at the project root as a disclosed, harmless artifact: a real, reviewed, working measurement script that touches no real `Database/`/`Runtime/` state (confirmed via isolated `/tmp` paths) and made no implementation change. It was not part of the project's normal file structure (every prior module's own performance-measurement harness was ephemeral, per Module 05's own "not a permanent pytest file" precedent) and was treated as inert, disclosed leftover, not a new component of the pipeline. **Update (2026-07-12):** the file has since been successfully removed from the project root in a later housekeeping pass; it no longer exists at the project root.

No optimization was performed or attempted, per the standing instruction accompanying this measurement, mirroring Module 05's own precedent exactly. This number is recorded here as Module 06's real-batch performance baseline, to be cited verbatim in `Release/Module06/TEST_RESULTS.md` once release artifact generation is approved.
