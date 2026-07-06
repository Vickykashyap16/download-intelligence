# Module 03 (Metadata Extraction) — Independent Implementation Audit

**Posture:** performed as if the auditor did not write this module — every claim below was re-verified directly against the current source files, the frozen design (`Module 03 Design.md`), both design reviews, Module 01/02 contracts, `Rules/*`, `FileRecord`, `storage/database.py`/`storage/runtime_io.py`, `Release/VERSIONS.md`, and `Release/DEPENDENCY_DIAGRAM.md` — not against memory of having built it.

**Scope verified:** `src/pipeline/metadata.py`, `src/core/archive.py`, `src/core/media.py`, `src/pipeline/test_metadata.py`, `src/core/test_archive.py`, `src/core/test_media.py`, `src/requirements.txt`. Full suite re-run fresh during this audit: **155/155 passing** (62 in `test_metadata.py`, 7 in `test_archive.py`, 4 in `test_media.py`, 82 carried over from Modules 01–02, unaffected).

---

## Findings

### F1 — Medium: `_validate_and_merge()`'s type check silently admits Python `bool`

`isinstance(value, (str, int, float))` (metadata.py, `_validate_and_merge`) is true for `True`/`False`, because `bool` is a subclass of `int` in Python. Verified live:

```
validated, redacted = engine._validate_and_merge(Category.INVOICE, ["vendor","invoice_date"], {"vendor": True, "invoice_date": "2026-07-05"})
# -> {'vendor': True, 'invoice_date': '2026-07-05'}
```

**Why it matters:** §12 states "a value's type must roughly match what's expected for that field... a value that doesn't is treated as not-found, not coerced or guessed." No field in the entire taxonomy (§7) is boolean-shaped — every field is a name, date, description, or amount — so a `bool` is always a wrong-type answer, exactly the case this rule exists to catch. The Engine is documented as "the trust boundary between a provider's answer and `extracted_metadata`" (§12/§18); this is the one place that boundary doesn't hold.

**Impact:** a malformed value (`True`/`False`) would be merged into `extracted_metadata`, counted as "found" for `extraction_complete` and for Module 06's future missing-field deductions, and could reach Module 05's naming templates literally as the string `"True"`. Low likelihood in practice (v1's only provider is Claude reading files directly, not a flaky network API), but the validation gap is real and independent of how likely a bad answer is — the whole point of Engine-side validation is to not depend on the provider behaving.

**Trade-off:** none — excluding `bool` costs nothing and has no legitimate use case in this taxonomy.

**Smallest fix:**
```python
if value is not None and (isinstance(value, bool) or not isinstance(value, (str, int, float))):
    continue
```
Plus one regression test (a provider returning `True` for a required field must leave it `null` and `extraction_complete: False`).

---

### F2 — Medium: the taxonomy-drift test §20 explicitly committed to was not built, and no substitute exists

Design §20: *"assert every category in `Category` has a defined entry in §7's table... **and that `Rules/Confidence Rules.md`'s deduction math references field names that actually exist in that table** — a direct, structural guard against the exact class of drift Module 02's independent release audit had to catch after the fact (F4)."*

`test_every_non_unknown_category_has_a_taxonomy_entry` implements only the first half (every category has a taxonomy entry, required list non-empty). No test exists that checks anything in `Rules/Confidence Rules.md` at all.

**Why it matters:** this isn't pedantry about an unimplementable literal reading — `Rules/Confidence Rules.md` doesn't enumerate field names to cross-check (it only says "required fields defined per category in `Build-out/03 Metadata Extraction/03 Metadata Extraction.md`"), but a reasonable equivalent test (assert that citation string points at a file that actually exists, or — once `Rules/Metadata Rules.md` is created per §10 — points there instead) was buildable and wasn't built. This is the same category of gap (a design-committed regression test silently dropped) that Module 02's own release audit flagged as a lesson to carry forward (§21 says as much), and here it recurred.

**Impact:** nothing breaks today, but the citation has, in fact, already drifted (see F3) with no automated guard that would have caught it.

**Trade-off:** a literal field-name-matching test would be over-engineered for a doc that doesn't name fields; a lighter "citation target exists / is the current doc" test is proportionate and cheap.

**Smallest fix:** one new test asserting `Path("Build-out/03 Metadata Extraction/03 Metadata Extraction.md")` (or whatever `Rules/Confidence Rules.md` currently cites) exists, so a future rename/retirement of that file is caught immediately rather than silently producing a dead link. Upgrade to a same-file-name assertion once §10's `Rules/Metadata Rules.md` move happens.

---

### F3 — Low: `Rules/Confidence Rules.md` still cites the superseded pointer doc

Line 21: *"required fields defined per category in `Build-out/03 Metadata Extraction/03 Metadata Extraction.md`"* — the short pre-design pointer note, not `Module 03 Design.md` §7 (the actual current source of truth) or `Rules/Metadata Rules.md` (which doesn't exist yet).

**Why it matters / impact:** confusing for a future reader trying to find the authoritative taxonomy, but functionally harmless in v1 — Module 03's code never reads `Confidence Rules.md`, and Module 06 (the module that will) doesn't exist yet. This is not new drift introduced by this implementation; it's a pre-existing gap the design itself already disclosed and explicitly deferred (§10: *"that reference would be updated to point at `Rules/Metadata Rules.md` instead, if this recommendation is approved"*). Module 03's implementation correctly left `Rules/*` untouched, as instructed.

**Trade-off:** fixing this now means updating a citation to point at a design doc rather than the (still-pending-approval) `Rules/Metadata Rules.md` §10 recommends — arguably premature until that recommendation is actually approved.

**Smallest fix:** either leave as-is until §10 is approved (recommended), or update the citation now to `Build-out/03 Metadata Extraction/Module 03 Design.md §7` as an interim pointer.

---

### F4 — Cosmetic: `Module 03 Design.md` §13's own illustrative log JSON is incomplete/inconsistent, not the implementation

The §13 example JSON includes `"error_detail": null` present-as-null in what represents a successful (non-fallback) call, but doesn't show `extraction_complete` at all anywhere in the example — even though §7/§11 both mandate it always be present. The implementation is actually *more correct* than the design's own illustration: `extraction_complete` is unconditionally present (verified: `test_extract_metadata_batch_writes_an_extract_metadata_action_log_entry` asserts it), and `error_detail`/`provider_metadata` are correctly *omitted* rather than null-clutter, following the established Module 02 convention the module's own docstring cites. This finding is against the frozen design document's example, not against the code.

**Impact:** none on behavior; a future reader comparing the log's actual shape against §13's illustration only might be briefly confused about which keys are always-present vs. conditional.

**Smallest fix:** a documentation-only touch-up to §13's JSON example (add `extraction_complete`, remove the misleading always-present `error_detail: null`) — optional, no code change implied.

---

### Reviewed, no finding (explicitly checked and confirmed correct)

- **Taxonomy fidelity:** every required/optional field for all 11 non-Unknown categories in `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` matches §7's table exactly, field-for-field.
- **Deterministic/judgment split (§9):** `_DETERMINISTIC_ONLY_CATEGORIES` (Archive/Application/Video/Audio) and `_IMAGE_FAMILY_CATEGORIES` (Image/Screenshot) match the design table exactly; text-bearing categories (Invoice/Resume/Bank Statement/Contract/Document) never skip the provider. No category ever calls a provider outside its designed group — confirmed by `provider.received_requests == []` assertions across the deterministic-only test set.
- **Timestamp hierarchy (§9A):** `capture_date` sourced only from EXIF (tier 2), never substituted with `FileRecord.modified_at`, confirmed by a real no-EXIF photo test asserting `None`, not a fallback. Video's `duration`/`content_date` unconditionally `None`. Audio's `recording_date` sourced only from tier-1 embedded tags. No tier-4 (filesystem) value ever reaches `extracted_metadata`.
- **Bank Statement redaction (§18):** exact digit-count rule (>4 digits → redact to `null` + name-only logging; ≤4 including empty → pass through) verified against all four boundary cases in the test suite, and verified scoped to `account_last4` only (a 12-digit `invoice_number` is correctly left untouched).
- **Closed-taxonomy privacy control (§7/§18):** an unrequested key (`"ssn"`) returned by a stub provider is dropped, never merged — confirmed live and by test.
- **Provider boundary correctness:** `MetadataExtractionProvider` ABC cannot be instantiated directly; `ClaudeLiveExtractor` is a documented, exception-raising placeholder identical in spirit to `ClassificationEngine`'s precedent; `response.metadata.latency_ms` is measured by the Engine wrapping the call (not self-reported), the same pattern classification.py uses at line 463, for the same documented reason (design §18/§21 of Module 02).
- **Fallback handling (§12):** provider-unavailable, provider-error, and unanticipated-exception paths all correctly leave judgment fields `null`, preserve already-found deterministic fields (verified: a provider failure on an Image record keeps its real EXIF `capture_date`), set `fallback_used`/`fallback_reason`, and never crash the batch.
- **Text/vision dispatch (§21's "byte-for-byte the same dispatch as `ClassificationEngine._extract()`" claim):** verified directly against `classification.py`'s `_extract()` — identical extension check, identical `render_page_as_image()` fail-fast-only usage, identical return shape. The claim holds.
- **Module Contract (§5):** `test_extract_metadata_batch_leaves_every_non_owned_field_byte_identical` passes — every `FileRecord` field outside `extracted_metadata` is provably untouched, across all 24 fields on the record.
- **Database/serialization (§14/§15):** `storage/database.py` re-read fresh — unmodified; `extracted_metadata` correctly never appears in `_reconstruct_typed_fields()` (deliberately stays a plain dict, no typed reconstruction needed, exactly as §15 argues). A full save→reload round-trip is exercised and passes (`test_extract_metadata_batch_persists_extracted_metadata`).
- **Logging (§13):** `extract_metadata` action-log entries carry every documented field; `provider_metadata` correctly omitted when no provider was called; `redacted_fields` always present (even when empty); no `Runtime/Reports/*` writes anywhere in this module.
- **Modules 01/02 non-interference:** `Release/Module01/MODULE_CONTRACT.md` and `Release/Module02/MODULE_CONTRACT.md` re-read fresh; every field either contract lists as owned is confirmed absent from Module 03's read/write surface except as documented (`current_path`, `category`, etc. — read-only). No source file belonging to Modules 01–02 was modified (mtimes confirmed outside this implementation's session window; contract regression test independently confirms behaviorally).
- **Dependency (§16):** `mutagen` added to `requirements.txt` with the exact justification the design specifies; video tag/duration reading correctly not attempted (no dependency approved).
- **No code-execution/zip risk (§18):** `core/archive.py` only calls `zipfile.namelist()` — reads the central directory only, never decompresses entry contents; confirmed by a dedicated test proving corrupted *entry content* doesn't affect name listing.
- **`Release/VERSIONS.md` still showing Module 03 as "Not started":** correct under that ledger's own stated convention (tracks *released* status only) — not a defect, since release artifacts were explicitly out of scope for this phase.
- **`Release/DEPENDENCY_DIAGRAM.md`:** unchanged, strictly linear 01→02→03→..., consistent with this module's design.
- **Dead scaffolding (§27's accepted trade-off):** `MetadataExtractionProvider` going unused for Archive/Application/Video, and `MetadataExtractionRequest.mime_type` never populated by any Engine code path, are both pre-accepted, explicitly named trade-offs (§27, and the same unused-field pattern already present in Module 02's `ClassificationRequest.mime_type`) — not new dead code.
- **Duplicate logic (`_sanitize_error` re-implemented rather than imported):** explicitly disclosed and justified by design §21 as deliberate convention-following without cross-module coupling — not an oversight.

---

## Severity Summary (original pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 2 (F1, F2) |
| Low | 1 (F3) |
| Cosmetic | 1 (F4) |

---

## Remediation (second pass)

All four findings resolved. Smallest-possible-fix scope only — no redesign, no scope expansion.

**F1 — fixed.** `_validate_and_merge()` (metadata.py) now explicitly excludes `bool` before the `isinstance(value, (str, int, float))` check, since `bool` is an `int` subclass and no field in the taxonomy is boolean-typed:
```python
if value is not None and (
    isinstance(value, bool) or not isinstance(value, (str, int, float))
):
    continue
```
Four new regression tests added to `test_metadata.py`: `True` rejected, `False` rejected, a mixed valid+boolean response drops only the boolean field, and a boolean judgment-field answer does not disturb a sibling deterministic field already found (Image's EXIF `capture_date` survives a boolean `description`).

**F2 — fixed.** `Rules/Confidence Rules.md` doesn't itself enumerate field names — it cites a document as its source of truth — so the drift guard was built in two parts: `test_confidence_rules_metadata_citation_points_to_the_current_taxonomy_source` (asserts the citation points at `Module 03 Design.md`, not a superseded doc, and that the cited file exists) and `test_design_doc_taxonomy_table_matches_code_taxonomy_exactly` (parses §7's actual markdown table and asserts it agrees field-for-field with `REQUIRED_FIELDS`/`OPTIONAL_FIELDS`). Both pass.

**Obsolete-reference report (as requested, not acted on beyond F3's scope):** while investigating F2, the now-superseded `Build-out/03 Metadata Extraction/03 Metadata Extraction.md` pointer doc's own "Fields by category" section was compared against the current taxonomy and found to be stale in several ways — it has no `capture_date` for Image at all, merges Video and Audio into a single undifferentiated row (no `track_title`/`artist` for Audio), and says "counterparties" (plural) where the current taxonomy has a single `counterparty`. This file is no longer cited by anything (after F3's fix) and Module 03 Design.md already frames it as superseded for architectural purposes, so per your "do not silently modify business rules" instruction it was left untouched — flagged here for visibility only, no action taken.

**F3 — fixed.** `Rules/Confidence Rules.md` line 21's citation changed from `Build-out/03 Metadata Extraction/03 Metadata Extraction.md` to `Build-out/03 Metadata Extraction/Module 03 Design.md`. Only the document reference changed — deduction values, tiers, and hard floors are byte-identical to before.

**F4 — fixed.** `Module 03 Design.md` §13's illustrative JSON now includes `extraction_complete: true` (previously missing from the example entirely, despite §7/§11 mandating it always be present) and no longer shows `error_detail: null` as if always-present — a short paragraph now explains the omit-when-inapplicable convention the implementation actually follows. Documentation-only; no implementation code touched.

### Verification

- `src/pipeline/test_metadata.py` alone: **57/57 passing** (51 original + 6 new: 4 boolean-validation tests, 2 drift-guard tests).
- Full suite (`src/`): **161/161 passing** (up from 155 before this remediation).
- Module 01/02 isolated re-run (`test_watch_ingest.py` + `test_classification.py`): **61/61 passing**, unchanged from before this remediation — confirmed unaffected. No Module 01/02 source file was touched; only `src/pipeline/metadata.py`, `src/pipeline/test_metadata.py`, `Rules/Confidence Rules.md`, and `Build-out/03 Metadata Extraction/Module 03 Design.md` were modified.

## Final Severity Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| Cosmetic | 0 |

All findings from the original audit are resolved and independently re-verified against the frozen design, both prior reviews, Module 01/02 contracts, `Rules/*`, `FileRecord`, and the full test suite. No new findings surfaced during remediation.

**Module 03 implementation is approved for integration testing.**
