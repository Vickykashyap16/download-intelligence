# Metadata & Log Schema — v1 (canonical, matches `src/models/file_record.py`)

This doc is kept in sync with `src/models/file_record.py` by hand; if they ever drift,
the code wins (see `CHANGELOG.md`'s Module 01 entries for what changed and why —
notably the `file_id` redesign and the addition of the raw-file-info fields below,
neither of which was anticipated when this doc was first drafted pre-implementation).

## Metadata record (per file, stored in `Database/Metadata/metadata_store.json`)

```json
{
  "file_id": "b3f1c2a0-....-....-....-............",
  "source_id": "downloads",
  "original_name": "invoice.pdf",
  "original_path": "/Users/vicky/Downloads/invoice.pdf",
  "current_path": "/.../Finance/GST_Invoice_Amazon_2026-07-05.pdf",

  "extension": ".pdf",
  "mime_type": "application/pdf",
  "size_bytes": 48213,
  "created_at": "2026-07-05T14:31:40Z",
  "modified_at": "2026-07-05T14:31:40Z",
  "content_hash": "83a62aa049d5…",

  "discovered_at": "2026-07-05T14:32:00Z",
  "status": "discovered",
  "error": null,

  "category": "Invoice",
  "extracted_metadata": {
    "vendor": "Amazon",
    "invoice_number": null,
    "invoice_date": "2026-07-05",
    "amount": 1499.00,
    "currency": "INR",
    "tax_type": "GST"
  },

  "suggested_name": "Amazon_2026-07-05.pdf",
  "suggested_destination": "Finance/",
  "naming_signals": {
    "fields_fell_back": []
  },

  "duplicate_of": null,
  "version_group_id": null,
  "version_rank": null,

  "confidence_score": 92,
  "confidence_breakdown": {
    "missing_required_field:invoice_number": -8
  },
  "tier": "approval_required",

  "batch_id": "2026-07-05_143200",
  "processed_at": "2026-07-05T14:32:00Z",
  "approved_by": "user",
  "approved_at": "2026-07-05T14:35:00Z",
  "reversible": true
}
```

### Identity fields — why `file_id` isn't derived from path or content

`file_id` is a permanent, arbitrary identifier (UUID4) assigned once at first discovery
(Module 01) and never recomputed. Two things it deliberately is NOT:

- **Not path-derived.** A file gets moved/renamed by Module 07 during normal operation —
  an ID derived from path would either change (breaking continuity with the existing
  record) or require careful discipline to never re-derive post-move. Assigning it once
  and carrying it forward sidesteps the problem entirely.
- **Not content-derived.** Two different physical files with identical bytes would
  collide onto the same ID, silently merging their Database records before Module 04
  (Duplicate & Version Detection) ever gets to decide what to do about the duplicate.

Instead, three concerns are kept separate:
- **`file_id`** — permanent identity, assigned once, never recomputed.
- **`content_hash`** — SHA-256 of file bytes; what Module 04 actually compares across
  records to find duplicates. Null when the file couldn't be read (`status: "unreadable"`).
- **`current_path`** — live location; Module 01 sets it at discovery (equal to
  `original_path` at that point), Module 07 updates it after every move/rename. Always
  read this field — not `original_path` — to find where a file actually is right now.
  `original_name`/`original_path` stay fixed forever as the first-discovery audit record.

Re-scanning a file that's still sitting at a previously-seen `current_path` reuses that
record's `file_id` and `discovered_at` (see `find_by_current_path()` in
`src/storage/database.py`) rather than minting a new one — this is what keeps repeated
Manual-mode scans idempotent.

`extracted_metadata` shape varies by category — see field lists in `Build-out/03 Metadata Extraction/Module 03 Design.md` §7 (the pre-design pointer doc `03 Metadata Extraction.md` is superseded — see `Module 03 Implementation Audit.md`'s F3 for why). `confidence_breakdown` shape is defined in `Rules/Confidence Rules.md` — every score must be traceable to this list, never a bare AI-estimated number.

## Database/FileIndex (fast lookups)

- `hash_index.json` — `{ "sha256": "file_id" }`
- `phash_index.json` — `{ "perceptual_hash": ["file_id", ...] }`
- `name_index.json` — `{ "normalized_name": ["file_id", ...] }`

## Database/History (lineage)

`version_history.json` — one entry per `version_group_id`:

```json
{
  "version_group_id": "uuid",
  "files": [
    {"file_id": "uuid-v8", "filename": "Resume_v8.pdf", "rank_at_time": "superseded", "superseded_at": "2026-07-05T14:35:00Z"},
    {"file_id": "uuid-v9", "filename": "Resume_v9.pdf", "rank_at_time": "latest"}
  ]
}
```

## Action log (append-only, machine-readable, `Runtime/Logs/action_log.jsonl`)

One JSON line per action:

```json
{"batch_id": "2026-07-05_batch01", "file_id": "uuid", "action": "move_rename", "from": "/Users/vicky/Downloads/invoice.pdf", "to": "/.../Finance/GST_Invoice_Amazon_2026-07-05.pdf", "timestamp": "2026-07-05T14:32:00Z", "approved_by": "user"}
```

Other `action` values: `discover` (Module 01 — a supported file was found and queued), `classify` (Module 02 — a file was assigned a category and classification signals; `details` carries `category`, `signals`, `mode`, `processing_time_ms`, `fallback_used`, `fallback_reason`, `error_detail` when a fallback occurred, and `provider_metadata` when a provider was actually called — see `Build-out/02 Classification/Module 02 Design.md` §12), `extract_metadata` (Module 03 — a classified file had its metadata extracted; `details` carries `category`, `fields_extracted`, `fields_missing`, `mode` (`deterministic` | `text` | `vision` | `mixed`), `processing_time_ms`, `extraction_complete`, `fallback_used`, `fallback_reason`, `redacted_fields` (always present, even when empty — see the Bank Statement `account_last4` rule above), `error_detail` when a fallback occurred, and `provider_metadata` when a provider was actually called — see `Build-out/03 Metadata Extraction/Module 03 Design.md` §7/§13/§18), `detect_duplicates_and_versions` (Module 04 — a file's duplicate/version relationships were detected; `details` carries `duplicate_of`, `version_group_id`, `version_rank`, `match_type` (`exact` | `fuzzy` | `version` | `null`), `phash_distance`, `version_conflict`, `conflict_type` (`date_token_disagreement` | `cross_group` | `null`, plus `conflicting_group_ids` when `cross_group`), `processing_time_ms` — see `Build-out/04 Duplicate & Version Detection/Module 04 Design.md` §7/§17/§18. When Module 04's one disclosed side effect (§4/§7) touches a *different*, earlier-processed record's `version_group_id`/`version_rank`, that other record gets its own second `detect_duplicates_and_versions` log line — `joined_by`/`superseded_by` — rather than a rewrite of its original entry, per the append-only logging philosophy), `suggest_naming_and_destination` (Module 05 — a file's name and destination were suggested; `details` carries `suggested_name`, `suggested_destination`, `fields_fell_back` (which taxonomy fields used their "Unknown_X" placeholder — always present, even when empty, mirroring `redacted_fields`'s convention), `collision_suffix_applied` (bool), `override_applied` (`"exact_duplicate"` | `"superseded_version"` | `null`), `processing_time_ms` — see `Build-out/05 Naming & Destination/Module 05 Design.md` §7/§11/§18. No `fallback_used`/`provider_metadata` — Module 05 has no Provider, §17), `score_confidence` (Module 06 — a file's confidence score, breakdown, and tier were computed; `details` carries `confidence_score`, `confidence_breakdown` (named deduction → negative int, only the deductions that actually applied, per-category-capped — see the "Cap representation" rule below), `tier` (`auto` | `approval_required` | `review_required`), `hard_floors_applied` (list of hard-floor log identifiers that were triggered, in the fixed §13 table order — always present, even when empty, mirroring `fields_fell_back`'s convention), `processing_time_ms` — see `Build-out/06 Confidence & Review/Module 06 Design.md` §9/§12/§13/§16. No `fallback_used`/`provider_metadata` — Module 06 has no Provider, §2), `archive_duplicate`, `archive_superseded_version`, `skip`, `error`, `undo`. (Documentation gaps found and fixed during release audits: `classify` — Module 02 release audit, 2026-07-06; `extract_metadata` — Module 03 release audit, 2026-07-06. Both action types had been in use since their respective modules shipped but were never added here; see `CHANGELOG.md`. `detect_duplicates_and_versions`, `suggest_naming_and_destination`, and `score_confidence` were each added at their respective module's own implementation time specifically to avoid a further recurrence of this gap.)

`confidence_breakdown`'s cap representation (Module 06 Design.md §12): required-field deductions are capped at a total magnitude of 30, optional-field deductions at 10, each enforced independently per record. Fields are walked in a fixed order (the category's taxonomy table order); each missing field gets its full nominal deduction while the running subtotal for its category stays within the cap, and gets `0` — never omitted from `confidence_breakdown` — for every field checked after the cap is reached. This keeps `confidence_breakdown` fully truthful and auditable (every missing field is visible) while guaranteeing the total deduction from either category never exceeds its cap.

An undo replays the matching line(s) for a `batch_id` with `from`/`to` swapped.

### Skip reasons (`action: "skip"`, `details.reason`)

Module 01's `SkippedEntry.reason` / the corresponding action-log `details.reason`: `symlink`, `directory`, `system_file`, `temporary_download`, `ignored_pattern` (reserved, unused by any current v1 rule — see `Rules/Ignore Rules.md`), `zero_byte`, `unstable`, `unsupported_extension`. `system_file`/`temporary_download` replaced a single generic `ignored_name` reason after the Module 01 UAT found it didn't give the user enough information to know *why* something in Downloads wasn't picked up.

## Reports (human-readable, `Runtime/Reports/`)

**Daily Summary** (`Runtime/Reports/Daily Summary/summary_YYYY-MM-DD.md`):

```markdown
# Daily Summary — 2026-07-05

- Files scanned: 12
- Auto-filed: 7
- Approval required: 3
- Review required: 2
- Duplicates found: 1 (archived)
- Versions archived: 1 (Resume_v8.pdf → superseded by v9)
- Errors: 0

## Files
| Original | New Name | Destination | Category | Confidence | Tier |
|---|---|---|---|---|---|
| invoice.pdf | GST_Invoice_Amazon_2026-07-05.pdf | Finance/ | Invoice | 82 | approval_required |
| ... | ... | ... | ... | ... | ... |
```

**Weekly Summary**, **Duplicate Report**, **Storage Report** — same idea, different rollup window/focus; see `Runtime/Reports/README.md`.

## Learning (`Database/Learning/User Corrections.json`)
Schema and purpose: see `Database/Learning/README.md`.
