# Module 05 (Naming & Destination) — Design

Pre-implementation design for Module 05, produced under `Governance/ENGINEERING_STANDARD.md`'s lifecycle (Design → Independent Design Review → Design Refinement → Design Freeze → Implementation → ...). No implementation code has been written. This document supersedes the pre-design pointer note `Build-out/05 Naming & Destination/05 Naming & Destination.md` — that note is not deleted (workspace convention), but is no longer the canonical description of this module's architecture; this document is.

Produced on `module05-design` (git branch), against Pipeline v0.4.0 (Modules 01–04 permanently frozen and released — `Release/VERSIONS.md`). Reconstructed from first principles rather than assumed: `Governance/ENGINEERING_STANDARD.md`, `Governance/ARCHITECTURE_DECISIONS.md` (19 decisions), `Governance/PIPELINE_CONTRACT_VERIFICATION.md`, `Governance/FROZEN_MODULE_CHANGE_POLICY.md`, `Release/Module01–04/MODULE_CONTRACT.md`, `Release/VERSIONS.md`, `Release/DEPENDENCY_DIAGRAM.md`, `src/models/file_record.py`, `Rules/Naming Rules.md`, `Rules/Folder Rules.md`, `Rules/Confidence Rules.md`, `src/pipeline/metadata.py`'s real `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` taxonomy (the ground truth, not the design doc's own prose description of it), `src/pipeline/naming.py`'s pre-existing scaffold stub, and `src/config/sources.yaml`.

**Unlike Module 04's first draft, this design initially surfaced a substantial number of open architectural questions** — not because the module is more complex than Module 04, but because `Rules/Naming Rules.md` and `Rules/Folder Rules.md` were both written before Module 03's real, frozen taxonomy existed (they predate real field names), before Module 04 established the "signal vs. execution" split as a formal pattern, and before the strict linear pipeline order (`ARCHITECTURE_DECISIONS.md` #17) was written down as an explicit constraint. Several of these gaps were already flagged as deferred to this exact design phase by `Release/Module03/KNOWN_LIMITATIONS.md`'s finding F5; several more were newly discovered by this design's own field-by-field cross-check (§10). **All 12 were subsequently resolved through an explicit, item-by-item architectural decision review (2026-07-09) and approved by the project owner.** See §29, "Resolved architectural decisions," for the complete record of each decision, its alternatives, and its rationale.

---

## 1. Purpose

Module 05 answers one question for every file Modules 01–04 have already discovered, classified, metadata-extracted, and duplicate/version-checked: **"what should this file be called, and where should it go?"** It turns a category plus its extracted metadata (plus any duplicate/version signal from Module 04) into two suggestions:

- **`suggested_name`** — a human-readable filename, following `Rules/Naming Rules.md`'s per-category template, with the original extension preserved.
- **`suggested_destination`** — a folder path (relative to a filed-library root Module 05 itself never resolves to an absolute path — see §9), following `Rules/Folder Rules.md`'s category mapping, with Module 04's duplicate/version overrides taking precedence when they apply.

Module 05 suggests. It does not execute. Consistent with the "signal vs. fact, suggestion vs. execution" split this pipeline already establishes for Module 04 (§28 of `Module 04 Design.md`): no file is moved, renamed, or touched on disk by this module. That is Module 07's job.

## 2. Responsibilities

Module 05 owns:
- Filling the category-appropriate naming template from `extracted_metadata`, with a defined, deterministic fallback for every field that could be missing (§11).
- Sanitizing the filled template into a valid, safe filename (§12).
- Detecting and resolving *within-batch* filename collisions (§13) — the only collision class Module 05 can actually observe (see §9 for why real-filesystem collision detection is explicitly out of scope for this module).
- Mapping category to a destination folder per `Rules/Folder Rules.md`, applying Module 04's duplicate/version overrides when they apply (§14).
- Populating `suggested_name`, `suggested_destination`, and `naming_signals` (a new `FileRecord` field, confirmed §29 item 3) recording which fields fell back, for Module 06's `-10`-per-fallback deduction to consume.
- Logging one `suggest_naming_and_destination` action-log entry per file it processes (§18).

Module 05 must never:
- Move, rename, delete, or archive a file on disk, or create a destination folder. It has no filesystem-write role in this pipeline at all — it never even reads the destination library's real directory listing (§9). (Module 07's job.)
- Decide *whether* a file actually gets filed — that depends on `tier` (`review_required` → not moved at all, per `Rules/Folder Rules.md`), which does not exist yet when Module 05 runs (§8). Module 05 always computes a suggestion; Module 07 decides whether to act on it.
- Compute a confidence score or tier, even though its own fallback signal directly feeds one of `Rules/Confidence Rules.md`'s existing deductions (`-10` per naming fallback). (Module 06's job.)
- Touch any field owned by Module 01, 02, 03, or 04.
- Re-derive or override any judgment Module 02/03 already made (e.g. it never second-guesses `category` or re-extracts a metadata field) — it only consumes what's already there.

## 3. Inputs

**Receives:** `List[FileRecord]` from Module 04 — specifically, every record with `status == "discovered"`. **Unlike Module 03 (which excludes `Category.UNKNOWN`), Module 05 must include `Category.UNKNOWN`** — `Rules/Folder Rules.md`'s own override table states "Unknown category → always `Unknown/`, regardless of confidence score," which is a real naming/destination outcome Module 05 is responsible for producing, not something that can be silently skipped the way Module 03 skips it. (Records with `category is None` — Module 01 never had readable bytes — are excluded, same as every judgment-dependent module upstream; see §26.)

**Also receives (internally):** nothing beyond the record list and the already-accumulated `Database/FileIndex/`/`Database/History/` state Module 04 built (read-only — Module 05 never writes to `Database/FileIndex/`/`Database/History/`, those remain exclusively Module 04's). Module 05 has no provider dependency (confirmed, §17).

## 4. Outputs

**Produces:**
- The same `List[FileRecord]` handed in, enriched in place (mirrors every earlier module's batch shape).
- One `suggest_naming_and_destination` action-log entry per file processed in `Runtime/Logs/action_log.jsonl` (§18).
- No new `Database/` structures are proposed — unlike Module 04, Module 05 needs no index of its own (there is nothing later modules need to look up *about* a suggested name/destination the way Module 04's hash/name indexes exist so future records can be compared against past ones).

## 5. Module Contract

**INPUT:** `List[FileRecord]` from Module 04, `status == "discovered"`, including `Category.UNKNOWN` (§3).

**OUTPUT:** Same records, enriched in place. No disclosed side effect on any other record (unlike Module 04) — Module 05's within-batch collision handling (§13) reads other records in the same batch but never writes to them.

**Guarantees** — fields Module 05 owns and populates, confirmed per §29:
- `suggested_name` — a non-empty, sanitized filename string with the original extension preserved, populated for every processed record.
- `suggested_destination` — a folder path string, relative to an unresolved library root (§9 — resolving that root is explicitly out of scope for Module 05; see §27), populated for every processed record.
- `naming_signals` — a new `FileRecord` field (confirmed §29 item 3), mirroring `classification_signals`/`duplicate_signals`'s established pattern: a small, typed structure recording which specific fields fell back to a placeholder value, for Module 06's deduction to consume without needing to re-run Module 05's own template logic. Populated for every processed record: a default/empty structure (no fields recorded) when no fallback occurred, populated with one entry per affected field when one or more fallbacks occurred.

**DOES NOT MODIFY:** every field owned by Modules 01–04 (per their frozen contracts — see §23); every field reserved for Modules 06–08 (`confidence_score`, `confidence_breakdown`, `tier`, `processed_at`, `approved_by`, `approved_at`, `reversible`).

**Provider boundary:** none. Module 05 is fully deterministic — no provider of any kind (confirmed §29 item 11; see §17).

**Verified by:** to be built during implementation (§28) — a Module Contract immutability test (every non-owned field byte-identical before/after), mirroring every earlier module's own such test.

## 6. Internal architecture (confirmed)

Confirmed: two-layer shape, mirroring Module 04's, no provider (§17, §29 item 11):

```
suggest_naming_and_destination_batch()  (src/pipeline/naming.py — batch orchestration,
                                          persistence, logging — mirrors
                                          detect_duplicates_batch()'s shape)
      -> NamingEngine  (per-file decision-making: build filename -> sanitize ->
                         resolve within-batch collision -> resolve destination;
                         fully deterministic)
```

No Engine/Provider split. If a genuine judgment need is ever discovered in a future version, `Governance/ARCHITECTURE_DECISIONS.md` decision #4/#5 already establishes that a module needing this pattern writes its own Engine/Provider classes rather than importing Module 02's or Module 03's — noted here only as forward-compatibility context (§27), not a plan for this release.

Supporting helpers (in `naming.py`, not `core/`, following the established convention that module-specific naming/formatting logic stays local — same rationale Module 03 and Module 04 both used for their own filename helpers):
- `build_filename(record)` — fills the category template from `extracted_metadata`, using the confirmed per-category field mapping (§10, §11).
- `sanitize_filename(name)` — enforces the confirmed rules (§12).
- `resolve_within_batch_collision(name, destination, seen_this_batch)` — the `_2`/`_3` suffix logic, scoped to what Module 05 can actually observe (§13).
- `resolve_destination(record)` — category → folder mapping plus Module 04's override precedence (§14). Confirmed signature takes no `tier` parameter (§29 item 1) — the pre-existing scaffold signature `resolve_destination(category, tier)` presumed `tier` was available at this point in the pipeline; it is not (§8), and that stub is now formally superseded by this design.

## 7. Processing workflow (confirmed)

For each record, in **the same deterministic batch order Module 04 already established** (`discovered_at` ascending, `file_id` lexicographic tie-break) — confirmed (§29 item 12), for the sole reason that matters here: within-batch collision-suffix assignment (§13) must be reproducible across re-runs of an identical batch:

1. **Skip ineligible records:** `status != "discovered"` or `category is None` are left untouched (§26). Unlike Module 03, `Category.UNKNOWN` is **not** skipped (§3).
2. **Build the filename:** look up the category's template (§10, confirmed per-category field mapping), fill it from `extracted_metadata`, applying the confirmed fallback for every missing field (§11) and recording which fields fell back in `naming_signals` (§29 item 3).
3. **Sanitize:** apply §12's confirmed rules (whitelist character filtering, naive Title_Case, longest-field truncation).
4. **Resolve destination:** category → folder (`Rules/Folder Rules.md`), with Module 04's `duplicate_of`/`version_rank` overrides taking precedence when they apply, regardless of category (§14) — mirroring Module 04's own "exact-duplicate detection runs regardless of category" precedent (§9 of `Module 04 Design.md`).
5. **Resolve within-batch collision:** if another record already processed in this same batch produced the identical `(suggested_name, suggested_destination)` pair, apply the `_2`/`_3` suffix (§13). **Real-filesystem collision detection against the destination library is explicitly out of scope for this module** (§9) — Module 07 is responsible for the authoritative check at execution time, since only it has a guaranteed-current view of the destination.
6. **Persist and log:** save the record, append one `suggest_naming_and_destination` action-log entry (§18).

A single record's failure at any step never aborts the batch — the same resilience pattern every earlier module already establishes (§21).

## 8. The `tier` ordering resolution (confirmed, §29 item 1)

`Rules/Folder Rules.md`'s override table states: *"`review_required` tier (score < 80) → not moved at all, regardless of category. The file stays in its original location."* This is a real, named override — but `tier` is Module 06's output, and Module 06 runs **after** Module 05 in the strict linear pipeline (`ARCHITECTURE_DECISIONS.md` #17, `Release/DEPENDENCY_DIAGRAM.md`: 04 → 05 → 06 → 07). Module 05 cannot possibly know a record's `tier` at the time it computes `suggested_destination`, because that tier does not exist yet.

This directly contradicts the pre-existing scaffold stub's own signature — `resolve_destination(category: str, tier: str)` in `src/pipeline/naming.py` — which presumes `tier` is a Module 05 input. It was written before Module 04 existed and before the pipeline order was formalized as an explicit architectural constraint; it is not evidence that this was ever actually resolved.

**Confirmed resolution (§29 item 1):** `resolve_destination()` drops the `tier` parameter entirely. Module 05 always computes a real `suggested_destination` for every eligible record — including records that will eventually turn out to be `review_required` — based only on category (plus Module 04's overrides, §14). The "don't actually move a `review_required` file" behavior is Module 07's execution-time gate: Module 07 reads both `suggested_destination` (Module 05's output) and `tier` (Module 06's output, available by the time Module 07 runs) together, and does not execute the move when `tier == "review_required"`, leaving the file in its original location exactly as `Folder Rules.md` specifies. This mirrors Module 04's own "supplies the signal, a later module applies the routing/execution rule" pattern exactly, and requires no schema or contract change to any frozen module — it only finalizes what `resolve_destination()`'s own signature looks like, which was never part of any frozen contract to begin with (it was only ever an unimplemented stub). Module 07's own design is responsible for actually implementing this gate; that implementation is out of scope for Module 05.

## 9. Filesystem-read scope: what Module 05 does and does not touch

**Confirmed (§29 item 2):** Module 05 never reads the real destination library's directory listing, and never learns the destination library's absolute root path. Three independent reasons converged on this decision:

- **No configuration for it exists.** `src/config/sources.yaml` configures only the *source* (the Downloads folder being scanned) — there is no equivalent "destination library root" entry anywhere in the actual implementation. `suggested_destination` is documented (`05 Naming & Destination.md`, the pointer note this design supersedes) as "relative to the filed library root" — meaning Module 05 was always intended to output a *relative* path, never resolve it to an absolute one.
- **A relative-path output needs no real filesystem access to produce.** Every input Module 05 needs (category, `extracted_metadata`, Module 04's overrides) is already in the `FileRecord` it's processing — no destination-folder read is required to compute a category → relative-folder mapping.
- **The destination library's true state is only guaranteed accurate at execution time.** Even if Module 05 *could* read the real destination folder, that read could be stale by the time Module 07 actually executes the move (a real Downloads-folder-processing workflow implies a real time gap between "suggest" and "approve and execute" — the whole reason a Preview/Approval stage, Module 07, exists at all). A collision check performed at suggestion time would be a guess Module 07 would have to re-verify anyway.

**Consequence:** Module 05's own collision detection (§13) is necessarily scoped to *within the current batch only* — two records processed in the same run that would independently produce the identical `(suggested_name, suggested_destination)` pair. This is a real, useful, and fully self-contained check Module 05 can perform without any filesystem dependency beyond what it's already given. The *authoritative* collision check — against the real, current state of the destination library — is Module 07's responsibility at execution time, which this design explicitly does not attempt to pre-empt or duplicate.

## 10. Naming template field-mapping audit — cross-checked against the real, frozen Module 03 taxonomy (not the design doc's prose description of it)

`Rules/Naming Rules.md` was written before Module 03's real taxonomy (`REQUIRED_FIELDS`/`OPTIONAL_FIELDS` in `src/pipeline/metadata.py`) existed. This section cross-checks every category's template placeholder against the actual, ground-truth field names — not against `Build-out/03 Metadata Extraction.md`'s superseded prose description, and not against `Rules/Naming Rules.md`'s own possibly-stale assumptions. Two mismatches were already flagged as deferred to this exact design phase by `Release/Module03/KNOWN_LIMITATIONS.md` (finding F5); the rest were newly discovered by this audit. All mismatches are now resolved (§29).

| Category | Template (`Naming Rules.md`) | Real Module 03 fields (required + optional) | Finding |
|---|---|---|---|
| Invoice | `{DocSubtype}_{Vendor}_{Date}` | `vendor`, `invoice_date` (req) + `invoice_number`, `amount`, `currency`, `tax_type` (opt) | `{Vendor}`→`vendor` OK. `{Date}`→`invoice_date` OK (rename only). `{DocSubtype}` had no corresponding taxonomy field — **resolved (§29 item 4):** template revised to `{Vendor}_{InvoiceNumber}_{Date}`, falling back to `{Vendor}_{Date}` when `invoice_number` is absent. |
| Resume | `Resume_{CandidateName}_{VersionOrDate}` | `candidate_name` (req) + `version_indicator`, `last_modified_date` (opt) | `{CandidateName}`→`candidate_name` OK. `{VersionOrDate}` composite had no stated priority rule — **resolved (§29 item 9):** `version_indicator` takes priority when present, falling back to `last_modified_date`, falling back to `Unknown` when neither is present. |
| Bank Statement | `{BankName}_Statement_{Period}` | `bank_name`, `statement_period` (req) + `account_last4` (opt) | Clean match (rename only: `{BankName}`→`bank_name`, `{Period}`→`statement_period`). |
| Contract | `{ContractType}_{PartyName}_{EffectiveDate}` | `contract_type`, `counterparty`, `effective_date` (req) + `term_length` (opt) | `{ContractType}`/`{EffectiveDate}` OK. `{PartyName}` renamed to `{Counterparty}` — a clean rename, no ambiguity, already flagged `Release/Module03/KNOWN_LIMITATIONS.md` F5; not part of the 12-item decision review since no alternative existed. |
| Document (generic) | `{BestGuessTitle}_{DateIfKnown}` | `best_guess_title` (req) + `document_date`, `description` (opt) | Clean match (rename only: `{DateIfKnown}`→`document_date`). |
| Image | `{Description}_{Variant}` | `description` (req) + `variant`, `capture_date` (opt) | Clean match (rename only). |
| Screenshot | `Screenshot_{ContextDescription}_{Date}` | `context_description` (req) + `capture_date` (opt) | Clean match (rename only: `{Date}`→`capture_date`). |
| Application | `{AppName}_{Version}_{Platform}` | `app_name` (req) + `version`, `platform` (opt) | Clean match, no rename needed. |
| Archive | `{ContentsSummary}_{Date}` | `contents_summary` (req); **no optional fields at all** | `{ContentsSummary}` OK. `{Date}` had no corresponding field anywhere in Archive's taxonomy — **resolved (§29 item 5):** falls back directly to `modified_at` (Module 01, tier-4). |
| Video | `{Description}_{Date}` | `description` (req) + `duration`, `content_date` (opt) | `{Description}` OK. `{Date}`→`content_date`, always `null` in v1 (no video-tag library approved, `Release/Module03/KNOWN_LIMITATIONS.md`) — **resolved (§29 item 7):** falls back to `modified_at` (Module 01, tier-4), same rule as Archive. |
| Audio | `{TrackTitle}_{Artist}` (fallback: `{Description}_{Date}`) | `track_title` (req) + `artist`, `duration`, `recording_date` (opt); **no `description` field at all** | `{TrackTitle}`/`{Artist}` OK for the primary template. The documented fallback template `{Description}_{Date}` referenced a field (`description`) that does not exist anywhere in Audio's taxonomy — **resolved (§29 item 8):** fallback template is `{TrackTitle}_{RecordingDate}`, falling back further to `{TrackTitle}` alone when `recording_date` is also absent. |
| Unknown | `UNSORTED_{OriginalName}` | N/A — Module 03 never processes `Category.UNKNOWN` at all | `{OriginalName}` resolves to `FileRecord.original_name` (Module 01's field), never `extracted_metadata` — the only category whose naming has zero Module 03 dependency. |

**All mismatches surfaced by this audit have been resolved** via the explicit architectural decision review (§29 items 4, 5, 7, 8, 9) — each is now reflected in the table above and, for Invoice, Resume, Archive, Video, and Audio, changes the effective template from what `Rules/Naming Rules.md` currently documents. **`Rules/Naming Rules.md` itself is a living business-rules document maintained outside this design's authority (`Rules/` per `CLAUDE.md`) and is not edited by this document** — updating it to match Module 05's confirmed implementation is a required follow-up action at implementation time, not performed here.

## 11. Filling the template — fallback strategy (confirmed)

**Confirmed structural principle (mirrors `ARCHITECTURE_DECISIONS.md` #7/#19 exactly):** a missing field is never silently blanked and never fabricated. `Rules/Naming Rules.md`'s own stated convention — a named, safe fallback value (`Unknown_Vendor`, `Unknown_Date`) rather than an empty gap or a raw placeholder token — is adopted as-is. Which real field feeds which placeholder, and every category's fallback chain, is now fully confirmed per §10's resolved table and §29 items 4, 5, 7, 8, 9 (e.g. Archive's now-placeholder-less date slot falls back to `modified_at`, per §29 item 5).

**Every fallback used is recorded**, not just silently applied — this is the raw signal `naming_signals` (§5, §29 item 3, confirmed) exists to carry forward to Module 06's `-10`-per-fallback deduction, the same "the module that causes a deduction-worthy event is the one that must supply the auditable signal for it" principle Module 04 established for `duplicate_signals`.

## 12. Sanitization rules (confirmed, §29 item 6; whitespace handling corrected post-freeze — see below)

`Rules/Naming Rules.md` states, qualitatively: `Title_Case_With_Underscores`, no spaces, no special characters, dates in `YYYY-MM-DD`, max ~80 characters, always preserve the original extension. This design closes that qualitative gap with the same numeric/algorithmic precision Module 03's redaction rule and Module 04's similarity threshold received (`ARCHITECTURE_DECISIONS.md` #9, `Module 04 Design.md` §10):

- **Whitespace normalization (confirmed, post-freeze correction #1):** every run of one or more whitespace characters (spaces, tabs, newlines, and other Unicode whitespace matched by Python's `\s`) is converted to a single `_` **before** the whitelist filter below runs. This is a normalization step, not a character-class exception — it ensures the word boundaries in a multi-word field value (e.g. a vendor name, a person's name, a document title) are preserved as the `Title_Case_With_Underscores` convention's own name implies, rather than silently disappearing.
- **Character set:** whitelist-only, applied after whitespace normalization above. Letters, digits, underscore, and hyphen pass through; every other character (including all Unicode outside that set) is stripped, not replaced or rejected. Chosen over a blacklist approach because a whitelist is a closed, structurally enforced boundary rather than a reactive list that could miss a dangerous character class — the same "structural trust boundary, not a denylist" principle `ARCHITECTURE_DECISIONS.md` #8/#9 already establishes elsewhere, and it directly closes §19's path-injection concern (path separators, `..`, and every other traversal-relevant character are excluded by construction, not by enumeration). Because whitespace is now converted to `_` first (above), it never reaches this step as whitespace — it is a normal segment separator by the time the whitelist runs, and existing underscores are left as-is (no doubling: a run of whitespace collapses to exactly one `_`, and a pre-existing `_` adjacent to normalized whitespace is not duplicated, per the implementation's segment-based joining in §12's truncation/Title_Case steps below).
- **Title_Case:** naive per-word capitalization of every underscore-delimited segment, with no exceptions list (no acronym preservation, no numeric special-casing). An acronym like `NDA` may render as `Nda` — accepted as a cosmetic cost, consistent with this project's general tolerance for cosmetic imperfection over added rule complexity and ongoing exceptions-list maintenance.
- **Truncation:** if the filled-and-sanitized name (before the extension, before any collision suffix) exceeds ~80 characters, the single longest field value is truncated first, preserving the template's overall structure and every other field intact. Reject/flag-instead-of-truncate was rejected because it would violate the "always produce a suggestion, never blank" principle (§11, `ARCHITECTURE_DECISIONS.md` #7/#19). A truncated name can still collide with another record's name — that case is handled the same as any other collision, by §13's within-batch suffixing.
- **`Category.UNKNOWN`:** `UNSORTED_{OriginalName}` goes through the identical sanitization pass as every other category — no separate code path. Accepted trade-off: an unusual `original_name` may sanitize into something less recognizable, at low severity given `Unknown` is already the lowest-trust, review-adjacent category.

**Post-freeze correction #1 (design-completeness gap, discovered during UAT, applied 2026-07-09) — internal whitespace was silently stripped rather than converted to `_`, undermining this section's own "human-readable filename" purpose (§1) for the common case of multi-word field values:** as originally frozen, this section's whitelist rule (above) treated whitespace exactly like any other disallowed character — stripped, not replaced — so a real, live-judgment-derived value like `"Northwind Traders"` sanitized to `"Northwindtraders"` rather than `"Northwind_Traders"`. This was a faithful implementation of what was actually written (confirmed: not an implementation defect — `Governance/FROZEN_MODULE_CHANGE_POLICY.md` §1.2's "confirm it reproduces against the frozen module's own code and frozen contract" check was performed and the behavior matched the frozen text exactly), but the specific, high-impact consequence for multi-word real-world content was never separately surfaced or weighed during this design's original review — only the narrower acronym-casing cosmetic cost (`"NDA"` → `"Nda"`) was explicitly named and accepted. Discovered during Module 05's User Acceptance Testing (`Tests/Module 05 UAT Plan.md`, Finding UAT-1), where 8 of 17 real UAT files (47%) — a vendor name, a counterparty name, a candidate name, a document title, an archive contents summary, and others — lost their internal word spacing entirely. Classified Medium severity per `Governance/FROZEN_MODULE_CHANGE_POLICY.md` §2 (a real, contained, non-catastrophic defect: no data loss, crash, or security issue, but a systemic readability regression against §1's own stated purpose and against `Rules/Naming Rules.md`'s own `Title_Case_With_Underscores` convention name, affecting the majority of real multi-word content rather than a rare edge case). Approved by the project owner on 2026-07-09; resolved via the smallest acceptable fix (whitespace-to-`_` normalization added as a new first step, above) rather than any broader rule change — every other confirmed §12 rule (character whitelist, Title_Case, truncation, `Category.UNKNOWN` treatment) is unchanged. Per `Governance/FROZEN_MODULE_CHANGE_POLICY.md` §5, this is scoped as a `PATCH`-level fix (stays entirely within Module 05's existing, not-yet-released `MODULE_CONTRACT.md` — `suggested_name`'s guarantee, "a non-empty, sanitized filename string," is unaffected in shape, only in the specific characters produced for previously-whitespace-containing input).

## 13. Within-batch collision resolution (scope narrowed from the original pointer doc — see §9)

**Confirmed scope:** only collisions *within the current batch* are detected and resolved by Module 05 — never against the real destination filesystem (§9). Two (or more) records processed in the same run whose computed `(suggested_name, suggested_destination)` pair is identical after sanitization get `_2`, `_3`, etc. appended before the extension, in the same deterministic batch-processing order established for the rest of this design (§7) — never overwriting, matching `Naming Rules.md`'s stated principle exactly, just narrowed in scope to what Module 05 can actually and honestly observe.

## 14. Destination resolution and override precedence

**Category → folder mapping** per `Rules/Folder Rules.md`'s table, unconditionally available to Module 05 (no pipeline-ordering problem here, unlike `tier` — category has existed since Module 02).

**Override precedence (confirmed):** Module 04's `duplicate_of`/`version_rank` signals — both already populated by the time Module 05 runs — take precedence over the normal category mapping, regardless of category, mirroring Module 04's own "exact-duplicate detection runs regardless of category" precedent:
- `duplicate_of is not None` (an exact duplicate) → `~ARCHIVE~/Duplicates/`, never the normal destination.
- `version_rank == "superseded"` → `~ARCHIVE~/Old Versions/`, never the normal destination.
- Neither applies → the normal category mapping (or `Unknown/`, unconditionally, for `Category.UNKNOWN`).

**Confirmed (§29 item 10):** naming runs normally regardless of the destination override — a duplicate/superseded file benefits from a readable name in its archive location exactly as much as any other filed file. An override never short-circuits naming.

`duplicate_signals.fuzzy_duplicate` (a near-duplicate *signal*, not a certain fact) is deliberately **not** a destination override — only Module 06's confidence deduction/hard floor reads it; it never changes where Module 05 suggests a file go, consistent with Module 04's own "a near-duplicate is a signal for review, not a routing fact" distinction (`Module 04 Design.md` §8).

## 15. Metadata usage

Module 05 reads, but never writes:
- `original_name`, `modified_at` (Module 01) — `original_name` for `Category.UNKNOWN`'s naming and as the ultimate tier-4 date fallback source; `modified_at` as the tier-4 date fallback for Archive/Video (§10, §29 items 5/7).
- `category` (Module 02) — to select the naming template and destination mapping.
- `extracted_metadata` (Module 03) — the primary source for every template field, per category (§10, §11).
- `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals` (Module 04) — for destination-override precedence (§14). Only `duplicate_of` and `version_rank` are load-bearing for routing; `duplicate_signals.fuzzy_duplicate`/`version_conflict` are read-only context, never override triggers.

## 16. Confidence considerations

Module 05 computes no score and assigns no tier — unconditionally Module 06's job, the same relationship every earlier module has to `Rules/Confidence Rules.md`. What Module 05 must produce is the raw, honest signal one existing deduction already depends on:
- `−10` per fallback used, "Naming template had to fall back to a placeholder value" → sourced from `naming_signals` (§5, §11, confirmed §29 item 3).

## 17. AI vs. deterministic responsibilities (confirmed: fully deterministic, §29 item 11)

**Confirmed: Module 05 has no provider, no live-Claude-judgment step, and no Engine/Provider split — the same conclusion Module 04's design reached for itself (§14 of `Module 04 Design.md`), for structurally the same reason, and now independently reconfirmed for Module 05 through its own explicit decision review.**

Every decision Module 05 makes — which template applies, filling it from already-extracted fields, string sanitization, within-batch collision suffixing, category-to-folder lookup, override precedence — is a computation over already-structured data (a category label, a dict of already-extracted string/number values, Module 04's already-computed signals). None of it requires *reading and understanding a document's content* the way classification or metadata extraction does; Module 05 never opens a file, never looks at an image, never reads text. This is a stronger case for "no provider needed" than Module 04's own, since Module 04 at least reads raw file bytes for hashing — Module 05 touches no file content at all, only already-structured `FileRecord` fields.

**This finding explicitly supersedes the original pre-build brief's framing, rather than silently discarding it.** The *original* brief (`Pre-build context.md` §9's tools table) anticipated "Claude + template rules per category" and "Claude proposes, human sets the rules initially — human owns taste," which read as anticipating a judgment role for Module 05 the way Module 02/03 have one. This design worked through that tension explicitly — the same reconciliation Module 04's design performed for itself (§14 of `Module 04 Design.md`) — rather than assuming precedent. The resolution is further reinforced, not just asserted: every specific "maybe we need judgment here" case surfaced during this design's own review (Invoice's `{DocSubtype}`, §29 item 4; Resume's `{VersionOrDate}` priority, §29 item 9; Archive/Video's missing date fields, §29 items 5/7; Audio's broken fallback, §29 item 8) turned out to have a satisfying deterministic rule once examined, leaving no remaining case for a provider to fill. Confirmed §29 item 11.

## 18. Logging

**Proposed action-log value: `suggest_naming_and_destination`**, following the established verb-naming convention (`discover`/`classify`/`extract_metadata`/`detect_duplicates_and_versions`). Per-file `details` (proposed — the log schema itself is finalized at implementation time, per `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`'s own update process, not by this design): `suggested_name`, `suggested_destination`, `fields_used` (which real fields fed the template), `fields_fell_back` (which placeholders used a fallback value — mirrors `naming_signals`' content, §29 item 3, and mirrors `extract_metadata`'s `fields_missing`/`redacted_fields` shape), `collision_suffix_applied` (bool, and which suffix if so), `override_applied` (`"exact_duplicate"` | `"superseded_version"` | `null`), `processing_time_ms`.

Following `ENGINEERING_STANDARD.md` §10's explicit rule (already violated twice — Module 02's `classify`, Module 03's `extract_metadata` — and correctly avoided a third time by Module 04's own implementation-time schema update): `Build-out/08 Logging & Reporting/Metadata & Log Schema.md` must be updated with this new action type in the *same* release cycle Module 05 ships, not left for a later audit to catch. Noted here as a hard requirement for the implementation/release stages, not applied by this design document itself.

## 19. Security considerations

- **No new code-execution surface.** Module 05 never reads file bytes or content at all (§17) — it only manipulates already-extracted string/number fields and builds path strings. This is a narrower attack surface than every earlier module, including Module 04 (which at least reads raw bytes for hashing).
- **No filesystem writes, no filesystem reads of the destination library** (§9) — Module 05 cannot be tricked by a malicious destination-folder state, because it never looks at one.
- **Path-injection consideration (new, not present in any earlier module's design):** since Module 05 builds a folder-path *string* from category/override logic and a filename *string* from extracted, provider-derived metadata, a provider-influenced field (e.g. a Document's `best_guess_title`, ultimately Claude-derived) must never be able to introduce path-traversal characters (`../`, absolute-path prefixes, embedded separators) into `suggested_name` or `suggested_destination`. `suggested_destination` itself is never provider-influenced (it's built entirely from `category`/Module 04's overrides, both deterministic by the time Module 05 reads them) — the risk is scoped specifically to `suggested_name`. Sanitization (§12)'s confirmed whitelist-only character filtering structurally excludes path separators and traversal sequences by construction, not merely handles spaces/special characters for readability — this is a security requirement, not just a formatting one, and should still be tested adversarially (a deliberately malicious `best_guess_title` containing `../../etc/passwd`-style content) the same way Module 03's redaction rule was, to verify the confirmed rule holds in implementation, not just on paper.
- **Bounded blast radius even if sanitization has a gap:** because Module 05 never executes a filesystem write itself, even a maximally adversarial `suggested_name` can only ever become a problem at Module 07's execution time — Module 07's own design will need its own independent, structural validation at the point it actually turns a suggestion into a real filesystem write (never trusting Module 05's sanitization alone, the same "trust boundary enforced independent of upstream behavior" principle `Governance/ENGINEERING_STANDARD.md` §20 already requires).

## 20. Performance considerations

- No new O(N×M) concern beyond the one every module since Module 02 already discloses (`save_file_record()`'s full-store read-modify-write per file, `ARCHITECTURE_DECISIONS.md` #11) — Module 05's own per-file work (template fill, string sanitization, a within-batch dict lookup for collision detection) is O(1) per file relative to batch size, not a scan of accumulated history the way Module 04's index lookups are.
- No new measured performance number is claimed by this design document itself (design phase, no code yet) — a real measurement is required at implementation/release, per `ENGINEERING_STANDARD.md` §21.

## 21. Failure handling

Same two-layer discipline as every earlier module (`ENGINEERING_STANDARD.md` §13):
- **Engine-level (anticipated failures):** a category with no defined template (should not occur given `Rules/Naming Rules.md` and `Rules/Folder Rules.md` cover every `Category` member, but defensively handled) falls back to the `Unknown` treatment rather than raising; a malformed/unexpectedly-typed `extracted_metadata` value degrades that one field to its fallback rather than crashing the record's entire naming attempt.
- **Batch-orchestration-level (unanticipated failures):** a single record's genuinely unexpected exception is caught by the batch function's own outer safety net, logged as an `error` action, and the batch continues.

No failure mode in Module 05 ever produces a fabricated field value or a silently-blank filename — an honest, disclosed fallback is always preferred to a guess (`ARCHITECTURE_DECISIONS.md` #7/#19).

## 22. Test strategy

Named here as a commitment this design makes (`ENGINEERING_STANDARD.md` §2's requirement) — not built during this design phase:

- Template-filling correctness for every category, using the confirmed real field mappings (§10, §29 items 4, 5, 7, 8, 9) — including the fallback path for every required and optional field.
- Sanitization boundary cases per §12's confirmed rules: the ~80-character longest-field-truncation boundary, whitelist character filtering, naive `Title_Case` (including the accepted acronym-rendering cosmetic cost), and whitespace-to-`_` normalization (post-freeze correction #1) — multiple consecutive spaces, tabs, mixed whitespace, leading/trailing whitespace, and interaction with pre-existing underscores (no doubling).
- Within-batch collision resolution: two, and three-or-more, records producing an identical `(name, destination)` pair in one batch.
- Destination override precedence: exact-duplicate overrides category mapping regardless of category; superseded-version overrides category mapping regardless of category; neither applies → normal mapping; `Category.UNKNOWN` always routes to `Unknown/` regardless of any other signal.
- `Category.UNKNOWN` end-to-end: confirms Module 05 (unlike Module 03) actually processes these records, with `original_name`-only naming and no `extracted_metadata` dependency.
- A Module Contract immutability test for the currently-processed record (all non-owned fields byte-identical before/after), matching every earlier module's own such test.
- Adversarial sanitization test: a deliberately path-traversal-laden extracted-metadata value never survives into `suggested_name`/`suggested_destination` (§19).
- Action-log shape for `suggest_naming_and_destination`, once §18's proposed detail shape is confirmed at implementation time.
- Deterministic batch-processing order (confirmed, §29 item 12) — re-running an identical batch must assign the same collision suffixes every time.

Integration Test Plan and UAT Plan are separate, later-lifecycle-stage artifacts (`ENGINEERING_STANDARD.md` §6.2/§6.3) — not written as part of this design document.

## 23. Integration with Modules 01–04

Reads (never writes): `original_name`, `modified_at` (Module 01); `category` (Module 02); `extracted_metadata` (Module 03); `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals` (Module 04). Every field read is already covered by an existing, frozen `MODULE_CONTRACT.md` guarantee — re-verified directly against all four contracts during this design's research phase (`Release/Module01–04/MODULE_CONTRACT.md`), not assumed from memory. No upstream module's contract, design document, or implementation is modified by this design or the module it describes. Consistent with `Governance/ARCHITECTURE_DECISIONS.md` #16 ("Frozen module policy"), nothing in Modules 01–04 is touched unless a genuine defect requiring the Frozen Module Change Policy is found — none was, during this design's research (§10's findings are gaps in `Rules/Naming Rules.md`, a living business-rule document explicitly marked "a draft to react to," not defects in any frozen module).

## 24. Dependencies for Modules 06–08

- **Module 06 (Confidence & Review)** reads `naming_signals` (confirmed, §29 item 3) to apply `Rules/Confidence Rules.md`'s existing `-10`-per-fallback deduction — the exact data this design exists to finally make available, the same relationship Module 04's `duplicate_signals` has to its own deductions.
- **Module 07 (Preview, Approval & Execution)** reads `suggested_name`/`suggested_destination` together with `tier` (Module 06's output) to decide both *what* to rename/move a file to and *whether* to actually execute that move at all (§8's confirmed resolution) — and performs the authoritative, real-filesystem collision check Module 05 explicitly does not attempt (§9).
- **Module 08 (Logging & Reporting)** reads Module 05's `suggest_naming_and_destination` action-log entries to build report rows (the "New Name"/"Destination" columns already sketched in `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`'s Daily Summary example).

## 25. Folder structure changes

- No change to `Build-out/`, `src/`, or `Database/` top-level structure. `src/pipeline/naming.py` is already scaffolded (stub-only) and named in `src/README.md`'s layout.
- No new `Database/` substructure — Module 05 needs no index of its own (§4).
- A new `src/models/naming.py` will be added, mirroring `src/models/duplicate.py`'s precedent, to define the confirmed `naming_signals` typed structure (§29 item 3). `FileRecord` itself (`src/models/file_record.py`) gains three new Module 05-owned fields: `suggested_name` (str), `suggested_destination` (str), `naming_signals` (the new typed structure) — the same pattern by which Module 04's own new fields were added directly to `FileRecord` at its release.

## 26. Known edge cases

- **A record with `category is None`** (Module 01 never had readable bytes) never reaches Module 05's real processing — filtered at the `status == "discovered"` gate the same way every judgment-dependent module already filters it (§3).
- **A record with `category == Category.UNKNOWN`** *does* reach Module 05 (§3) — the one category where Module 05's naming depends only on Module 01's `original_name`, never on `extracted_metadata` (which will be an empty `{}` for these records, since Module 03 never attempts extraction on `Unknown`).
- **A record that is simultaneously an exact duplicate and part of a version chain** — cannot occur per Module 04's own design (§7 step 1 of `Module 04 Design.md`: an exact-duplicate match short-circuits and skips version-chain checking entirely for that record) — so Module 05 never needs to arbitrate between the two overrides for the same record.
- **A record whose sanitized, template-filled name would exceed the ~80-character cap even before any collision suffix is added** — the confirmed longest-field-truncation rule (§12) applies first, leaving room for a possible later collision suffix, so a truncated name doesn't itself immediately collide with another truncated name from a different record.
- **A `Category.ARCHIVE` or `Category.VIDEO` record with no usable date field at all** — falls back to `modified_at` (Module 01, tier-4), the same "flagged, not authoritative" fallback discipline Module 03 already established for its own timestamp hierarchy (confirmed, §29 items 5, 7). `Category.AUDIO`'s own fallback (§29 item 8) uses `recording_date` before ever reaching `modified_at`, and drops to `{TrackTitle}` alone rather than a date-based fallback if `recording_date` is absent.

## 27. Future extensibility

- A future version could add a live-judgment provider if a genuine future need arises that requires content understanding at naming time (e.g. arbitrating a naming ambiguity no fixed rule can resolve well) — not built speculatively here, and not currently anticipated given §17's confirmed finding that no such need exists in v1 (§29 item 11).
- Per-entity subfolders for Resume/Contract (flagged as an open question in `Rules/Naming Rules.md` itself, already answered "flat for v1" — not reopened by this design).
- `Documents/` subfolder splits (`Rules/Folder Rules.md`'s own "future subfolders, not built in v1" list) — not reopened by this design; Module 05's category → folder mapping stays flat, matching the currently-frozen rules document.
- A real destination-library-root configuration (§9) will need to be introduced by whichever module first needs to resolve `suggested_destination` to an absolute path — almost certainly Module 07, not Module 05. Flagged here as a forward-compatibility note for that module's own design, not something this design pre-builds.

## 28. Explicit ownership boundaries

| | Module 05 owns | Module 05 must never do | Belongs to |
|---|---|---|---|
| Naming | `suggested_name`, fallback signal | Decide the final, actually-applied filename (a collision against the *real* destination could still change it) | Module 07 (execution) |
| Destination | `suggested_destination` (relative path) | Resolve to an absolute path, create a folder, decide whether to actually move the file | Module 07 (execution) |
| Filesystem | Nothing — reads only already-structured `FileRecord` fields | Read or write anything on disk | Module 07 |
| Confidence | Nothing (supplies raw fallback signal only) | Compute a score or tier | Module 06 |
| Database | Nothing new | Modify `FileIndex/`/`History/` (Module 04's) or `Metadata/`'s Module 01–04-owned fields | N/A — read-only there |
| Reporting | Nothing (supplies log entries only) | Generate the Daily/Weekly Summary itself | Module 08 |

---

## 29. Resolved architectural decisions (2026-07-09)

Every item below was open at this document's first draft, presented to the project owner as a decision table (alternatives, comparison against existing architecture/contracts/governance, and a recommendation for each), and approved exactly as recommended on 2026-07-09. None were resolved unilaterally by the designer — per `ENGINEERING_STANDARD.md` §2/§3, each is a business-rule or architectural judgment call reserved for the project owner, and each is recorded here for the same "never rewrite history" reason every other review/audit in this project appends rather than silently overwrites its findings.

1. **`tier` dropped from `resolve_destination()`'s signature; Module 07 is the sole enforcer of the `review_required` "don't move" rule.** Resolved — see §8. Rationale: the alternative of reordering the pipeline creates a real dependency cycle (Module 06 needs Module 05's `naming_signals`, so Module 06 cannot run before Module 05), and a second Module 05 invocation or a vestigial unused parameter both introduce patterns inconsistent with the rest of this pipeline.
2. **Module 05 has zero filesystem-read access to the destination library; collision detection is scoped to within-batch only.** Resolved — see §9. Rationale: a live destination-directory scan at suggestion time cannot avoid a TOCTOU staleness problem before Module 07's later execution, so it would duplicate work rather than remove it, and would give Module 05 a filesystem role no other "suggestion" stage in this pipeline has.
3. **A new persisted `naming_signals` field is added to `FileRecord`.** Resolved — see §5, §11, §16, §18, §24, §25. Rationale: unlike Module 02/03's fallback deductions, Module 06's naming-fallback deduction has no free recomputation path without re-running Module 05's own template logic; a first-class field matches the existing `classification_signals`/`duplicate_signals` precedent and avoids making the action log a second, off-pattern inter-module contract channel.
4. **Invoice's `{DocSubtype}` placeholder is dropped from the template; revised to `{Vendor}_{InvoiceNumber}_{Date}`, falling back to `{Vendor}_{Date}` when `invoice_number` is absent.** Resolved — see §10. Rationale: inventing a new Module 03 taxonomy field via the Frozen Module Change Policy for a naming convenience, not a genuine defect, would set a bad precedent and cost a full Module 03 re-audit/re-release for no proportionate benefit.
5. **Archive's `{Date}` falls back to `modified_at` (Module 01, tier-4).** Resolved — see §10, §11. Rationale: free, already-available data; dropping the placeholder entirely loses information and increases within-batch collision risk for no benefit.
6. **Sanitization rules are fully specified: whitelist character filtering, naive Title_Case with no exceptions list, longest-field truncation at the ~80-character boundary, and `Category.UNKNOWN` sanitized through the identical pass as every other category.** Resolved — see §12. Rationale: a whitelist is a closed, structurally enforced boundary consistent with this project's existing "closed taxonomy, not denylist" principle and directly closes §19's path-injection concern; the other sub-decisions each favored the simplest option that doesn't violate an existing project principle (never fabricate, never silently blank).
7. **Video's `{Date}` (mapped to the always-`null`-in-v1 `content_date`) falls back to `modified_at`, the same rule as Archive.** Resolved — see §10, §11. Rationale: free, already anticipated as the intended direction by `Release/Module03/KNOWN_LIMITATIONS.md`.
8. **Audio's fallback template is revised to `{TrackTitle}_{RecordingDate}`, falling back further to `{TrackTitle}` alone when `recording_date` is also absent.** Resolved — see §10. Rationale: the previously documented fallback referenced a field (`description`) that does not exist anywhere in Audio's taxonomy; the revised chain uses only real, already-available fields.
9. **Resume's `{VersionOrDate}` composite resolves as `version_indicator` first, falling back to `last_modified_date`, falling back to `Unknown` when neither is present.** Resolved — see §10, §11. Rationale: a resume's own stated version convention is a more specific, more informative signal than a raw date when both are available; this is the smallest change that resolves the ambiguity without expanding the template's documented single-slot shape.
10. **Naming runs normally and unconditionally, even for a record whose destination is overridden by an exact-duplicate or superseded-version routing.** Resolved — see §14. Rationale: a duplicate/superseded file that is archived, never deleted (this project's core non-negotiable), benefits from a readable, real name in its archive location exactly as much as any other filed file; short-circuiting to a generic name costs nothing to avoid and only loses information.
11. **Module 05 is fully deterministic — no provider, no Engine/Provider split.** Resolved — see §6, §17, §27. Rationale: no step in Module 05 ever reads file content, only already-structured `FileRecord` fields — a stronger case than Module 04's own no-provider conclusion; further reinforced by the fact that every apparent judgment gap raised during this same review (items 4, 5, 7, 8, 9) turned out to have a satisfying deterministic rule, leaving nothing left for a provider to do. This explicitly supersedes, rather than silently discards, the original pre-build brief's "Claude proposes" framing.
12. **Module 05 processes records in the same deterministic batch order Module 04 established (`discovered_at` ascending, `file_id` lexicographic tie-break).** Resolved — see §7. Rationale: the only real reason this matters — within-batch collision-suffix reproducibility across re-runs of an identical batch — is fully served by reusing an already-implemented, already-tested ordering rather than inventing a new one.

**Follow-up action required, out of scope for this document:** `Rules/Naming Rules.md`'s Invoice, Resume, Archive, Video, and Audio templates should be updated at implementation time to match items 4, 5, 7, 8, and 9 above. `Rules/` is a living business-rules document maintained outside `Build-out/`'s authority (per `CLAUDE.md`) and is not edited by this design.

No items remain open. **Design Freeze occurred on 2026-07-09**, following an Independent Design Review that found and resolved one Medium finding (`naming_signals`'s contract precision) before approving this document as fully resolved — preserved here as the historical record of this document's pre-freeze state, not rewritten to look as though every decision was obvious from the start. Implementation, three Independent Implementation Audit passes, Integration Testing, a full UAT (including the stop-and-restart cycle documented in §12's post-freeze correction #1), and an Independent Release Audit (`Release/Module05/RELEASE_AUDIT.md`) have all since taken place against this frozen document.
