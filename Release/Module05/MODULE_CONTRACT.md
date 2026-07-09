# Module Contract — Module 05 (Naming & Destination)

Every module in this pipeline declares what it receives, what it produces, what it guarantees about the fields it owns, and — just as importantly — what it must never touch. This is what lets later modules depend on earlier ones without accidentally overwriting each other's work. See `Release/DEPENDENCY_DIAGRAM.md` for how modules chain together and `Release/VERSIONS.md` for versioning.

## INPUT

**Receives:**
`List[FileRecord]` from Module 04 — specifically, every record with `status == "discovered"` and `category is not None` (`Build-out/05 Naming & Destination/Module 05 Design.md` §3/§7). Unlike Module 03, Module 05 does **not** skip `Category.UNKNOWN` — every discovered, classified record (including Unknown) receives a `suggested_name`/`suggested_destination`.

**Also receives (internally):** nothing beyond the record list itself and the other records already processed within the same batch (for within-batch collision detection, §13). Module 05 has **no provider dependency at all** (§17) and reads no `Database/FileIndex/`/`Database/History/` state — see "Provider boundary" below.

## OUTPUT

**Produces:**
- The same `List[FileRecord]` handed in, enriched in place (mirrors every earlier module's batch shape) — **with no disclosed side effect on any other record**, unlike Module 04. Module 05's within-batch collision handling reads other records already processed in the same batch but never writes to them.
- One `suggest_naming_and_destination` action-log entry per file processed in `Runtime/Logs/action_log.jsonl`.
- No new `Database/` structures — unlike Module 04, Module 05 needs no index of its own (there is nothing later modules need to look up *about* a suggested name/destination the way Module 04's hash/name indexes exist so future records can be compared against past ones).

**Guarantees** — fields Module 05 owns and populates:
- `suggested_name` — a non-empty, sanitized filename string with the original extension preserved, populated for every processed record.
- `suggested_destination` — a folder path string, relative to an unresolved library root (real-filesystem resolution is explicitly out of scope for Module 05, §9 — deferred to Module 07), populated for every processed record.
- `naming_signals` (`NamingSignals`) — always a full, populated structure for every processed record, never partially filled: a default/empty structure (no fields recorded) when no fallback occurred, populated with one entry per affected field — using that field's real taxonomy name, never a synthetic label (post-freeze-correction-free per the first Implementation Audit's M1 finding) — when one or more template fields fell back to a placeholder value. Mirrors `classification_signals`/`duplicate_signals`'s "never partially filled" guarantee.

**Determinism guarantee (part of the external contract, not just an internal detail):** given the same input batch, Module 05 always produces the same output. Records within a batch are processed in a fixed, defined order (`discovered_at` ascending, `file_id` lexicographic tie-break, identical to Module 04's own established order) specifically so this holds even when multiple records could otherwise tie for a collision suffix, or the caller's input-list order differs across runs — independently verified at both the unit and integration-testing level (M05-DET01: reversed input-list order, byte-identical outcome, including which of two colliding records receives the `_2` suffix).

## DOES NOT MODIFY

Module 05 never sets or touches any of the following on any record — every one of these is left exactly as Modules 01–04 left it:

- **Module 01's own fields** — `file_id`, `source_id`, `original_name`, `original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `batch_id` are all read, never rewritten.
- **Module 02's own fields** — `category`, `classification_signals` are read, never rewritten.
- **Module 03's own fields** — `extracted_metadata` is read, never rewritten.
- **Module 04's own fields** — `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals` are read (to drive destination-override precedence, §14), never rewritten.
- **Confidence & Review** — `confidence_score`, `confidence_breakdown`, `tier`
- **Preview, Approval & Execution** — `processed_at`, `approved_by`, `approved_at`, `reversible`
- **Logging & Reporting** — `Runtime/Reports/*`. Module 05 only ever appends to `Runtime/Logs/action_log.jsonl`, never to `Reports/`.

**No disclosed exception.** Unlike Module 04, there is no case in which Module 05 modifies a record other than the one it is currently processing.

**Verified by:** `test_module_contract_immutability_every_non_owned_field_byte_identical` (unit — every non-owned `FileRecord` field, sentinel-valued, confirmed byte-identical before/after, built exhaustively from the start of implementation, mirroring Module 04's own eventual M2-driven rigor without needing a follow-up finding to reach it); M05-C01 (integration — the same guarantee re-verified on a real, fully multi-module-populated record, all 29 non-owned fields `asdict()`-compared programmatically); and the UAT restart's own direct confirmation on real, live-judgment-derived records.

## Provider boundary (internal architecture, not part of the external contract)

**Module 05 has no Provider layer at all — the same architectural departure Module 04 established for itself, not an oversight.** Two layers, not three: `suggest_naming_and_destination_batch()` (batch orchestration) → `NamingEngine` (per-file decision-making: build filename → sanitize → resolve within-batch collision → resolve destination). Every decision Module 05 makes is a computation over already-structured data — a category label, a dict of already-extracted string/number values, Module 04's already-computed signals. None of it requires reading and understanding a document's content the way classification or metadata extraction does; Module 05 never opens a file, never looks at an image, never reads text — a narrower surface than even Module 04, which at least reads raw file bytes for hashing (`Module 05 Design.md` §17).

**Explicit disclosure:** as with Module 04, there is no interactive-vs-autonomous distinction to make here. Module 05's OUTPUT guarantees above hold identically whether invoked during a live Claude session or an unattended/scheduled run — there is no judgment-dependent field that could degrade between the two. See `KNOWN_LIMITATIONS.md` for related, disclosed scope boundaries (within-batch-only collision detection; no `tier` awareness, since Module 06 does not exist yet).

## The `tier` parameter is explicitly not part of this contract

The pre-existing scaffold stub's signature (`resolve_destination(category, tier)`) presumed `tier` (Module 06's future output) was available to Module 05. It is not — Module 06 runs after Module 05 in the strict linear pipeline (`Release/DEPENDENCY_DIAGRAM.md`) — and this contract confirms `resolve_destination()` takes no `tier` parameter. Module 05 always computes a real `suggested_destination` for every eligible record, including records that will eventually turn out to be `review_required`; the "don't actually move a `review_required` file" behavior is Module 07's execution-time gate, reading both `suggested_destination` (this module's output) and `tier` (Module 06's output) together. This requires no schema or contract change to any frozen module, since `resolve_destination()`'s parameter list was never part of any frozen contract to begin with — it was only ever an unimplemented stub (`Module 05 Design.md` §8).
