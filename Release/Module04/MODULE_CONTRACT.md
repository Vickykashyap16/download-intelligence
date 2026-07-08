# Module Contract — Module 04 (Duplicate & Version Detection)

Every module in this pipeline declares what it receives, what it produces, what it guarantees about the fields it owns, and — just as importantly — what it must never touch. This is what lets later modules depend on earlier ones without accidentally overwriting each other's work. See `Release/DEPENDENCY_DIAGRAM.md` for how modules chain together and `Release/VERSIONS.md` for versioning.

## INPUT

**Receives:**
`List[FileRecord]` from Module 03 — specifically, every record with `status == "discovered"`. Unlike Modules 02→03's handoff, Module 04 does **not** gate its entire scope on `category` being set and non-`Unknown`: exact-duplicate detection is content-based and runs on every discovered record (including `Category.UNKNOWN`), while near-duplicate and version-chain detection are scoped to specific categories (`Build-out/04 Duplicate & Version Detection/Module 04 Design.md` §3/§9).

**Also receives (internally):** nothing beyond the record list and the accumulated `Database/FileIndex/`/`Database/History/` state built up across all prior runs. Module 04 has **no provider dependency at all** (§14) — see "Provider boundary" below.

## OUTPUT

**Produces:**
- The same `List[FileRecord]` handed in, enriched in place (mirrors `classify_batch()`/`extract_metadata_batch()`'s shape) — **with one disclosed exception**: Module 04 may also update the `version_group_id` and/or `version_rank` fields of a *different*, earlier-processed record already in the store, as a bounded side effect of detecting a version-chain relationship involving it (§7, §16, post-freeze correction #1). This is the one place in the pipeline so far where a module's own batch call can modify a record outside the list it was directly handed.
- One `detect_duplicates_and_versions` action-log entry per file processed in `Runtime/Logs/action_log.jsonl`. When the one disclosed side effect touches another record, that record gets its own second, later, append-only log line (`joined_by`/`superseded_by`) — never a rewrite of its original entry.
- Updated `Database/FileIndex/*.json` and, when a version chain is touched, `Database/History/version_history.json`.

**Guarantees** — fields Module 04 owns and populates:
- `duplicate_of` — the `file_id` of the exact-duplicate original, or `null` if none found.
- `version_group_id` — a UUID shared by every member of a detected version chain, or `null` if the record isn't part of one.
- `version_rank` — `"latest"` | `"superseded"`, populated only when `version_group_id` is set; `null` otherwise.
- `duplicate_signals` (`DuplicateSignals`) — always a full, populated structure for every processed record, never partially filled, storing only the single best-scoring match per detection type (never a list of several simultaneous candidates) — mirrors `classification_signals`'s "never partially filled" guarantee.

**Determinism guarantee (part of the external contract, not just an internal detail):** given the same input batch and the same accumulated `Database/FileIndex/`/`Database/History/` state, Module 04 always produces the same output. Records within a batch are processed in a fixed, defined order (`discovered_at` ascending, `file_id` lexicographic tie-break) specifically so this holds even when multiple version-chain candidates could otherwise tie, or the caller's input-list order differs across runs — independently verified at the integration-testing level (M04-DET01: reversed input-list order, byte-identical outcome).

## DOES NOT MODIFY

Module 04 never sets or touches any of the following on any record — every one of these is left exactly as Modules 01–03 left it:

- **Module 01's own fields** — `file_id`, `source_id`, `original_name`, `original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `batch_id` are all read, never rewritten.
- **Module 02's own fields** — `category`, `classification_signals` are read, never rewritten.
- **Module 03's own fields** — `extracted_metadata` is read (its category-appropriate date field, via `_best_available_date()`), never rewritten.
- **Naming & Destination** — `suggested_name`, `suggested_destination`
- **Confidence & Review** — `confidence_score`, `confidence_breakdown`, `tier`
- **Preview, Approval & Execution** — `processed_at`, `approved_by`, `approved_at`, `reversible`
- **Logging & Reporting** — `Runtime/Reports/*`. Module 04 only ever appends to `Runtime/Logs/action_log.jsonl`, never to `Reports/`.

**The one disclosed exception:** on a *different*, earlier-processed record involved in a version-chain relationship, only `version_group_id` and/or `version_rank` may change — never any other field on that other record.

**Verified by:** `test_module_contract_immutability_every_non_owned_field_byte_identical` (unit — all 27 non-owned `FileRecord` fields, sentinel-valued, confirmed byte-identical before/after, mirroring Module 03's own exhaustive precedent — added as part of the second Independent Implementation Audit's resolution of finding M2, which found the original two immutability tests only spot-checked a handful of fields); `test_module_contract_side_effect_exhaustively_verified_on_other_record` (unit — the one disclosed exception, including a real assertion on the affected other record's final `version_rank` value, not merely "changed"); M04-C01/M04-C02 (integration — the same two guarantees re-verified on a real, fully multi-module-populated record and a real cross-run side-effect update); and the UAT restart's own direct 0-diff Module Contract boundary check on a real record (`Resume_JordanPatel_v3.pdf`, `Runtime/UAT/Module04_UAT_2026-07-08_211306/summary.md`).

## Provider boundary (internal architecture, not part of the external contract)

**Module 04 has no Provider layer at all — a deliberate departure from Modules 02/03's pattern, not an oversight.** Two layers, not three: `detect_duplicates_batch()` (batch orchestration) → `DuplicateDetectionEngine` (per-file decision-making, calling `storage/database.py`'s FileIndex lookups directly, since there is no Provider layer to shield it behind). Every decision Module 04 makes — hash equality, perceptual-hash distance, filename similarity score, version-token parsing, date comparison — is a computation over already-extracted, already-structured data; none of it requires reading and understanding a document's content the way classification or metadata extraction does (`Module 04 Design.md` §14).

**Explicit disclosure:** unlike Modules 02/03, there is no interactive-vs-autonomous distinction to make here. Module 04's OUTPUT guarantees above hold identically whether invoked during a live Claude session or an unattended/scheduled run — there is no judgment-dependent field that could degrade between the two. See `KNOWN_LIMITATIONS.md` for the one related, disclosed caveat (a future version could add a live-judgment provider if the deterministic signals prove insufficiently discriminating in practice — not built, and not needed, for v1).

## Hashing algorithms are explicitly not part of this contract

The contract guarantees only the *semantic behavior* of `content_hash` and any perceptual-hash values Module 04 derives: stable across runs, deterministic for identical input, and comparable (via equality for `content_hash`, via distance for a perceptual hash). The contract makes no guarantee about, and no other module may depend on, which specific algorithm produces that behavior — not SHA-256 for `content_hash` (Module 01's implementation detail, already frozen), and not any particular perceptual-hash variant, hash size, or Hamming-distance calculation Module 04 itself chooses. A future algorithm or parameter change is a storage/index migration event governed by `Governance/FROZEN_MODULE_CHANGE_POLICY.md`, not a contract change (`Module 04 Design.md` §11A).
