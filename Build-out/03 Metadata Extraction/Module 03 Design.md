# Module 03 (Metadata Extraction) — Design & Architecture

**Status: DRAFT v1 — pending formal review and freeze. Design only. No implementation code exists or has been written for this module.**

This document is the complete pre-implementation design for Module 03, produced with the same engineering process used for Modules 01 and 02 (design → formal review → refinement → explicit approval → freeze → only then implement). It supersedes the short pointer note previously at `Build-out/03 Metadata Extraction/03 Metadata Extraction.md` for architectural purposes — that file's field-by-category content is carried forward and formalized below (§7), with a recommendation (§10) to relocate it into `Rules/`, matching the convention already established for classification, naming, folder, and confidence rules. **Module 01 and Module 02 are frozen and are not modified by this document** — this design only adds a new consumer of their already-frozen contracts.

---

## 1. Purpose

Turn each file Module 02 classified into a small set of structured, category-specific fields — the concrete facts (vendor, dates, amounts, names, descriptions) that Module 05 (Naming & Destination) needs to build a filename, and that Module 06 (Confidence & Review) needs to score completeness against. Module 03 does not classify (that's decided, final, and trusted as input), does not compare files to each other, does not name or move anything, and does not decide how confident to be about what it extracted — it reports what it found (and, implicitly, what it didn't) and leaves the judgment of what that's worth to Module 06.

## 2. Responsibilities

Following the layering precedent established by Module 02 (`classify_batch()` → `ClassificationEngine` → `ClassificationProvider`), Module 03 is three layers, batch-level down to raw extraction:

- **Module 03 itself** — batch orchestration: filtering, persistence, logging, per-file failure containment. Mirrors `classify_batch()`'s shape exactly.
- **`MetadataExtractionEngine`** (new) — per-file decision-making: which field set applies (by `category`), whether a field is obtainable deterministically or needs a provider call, which mode to request (text/vision), validation of whatever the provider returns, and what to do when a field can't be found.
- **`MetadataExtractionProvider`** (new) — performs structured extraction only, nothing else. An abstract contract with one concrete v1 implementation, `ClaudeLiveExtractor`, following the exact pattern `ClaudeLiveClassifier` established.

**Belongs to Module 03 (across all three layers):**
- Look up the required/optional field set for a record's `category` (§7).
- Skip records whose `category` is `Category.UNKNOWN` or `None`, or whose `status != "discovered"` — never attempt extraction on a file that was never meaningfully classified (§11 explains why this is not an oversight).
- Run deterministic field extraction where a field never needs judgment: image/screenshot capture date (`core/exif.py`), archive contents listing (`core/archive.py`, new), audio embedded tags (`core/media.py`, new), best-effort filename parsing for Application installers.
- Extract text (re-running `core/pdf.py`/`core/text.py` — see §21 for why this is a deliberate re-extraction, not reused state from Module 02) or render a vision image for scanned/no-text PDFs, and route judgment-dependent fields to `MetadataExtractionEngine` for a provider call when a deterministic answer isn't possible.
- Assign an `extracted_metadata` dict to every record it processes, shaped per §7 — present (possibly with some or all values `null`) for every record it attempts, absent only for records it correctly skipped.
- Apply the "never fabricate" rule (§7, §12): a field that can't be found is `null`, never a guess, never an empty string standing in for "unknown."
- Enforce the Bank Statement privacy rule (§18) as an Engine-level validation step, not merely a prompt instruction.
- Persist `extracted_metadata` via the existing, unmodified `storage/database.py`.
- Append an `extract_metadata` action-log entry per file processed (§13).
- Never call a specific AI provider directly from Module 03's own code — only through `MetadataExtractionEngine`, which in turn only calls the abstract `MetadataExtractionProvider` (§9, §23).

**MUST NOT be implemented until later modules (feature creep to explicitly avoid):**
- **Classification** — deciding or revising `category`. Module 02, already frozen. Module 03 *reads* `category`; it never second-guesses it, even if extraction strongly suggests a different category (see §19 edge case).
- **Duplicate/Version Detection** — comparing `content_hash`/perceptual hash, version-chain logic. Module 04.
- **Naming** — generating `suggested_name` from `extracted_metadata`. Module 05. Module 03 produces the raw fields; it never assembles a filename string.
- **Destination Selection** — generating `suggested_destination`. Module 05.
- **Confidence scoring** — computing `confidence_score`/`confidence_breakdown`/`tier`, including deciding *which* missing fields matter and by how much. Module 06. Module 03 supplies the raw material (§12); it never scores itself.
- **Execution** — moving, renaming, or staging any file; approvals. Module 07.
- **Reporting** — writing to `Runtime/Reports/*`. Module 08 (Module 03 only writes to `Runtime/Logs/action_log.jsonl`, same as Modules 01–02).

## 3. Inputs

- One `FileRecord` per file from Module 02, restricted to `status == "discovered"` **and** `category not in (None, Category.UNKNOWN)` (§11).
- The physical file at `current_path`.
- The field taxonomy (§7) — implemented directly in code per-category, same convention established for `Rules/Classification Rules.md`/`Rules/Ignore Rules.md`. Recommended to live in `Rules/Metadata Rules.md` (§10) rather than only in this design document.
- Which `MetadataExtractionProvider` is active — a simple default in v1 (`ClaudeLiveExtractor`), same convention as Module 02's `DEFAULT_PROVIDER` (§9).

## 4. Outputs

- `extracted_metadata` — a `dict`, shaped per §7, set for every processed record (never omitted for an attempted record, even if every value inside is `null`).
- One `extract_metadata` action-log entry per file processed (§13).
- `List[FileRecord]`, same records, enriched — returned for Module 04 to consume next, mirroring `classify_batch()`'s return-list pattern.

## 5. Module Contract

*(Same template as `Release/Module01/MODULE_CONTRACT.md` and `Release/Module02/MODULE_CONTRACT.md`. The internal Module 03 → Engine → Provider layering is an implementation detail — it does not change this contract's INPUT/OUTPUT surface with the rest of the pipeline.)*

**INPUT — Receives:** `List[FileRecord]` from Module 02, filtered to `status == "discovered"` and `category` a real, non-`Unknown` `Category` member.

**OUTPUT — Produces:** `List[FileRecord]` (same records, enriched).

**Guarantees:**
- `extracted_metadata` is always a `dict` (never `None`, never a bare string) on every record Module 03 attempts — present with category-appropriate keys, `null`-valued where a field couldn't be found.
- Every key in `extracted_metadata` for a given record is one of that category's defined field names (§7) — Module 03 never emits an ad hoc key not in the taxonomy.
- A record Module 03 does not attempt (`status != "discovered"`, or `category` is `None`/`Unknown`) is left with `extracted_metadata` at its `FileRecord` default (`{}`) — untouched, not an empty-but-attempted dict. This mirrors Module 02's `None`-vs-`Unknown` distinction: an empty dict here is ambiguous between "attempted, found nothing" and "never attempted," so Module 03 must be strict about only ever producing a non-empty-shaped dict (keys present, values possibly `null`) when it actually tried, and leaving the field completely untouched (`{}`, the dataclass default) otherwise. A future reader can distinguish the two by checking `category` first — `Unknown`/`None` explains an empty `extracted_metadata` without ambiguity.

**DOES NOT MODIFY:**
- **Classification (Module 02)** — `category`, `classification_signals` — read-only for Module 03.
- **Naming & Destination (Module 05)** — `suggested_name`, `suggested_destination`.
- **Duplicate & Version Detection (Module 04)** — `duplicate_of`, `version_group_id`, `version_rank`.
- **Confidence & Review (Module 06)** — `confidence_score`, `confidence_breakdown`, `tier`.
- **Preview, Approval & Execution (Module 07)** — `processed_at`, `approved_by`, `approved_at`, `reversible`.
- **Logging & Reporting (Module 08)** — `Runtime/Reports/*`. Module 03 only ever appends to `Runtime/Logs/action_log.jsonl`.
- **Module 01's own fields** — `file_id`, `source_id`, `original_name`, `original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `batch_id` — all read, never rewritten.

**Records with `category` `None` or `Unknown`, or `status == "unreadable"`,** are left with `extracted_metadata` at its default `{}` — Module 03 never touches them and they never receive an `extract_metadata` log entry.

## 6. Internal Workflow

Three layers, matching Module 02's shape:

```
Module 03 (batch orchestration)
      │  per FileRecord with status == "discovered" and category not in (None, Unknown)
      ▼
MetadataExtractionEngine (per-file decision-making)
      │  decides: which fields apply? deterministic? AI-assisted? missing?
      ▼
MetadataExtractionProvider (raw structured-extraction call only)
```

1. **Module 03:** filters to `status == "discovered"` and `category` a real, non-`Unknown` member; passes every other record through untouched.
2. **Module 03** hands each remaining record to `MetadataExtractionEngine.extract_file(record)`.
3. **Engine — field lookup:** looks up the required/optional field set for `record.category` (§7).
4. **Engine — deterministic fields:** for each field markable as deterministic for this category (§9), computes it directly (EXIF capture date, archive listing, embedded audio tags, filename-parsed app name/version/platform) — no provider call for these fields regardless of category.
5. **Engine — judgment fields (text-bearing categories):** re-extracts text (`core/pdf.py`/`core/text.py`, same libraries Module 02 uses, run independently — §21) and, if text is available, builds a `MetadataExtractionRequest` (mode: `"text"`) naming exactly the judgment fields still needed → calls the configured `MetadataExtractionProvider.extract()` → receives a `ProviderResponse` → **Engine validates it** (§12) → merges validated fields into `extracted_metadata`.
   - No extractable text (scanned PDF) → Engine renders the first page as an image (`core/pdf.py`'s existing `render_page_as_image()`) → builds a request in `"vision"` mode → same provider call and validation.
   - Extraction fails entirely (locked/encrypted) → unreachable in practice, since a locked file was already routed to `Category.UNKNOWN` by Module 02 and is filtered out at step 1 — documented here for completeness, not a live code path.
6. **Engine — judgment fields (image-family categories: Image, Screenshot):** builds a vision-mode request directly from the file itself (no text extraction attempted) for the description/context field; capture date, when present, comes from the deterministic EXIF pass in step 4, not the provider.
7. **Engine — Bank Statement `account_last4` digit-count check (§18's exact rule, not a heuristic pattern):** before merging a candidate `account_last4` value for a Bank Statement record, the Engine strips non-digit characters and checks length: more than 4 digits → the field is redacted to `null` and its name (never its value) is logged under `details.redacted_fields`; 4 digits or fewer (including empty) → passes through unchanged. This is the one field in the entire taxonomy with this extra check — see §18 for why it is not generalized to every field of every category.
8. **Engine — missing field handling:** any required or optional field not obtained by either path (deterministic or provider) is left `null` in `extracted_metadata` — never a placeholder string, never omitted from the dict's keys.
9. **Engine — provider unavailable / invalid response:** Engine applies the fallback strategy (§12) — never Module 03, never the provider itself. Unlike Module 02, a provider failure here does not force any field to a specific sentinel category; it simply means every judgment-dependent field for that call stays `null`, exactly as if the field were legitimately not found. There is no `extracted_metadata` equivalent of `Category.UNKNOWN` — a dict with all-`null` values *is* the honest fallback state.
10. **Module 03:** persists the record (`save_file_record()`, unchanged from Modules 01–02) and appends the `extract_metadata` action-log entry (§13).
11. **Module 03:** continues to the next record; any single-record failure at any layer is caught, logged, and never aborts the batch (same resilience pattern as `scan_source()`/`classify_batch()`).

## 7. Metadata Taxonomy

Formalizes and extends `Build-out/03 Metadata Extraction/03 Metadata Extraction.md`'s original field lists. **This section fully resolves the first independent review's F1 finding:** every rule below is stated explicitly, not inferred from the naming templates the way the first draft of this table was built. The required/optional assignments are proposed by this design and, per that review, are a business-rule judgment call, not an architectural one — **recommended to live in `Rules/Metadata Rules.md` (§10) once confirmed**, not treated as silently settled by this document alone.

### General rules (apply to every category unless a category's row below says otherwise)

- **Prohibited metadata (universal rule, applies identically to all twelve categories):** any field name not explicitly listed as required or optional for a record's `category` is prohibited. The Engine drops it if a provider returns it anyway (§12) — no prompt ever requests it in the first place. This is a closed taxonomy: the required+optional field list *is* the privacy boundary for every category, not only the ones with a named example in the table below. Where a category's row names a specific prohibited example, that's for a human reader's benefit (prompt author, future auditor, this design's own reviewer) — its absence elsewhere never means "anything goes," it means "only what's named as required/optional, full stop."
- **Extraction priority (universal rule):** required fields are always requested. Optional fields are requested in the same combined call (§8) but are the first (and only) fields ever dropped if a future provider implementation has a hard per-call field limit — none exists in v1; this rule is defined now so the answer isn't improvised under pressure later. Required fields are never sacrificed to make room for optional ones, under any circumstance.
- **Minimum acceptable extraction:** at least one required field successfully found. A record where every required field is `null` is not an error — it is still persisted, still logged, and the batch still continues — but it is explicitly labeled `extraction_complete: false` in that record's `extract_metadata` action-log entry (§13), the weakest possible non-error outcome, distinct from a record where some or all required fields were found.
- **When extraction is considered incomplete:** a direct, mechanical definition, not a judgment call — `extraction_complete = all(record.extracted_metadata[f] is not None for f in required_fields[category])`. Any required field left `null` makes the whole record incomplete, regardless of how many optional fields were found.
- **When Module 03 stops trying — four independent stopping rules:**
  1. **Before starting at all:** `category` is `None`/`Unknown`, or `status != "discovered"` (§3/§11) — no attempt, no log entry.
  2. **After the deterministic pass, for categories with zero judgment fields** (Archive, Application — §9): stop immediately once the deterministic pass completes, whether or not every field was found — there is no provider to ask for anything else.
  3. **After exactly one provider call, for judgment fields:** no retry on failure or an invalid response (§12), matching Module 02's established no-retry precedent exactly. A field is never asked about a second time within the same run.
  4. **Per field, never cross-method:** if a field's designated deterministic source doesn't have it (e.g. EXIF has no capture date for a given image), Module 03 does not then ask the provider to guess it, even if a provider call is already happening for other fields on the same record. A field's source — deterministic or judgment — is fixed by §9's table; it is never a fallback chain within a single record.

### Per-category fields

| Category | Required | Optional | Category-specific prohibited examples (in addition to the universal rule above) |
|---|---|---|---|
| Invoice | `vendor`, `invoice_date` | `invoice_number`, `amount`, `currency`, `tax_type` | Full payment-card or bank-account numbers, even if visible in the source text. |
| Resume | `candidate_name` | `version_indicator`, `last_modified_date` | Phone number, email address, home address, date of birth, national ID/SSN — commonly present in real resumes, never extracted regardless of how prominently they appear in the source text. |
| Bank Statement | `bank_name`, `statement_period` | `account_last4` | Full account number, routing number, balance, transaction line items — restated here as the taxonomy's own binding rule, not only a prose aside; see §18 for the additional value-level check unique to this category. |
| Contract | `contract_type`, `counterparty`, `effective_date` | `term_length` | A signatory's personal details beyond the counterparty's own name (e.g. a signer's home address or personal phone number appearing in a signature block). |
| Document (generic) | `best_guess_title` | `document_date`, `description` | None beyond the universal rule — deliberately the most permissive category, but still closed to exactly these three keys. |
| Image / product photo | `description` | `variant`, `capture_date` | Any identifying detail visible *in* the photo (a face, a license plate, an address on a package label) is not a defined field and must never be promoted into one via `description`'s free text — `description` means "what kind of photo is this," never "transcribe everything visible." `capture_date` sourced per §9A's hierarchy (EXIF only in v1). |
| Screenshot | `context_description` | `capture_date` | Same rule as Image — `context_description` describes the kind of screen content (e.g. "login error dialog"), never a transcription of on-screen personal data (an inbox's message previews, a balance visible in a banking-app screenshot, etc.). `capture_date` expected `null` in the overwhelming majority of cases — screenshots typically carry no camera EXIF at all, the same fact Module 02's Screenshot-vs-Image heuristic already relies on (§19). |
| Application (installer) | `app_name` | `version`, `platform` | None beyond the universal rule. Deterministic only in v1 (§9) — filename-pattern parsing, no provider call. |
| Archive | `contents_summary` | — | Entry *contents* — only top-level entry names are ever read (§18). Deterministic only in v1 (§9). |
| Video | `description` | `duration`, `content_date` | None beyond the universal rule. `duration` and `content_date` are defined fields that are **unconditionally `null` in v1** — no tier-1/tier-3 source is implemented for Video yet (§9A, §16) — kept in the taxonomy now (rather than added later) so Module 05/06 can code against a stable contract as v1's extraction capability grows. `content_date` (renamed from an earlier draft's ambiguous `date`) is never filesystem-sourced — see §9A for why. |
| Audio | `track_title` | `artist`, `duration`, `recording_date` | None beyond the universal rule. `recording_date` restores a field the original pointer doc named ("capture/creation date") that an earlier draft of this table had dropped — sourced from embedded ID3-style tags when present (`core/media.py`, §16, pending dependency approval), `null` otherwise; never filesystem-sourced (§9A). |
| Unknown | *(none — category excluded entirely, §3/§11)* | | |

**"Never fabricate" rule, restated precisely:** a field is `null` when (a) no deterministic source produced a value, and (b) either no provider call was made for it, or the provider was asked and either didn't return it or returned something the Engine's validation rejected. A `null` is always a true statement about what was found, never a placeholder for "the provider guessed and we don't trust it" — the Engine's validation step exists specifically so a low-confidence guess never silently reaches `extracted_metadata` dressed up as a confident answer.

## 7A. How the Taxonomy Is Consumed (resolves F1's consumption question)

- **Module 05 (Naming & Destination)** reads `extracted_metadata`'s values directly to fill `Rules/Naming Rules.md`'s templates. Module 05 — never Module 03 — owns the decision of what to do when a naming-relevant field is `null` (its existing placeholder convention, `Unknown_Vendor` etc.). Module 05 can trust that a `null` required field is a genuine, honestly-reported miss, never an artifact of a provider running out of room mid-call (the extraction-priority rule above), and that every value it reads was already validated — and, where applicable, redaction-checked (§18) — before ever reaching `extracted_metadata`. Module 05 performs no privacy filtering of its own, by design, because Module 03's boundary already guarantees it never has to. Module 05 also owns resolving Resume's `{VersionOrDate}` compound naming slot from the two independent optional fields Module 03 reports (§7's Resume row), and owns reaching directly into `FileRecord.modified_at` as its own last-resort naming fallback when a content-authored date (`capture_date`/`content_date`/`recording_date`) is `null` (§9A) — Module 03 never pre-resolves either of these on Module 05's behalf.
- **Module 06 (Confidence & Review)** consumes the required/optional split as the direct input to `Rules/Confidence Rules.md`'s deduction formula (`−8`/missing required, `−2`/missing optional) — this taxonomy *is* the previously-missing definition that formula always assumed existed (§10). Module 06 inherits the `extraction_complete` concept implicitly: a record with `extraction_complete: false` will always have accumulated at least one `−8` deduction, so no new confidence rule is needed to represent it — it is a restatement of existing math, not an additional signal. Module 06 never needs to verify `extracted_metadata` is free of prohibited fields; it trusts Module 03's closed-taxonomy guarantee unconditionally, the same way Module 03 itself trusts Module 02's `category` without re-validating it (§21).
- **Module 07 (Preview, Approval & Execution)** has no direct field-level dependency on `extracted_metadata` (§22, unchanged) — but if a future version of Module 07 surfaces per-file metadata in an approval preview (plausible given its name, though not designed here), it inherits the same privacy guarantee passively: whatever it might display was never carrying prohibited content to begin with, because Module 03 never wrote any. This is a forward-looking constraint on Module 07's eventual design, not a capability Module 07 needs to build itself.

## 8. Extraction Strategy

Cheap-first, same discipline as Module 02's classification strategy (§7 of `Module 02 Design.md`): compute every deterministic field before considering a provider call at all, and only ask the provider for the specific fields that genuinely require judgment — never re-ask for a field the deterministic pass already filled. The `MetadataExtractionRequest` (§9) built for a text/vision call therefore names only the judgment-dependent fields still outstanding for that category, not the category's full field list — this keeps provider prompts minimal and keeps a future provider swap from needing to know which fields are deterministic in the first place (that knowledge stays entirely inside the Engine, matching Module 02's Engine/Provider trust-boundary precedent, §25 of `Module 02 Design.md`).

## 9. Deterministic vs. AI Responsibilities

| Field / responsibility | Deterministic | Judgment (via `MetadataExtractionEngine` → `MetadataExtractionProvider`) | Decided by |
|---|---|---|---|
| Image/Screenshot `capture_date` | ✅ (`core/exif.py`, reused from Module 02 — tier 2 of §9A's hierarchy) | | Engine |
| Archive `contents_summary` | ✅ (`core/archive.py`, new — stdlib `zipfile`, no new dependency) | | Engine |
| Audio `track_title`/`artist`/`duration`/`recording_date` (when embedded tags exist) | ✅ (`core/media.py`, new — `mutagen`, a new dependency, §16; `recording_date` is tier 1 of §9A's hierarchy) | | Engine |
| Application `app_name`/`version`/`platform` | ✅ (filename-pattern parsing) | | Engine |
| Video `description` | ✅ (filename-pattern parsing, best-effort — §19) | — (no provider call in v1; a genuinely ambiguous filename simply yields a low-information result, not a provider fallback) | Engine |
| Video `duration`/`content_date` | Unconditionally `null` in v1 — no tier-1/tier-3 source implemented (§9A, §16) | Never provider-sourced — not a judgment question | Engine (reports `null`, never guesses) |
| Invoice/Resume/Bank Statement/Contract/Document text fields | | ✅ | Provider (Engine validates) |
| Image/Screenshot `description`/`context_description` | | ✅ (vision) | Provider (Engine validates) |
| Bank Statement `account_last4` digit-count check | ✅ (Engine-level check, §18 — exact rule, not a pattern heuristic) | | Engine (never the provider — the provider is not trusted to self-censor) |
| Mode selection (text/vision/deterministic-only) | — | — | **Engine only** |
| Fallback on provider failure/invalid response | — | — | **Engine only** |

The Provider never decides which fields are deterministic, never decides mode, and never decides fallback — it only answers the specific field-extraction question it's asked, for the fields it's asked about, in the mode it's asked to answer in. Identical division of labor to Module 02's Engine/Provider split (§25 of `Module 02 Design.md`), applied to a different kind of question.

## 9A. Timestamp Source Hierarchy (resolves F4)

Any field representing "when was this content actually created" — as opposed to "when did this file arrive on this filesystem" — is sourced according to a single, explicit four-tier hierarchy, applied consistently across every category that has such a field (Image/Screenshot's `capture_date`, Video's `content_date`, Audio's `recording_date`):

1. **Embedded content metadata** — tags written by the device/software that created the file, describing the content's own history (e.g. an audio file's ID3 `TDRC`/`TYER` recording-date tag; a video container's creator-supplied creation-time tag, where distinct from tier 3's format-level header). Highest priority: closest to the ground truth of when the content was actually made.
2. **EXIF** — camera-specific metadata, applicable to Image/Screenshot only. Kept as its own tier rather than folded into tier 1 because EXIF already has its own well-established reader (`core/exif.py`, built for Module 02) and its own well-documented gap (screenshots systematically lack it, §7) distinct from tag-based embedded metadata on other media types.
3. **Container/format metadata** — timestamps written into a file format's own structural headers by whatever tool last touched the file (e.g. a QuickTime `mvhd` atom, an MP4 box-level timestamp), distinct from tier 1's content-authored tags. Ranked below tiers 1–2 because format-level headers are more easily reset or overwritten by transcoding/re-export tools without the underlying content having changed — a weaker signal of true content-creation time than a tag the original creating device wrote deliberately.
4. **Filesystem timestamps** (`FileRecord.created_at`/`modified_at`) — always available (Module 01 already populates them), but describe what happened to the *bytes on this filesystem* (download, copy, transfer), which is frequently and sometimes wildly unrelated to when the underlying content was actually created. Lowest priority for exactly this reason.

**Why this order is correct:** each tier down the list answers a progressively less specific question — tiers 1–2 answer "when was this content made," tier 3 answers "when did some tool last write this file's headers," and tier 4 answers "when did this file arrive here." A field semantically named `capture_date`/`content_date`/`recording_date` promises the first question's answer, not the fourth's.

**Why Module 03 never substitutes a lower tier's value into a higher tier's field:** doing so would violate §7's "never fabricate" rule in a subtle way — not by inventing a false value, but by mislabeling a true-but-different fact as something it isn't (a download timestamp presented as a capture date). This is why `content_date`/`recording_date`/`capture_date` are permitted to be `null` in `extracted_metadata` even when `FileRecord.modified_at` is trivially available — **Module 03 deliberately does not reach for the easiest available proxy.** If a naming template's date slot needs *some* date rather than none, resolving that gap is Module 05's job, reading `FileRecord.modified_at` directly itself as its own last-resort naming fallback (§7A) — not something Module 03 pre-resolves on Module 05's behalf.

**v1 implementation status, by tier:**
- **Tier 1** — implemented for Audio only (`core/media.py`/`mutagen`, §16, pending dependency approval); not implemented for Video (no library approved — §16, §27).
- **Tier 2** — implemented for Image/Screenshot (`core/exif.py`, reused unchanged from Module 02).
- **Tier 3** — not implemented for any category in v1 (would need a container-metadata reader, e.g. `pymediainfo` or `ffprobe` for video — a bigger dependency decision than this module warrants alone, §16/§27).
- **Tier 4** — never written into `extracted_metadata` by Module 03, for any category, per the rule above — available to Module 05 directly via `FileRecord`, always.

**Practical consequence, stated plainly:** Video's `content_date` is unconditionally `null` in v1 (no tier 1 or 3 source exists yet); Audio's `recording_date` is populated when tier-1 tags exist and `null` otherwise; Image/Screenshot's `capture_date` is populated when EXIF has it (routinely absent for screenshots, §7) and `null` otherwise. None of these ever fall back to tier 4 within Module 03 itself — this reframes what the first design draft presented ambiguously (Video "using" `FileRecord.modified_at`) into an explicit, disclosed limitation rather than a silent substitution.

## 10. Rules Interaction

**Recommendation (not yet applied — a filesystem/documentation change requiring explicit approval, same as any other change in this design phase): promote §7's taxonomy table into a new `Rules/Metadata Rules.md`,** retiring the field-list portion of `Build-out/03 Metadata Extraction/03 Metadata Extraction.md` in favor of a pointer, exactly the relationship `Build-out/02 Classification/02 Classification.md` now has to `Rules/Classification Rules.md`. Rationale: `CLAUDE.md`'s own working rule states business rules (classification, naming, folder routing, confidence scoring, ignore patterns) live in `Rules/`, not in `Build-out/`; the metadata field taxonomy is the same kind of living business rule (it will need tuning as real files are seen, exactly like `Rules/Naming Rules.md` already anticipates for its own templates) and is currently the one such rule set still living outside that convention. `Rules/Confidence Rules.md` already points at `Build-out/03 Metadata Extraction/03 Metadata Extraction.md` for its required-field definitions — that reference would be updated to point at `Rules/Metadata Rules.md` instead, if this recommendation is approved.

Until approved, this design document (§7) is the authoritative source for the taxonomy, in the same way `Module 02 Design.md` was authoritative for `Category`'s member list before `Rules/Classification Rules.md` and the enum both existed.

`Rules/Confidence Rules.md`'s deduction table is the reference for exactly how missing required/optional fields translate into score deductions — Module 03 supplies the raw `extracted_metadata` dict; it is Module 06's job, not Module 03's, to diff that dict against the taxonomy's required/optional lists and compute the deduction (§12). This keeps the "which fields are required" fact defined in exactly one place (the taxonomy) while keeping "what a missing field costs" defined in exactly one other place (`Confidence Rules.md`) — neither document needs to know the other's internals, only that the field *names* they both reference agree, which is what a taxonomy-drift test (§20) should guard.

## 11. Confidence Implications

**Module 03 does not compute `confidence_score`, `confidence_breakdown`, or `tier`, and does not itself compute or persist a "fields missing" list.** That remains fully owned by Module 06, per `Rules/Confidence Rules.md`'s explicit single-source-of-truth principle — identical discipline to Module 02's §9. Module 03's only obligation toward confidence is to emit an honest `extracted_metadata` dict; Module 06 diffs it against the taxonomy (§7/§10) to find gaps and apply deductions. Two things Module 03 must guarantee for Module 06 to be able to do this correctly:
- Every key that *should* be present for a category (per §7) is present in the dict, even when its value is `null` — a genuinely missing key (as opposed to a present-but-`null` key) would be indistinguishable from "Module 03 never ran" and should never happen for an attempted record.
- `Category.UNKNOWN`/`None` records are the one case where the dict is correctly *absent* (default `{}`) rather than key-complete-but-null — Module 06 already hard-floors Unknown to `review_required` regardless of metadata (`Rules/Confidence Rules.md`), so this asymmetry is safe and mirrors Module 02's own `None`-vs-`Unknown` precedent rather than inventing a new one.

**Why extraction (not classification) attempted at all on ambiguous/multi-document files:** `Rules/Confidence Rules.md` already hard-floors `ambiguous` and `multi_document_detected` signals to `review_required`/`approval_required`-or-worse regardless of extraction quality. Module 03 still attempts extraction on these records (rather than skipping them the way it skips `Unknown`) because a human reviewing a flagged file benefits from whatever fields *were* found, even if the review outcome was already decided by Module 02's signals — extraction effort is never wasted the way it would be on a genuinely unclassified `Unknown` file.

## 12. Error Handling

**General:** single-record failures at any layer never abort the batch — caught, logged, continue, identical pattern to Modules 01–02.

**Validation, every time:** every `ProviderResponse` is validated before any of its fields are trusted:
- Every key in the response must be one of the field names the request actually asked for (§8) — an extra, unrequested key is dropped, not merged in (the same "the Engine is the trust boundary, not the provider" principle Module 02 established for `category`).
- A value's type must roughly match what's expected for that field (e.g. `amount` should parse as a number; a value that doesn't is treated as not-found, not coerced or guessed).
- Bank Statement's `account_last4` field specifically (no other field, no other category) additionally passes the digit-count check (§7 note, §18) before being trusted.

**Failure modes recognized**, reusing Module 02's exact vocabulary and reasoning (`provider_unavailable`/`invalid_response`/`provider_exception`) via Module 03's own parallel exception types (§21 explains why these are a deliberate, structurally-similar-but-separate set, not an import from `classification.py`):
1. **v1 fallback behavior (uniform, matching Module 02):** no retry. Every judgment-dependent field for the affected call stays `null`. `fallback_used = True` and a specific `fallback_reason` are recorded in the action-log entry's `details` (§13) — not inside `extracted_metadata` itself, keeping the same content-vs-process separation Module 02 established for `ClassificationSignals` vs. the action log.
2. **Sanitized diagnostics (reusing Module 02's F3-established pattern, not reinventing it):** every fallback path populates an `error_detail` string via the same `_sanitize_error()`-style helper (length-bounded, exception type + message, never raw file content) — a direct, deliberate reuse of a pattern that was added to Module 02 after its own release audit found its absence to be a real operability gap. Module 03 adopts it from day one instead of waiting to rediscover the same gap.
3. **No secondary-provider fallback chain in v1** — identical reasoning to Module 02 §11: with exactly one provider implemented, there's nothing to fall back *to* except all-`null` fields.

**Deterministic-path failures** (a corrupted zip Module 01 let through, an image `PIL` can't open, a `.docx` that fails to parse): caught per-field, that specific field left `null`, not treated as a whole-record failure — one bad field should not suppress the fields that *did* extract cleanly. This is a deliberate difference from Module 02, where a single extraction failure meant the whole classification fell back to `Unknown`; Module 03's fields are independent of each other, so a partial result is both possible and desirable.

## 13. Logging

New action-log entry type, `extract_metadata`, extending the same vocabulary Modules 01–02 already extended (`discover`, `classify`, now `extract_metadata`):

```json
{
  "batch_id": "...",
  "file_id": "...",
  "action": "extract_metadata",
  "from": "current_path",
  "to": null,
  "details": {
    "category": "Invoice",
    "fields_extracted": ["vendor", "invoice_date"],
    "fields_missing": ["invoice_number", "amount", "currency", "tax_type"],
    "mode": "text",
    "processing_time_ms": 910,
    "extraction_complete": true,
    "provider_metadata": {
      "provider_name": "claude_live",
      "model": "claude-sonnet-5",
      "provider_version": null,
      "latency_ms": 875,
      "reasoning": null
    },
    "fallback_used": false,
    "fallback_reason": null,
    "redacted_fields": []
  }
}
```

This illustrates the happy-path shape exactly as implemented: `extraction_complete` is always present (both of Invoice's required fields, `vendor`/`invoice_date`, were found here, so `true`); `provider_metadata` is present because a provider was actually called; `error_detail` is omitted entirely rather than shown as a `null` placeholder, since — like `provider_metadata` — it is only ever added to `details` when applicable (omitted-when-inapplicable, not null-clutter, the same convention Module 02 established). A fallback-path entry would instead omit `provider_metadata` and include a real, sanitized `error_detail` string.

- `fields_extracted`/`fields_missing` — log-only convenience derived from `extracted_metadata` at write time (not persisted on `FileRecord`, not a second source of truth — recomputed from the dict, never drifting from it by construction). Exists purely so a human scanning the action log doesn't have to mentally diff a JSON blob against the taxonomy.
- `extraction_complete` — always present (§7/§11's mechanical definition), computed once and logged, never recomputed by any later module.
- `mode` — `"deterministic"` | `"text"` | `"vision"` | `"mixed"` (a category with both deterministic and judgment fields, e.g. Image's `capture_date` + `description`, logs `"mixed"` — a genuinely new mode value Module 02 never needed, since none of its categories split work between deterministic and judgment fields for the *same* record).
- `provider_metadata` — present only when a provider was actually called (omitted for `mode: "deterministic"`), identical shape and reasoning to Module 02's §12.
- `redacted_fields` — new, specific to Module 03's Bank Statement safeguard (§18): names which fields (if any) were dropped by the redaction check, without ever logging the redacted value itself.
- **Privacy note (reused from Module 02 §17, now load-bearing rather than hypothetical):** unlike Module 02's `reasoning` field (a v1 non-issue since `ClaudeLiveClassifier` leaves it `None`), Module 03's extracted field *values themselves* are the log content, and Bank Statement's redaction rule exists precisely because this log line is not a hypothetical future risk — it is the actual place sensitive data could leak in v1 if unguarded.
- No `Runtime/Reports/*` writing — Module 08's job, out of scope here.

## 14. Database Changes

None required to `storage/database.py` beyond what already exists. `FileRecord.extracted_metadata` is already a plain `dict` field (Module 01's original scaffold), already handled correctly by `save_file_record()`/`load_metadata_store()`'s generic dict (de)serialization — unlike `Category`/`ClassificationSignals`, no typed-model reconstruction step is needed on load, because §7's deliberate choice (below) keeps this field a dict, not a dataclass. `Database/FileIndex/`, `Database/History/`, and `Database/Learning/` remain untouched (Module 04/07 territory).

## 15. FileRecord Changes

**None.** `FileRecord.extracted_metadata: dict = field(default_factory=dict)` already exists, reserved for Module 03 since Module 01's original scaffold (`src/models/file_record.py`, "Metadata Extraction (Module 03)" section). No new field, no new sub-model.

**Why `extracted_metadata` deliberately stays a plain dict, not a typed dataclass (extending Module 02 §14's reasoning, not repeating it from scratch):** `Module 02 Design.md` §14 already reasoned through exactly this question for `classification_signals` vs. `confidence_breakdown`/`extracted_metadata`, and concluded the latter two should stay dicts because their shape "varies by category" / is "genuinely open-ended." This design confirms that conclusion still holds now that Module 03 is being designed in full: §7's table has twelve categories with different, non-overlapping field sets — a single fixed dataclass would need either one field per possible key across all categories (mostly `None` for any given record) or a category-keyed union of per-category dataclasses (real type safety, but meaningfully more code for a field set still expected to be tuned after real files are seen, per §10's "living rule" framing). A plain dict, validated against the taxonomy at the Engine boundary (§12) rather than at the type-system boundary, is the better trade-off for v1 — the same conclusion Module 02 reached, now independently re-confirmed rather than assumed.

## 16. Folder Structure Changes

- `src/pipeline/metadata.py` — already scaffolded (stub) per `src/README.md`'s layout; implemented here, matching the pattern of `classification.py` growing from stub to real module.
- `src/core/archive.py` — **new file.** Deterministic top-level entry listing for Archive's `contents_summary`, using Python's stdlib `zipfile` — no new dependency. (v1's classification-time archive handling was extension-only, §17 of `Module 02 Design.md` — this is Module 03's first actual look inside an archive's structure, listing names only, never extracting contents.)
- `src/core/media.py` — **new file, new dependency.** Embedded audio-tag reading (`track_title`/`artist`/`duration`) for the Audio category, proposed via `mutagen` (pure-Python, no system binary dependency, actively maintained) — added to `src/requirements.txt` only upon approval, not now. Video tag/duration reading is explicitly **not** included in this new module for v1 (§9's table, §27) — a robust solution generally needs a system binary (`ffprobe`) that isn't guaranteed present in every environment this project runs in, and adding that dependency is a bigger decision than this module warrants on its own merits alone (Video's `duration` field simply stays `null` in v1, disclosed in `Rules/Metadata Rules.md`/`KNOWN_LIMITATIONS.md` once written).
- No new `Database/`, `Runtime/`, or `Rules/` **folders** — only the recommended new `Rules/Metadata Rules.md` **file** (§10).

## 17. Performance Considerations

- Deterministic fields (EXIF, archive listing, audio tags, filename parsing) are as cheap as Module 02's own deterministic passes.
- The provider call remains the expensive step, same as Module 02 — one call per text/vision-needing category, now potentially asking for *multiple* fields in a single call (e.g. Invoice's `vendor` + `invoice_date` together) rather than one call per field, deliberately batched at the request level to avoid N provider round-trips for N fields on the same file.
- **Re-extraction cost (new, specific to Module 03):** re-running text extraction independently of Module 02 (§21) means a text-bearing file's content is parsed from disk twice across the pipeline's first two content-reading stages — accepted as a deliberate, small, per-file cost in exchange for keeping Module 02 and Module 03 fully decoupled (§21); revisit only if profiling ever shows PDF/DOCX parsing, not the provider call, as the actual bottleneck (unlikely, given Module 02's own measurement that parsing cost is already dwarfed by provider latency, §18 of `Module 02 Design.md`).
- No batching/parallelization in v1, matching Modules 01–02's established simplicity.

## 18. Security Considerations

**This section fully resolves the first independent review's F2 and F3 findings** — replacing the earlier qualitative "pattern check" description with an exact, testable rule, and stating explicitly why the extra rule is scoped where it is.

**Universal control — closed taxonomy (§7), the generalization F3 asked for:** the single most load-bearing privacy control in this design applies identically to every category, not only Bank Statement: a provider is never asked about, and the Engine never accepts, any field outside a category's defined required/optional list (§7). This alone prevents the most obvious leakage path — a provider volunteering an extra, unrequested field or a free-text field drifting into transcription of sensitive on-screen/in-document content (§7's Image/Screenshot/Resume prohibited-examples) — for all twelve categories. The mechanism itself (§12's key-membership and type validation) already existed in the first draft; what changes here is naming it explicitly as this design's primary privacy control, not merely a data-integrity one, and confirming — per F3's specific ask — that it is the general-purpose answer for every category, so no further per-category redaction machinery is needed anywhere except the one case below.

**Value-level control — scoped specifically to Bank Statement's `account_last4` (resolves F2's precision ask and F3's scoping question together):** closed taxonomy alone is insufficient for exactly one field in the entire v1 taxonomy. `account_last4` is unique in that its whole purpose is to be a deliberately truncated, safe view of a value — the full account number — that is itself prohibited (§7's Bank Statement row). The risk here is not an extra field; it is the *requested* field's value silently containing more than it should. No other field in any category has this shape: every other field is either meant to be captured in full (an invoice's `amount`, a contract's `effective_date`) or is free descriptive text with no single "unsafe superset" value it is derived from. This is why the check below is scoped to this one field rather than generalized into a blanket scanner over every field of every category — a blanket digit-pattern check would routinely misfire on fields that are *supposed* to contain long numbers (an `invoice_number`, a `statement_period` formatted numerically), which would itself violate the "never fabricate/never suppress a true value" principle (§7) in the opposite direction. Scoping precisely, rather than generalizing broadly, is the choice that avoids over-engineering here.

**The rule, stated exactly and testably:**
1. After the Engine receives a candidate value for `account_last4` (in practice always from the judgment path — no deterministic account-number reader exists), strip all non-digit characters from the value.
2. If the resulting digit string is **longer than 4 digits**, the entire field is redacted: `extracted_metadata["account_last4"]` is set to `null`, and the field name `"account_last4"` (never the value) is added to that record's `extract_metadata` action-log entry under `details.redacted_fields` (§13).
3. If the resulting digit string is **4 digits or fewer**, including empty (the provider correctly found nothing), the value passes through unchanged — a genuine 4-digit value is exactly what this field exists to hold, so no valid value can ever be redacted by this check.
4. This check runs exactly once, immediately after the field's value is received and before it is merged into `extracted_metadata` — never re-run, never applied retroactively to an already-persisted record, and never applied to any field other than `account_last4`.

**What remains visible / what is stored / what appears in logs / what later modules may access:**
- **Remains visible** (in `extracted_metadata`, on the persisted `FileRecord`): `bank_name`, `statement_period`, and `account_last4` only when genuinely 4 digits or fewer.
- **Stored internally:** nothing beyond what is visible above — redaction means deletion, not relocation; there is no separate, hidden store of the rejected value anywhere.
- **Appears in logs** (`Runtime/Logs/action_log.jsonl`): the field *name* `"account_last4"` inside `details.redacted_fields` when redaction occurred; never the value, redacted or otherwise. `details.fields_extracted`/`details.fields_missing` (§13) reflect the post-redaction state — a redacted field logs exactly like a genuinely-not-found field, distinguishable only by its presence in `redacted_fields`.
- **What later modules may access:** Module 05/06/07 read only the post-redaction `extracted_metadata` (§7A) — none of them, nor any future module, has a path to the original unredacted value, because it was never persisted past the Engine's own in-memory validation step.

**Why a redacted field needs no new Confidence Rules deduction:** `account_last4` is optional (§7) — a redacted value becomes `null`, which Module 06 treats exactly like any other missing optional field (`−2` deduction, §7A/§11). No new deduction category is introduced; redaction produces an honest `null`, not a special state.

**No code-execution risk:** `core/archive.py`'s use of `zipfile` lists entry *names* only — it never extracts, decompresses, or opens any entry's contents. This is a deliberate scope limit, not an oversight: full archive extraction (and the path-traversal/zip-bomb risk that comes with it) is explicitly out of scope for v1's "best-effort contents summary."

**Provider content exposure:** unchanged from Module 02 §17 — v1's `ClaudeLiveExtractor` makes no network call, no new exposure beyond what Module 02 already accepted for the same reason.

**`reasoning` field exposure:** if a future `MetadataExtractionProvider` populates a `reasoning`-equivalent field, the same discipline from Module 02 §17 applies without modification — no raw sensitive content flows into the action log.

## 19. Known Edge Cases

- **Extraction disagrees with classification** (e.g. a document classified `Contract` reads, on closer text extraction, more like an Invoice). Module 03 **never** revises `category` — it extracts Contract's fields as best it can (likely mostly `null`) and lets the resulting sparse `extracted_metadata` naturally produce a low confidence score (via Module 06's missing-required-field deductions) that routes to review. This is the same "never perform another module's job" discipline Module 02 applied to itself, now applied in the other direction (Module 03 trusting Module 02's output rather than the reverse).
- **Screenshot `capture_date` is `null` in the overwhelming majority of cases.** Documented explicitly in §7 so this doesn't look like a Module 03 defect during future validation — it is the expected, correct result of screenshots genuinely lacking camera EXIF, the same fact Module 02's own classification heuristic already depends on.
- **Multi-document files** (`classification_signals.multi_document_detected == True`) — Module 03 attempts extraction on the file as a single unit (whatever the provider can find, likely from the first/primary document within it), never attempts to split or produce multiple field-sets from one `FileRecord`. Consistent with `Build-out/03 Metadata Extraction/03 Metadata Extraction.md`'s original edge-case note and with `Rules/Confidence Rules.md`'s hard floor already forcing `review_required` regardless.
- **Non-English content** (`classification_signals.non_english_detected == True`) — the extracted text (whatever language it's in) is still sent to the provider; no special-casing needed, since the provider is asked to extract structured fields, not to translate or summarize in English specifically. `detected_language` is available on the record if a future provider implementation wants to use it as prompt context, but the v1 design doesn't require passing it.
- **Locked/encrypted files never reach Module 03** — already routed to `Category.UNKNOWN` by Module 02, filtered out at §3/§11. Documented here only to make explicit that this is not an accidental gap.
- **Video/Audio filename-only fallback produces a low-information `description`/`track_title`** (e.g. the original filename verbatim) when no embedded tags exist and the filename itself is uninformative (`IMG_4821.MOV`). Accepted for v1 — `null` would be equally uninformative and less useful to a human reviewer than the original name; not treated as fabrication since it's the literal, unaltered filename, not a guess.

## 20. Test Strategy

- **Unit tests:** the required/optional field lookup for every category (§7); deterministic extractors (`core/archive.py`, `core/media.py`, filename-pattern parsing for Application) against synthetic fixtures; `MetadataExtractionEngine` orchestration exercised with a **fake/stub `MetadataExtractionProvider`** (a test double returning canned `ProviderResponse`s), mirroring Module 02's `FakeClassificationProvider` pattern exactly.
- **Fallback-specific unit tests:** a stub provider that raises, one that returns an unrequested/extra field (must be dropped, not merged), one that returns a field of the wrong type (must be treated as not-found) — each must leave the affected fields `null`, set the correct `fallback_reason`, and never crash the batch.
- **Redaction-specific unit tests (new, not present in Module 02's suite — no equivalent risk existed there):** exact boundary cases per §18's precise rule — a 4-digit value passes through unchanged; a 5-digit value is redacted to `null` with `"account_last4"` recorded in `redacted_fields`; an empty/missing value passes through as `null` without being counted as "redacted." Also: a stub provider returning a long digit string for a *different* category's numeric field (e.g. Invoice's `invoice_number`) must **not** be redacted — proving the check is scoped to `account_last4` only, not a blanket digit-pattern filter (§18).
- **Timestamp hierarchy unit tests (new, §9A):** Image/Screenshot `capture_date` sourced only from EXIF, never from `FileRecord.modified_at`, even when EXIF is absent (must stay `null`, not silently substituted); Video `content_date`/`duration` always `null` in v1 regardless of file content (no tier-1/tier-3 source exists to test against); Audio `recording_date` populated when a stub embedded tag is present, `null` when absent — none of the three ever equal `FileRecord.modified_at` by coincidence-masking substitution (assert the field is `null`, not merely "some value," when no qualifying tier produced one).
- **Taxonomy-drift test (new, directly modeled on Module 02's F2/F4 lesson — §21 below explains why this is being built proactively rather than discovered via a future audit):** assert every category in `Category` has a defined entry in §7's table (or `Rules/Metadata Rules.md`, once created) and that `Rules/Confidence Rules.md`'s deduction math references field names that actually exist in that table — a direct, structural guard against the exact class of drift Module 02's independent release audit had to catch after the fact (F4).
- **Contract test:** assert every `FileRecord` field outside Module 03's Module Contract guarantees is byte-identical before and after a record passes through `extract_metadata_batch()` — the same generic pattern as Module 02's `test_classify_batch_leaves_every_non_owned_field_byte_identical`, applied here from the start rather than added after a release audit finds it missing.
- **Integration tests:** real files from `Samples/`/`Tests/` datasets already built for Modules 01–02, reused where categories overlap; new `Tests/Module 03 Metadata/` dataset needed for categories with no existing representative sample (a real ZIP archive with known top-level entries, an MP3 with known ID3 tags, an installer-style filename set, a Bank Statement PDF containing an account-number-shaped string specifically to exercise the redaction check).
- **UAT:** same real-end-user pattern as Modules 01–02 — a real external Downloads-style batch, run through Modules 01→02→03 in sequence, with live Claude judgment as the actual provider, same self-graded-sample caveat disclosed up front this time (§21) rather than found by a later audit.
- **Regression:** full suite re-run after every change, same discipline as Modules 01–02.

## 21. Dependencies on Modules 01–02

- Reads (never writes) `current_path`, `extension`, `mime_type`, `status`, `file_id` (Module 01); `category`, `classification_signals` (Module 02). (`content_hash` is Module 04's concern, not read by Module 03 — omitted here after this review found it listed without any corresponding use anywhere else in this document.)
- Reuses `storage/database.py`/`storage/runtime_io.py` unchanged — no changes requested of either frozen module.
- Reuses `core/pdf.py`, `core/text.py`, `core/images.py`, `core/exif.py` unchanged — the same content-reading libraries Module 02 already integrated, called again independently by Module 03.

**Why Module 03 re-extracts text/renders vision images rather than receiving them from Module 02 (a direct answer to "no duplicated logic between modules," anticipating what a future audit would otherwise have to ask):** Module 02's `classify_batch()` contract (`Release/Module02/MODULE_CONTRACT.md`) does not output extracted text or rendered image bytes anywhere — they are ephemeral, computed inside `ClassificationEngine.classify_file()`, used for one provider call, and discarded. Persisting raw extracted text on `FileRecord` so Module 03 could reuse it was considered and rejected: it would mean storing arbitrary file content (including a Bank Statement's own text, before any redaction logic exists to protect it) inside `metadata_store.json`, a much larger privacy surface than anything Module 01 or Module 02 currently creates, for a modest performance saving (§17) on a step that's already dominated by provider latency. Re-extraction is therefore not accidental duplication — it's the same library call made twice, by two modules that each own their own transient use of it, with nothing shared or coupled between them. This also means `ClassificationEngine`/`ClassificationProvider` (internal to `classification.py`, explicitly "implementation details" per `Module 02 Design.md` §25) are never imported by `metadata.py` — Module 03 defines its own parallel `MetadataExtractionEngine`/`MetadataExtractionProvider`/exception classes, structurally similar by deliberate convention-following, not by code sharing. Naming the same architectural pattern the same way across modules is a documentation/naming-consistency goal, not a coupling risk.

**Lessons carried forward explicitly from Module 02's release audit, applied here from the start rather than after the fact:** Module 02 shipped without a taxonomy-drift test and without sanitized fallback diagnostics, and its own independent audit found both gaps before freeze (F2, F3). This design builds both in from the beginning (§13's `error_detail`, §20's taxonomy-drift test) rather than waiting for Module 03's own audit to rediscover the same lesson.

## 22. Responsibilities Reserved for Modules 04–08

- **Module 04 (Duplicate & Version Detection)** — may find `extracted_metadata` fields useful context for a future version-chain heuristic (e.g. two Resumes with the same `candidate_name` but different `version_indicator`) — not a v1 commitment; Module 03 does not itself compare records to each other.
- **Module 05 (Naming & Destination)** — the primary consumer: builds `suggested_name` from `extracted_metadata` per `Rules/Naming Rules.md`'s templates, and resolves compound slots (Resume's `{VersionOrDate}`) that Module 03 deliberately leaves as two separate optional fields (§7) rather than pre-resolving.
- **Module 06 (Confidence & Review)** — diffs `extracted_metadata` against the taxonomy (§7/§10) to compute missing-required/missing-optional deductions; Module 03 never performs this diff itself (§11).
- **Module 07 (Execution)** — no direct dependency on `extracted_metadata` beyond what already flows through `suggested_name`/`suggested_destination`.
- **Module 08 (Logging & Reporting)** — the Daily Summary's per-file table (`Metadata & Log Schema.md`) doesn't currently show extracted fields directly, only `category`/confidence/tier — whether to surface any `extracted_metadata` fields in a future summary is a Module 08 decision, not addressed here.

## 23. Public Interfaces

```
extract_metadata_batch(records: List[FileRecord]) -> List[FileRecord]
```
Module 03's only externally-relevant surface — same shape as `classify_batch()`, callable from `src/main.py`'s CLI the same way Module 02 was wired in (§ Module 02's "Wire into src/main.py" step).

```
MetadataExtractionEngine.extract_file(record: FileRecord) -> EngineResult
```
Internal, not part of the external contract — `EngineResult` carries `extracted_metadata: dict`, `mode`, `processing_time_ms`, `provider_metadata: Optional[ProviderMetadata]`, `fallback_used: bool`, `fallback_reason: Optional[str]`, `error_detail: Optional[str]`, `redacted_fields: List[str]` — deliberately mirroring `classification.py`'s `EngineResult` shape field-for-field where the concept transfers, for a reader already familiar with Module 02 to recognize the pattern immediately.

```
MetadataExtractionProvider.extract(request: MetadataExtractionRequest) -> ProviderResponse
```
The abstract contract, one method — `MetadataExtractionRequest` carries `file_id`, `path`, `extracted_text: Optional[str]`, `mode: Literal["text", "vision"]`, `mime_type: Optional[str]`, and `fields_requested: List[str]` (the one genuinely new field relative to Module 02's `ClassificationRequest` — because Module 03, unlike Module 02, is asking for a variable set of named answers per call, not one fixed classification decision).

## 24. Sequence Diagrams

**Happy path — Invoice, text-bearing:**
```
Module03.extract_metadata_batch([record])
   │
   ├─▶ Engine.extract_file(record)
   │      │
   │      ├─▶ lookup taxonomy(Invoice) → required: [vendor, invoice_date], optional: [invoice_number, amount, currency, tax_type]
   │      ├─▶ core/pdf.py: extract_text(path) → "Invoice #4471 from Amazon, dated ..."
   │      ├─▶ build MetadataExtractionRequest(mode="text", fields_requested=[all six])
   │      ├─▶ Provider.extract(request) → ProviderResponse(vendor="Amazon", invoice_date="2026-07-05", invoice_number=null, amount=1499.00, currency="INR", tax_type="GST")
   │      ├─▶ Engine validates every field (types, requested-key membership)
   │      └─▶ EngineResult(extracted_metadata={...}, mode="text", fallback_used=False, ...)
   │
   ├─▶ save_file_record(record with extracted_metadata set)
   └─▶ append_action_log(extract_metadata entry)
```

**Fallback path — provider exception:**
```
Module03.extract_metadata_batch([record])
   │
   ├─▶ Engine.extract_file(record)
   │      ├─▶ core/text.py: extract_text(path) → "..."
   │      ├─▶ build request, call Provider.extract(request)
   │      ├─▶ Provider raises ProviderError("upstream failure")
   │      ├─▶ Engine catches, _sanitize_error(exc) → error_detail
   │      └─▶ EngineResult(extracted_metadata={vendor: null, invoice_date: null, ...}, fallback_used=True, fallback_reason="provider_exception", error_detail="...")
   │
   ├─▶ save_file_record(record — every requested field null, record still persisted)
   └─▶ append_action_log(extract_metadata entry, fallback fields populated)
```

**Deterministic-only path — Archive:**
```
Module03.extract_metadata_batch([record])
   │
   ├─▶ Engine.extract_file(record)
   │      ├─▶ lookup taxonomy(Archive) → required: [contents_summary]
   │      ├─▶ core/archive.py: list_top_level_entries(path) → ["invoices/", "readme.txt", "photo.jpg"]
   │      └─▶ EngineResult(extracted_metadata={contents_summary: "invoices/, readme.txt, photo.jpg"}, mode="deterministic", provider_metadata=None)
   │
   ├─▶ save_file_record(record)
   └─▶ append_action_log(extract_metadata entry, no provider_metadata key)
```

## 25. State Transitions

`extracted_metadata` moves through exactly three states per record, mirroring the `category`/`None`/`Unknown` three-state pattern Module 02 established:

```
{}  (default, Module 01/02 era — untouched)
 │
 │  record has status == "discovered" AND category not in (None, Unknown)
 ▼
{key: null, key: null, ...}   (Module 03 attempted, nothing found yet — usually
 │                              further populated before persistence, but a full-
 │                              fallback record (§12) can legitimately persist in
 │                              exactly this all-null shape — see §12, not a
 │                              purely transient state that never reaches disk)
 │  deterministic + provider passes run
 ▼
{key: <value or null>, ...}   (Module 03's final, persisted state — every taxonomy
                                key present, each either a real value or an honest null)
```

Records that never enter Module 03 at all (`Unknown`/`None` category, or `unreadable` status) stay at `{}` permanently through this module — the same terminal state as if Module 03 didn't exist for them, which is the correct, honest representation (§5).

## 26. Failure and Recovery Behavior

- **Single-field failure:** caught at the field level where possible (deterministic extractors), that field left `null`, sibling fields unaffected (§12).
- **Single-record failure (provider call, or a deterministic extractor raising unexpectedly outside its own per-field try/except):** caught by `MetadataExtractionEngine.extract_file()`'s own outer boundary, entire record's `extracted_metadata` becomes all-`null` for the fields that were in flight, `fallback_used=True`, batch continues — same shape as Module 02's provider-exception fallback, applied one level up when something outside the expected failure surface occurs.
- **Batch-level safety net:** `extract_metadata_batch()`'s own outer try/except remains the last line of defense for anything genuinely unanticipated, identical in spirit and intended test coverage to `classify_batch()`'s outer safety net (verified there by `test_classify_batch_outer_safety_net_still_covers_truly_unanticipated_failures`; Module 03 should have a direct equivalent, §20).
- **Recovery/idempotency:** re-running `extract_metadata_batch()` against a record that already has non-empty `extracted_metadata` is expected to simply re-run and overwrite — Module 03 has no "already processed" guard of its own, relying on Module 03's caller (eventually `src/main.py`'s pipeline orchestration) to decide whether re-extraction is desired, consistent with how Module 02 was wired (its CLI step "loads discovered-but-unclassified records" — the equivalent Module 03 CLI step would load discovered, classified-but-unextracted records, by the same convention).
- **Undo:** Module 03 does not participate in the action log's `undo` semantics directly (it never moves or renames a file) — an `undo` of a later module's move doesn't need to touch `extracted_metadata` at all, since the extracted fields describe the file's *content*, not its location.

## 27. Future Extensibility

- **A second `MetadataExtractionProvider`** (network API, local model) is a pure plug-in exactly the way a second `ClassificationProvider` would be — the Engine's field-validation/fallback logic doesn't change to add one, by the same design that made this true for Module 02 (§9 of `Module 02 Design.md`).
- **A shared base "AI provider" abstraction across Module 02 and Module 03** (a common `core/ai_provider_base.py` defining the request/response/exception shape once, subclassed by both `ClassificationProvider` and `MetadataExtractionProvider`) was considered and explicitly **not** adopted for v1 — with only two modules and two different request/response shapes so far, this is premature generality (`ROADMAP.md` Version 2+ candidate, not a v1 decision); each module owning its own small, independent provider boundary is cheaper to reason about today and costs nothing to unify later once a third AI-driven module makes the shared shape obvious rather than guessed at.
- **Video duration/tag extraction** — deferred (§16) pending a decision on whether to accept a system-binary dependency (`ffprobe`) or a pure-Python partial solution; flagged for `ROADMAP.md`, not designed further here.
- **A category-keyed union of typed extraction dataclasses** (replacing the plain-dict `extracted_metadata`, §15) remains available as a future refinement once the taxonomy (§7) has stabilized against real files, the same maturity bar `Rules/Naming Rules.md` and `Rules/Metadata Rules.md` (if created, §10) are both explicitly waiting for before their own contents are treated as locked.
- **Surfacing extracted fields in Module 08's Daily Summary** (§22) — not designed here, left open for whoever designs Module 08's reporting in more depth than its current pointer doc does.
- **Engine/Provider scaffolding for deterministic-only categories, named as an accepted trade-off (resolves the first review's F8):** Archive and Application never call a provider at all in v1, and Video calls one only marginally (§9) — meaning `MetadataExtractionProvider` is unused scaffolding for a meaningful fraction of the taxonomy. This mirrors a cost Module 02's own design named for itself (`Module 02 Design.md` §22, risk 1) and is accepted here for the same reason: consistency with an established, already-proven pattern and cheap future extensibility for any category that becomes judgment-dependent later outweigh the small cost of an interface a few categories never exercise. Stated explicitly here as a deliberate acceptance, not an inherited assumption.

---

## 28. Ownership & Boundaries Summary

**What Module 03 owns:**
- `extracted_metadata` — fully, for every record with `status == "discovered"` and a real, non-`Unknown` `category`.
- The `extract_metadata` action-log entry shape (§13).
- The deterministic extraction helpers it introduces (`core/archive.py`, `core/media.py`) and the filename-parsing logic for Application installers.
- The required/optional field taxonomy (§7) — in code always, and in `Rules/Metadata Rules.md` if §10's recommendation is approved.

**What Module 03 must never do:**
- Set or revise `category` or `classification_signals` (Module 02's, frozen).
- Compute `confidence_score`, `confidence_breakdown`, or `tier`, or decide which missing fields "matter" (Module 06).
- Generate `suggested_name` or `suggested_destination`, or resolve a naming template's compound slots (Module 05).
- Compare one file's `extracted_metadata` to another's (Module 04).
- Move, rename, stage, or write to `Runtime/Reports/*` (Modules 07/08).
- Emit any field name outside a category's defined required/optional list (§7's universal prohibited-metadata rule) — this is now a named, explicit rule, not an inference.
- Trust a provider's own claim of what's safe to return for Bank Statement's `account_last4` without independently checking (§18's exact digit-count rule).
- Substitute a lower-priority timestamp source (filesystem time) for a higher-priority one (embedded/EXIF/container metadata) under a content-dated field's name (§9A).
- Fabricate a field value it didn't actually find (§7).

**What becomes immutable after Module 03:**
- `extracted_metadata`, for a given batch run, is not expected to change again except by an explicit future re-run of Module 03 itself (§26) — later modules (04–08) read it but never write to it, per each of their own contracts once designed.
- The required/optional/prohibited assignment for a given category (§7), once confirmed per F1's resolution — a business rule, not something Module 03 itself may revise silently on a future run.

**What later modules are expected to consume:**
- **Module 04** — optionally, `extracted_metadata` fields as version-chain context (not a v1 commitment).
- **Module 05** — `extracted_metadata` directly, as the primary input to every naming template in `Rules/Naming Rules.md`, including resolving Resume's compound naming slot and reaching into `FileRecord.modified_at` itself as the naming layer's own last-resort date fallback (§7A, §9A) — both explicitly Module 05's job, never pre-resolved by Module 03.
- **Module 06** — `extracted_metadata`, diffed against the taxonomy (§7/§10), as the source of missing-required/missing-optional confidence deductions, including treating a redacted `account_last4` exactly like any other missing optional field (§18).
- **Module 07** — no direct field-level dependency today, but inherits Module 03's privacy guarantees passively should a future approval-preview surface metadata to the user (§7A).
- **Module 08** — potentially, for a future richer Daily Summary (§27), not a v1 commitment.

---

**This design is presented for review, not yet frozen.** No code has been written; `FileRecord`/`storage/database.py` require no changes (§14/§15); the required/optional/prohibited taxonomy (§7) is pending your explicit confirmation, category by category, before it is treated as settled business rule rather than this design's own proposal; the recommended documentation relocation (§10, `Rules/Metadata Rules.md`) and the one new dependency (§16, `mutagen`) are both likewise explicitly flagged as pending approval, not applied.
