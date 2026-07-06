# Module Contract — Module 03 (Metadata Extraction)

Every module in this pipeline declares what it receives, what it produces, what it guarantees about the fields it owns, and — just as importantly — what it must never touch. This is what lets later modules depend on earlier ones without accidentally overwriting each other's work. See `Release/DEPENDENCY_DIAGRAM.md` for how modules chain together and `Release/VERSIONS.md` for versioning.

## INPUT

**Receives:**
`List[FileRecord]` from Module 02 — specifically, the subset with `status == "discovered"` and a real, non-`Unknown` `category` (`extract_metadata_batch()`'s own filter: `status == "discovered" and category not in (None, Category.UNKNOWN) and extracted_metadata == {}`). Records Module 02 left at `Category.UNKNOWN`, records Module 01 marked `status == "unreadable"` (`category` still `None`), and records already extracted are all accepted into the input list but passed through completely untouched.

**Also receives (internally, not from the caller):** an optional `MetadataExtractionProvider` implementation, defaulting to `ClaudeLiveExtractor()`. Real production runs rely on live Claude judgment fulfilling this role during an agent-driven session; automated tests inject `FakeMetadataExtractionProvider` instead. See `Build-out/03 Metadata Extraction/Module 03 Design.md` §23.

## OUTPUT

**Produces:**
- The same `List[FileRecord]` handed in, enriched in place (`extract_metadata_batch()` mirrors Module 02's `classify_batch()` shape exactly: same records in, same records back out).
- One `extract_metadata` (or, for a truly unanticipated failure, `error`) action-log entry per file processed in `Runtime/Logs/action_log.jsonl`.

**Guarantees** — fields Module 03 owns and fully populates on every eligible `FileRecord` it processes:
- `extracted_metadata` — a dict with exactly one key per field in that category's closed taxonomy (`REQUIRED_FIELDS[category] + OPTIONAL_FIELDS[category]`, `Build-out/03 Metadata Extraction/Module 03 Design.md` §7) — never a field outside that taxonomy, never a partially-keyed dict. Each value is either a real, found value or an honest `null` — never fabricated, never coerced from a wrong-typed provider answer.

**Action log detail** (not persisted on `FileRecord` itself — log-only, per design §13): `category`, `fields_extracted`, `fields_missing`, `mode` (`"deterministic"` | `"text"` | `"vision"` | `"mixed"`), `processing_time_ms`, `extraction_complete` (mechanical: `True` iff every required field for the category is non-null), `fallback_used`, `fallback_reason`, `redacted_fields` (always present, even when empty — see the Bank Statement `account_last4` rule below), `error_detail` (a sanitized diagnostic string, present when a fallback occurred), and `provider_metadata` (provider name/model/version/latency/reasoning) when a provider was actually invoked.

## DOES NOT MODIFY

Module 03 never sets or touches any of the following on any record — every one of these is left exactly as Module 01/02 left it:

- **Module 01's own fields** — `file_id`, `source_id`, `original_name`, `original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `batch_id` are all read, never rewritten.
- **Module 02's own fields** — `category`, `classification_signals` are read, never rewritten.
- **Naming & Destination** — `suggested_name`, `suggested_destination`
- **Duplicate & Version Detection** — `duplicate_of`, `version_group_id`, `version_rank`
- **Confidence & Review** — `confidence_score`, `confidence_breakdown`, `tier`
- **Preview, Approval & Execution** — `processed_at`, `approved_by`, `approved_at`, `reversible`
- **Logging & Reporting** — `Runtime/Reports/*`. Module 03 only ever appends to `Runtime/Logs/action_log.jsonl`, never to `Reports/`.

**Records Module 02 left at `Category.UNKNOWN` or `None`** (never readable, or readable but unclassifiable) are left with `extracted_metadata` still at its `FileRecord` default (`{}`) — Module 03 never attempts extraction on them, and they never receive an `extract_metadata` log entry.

**Verified by:** `test_extract_metadata_batch_leaves_every_non_owned_field_byte_identical` (unit — every `FileRecord` field outside `extracted_metadata` is provably untouched, across all 24 fields on the record), M03-C01/M03-C02/M03-C03 (integration — confirms both the populated and untouched field sets on real records across all three upstream states), and direct inspection of `metadata_store.json` after the real UAT run (every field outside `extracted_metadata` came back identical to its post-Module-02 value; see `TEST_RESULTS.md`).

## Provider boundary (internal architecture, not part of the external contract)

Module 03 is internally layered `extract_metadata_batch()` → `MetadataExtractionEngine` → `MetadataExtractionProvider`, but only `extract_metadata_batch()`'s behavior above is the actual module contract other modules can depend on. `MetadataExtractionEngine` and `MetadataExtractionProvider` are implementation details free to change (e.g. a future non-Claude or networked provider) without constituting a breaking change to this contract, as long as `extract_metadata_batch()`'s INPUT/OUTPUT/guarantees hold. Deliberately not code-shared with Module 02's identically-shaped `ClassificationEngine`/`ClassificationProvider` — a separate set of classes by design (`Module 03 Design.md` §21), not an oversight.

**Explicit disclosure (same deployment-model caveat as Module 02's `MODULE_CONTRACT.md`):** as of this release, **no autonomous `MetadataExtractionProvider` implementation exists.** The only concrete provider, `ClaudeLiveExtractor`, requires a live, agent-driven Claude session — its `extract()` method raises `NotImplementedError` if invoked any other way, by design (it is fulfilled by Claude's own live reasoning during a run, not by autonomous code). This means the OUTPUT guarantees above hold unconditionally (every eligible record gets a real, key-complete `extracted_metadata` dict, even in an unattended run — via the fallback strategy, not real judgment), but the *quality* of judgment-dependent fields is only meaningful when Module 03 runs inside a live Claude session. See `KNOWN_LIMITATIONS.md`.

## Privacy control (part of the external contract, not just an internal detail)

Two structural guarantees hold for every record Module 03 processes, enforced at `MetadataExtractionEngine._validate_and_merge()` — the trust boundary between a provider's raw answer and `extracted_metadata` — not merely by prompt instruction:
- **Closed taxonomy:** any field name a provider returns that isn't in that category's required+optional list is dropped before ever reaching `extracted_metadata`, the on-disk store, or the action log.
- **Bank Statement `account_last4` redaction:** if the value contains more than 4 digits, it is redacted to `null` and only the field *name* (never the value) is recorded, in `redacted_fields`. A value of 4 digits or fewer (including empty) passes through unchanged. This check runs exactly once, never retroactively.

Both are unconditional — they hold regardless of which provider is configured, including a provider that behaves badly (verified adversarially: `MC01`/`PR01`/`SEC02` feed a deliberately over-long account number and an out-of-taxonomy field, both caught by the Engine itself, not by the provider self-censoring).
