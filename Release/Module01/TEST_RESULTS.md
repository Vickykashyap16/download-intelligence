# Test Results — Module 01 (Watch & Ingest)

Full detail lives in `Tests/Module 01 Validation & Test Plan.md` and `Runtime/UAT/`; this is the release-record summary.

## Unit tests

`src/pipeline/test_watch_ingest.py` — **13 of 13 passing** (pytest, isolated `tmp_path`/`monkeypatch` fixtures, no real Database/Runtime files touched):

- `test_is_ignored_name_matches_known_junk`
- `test_classify_ignored_name_returns_specific_reason` *(added for the UAT-driven skip-reason change)*
- `test_is_supported_extension`
- `test_get_extension_is_lowercased`
- `test_is_zero_byte`
- `test_generate_new_file_id_is_random_each_call`
- `test_build_file_record_reads_supported_file`
- `test_build_file_record_two_different_files_get_different_ids`
- `test_build_file_record_reuses_id_for_unmoved_file`
- `test_build_file_record_flags_content_change_at_same_path`
- `test_scan_source_skips_ignored_and_unsupported` *(updated to assert `system_file`/`temporary_download`)*
- `test_scan_source_skips_symlinks_without_following_them` *(regression test for the symlink defect)*
- `test_scan_source_raises_on_missing_directory`

Last confirmed run: 2026-07-06, `13 passed in 1.07s`.

## Integration tests

`Tests/Module 01 Validation & Test Plan.md` — **27 of 27 executable cases pass**, run against the real code (not just planned) using `Samples/*` and six `Tests/` datasets (Small Batch, Mixed Downloads, Duplicate Files, Corrupted Files, Large Batch, Edge Cases):

| Section | Cases | Result |
|---|---|---|
| Functional (F01–F07) | 7 | 7 PASS |
| Boundary (B01–B06) | 7 | 7 PASS |
| Edge (E01–E07) | 7 | 7 PASS |
| Failure (X01–X05) | 5 | 5 PASS |
| Security (S01–S05) | 3 executable + 2 analysis-only | 3 PASS, 2 N/A by design |

One gap not yet executed: **M01-S05** (adversarial filename vs. action-log JSON safety) — needs one additional dataset file. Tracked in `KNOWN_LIMITATIONS.md`, not blocking.

## UAT summary

Two full user-acceptance runs, each executed exactly as an end user would (`python -m src.main` against a real, external, temporary Downloads-like folder — `/tmp/uat_downloads`, outside the project), archived under `Runtime/UAT/`:

- **Run 1** (`Module01_UAT_2026-07-05_190028/`): 7 discovered, 5 skipped, 12 total, reconciled exactly. Found two gaps: terminal output didn't show skipped items, and skip reasons were too generic (`ignored_name` covering two distinct cases).
- **Run 2** (`Module01_UAT_2026-07-05_191108/`): rerun after both fixes, same test data, same 7/5/12 outcome. Confirmed the CLI now prints the full summary and specific reasons (`system_file`, `temporary_download`) correctly. One small import bug in the fix itself was caught and corrected during this rerun before it was reported complete.

Each run's `metadata_store.json`, `action_log.jsonl`, `terminal_output.txt`, and `summary.md` are preserved in their own timestamped folder; the real `Database/`/`Runtime/` files were reset to empty after each run so the project's true first scan starts clean.

## Security review

- **Symlink traversal** — defect found and fixed (see `RELEASE_NOTES.md`); regression test in place and passing.
- **Permission-locked/unreadable files** — handled via `status: "unreadable"` + recorded error, no crash, no privilege-escalation attempt. Verified against a real `chmod`-restricted file.
- **Path traversal via filename** — considered and ruled out: `iterdir()` only yields OS-resolved direct children; no user-supplied path string is concatenated or parsed by this module.
- **Code execution from file contents** — considered and ruled out: the only content-touching operation is byte-level SHA-256 hashing; `mimetypes.guess_type()` is a pure filename string match. No archive extraction, no document parsing.
- **Action-log injection via filename** — identified as an untested gap (M01-S05); not yet executed, tracked in `KNOWN_LIMITATIONS.md`.

## Regression tests

Full unit suite (13 tests) re-run after every code change made during this release cycle — the symlink fix, the file_id redesign, and the CLI/skip-reason UAT fixes — with 100% pass rate confirmed each time, most recently 2026-07-06.

## Performance observations

- Single real scan of 75 files (`Tests/Large Batch/`, unpatched real 0.5-second stability interval): **38.12 seconds**, all 75 correctly discovered with unique `file_id`s. Confirms the sequential per-file stability check as the dominant cost at volume — not an algorithmic problem, informational only, since v1 is Manual mode.
- `find_by_current_path()`'s linear scan was not a measurable bottleneck at tested volumes (dozens to 75 records) but is flagged in `KNOWN_LIMITATIONS.md` as the first thing to revisit if the store grows substantially.
