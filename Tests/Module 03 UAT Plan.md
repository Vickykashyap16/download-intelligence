# Module 03 (Metadata Extraction) — UAT Plan

Real end-to-end acceptance test of the complete Module 01 → 02 → 03 pipeline, run the way an actual user would experience it: a realistic, external, Downloads-style folder, scanned by Module 01's real `scan_source()`, classified by Module 02 using **live Claude judgment as the actual `ClassificationProvider`**, and metadata-extracted by Module 03 using **live Claude judgment as the actual `MetadataExtractionProvider`** — not the routing/canned fakes used in `Tests/Module 03 Integration Test Plan.md`. This is the one validation step the automated integration plan explicitly could not cover (its own Section 8/AI-assisted section notes this): whether live judgment actually produces correct, complete, correctly-redacted metadata on real, varied files — not just whether the plumbing works.

## Why this has to be live, not scripted

`ClaudeLiveClassifier.classify()`/`ClaudeLiveExtractor.extract()` are documented placeholders — they raise `NotImplementedError` by design, because the real "implementation" of judgment is Claude reasoning live during an agent-driven run, not a function body. For this UAT, Claude actually read every judgment-needing file's real extracted content (via the same `core/pdf.py`/`core/text.py` functions Module 02/03 use internally) and constructed the real `ProviderResponse`/`ProviderResponse` objects itself — exactly matching what `ClaudeLiveClassifier`/`ClaudeLiveExtractor` describe doing in a genuine production run, and exactly the same methodology `Tests/Module 02 UAT Plan.md` established.

## CLI wiring added for this UAT (not a Module 03 implementation change)

Module 03 was never wired into `src/main.py`'s CLI (deliberately deferred — see `src/main.py`'s prior docstring, "everything past classification is still scaffold"). To satisfy "use the actual CLI entry point and production code paths," this UAT added:
- `extract()` to `src/main.py` — mirrors `classify()`'s exact shape (loads classified-but-unextracted records, calls `extract_metadata_batch()`, prints a summary, matching `classify()`'s established pattern).
- An optional `provider=None` parameter to both `classify()` and the new `extract()` — the same documented pattern `classify()`'s own docstring already specified for a real run ("supplies live judgment by passing a provider built during that session ... instead of relying on this function's default"). Default behavior (no provider passed) is unchanged.
- `__main__` now runs `scan(); classify(); extract()`.

This is orchestration/CLI wiring, not a change to `src/pipeline/metadata.py`'s engine logic — consistent with your standing instruction not to modify Module 03's implementation absent a genuine defect. No defect was found, so `metadata.py` itself was not touched.

## Test data

A new, external folder — `/tmp/uat_m03_downloads` (outside the project, ephemeral, not preserved after the run, same convention as Modules 01/02's UATs) — 19 entries:

| File | What it's really testing |
|---|---|
| `Amazon_Order_Invoice_2026.pdf` | Ordinary invoice — full required + optional field set |
| `Chase_Statement_June2026.pdf` | Bank statement, text **contains the full account number** — deliberately tests the Engine's redaction safety net against an imperfect live answer, not just a well-behaved one |
| `NDA_signed_copy.pdf` | Contract — full field set |
| `user_manual_v3.txt` | Generic Document |
| `JordanPatel_Resume_2026.docx` | Resume |
| `Screen Shot 2026-07-04 at 3.42.11 PM.png` | Screenshot — vision judgment, no camera EXIF |
| `IMG_4821.jpg` | Real camera-style photo **with genuine EXIF** (`Make`/`DateTimeOriginal`) — tests tier-2 timestamp sourcing for real, not synthetically bypassed |
| `product_demo_final.mp4` | Video — deterministic |
| `project_files.zip` | Archive, nested directory — deterministic |
| `SomeApp_2.4.1_Mac.dmg` | Application, realistic version/platform filename — deterministic |
| `voice_memo.mp3` | Audio, **real embedded ID3 tags** (via `ffmpeg`) — tests tier-1 timestamp sourcing for real |
| `download_error.pdf` | Malformed PDF — extraction-failure path |
| `Confidential_Agreement.pdf` | Real password-protected PDF (via `pypdf` encryption) — locked path |
| `facture_boulangerie.pdf` | Non-English (French) invoice — language signal + still needs a real category and real extraction |
| `payment_confirmation.pdf` | Genuinely ambiguous invoice/receipt wording — judgment-quality test |
| `corrupted_project.zip` | Valid `.zip` extension, garbage bytes — Module 02 lets it through (extension-only), Module 03 must catch the corruption itself |
| `.DS_Store` | OS junk — skipped before Module 02 |
| `empty_placeholder.pdf` | Zero-byte — skipped before Module 02 |
| `movie_download.torrent` | Unsupported extension — skipped before Module 02 |

## Steps

1. **Module 01 (real scan):** `src/main.py`'s real `scan()`, pointed at `/tmp/uat_m03_downloads` (via a temporary `sources.yaml` edit, restored immediately after the run), against isolated `Database`/`Runtime` paths.
2. **Live classification (real judgment):** for every text-bearing file, Claude read the file's actual extracted content (via the real `core/pdf.py`/`core/text.py` functions) and produced its own category judgment, wired into a `ClassificationProvider` built for this run only, passed to `classify()`'s new `provider=` parameter.
3. **Live metadata extraction (real judgment):** for every judgment-dependent category (Invoice/Resume/Bank Statement/Contract/Document deep text pass; Image/Screenshot vision pass), Claude produced its own field answers from the same real extracted content, wired into a `MetadataExtractionProvider` built for this run, passed to `extract()`'s new `provider=` parameter.
4. **Persist and inspect:** verify every file's final `category`, `classification_signals`, and `extracted_metadata` against the "what it's really testing" column above; verify redaction, timestamp hierarchy, logging, and database contents directly against the raw JSON/JSONL files.
5. **Archive:** `metadata_store.json`, `action_log.jsonl`, `terminal_output.txt`, and `summary.md` under `Runtime/UAT/Module03_UAT_2026-07-06_100928/`.

## Expected outcomes

- 16 discovered, 3 skipped (`.DS_Store` → `system_file`, `empty_placeholder.pdf` → `zero_byte`, `movie_download.torrent` → `unsupported_extension`) — 19 total, reconciling exactly.
- Every deterministic file (Video/Archive/Application/Audio, plus the corrupted archive and the real-EXIF/no-EXIF image split) gets its category/fields with zero classification-provider calls where deterministic.
- Every text/vision-bearing file gets a real, judgment-based category and extraction matching what a person would conclude from the actual content.
- `Chase_Statement_June2026.pdf`'s deliberately-full account number is redacted to `null` by the Engine, with only the field name (never the value) appearing in the log.
- `corrupted_project.zip` is classified `Archive` by Module 02 (never opens the file) but falls back gracefully in Module 03 (`extraction_failed`, `contents_summary: null`).
- `Confidential_Agreement.pdf`/`download_error.pdf` never reach Module 03 at all (`Category.UNKNOWN`).
- No unhandled exception anywhere in the run.

## Pass/Fail

Pass if every file's final classification and extracted metadata are defensible against its real content when read directly, redaction/timestamp-hierarchy/logging behave exactly as designed, no prohibited or over-long value ever reaches disk, and the run completes with no unhandled exception. A judgment call a reasonable person could see differently (the ambiguous receipt/invoice) is not a failure by itself — what matters is that the `ambiguous` signal and the extracted fields are honest and defensible, not that every call is unanimous.

---

## Execution Results (run 2026-07-06, batch `2026-07-06_100928`)

Full results, reasoning, and verdict are recorded in `Runtime/UAT/Module03_UAT_2026-07-06_100928/summary.md`, alongside the raw `metadata_store.json`, `action_log.jsonl`, and `terminal_output.txt` from the real run.

**Headline result: zero defects found. All 20 requested verification dimensions checked and passed.** No changes were made to `src/pipeline/metadata.py` (or `classification.py`/`watch_ingest.py`) as a result of this UAT — only the pre-planned, additive `extract()`/`provider=` CLI wiring in `src/main.py`, which is orchestration, not Module 03's implementation.

**Module 03 is approved for release artifact generation.**
