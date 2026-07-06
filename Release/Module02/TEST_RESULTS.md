# Test Results — Module 02 (Classification)

Full detail lives in `Tests/Module 02 Integration Test Plan.md`, `Tests/Module 02 UAT Plan.md`, and `Runtime/UAT/`; this is the release-record summary.

## Unit tests

`src/models/test_classification.py` (6), `src/storage/test_database.py` (2), `src/core/test_pdf.py` (6), `src/core/test_text.py` (7), `src/core/test_images.py` (7), `src/core/test_exif.py` (4), `src/pipeline/test_classification.py` (48), `src/pipeline/test_watch_ingest.py` (13, Module 01, unaffected) — **93 of 93 passing**, pytest, isolated `tmp_path`/`monkeypatch` fixtures, no real Database/Runtime files touched. (Corrected 2026-07-06: an earlier draft of this document stated 46 for `test_classification.py` and omitted `test_watch_ingest.py` from the per-file breakdown — an arithmetic error caught during the independent release audit, F10. The 90-test aggregate before the audit's fixes, and 93 after, were both otherwise accurate.)

Key groups in `test_classification.py`: deterministic-function tests (extension routing, screenshot/image split, locked-PDF detection, non-English detection), provider-boundary tests (ABC enforcement, `FakeClassificationProvider` double, `ClaudeLiveClassifier`'s documented placeholder), `ClassificationEngine` tests (every deterministic/text/vision/fallback path, including `error_detail` capture — added post-audit, F3), `classify_batch()` tests (persistence, unreadable-passthrough, log shape, provider metadata, resilience to a vanished/unreadable file), and two Module Contract regression tests added after the release audit (F2): a field-immutability test and an extension-mapping drift test.

Last confirmed run: 2026-07-06 (post-audit-fixes), `93 passed in 2.04s`.

## Integration tests

`Tests/Module 02 Integration Test Plan.md` — **26 of 26 executable cases pass** (after one defect was found and fixed during the original run, and re-confirmed after the independent release audit's fixes — see below), run against the real code using `Samples/*`, five reused `Tests/` datasets, and one new dataset built for this plan (`Tests/Module 02 Classification/`):

| Section | Cases | Result |
|---|---|---|
| Functional (F01–F07) | 7 | 7 PASS |
| Boundary (B01–B06) | 6 | 6 PASS (B06 failed on first execution, fixed, re-run PASS) |
| Edge (E01–E04) | 4 | 4 PASS |
| Failure (X01–X04, +X03b) | 5 | 5 PASS |
| Performance (P01) | 1 | measured, see below |
| Security (S01–S03) | 3 | 3 PASS |

Re-executed in full after the independent release audit's code changes (F3/F4/F6) — all 26 cases still pass with no change in expected outcomes.

## Defects found and fixed

**During integration testing:** `ClassificationEngine.classify_file()`'s deterministic image-split branch (`classify_screenshot_or_image()`, which opens files via PIL) had no error handling, unlike the already-wrapped text-bearing branch. Surfaced by `Tests/Large Batch/`'s 75-file run (M02-B06): its synthetic `.jpg`/`.png` fixtures are placeholder bytes, not real image content, and 20 of 75 files raised uncaught out of `classify_file()`, leaving them with `category=None` and an `error` log entry instead of a graceful fallback. Fixed by wrapping the image-split branch the same way the text-bearing branch already was — it now returns `Category.UNKNOWN` with `fallback_used=True`, `fallback_reason="unreadable_content"`. Re-verified: all 75 files now get a real category or `Category.UNKNOWN`. Full writeup: `Tests/Module 02 Integration Test Plan.md` Section 10; `CHANGELOG.md`, 2026-07-06.

**During the independent release audit (`RELEASE_AUDIT.md`), three High and three Medium findings were resolved in code:**
- **F3 (High):** fallback paths (`extraction_failed`, `unreadable_content`, `provider_exception`, `invalid_response`) previously discarded the actual exception message. Fixed: added `EngineResult.error_detail`, a sanitized/length-bounded diagnostic string, populated on every fallback path and included in the `classify` action-log entry.
- **F2 (High):** two tests promised by the frozen design (§16/§19) but never implemented — a Module Contract field-immutability test and an extension-mapping drift test. Both added as permanent regression tests.
- **F6 (Medium):** the `extraction_failed` fallback path left `no_extractable_text` at its default `False` even though the file genuinely had no usable text. Fixed to set it `True`, matching the sibling no-content case.
- **F4 (Medium):** `.tar` was missing from `_EXTENSION_CATEGORY_MAP` despite being listed in `Rules/Classification Rules.md`. Fixed, and now guarded by `test_extension_category_map_matches_rules_taxonomy`.
- **F5 (Medium):** the `classify` action type was missing from `Build-out/08 .../Metadata & Log Schema.md` and `runtime_io.py`'s docstring. Both corrected.
- **F1 (High, documentation only):** unqualified "Production Ready" wording across `MODULE_STATUS.md`/`RELEASE_NOTES.md`/`PRODUCTION_CHECKLIST.md`/`MODULE_CONTRACT.md` did not distinguish interactive Claude-assisted operation from autonomous production readiness. Corrected across all four documents plus `KNOWN_LIMITATIONS.md`.

See `RELEASE_AUDIT.md` for full findings and `RELEASE_AUDIT_2.md` for the follow-up audit verifying these were resolved correctly.

## UAT summary

One full user-acceptance run, executed exactly as production would: Module 01's real `scan_source()` against an external, temporary Downloads-like folder (`/tmp/uat_m02_downloads`, 18 files, outside the project), followed by Module 02's real `classify_batch()` using **live Claude judgment as the actual provider** (not a fake/canned response) — archived under `Runtime/UAT/Module02_UAT_2026-07-06_015818/`:

- 16 discovered, 2 skipped (`system_file`, `unsupported_extension`) — matches expectation exactly.
- All 16 discovered files received a correct, defensible category. The live provider was invoked exactly 8 times — precisely the files needing real judgment; the other 8 (deterministic/locked/malformed) never reached it.
- The deliberately hard case (`payment_confirmation.pdf`, worded "RECEIPT / INVOICE" describing a completed payment) was correctly flagged `ambiguous=True` rather than confidently misclassified — the intended judgment-quality test.
- The non-English (French) invoice was classified correctly with `non_english_detected=True`/`detected_language="fr"` captured independently of the category decision.
- No exception occurred during either the scan or classification phase.

`metadata_store.json`, `action_log.jsonl`, `terminal_output.txt`, and `summary.md` preserved in the timestamped run folder.

**Caveat, added after the independent release audit (F7):** this run validates that Module 02's architecture correctly delegates to live Claude judgment when running inside an interactive, agent-driven session — it is not independent validation of judgment quality at scale. The sample is small (8 judgment calls, one run) and self-graded (the same agent that implemented the classifier also wrote the test files and defined the expected answers, including the "correct" resolution of the deliberately ambiguous case). Treat this as a successful plumbing/architecture validation with one well-reasoned hard-case demonstration, not as a statistically meaningful judgment-quality benchmark. A second, independent rating pass (a different session/context, or the project owner spot-checking some of the eight calls) would strengthen this claim if judgment quality at scale becomes a concern.

## Security review

- **No code execution risk from file contents** — confirmed by code review (`pdfplumber`/`pypdf`/`python-docx`/`langdetect` only, no archive extraction, no shelling out) and by M02-E03/M02-B01 completing safely against adversarial-shaped input.
- **Provider boundary is a real trust boundary** — `ClassificationEngine._validate_category()` rejects any string that isn't a real `Category` enum member, including an adversarial injection-shaped string (M02-S02) — identical treatment to an ordinary invalid response.
- **Action log JSON safety for adversarial provider metadata** — a `reasoning` string containing quotes/newlines/tabs round-trips through `action_log.jsonl` exactly, confirmed via `json.loads()` (M02-S03).

## Regression tests

Full unit suite re-run after every change, 100% pass rate each time: 90 tests after the integration-testing image-read-failure fix (one test renamed/updated — `test_classify_batch_gracefully_falls_back_for_a_vanished_image_file` — and one new regression test added — `test_classify_batch_outer_safety_net_still_covers_truly_unanticipated_failures`); **93 tests after the independent release audit's fixes** (three more tests updated to assert `error_detail`/`no_extractable_text` per F3/F6, plus the two new F2 contract tests).

## Performance observations

- A full `Tests/Large Batch/` run (75 files) with `FakeClassificationProvider` (near-zero simulated latency) took **0.25 seconds** — Module 02 has no deliberate per-file delay (unlike Module 01's stability-check sleep), so this is dominated by PDF/DOCX parsing cost.
- A real run's actual wall-clock time is dominated by how long live Claude judgment takes per file — not measurable via automated timing, only observable during a live run (see `Tests/Module 02 Integration Test Plan.md` Section 8).
