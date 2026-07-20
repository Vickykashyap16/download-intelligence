# Module 08 (Logging & Reporting) — Integration Test Plan

Validates the complete interaction between `src/pipeline/reporting.py` / `src/storage/runtime_io.py` (Module 08) and Modules 01–07 — real files, a real batch, run through the full `scan()` → `classify()` → `extract()` → `detect_duplicates()` → `suggest_naming()` → `score_confidence()` → `execute()` → `report()` chain, invoked through the real `src/main.py` CLI functions, against `Build-out/08 Logging & Reporting/Module 08 Design.md` (frozen), `Governance/ARCHITECTURE_DECISIONS.md` decisions 25–31, and Module 08's own fresh Independent Implementation Audit (RWP-A, WP-1 through WP-7, PASS WITH RECOMMENDATIONS), before Module 08 is allowed to proceed to UAT.

Existing unit tests (`src/pipeline/test_reporting.py`, `src/storage/test_runtime_io.py`, `src/test_main.py` — 161 tests of the full 716-test `src/` suite) already cover Module 08's own functions in isolation using synthetic `FileRecord`s and hand-built action-log entries constructed directly. This plan is the complementary **integration-level, black-box** pass: real files from `Tests/`, a real seven-module batch, routing fake providers standing in for live Claude judgment (Modules 02/03 only — Module 08 itself has no Provider, it is fully deterministic per §2 of its design), and real, black-box-inspected `Runtime/Reports/*` output — `generate_daily_summary()`/`generate_weekly_summary()`/`generate_duplicate_report()`/`generate_storage_report()`/`report()` exercised only as a consequence of the real upstream pipeline's real output and the real CLI functions (`main.scan()` through `main.execute()`, then `main.report()`), never called directly against hand-built in-memory objects except where this plan explicitly simulates a log-corruption or multi-day boundary (documented inline), and no pipeline stage skipped or shortcut.

**Dataset used — the same 9-file batch `Tests/Module 07 Integration Test Plan.md` already proved flows cleanly through Modules 01–07, reused unchanged (no new files created for this plan):**
- `Tests/Module 05 Naming/Invoice_Alpha.pdf`, `Invoice_MissingVendor.pdf`
- `Tests/Module 02 Classification/password_protected_contract.pdf`
- `Tests/Duplicate Files/invoice_download.txt` / `invoice_download (1).txt` (exact duplicate pair)
- `Tests/Duplicate Files/Resume_v8.pdf` / `Resume_v9.pdf` (version chain)
- `Tests/Duplicate Files/product_photo_v1.jpg` / `product_photo_v2.jpg` (version chain)

Reusing Module 07's own proven fixtures (rather than building new ones) is deliberate: it means every `FileRecord` Module 08 aggregates in this plan was produced by the real Module 01–07 pipeline, not fabricated to be convenient — the strongest available cross-module contract check.

**Routing fake providers** (`RoutingClassificationProvider`/`RoutingMetadataProvider`, keyed by filename), mirroring Module 03/04/05/06/07's own Integration Test Plan precedent exactly, stand in for `ClaudeLiveClassifier`/`ClaudeLiveExtractor` (documented placeholders). `main._SOURCES_CONFIG_PATH` and `src.pipeline.watch_ingest._SOURCES_CONFIG_PATH` are both monkeypatched to an isolated `sources.yaml` carrying a real `destination_root`; `database`'s and `runtime_io`'s module-level path constants are monkeypatched to an isolated `/tmp` tree — the same category of test-only isolation as every prior module's Integration Test Plan, never a shortcut around any pipeline stage.

Test IDs map to this plan's sections: `F` functional (all four report types + `report()` orchestration), `LOG` corrupted/partial action-log, `MIX` mixed-batch, `WK` multi-day Weekly Summary rollup, `CTR` cross-module contracts, `PERF` performance, `REG` regression.

---

## 1. Functional scenarios — all four report types together (Run A)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M08-F01 | Full seven-stage pipeline (Modules 01–07) runs cleanly against a real 9-file batch, feeding Module 08 real, fully-populated records and a real action log | All 9 fixtures | All 9 discovered/classified/extracted/duplicate-checked/named/scored; 2 executed (an exact-duplicate pair, one landing in `~ARCHIVE~/Duplicates/`), 7 left unexecuted (`approval_required` with no decision, or `review_required`). |
| M08-F02 | `generate_daily_summary()` produces correct, traceable counts against the real batch | Real action log + metadata store | "Files scanned: 9", "Approval required: 3", "Review required: 6", "Duplicates found: 1 (archived)" — each hand-verified against the real Module 01–07 output. |
| M08-F03 | `generate_storage_report()` includes only the 2 real executed (`processed_at is not None`) records, correctly excluding the other 7 | Same | "Filed records: 2"; both `Finance/` and `~ARCHIVE~/Duplicates/` destination buckets present with correct real `size_bytes` sums. |
| M08-F04 | `generate_duplicate_report()` correctly categorizes real signal-bearing records by their real last disposition action, and correctly excludes "latest"-ranked siblings from their own row | Same | 3 records tracked (1 real duplicate, 2 real superseded versions); the executed duplicate shows "Archived"; the two still-`review_required` superseded versions show "Kept" (never executed yet). |
| M08-F05 | `report()` orchestrates all four generators in one call and prints a correct CLI summary | Same | Four paths printed, no exception, "Module 08 report generation complete." |

## 2. Corrupted / partial action-log scenario (§12 Layer 1)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M08-LOG01 | A truncated JSON line and a stray blank line appended mid-log (simulating an interrupted write) do not crash `report()` | Real log + 1 malformed line + 1 blank line | `report()` completes without raising; Daily Summary discloses "Malformed log lines skipped: 1". |
| M08-LOG02 | Every real, well-formed count is still correct despite the corruption | Same | "Files scanned: 9" and every other real figure unchanged from the pre-corruption run. |

## 3. Mixed-batch scenario

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M08-MIX01 | A single real batch containing `approval_required`, `review_required`, an executed exact duplicate, and two not-yet-executed superseded versions all aggregate correctly together, with no cross-contamination between report types | Full 9-file batch, post-`execute()` | Daily Summary's tier breakdown, Storage Report's filed-only scope, and Duplicate Report's disposition categorization each independently and correctly reflect the same underlying mixed state. |

## 4. Weekly Summary multi-day rollup (§9, decision 27)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M08-WK01 | `generate_weekly_summary()` correctly rolls up a real, already-written Daily Summary file as "Reported" once its own day is closed, and correctly shows every other day in the week as "No activity" | Real Day 1 Daily Summary (from Run A) + `generate_weekly_summary()` called for that week with "now" simulated one day later | Day 1 shown "Reported" with totals matching the real Daily Summary exactly (9/0/3/6/1/0/0); every other day in the week shows "No activity" (real, known zero — the week's other days genuinely had no action-log entries). |

## 5. Cross-module contracts (Modules 01–07)

| ID | Objective | Test data | Expected result |
|---|---|---|---|
| M08-CTR01 | Module 08 reads real `suggested_destination`/`suggested_name` (Module 05), `category`/`confidence_score`/`tier` (Modules 02/06), `duplicate_of`/`version_rank` (Module 04), and `processed_at`/`size_bytes` (Module 01/07) fields correctly, with no reconstruction or reinterpretation of any field | Full real batch | Every report's figures traced by hand against the real `FileRecord` values and real action-log entries; all 8 hand cross-checks in Execution Results passed. |
| M08-CTR02 | No Module 01–07 source file is modified by this Integration Testing pass | — | `git diff --stat` against the real repository shows zero changes to any file outside `Tests/Module 08 Integration Test Plan.md` itself. |

## 6. Performance (§19)

| ID | Objective | Method | Expected result |
|---|---|---|---|
| M08-PERF01 | `report()` completes quickly against the real 9-file batch | Wall-clock timing | Sub-10ms for 9 records / 57 log lines. |
| M08-PERF02 | `report()` scales without a crash or unreasonable slowdown at higher volume | 2,000 synthetic records appended to the real batch's own metadata store/action log (Module 08's own O(records)/O(log lines) cost in isolation, per §19 — not a whole-pipeline volume test, which is Module 07's own concern) | Well under 1 second for ~2,000 records / ~2,000 log lines. |

## 7. Regression validation

| ID | Objective | Method | Expected result |
|---|---|---|---|
| M08-REG01 | Full existing unit suite still passes | `pytest src/ -q` | All unit tests pass, no new failures introduced by this integration pass. |
| M08-REG02 | No Module 01–07 or Module 08 source file modified during this pass | `git diff --stat` (content-based) | No `src/*.py` change present anywhere. |

---

## 8. Pass / fail criteria

Each case above passes only if every assertion in its expected result holds simultaneously against the real implementation. The plan as a whole passes if every executable case passes and the regression suite (§7) shows no new failures. Per the standing instruction for this integration-testing phase, any genuine implementation or design defect discovered here is stopped on immediately, not auto-fixed, and reported using `Governance/ENGINEERING_STANDARD.md` §14's severity scale (Critical/High/Medium/Low/Cosmetic), each with a recommended smallest fix. A failure traced to this plan's own test-harness code (fixture construction, isolation setup, or assertion logic) rather than to `src/pipeline/reporting.py`/`src/storage/runtime_io.py`/`src/main.py`'s `report()` or their Module 01–07 dependencies is a harness-authoring error, corrected in the harness and disclosed below, not counted as a Module 08 finding — the same distinction every prior module's Integration Test Plan draws.

---

## Execution Results (run against the real code, 2026-07-19)

All sections above were implemented as a real, executable Python harness (`m08_integration_harness.py`, not a permanent pytest file — mirroring Module 03/04/05/06/07's own precedent that only this markdown plan persists) and run against the real `src/pipeline/watch_ingest.py` through `src/pipeline/execution.py`, `src/pipeline/reporting.py`, `src/storage/runtime_io.py`, and the real `src/main.py` CLI functions including `report()`, using isolated `Database`/`Runtime` paths and an isolated destination-library folder pointed at by a real, isolated `sources.yaml`, so nothing touched the project's real store, logs, or `Downloads`-equivalent.

**Run A (9-file batch, Modules 01–07 via real CLI functions in sequence):**

```
Tiers after scoring: approval_required: 3, review_required: 6
Executed batch — 9 eligible: Executed: 2   Skipped: 7
```

Real Module 04 signals confirmed: 1 exact duplicate (`invoice_download.txt` → `invoice_download (1).txt`), 2 version chains (`Resume_v8/v9`, `product_photo_v1/v2`). The exact-duplicate pair was `approval_required` with decisions supplied for both, so both executed — the canonical record to `Finance/`, the duplicate to `~ARCHIVE~/Duplicates/`. Every other record was left correctly unexecuted (`review_required`, or `approval_required` with no decision supplied) — the same G3/I2 guarantee Module 07's own Integration Testing already certified, exercised here only as a byproduct of building real upstream data for Module 08.

**Module 08 — `report()` against real Day-1 data:**

```
Report generation:
  - Daily Summary: .../Daily Summary/summary_2026-07-19.md
  - Weekly Summary: .../Weekly Summary/summary_2026-W29.md
  - Duplicate Report: .../Duplicate Report/duplicate_report.md
  - Storage Report: .../Storage Report/storage_report.md
report() took 0.0034s over 57 action-log lines / 9 metadata records
[PASS] zero-write guarantee holds against real pipeline-produced data
```

Daily Summary (real): `Files scanned: 9`, `Approval required: 3`, `Review required: 6`, `Duplicates found: 1 (archived)`, one real "## Files" row per executed record with correct `New Name`/`Destination`/`Category`/`Confidence`/`Tier`.

Storage Report (real): `Filed records: 2`, `Total space used: 134 B`, `Finance/: 67 B`, `~ARCHIVE~/Duplicates/: 67 B`, `By Category → Invoice: 134 B` — correctly excludes all 7 unexecuted records regardless of their own real `size_bytes`.

Duplicate Report (real): `Records tracked: 3 (1 duplicates, 2 superseded versions)`, `Archived: 1`, `Kept: 2` — the executed duplicate correctly "Archived"; the two still-unexecuted superseded versions (`Resume_v8.pdf`, `product_photo_v1.jpg`) correctly "Kept," each correctly related to their real "latest" sibling by name, neither sibling given its own row.

**M08-F01 through M08-F05: 8/8 hand cross-checks passed** — every figure traced directly to the real batch's real Module 01–07 output, matching Execution Results exactly.

**Corrupted/partial action-log (M08-LOG01/02):**

```
[PASS] malformed line disclosed in Daily Summary: True
[PASS] real counts still correct despite corruption: True
[PASS] report() did not raise on corrupted log
```

A truncated line and a stray blank line were appended directly to the real, already-populated action log; `report()` was re-run and correctly disclosed "Malformed log lines skipped: 1" while every real count remained unchanged from the pre-corruption run.

**Mixed-batch (M08-MIX01):** confirmed by inspection of the same Run A output above — `approval_required`, `review_required`, an executed duplicate, and two unexecuted superseded versions all coexisted in one real batch, and each of the three report types independently reflected the correct subset with no cross-contamination (e.g., Storage Report never included the two still-`review_required` superseded versions despite their appearing in the Duplicate Report).

**Weekly Summary multi-day rollup (M08-WK01):**

```
[PASS] Day 1 correctly shown as 'Reported' (closed) in Day-2's Weekly Summary
[PASS] Weekly totals correctly rolled up from Day 1's real Daily Summary
```

```
# Weekly Summary — 2026-W29
- Week range: 2026-07-13 to 2026-07-19
- Files scanned: 9 | Approval required: 3 | Review required: 6 | Duplicates found: 1
## Days
| 2026-07-13 .. 2026-07-18 | No activity | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-07-19               | Reported    | 9 | 0 | 3 | 6 | 1 | 0 | 0 |
```

`generate_weekly_summary()` was called directly for the real week containing Day 1, with "now" simulated one day later so Day 1 correctly evaluated as closed — the real, already-written Daily Summary file was parsed back and its totals matched exactly, and every other day in the week correctly showed "No activity" (a real, known zero — those days genuinely had no action-log entries).

**Performance (M08-PERF01/02):**

```
report() over 9 records / 57 log lines:       0.0034s
report() over 2,009 records / 2,059 log lines: 0.258s
```

No crash, no unreasonable slowdown, consistent with §19's O(records)/O(log lines) claim. This is Integration Testing's own measurement, not the release-certified figure — that measurement is RWP-D's Release Audit's own responsibility.

**Cross-module contracts (M08-CTR01/02):** every field Module 08 read traced correctly to its real, upstream-module-written value (§21 auditability, confirmed by the 8 hand cross-checks above). `git diff --stat` against the real repository, run immediately after this pass, showed **zero changes to any file outside this plan document itself** — no Module 01–08 source file was modified.

### Harness corrections during development (disclosed, not Module 08 findings)

One issue surfaced while building the harness, root-caused to the harness's own scenario construction, not to `src/pipeline/reporting.py` or any upstream module:

1. **Initial Weekly Summary rollup scenario crossed a real ISO week boundary by accident.** The real "today" this session (2026-07-19) is a Sunday — the last day of ISO week 29. The harness's first attempt simulated "one day later" to close Day 1, which landed in ISO week 30, a *different* week than Day 1 itself — so Day 1 never appeared in the Weekly Summary being inspected, a harness scenario-selection mistake, not a defect in `generate_weekly_summary()`. Fixed by calling `generate_weekly_summary()` directly for the week containing Day 1 (rather than relying on `report()`'s own always-"this week" convenience scoping, decision 26), with only the module's internal "now" reference faked forward. Confirmed this is the correct fix, not a workaround, by re-reading `generate_weekly_summary(report_week)`'s own real signature: `report_week` determines which week to roll up via its own `isocalendar()`, independent of "now," which only determines the closed/open cutoff — exactly the real, designed behavior, now exercised correctly.

None of this required any change to `src/pipeline/reporting.py`, `src/storage/runtime_io.py`, `src/main.py`, or any other production file.

### Regression validation (§7) results

- **M08-REG01:** `pytest src/ -q` → **716/716 passed.**
- **M08-REG02:** `git diff --stat` confirmed zero changes to any Module 01–08 source file.

### Conclusion

Every functional, corrupted-log, mixed-batch, multi-day-rollup, cross-module-contract, and performance case this plan checked passed against the real Module 08 implementation and its real Module 01–07 dependencies, run as a genuine eight-module batch through isolated storage and the real CLI entry points — not against Module 08 in isolation, and not through any implementation shortcut. The full regression suite (716 unit tests) passed unchanged, and no Module 01–08 source file was modified during this pass. The one issue encountered during harness development was root-caused to the harness's own scenario construction and corrected there, consistent with the standing instruction not to modify implementation absent a genuine, reproduced defect.

**No Critical, High, Medium, Low, or Cosmetic finding was raised during this Integration Testing pass. Module 08 Integration Testing is complete with zero defects found.**
