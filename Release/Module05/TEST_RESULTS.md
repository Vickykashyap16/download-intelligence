# Test Results — Module 05 (Naming & Destination)

Full detail lives in `Build-out/05 Naming & Destination/Module 05 Integration Test Plan.md`, `Tests/Module 05 UAT Plan.md`, and `Runtime/UAT/`; this is the release-record summary. All counts below were re-verified by direct `pytest` execution during release-package preparation (2026-07-09), not carried forward from memory.

## Unit tests

**297 of 297 passing**, pytest, isolated `tmp_path`/`monkeypatch` fixtures, no real Database/Runtime files touched:

| File | Tests | Owner |
|---|---|---|
| `src/pipeline/test_watch_ingest.py` | 13 | Module 01 |
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
| `src/pipeline/test_naming.py` | 69 | **Module 05** |
| `src/storage/test_database.py` | 18 (2 Module 02 + 14 Module 04 + 2 **Module 05** serialization tests) | Module 02 + 04 + **Module 05** |
| **Total** | **297** | |

Module 05's own contribution: **71 new tests** (69 + 2), grown across this module's lifecycle: 48 `test_naming.py` + 2 `storage/test_database.py` at initial implementation (276 total suite-wide) → 290 total suite-wide after the first Independent Implementation Audit's M1–M3/L1/L2 fixes added 14 new tests (`test_naming.py` reached 62) → 297 total suite-wide after post-freeze correction #1 added 7 whitespace-normalization regression tests (`test_naming.py` reached 69). Modules 01–04's baseline (226) is unchanged and re-confirmed passing alongside Module 05's.

Key groups in `test_naming.py`: per-category template-filling correctness for all twelve categories including every confirmed fallback path (required and optional fields, closed during the first audit's M3 remediation), sanitization boundary cases (whitespace normalization added by post-freeze correction #1; whitelist character filtering; Title_Case; iterative longest-segment truncation, corrected by M2, including the multi-segment-overflow case; an adversarial path-traversal test), within-batch collision resolution (including the `(destination, name)` key scoping test), destination override precedence (exact-duplicate, superseded-version, none), `Category.UNKNOWN` end-to-end, deterministic batch-processing order/re-run stability, action-log shape, and the exhaustive Module Contract immutability test (every non-owned `FileRecord` field, built exhaustively from the start, unlike Module 04's own first-pass implementation which needed a follow-up finding to reach that rigor). `test_database.py`'s Module 05 additions cover `naming_signals`'s round-trip serialization and graceful handling of a pre-Module-05 record.

Last confirmed run: 2026-07-09, `297 passed in 2.63s` (full suite). Module 01–04 isolated (`test_watch_ingest.py` + `test_classification.py` + `models/test_classification.py` + `core/test_pdf.py` + `core/test_text.py` + `core/test_images.py` + `core/test_exif.py` + `test_metadata.py` + `core/test_archive.py` + `core/test_media.py` + `test_duplicate_detector.py` + `core/test_hashing.py`): unchanged from Module 04's own 226-test baseline (minus Module 05's 71 net-new). Module 05 isolated (`test_naming.py` + `storage/test_database.py`'s 2 additions): `71 passed`.

## Integration tests

`Build-out/05 Naming & Destination/Module 05 Integration Test Plan.md` — a real five-module batch (`scan()` → `classify(provider=...)` → `extract(provider=...)` → `detect_duplicates()` → `suggest_naming()`, via the real `src/main.py` CLI functions), routing fake providers for Module 02/03 judgment, across nine sections:

| Section | Cases | Result |
|---|---|---|
| Functional (F01–F05) | 5 | 5 PASS |
| Cross-module contract (C01–C02) | 2 | 2 PASS |
| Collision handling (COLL01–COLL02) | 2 | 2 PASS (COLL02 an emergent, unplanned-but-genuine confirmation) |
| Override behavior (OVR01–OVR03) | 3 | 3 PASS |
| Determinism (DET01) | 1 | 1 PASS |
| Serialization (SER01) | 1 | 1 PASS |
| Logging (LOG01) | 1 | 1 PASS |
| CLI orchestration (CLI01–CLI02) | 2 | 2 PASS |
| Regression (REG01–REG03) | 3 | 3 PASS |

**All planned cases passed on first execution — no harness-authoring errors encountered this pass** (unlike Module 04's own Integration Testing, which needed two harness corrections). Zero implementation defects found.

## Defects found and fixed

**During the first Independent Implementation Audit (`Build-out/05 Naming & Destination/Module 05 Implementation Audit.md`, first pass), 3 Medium + 2 Low + 1 Cosmetic findings:**
- **M1 (Medium):** `naming_signals.fields_fell_back` recorded synthetic, non-taxonomy field names (`"date"`, `"version_or_date"`) for Video and Resume's fallback cases, contradicting `NamingSignals`'s own documented "real taxonomy field name" contract. Fixed: both now record real field names (`"modified_at"`, `"version_indicator"`/`"last_modified_date"`).
- **M2 (Medium):** `_truncate_longest_segment()`'s single-pass truncation did not guarantee the ~80-character cap when overflow exceeded the single longest segment's own length, and could leave a stray/doubled underscore. Fixed: made iterative, with empty segments dropped before the final join; verified via mutation testing.
- **M3 (Medium):** five categories (Bank Statement, Contract, Image, Screenshot, Application) had zero fallback-path test coverage and Document was missing its required-field case, contrary to the design's §22 test-strategy commitment. Fixed: nine tests added.
- **L1 (Low):** a hedged test assertion (`"6.1"` vs `"61"`) on a fully deterministic outcome. Fixed: single correct assertion.
- **L2 (Low):** duplicated override-detection logic between `resolve_destination()` and `NamingEngine.suggest_file()` with no drift guard. Fixed: duplication removed entirely via a shared `_determine_override()` helper.
- **C1 (Cosmetic):** `_SIMPLE_TEMPLATES`'s type annotation didn't accurately describe `"literal"` entries. Zero runtime impact — carried forward, not fixed as part of this release (see `KNOWN_LIMITATIONS.md`).

**Re-verified independently on a second Implementation Audit pass:** M1, M2, M3, L1, L2 all resolved and confirmed with no remaining issue; C1 confirmed still open, unchanged, out of scope. Suite grew from 276 to 290 (14 net new tests).

**Discovered during UAT Run 1, independently verified as a design-completeness gap (not an implementation defect), corrected as post-freeze correction #1, and re-verified clean on a third Implementation Audit pass:**
- **Finding UAT-1 (Medium):** `sanitize_filename()`'s whitelist-only character filtering stripped internal whitespace entirely rather than converting it to `_`, undermining the module's own "human-readable filename" purpose for the majority of real, multi-word content observed in that run (8 of 17 discovered files, 47%). Fixed: whitespace now converts to `_` before the whitelist filter runs. Seven new regression tests added, confirmed genuinely load-bearing via mutation testing (temporarily disabling the fix reproduces the exact UAT-1 symptom, then cleanly reverted). Suite grew from 290 to 297.

**During the final Release Audit (`RELEASE_AUDIT.md`), 4 Medium + 1 Cosmetic findings, all resolved (second pass, same document):**
- **F1 (Medium):** `src/README.md`'s Module 05 status bullet was stale and, in the sanitization description, factually wrong. Fixed.
- **F2 (Medium):** `CHANGELOG.md` had dated entries for only 2 of Module 05's roughly 8 lifecycle stages. Fixed: six new entries added.
- **F3 (Medium):** no measured (only estimated) performance number existed for Module 05 against a realistic batch size. Fixed: 75-file real Module 01→05 chain measured at 39.711 seconds.
- **F4 (Medium, pre-existing/inherited):** `Governance/PROJECT_ROADMAP.md` was severely stale, predating Module 04's entire released lifecycle. Fixed.
- **C1 (Cosmetic):** `Module 05 Design.md` retained two small pieces of pre-freeze language. Fixed.

See `IMPLEMENTATION_AUDIT.md` and `RELEASE_AUDIT.md` for full findings, evidence, and verification.

## UAT summary

Two UAT runs, both executed exactly as production would: the real five-module chain (`scan()` → `classify(provider=...)` → `extract(provider=...)` → `detect_duplicates()` → `suggest_naming()`, via `src/main.py`'s actual CLI entry points) against an external, temporary Downloads-like folder (`/tmp/uat_m05_downloads`, outside the project), using **live Claude judgment as the actual Module 02/03 providers** — Module 05 itself needed no provider (fully deterministic, §17).

**Run 1 (2026-07-09, archived at `Runtime/UAT/Module05_UAT_2026-07-09_034717/`):** 17 discovered, 2 skipped, reconciling exactly. Stopped immediately, per the standing "stop, don't auto-fix" instruction, on discovering a genuine, real finding: Finding UAT-1 (whitespace stripped instead of converted to underscore). Full finding (root cause, impact, smallest recommended fix) archived alongside the real console transcript and persisted `metadata_store.json`/`action_log.jsonl`.

**Restart (2026-07-09, after the post-freeze correction #1 design-correction cycle, archived at `Runtime/UAT/Module05_UAT_2026-07-09_041725/`):** reused the exact same external dataset and the exact same live-judgment answers as the original stopped Run 1, isolating the fix as the only variable.
- All 8 previously-affected files now produce correctly underscore-separated names.
- Everything else reproduced identically to the original Run 1 (same scan/classification/extraction outcomes, same duplicate/version detection, same collision suffix, same overrides, same fallback field names).
- Idempotency (Run 2): a second `suggest_naming()` call changed 0 records, appended 0 log entries.
- A dedicated, deeper 13-case adversarial sanitization pass (nested path traversal, script-injection-style content, reserved characters, overflow length, zero-width-space scope boundary) — §19's path-injection guarantee confirmed still holding with the new whitespace-normalization step in place.

`metadata_store.json`, `action_log.jsonl`, `terminal_output_run1.txt`, `terminal_output_run2_idempotency.txt`, and `summary.md` preserved in both timestamped run folders.

**Caveat:** the same session that implemented Module 05 also defined the "correct" expected judgment answers for the UAT dataset, which `Governance/ENGINEERING_STANDARD.md` §6.3 requires disclosing as a non-solved limitation, not statistically meaningful judgment-quality validation — the same standing caveat applied to every earlier module's UAT. Module 05 itself has no provider and makes no judgment call (§17) — its own correctness is verified by deterministic, re-derivable computation over whatever category/fields it's handed, a stronger form of evidence than judgment-quality sampling and not subject to the same caveat, the same distinction Module 04's own UAT summary drew.

## Security review

- **No new code-execution surface.** Module 05 never reads file bytes or content at all — a narrower attack surface than every earlier module, including Module 04 (which at least reads raw bytes for hashing).
- **No filesystem writes, no filesystem reads of the destination library** — Module 05 cannot be tricked by a malicious destination-folder state, because it never looks at one.
- **Path-injection guarantee held throughout, including after post-freeze correction #1.** Sanitization's whitelist-only character filtering structurally excludes path separators and traversal sequences by construction. Verified adversarially at the unit level (`test_sanitize_filename_never_produces_path_traversal_sequences`, `test_build_filename_adversarial_extracted_metadata_never_produces_traversal`), at the UAT level (a real adversarial filename with emoji/em-dash, plus a dedicated 13-case adversarial pass in the UAT restart covering nested path traversal, script-injection-style content, and reserved characters), and independently re-confirmed during both the third Implementation Audit and the Release Audit that the new whitespace-normalization step does not reopen this guarantee (`/` and `..` are not whitespace, so they still reach the unchanged whitelist filter).
- **Zero-width-space (U+200B) scope-boundary check:** confirmed correctly *not* treated as whitespace by the `\s`-based normalization (Python's `\s` class doesn't match it, unlike U+00A0 non-breaking space, which does) — still stripped by the whitelist like any other disallowed character, verifying the fix's scope is precisely "matches Python's `\s`," not "any invisible-looking character."

## Regression tests

Full unit suite re-run after every change during this release cycle, 100% pass rate each time: 276 after initial implementation, 290 after the first Implementation Audit's M1–M3/L1/L2 fixes, unchanged through Integration Testing, 297 after post-freeze correction #1's fix during the UAT-driven design-correction cycle, unchanged through the UAT restart and the Release Audit's documentation-only fixes. Module 01–04 isolated re-run: confirmed unchanged throughout, most recently 226/226 alongside Module 05's own tests.

## Performance observations

- **Real Module 01→05 chain measurement (Release Audit finding F3):** 75 synthetic files (`Tests/Large Batch/`, the same batch size as Module 04's own `M04-PERF01` precedent) through the complete real five-module chain, instant fixed-answer fake providers standing in for Modules 02/03's live judgment, measured at **39.711 seconds** total wall-clock. All 75 records reached Module 05 and received a real `suggested_name`; 39 fell back to `Category.UNKNOWN` via genuine parsing-failure recovery on the fixtures' random-byte placeholder content (expected, not a defect). No optimization was performed or attempted.
- Module 05's own design argues its per-file work (template fill, string sanitization, a within-batch dict lookup) is O(1) per file relative to batch size, not a scan of accumulated history the way Module 04's index lookups are (`Module 05 Design.md` §20) — this measurement is consistent with that claim, though no isolated per-file cost was separately measured.
- `save_file_record()`'s inherited O(N×M) full-store-rewrite cost, already disclosed by Modules 02–04 as their own inherited problem, is now also disclosed as Module 05's own concern (see `KNOWN_LIMITATIONS.md`).
