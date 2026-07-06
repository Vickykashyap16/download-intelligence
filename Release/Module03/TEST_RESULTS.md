# Test Results — Module 03 (Metadata Extraction)

Full detail lives in `Tests/Module 03 Integration Test Plan.md`, `Tests/Module 03 UAT Plan.md`, and `Runtime/UAT/`; this is the release-record summary. All counts below were re-verified by direct `pytest` execution during release-package preparation (2026-07-06), not carried forward from memory.

## Unit tests

**161 of 161 passing**, pytest, isolated `tmp_path`/`monkeypatch` fixtures, no real Database/Runtime files touched:

| File | Tests | Owner |
|---|---|---|
| `src/pipeline/test_watch_ingest.py` | 13 | Module 01 |
| `src/pipeline/test_classification.py` | 48 | Module 02 |
| `src/models/test_classification.py` | 6 | Module 02 |
| `src/storage/test_database.py` | 2 | Module 02 (typed-field serialization) |
| `src/core/test_pdf.py` | 6 | Module 02 |
| `src/core/test_text.py` | 7 | Module 02 |
| `src/core/test_images.py` | 7 | Module 02 |
| `src/core/test_exif.py` | 4 | Module 02 |
| `src/pipeline/test_metadata.py` | 57 | **Module 03** |
| `src/core/test_archive.py` | 7 | **Module 03** |
| `src/core/test_media.py` | 4 | **Module 03** |
| **Total** | **161** | |

Module 03's own contribution: **68 new tests** (57 + 7 + 4). Modules 01–02's baseline (93) is unchanged and re-confirmed passing alongside Module 03's.

Key groups in `test_metadata.py`: taxonomy/accessor tests (`required_fields()`/`optional_fields()`/`all_fields_for()`/`is_extraction_complete()`), deterministic-extraction tests per category (Archive, Application, Video, Audio — each with a provider that raises if ever called, proving it never is), Image/Screenshot mixed-mode tests (EXIF-sourced `capture_date`, vision-only judgment field, capture_date never substituting a filesystem timestamp), provider-boundary tests (ABC enforcement, `FakeMetadataExtractionProvider`, `ClaudeLiveExtractor`'s documented placeholder), `MetadataExtractionEngine` tests (every deterministic/text/vision/fallback path), `_validate_and_merge()` tests (closed-taxonomy dropping, type rejection including the four boolean-validation regression tests added for F1, the exact Bank Statement `account_last4` digit-count boundary cases), `extract_metadata_batch()` tests (persistence, non-owned-field immutability, log shape, provider metadata, resilience to an unexpected internal failure), and the two taxonomy-drift regression tests added for F2 (citation-target and full-table cross-check against `Rules/Confidence Rules.md`/`Module 03 Design.md`).

Last confirmed run: 2026-07-06, `161 passed in 2.43s` (full suite); `test_metadata.py` alone `57 passed in 0.69s`; `test_archive.py` `7 passed in 0.03s`; `test_media.py` `4 passed in 0.03s`.

## Integration tests

`Tests/Module 03 Integration Test Plan.md` — **59 of 59 executable cases pass**, run against the real code end-to-end (`scan_source()` → `classify_batch()` → `extract_metadata_batch()`) using `Samples/*`, five reused `Tests/` datasets, and one new dataset built for this plan (`Tests/Module 03 Metadata/`):

| Section | Cases | Result |
|---|---|---|
| Functional (F01–F11) | 11 | 11 PASS |
| Cross-module contract (C01–C04) | 4 | 4 PASS |
| Metadata correctness (MC01–MC03) | 3 | 3 PASS |
| Required/optional validation (RO01–RO03) | 3 | 3 PASS |
| Privacy/redaction (PR01–PR03) | 3 | 3 PASS |
| Timestamp hierarchy (TS01–TS05) | 5 | 5 PASS |
| Deterministic extraction (DET01–DET04) | 4 | 4 PASS |
| AI-assisted extraction (AI01–AI03) | 3 | 3 PASS |
| Failure (X01–X04) | 4 | 4 PASS |
| Corrupted file (CORR01–CORR04) | 4 | 4 PASS |
| Locked file (LOCK01) | 1 | 1 PASS |
| Unsupported metadata (UNS01–UNS03) | 3 | 3 PASS |
| Mixed batch (MIX01–MIX02) | 2 | 2 PASS |
| Performance (PERF01) | 1 | measured, see below |
| Security (SEC01–SEC03) | 3 | 3 PASS |
| Database (DB01–DB02) | 2 | 2 PASS |
| Logging (LOG01–LOG03) | 3 | 3 PASS |

First pass: 55/59 (4 failures, all confirmed test-harness bugs, not implementation defects — see below). Re-execution after harness fixes: **59/59 pass.**

## Defects found and fixed

**During integration testing — 4 test-harness bugs, zero implementation defects:**
- `RoutingClassificationProvider.classify()` returned a bare `ClassificationResult` instead of the real provider contract's `ProviderResponse` wrapper; `ClassificationEngine`'s own outer safety net correctly caught the mismatch (silently left `category=None`) rather than crashing — exactly the resilience Module 02's design specifies. Fixed in the harness.
- M03-UNS03 asserted the entire batch's provider-request list was empty, but the batch also legitimately contained a real EXIF photo needing its own judgment call. Scoped the assertion to Archive's own request only.
- M03-MIX01 assumed `mystery_file.xyz` would reach Module 02/03 as `Category.UNKNOWN`; verified directly that Module 01's `SUPPORTED_EXTENSIONS` doesn't include `.xyz` at all, so it's filtered out at Module 01 itself. Corrected the assertion to match verified reality.
- M03-SEC03's log-entry lookup grabbed the alphabetically-first `extract_metadata` entry instead of the intended screenshot entry. Fixed to filter for the specific file.

**During the independent implementation audit (`Build-out/03 Metadata Extraction/Module 03 Implementation Audit.md`), 2 Medium findings resolved in code, 1 Low and 1 Cosmetic resolved in documentation:**
- **F1 (Medium):** `_validate_and_merge()`'s type check silently admitted Python `bool` (a subclass of `int`) as a valid value for any field, though no field in the taxonomy is boolean-shaped. Fixed: explicit `bool` exclusion added before the `isinstance` check; four regression tests added.
- **F2 (Medium):** the taxonomy-drift regression test the design committed to (§20) — verifying `Rules/Confidence Rules.md`'s citation targets a real, current document — was never built. Fixed: two regression tests added (citation-target check, full-table cross-check).
- **F3 (Low):** `Rules/Confidence Rules.md` cited the superseded pre-design pointer doc. Citation updated; no business logic changed.
- **F4 (Cosmetic):** `Module 03 Design.md` §13's illustrative JSON example was inconsistent with the (more correct) implemented logging contract. Example updated; no code changed.

**During the independent release audit (`Release/Module03/RELEASE_AUDIT.md`), 3 Medium and 2 Low findings resolved, all outside `src/pipeline/metadata.py`:**
- **F1 (Medium):** the project's real `Database/`/`Runtime/` files contained synthetic debug data from an earlier un-isolated debugging session. Investigated, archived (not deleted), and reset to a clean empty state across two verified stages.
- **F2 (Medium):** `extract_metadata` was entirely undocumented in the canonical `Metadata & Log Schema.md` — the same category of gap already caught once for Module 02's `classify`. Fixed.
- **F3 (Low):** `Metadata & Log Schema.md` also cited the superseded pointer doc. Fixed.
- **F4 (Medium):** `src/README.md`'s Status section didn't mention Module 03 at all. Fixed.
- **F5 (Low):** `Rules/Naming Rules.md`'s Contract/Audio templates don't cleanly match the real taxonomy field names. Recorded in `KNOWN_LIMITATIONS.md` as deferred to Module 05's design, per instruction not to edit `Naming Rules.md` prematurely.

See `IMPLEMENTATION_AUDIT.md` and `RELEASE_AUDIT.md` for full findings, evidence, and verification.

## UAT summary

One full user-acceptance run, executed exactly as production would: the real three-module chain (`scan()` → `classify(provider=...)` → `extract(provider=...)`, via `src/main.py`'s actual CLI entry points) against an external, temporary Downloads-like folder (`/tmp/uat_m03_downloads`, 19 files, outside the project), using **live Claude judgment as the actual classification and metadata-extraction providers** (not fakes/canned responses) — archived under `Runtime/UAT/Module03_UAT_2026-07-06_100928/`:

- 16 discovered, 3 skipped (`.DS_Store` → `system_file`, `empty_placeholder.pdf` → `zero_byte`, `movie_download.torrent` → `unsupported_extension`) — 19 total, reconciling exactly.
- Every deterministic-only file (Video, Archive, Application) and the deliberately corrupted archive were handled correctly with zero provider calls where deterministic.
- The real-EXIF photo (`IMG_4821.jpg`) and the no-EXIF screenshot both produced correct, defensible extraction from real content read live.
- **Deliberate adversarial redaction test:** the full, real account number from `Chase_Statement_June2026.pdf`'s actual text was fed as the "live" answer for `account_last4` (not a well-behaved, pre-truncated answer) — the Engine's own structural redaction rule caught and redacted it to `null`, proving the defense holds against an imperfect provider response, not just a well-behaved one. Verified via direct grep: the full account number appears nowhere in `metadata_store.json` or `action_log.jsonl`.
- No unhandled exception anywhere in the run.

`metadata_store.json`, `action_log.jsonl`, `terminal_output.txt`, and `summary.md` preserved in the timestamped run folder, covering all 20 requested verification dimensions.

**Caveat (same standard Module 02's own `TEST_RESULTS.md` applies to its UAT):** this run validates that Module 03's architecture correctly delegates to live Claude judgment and that the redaction/timestamp/logging mechanics hold against real content — it is not independent, statistically meaningful validation of judgment quality at scale. The sample is small (9 judgment-dependent extraction calls, one run) and self-graded (the same agent that implemented the extractor also read the files and defined the expected answers).

## Security review

- **No code execution risk from file contents** — confirmed by code review (`core/archive.py` only calls `zipfile.namelist()`, never decompresses entry contents; `core/media.py`/`mutagen` reads tag metadata only) and by SEC01 completing safely against a zip with a corrupted-content (but validly-named) entry.
- **Provider boundary is a real trust boundary** — `_validate_and_merge()` rejects any field name outside the category's closed taxonomy and any value that isn't a plain, correctly-typed `str`/`int`/`float` (including the `bool` exclusion, F1), regardless of provider behavior.
- **Redaction is structural, not prompt-dependent** — verified against a deliberately non-self-censoring live provider during UAT, not only against a well-behaved fake during unit/integration testing.
- **Action log JSON safety for adversarial field values** — a `context_description` string containing quotes/newlines/tabs round-trips through `action_log.jsonl` exactly (SEC03).

## Regression tests

Full unit suite re-run after every change during this release cycle, 100% pass rate each time: 155 tests after initial implementation, 161 after the implementation audit's F1/F2 fixes (6 new regression tests), unchanged at 161 through integration testing, UAT, and the release audit (all of whose fixes were outside `src/pipeline/*.py`). Module 01/02 isolated re-run (`test_watch_ingest.py` + `test_classification.py` + supporting `core`/`models`/`storage` tests): confirmed unchanged throughout, most recently 118/118 alongside Module 03's own tests.

## Performance observations

- `Tests/Large Batch/` (75 files) through the full classify→extract chain (fake provider, near-zero simulated latency): **0.280 seconds.** No algorithmic concern.
- A real run's actual wall-clock time is dominated by how long live Claude judgment takes per file — not measurable via automated timing, only observable during a live run.
