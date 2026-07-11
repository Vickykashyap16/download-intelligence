# Test Results — Module 06 (Confidence & Review)

Full detail lives in `Tests/Module 06 Integration Test Plan.md`, `Tests/Module 06 UAT Plan.md`, and `Runtime/UAT/`; this is the release-record summary. All counts below were re-verified by direct `pytest` execution during release-package preparation (2026-07-11), not carried forward from memory.

## Unit tests

**352 of 352 passing**, pytest, isolated `tmp_path`/`monkeypatch` fixtures, no real Database/Runtime files touched:

| File | Tests | Owner |
|---|---|---|
| `src/pipeline/test_watch_ingest.py` | 15 (13 original + 2 from the v1.0.1 post-freeze correction) | Module 01 |
| `src/pipeline/test_classification.py` | 48 | Module 02 |
| `src/models/test_classification.py` | 6 | Module 02 |
| `src/core/test_pdf.py` | 6 | Module 02 |
| `src/core/test_text.py` | 7 | Module 02 |
| `src/core/test_images.py` | 7 | Module 02 |
| `src/core/test_exif.py` | 4 | Module 02 |
| `src/pipeline/test_metadata.py` | 57 | Module 03 |
| `src/core/test_archive.py` | 7 | Module 03 |
| `src/core/test_media.py` | 4 | Module 03 |
| `src/pipeline/test_duplicate_detector.py` | 47 | Module 04 |
| `src/core/test_hashing.py` | 4 | Module 04 |
| `src/pipeline/test_naming.py` | 69 | Module 05 |
| `src/pipeline/test_confidence.py` | 52 | **Module 06** |
| `src/storage/test_database.py` | 18 (2 Module 02 + 14 Module 04 + 2 Module 05 serialization tests — Module 06 needed no new serialization test, since its three owned fields are plain JSON primitives requiring no typed reconstruction) | Module 02 + 04 + 05 |
| `src/test_main.py` | 1 (new file — Module 06's own CLI-level idempotency test) | **Module 06** |
| **Total** | **352** | |

Module 06's own contribution: **53 new tests** (52 `test_confidence.py` + 1 new `src/test_main.py`), grown across this module's lifecycle: 50 `test_confidence.py` tests at initial implementation (347 total suite-wide) → 349 total suite-wide after the reconstructed Implementation Audit's M1/M2 fixes added 2 new tests (`test_confidence.py` reached 52) → 352 total suite-wide after Module 01's separately-versioned v1.0.1 post-freeze correction added 2 tests to `test_watch_ingest.py` and Module 06's own `src/test_main.py` added 1 CLI idempotency test. Modules 01–05's baseline (excluding Module 01's own +2) is unchanged from Module 05's own released count of 297.

Key groups in `test_confidence.py`: every one of the nine deduction rules individually and stacked, cap enforcement at the exact boundary for both required and optional categories (including a monkeypatched-taxonomy integration test proving the two caps are enforced independently), all four hard floors individually and stacked in fixed table order (including the Unknown-category/Corrupted-file single-identifier merge test), the `hard_floors_applied` data-flow guarantee, `compute_score()` hand-verified against `Rules/Confidence Rules.md`'s own worked example, score-clipping and tier-boundary tests, the eligibility filter, deterministic batch order (both log-order and byte-identical output values — the reconstructed Implementation Audit's M2 fix), action-log shape, defensive None-signals handling, the taxonomy cross-check regression test, and the exhaustive Module Contract immutability test.

Last confirmed run: 2026-07-11, `352 passed in 2.73s` (full suite). Module 01–05 isolated: unchanged from each module's own most-recently-verified baseline. Module 06 isolated (`test_confidence.py` + `src/test_main.py`): `53 passed`.

## Integration tests

`Tests/Module 06 Integration Test Plan.md` — a real six-module batch (`scan()` → `classify(provider=...)` → `extract(provider=...)` → `detect_duplicates()` → `suggest_naming()` → `score_confidence()`, via the real `src/main.py` CLI functions), routing fake providers for Module 02/03 judgment only (Module 06 itself needed no fake — fully deterministic), across 8 sections:

| Section | Cases | Result |
|---|---|---|
| Functional (F01–F11) | 11 | 11 PASS |
| Logging (LOG01–LOG03) | 3 | 3 PASS |
| Serialization (SER01–SER02) | 2 | 2 PASS |
| CLI wiring (CLI01) | 1 | 1 PASS |
| CLI-level idempotency (IDEM01–IDEM02) | 2 | 2 PASS |
| Cross-module Module Contract (C01–C02) | 2 | 2 PASS |
| Determinism (DET01) | 1 | 1 PASS |
| Regression (REG01–REG03) | 3 | 3 PASS |

**22 of 22 planned integration cases passed on final execution** (excluding the 3 regression cases, counted separately above). Two issues surfaced during harness development, both confirmed to be defects in this plan's own test harness, not in Module 06 or any of Modules 01–05: (1) `Contract_v1.pdf`/`Contract_v2.pdf`'s fake-provider `effective_date` values needed to disagree with their filename tokens (mtime-based engineering was lost on `git checkout`) — fixed in the harness; (2) `M06-CLI01`'s hardcoded expected tier-count dict was stale after fix (1) changed the real distribution — fixed in the harness. Re-execution after both corrections: all 22 planned cases passed.

## Defects found and fixed

**During the reconstructed Independent Implementation Audit (`IMPLEMENTATION_AUDIT.md`), 2 Medium findings, both design-committed §21 test-coverage gaps, not behavioral defects:**
- **M1 (Medium):** the "every deduction simultaneously" test §21 committed to was missing. Fixed: `test_all_nine_deduction_rules_simultaneously_with_cap_enforcement` added.
- **M2 (Medium):** the determinism test §21 committed to only checked action-log line order, not actual output values. Fixed: `test_batch_deterministic_order_reversed_input_produces_byte_identical_field_values` added.

**During UAT Run 1, a genuine Critical defect was found — in Module 01, not Module 06:**
- **Finding UAT-1 (Critical):** re-scanning a source folder already tracked in the metadata store, with real Module 02–06 output on those records, silently wiped every downstream-owned field back to its default. Root-caused to `build_file_record()` in `watch_ingest.py` always constructing a brand-new `FileRecord` even when re-identifying an already-tracked file, combined with `save_file_record()`'s whole-object-replace upsert. Classified primarily a Module 01 implementation defect against its own already-stated (but re-scan-silent) contract. Resolved as **Module 01's own** post-freeze correction #1 (`v1.0.0` → `v1.0.1`) under `Governance/FROZEN_MODULE_CHANGE_POLICY.md` — see `Release/Module01/RELEASE_NOTES.md` for the full record. Not a Module 06 defect: Module 06 behaved exactly as designed given the state Module 01 handed it.

**During the Release Audit, across three restart cycles, three genuine documentation/evidence findings, all resolved (see `RELEASE_AUDIT.md` for full chronology):**
- No written record of the Independent Implementation Audit existed anywhere — reconstructed from surviving evidence (`IMPLEMENTATION_AUDIT.md`).
- `Release/VERSIONS.md`'s Module 06 status row was stale ("Not started") — corrected to "Release Audit in progress" with a new dated History entry.
- No measured performance number existed for Module 06 — resolved with a real 75-file `Tests/Large Batch/` measurement (40.122 seconds).

## UAT summary

Two UAT runs, both executed exactly as production would: the real six-stage chain (`scan()` → `classify(provider=...)` → `extract(provider=...)` → `detect_duplicates()` → `suggest_naming()` → `score_confidence()`, via `src/main.py`'s actual CLI entry points) against an external, temporary Downloads-like folder (outside the project), using **live Claude judgment as the actual Module 02/03 providers** — Module 06 itself needed no provider (fully deterministic, §2).

**Run 1 (2026-07-11, archived at `Runtime/UAT/Module06_UAT_2026-07-11_162320/`):** 25 entries, 23 discovered, 2 skipped, reconciling exactly. Steps 1–7 (the entirety of Module 06's own scoring logic — every deduction, every hard floor, every tier) verified clean against real, live-judged content: all nine deduction rules and all four hard floors triggered at least once, full three-tier spread (9 `auto` / 5 `approval_required` / 9 `review_required`), every `confidence_breakdown`/`hard_floors_applied` entry hand-verified against `Rules/Confidence Rules.md`. Step 8 (idempotency) stopped immediately on Finding UAT-1 — a Critical, previously-undiscovered defect in Module 01, not Module 06.

**Restart (2026-07-11, archived at `Runtime/UAT/Module06_UAT_2026-07-11_232902_restart/`):** a genuine rebuild, not a resume — external dataset and real `Database`/`Runtime` state rebuilt/reset from scratch, holding every variable constant except the corrected Module 01 (`v1.0.0` → `v1.0.1`). Steps 1–6 clean, 23/23 files, same dimension coverage as Run 1 (tier spread 9/5/9). **Step 7 (idempotency): clean — the exact scenario that failed catastrophically in Run 1.** A full field-by-field diff confirmed every field of every record byte-identical except Module 01's own `batch_id`. Steps 8/9 (content-change re-scan): clean — a genuinely rewritten file correctly had all 17 downstream-owned fields reset and re-entered the full Module 02→06 pipeline with no code change needed anywhere. Step 10 (determinism/logging/serialization/Module Contract boundaries): clean, full regression suite 352/352 throughout. One self-caught, disclosed harness error during the determinism check (a log-path isolation gap, corrected, not a module defect — full detail in the restart's own `summary.md`).

`metadata_store.json`, `action_log.jsonl`, and a written summary preserved in both timestamped run folders.

**Caveat:** the same session that implemented Module 06 also defined the "correct" expected judgment answers for the UAT dataset's Module 02/03 steps, which `Governance/ENGINEERING_STANDARD.md` §6.3 requires disclosing as a non-solved limitation, not statistically meaningful judgment-quality validation — the same standing caveat applied to every earlier module's UAT. Module 06 itself has no provider and makes no judgment call (§2) — its own correctness is verified by deterministic, re-derivable arithmetic over whatever signals it's handed, a stronger form of evidence than judgment-quality sampling and not subject to the same caveat.

## Security review

- **The narrowest attack surface of any module built so far.** Module 06 never opens a file, never reads bytes, never reads text — narrower than every prior module, including Module 05 (which builds path strings) and Module 04 (which reads raw bytes for hashing).
- **No filesystem write, no filesystem read.** Module 06 produces only an `int`, a `dict[str, int]`, and a `str` — no path-injection surface exists to defend at all.
- **No new sensitive-value exposure.** Every value Module 06 reads has already passed through Module 03's structural redaction/closed-taxonomy controls before Module 06 ever sees it; Module 06 itself never logs or persists a raw metadata *value*, only field *names* (in `confidence_breakdown`'s keys) and booleans/counts.
- **Adversarial-input verification:** `test_defensive_none_signals_treated_as_no_signals` and `test_hard_floors_defensive_none_signals_never_trigger` (both re-run fresh and passing) construct a record with `classification_signals`/`duplicate_signals`/`naming_signals` unexpectedly `None` despite the eligibility filter's guarantees — the one real anticipated-failure class this module has — confirming graceful degradation ("no deductions from that source") rather than a crash.

## Regression tests

Full unit suite re-run after every change during this release cycle, 100% pass rate each time: 347 after initial implementation, 349 after the reconstructed Implementation Audit's M1/M2 fixes, unchanged through Integration Testing, 352 after Module 01's separately-versioned v1.0.1 patch and Module 06's own `src/test_main.py` addition, unchanged through the UAT restart, the Release Audit's three documentation/evidence fixes, and the performance measurement. Module 01–05 isolated re-run: confirmed unchanged throughout, most recently alongside Module 06's own tests.

## Performance observations

- **Real Module 01→06 chain measurement (Release Audit PCV Check 12):** 75 synthetic files (`Tests/Large Batch/`, the same batch size and methodology as Module 05's own baseline), instant fixed-answer fake providers standing in for Modules 02/03's live judgment, measured at **40.122 seconds** total wall-clock. All 75 records reached Module 05 and Module 06 (`confidence_score` populated); tier spread 9 `auto` / 9 `approval_required` / 57 `review_required` (dominated by the `unknown_category` hard floor, expected — `Tests/Large Batch/`'s files are random-byte placeholder content, not real documents). No optimization was performed or attempted.
- **Comparison against the Module 05 baseline (39.711 seconds):** a difference of **+0.411 seconds (+1.0%)** for one additional real pipeline stage — not an order-of-magnitude regression by any margin, consistent with Module 06's own design claim (§17) of being the cheapest per-file module built so far (no file content read, no string manipulation, no within-batch dict lookup).
- `save_file_record()`'s inherited O(N×M) full-store-rewrite cost, already disclosed by Modules 02–05 as their own inherited problem, is now also disclosed as Module 06's own concern (see `KNOWN_LIMITATIONS.md`).
