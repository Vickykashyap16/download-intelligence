# Module Contract — Module 02 (Classification)

Every module in this pipeline declares what it receives, what it produces, what it guarantees about the fields it owns, and — just as importantly — what it must never touch. This is what lets later modules depend on earlier ones without accidentally overwriting each other's work. See `Release/DEPENDENCY_DIAGRAM.md` for how modules chain together and `Release/VERSIONS.md` for versioning.

## INPUT

**Receives:**
`List[FileRecord]` from Module 01 — specifically, the subset with `status == "discovered"`. Records with `status == "unreadable"` are accepted into `classify_batch()`'s input list but passed through completely untouched (see DOES NOT MODIFY below); Module 02 never attempts to classify a file Module 01 couldn't read.

**Also receives (internally, not from the caller):** an optional `ClassificationProvider` implementation, defaulting to `ClaudeLiveClassifier()`. Real production runs rely on live Claude judgment fulfilling this role during an agent-driven session; automated tests inject `FakeClassificationProvider` instead. See `Build-out/02 Classification/Module 02 Design.md` §24/§25.

## OUTPUT

**Produces:**
- The same `List[FileRecord]` handed in, enriched in place (`classify_batch()` mirrors Module 01's `build_ingest_queue()` shape: same records in, same records back out).
- One `classify` (or, for a truly unanticipated failure, `error`) action-log entry per file processed in `Runtime/Logs/action_log.jsonl`.

**Guarantees** — fields Module 02 owns and fully populates on every `status == "discovered"` `FileRecord` it processes:
- `category` — a `Category` enum member (never a raw string, never left `None` for a processed record). `Category.UNKNOWN` specifically means "Module 02 tried on a readable file and found no match or hit a known failure mode" — deliberately distinct from `None`, which means Module 01 never had readable bytes to try in the first place.
- `classification_signals` — a full `ClassificationSignals` instance (never partially filled, never `None` for a processed record): `ambiguous`, `multi_document_detected`, `no_extractable_text`, `non_english_detected`, `detected_language`, `locked`.

**Action log detail** (not persisted on `FileRecord` itself — log-only, per design §12): `mode` (`"deterministic"` | `"text"` | `"vision"`), `processing_time_ms`, `fallback_used`, `fallback_reason`, `error_detail` (a sanitized diagnostic string, present when a fallback occurred — added after the release audit, F3), and `provider_metadata` (provider name/model/version/latency/reasoning) when a provider was actually invoked.

## DOES NOT MODIFY

Module 02 never sets or touches any of the following on any record — every one of these is left at its `FileRecord` default (`None` / empty dict / dataclass default), for the owning module listed to fill in later:

- **Metadata Extraction** — `extracted_metadata`
- **Naming & Destination** — `suggested_name`, `suggested_destination`
- **Duplicate & Version Detection** — `duplicate_of`, `version_group_id`, `version_rank`
- **Confidence & Review** — `confidence_score`, `confidence_breakdown`, `tier`
- **Preview, Approval & Execution** — `processed_at`, `approved_by`, `approved_at`, `reversible`
- **Logging & Reporting** — `Runtime/Reports/*`. Module 02 only ever appends to `Runtime/Logs/action_log.jsonl`, never to `Reports/`.
- **Module 01's own fields** — `file_id`, `source_id`, `original_name`, `original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `batch_id` are all read, never rewritten.

**Records Module 01 marked `status == "unreadable"`** are left with `category` and `classification_signals` both still `None` — Module 02 never touches them at all, and they never receive a `classify` log entry.

**Verified by:** `test_classify_batch_skips_unreadable_records_untouched` (unit), M02-F05/M02-F07 (integration — confirms both the populated and untouched field sets on a real record), and direct inspection of `metadata_store.json` after the real UAT run (every later-module field came back `null`/empty; see `TEST_RESULTS.md`).

## Provider boundary (internal architecture, not part of the external contract)

Module 02 is internally layered `classify_batch()` → `ClassificationEngine` → `ClassificationProvider`, but only `classify_batch()`'s behavior above is the actual module contract other modules can depend on. `ClassificationEngine` and `ClassificationProvider` are implementation details free to change (e.g. a future non-Claude or networked provider) without constituting a breaking change to this contract, as long as `classify_batch()`'s INPUT/OUTPUT/guarantees hold.

**Explicit disclosure (added after the independent release audit, 2026-07-06 — finding F1):** as of this release, **no autonomous `ClassificationProvider` implementation exists.** The only concrete provider, `ClaudeLiveClassifier`, requires a live, agent-driven Claude session — its `classify()` method raises `NotImplementedError` if invoked any other way, by design (it is fulfilled by Claude's own live reasoning during a run, not by autonomous code). This means the OUTPUT guarantees above hold unconditionally (every processed record gets a real `Category` and `ClassificationSignals`, even in an unattended run — via the fallback strategy, not real judgment), but the *quality* of judgment-dependent categories is only meaningful when Module 02 runs inside a live Claude session. A reader depending on this contract alone, without also reading `KNOWN_LIMITATIONS.md`, should still come away knowing this.
