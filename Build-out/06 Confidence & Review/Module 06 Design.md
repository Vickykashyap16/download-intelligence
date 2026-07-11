# Module 06 (Confidence & Review) — Design

**Status: Architecture frozen.** Reviewed across four independent Design Review passes (`Module 06 Design Review.md`) — Critical/High/Medium findings M1 (hard-floor logging data flow), M2 (Unknown category / Corrupted file identifier collision), M3 (deduction-cap representation), and Low finding L1 (dead cross-reference) were each raised, approved, applied, and re-verified from first principles; one Cosmetic wording inconsistency (C1) was found and fixed on the spot in the fourth pass. No Critical, High, Medium, or Low findings remain. Frozen and accepted by the project owner; Implementation phase now underway. Following `Governance/ENGINEERING_STANDARD.md` §1/§2: this document was produced after reading every Governance document, the frozen contracts for Modules 01–05, `Release/VERSIONS.md`, `Release/DEPENDENCY_DIAGRAM.md`, and the full Module 05 release package, and after reconstructing the pipeline's actual architecture from those sources rather than from memory. This document does not modify any frozen module's design, contract, or implementation — Modules 01–05 remain exactly as released at Pipeline v0.5.0.

Supersedes `Build-out/06 Confidence & Review/06 Confidence & Review.md` for architectural purposes, the same relationship every earlier module's real design document has to its own short pre-design pointer note (that file is left in place, unedited, per the established precedent — neither Module 04's nor Module 05's own pointer file was retroactively marked "superseded" either; this design document is simply the new canonical source going forward, per `ENGINEERING_STANDARD.md` §10).

---

## 1. Purpose

Score how much to trust the complete output of Modules 02–05 for one file — its category, its extracted metadata, its naming/destination suggestion, and its duplicate/version relationship — and translate that trust into a `tier` that Module 07 will use to decide whether a file may be filed automatically, filed after a one-click confirmation, or must be left untouched pending human review. Module 06 is a pure **judgment-aggregation and arithmetic** step: it never re-examines file content itself, never makes a new judgment call about what a file *is*, and never moves, renames, or touches a file on disk. It exists specifically so that every earlier module's uncertainty signals — deliberately collected but deliberately not acted upon by those modules (`Governance/ARCHITECTURE_DECISIONS.md` decision 3) — finally get consumed and turned into one auditable number and one routing decision.

## 2. Architectural decision: deterministic arithmetic, not provider-derived judgment

**This decision is evaluated explicitly, before any other part of this design, per your instruction — not assumed from Module 04/05's precedent alone, even though the conclusion ultimately agrees with it.**

### 2.1 The question

Three things Module 06 produces need a source: the **confidence score** (0–100), the **confidence deductions** that justify it (`confidence_breakdown`), and — implicitly, since no dedicated free-text field exists for it — the **review reason** a human sees when a file lands in `approval_required`/`review_required`. Each of these *could*, in principle, be produced by a live Claude judgment call (e.g. "look at everything Modules 02–05 found and assess how trustworthy this filing decision is, in your own words") rather than by arithmetic. This has to be decided deliberately, because Modules 02 and 03 do have a provider layer, and a reader encountering Module 06 for the first time could reasonably assume every remaining module keeps that pattern by default.

### 2.2 What was actually checked

Every one of Rules/Confidence Rules.md's nine deductions and five named hard-floor rules was traced to a specific, already-existing `FileRecord` field or signal, populated by an already-frozen upstream module, to determine whether computing it requires any new judgment call or only arithmetic over data that already exists. (The table below has four hard-floor rows, not five — "Corrupted file" and "Unknown category" share one identical, indistinguishable trigger, per §2.4/§13, so they are implemented and logged as a single hard floor with one identifier, not two.)

| Rule (`Rules/Confidence Rules.md`) | Source field | Owning module | New judgment required? |
|---|---|---|---|
| Ambiguous classification (−15) | `classification_signals.ambiguous` | 02 | No — already a boolean Module 02 decided |
| No extractable text (−30) | `classification_signals.no_extractable_text` | 02 | No |
| Missing required metadata field (−8 each, max −30) | `extracted_metadata[field] is None`, cross-referenced against that category's required-field list | 03 | No — null-check only |
| Missing optional metadata field (−2 each, max −10) | `extracted_metadata[field] is None`, cross-referenced against that category's optional-field list | 03 | No |
| Naming fallback used (−10 per field) | `naming_signals.fields_fell_back` | 05 | No — already a populated list |
| Near-duplicate / fuzzy match (−20) | `duplicate_signals.fuzzy_duplicate` | 04 | No |
| Version conflict (−25) | `duplicate_signals.version_conflict` | 04 | No |
| Non-English content (−10) | `classification_signals.non_english_detected` | 02 | No |
| Locked / password-protected (−40) | `classification_signals.locked` | 02 | No |
| Unknown category (hard floor — also covers "Corrupted file," see §2.4/§13; one hard floor, one identifier, not two) | `category == Category.UNKNOWN` | 02 | No |
| Near-duplicate (hard floor) | `duplicate_signals.fuzzy_duplicate` | 04 | No (same field as its deduction) |
| Multi-document file (hard floor) | `classification_signals.multi_document_detected` | 02 | No |
| Locked / unreadable file (hard floor) | `classification_signals.locked` | 02 | No (same field as its deduction) |

Every single row resolves to a direct field read or a null-check against an already-known taxonomy — never a re-read of file bytes, never an assessment of file content, never a case where the "right" answer depends on understanding what the document actually says. This is a stronger case for "no provider" than either Module 04's or Module 05's own reasoning: those modules at least touch derived-from-content data (hashes, extracted field values); Module 06 touches only *other modules' already-finished judgments about that data*, one level further removed from the file itself.

### 2.3 Why arithmetic, and not judgment, is the right choice — not merely the available one

- **It is what the business rule itself specifies.** `Rules/Confidence Rules.md`'s own header states the requirement directly: *"Every confidence score must be explainable: a starting value plus a list of named deductions, not an arbitrary AI-generated percentage."* Its closing rationale section is explicit: *"An AI-reported 'I'm 92% confident' number can't be audited or tuned — you can't tell why it moved from one run to the next. A fixed deduction table means every score is reproducible, every deduction is individually adjustable..."* This is not an implementation detail left open for Module 06's design to decide — it is a standing project non-negotiable, restated in `CLAUDE.md` itself (*"Confidence is points-based and auditable... never an arbitrary AI-reported percentage"*). A provider-derived score would directly violate it.
- **It matches `Governance/ARCHITECTURE_DECISIONS.md` decision 6** ("Deterministic before AI — never call a provider when a real answer already exists"): every one of Module 06's inputs *is* a real answer already computed by an earlier module. Calling a provider to re-derive an opinion about data that's already a settled, typed fact on the record would be the exact waste that decision warns against, not a defensible new judgment call.
- **It matches decisions 4/5's own logic in reverse.** Modules 02/03 need a Provider specifically because *no* deterministic source exists for "what does this document say" — that is genuinely something only reading the content can answer. Module 06 has the opposite shape: a deterministic source (the upstream signal) exists for every single thing it needs to decide. The same reasoning that justified a Provider for 02/03 justifies *not* having one for 06.
- **"Review reason" is not a separate field requiring its own judgment call.** `Rules/Confidence Rules.md`'s worked example shows the stored `confidence_breakdown` itself *is* the reason (`{"missing_required_field:invoice_number": -8, "naming_fallback:vendor": -10}`) — a human reading the Daily Summary or the metadata record sees exactly which named deductions applied, which is already a complete, auditable explanation. No natural-language summary sentence is generated anywhere in the existing schema (`Build-out/08 Logging & Reporting/Metadata & Log Schema.md`'s Daily Summary table has no free-text "reason" column, only Confidence/Tier), so there is no gap here for a provider to fill even under the most generous reading of "review reason."
- **Consistency with the two most recent, most rigorously audited modules.** Modules 04 and 05 both independently reached "no provider" through their own dedicated design-review sections (`Module 04 Design.md` §14, `Module 05 Design.md` §17), each for structurally the same reason: every decision is a computation over already-structured data. Module 06 is a third, independent confirmation of the same pattern — not an assumption carried over uncritically, but the same conclusion re-derived from scratch against Module 06's own actual inputs (§2.2's table above).

### 2.4 The one genuinely non-obvious mapping — re-verified precisely against actual upstream behavior, per your directive to rely only on existing guarantees and introduce no new signal

"Corrupted file (fails to open/parse at all) → always `review_required`" has no dedicated `FileRecord` signal — there is no `corrupted: bool` field anywhere in `ClassificationSignals`, `DuplicateSignals`, or `NamingSignals`, and this design introduces none. The only candidate existing guarantee is Module 02's own contract language for `category`: *"`Category.UNKNOWN` specifically means 'Module 02 tried on a readable file and found no match or hit a known failure mode'"* (`Release/Module02/MODULE_CONTRACT.md`).

**This guarantee was re-traced against the actual code (`src/pipeline/classification.py`, `src/pipeline/metadata.py`), not assumed from the previous pass's own conclusion — and the previous pass's claim that it covers *every* corrupted file was found to be too broad. The real coverage splits by category family:**

- **For the seven judgment-dependent categories** (Invoice, Resume, Bank Statement, Contract, Document, Image, Screenshot): Module 02's classification Engine wraps its text/image-reading branches in `try/except`, converging any unreadable or malformed file onto `Category.UNKNOWN` (`fallback_reason="unreadable_content"`) — confirmed directly in `classification.py` line 343. **For these seven categories, `category == Category.UNKNOWN` is a real, verified, sufficient existing guarantee for "this file could not be meaningfully read," and the "Unknown category" hard floor fully and correctly implements the "Corrupted file" floor with no new signal.**
- **For the four deterministic-only categories** (Archive, Application, Video, Audio — `_DETERMINISTIC_ONLY_CATEGORIES`), `category` is assigned purely from file extension (`_EXTENSION_CATEGORY_MAP`, `classification.py` line 50), **before any file content is ever read** — a corrupted `.zip`, `.exe`, `.mp4`, or `.mp3` still receives its real, non-`Unknown` category. Content is only touched later, by Module 03, and only for two of the four:
  - **Archive:** `summarize_contents()` opening a corrupted zip fails, producing `extracted_metadata["contents_summary"] = None` (its one required field) via the existing `fallback_reason="extraction_failed"` path (`metadata.py` line 361–371) — this degrades to the ordinary "missing required field" deduction (§12, −8), **not** a hard floor. A corrupted Archive file with no other issues would score 92 (`approval_required`), not `review_required`.
  - **Audio:** `_extract_audio_fields()` is likewise wrapped by the same outer `try/except` — a corrupted audio file degrades to a missing-required-field deduction on `track_title`, the same as Archive, not a hard floor.
  - **Application and Video:** both are parsed from the **filename string alone** (`_parse_application_filename()`/`_parse_video_filename()`, `metadata.py` lines 131–164) and explicitly "never raise" — file content is never opened or validated at all for these two categories in the current pipeline. **A corrupted Application or Video file is, today, completely undetectable as corrupted by any upstream module** — no signal exists anywhere on `FileRecord` that distinguishes it from a healthy one.

**Conclusion, precisely stated (not overclaimed):** Module 06 implements the "Corrupted file" hard floor as `category == Category.UNKNOWN` and only that — introducing no new signal, relying only on Module 02's existing, cited guarantee. This is **complete and correct for the seven judgment-dependent categories**, and **a disclosed, inherited gap for Archive/Audio** (corruption there costs only a −8 deduction, not a forced `review_required`) **and for Application/Video** (corruption there is invisible to the pipeline entirely). This gap is not introduced by Module 06 and cannot be closed by Module 06 alone — closing it would require Module 02 or Module 03 to detect and report corruption for these four categories, which is a change to an already-frozen module's contract and therefore a matter for the Frozen Module Change Policy, not this design. Recorded here as a confirmed implementation instruction (§13, §24) and carried forward to §22 (Risks) and Module 06's own future `KNOWN_LIMITATIONS.md` at release time, so it is disclosed rather than silently inherited.

**Corollary, added per your M2 clarification: "Corrupted file" is not an independently detectable condition, and is not a second hard floor.** Because its trigger (`category == Category.UNKNOWN`) is byte-for-byte identical to "Unknown category"'s trigger, and Module 06 has no signal anywhere on `FileRecord` that distinguishes *why* a record is `Category.UNKNOWN` (ambiguous content, unsupported content, or a genuine parse failure all converge on the same value — this is the whole point of §2.4's analysis above), the two conceptual rules named in `Rules/Confidence Rules.md` are implemented as **one** hard floor: one trigger, one log identifier (`unknown_category`, §13), one tier ceiling (`review_required`). A `Category.UNKNOWN` record's `hard_floors_applied` entry never contains a second, separate `corrupted_file` value — there is no second fact to report, only one signal wearing two business-rule names. This relationship is documented here, in §13's hard-floor table (one row, not two), and in §16's logging definition, rather than implemented as if the two rules were independently observable.

### 2.5 Conclusion

**Module 06 is fully deterministic. No Provider, no Engine/Provider split, no live-Claude-judgment step of any kind.** Two layers only, mirroring Module 04/05's established shape: `score_confidence_batch()` (batch orchestration) → `ConfidenceEngine` (per-file decision-making). This conclusion is treated as confirmed for the remainder of this design (§9 onward assumes it), not left open — the evidence in §2.2–2.4 is conclusive, not merely convenient.

## 3. Responsibilities

- Compute `confidence_score` (0–100) for every eligible record, per `Rules/Confidence Rules.md`'s formula: start at 100, subtract every applicable deduction, clip to `[0, 100]`.
- Compute `confidence_breakdown` — the exact named-deduction dict that produced the score, keyed exactly as `Rules/Confidence Rules.md`'s worked example shows (e.g. `"missing_required_field:invoice_number"`, `"naming_fallback:vendor"`).
- Compute `tier` (`auto` | `approval_required` | `review_required`) from the score via the tier lookup table, then apply every hard floor — hard floors may only push the tier **down**, never up (`Rules/Confidence Rules.md`'s own stated invariant).
- Read, but never modify, every signal Modules 01–05 already produced.
- Log one `score_confidence` action-log entry per file processed, carrying the same breakdown/tier detail as the persisted record plus which hard floor(s), if any, applied.

## 4. Responsibilities explicitly reserved for later modules (per `ARCHITECTURE_DECISIONS.md` decision 3)

Stated up front, before implementation, so a future audit can verify Module 06's actual code against this list rather than assuming scope from its name alone:

- **Deciding what to actually do about a low tier** — leaving a file in place, moving it, or asking for approval — is Module 07's job entirely. Module 06 only computes `tier`; it never reads or writes `processed_at`/`approved_by`/`approved_at`, never touches the filesystem, and never checks `suggested_destination` against a real directory listing.
- **Rendering the Daily/Weekly Summary, Duplicate Report, or Storage Report** is Module 08's job. Module 06 never writes to `Runtime/Reports/`.
- **Deciding whether a specific deduction weight is still calibrated correctly** is an ongoing, disclosed project-owner tuning activity (`Rules/Confidence Rules.md`'s own "Tuning note"), not something Module 06's code silently self-adjusts. Module 06 reads the weights as fixed constants matching the current rules document; changing a weight is a `Rules/Confidence Rules.md` edit plus a version bump, not a runtime behavior.
- **Learning from user corrections** (`Database/Learning/User Corrections.json`) is out of scope for v1 for every module, Module 06 included — v1 is passive capture only, per `CLAUDE.md`'s "Working Rules." Module 06 does not read or write this file.
- **Re-deriving or second-guessing an upstream module's own signal.** If `classification_signals.ambiguous` is `False`, Module 06 does not independently decide the classification "looks ambiguous anyway" — it trusts the signal exactly as Module 02 reported it, the same "no module retroactively fixes an earlier module's value" discipline `ENGINEERING_STANDARD.md` §11 requires.

## 5. Inputs

**Receives:** `List[FileRecord]` from Module 05 — specifically, every record with `status == "discovered"`, a real `category` (including `Category.UNKNOWN` — the hard floor for it is exactly what Module 06 exists partly to enforce), and a real `suggested_name` (confirms Module 05 has already processed the record, so `naming_signals`, `duplicate_signals`, and `extracted_metadata` are all in their final, stable state before Module 06 reads any of them). See §11 for the exact eligibility filter and why it's shaped this way.

**Also receives (internally):** nothing beyond the record list itself. No provider (§2), no cross-record batch state (§9 — unlike Module 05's within-batch collision check, no record's score depends on any other record in the same batch), no `Database/FileIndex/`/`Database/History/` reads.

**Fields actually read**, each traced to an explicit upstream `MODULE_CONTRACT.md` guarantee (full traceability table in §19):
`category`, `classification_signals` (`ambiguous`, `no_extractable_text`, `non_english_detected`, `locked`, `multi_document_detected`), `extracted_metadata`, `naming_signals.fields_fell_back`, `duplicate_signals` (`fuzzy_duplicate`, `version_conflict`), plus `status`, `file_id`, `discovered_at` for eligibility filtering and deterministic batch ordering (the same two fields every prior module's batch order already keys on).

## 6. Outputs

**Produces:**
- The same `List[FileRecord]` handed in, enriched in place — mirrors every earlier module's batch shape exactly (`classify_batch()`/`extract_metadata_batch()`/`detect_duplicates_batch()`/`suggest_naming_and_destination_batch()`'s established convention).
- One `score_confidence` action-log entry per file processed in `Runtime/Logs/action_log.jsonl` (§16 for the confirmed shape).
- No new `Database/` structures (§14) and no `Runtime/Reports/` output (§15) — nothing later needs to look up "by confidence score," and report rendering is Module 08's job.

## 7. Module Contract

**INPUT:** `List[FileRecord]` from Module 05, filtered to `status == "discovered"`, `category is not None`, `suggested_name is not None` (§11).

**OUTPUT:** Same records, enriched in place. **No disclosed side effect on any other record** — unlike Module 04, and the same as Module 05: Module 06 never reads or writes a record other than the one currently being scored. No cross-record dependency exists in the scoring math itself (each record's score depends only on its own fields).

**Guarantees** — fields Module 06 owns and fully populates, for every eligible record:
- `confidence_score` — an `int` in `[0, 100]`, populated for every processed record, never left `None`.
- `confidence_breakdown` — a `dict[str, int]`, always present (an empty dict `{}` is the valid, honest "no deductions applied" case — the file scored a clean 100 — not a sentinel for "not yet processed"; distinguishing "not yet processed" from "processed, nothing to deduct" is done via `confidence_score is None`, not via `confidence_breakdown`'s emptiness, exactly mirroring how `naming_signals.fields_fell_back == []` already means "processed, no fallback" rather than "not yet processed" for Module 05).
- `tier` — one of `"auto"` | `"approval_required"` | `"review_required"`, populated for every processed record, never left `None`.

**Determinism guarantee (part of the external contract):** given the same input record (its own fields, independent of any other record in the batch or any prior run's state), Module 06 always produces the same score, breakdown, and tier. Batch order still follows the established `discovered_at` ascending / `file_id` lexicographic tie-break convention for log-ordering consistency with every other module, but — unlike Module 04's collision-sensitive ordering or Module 05's within-batch naming-collision ordering — no record's *output value* depends on that order, since nothing about Module 06's math reads any other record.

## 8. DOES NOT MODIFY

Module 06 never sets or touches any of the following on any record — every one is left exactly as Modules 01–05 left it:

- **Module 01's own fields** — `file_id`, `source_id`, `original_name`, `original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `batch_id` are all read (`status`, `file_id`, `discovered_at`) or ignored, never rewritten.
- **Module 02's own fields** — `category`, `classification_signals` are read, never rewritten.
- **Module 03's own fields** — `extracted_metadata` is read, never rewritten.
- **Module 04's own fields** — `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals` are read (`duplicate_signals` only), never rewritten.
- **Module 05's own fields** — `suggested_name`, `suggested_destination`, `naming_signals` are read, never rewritten.
- **Preview, Approval & Execution** — `processed_at`, `approved_by`, `approved_at`, `reversible`.
- **Logging & Reporting** — `Runtime/Reports/*`. Module 06 only ever appends to `Runtime/Logs/action_log.jsonl`, never to `Reports/`.

**Verified by (committed for implementation, §21):** a Module Contract immutability test asserting every non-owned field is byte-identical before and after `score_confidence_batch()` runs, built exhaustively from the start (all fields except the three owned ones — the same rigor Module 05's own equivalent test was built with from day one, not requiring a follow-up finding to reach it the way Module 04's first pass did).

## 9. Internal architecture (confirmed, per §2.5)

```
score_confidence_batch()   (src/pipeline/confidence.py — batch orchestration:
                             deterministic discovered_at/file_id ordering,
                             persistence, logging — mirrors every prior
                             module's batch-function shape)
      -> ConfidenceEngine   (per-file decision-making: compute deductions ->
                              sum -> clip -> look up tier -> apply hard floors;
                              fully deterministic, no Provider)
```

No Engine/Provider split (§2). No code sharing with any sibling module's Engine (`ARCHITECTURE_DECISIONS.md` decision 5's "convention-following, not coupling" default) — `ConfidenceEngine` is its own class, not a subclass or wrapper of `ClassificationEngine`/`MetadataExtractionEngine`/`DuplicateDetectionEngine`/`NamingEngine`, even though its overall two-layer shape matches Module 04/05's.

Supporting helpers (in `confidence.py`, not `core/`, following the same "module-specific logic stays local" convention every prior module has used):
- `compute_deductions(record) -> dict[str, int]` — walks every rule in §12's table, returns only the deductions that actually applied (an empty dict when none did). **Enforces the −30 required-field / −10 optional-field category caps itself, before returning (user-approved fix M3)** — see §12's "Cap representation" note for the exact, single-interpretation rule.
- `compute_score(deductions) -> int` — `100 + sum(deductions.values())`, clipped to `[0, 100]` (post-freeze correction, implementation-discovered — see `Module 06 Design Review.md`'s "Post-freeze correction" section). Every value in the `deductions` dict is itself already negative (§12's table: `−15`, `−30`, etc. — matching `Rules/Confidence Rules.md`'s own worked example, `{"missing_required_field:invoice_number": -8, "naming_fallback:vendor": -10}` → `100 + (-8) + (-10) = 82`), so *adding* them to 100 is what performs the subtraction; a literal `100 - sum(deductions.values())` would double-negate and inflate the score instead. Unconditional and exact: because `compute_deductions()` already enforces both caps before returning (per its own bullet, above), this sum always equals the true, capped score reduction — `compute_score` itself performs no capping logic of its own and needs none.
- `lookup_tier(score) -> str` — the three-band lookup (§13).
- `apply_hard_floors(record, tier) -> tuple[str, list[str]]` — walks every hard floor in §13's table exactly once and, for each one, evaluates its trigger condition against `record`. Returns `(new_tier, hard_floors_applied)`: `new_tier` is `tier` clamped down (never raised) by the minimum of every hard floor whose trigger was true, and `hard_floors_applied` is the list of those same triggered floors' log identifiers (§13's "Log identifier" column), in the table's fixed row order. This single walk is the sole source of both the tier-clamping decision and the logging data — there is no second, separate computation of "which floors applied" anywhere else in the design (user-approved fix M1: the tier decision and the log record are two views of the same walk, not two independent facts that could drift apart). Deliberately takes the already-computed `tier`, not the raw `score`, as its input — a hard floor is a tier-level override, not a second scoring pass.

## 10. Required/optional field taxonomy: an independent, disclosed, cross-checked table — not an import from Module 03 (confirmed decision, with rationale)

Module 06 needs to know, per category, which `extracted_metadata` keys are "required" (−8 each) versus "optional" (−2 each). The literal data (`REQUIRED_FIELDS`/`OPTIONAL_FIELDS`) already exists as module-level constants in `src/pipeline/metadata.py` — but importing them directly was considered and **rejected**:

- `Governance/ARCHITECTURE_DECISIONS.md` decision 15 states plainly: `MODULE_CONTRACT.md` is *"explicitly the only part of a module's design that later modules may depend on"* — a module's internal architecture, including its private module-level constants, "is never part of the contract and may change freely as long as the contract's behavior holds." `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` are not mentioned anywhere in `Release/Module03/MODULE_CONTRACT.md` — only the *shape* of `extracted_metadata` (exactly one key per taxonomy field) is guaranteed, not that the taxonomy dicts themselves are stable, importable API surface.
- This is the identical situation decision 5 already resolved for Module 02/03's Provider classes: real, disclosed duplication, deliberately preferred over a cross-module import that would create a hidden coupling (a future refactor of `metadata.py`'s internal constant names or structure could silently break Module 06 if it imported them directly).

**Decision:** `confidence.py` defines its own literal `_REQUIRED_FIELD_COUNT`/`_OPTIONAL_FIELD_COUNT`-equivalent table (or the field lists themselves, whichever proves cleaner at implementation time — an implementation detail, not an architectural one), sourced from and matching `Build-out/03 Metadata Extraction/Module 03 Design.md` §7 (the frozen, authoritative design section `Rules/Confidence Rules.md` itself already cites: *"required fields defined per category in Build-out/03 Metadata Extraction/Module 03 Design.md §7"*) — not from `metadata.py`'s code. A permanent regression test cross-checks Module 06's own table against `metadata.py`'s real, current `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` (reading the actual runtime dicts for the *test's* own verification purposes only, never from `confidence.py`'s production code path) — the identical discipline already established for `Rules/Confidence Rules.md`'s own citation-and-taxonomy-cross-check test, built after Module 03's implementation audit F2 specifically to catch this exact class of drift.

## 11. Processing workflow (confirmed)

For each eligible record, in the same deterministic batch order every module since Module 04 has used (`discovered_at` ascending, `file_id` lexicographic tie-break — preserved here purely for log-ordering consistency with the rest of the pipeline, not because any output value depends on it, per §7):

1. **Filter eligibility:** `status == "discovered"` and `category is not None` and `suggested_name is not None`. This mirrors `suggest_naming()`'s own filter shape in `main.py` (a direct field-null check, not a dedicated idempotency function) for the same reason Module 05's filter works this way: `confidence_score` is unambiguously `None` only pre-processing and always a real `int` afterward — no "legitimately stays null forever" case exists, so a Module-04-style dedicated `needs_confidence_scoring()` helper is not needed for this reason alone. (`confidence_score is None` is *also* used as the "not yet processed" half of the real re-run filter `main.py`'s eventual `score_confidence()` CLI function will use — see §21's eligibility-filter test bullet and §24's confirmed per-record-vs-CLI-level filter distinction.)
   - Requiring `suggested_name is not None` (rather than just `category is not None`) is deliberate: it guarantees Module 05 has already run, so `naming_signals`, `duplicate_signals`, and `extracted_metadata` are all in their final state — Module 06 must never score a record using a signals object that's still `None` because an upstream module hasn't reached it yet (`ENGINEERING_STANDARD.md` §11: "No module reads a field before the module that owns it has actually populated it").
   - A record Module 01 marked `status == "unreadable"` never reaches this filter (`category` stays `None` forever for such records) — consistent with every prior module's treatment; `"unreadable"` is a distinct, Module-01-only lifecycle state, not something Module 06 scores. See §23 item 4 for why this doesn't leave a gap in the "locked/unreadable" hard floor's real-world coverage.
2. **Compute deductions:** `compute_deductions(record)`, per §12's full table.
3. **Compute score:** `compute_score(deductions)` — sum the (already-negative) deduction values, add that sum to 100, clip to `[0, 100]` (post-freeze correction — §9).
4. **Look up tier:** `lookup_tier(score)` — the three-band table (§13).
5. **Apply hard floors:** `tier, hard_floors_applied = apply_hard_floors(record, tier)` — each applicable floor clamps the tier down, never up (§13); `hard_floors_applied` is produced by this same call, not recomputed separately (§9, user-approved fix M1).
6. **Persist and log:** save the record (`confidence_score`, `confidence_breakdown`, `tier` now populated), append one `score_confidence` action-log entry carrying `hard_floors_applied` exactly as returned by step 5 (§16).

A single record's failure at any step never aborts the batch (§18) — the same resilience pattern every earlier module already establishes.

## 12. Deduction table (confirmed mapping, business-rule values owned by `Rules/Confidence Rules.md` — not restated or altered here, only mapped to source fields)

| Deduction key format | Trigger | Value | Source |
|---|---|---|---|
| `"ambiguous_classification"` | `classification_signals.ambiguous is True` | −15 | `classification_signals` |
| `"no_extractable_text"` | `classification_signals.no_extractable_text is True` | −30 | `classification_signals` |
| `"missing_required_field:<field>"` | `extracted_metadata[field] is None` for each `field` in that category's required list (§10) | −8 each, capped at −30 total | `extracted_metadata` + §10's table |
| `"missing_optional_field:<field>"` | `extracted_metadata[field] is None` for each `field` in that category's optional list (§10) | −2 each, capped at −10 total | `extracted_metadata` + §10's table |
| `"naming_fallback:<field>"` | one entry per field in `naming_signals.fields_fell_back` | −10 each | `naming_signals` |
| `"fuzzy_duplicate"` | `duplicate_signals.fuzzy_duplicate is True` | −20 | `duplicate_signals` |
| `"version_conflict"` | `duplicate_signals.version_conflict is True` | −25 | `duplicate_signals` |
| `"non_english_content"` | `classification_signals.non_english_detected is True` | −10 | `classification_signals` |
| `"locked_file"` | `classification_signals.locked is True` | −40 | `classification_signals` |

`Category.UNKNOWN` records have no required/optional field list (§10's table has no entry for it, mirroring `extracted_metadata`'s own `{}` default for records Module 03 never processed) — the missing-field deductions simply contribute nothing for such records, which is immaterial since the Unknown-category hard floor (§13) already forces `review_required` regardless of the arithmetic.

Deduction keys are proposed here at the string-format level (e.g. `missing_required_field:vendor`) to exactly match `Rules/Confidence Rules.md`'s own worked example (`"missing_required_field:invoice_number"`, `"naming_fallback:vendor"`) — the two keys the rules document itself already names verbatim. The remaining seven keys are this design's own proposed naming, chosen to follow the same `snake_case_reason` / `snake_case_reason:field` shape; not yet used anywhere else, so free to confirm or rename during review without any compatibility concern.

**Cap representation (user-approved fix M3) — the single, deterministic rule for how the −30 required-field / −10 optional-field caps (`Rules/Confidence Rules.md`) affect `confidence_breakdown`'s actual contents.** These are the frozen business-rule cap *values* (unchanged, restated here only to anchor the rule below, not reinterpreted); this note defines only how `compute_deductions()` applies them — a gap the previous pass of this design left unspecified.

For each of the two capped categories (`missing_required_field:*`, `missing_optional_field:*`) independently, walk that category's missing fields for the record in the same fixed order §10's required/optional field table lists them in (deterministic — never iteration-order-dependent), maintaining a running subtotal for that category only:

1. For each missing field in order: if adding its full nominal deduction (`−8` for required, `−2` for optional — the exact, unchanged values from §12's table above) would keep the category's running subtotal within its cap (`−30` or `−10`), add the field to `confidence_breakdown` at its full nominal value and update the running subtotal.
2. Once a field's full nominal value would push the running subtotal past its cap, that field — and every subsequent missing field in the same category, regardless of order — is still added to `confidence_breakdown` as its own key (**never omitted, per your requirement that nothing be hidden once a cap is reached**), but recorded at a value of `0`. A `0` entry means exactly one thing: "this field is genuinely missing, and is honestly disclosed as such, but contributed no additional score deduction because this category's cap was already reached by earlier-ordered fields" — never a signal that the field is actually present.
3. The two categories (required, optional) are capped independently of one another and of every other deduction in §12's table — reaching the required-field cap has no effect on optional-field deductions, and vice versa.

This is the only interpretation consistent with `compute_score()`'s unconditional `100 + sum(deductions.values())` formula (§9, post-freeze correction): because every category's running total inside `confidence_breakdown` is already held at or under its cap before `compute_deductions()` returns, the sum is always exactly the true, capped score reduction — `compute_score()` requires no separate capping step, and `confidence_breakdown` always remains a complete, truthful list of every missing field, auditable exactly as `Rules/Confidence Rules.md`'s own stated rationale (§2.3) requires. No deduction value, category rule, or cap threshold is changed by this note — only the previously-unstated mechanics of applying an already-frozen rule.

## 13. Tier and hard floor table (confirmed mapping, business-rule values owned by `Rules/Confidence Rules.md`)

**Tier lookup** (applied to the clipped score before any hard floor):

| Score | Tier |
|---|---|
| 95–100 | `auto` |
| 80–94 | `approval_required` |
| < 80 | `review_required` |

**Hard floors** (applied after the tier lookup; each one, if triggered, clamps the tier to its stated minimum — never raises it). Four hard floors, not five: `Rules/Confidence Rules.md` names "Unknown category" and "Corrupted file" as two separate business rules, but — per §2.4/§2.4's corollary — they resolve to one identical, indistinguishable trigger on `FileRecord`, so they are implemented and logged here as **one** hard floor with one row, one trigger, and one log identifier (user-approved fix M2: one deterministic trigger, one deterministic identifier, one deterministic logging representation, per hard floor, with no exceptions):

| Hard floor | Trigger — existing upstream guarantee relied on, exactly | Minimum tier forced | Log identifier |
|---|---|---|---|
| Unknown category (also implements "Corrupted file" — §2.4) | `category == Category.UNKNOWN` — `Release/Module02/MODULE_CONTRACT.md`'s `category` guarantee | `review_required` | `unknown_category` |
| Near-duplicate / fuzzy match | `duplicate_signals.fuzzy_duplicate is True` — `Release/Module04/MODULE_CONTRACT.md`'s `duplicate_signals` guarantee | `approval_required` (never `auto`) | `fuzzy_duplicate` |
| Multi-document file | `classification_signals.multi_document_detected is True` — `Release/Module02/MODULE_CONTRACT.md`'s `classification_signals` guarantee | `review_required` | `multi_document_detected` |
| Locked / unreadable file | `classification_signals.locked is True` — `Release/Module02/MODULE_CONTRACT.md`'s `classification_signals` guarantee (see §13A for why this single field is sufficient) | `review_required` | `locked_file` |

`"Corrupted file"` is never a separate `hard_floors_applied` entry and is never checked as a second condition anywhere in `apply_hard_floors()` (§9) — a `Category.UNKNOWN` record's log entry contains `unknown_category` exactly once, the same as any other `Category.UNKNOWN` record, regardless of whether the underlying cause was ambiguity, an unsupported format, or a genuine parse failure (§2.4 — Module 06 cannot and does not distinguish these). Every other trigger in this table remains fully independent of every other (no two of the remaining three floors, or of "Unknown category," share a trigger field), so no other row requires this treatment.

No new signal is introduced anywhere in this table — every trigger reads a field already named as a "Guarantees" entry in an already-frozen `MODULE_CONTRACT.md`, per your instruction.

"Clamps down, never raises" is implemented as: for each triggered floor, take the stricter (lower) of the tier so far and the floor's minimum — `review_required` is stricter than `approval_required`, which is stricter than `auto`. Multiple floors can apply simultaneously (e.g. an Unknown-category file that's also a fuzzy match); the result is simply whichever floor's minimum is strictest, which in practice is always `review_required` once any floor other than the fuzzy-match one applies.

### 13A. "Locked / unreadable file" — precisely, why `classification_signals.locked` alone is sufficient (confirmed, not open)

Re-traced against Module 01 and Module 02's exact contract text, per your instruction to rely only on existing guarantees and infer no new state:

- A file Module 01 marks `status == "unreadable"` (a real filesystem-level read failure at discovery time) is, by Module 02's own contract, **never processed at all**: *"Records with `status == 'unreadable'` are accepted into `classify_batch()`'s input list but passed through completely untouched... Module 02 never attempts to classify a file Module 01 couldn't read"* (`Release/Module02/MODULE_CONTRACT.md`, INPUT section). Such a record's `category` therefore stays `None` forever — it never satisfies Module 06's own eligibility filter (§11: `category is not None`), and never receives a `tier` at all, by the same structural exclusion every module since Module 02 already applies to it. It does not need a hard floor because it is never a candidate for filing in the first place — Module 05 never names it, Module 06 never scores it, and Module 07 will never be asked to move it.
- A file that *is* readable at the filesystem level but is locked/password-protected at the content level (a real password-protected PDF, confirmed handled during Module 03's own UAT — `Release/Module03/`'s release record) **is** processed, and Module 02's classification Engine sets `classification_signals.locked = True`, explicitly named in `Release/Module02/MODULE_CONTRACT.md`'s `classification_signals` guarantee. This is the only real-world case the "Locked / unreadable file" rule is actually protecting against for a file that could otherwise reach Module 07 — and it is fully covered by this one existing field.

**Conclusion:** `classification_signals.locked` is sufficient by itself. The "unreadable" half of the rule's name describes a state (`status == "unreadable"`) that is already, structurally, excluded from ever reaching a filing decision — adding a check for it in Module 06 would be dead code, not a safety improvement, since no record in that state can ever arrive at Module 06's eligibility filter.

## 14. Database changes

**None.** No new `Database/` file, no new index. Nothing later in the pipeline needs to look up a record *by* its confidence score or tier the way Module 04's hash/phash/name indexes let future records be compared against past ones — Module 07 reads `tier` directly off the `FileRecord` it's already holding, the same way it will read `suggested_name`/`suggested_destination`. This mirrors Module 05's own "no new Database structures" precedent exactly, for the same underlying reason (a scoring/labeling module, not a lookup-index-building one).

## 15. Runtime changes

- `Runtime/Logs/action_log.jsonl` gains one new action type, `score_confidence` (confirmed) — §16.
- No `Runtime/Reports/*` output. Report rendering (Daily Summary, Weekly Summary, Duplicate Report, Storage Report) is Module 08's job entirely; Module 06 only produces the `confidence_score`/`confidence_breakdown`/`tier` fields those reports will eventually read.
- No `Runtime/Temp/` usage — Module 06 processes records already fully resident in the metadata store; it has no in-flight batch state of its own beyond the batch list already passed into `score_confidence_batch()`.

## 16. Logging

**Confirmed action-log value: `score_confidence`** (user-approved decision 3 — follows the existing action naming convention, e.g. `classify`, `extract_metadata`, `detect_duplicates_and_versions`, `suggest_naming_and_destination`; no longer a proposal). Per-file `details` (finalized at implementation time, per `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`'s own update process, not by this design document alone — but committed to be added to that schema doc in the *same* release cycle Module 06 ships, per `ENGINEERING_STANDARD.md` §10's explicit rule, avoiding a third recurrence of the classify/extract_metadata documentation-gap class):

- `confidence_score` (int, mirrors the persisted field)
- `confidence_breakdown` (dict, mirrors the persisted field — logged in full, not just referenced, so the action log alone is enough to audit a historical score without needing the current metadata record)
- `tier` (string, mirrors the persisted field)
- `hard_floors_applied` (list of strings drawn only from §13's four "Log identifier" values — `unknown_category`, `fuzzy_duplicate`, `multi_document_detected`, `locked_file` — e.g. `["unknown_category"]`, or `[]` when none applied) — confirmed (user-approved decision 4), new log-only detail, not persisted on `FileRecord` itself, so a reviewer can see *why* the tier is stricter than the raw score alone would suggest without re-deriving it by hand.

  **Data flow (user-approved fix M1):** this list is never independently recomputed. It is exactly the second element of the tuple `apply_hard_floors(record, tier)` returns (§9, §11 step 5) — the same single walk over §13's table that decides the tier clamp also produces this list, so the logged value and the tier decision can never drift apart from one another.

  **Definition of "applied" (resolves the user's phrase "every hard floor that affected the final confidence score" against Rules/Confidence Rules.md's actual formula):** a hard floor's *trigger condition* is evaluated against the record's fields (§13) independently of the arithmetic score. `hard_floors_applied` lists every hard floor whose trigger condition was true for this record, regardless of whether that hard floor's tier ceiling was actually stricter than the tier the arithmetic score alone would have produced. This is a deliberate choice: hard floors constrain `tier`, never `confidence_score` itself (Rules/Confidence Rules.md — the score is always the pure arithmetic result; hard floors are a second, independent step applied after scoring, per §11 step 5/§13). Listing every *triggered* floor rather than only every floor that *changed the outcome* keeps the log line reproducible from the record's own fields alone (a reviewer can re-check each trigger condition directly) and avoids a second, hidden "did this floor matter" computation that itself would need auditing. If a record triggers more than one hard floor, all are listed, in §13's table row order (per §9's `apply_hard_floors()` description) — e.g. a fuzzy-matched file that is also locked records `["fuzzy_duplicate", "locked_file"]` (fuzzy match is §13's second row, locked/unreadable its fourth), never the reverse — the persisted `tier` reflects the strictest (lowest) ceiling among them, per §13's tie-break rule.

  **One identifier per hard floor, always (user-approved fix M2):** §13's table has exactly four rows and four identifiers, one apiece — "Unknown category" is the only row that also implements a second business-rule name ("Corrupted file," per §2.4), and it is logged as `unknown_category` alone, never as `unknown_category` and a second `corrupted_file` entry together. There is no case in this design where two different `hard_floors_applied` strings are logged for what is, on the record's actual fields, one and the same trigger.

- `processing_time_ms` (int, mirrors every prior module's log entry)

No `fallback_used`/`fallback_reason`/`provider_metadata` keys — Module 06 has no Provider (§2) and no fallback path in the Module 02/03 sense (a record either has all the signals it needs, per §11's eligibility filter, or it isn't eligible yet — there is no "provider unavailable" case to report).

## 17. Performance expectations

No new O(N×M) concern beyond the one every module since Module 02 already discloses (`save_file_record()`'s full-store read-modify-write per file, `ARCHITECTURE_DECISIONS.md` decision 11) — Module 06's own per-file work (a fixed number of field reads, a handful of arithmetic operations, one dict lookup for the tier band) is O(1) per file relative to batch size, and does not even require the one within-batch dict lookup Module 05's collision detection needs — Module 06 is, if anything, cheaper per file than any module built so far, since it reads no file content and performs no string manipulation. No new measured performance number is claimed by this design document itself (design phase, no code yet) — a real measurement against `Tests/Large Batch/` or equivalent is required at implementation/release, per `ENGINEERING_STANDARD.md` §21, following the same disclosed-until-measured pattern Module 05's own design used for itself (§20 of that document).

## 18. Failure handling

Same two-layer discipline as every earlier module (`ENGINEERING_STANDARD.md` §13, `ARCHITECTURE_DECISIONS.md` decision 18):

- **Engine-level (anticipated failures):** if a record's `classification_signals`, `duplicate_signals`, or `naming_signals` is unexpectedly `None` despite the eligibility filter's guarantees (a defensive check against an upstream contract violation that should never happen if Modules 02/04/05 hold their own guarantees, but is not assumed impossible) — treat the missing signals object as its own default "nothing unusual" instance (`ClassificationSignals()`, `DuplicateSignals()`, `NamingSignals()`), matching every one of those classes' own "always fully populated, defaults to nothing-unusual" contract, rather than raising. This degrades gracefully to "no deductions from that signal source" instead of crashing the whole record's scoring.
- **Batch-orchestration-level (unanticipated failures):** `score_confidence_batch()` wraps each record's `ConfidenceEngine` call in a try/except last-resort safety net, exactly like every prior module — an `error` action-log entry, and processing continues to the next file rather than aborting the batch.

Module 06's failure surface is narrower than any judgment-dependent module's: with no Provider, there is no "provider unavailable"/"provider exception"/"invalid response" fallback class to handle at all (§16's log shape reflects this — no `fallback_used`/`fallback_reason` keys). The only realistic anticipated failure is the defensive signals-object check above; everything else falls to the generic outer safety net.

## 19. Dependencies — every field Module 06 reads, traced to its owning module's explicit contract guarantee

| Field | Owning module | Guaranteed by (`MODULE_CONTRACT.md`) |
|---|---|---|
| `status` | 01 | "Guarantees" — `status` (`"discovered"` \| `"unreadable"`) |
| `file_id`, `discovered_at` | 01 | "Guarantees" — both always populated |
| `category` | 02 | "Guarantees" — always a `Category` member for a processed record |
| `classification_signals` | 02 | "Guarantees" — always a full instance, never partially filled |
| `extracted_metadata` | 03 | "Guarantees" — exactly one key per taxonomy field, real value or honest `null` |
| `duplicate_signals` | 04 | "Guarantees" — always a full instance, never partially filled |
| `suggested_name` | 05 | "Guarantees" — non-empty string once processed (used only for eligibility filtering, §11 — not read for its content) |
| `naming_signals` | 05 | "Guarantees" — always a full instance, never partially filled |

Every field above traces to an explicit, currently-frozen guarantee — none is an inferred or "usually true" assumption (`ENGINEERING_STANDARD.md` §2's own required cross-check, performed here at design time specifically so `Governance/PIPELINE_CONTRACT_VERIFICATION.md` check 2 has nothing new to find at release). No field is read from any module's private, non-contract internals except the one deliberate, disclosed exception in §10 (a cross-check *test* reading `metadata.py`'s real constants, never production code).

**Rule-document dependency:** `Rules/Confidence Rules.md` (the formula, every deduction value, every hard floor, and the tier bands — all owned by the project owner, not by this design; this design maps them to fields, it does not restate or reinterpret their values). `Build-out/03 Metadata Extraction/Module 03 Design.md` §7 (the required/optional taxonomy, per §10's independent-table decision).

## 20. Security considerations

The narrowest attack surface of any module built so far:
- **No file-content read of any kind.** Module 06 never opens a file, never reads bytes, never reads text — narrower even than Module 05 (which builds path strings, though also reads no content) and Module 04 (which reads raw bytes for hashing).
- **No filesystem write, no filesystem read.** Module 06 produces only an `int`, a `dict[str, int]`, and a `str` — no path string, no filename string, so there is no path-injection surface to defend at all (unlike Module 05's §19).
- **No new sensitive-value exposure.** Every value Module 06 reads has already passed through Module 03's structural redaction/closed-taxonomy controls (`ARCHITECTURE_DECISIONS.md` decisions 8/9) before Module 06 ever sees it; Module 06 itself never logs or persists a raw metadata *value*, only field *names* (in `confidence_breakdown`'s keys) and booleans/counts — the same "name, never the value" discipline Module 03's own redaction already established for `redacted_fields`.

## 21. Test strategy (committed — a later audit checks the actual test suite against this list, per `ENGINEERING_STANDARD.md` §2)

- **Per-deduction unit tests**, each of the nine rows in §12, both triggered and not-triggered cases, including a record with every deduction simultaneously (to confirm summation, not just single-deduction correctness) and a record with zero applicable deductions (score exactly 100, `confidence_breakdown == {}`).
- **Cap enforcement tests (M3)** for the −30 required-field and −10 optional-field caps — constructed directly (a category with enough missing fields to exceed the cap, even if no *current* category's real taxonomy reaches it, so the cap logic itself is verified independent of today's taxonomy shape) rather than assumed unreachable and left untested. Each test asserts, per §12's "Cap representation" rule: (a) every missing field in the over-the-cap category appears as its own key in `confidence_breakdown` — none are omitted; (b) fields within the cap (in §10's fixed field order) show their full nominal value, and every field beyond the cap shows exactly `0`; (c) `sum(confidence_breakdown.values())` for that category never exceeds the cap; (d) `confidence_score` reflects the true, capped total, confirming `compute_score()`'s unconditional summation and `compute_deductions()`'s own cap enforcement agree exactly.
- **Score-clipping boundary tests** — a record whose raw deduction sum would drive the score below 0, confirming it clips to exactly 0, not a negative number.
- **Tier boundary tests** — scores of exactly 95, 94, 80, and 79, confirming the exact tier cutoffs from §13's table.
- **Each hard floor's own test**, both in isolation and stacked against a case where the raw score alone would have produced a *better* tier than the floor allows — confirming the floor actually overrides the arithmetic, not merely agrees with it by coincidence. Each such test also asserts `apply_hard_floors()`'s returned `hard_floors_applied` list contains exactly that floor's §13 identifier, and a stacked-floor case (e.g. locked + fuzzy match) asserts both identifiers are present and no others (M1).
- **`Category.UNKNOWN` end-to-end test** — confirms zero required/optional-field deductions (no taxonomy entry) but `tier == "review_required"` regardless, via the hard floor alone, and asserts `hard_floors_applied == ["unknown_category"]` exactly — never `["unknown_category", "corrupted_file"]` or any other second entry for the same trigger (M2).
- **`hard_floors_applied`/tier consistency test (M1)**, including a case where a triggered floor does *not* change the outcome (e.g. a fuzzy-match record whose arithmetic tier is already `review_required`, stricter than the fuzzy-match floor's own `approval_required` minimum) — confirms `fuzzy_duplicate` still appears in `hard_floors_applied` per §16's "trigger condition true, regardless of whether it changed the outcome" definition, and confirms the returned tier always equals the incoming tier clamped by the minimum of every floor listed (never a stricter or looser value than the list's own floors imply), so the tuple's two elements can never disagree with each other.
- **§10's taxonomy cross-check regression test** — Module 06's own required/optional field table compared field-by-field against `src/pipeline/metadata.py`'s real `REQUIRED_FIELDS`/`OPTIONAL_FIELDS`, the same drift-guard class already established for `Rules/Confidence Rules.md`'s own citation test.
- **Module Contract immutability test** — every non-owned `FileRecord` field byte-identical before/after, built exhaustively from the start (§8).
- **Deterministic batch-order test** — same batch, reversed input order, byte-identical `confidence_score`/`confidence_breakdown`/`tier` for every record (confirming §7's claim that order doesn't affect output value, not just that it doesn't crash).
- **Defensive signals-object test** (§18) — a record constructed with `classification_signals`/`duplicate_signals`/`naming_signals` left `None` despite passing the eligibility filter, confirming graceful degradation to "no deductions from that source" rather than a crash.
- **Action-log shape test** — confirms the `score_confidence` entry's `details` matches §16's confirmed shape exactly.
- **Eligibility filter tests** — a `status == "unreadable"` record, a `category is None` record, and a `suggested_name is None` record are each confirmed to be excluded from the batch (never scored), plus a record that's already been scored once (`confidence_score is not None`) is confirmed excluded from a second run (idempotency, mirroring `suggest_naming()`'s CLI-level idempotency check, §11's own re-run filter).

Integration Test Plan and UAT Plan are out of scope for this design document — they are their own later-stage deliverables, per `ENGINEERING_STANDARD.md` §6.2/§6.3, produced only after implementation and its own independent audit.

## 22. Risks

- **Weight-tuning friction.** `Rules/Confidence Rules.md`'s own "Tuning note" explicitly anticipates the deduction values changing after real batches are observed. If `confidence.py` hardcodes deduction values as scattered inline magic numbers rather than named constants at the top of the module (mirroring `Rules/Naming Rules.md`'s values being centralized in `naming.py`'s own template tables), a future tuning pass becomes riskier and harder to audit than it needs to be. Mitigation: every deduction value and hard-floor mapping lives in one small, clearly-named constants block, cross-referenced by a comment pointing at the exact `Rules/Confidence Rules.md` line it mirrors.
- **Silent scope creep into Module 07's territory.** Because `tier == "review_required"` conceptually implies "don't move this file," there's a real temptation to have Module 06 itself skip writing `suggested_destination`-adjacent behavior or otherwise start enforcing the "leave in place" rule. This is explicitly out of scope (§4) — Module 06 computes and stores `tier` only; Module 07 is solely responsible for reading it and deciding not to move a file, the same deferred-gate pattern Module 05's own design already established for itself regarding `tier` (`Module 05 Design.md` §8).
- **Downstream amplification of a scoring defect.** Module 06 is the last "should we trust this?" checkpoint before Module 07 starts actually moving/renaming real files. A defect here (an incorrectly *lenient* score routing something to `auto` that should have been `review_required`) has a materially worse real-world consequence than an equivalent defect in an earlier, purely-advisory module — this argues for holding Module 06's test rigor to at least the same standard as Module 04/05's, not a lighter one just because the arithmetic itself is simple. Mitigation: the hard-floor-stacking test (§21) specifically targets the highest-consequence failure mode (a hard floor silently failing to override a good score).
- **Taxonomy duplication drift** (§10) — mitigated by the committed cross-check regression test, but only as strong as that test actually being run in CI/at every release, per `ENGINEERING_STANDARD.md` §19's standing regression policy.
- **Corrupted-file detection gap, inherited from Modules 02/03 (disclosed, not fixable within Module 06 — see §2.4/§13).** The "Unknown category" hard floor fully and correctly covers a corrupted file in any of the 7 judgment-dependent categories (Invoice, Resume, Bank Statement, Contract, Document, Image, Screenshot) and degrades gracefully (an ordinary −8 missing-field deduction, not a hard floor) for Archive/Audio. For Application and Video, category is parsed from the filename string alone (`_parse_application_filename()`/`_parse_video_filename()`, both documented "never raise," per `src/pipeline/classification.py`) — file content is never opened or validated, so a corrupted Application or Video file is completely undetectable as corrupted anywhere in the current pipeline and will not trigger any hard floor. Impact: a corrupted `.zip` misnamed with a video extension, or a genuinely corrupted video/application file, can still reach `auto`/`approval_required` tiers on Module 06's arithmetic alone. This is a real, disclosed limitation of the *inherited* upstream signal set, not a defect in Module 06's own logic — Module 06 was explicitly instructed (user-approved decision 2) not to introduce a new corruption signal or duplicate existing state, and closing this gap would require changing an already-frozen Module 02 or 03 contract via the Frozen Module Change Policy, which is out of scope for Module 06's design. Carried forward to Module 06's own `KNOWN_LIMITATIONS.md` at release time.

## 23. Open architectural decisions

None remain open. All 4 items previously listed here were resolved by the user's decisions (approved this design cycle) and are now recorded in §24 (see the "Corrupted file hard floor," "Action-log value," "`hard_floors_applied` is logged," and "`classification_signals.locked`" bullets respectively), with the reasoning applied at each cross-referenced section:

1. ~~§2.4 — "Corrupted file" hard floor mapping.~~ Resolved — see §24's "Corrupted file hard floor" bullet, with the full per-category-family analysis in §2.4 and the resulting disclosed gap recorded in §22.
2. ~~§16 — action-log value name, `score_confidence`.~~ Resolved — see §24's "Action-log value" bullet, applied in §16.
3. ~~§16 — whether `hard_floors_applied` should be logged.~~ Resolved — see §24's "`hard_floors_applied` is logged" bullet, applied in §16 (including the precise definition of "applied").
4. ~~§11/§13 — whether `classification_signals.locked` alone covers the "Locked / unreadable file" hard floor.~~ Resolved — see §24's "`classification_signals.locked`" bullet, with the full citation-backed argument in new §13A and applied in §13.

## 24. Confirmed architectural decisions (resolved by this design, not open)

For a reviewer's quick reference — everything below was reasoned through explicitly in this document and is not awaiting further confirmation, only independent review per `ENGINEERING_STANDARD.md` §3:

- Fully deterministic, no Provider, no Engine/Provider split (§2).
- Two-layer architecture (`score_confidence_batch()` → `ConfidenceEngine`), not code-shared with any sibling module (§9).
- Required/optional field taxonomy independently defined in `confidence.py`, cross-checked by a dedicated regression test against `metadata.py`'s real constants — never imported directly (§10).
- No new `Database/` structures (§14); no `Runtime/Reports/` output (§15).
- Per-record eligibility filter (§11 step 1): `status == "discovered" and category is not None and suggested_name is not None`. `confidence_score is None` is a separate, CLI-level re-run/idempotency filter (mirroring `suggest_naming()`'s own CLI-level idempotency check), not part of the per-record eligibility filter itself (§11, §21).
- No disclosed side effect on any record other than the one being scored (§7).
- `confidence_breakdown == {}` is a valid, honest "scored, nothing deducted" state, distinguished from "not yet scored" via `confidence_score is None`, not via the breakdown's emptiness (§7).
- **"Corrupted file" hard floor is implemented as `category == Category.UNKNOWN`, and only that — no new signal introduced.** Complete and correct for the 7 judgment-dependent categories; a disclosed, inherited gap for Archive/Audio (degrades to a −8 deduction) and Application/Video (completely undetectable). Closing the gap would require a Frozen Module Change Policy action against Module 02/03, out of scope here (§2.4, §13, §22 — user-approved decision 2).
- **Action-log value: `score_confidence`**, following the existing `classify`/`extract_metadata`/`detect_duplicates_and_versions`/`suggest_naming_and_destination` naming convention (§16 — user-approved decision 3).
- **`hard_floors_applied` is logged**, listing every hard floor whose trigger condition was true for the record (independent of whether it changed the outcome), never a hidden "did this matter" computation (§16 — user-approved decision 4).
- **`classification_signals.locked` alone fully covers the "Locked / unreadable file" hard floor.** `status == "unreadable"` records never reach Module 06 (excluded by §11's eligibility filter, per Module 02's `MODULE_CONTRACT.md` INPUT-section guarantee); the only case the hard floor protects against — a readable-but-password-protected file — is exactly what `classification_signals.locked` reports. No new state is inferred (§13A, §13 — user-approved decision 5).
- **`apply_hard_floors(record, tier)` returns `(new_tier, hard_floors_applied)`, one walk producing both.** The tier-clamping decision and the `hard_floors_applied` log list are two views of the exact same pass over §13's table, computed once, never derived separately — closes the internal-architecture/logging-requirement gap the first Design Review's M1 finding identified (§9, §11 step 5, §16 — user-approved fix M1).
- **"Unknown category" and "Corrupted file" are one hard floor, not two.** §13's table has four rows, four triggers, four log identifiers — `Rules/Confidence Rules.md`'s two rule *names* that share an identical, indistinguishable trigger (`category == Category.UNKNOWN`) are logged under one identifier, `unknown_category`, never as two separate `hard_floors_applied` entries for the same underlying fact — closes the first Design Review's M2 finding (§2.4's corollary, §13, §16 — user-approved fix M2).
- **The −30/−10 deduction caps are enforced inside `compute_deductions()`, per category, in §10's fixed field order, before it returns.** Fields within the cap are recorded at their full nominal value; every field beyond the cap is still recorded — never hidden — at a value of `0`, so `confidence_breakdown` always lists every genuinely missing field while its sum never exceeds the cap and `compute_score()`'s unconditional `100 + sum(deductions.values())` stays exact. No deduction value or cap threshold changed — only the previously-unspecified mechanics of applying them, now with exactly one possible interpretation — closes the second Design Review's M3 finding (§9, §12's "Cap representation" note, §21 — user-approved fix M3).
- **`compute_score(deductions) -> int` is `100 + sum(deductions.values())`, not `100 - sum(deductions.values())`.** Every stored deduction value is already negative (§12), matching `Rules/Confidence Rules.md`'s own worked example (`100 + (-8) + (-10) = 82`) — post-freeze correction, implementation-discovered (§9, §11 step 3, §12; see `Module 06 Design Review.md`'s "Post-freeze correction" section).
