# Module Contract — Module 01 (Watch & Ingest)

Every module in this pipeline declares what it receives, what it produces, what it guarantees about the fields it owns, and — just as importantly — what it must never touch. This is what lets later modules depend on earlier ones without accidentally overwriting each other's work. See `Release/DEPENDENCY_DIAGRAM.md` for how modules chain together and `Release/VERSIONS.md` for versioning.

## INPUT

**Receives:**
A configured Source (`src/config/sources.yaml`): a filesystem directory path, `source_id`, and execution mode. Not a `FileRecord` list — Module 01 is the pipeline's entry point, so there is no upstream module output to receive.

## OUTPUT

**Produces:**
- `List[FileRecord]` — one per supported, stable, non-ignored file discovered in the Source's top level (`build_ingest_queue()`, or `scan_source().records` for the full result).
- `List[SkippedEntry]` — one per entry deliberately not queued, each with a specific reason (`scan_source().skipped`). Not passed forward to Module 02 — surfaced via the CLI and `Runtime/Logs/action_log.jsonl` instead.

**Guarantees** — fields Module 01 owns and fully populates on every `FileRecord` it produces:
- `file_id` — permanent UUID4, assigned once at first discovery, stable across re-scans of a file that hasn't moved.
- `source_id`, `original_name`, `original_path`, `current_path`
- `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`
- `content_hash` — SHA-256 of file bytes, or `null` if `status == "unreadable"`.
- `discovered_at`, `status` (`"discovered"` | `"unreadable"`), `error`
- `batch_id`

## DOES NOT MODIFY

Module 01 never sets or touches any of the following — every one of these is left at its `FileRecord` default (`None` / empty dict / dataclass default) on every record it produces, for the owning module listed to fill in later:

- **Classification** — `category`
- **Metadata Extraction** — `extracted_metadata`
- **Naming & Destination** — `suggested_name`, `suggested_destination`
- **Duplicate & Version Detection** — `duplicate_of`, `version_group_id`, `version_rank`
- **Confidence & Review** — `confidence_score`, `confidence_breakdown`, `tier`
- **Preview, Approval & Execution** — `processed_at`, `approved_by`, `approved_at`, `reversible` (left at its dataclass default of `true` — Module 01 does not set this field itself)
- **Logging & Reporting** — `Runtime/Reports/*` (Daily/Weekly Summary, Duplicate Report, Storage Report). Module 01 only ever writes to `Runtime/Logs/action_log.jsonl`, never to `Reports/`.

**Verified by:** `test_build_file_record_reads_supported_file` (asserts `category`, `suggested_name`, and `confidence_score` are `None` on every record Module 01 builds) and by direct inspection of every field in `metadata_store.json` after both real UAT runs (see `TEST_RESULTS.md`) — every later-module field came back `null`/empty in both.
