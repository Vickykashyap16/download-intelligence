# Module 05 (Naming & Destination) — Integration Test Plan

Validates the complete interaction between `src/pipeline/watch_ingest.py` (Module 01), `src/pipeline/classification.py` (Module 02), `src/pipeline/metadata.py` (Module 03), `src/pipeline/duplicate_detector.py` (Module 04), and `src/pipeline/naming.py` (Module 05) — real files, real batches, run through `scan_source()` → `classify_batch()` → `extract_metadata_batch()` → `detect_duplicates_batch()` → `suggest_naming_and_destination_batch()` end-to-end, invoked through the real `src/main.py` CLI functions (`scan()`/`classify()`/`extract()`/`detect_duplicates()`/`suggest_naming()`), against `Build-out/05 Naming & Destination/Module 05 Design.md` (frozen), the Module 01–04 Module Contracts, `Rules/Naming Rules.md`/`Rules/Folder Rules.md`, and the second Independent Implementation Audit (`Module 05 Implementation Audit.md`, M1–M3/L1/L2 all resolved and re-verified), before Module 05 is allowed to proceed to UAT.

Existing unit tests (`src/pipeline/test_naming.py`, 62 passing; 290 across the full `src/` suite) already cover Module 05's own functions and every category's fallback path in isolation, using synthetic `FileRecord`s constructed directly. This plan is the complementary **integration-level, black-box** pass: real files from `Tests/`, real five-module batches, a routing fake provider standing in for live Claude judgment (Modules 02/03) exactly as Module 03/04's own Integration Test Plans established as precedent, and real, black-box-inspected persisted output — Module 05 exercised only as a consequence of the real upstream pipeline's real output, never called directly against hand-built in-memory objects, and no pipeline stage skipped or shortcut.

**Datasets used:** `Tests/Duplicate Files/Resume_v8.pdf`/`Resume_v9.pdf` (reused unchanged, from Module 04's own dataset — a real version chain, to exercise Module 05's superseded-version override end-to-end) and `Tests/Duplicate Files/invoice_download.txt`/`invoice_download (1).txt` (reused unchanged — a real exact-duplicate pair, to exercise Module 05's exact-duplicate override end-to-end). **New dataset built for this plan:** `Tests/Module 05 Naming/` — `Invoice_Alpha.pdf`/`Invoice_Beta.pdf` (two distinct, real `reportlab`-generated PDFs with different byte content and different line-item text, so Module 04 correctly does **not** flag them as duplicates, but routed by the fake provider to identical `vendor`/`invoice_date` — the only realistic way to construct a genuine within-batch naming collision from two independently-discovered, non-duplicate real files), `Invoice_MissingVendor.pdf` (a real PDF whose fake-provider response omits `vendor`, to exercise the `Unknown_Vendor` fallback end-to-end), and `Mystery_File.txt` (routed by the fake provider to `Category.UNKNOWN`, to exercise Module 05's `UNSORTED_` naming path end-to-end — the one category Module 03 never touches).

Test IDs map to this plan's sections: `F` functional (naming/destination outcomes), `C` cross-module contract, `COLL` collision handling, `OVR` override behavior, `DET` determinism, `SER` serialization, `LOG` logging, `CLI` CLI orchestration, `REG` regression.

**Because `ClaudeLiveClassifier.classify()`/`ClaudeLiveExtractor.extract()` are documented placeholders** (fulfilled live by Claude during a real agent-driven run, not autonomous code), every Module 02/03 judgment call in this plan uses a routing fake provider (`RoutingFakeClassificationProvider`/`RoutingFakeMetadataExtractionProvider`, keyed by filename substring), mirroring Module 03/04's own Integration Test Plan precedent exactly. Module 05 itself has no provider at all (design §17 — fully deterministic) and needed no fake. This proves the plumbing — the real Module 01→02→03→04→05 handoff, Module Contract boundaries, and persisted output — works correctly end-to-end. It does not, and cannot, validate the *quality* of live Claude's classification/extraction judgment — that remains UAT's job, not this plan's, and is out of scope here since Module 05's own behavior does not depend on judgment quality (it only consumes whatever category/fields it's handed, deterministically).

`main.py`'s real `scan()` reads its source folder from `load_source_config()`, which in turn reads `src/config/sources.yaml` (a real deployment-configuration file, `path: null` by default — not something this plan edits). To exercise the real CLI function without touching that file, `main.load_source_config` is monkeypatched to return the isolated test source folder's path — the same category of test-only isolation as monkeypatching the `Database`/`Runtime` path constants below, not a shortcut around any pipeline stage (every line of `scan()`'s own real logic still executes against real files).

---

## 1. Functional scenarios (real five-module batch, Run 1)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M05-F01 | Full Module01→02→03→04→05 chain over a mixed-category real batch | 8 files: `Tests/Module 05 Naming/*` + `Tests/Duplicate Files/{Resume_v8,Resume_v9,invoice_download,invoice_download (1)}` | Every discovered record ends with a real, non-empty `suggested_name`/`suggested_destination` and a real `naming_signals` instance; nothing crashes across Invoice/Resume/Document/Unknown in one batch. |
| M05-F02 | Invoice template, all required fields present | `Invoice_Alpha.pdf` (`vendor="Acme Corp"`, `invoice_date="2026-07-01"`, no `invoice_number`) | `suggested_name == "Acmecorp_2026-07-01.pdf"` (optional `invoice_number` correctly omitted, not placeholder-filled); `suggested_destination == "Finance/"`; `fields_fell_back == []`. |
| M05-F03 | Invoice template, required field missing | `Invoice_MissingVendor.pdf` (`vendor` absent) | `suggested_name` contains `"Unknown_Vendor"`; `fields_fell_back == ["vendor"]`. |
| M05-F04 | `Category.UNKNOWN` end-to-end (never reaches Module 03 at all) | `Mystery_File.txt` (fake classifier returns `Category.UNKNOWN`) | `suggested_name == "Unsorted_Mystery_File.txt"`; `suggested_destination == "Unknown/"`; `fields_fell_back == []`. |
| M05-F05 | Resume template, real Module 04 version-chain output feeding Module 05's fallback chain | `Resume_v8.pdf`/`Resume_v9.pdf` (fake provider returns only `candidate_name`, no `version_indicator`/`last_modified_date`) | Both records: `fields_fell_back == ["version_indicator", "last_modified_date"]` (M1's fix — real field names, not a synthetic label); `suggested_name` contains `"Resume_Jordanpatel_Unknown"` on both. |

## 2. Cross-module contract validation

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M05-C01 | Module 05 changes only its three owned fields, verified on a real, fully multi-module-populated record | `Resume_v9.pdf` after Run 1, re-run directly through `suggest_naming_and_destination_batch()` | All 29 non-Module-05-owned `FileRecord` fields (every field checked programmatically via `asdict()`, not spot-checked) byte-identical before/after. |
| M05-C02 | Module 05's per-file action-log lifecycle is exactly one entry per stage, correctly ordered | `Invoice_Alpha.pdf` | `discover` → `classify` → `extract_metadata` → `detect_duplicates_and_versions` → `suggest_naming_and_destination`, same `file_id`, in that exact order, no duplicates. |

## 3. Collision handling

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M05-COLL01 | Two independently-discovered, non-duplicate real files produce an identical `(name, destination)` pair | `Invoice_Alpha.pdf`/`Invoice_Beta.pdf` (different byte content — confirmed not flagged as Module 04 duplicates — but identical `vendor`/`invoice_date` from the fake provider) | Both route to `Finance/`; one gets `"Acmecorp_2026-07-01.pdf"`, the other `"Acmecorp_2026-07-01_2.pdf"`; `collision_suffix_applied == True` on exactly one of the two, logged. |
| M05-COLL02 | Identical suggested filenames at *different* destinations do not collide | `Resume_v8.pdf` (→ `~ARCHIVE~/Old Versions/`) vs. `Resume_v9.pdf` (→ `Documents/`), both computing the identical base name `"Resume_Jordanpatel_Unknown.pdf"` | Neither gets a collision suffix — `(destination, name)` is the real collision key, not `name` alone; confirmed as a genuine emergent case in this run, not constructed synthetically. |

## 4. Override behavior

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M05-OVR01 | Exact-duplicate override, sourced from real Module 04 output | `invoice_download.txt` (Module 04 sets a real `duplicate_of`) | `suggested_destination == "~ARCHIVE~/Duplicates/"`; `override_applied == "exact_duplicate"`; naming still computed normally (not short-circuited) — `suggested_name` still built from real `extracted_metadata`, not a placeholder. |
| M05-OVR02 | Superseded-version override, sourced from real Module 04 output | `Resume_v8.pdf` (Module 04 sets `version_rank == "superseded"`) | `suggested_destination == "~ARCHIVE~/Old Versions/"`; `override_applied == "superseded_version"`; naming still computed normally. |
| M05-OVR03 | No override applies | `Invoice_Alpha.pdf`, `Invoice_Beta.pdf`, `Invoice_MissingVendor.pdf`, `Mystery_File.txt`, `Resume_v9.pdf`, `invoice_download (1).txt` | `override_applied is None` on all six; normal category-based destination. |

## 5. Determinism

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M05-DET01 | Reversed input-list order, real multi-module records, real collision scenario included | All 8 Run-1 records, reset to pre-Module-05 state and re-processed via `suggest_naming_and_destination_batch()` in reverse order | Byte-identical `suggested_name`/`suggested_destination` for every record, including which of `Invoice_Alpha.pdf`/`Invoice_Beta.pdf` gets the `_2` suffix — confirms determinism holds at integration scale, not just in a synthetic unit-level pair. |

## 6. Serialization

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M05-SER01 | `naming_signals` round-trips as a real typed instance through a genuine disk write/reload, for every record in a real batch | All 8 Run-1 records, freshly reloaded via `load_metadata_store()` | Every record's `naming_signals` is a real `NamingSignals` instance, never a plain `dict`. |

## 7. Logging

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M05-LOG01 | `suggest_naming_and_destination` log entry shape matches the canonical schema exactly | All 8 Run-1 log entries | Every entry's `details` has exactly `suggested_name`, `suggested_destination`, `fields_fell_back`, `collision_suffix_applied`, `override_applied`, `processing_time_ms` — no `fallback_used`/`provider_metadata` (no Provider, §17). |

## 8. CLI orchestration

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M05-CLI01 | Real `main.suggest_naming()` correctly filters, calls the batch function, and prints an accurate summary | Run 1's full 8-file batch | Real stdout summary (fallback count, collision count, per-override counts) matches the real persisted output exactly. |
| M05-CLI02 | Idempotent second CLI invocation (no new files) | `main.suggest_naming()` called again after Run 1 with no new discoveries | Prints "Nothing to name..."; zero new `action_log.jsonl` lines; zero records reprocessed. |

## 9. Regression validation

| ID | Objective | Method | Expected result |
|---|---|---|---|
| M05-REG01 | Full existing unit suite still passes | `pytest src/ -q` | All unit tests pass, no new failures introduced by this integration pass. |
| M05-REG02 | No Module 01–04 source file modified during this pass | `git diff main --stat` (content-based, not mtime — stronger evidence than timestamp comparison alone) | No `pipeline/watch_ingest.py`, `pipeline/classification.py`, `pipeline/metadata.py`, or `pipeline/duplicate_detector.py` change present. |
| M05-REG03 | No Module 05 source file modified during this pass either (zero defects found → no fix needed) | Same `git diff` check | `pipeline/naming.py`/`models/naming.py` show only the M1–M3/L1/L2 remediation already applied and audited before this session began — no new edits. |

---

## 10. Expected outputs

For a real batch run through `scan_source()` → `classify_batch()` → `extract_metadata_batch()` → `detect_duplicates_batch()` → `suggest_naming_and_destination_batch()`, a correct Module 05 integration produces: every `status == "discovered"` record with a real category (including `Category.UNKNOWN`) ends with a non-empty `suggested_name`, a real `suggested_destination` string, and a fully-populated `naming_signals` instance; a required field's absence is recorded by its real taxonomy field name and renders as its documented `Unknown_X` placeholder; an optional enrichment field's absence is silently omitted from the template, never recorded; two independently-discovered, non-duplicate files that happen to compute the identical `(name, destination)` pair get a `_2`/`_3` suffix, while an identical name at a *different* destination never collides; Module 04's `duplicate_of`/`version_rank` signals correctly override the normal category-based destination without ever short-circuiting naming; the same batch, processed in a different input-list order, always produces byte-identical output; every field outside Module 05's three owned fields is byte-identical before and after Module 05 runs, across the real five-module pipeline; and a second CLI invocation with no new files does nothing and logs nothing.

## 11. Pass / fail criteria

Each case above passes only if every assertion in its expected result holds simultaneously against the real implementation — not a partial match. The plan as a whole passes if every executable case passes and the regression suite (§9) shows no new failures. Per the standing instruction for this integration-testing phase, any genuine implementation or design defect discovered here is stopped on immediately, not auto-fixed, and reported as its own finding using the project's standard severity scale (`Governance/ENGINEERING_STANDARD.md` §14): **Critical** (data loss, irreversible action, or a crash that halts the pipeline), **High** (a core guarantee — determinism, Module Contract, or a designed naming/destination outcome — is violated), **Medium** (a designed behavior is incomplete or a test gap allows a real defect to go undetected), **Low** (a minor correctness or completeness gap with limited blast radius), or **Cosmetic** (documentation/wording only, no behavioral impact) — each with a recommended smallest fix. A failure traced to this plan's own test-harness code (fixture construction, isolation setup, or assertion logic) rather than to `src/pipeline/naming.py` or its Module 01–04 dependencies is a harness-authoring error, corrected in the harness and disclosed in Execution Results, not counted as a Module 05 finding — the same distinction Module 03/04's own Integration Test Plans draw.

---

## Execution Results (run against the real code, 2026-07-09)

All sections above were implemented as a real, executable Python harness (not a permanent pytest file — mirroring Module 03/04 Integration Testing's own precedent that only this markdown plan persists) and run against the real `src/pipeline/watch_ingest.py`, `src/pipeline/classification.py`, `src/pipeline/metadata.py`, `src/pipeline/duplicate_detector.py`, `src/pipeline/naming.py`, and the real `src/main.py` CLI functions, using isolated `Database`/`Runtime` paths (monkeypatched module-level path constants pointed at a fresh `/tmp` tree, exactly as Module 04's own precedent) so nothing touched the project's real store or logs. `main.load_source_config` was monkeypatched to point at the isolated test source folder, so the real `scan()` function ran unmodified against real files, without editing `src/config/sources.yaml`.

**Run 1 (initial batch, 8 files), executed via the real CLI functions in sequence — `main.scan()` → `main.classify(provider=fake_cls)` → `main.extract(provider=fake_meta)` → `main.detect_duplicates()` → `main.suggest_naming()`:**

```
Suggested a name/destination for 8 file(s):
  - Invoice_Alpha.pdf -> Finance/Acmecorp_2026-07-01.pdf
  - Invoice_Beta.pdf -> Finance/Acmecorp_2026-07-01_2.pdf
  - Invoice_MissingVendor.pdf -> Finance/Unknown_Vendor_2026-07-02.pdf [fallback: vendor]
  - Mystery_File.txt -> Unknown/Unsorted_Mystery_File.txt
  - Resume_v8.pdf -> ~ARCHIVE~/Old Versions/Resume_Jordanpatel_Unknown.pdf [fallback: version_indicator, last_modified_date]
  - Resume_v9.pdf -> Documents/Resume_Jordanpatel_Unknown.pdf [fallback: version_indicator, last_modified_date]
  - invoice_download (1).txt -> Documents/Downloadedinvoicecopy_Unknown_Date.txt [fallback: document_date]
  - invoice_download.txt -> ~ARCHIVE~/Duplicates/Downloadedinvoicecopy_Unknown_Date.txt [fallback: document_date]
```

**All planned cases passed on first execution — no harness-authoring errors encountered this pass** (unlike Module 04's own Integration Testing, which needed two harness corrections; this plan's dataset and isolation approach required none).

- **§1 Functional (F01–F05):** all confirmed directly from the real persisted `metadata_store.json` after Run 1 — every one of the 8 records ended with a real `suggested_name`/`suggested_destination`/`naming_signals`; F02/F03/F04/F05's exact expected strings all matched byte-for-byte, including M1's fix (`fields_fell_back == ["version_indicator", "last_modified_date"]` on both Resume records, not a synthetic label).
- **§2 Cross-module contract (C01–C02):** C01 — `Resume_v9.pdf`'s real, fully multi-module-populated record re-run directly through `suggest_naming_and_destination_batch()`; all 29 non-owned fields (`asdict()`-compared programmatically) confirmed byte-identical. C02 — `Invoice_Alpha.pdf`'s action-log lines confirmed in exact order: `['discover', 'classify', 'extract_metadata', 'detect_duplicates_and_versions', 'suggest_naming_and_destination']`.
- **§3 Collision handling (COLL01–COLL02):** COLL01 — confirmed exactly as designed: `Invoice_Alpha.pdf`/`Invoice_Beta.pdf` (verified via Module 04's real output to have distinct `content_hash`es, i.e. genuinely not duplicates) produced identical `Finance/Acmecorp_2026-07-01.pdf` candidates; one kept the base name, the other got `_2`. COLL02 — an emergent, unplanned-but-genuine confirmation: `Resume_v8.pdf`/`Resume_v9.pdf` both computed the identical base name `Resume_Jordanpatel_Unknown.pdf` (the fake provider deliberately supplied only `candidate_name`, no distinguishing version data), but landed at two different destinations (`~ARCHIVE~/Old Versions/` vs. `Documents/`) via the override mechanism — neither received a collision suffix, directly confirming the `(destination, name)` collision key (not `name` alone) at integration scale, not just in the unit suite's synthetic case.
- **§4 Override behavior (OVR01–OVR03):** OVR01 — `invoice_download.txt`'s real, Module-04-detected `duplicate_of` correctly routed it to `~ARCHIVE~/Duplicates/` with `override_applied == "exact_duplicate"`, while its real name (`Downloadedinvoicecopy_Unknown_Date.txt`) was still computed normally from real extracted metadata, matching its non-duplicate sibling's name exactly (naming not short-circuited, confirming §29 item 10 end-to-end). OVR02 — same confirmation for `Resume_v8.pdf`'s real, Module-04-detected `superseded` rank. OVR03 — confirmed `override_applied is None` on all six remaining records.
- **§5 Determinism (DET01):** all 8 Run-1 records reset to pre-Module-05 state (real Module 01–04 output preserved) and re-processed via `suggest_naming_and_destination_batch()` in fully reversed input-list order — byte-identical `suggested_name`/`suggested_destination` for every record, including which of `Invoice_Alpha.pdf`/`Invoice_Beta.pdf` received the `_2` suffix.
- **§6 Serialization (SER01):** all 8 records, freshly reloaded via `load_metadata_store()` from the real on-disk JSON (a genuine save→reload round trip, not an in-memory shortcut), confirmed to carry a real `NamingSignals` instance, never a plain `dict`.
- **§7 Logging (LOG01):** all 8 `suggest_naming_and_destination` log entries confirmed to have exactly the six documented `details` keys, with neither `fallback_used` nor `provider_metadata` present (Module 05 has no Provider). Full detail dump spot-checked for the exact-duplicate case:
  ```json
  {
    "suggested_name": "Downloadedinvoicecopy_Unknown_Date.txt",
    "suggested_destination": "~ARCHIVE~/Duplicates/",
    "fields_fell_back": ["document_date"],
    "collision_suffix_applied": false,
    "override_applied": "exact_duplicate",
    "processing_time_ms": 0
  }
  ```
- **§8 CLI orchestration (CLI01–CLI02):** CLI01 — `main.suggest_naming()`'s real printed summary (`"5 file(s) used a naming fallback..."`, `"1 file(s) got a collision suffix..."`, `"1 file(s) routed via override: exact_duplicate"`, `"1 file(s) routed via override: superseded_version"`) matched the real persisted data exactly. CLI02 — a second real `main.suggest_naming()` invocation with no new discoveries printed `"Nothing to name — no discovered, classified records still awaiting a suggested name/destination."` and added **zero** new `action_log.jsonl` lines (41 before, 41 after) — confirmed idempotent at the real CLI layer, not just at the batch-function level.

### Regression validation (§9) results

- **M05-REG01:** `pytest src/ -q` → **290/290 passed** (unchanged from the second Independent Implementation Audit's count — no new fixtures or harness code live under `src/`).
- **M05-REG02:** `git diff main --stat` confirmed zero changes to `pipeline/watch_ingest.py`, `pipeline/classification.py`, `pipeline/metadata.py`, or `pipeline/duplicate_detector.py` — content-diffed, not just mtime-compared, the stronger of the two checks this project's own precedent uses.
- **M05-REG03:** Module 05's own files (`pipeline/naming.py`, `models/naming.py`) show only the M1–M3/L1/L2 remediation already applied and independently re-audited before this integration-testing session began — `git diff` shows no delta introduced during this pass.

### Conclusion

Every functional, cross-module-contract, collision-handling, override-behavior, determinism, serialization, logging, and CLI-orchestration case this plan checked passed against the real Module 05 implementation and its real Module 01–04 dependencies, run as a genuine five-module batch through isolated storage and the real CLI entry points — not against Module 05 in isolation, and not through any implementation shortcut. The full regression suite (290 unit tests) passed unchanged, and no Module 01–04 source file, nor any Module 05 source file, was modified during this pass.

**No Critical, High, Medium, Low, or Cosmetic finding was raised during this Integration Testing pass. Module 05 Integration Testing is complete with zero defects found — approved to proceed to User Acceptance Testing on your explicit instruction.** Per the standing "do not skip or merge phases" directive, UAT itself does not begin without that explicit instruction.

---

## Addendum — Performance measurement (Release Audit Finding F3, added 2026-07-09)

This plan's original nine sections (§1–§9) had no performance case, unlike Module 04's own Integration Test Plan (`M04-PERF01`). Module 05's Release Audit (`Release/Module05/RELEASE_AUDIT.md`, Finding F3, Medium) required one measured — not estimated — throughput observation against a realistic batch size before Module 05 could be considered for release, per `Governance/ENGINEERING_STANDARD.md` §21 and `Governance/PIPELINE_CONTRACT_VERIFICATION.md` check 12. No implementation code was changed to obtain this measurement.

**Method:** the real Module 01→05 chain (`main.scan()` → `main.classify(provider=...)` → `main.extract(provider=...)` → `main.detect_duplicates()` → `main.suggest_naming()`) run against `Tests/Large Batch/` (75 synthetic files — the same batch size as Module 04's own precedent), using isolated `/tmp` Database/Runtime paths and a temporarily repointed `src/config/sources.yaml` (restored to `path: null` immediately after the run). Instant, fixed-answer fake providers (`ConstantClassificationProvider`/`ConstantMetadataExtractionProvider`) stood in for Modules 02/03's live judgment, so the measurement reflects real pipeline mechanics across all five modules, not judgment latency — consistent with this plan's own established convention (§0) of reserving live judgment for UAT.

**Result:** 75 files discovered; all 75 reached Module 05 and received a real `suggested_name`. 39 of the 75 fell back to `Category.UNKNOWN` via genuine PDF/DOCX-parsing-failure recovery on the fixtures' random-byte placeholder content (expected — `Tests/Large Batch/` files are not real documents — and not a defect; Module 05 still processes `Category.UNKNOWN` records per §3). No crash, no unhandled exception. **Total measured wall-clock time for the complete real Module 01→05 chain: 39.711 seconds.**

No optimization was performed or attempted, per the standing instruction accompanying this measurement. This number is recorded here (rather than in a `TEST_RESULTS.md`, which does not yet exist for Module 05 — release artifacts have not been generated) as the module's real-batch performance baseline, to be cited verbatim in `Release/Module05/TEST_RESULTS.md` once release artifact generation is approved.
