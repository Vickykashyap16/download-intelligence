# Module Contract — Module 06 (Confidence & Review)

Every module in this pipeline declares what it receives, what it produces, what it guarantees about the fields it owns, and — just as importantly — what it must never touch. This is what lets later modules depend on earlier ones without accidentally overwriting each other's work. See `Release/DEPENDENCY_DIAGRAM.md` for how modules chain together and `Release/VERSIONS.md` for versioning.

## INPUT

**Receives:**
`List[FileRecord]` from Module 05 — specifically, every record with `status == "discovered"`, `category is not None` (including `Category.UNKNOWN` — the hard floor for it is exactly what Module 06 exists partly to enforce), and `suggested_name is not None` (confirms Module 05 has already processed the record, so `naming_signals`, `duplicate_signals`, and `extracted_metadata` are all in their final, stable state before Module 06 reads any of them).

**Also receives (internally):** nothing beyond the record list itself. **Module 06 has no provider dependency at all** (`Module 06 Design.md` §2) — see "Provider boundary" below. No cross-record batch state either — unlike Module 04's collision-sensitive ordering or Module 05's within-batch naming-collision ordering, no record's *output value* depends on any other record in the same batch.

## OUTPUT

**Produces:**
- The same `List[FileRecord]` handed in, enriched in place (mirrors every earlier module's batch shape) — **with no disclosed side effect on any other record**, the same as Module 05, unlike Module 04. Module 06 never reads or writes a record other than the one currently being scored.
- One `score_confidence` action-log entry per file processed in `Runtime/Logs/action_log.jsonl`.
- No new `Database/` structures — nothing later in the pipeline needs to look up a record *by* its confidence score or tier; Module 07 reads `tier` directly off the `FileRecord` it's already holding.

**Guarantees** — fields Module 06 owns and fully populates, for every eligible record:
- `confidence_score` — an `int` in `[0, 100]`, populated for every processed record, never left `None`.
- `confidence_breakdown` — a `dict[str, int]`, always present (an empty dict `{}` is the valid, honest "no deductions applied" case — the file scored a clean 100 — not a sentinel for "not yet processed"; distinguishing "not yet processed" from "processed, nothing to deduct" is done via `confidence_score is None`, not via `confidence_breakdown`'s emptiness).
- `tier` — one of `"auto"` | `"approval_required"` | `"review_required"`, populated for every processed record, never left `None`.

**Determinism guarantee (part of the external contract):** given the same input record (its own fields, independent of any other record in the batch or any prior run's state), Module 06 always produces the same score, breakdown, and tier. Batch order still follows the established `discovered_at` ascending / `file_id` lexicographic tie-break convention for log-ordering consistency, but no record's output value depends on that order — independently verified at both the unit level (`test_batch_deterministic_order_reversed_input_produces_byte_identical_field_values`) and the integration/UAT level (a real reversed-input-order rerun against real storage).

## DOES NOT MODIFY

Module 06 never sets or touches any of the following on any record — every one is left exactly as Modules 01–05 left it:

- **Module 01's own fields** — `file_id`, `source_id`, `original_name`, `original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `batch_id` are all read (`status`, `file_id`, `discovered_at`) or ignored, never rewritten.
- **Module 02's own fields** — `category`, `classification_signals` are read, never rewritten.
- **Module 03's own fields** — `extracted_metadata` is read, never rewritten.
- **Module 04's own fields** — `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals` are read (`duplicate_signals` only), never rewritten.
- **Module 05's own fields** — `suggested_name`, `suggested_destination`, `naming_signals` are read, never rewritten.
- **Preview, Approval & Execution** — `processed_at`, `approved_by`, `approved_at`, `reversible`.
- **Logging & Reporting** — `Runtime/Reports/*`. Module 06 only ever appends to `Runtime/Logs/action_log.jsonl`, never to `Reports/`.

**No disclosed exception.** Like Module 05, and unlike Module 04, there is no case in which Module 06 modifies a record other than the one it is currently processing.

**Verified by:** `test_module_contract_immutability_every_non_owned_field_byte_identical` (unit — every non-owned `FileRecord` field, sentinel-valued, confirmed byte-identical before/after, built exhaustively from the start); M06-C01/M06-C02 (integration — the same guarantee re-verified on 13 real, fully multi-module-populated records, every field programmatically compared, not spot-checked); and the UAT restart's own direct, full field-by-field diff on 23 real records (`Tests/Module 06 UAT Plan.md`, "Run 2 — Restart," Step 7).

## Provider boundary (internal architecture, not part of the external contract)

**Module 06 has no Provider layer at all — the narrowest architectural surface of any module built so far, confirmed across four independent Design Review passes (`Module 06 Design.md` §2).** Two layers, not three: `score_confidence_batch()` (batch orchestration) → `ConfidenceEngine` (per-file decision-making: `compute_deductions()` → `compute_score()` → `lookup_tier()` → `apply_hard_floors()`). Every one of `Rules/Confidence Rules.md`'s nine deductions and four hard floors resolves to a direct field read or null-check against an already-computed upstream signal — never a re-read of file bytes, never a new judgment call about what a file *is* or *says*. This is a stronger case for "no provider" than either Module 04's or Module 05's own reasoning: those modules at least touch derived-from-content data; Module 06 touches only *other modules' already-finished judgments about that data*.

**Explicit disclosure:** as with Modules 04/05, there is no interactive-vs-autonomous distinction to make here. Module 06's OUTPUT guarantees above hold identically whether invoked during a live Claude session or an unattended/scheduled run — there is no judgment-dependent field that could degrade between the two. See `KNOWN_LIMITATIONS.md` for the one related, disclosed, inherited caveat (the "Corrupted file" hard floor's incomplete coverage for Archive/Audio/Application/Video, inherited from Modules 02/03's existing signal set).

## Required/optional field taxonomy is independently defined, never imported

`confidence.py` defines its own literal required/optional field taxonomy table, sourced from and matching `Build-out/03 Metadata Extraction/Module 03 Design.md` §7 — not imported from `pipeline/metadata.py`'s `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` constants, since those are internal implementation detail, not part of Module 03's `MODULE_CONTRACT.md`. A permanent regression test (`test_taxonomy_matches_metadata_module_real_constants`) cross-checks Module 06's own table against `metadata.py`'s real, current constants for the test's own verification purposes only — this does not create a contract dependency, only a drift-detection guard, following the same discipline `Rules/Confidence Rules.md`'s own citation-and-taxonomy-cross-check test already established.

## "Unknown category" and "Corrupted file" are one hard floor, not two

`Rules/Confidence Rules.md` names these as two separate business rules, but both resolve to one identical, indistinguishable trigger (`category == Category.UNKNOWN`) on the data Module 06 actually has access to — implemented and logged as a single hard floor with one identifier, `unknown_category`, never two separate `hard_floors_applied` entries for one underlying fact (`Module 06 Design.md` §2.4/§13).
