# Module 03 release-audit repository cleanup — 2026-07-06

Archived here, not deleted, per the project's "never permanently delete anything" non-negotiable.

## What happened

During Module 03's implementation-audit troubleshooting, an ad-hoc debug session ran the real pipeline functions (`scan_source()` / `classify_batch()` / `extract_metadata_batch()`) directly against this project's real, hardcoded `Database/`/`Runtime/` paths instead of an isolated tmp path — unlike every integration-test and UAT script, which correctly isolated storage. This left synthetic debug data in the project's live `Database/Metadata/metadata_store.json` and `Runtime/Logs/action_log.jsonl`, discovered during Module 03's final independent release audit (`Release/Module03/RELEASE_AUDIT.md`, finding F1).

## What's archived here

- **`metadata_store_original.json`** — the full, unmodified content of `Database/Metadata/metadata_store.json` before any cleanup: 2 records, both `source_id: "dbg2"` (`sample_product_photo.jpg`, `sample_screenshot_login_error.png`), batch `2026-07-06_095533`.
- **`action_log_original.jsonl`** — the full, unmodified content of `Runtime/Logs/action_log.jsonl` before any cleanup: 16 lines across three batches (`2026-07-06_095020`, `2026-07-06_095313`, `2026-07-06_095533`).

## Cleanup, in two stages

**Stage 1 (approved):** removed the 6 lines/2 records directly and confirmably tagged `source_id: "dbg2"` (batch `095533`). `metadata_store.json` reset to `[]` (100% of its content was `dbg2`-tagged). 10 action-log lines from two earlier batches (`095020`, `095313`) were deliberately left in place at this stage — not confirmably `dbg2`-tagged (the action log format doesn't record `source_id`, and their corresponding `FileRecord`s no longer existed to check directly).

**Stage 2 (approved, this archive):** investigated the remaining 10 lines and found high-confidence evidence they are also synthetic debug output, not real user activity:
- Every path they reference points into this vault's own internal fixture directories — `Samples/Invoices/sample_invoice_amazon.pdf`, `Samples/Invoices/sample_invoice_messy_multicurrency.pdf`, and seven entries under `Tests/Mixed Downloads/` (`GST_Invoice_draft.pdf`, `IMG_20260705.jpg`, `Old Stuff/`, `Resume_final_v2.docx`, `empty_placeholder.pdf`, `mystery_file.xyz`, `partial_download.crdownload`, `.DS_Store`) — all pre-existing, named test fixtures built earlier in this engagement for Module 01/02 validation, still present on disk with matching names.
- `src/config/sources.yaml`'s configured source path is `null` ("filled in at runtime from the user's actual Downloads folder path") — it has never pointed at `Samples/` or `Tests/`. A real production scan could not have produced these entries; only a debug script calling `scan_source()` directly with a hardcoded fixture path could have.
- `CLAUDE.md` states explicitly: "This vault is the build/planning workspace, not the user's real Downloads folder" — there is no legitimate scenario in which a genuine first real run would ever scan these paths.
- Their `file_id`s do not appear anywhere in `metadata_store.json` (which, after Stage 1, is empty) — no persisted `FileRecord` backs any of them.
- Their timestamps (09:50:21 and 09:53:13 on 2026-07-06) cluster tightly with the confirmed `dbg2` debug session (09:55:33) the same morning — consistent with a short sequence of ad-hoc debugging commands run back-to-back in the same session.

On this evidence, all 10 lines were removed from `Runtime/Logs/action_log.jsonl` in Stage 2, leaving it empty — restoring the project's documented "empty until first real run" state for both files.

No archived UAT evidence (`Runtime/UAT/*`) was touched at any stage.
