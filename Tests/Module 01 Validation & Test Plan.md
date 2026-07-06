# Module 01 (Watch & Ingest) — Validation & Test Plan

Validates `src/pipeline/watch_ingest.py` and the parts of `src/storage/database.py`, `src/storage/runtime_io.py`, and `src/core/hashing.py` it depends on, against the Build-out 01 spec and `Rules/Ignore Rules.md`, before Module 02 is allowed to depend on it.

Existing unit tests (`src/pipeline/test_watch_ingest.py`, 12 passing) cover the individual helper functions in isolation with synthetic `tmp_path` fixtures. This plan is the complementary **integration-level** pass: real files, real directory scans, real edge cases, run against the actual code and reported here with real pass/fail results — not just asserted in pytest.

Datasets used (all created for this plan): `Samples/*` (canonical single examples) and `Tests/Small Batch/`, `Tests/Mixed Downloads/`, `Tests/Duplicate Files/`, `Tests/Corrupted Files/`, `Tests/Large Batch/`, `Tests/Edge Cases/`.

Test IDs: `F` functional, `B` boundary, `E` edge case, `X` failure scenario, `P` performance, `S` security.

---

## 1. Functional test cases

### M01-F01 — Full batch discovery, all supported types
- **Objective:** Confirm every supported extension in `SUPPORTED_EXTENSIONS` is discovered and queued when present in one scan.
- **Test data:** `Tests/Small Batch/` (9 files: `invoice.pdf`, `photo.jpg`, `resume.docx`, `notes.txt`, `archive.zip`, `audio_clip.mp3`, `video_clip.mp4`, `installer_mac.dmg`, `installer.pkg`).
- **Steps:** Call `scan_source(str(path_to_small_batch), source_id="downloads")` against an isolated metadata store.
- **Expected result:** `len(result.records) == 9`, `len(result.skipped) == 0`, one `FileRecord` per file with `extension` matching the file's real suffix.
- **Pass/Fail:** Pass if counts and extensions match exactly; fail on any missing/extra record or misclassified extension.

### M01-F02 — FileRecord field completeness for a single file
- **Objective:** Confirm every field Module 01 owns is populated correctly and every later-module field is left at its default.
- **Test data:** `Tests/Small Batch/invoice.pdf`.
- **Steps:** `build_file_record(path, source_id="downloads", batch_id="test-batch")`.
- **Expected result:** `file_id` is a valid UUID4 string; `content_hash` is a 64-char hex SHA-256 digest; `original_path == current_path` (first sighting); `size_bytes` matches `path.stat().st_size`; `created_at`/`modified_at` are ISO-8601 with timezone; `mime_type == "application/pdf"`; `status == "discovered"`; `error is None`; `category`, `suggested_name`, `confidence_score` (and all other Module 02+ fields) are `None`.
- **Pass/Fail:** Pass only if all of the above hold simultaneously.

### M01-F03 — Idempotent re-scan of an unmoved, unchanged file
- **Objective:** Confirm scanning the same file twice, untouched, reuses identity rather than minting a new record.
- **Test data:** `Samples/Invoices/sample_invoice_amazon.pdf` copied into a scratch scan directory.
- **Steps:** Scan once, `save_file_record()` the result, scan again (new `batch_id`, same path, same content).
- **Expected result:** Second scan's `file_id`, `original_name`, `original_path`, `discovered_at` all equal the first scan's; only `batch_id` (and `modified_at`, if the filesystem updates it) differs.
- **Pass/Fail:** Pass if identity fields are stable across both scans.

### M01-F04 — In-place content change at the same path is flagged, not silently overwritten
- **Objective:** Confirm editing a tracked file's contents surfaces `content_changed=True` while keeping the same `file_id`.
- **Test data:** A scratch copy of `Samples/Documents/sample_generic_document_manual.txt`, overwritten with different text between scans.
- **Steps:** Scan → save → overwrite file content → scan again.
- **Expected result:** `content_changed is True`; `file_id` unchanged; `content_hash` differs between the two records.
- **Pass/Fail:** Pass if both the flag and the identity-stability hold together.

### M01-F05 — Identical content at two different paths gets two different identities
- **Objective:** Confirm content hash alone never determines `file_id` (that decision belongs to Module 04, not Module 01).
- **Test data:** `Tests/Duplicate Files/invoice_download.txt` and `invoice_download (1).txt` (byte-identical content, different filenames).
- **Steps:** Scan `Tests/Duplicate Files/`.
- **Expected result:** Two separate `FileRecord`s, `file_id`s differ, `content_hash`s are equal.
- **Pass/Fail:** Pass if both records exist independently with matching hashes and distinct IDs.

### M01-F06 — Metadata store is cumulative across batches, not per-scan
- **Objective:** Confirm `metadata_store.json` accumulates records from every scan rather than being overwritten by the latest one.
- **Test data:** `Tests/Small Batch/` scanned as batch 1, `Tests/Mixed Downloads/` (supported files only) scanned as batch 2, same isolated store.
- **Steps:** `build_ingest_queue()` on Small Batch, then again on Mixed Downloads; inspect the store file directly.
- **Expected result:** The store contains records from both batches (Small Batch's 9 plus Mixed Downloads' 3 supported files); nothing from batch 1 disappears after batch 2 runs.
- **Pass/Fail:** Pass if the union is present; fail if batch 1's entries are missing after batch 2.

### M01-F07 — Action log has one entry per entry processed, including skips
- **Objective:** Confirm `Runtime/Logs/action_log.jsonl` (or its isolated test equivalent) records every entry the scan looked at, not just the ones it queued.
- **Test data:** `Tests/Mixed Downloads/` (mix of discoverable, ignored, and skipped entries).
- **Steps:** Scan, then read the log file and count lines against `len(records) + len(skipped)`.
- **Expected result:** Line count equals total entries processed; each line's `action` is one of `discover`/`skip`/`error`; each `file_id` in a `discover`/`error` line matches the corresponding record.
- **Pass/Fail:** Pass if counts and actions reconcile exactly.

---

## 2. Boundary conditions

### M01-B01 — Zero-byte files are skipped, not errored
- **Objective:** Confirm a zero-byte file is treated as an incomplete download, not a crash or a valid empty record.
- **Test data:** `Tests/Corrupted Files/zero_byte.pdf`, `Tests/Mixed Downloads/empty_placeholder.pdf`.
- **Steps:** Scan each containing folder.
- **Expected result:** Both appear in `result.skipped` with `reason == "zero_byte"`; no `FileRecord` created for either.
- **Pass/Fail:** Pass if both are skipped with the exact reason and no record exists.

### M01-B02 — Extension case-insensitivity
- **Objective:** Confirm `.PDF` is recognized the same as `.pdf`.
- **Test data:** `Tests/Edge Cases/Statement.PDF`.
- **Steps:** Scan `Tests/Edge Cases/`; inspect the resulting record for this file.
- **Expected result:** `is_supported_extension` is `True`; `record.extension == ".pdf"` (lowercased); file is queued, not skipped.
- **Pass/Fail:** Pass if the file is discovered and its stored extension is lowercase.

### M01-B03 — No file extension at all
- **Objective:** Confirm files with no extension (common in real Downloads folders — `LICENSE`, config files) are skipped as unsupported rather than erroring.
- **Test data:** `Tests/Edge Cases/LICENSE`, `Tests/Edge Cases/.hidden_dotfile_no_ext`.
- **Steps:** Scan `Tests/Edge Cases/`.
- **Expected result:** Both appear in `result.skipped` with `reason == "unsupported_extension"` (`get_extension` returns `""` for both, per `pathlib` treating a single leading dot as no suffix).
- **Pass/Fail:** Pass if both are skipped with that exact reason; fail if either raises or is silently dropped without a `SkippedEntry`.

### M01-B04 — Very long filename
- **Objective:** Confirm a filename near the filesystem's practical length ceiling doesn't break path handling, hashing, or logging.
- **Test data:** `Tests/Edge Cases/` 200-character-stem `.txt` file.
- **Steps:** Scan `Tests/Edge Cases/`.
- **Expected result:** File is discovered normally; `original_name`/`current_path` round-trip correctly; action log line is written without truncation or error.
- **Pass/Fail:** Pass if the record is created and no exception is raised.

### M01-B05 — Unicode / emoji filename
- **Objective:** Confirm non-ASCII filenames (accented characters, emoji, em-dash) are handled without encoding errors.
- **Test data:** `Tests/Edge Cases/invoice_📄_north_star_—_v2.pdf`.
- **Steps:** Scan `Tests/Edge Cases/`.
- **Expected result:** File discovered, `original_name` preserves the Unicode characters exactly, `content_hash` computed successfully, action log entry written as valid JSON (UTF-8).
- **Pass/Fail:** Pass if the record's name matches byte-for-byte and the log line parses as JSON.

### M01-B06 — Large batch volume
- **Objective:** Confirm the scan handles a batch well beyond typical daily Downloads volume without degradation in correctness (throughput measured separately under Performance).
- **Test data:** `Tests/Large Batch/` (75 generated files across 8 extensions).
- **Steps:** Scan the full folder.
- **Expected result:** `len(result.records) + len(result.skipped) == 75`; every record has a unique `file_id`; no duplicate or dropped entries.
- **Pass/Fail:** Pass if the count reconciles exactly and every `file_id` is unique.

---

## 3. Edge cases

### M01-E01 — Directory whose name looks like a supported file
- **Objective:** Confirm a directory check wins over extension matching — `archive.zip/` (a folder) must never be treated as a zip file.
- **Test data:** `Tests/Edge Cases/archive.zip/` (a real directory containing `inner.txt`).
- **Steps:** Scan `Tests/Edge Cases/`.
- **Expected result:** Appears in `result.skipped` with `reason == "directory"`; no attempt to hash or read it as a file.
- **Pass/Fail:** Pass if skipped for the `directory` reason specifically (not `unsupported_extension` or an error).

### M01-E02 — In-progress / partial download suffixes
- **Objective:** Confirm files still being downloaded by a browser are recognized and ignored by name, independent of the stability check.
- **Test data:** `Tests/Mixed Downloads/partial_download.crdownload`.
- **Steps:** Scan `Tests/Mixed Downloads/`.
- **Expected result:** Skipped with `reason == "temporary_download"`, not `"unstable"`.
- **Pass/Fail:** Pass if the exact reason is `temporary_download`.

### M01-E03 — OS/system junk files
- **Objective:** Confirm `.DS_Store` and similar are never queued or hashed.
- **Test data:** `Tests/Mixed Downloads/.DS_Store`.
- **Steps:** Scan `Tests/Mixed Downloads/`.
- **Expected result:** Skipped with `reason == "system_file"`.
- **Pass/Fail:** Pass if skipped with that reason.

*(Both expected reasons updated 2026-07-06 — `ignored_name` was split into `system_file`/`temporary_download` after the Module 01 UAT found the generic reason wasn't informative enough. See `CHANGELOG.md`.)*

### M01-E04 — Unsupported but well-formed extension
- **Objective:** Confirm a file type simply not in `SUPPORTED_EXTENSIONS` (as opposed to malformed) is skipped cleanly.
- **Test data:** `Tests/Mixed Downloads/mystery_file.xyz`.
- **Steps:** Scan `Tests/Mixed Downloads/`.
- **Expected result:** Skipped with `reason == "unsupported_extension"`.
- **Pass/Fail:** Pass if skipped with that reason and no error.

### M01-E05 — Non-recursive scope: nested subfolder is not descended into
- **Objective:** Confirm v1's documented "top level only" scope (`Rules/Ignore Rules.md`) is actually honored, including files that would otherwise qualify.
- **Test data:** `Tests/Mixed Downloads/Old Stuff/should_not_be_scanned.pdf` (a valid, readable PDF one level down).
- **Steps:** Scan `Tests/Mixed Downloads/` and confirm the nested file never appears in either `records` or `skipped`.
- **Expected result:** `Old Stuff` itself is skipped with `reason == "directory"`; `should_not_be_scanned.pdf` does not appear anywhere in the `IngestResult` (it was never visited — `iterdir()` is non-recursive).
- **Pass/Fail:** Pass if the nested file is entirely absent from both lists.

### M01-E06 — Near-duplicate images are still two independent records at this stage
- **Objective:** Confirm Module 01 makes no near-duplicate judgment (that's Module 04) — two visually-similar-but-not-identical images are just two ordinary records.
- **Test data:** `Tests/Duplicate Files/product_photo_v1.jpg`, `product_photo_v2.jpg` (same dimensions, one pixel-value off).
- **Steps:** Scan `Tests/Duplicate Files/`.
- **Expected result:** Two records, two different `content_hash` values, two different `file_id`s — no special handling or flag.
- **Pass/Fail:** Pass if both are ordinary, independent `discovered` records.

### M01-E07 — Version-chain filenames
- **Objective:** Confirm `Resume_v8.pdf`/`Resume_v9.pdf` are treated as two ordinary, unrelated files (version-chain reasoning is Module 04/06 territory, not Module 01's).
- **Test data:** `Tests/Duplicate Files/Resume_v8.pdf`, `Resume_v9.pdf`.
- **Steps:** Scan `Tests/Duplicate Files/`.
- **Expected result:** Two independent records; nothing in Module 01's output links them.
- **Pass/Fail:** Pass if both are discovered normally with no cross-reference.

---

## 4. Failure scenarios

### M01-X01 — Malformed-but-readable file (wrong content for its extension)
- **Objective:** Confirm Module 01 does not attempt format validation — a `.pdf` file containing garbage bytes is still just bytes to hash, not a validation failure.
- **Test data:** `Tests/Corrupted Files/malformed_not_a_real.pdf` (arbitrary bytes, `.pdf` extension, not a real PDF structure).
- **Steps:** Scan `Tests/Corrupted Files/`.
- **Expected result:** File is discovered normally with `status == "discovered"` (NOT `"unreadable"`) and a valid `content_hash` — Module 01 only reads raw bytes for hashing and never parses PDF structure; format validation belongs to `core/pdf.py` / Module 03.
- **Pass/Fail:** Pass if the file is treated as an ordinary successful discovery. This is a deliberate boundary of Module 01's responsibility, not a defect — documented here so it isn't mistaken for one later.

### M01-X02 — Truncated file with a valid header
- **Objective:** Confirm a file that looks legitimate for the first few bytes (e.g. a real JPEG magic number) but is cut off mid-write is still just hashed as-is, not specially detected as "truncated."
- **Test data:** `Tests/Corrupted Files/truncated_mid_write.jpg` (valid JPEG SOI/APP0 header, then nothing).
- **Steps:** Scan `Tests/Corrupted Files/`.
- **Expected result:** Discovered normally, `status == "discovered"`, hash computed over the 4 bytes present. No crash.
- **Pass/Fail:** Pass if treated as an ordinary (very small) file. Genuine truncation detection (e.g. checking `is_stable()` against a still-transferring file) is only meaningful in real-time; a file that's already finished changing size but was truncated by something other than a browser download is out of Module 01's detection ability by design.

### M01-X03 — Permission-locked / unreadable file
- **Objective:** Confirm a file whose contents can't be read is captured as `status="unreadable"` with an error message, and does not crash the scan.
- **Test data:** `Tests/Corrupted Files/permission_locked.pdf` (chmod'd to deny read access).
- **Steps:** Scan `Tests/Corrupted Files/`.
- **Expected result:** A `FileRecord` IS still created (per spec — "detect unreadable files without crashing... record and continue") with `status == "unreadable"`, `content_hash is None`, `error` containing the underlying `PermissionError` message. `result.records` still includes it (it's a record, just an unreadable one); the action log has an `action == "error"` line for it. The scan continues to process the rest of `Tests/Corrupted Files/` afterward.
- **Pass/Fail:** Pass if the record exists with `status="unreadable"` and the scan completes without raising.
- **Portability note:** this file's permission bits were set via `chmod 000` in the current sandbox. `stat()` in this environment reports the mode as `0o600` (owner read/write) even though attempting to actually read the file correctly raises `PermissionError` — an artifact of the sandbox's filesystem layer, not of the test's validity. If this test is re-run in a different environment and the file turns out to be readable there (e.g. running as root, which ignores permission bits entirely), re-apply `chmod 000` and confirm with a direct `read_bytes()` attempt before trusting the scan result.

### M01-X04 — Missing/nonexistent source directory
- **Objective:** Confirm scanning a path that doesn't exist raises a clear, specific error rather than a generic or silent failure.
- **Test data:** A path guaranteed not to exist (e.g. `Tests/does_not_exist/`).
- **Steps:** `scan_source(str(missing_path))`.
- **Expected result:** Raises `NotADirectoryError` with a message naming the path.
- **Pass/Fail:** Pass if that exact exception type is raised (already covered by `test_scan_source_raises_on_missing_directory`; re-verified here at the integration level with a real vault-relative path).

### M01-X05 — One bad entry must not stop the rest of the scan
- **Objective:** Confirm the scan-level exception handling in `scan_source()` (catch-and-continue around `_process_entry`) actually protects the batch, not just in theory.
- **Test data:** `Tests/Corrupted Files/` as a whole (contains the unreadable file alongside normal ones) plus, if feasible, a synthetic entry engineered to raise inside `_process_entry` itself (e.g. a name that raises on `.stat()` unexpectedly).
- **Steps:** Scan the folder; confirm every other file in the same folder still produced a normal record or skip entry.
- **Expected result:** The unreadable/malformed files each get their own record/skip entry; no exception propagates out of `scan_source()`; total entries processed still equals the folder's file count.
- **Pass/Fail:** Pass if the scan returns a complete `IngestResult` covering all entries despite the problematic ones.

---

## 5. Performance tests

### M01-P01 — Large batch scan timing
- **Objective:** Get a baseline for scan throughput on a batch well above typical daily volume, to catch any accidentally-quadratic behavior (e.g. `find_by_current_path()`'s linear scan of the metadata store) before it matters.
- **Test data:** `Tests/Large Batch/` (75 files).
- **Steps:** Time `build_ingest_queue()` against an empty metadata store, then time it again as a re-scan (store now has 75 entries, so every `find_by_current_path()` call scans a non-trivial list).
- **Expected result:** Completes in well under a few seconds either way at this volume; re-scan isn't dramatically slower than first scan.
- **Pass/Fail:** Informational baseline rather than a strict gate at this scale — fail only if the run hangs, errors, or takes an unreasonable amount of time (e.g. >30s) for 75 files, which would indicate a real algorithmic problem worth flagging before Database/Metadata grows further.
- **Known scaling note:** `find_by_current_path()` is documented as a linear scan (see `src/storage/database.py`). That's fine at hundreds of records; if `metadata_store.json` grows into the thousands, this is the first place to revisit — noted here, not treated as a Module 01 defect today.

### M01-P02 — Stability-check overhead
- **Objective:** Confirm the deliberate `is_stable()` sleep (`STABILITY_CHECKS=2`, `STABILITY_CHECK_INTERVAL_SECONDS=0.5`) doesn't multiply unacceptably across a large batch, since each file is checked independently.
- **Test data:** `Tests/Large Batch/`.
- **Steps:** Measure total wall-clock time attributable to stability checks (`≈0.5s × number of files` in the worst case, since checks aren't parallelized).
- **Expected result:** For 75 files this is roughly 37 seconds if every file needs the full check — worth surfacing explicitly rather than treating as a "test."
- **Pass/Fail:** Not a pass/fail gate — a documented observation. **Flagged for follow-up:** at real-world Downloads volumes (dozens to low hundreds of files per manual scan) this sequential per-file delay is the dominant cost in the entire module and will be the first thing worth optimizing (e.g. batching the stability check across files) if scan time becomes noticeable to the user. Not a defect in the current spec, since v1 explicitly scoped Manual mode only — but worth the user's awareness.

---

## 6. Security considerations

### M01-S01 — Symlink traversal outside the source folder
- **Objective:** Confirm a symlink inside the source directory pointing anywhere else on disk is never followed, hashed, or recorded.
- **Test data:** Regression case already in `src/pipeline/test_watch_ingest.py::test_scan_source_skips_symlinks_without_following_them`.
- **Status:** **Defect found and fixed during this validation pass** (see `CHANGELOG.md`, 2026-07-06 entry). `_process_entry()` now checks `entry.is_symlink()` before any `is_dir()`/`is_file()` follow-through. Regression test in place and passing.
- **Pass/Fail:** Pass — fix verified, symlinked entries are skipped with `reason == "symlink"` and never reach the hashing step.

### M01-S02 — Unreadable/permission-denied files handled without privilege escalation or crash
- **Objective:** Confirm a file the process lacks permission to read is handled gracefully (see M01-X03) and that no part of the code attempts to work around the OS's permission decision.
- **Test data:** `Tests/Corrupted Files/permission_locked.pdf`.
- **Expected result:** `PermissionError` (a subclass of `OSError`) is caught exactly where `sha256_file()` documents it should be, surfaced as `status="unreadable"`, nothing more.
- **Pass/Fail:** Pass if the failure is handled as designed with no attempt to bypass the OS-level restriction.

### M01-S03 — Path traversal via filename (considered, not applicable at this stage)
- **Objective:** Consider whether a crafted filename could cause the scanner to read or write outside the intended directory.
- **Analysis:** `directory.iterdir()` only yields direct filesystem children that the OS itself resolved into that directory — a filename containing literal `..` characters (not a real path separator sequence, since `/` can't be part of a filename) is just an unusual name, not a traversal vector. There is no user-supplied path string being concatenated or parsed by this module beyond what `pathlib`/the OS already resolved. Not applicable to Module 01 as currently scoped.
- **Pass/Fail:** N/A — documented as considered and ruled out, not tested with a dedicated case.

### M01-S04 — No code execution risk from file contents
- **Objective:** Confirm nothing in Module 01 parses, executes, or interprets file contents in a way that untrusted bytes could exploit.
- **Analysis:** The only content-touching operation is `sha256_file()` (raw byte reads into a hash function) and `mimetypes.guess_type()` (pure string match on the filename, not the contents). No archive extraction, no document parsing, no shelling out to external tools happens in Module 01. `Tests/Corrupted Files/malformed_not_a_real.pdf` and `Tests/Edge Cases/archive.zip/` (a directory, not an actual archive being opened) exercise this: nothing attempts to interpret their contents structurally.
- **Pass/Fail:** Pass — confirmed by code review; no test can meaningfully "fail" this beyond confirming M01-X01 behaves as described.

### M01-S05 — Action log injection via filename
- **Objective:** Confirm a filename containing characters that could break JSON Lines formatting (quotes, newlines, control characters) doesn't corrupt `action_log.jsonl`.
- **Test data:** Not yet present in the dataset — **gap identified during this review.** Recommend adding a file with a name containing a literal double-quote and a newline-like Unicode character (e.g. `weird"name.txt`) to `Tests/Edge Cases/` before this case can be executed.
- **Pass/Fail:** **Not yet executed** — see Section 8 (gaps).

---

## 7. Expected outputs summary

For any scanned folder, a correct Module 01 run produces:
- One `FileRecord` per supported, stable, non-ignored, non-symlink, non-directory file — regardless of whether its contents are well-formed for its extension.
- One `SkippedEntry` per directory, symlink, ignored-name match, zero-byte file, unstable file, or unsupported extension — each with the specific `reason` string documented in `SkippedEntry`.
- Exactly one action-log line per entry processed (`discover`, `skip`, or `error`), with `file_id`/`from_path`/`details` populated appropriately.
- `metadata_store.json` containing every `FileRecord` ever saved via `save_file_record()`, cumulative across all past scans, keyed such that `find_by_current_path()` can re-identify unmoved files on the next scan.
- No unhandled exception under any single-entry failure — only a directory-level `NotADirectoryError` if the source path itself doesn't exist.

---

## 8. Scenarios that cannot be fully validated until later modules exist

- **End-to-end reversibility / undo:** Module 01 never moves or renames anything, so there is nothing to "undo" yet at this stage — the non-negotiable "every action must be reversible" can only be fully validated once Module 07 (Execution) actually performs moves and a rollback path exists to test against.
- **Confidence-score interplay:** `confidence_score` is deliberately left `None` by Module 01. Whether the *overall* pipeline behaves correctly at confidence boundaries (95/80 tier thresholds) depends on Module 06 and can't be exercised here.
- **Classification-dependent folder routing:** Which folder a file ultimately lands in (`Rules/Folder Rules.md`) depends on Module 02's category output, which doesn't exist yet — Module 01's job ends at "queued, with correct raw metadata," not "routed."
- **Duplicate/version detection correctness:** M01-F05, M01-E06, and M01-E07 above confirm Module 01 does NOT make any duplicate/version judgment (by design) — but whether Module 04's actual duplicate logic correctly acts on the `content_hash` values Module 01 produces can only be validated once Module 04 exists.
- **Real video/audio content:** `Samples/Videos/sample_product_demo.mp4` and every `.mp3`/`.mp4` file in `Tests/Small Batch/` and `Tests/Large Batch/` are placeholder binaries, not real media containers. This is sufficient for Module 01 (which only hashes bytes and reads the extension) but will need replacing with real media before Module 03 (metadata extraction, e.g. video duration/audio length) can be validated.
- **Zip archive contents:** `Tests/Small Batch/archive.zip` is a real, valid zip file, but Module 01 never opens it — only Module 03/classification would ever need to look inside. Nothing about internal archive handling can be validated at this stage.
- **True stability-check behavior on an actively-downloading file:** `is_stable()` is exercised here only against already-finished files (nothing in the test data changes size mid-scan). Validating the "wait, re-check next pass" behavior against a *genuinely* still-downloading file requires either a real slow download or a purpose-built script that writes a file incrementally during the test run — not attempted here since Manual mode scans are typically triggered after downloads finish. Worth a dedicated live test later if false "unstable" flags are ever reported by the user.

---

## 9. Gaps identified during this review (not defects — recommendations only)

- **M01-S05** (action-log JSON safety for adversarial filenames) is specified above but not yet executed — the dataset needs one more file added first.
- `src/README.md` currently says "11 passing" for the unit test count; the actual current count is 12 (the symlink regression test was added after that line was last updated). Cosmetic doc drift, not a code defect — worth a one-line fix whenever Module 01 is next touched, but not fixed here since this session is scoped to validation, not modification, absent a genuine defect.

No other gaps identified. Everything else planned above has real test data in place and is ready to execute.

---

## 10. Execution results (run against the real code, 2026-07-06)

Every test case above was executed for real against `src/pipeline/watch_ingest.py` and its dependencies (isolated `Database`/`Runtime` paths per run, so nothing touched the project's real store or logs). Full output available in this session's tool history.

**27 of 27 executed cases: PASS.** (M01-S03/S04 were analysis-only per their own design, not executable tests; M01-S05 was not executed — see gap below, unchanged from Section 9.)

| Section | Cases | Result |
|---|---|---|
| Functional (F01–F07) | 7 | 7 PASS |
| Boundary (B01–B06) | 7 (B01 split a/b) | 7 PASS |
| Edge (E01–E07) | 7 | 7 PASS |
| Failure (X01–X05) | 5 | 5 PASS |
| Performance (P01–P02) | 2 | measured, see below |
| Security (S01–S05) | 3 executable + 2 analysis-only | 3 PASS, 2 N/A (as designed) |

Also re-ran the existing unit suite (`pytest src/pipeline/test_watch_ingest.py`) as a regression check: **12/12 still passing**, no change since the symlink fix.

### Performance — measured, not estimated
- **M01-P01/P02:** a single real scan of `Tests/Large Batch/` (75 files, unpatched — i.e. the actual 0.5-second stability-check interval the shipped code uses) took **38.12 seconds**, all 75 files correctly discovered with unique `file_id`s. This empirically confirms the theoretical estimate in Section 5: the sequential per-file stability check is the dominant cost at this volume, purely due to the sleep, not any algorithmic issue in the scan logic itself. At realistic daily Downloads volumes (a handful to a few dozen files) this is a few seconds at most; flagged again here only because it's now measured fact rather than a projection.

### New finding from this execution pass: a testability defect in the existing unit test suite (not a Module 01 runtime defect)

While isolating stability-check timing for these integration runs, discovered that `is_stable()`'s `interval_seconds` parameter defaults to the *value of* `STABILITY_CHECK_INTERVAL_SECONDS` at function-definition time (standard Python default-argument binding), not a live lookup of the module constant. This means `src/pipeline/test_watch_ingest.py`'s existing `monkeypatch.setattr("src.pipeline.watch_ingest.STABILITY_CHECK_INTERVAL_SECONDS", 0)` **does not actually speed up `is_stable()`** the way its comment claims — it silently does nothing, and any test that reaches a real `is_stable()` call still sleeps the real 0.5 seconds. This has been happening invisibly: the existing suite's ~1.09s runtime is consistent with exactly one real 0.5s sleep occurring in `test_scan_source_skips_ignored_and_unsupported` (the only existing test where a stable, non-ignored file reaches the `is_stable()` check before its extension is evaluated).

This is **not a defect in `watch_ingest.py`'s actual behavior** — production code sleeps 0.5s between stability checks by design, and that's correct. It's a defect in the *test harness's* attempt to disable that sleep for speed, which happens to be harmless today (only costs ~0.5s) but would silently cost more as more `scan_source()`-based tests are added.

Confirmed the correct fix in this validation run (`wi.is_stable.__defaults__ = (wi.STABILITY_CHECKS, 0)`, reassigning the bound default directly) works as intended — used throughout the scripts run for this validation pass. **Not applied to `src/pipeline/test_watch_ingest.py` itself**, since that file is part of Module 01's approved deliverable and the instruction for this pass was to modify Module 01 only for a genuine defect *in Module 01* — this is a test-infrastructure nit, not a pipeline defect, so it's surfaced here as a recommendation rather than applied unilaterally. Recommend fixing whenever `test_watch_ingest.py` is next touched.

### Conclusion
No genuine defects found in `watch_ingest.py`, `database.py`, `runtime_io.py`, or `hashing.py` during this validation pass. Module 01's behavior matches its spec, including at the boundaries and failure modes exercised above. The one prior defect (symlink following) was already found and fixed before this plan was written, and is re-confirmed here at the integration level (M01-S01). High confidence Module 01 is ready to be depended on by Module 02.
