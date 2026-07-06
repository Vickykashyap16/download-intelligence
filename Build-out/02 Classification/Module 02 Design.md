# Module 02 (Classification) — Design & Architecture

**Status: DRAFT v2 — refinements applied, pending final freeze. Design only. No implementation code exists or has been written for this module.**

This document is the complete pre-implementation design for Module 02, produced with the same engineering process used for Module 01 (design → formal review → refinement → explicit approval → freeze → only then implement). Section 26 (Final Architecture Validation) is the second review pass — it checks the round-one review's findings against the changes applied below and looks for anything new, rather than re-listing unapplied recommendations from scratch.

Living business rules (the actual category list, heuristics, and edge cases) stay in `Rules/Classification Rules.md` and `Rules/Confidence Rules.md`, exactly as established for Module 01 — this document describes the *architecture around* those rules, not the rules themselves.

---

## 1. Purpose

Turn each file Module 01 discovered into exactly one `category` from the fixed v1 taxonomy, plus a small set of raw, honest, strongly-typed signals about *how confident that classification is* — for Module 06 to turn into a score later. Nothing else. Module 02 does not extract structured fields, does not compare files to each other, does not name or move anything, and does not decide how much to trust its own output (it reports signals; scoring is Module 06's job).

## 2. Responsibilities

Module 02 is now understood as three layers, from batch-level down to raw classification (see §6 and §25 for the full split):

- **Module 02 itself** — batch orchestration: filtering, persistence, logging, per-file failure containment.
- **`ClassificationEngine`** (new, §25) — per-file decision-making: which mode to use, whether to call a provider, how to validate what comes back, and what to do if it can't be trusted.
- **`ClassificationProvider`** (renamed from `ClassifierProvider`, see §26 item 6 resolved) — performs classification only, nothing else.

**Belongs to Module 02 (across all three layers):**
- Run the deterministic extension/MIME cheap pass (`Rules/Classification Rules.md` Pass 1).
- Run the deterministic Screenshot-vs-Image split for image files.
- Extract text from text-bearing files (delegating to `core/pdf.py`/`core/text.py`) and route it to the `ClassificationEngine` for a judgment-mode decision when a deterministic answer isn't possible.
- Render a scanned/no-text PDF's first page and route it to the Engine in vision mode when text extraction yields nothing.
- Detect password-protected/encrypted files (deterministic, via the PDF library's own exception) and detect non-English content (deterministic, via `core/text.py`'s planned language detection).
- Assign exactly one `category` (a `Category` enum member, §14) to every file it processes — never leave it ambiguous or blank for a file it attempted.
- Produce a `ClassificationSignals` object (§14) — the raw, strongly-typed flags Module 06's formula needs.
- Apply the fallback strategy (§11) when a provider is unavailable or returns something untrustworthy — this is the Engine's decision, never the provider's.
- Persist `category` + `classification_signals` via the existing, unmodified `storage/database.py`.
- Append a `classify` action-log entry per file, including mode/provider/timing metadata (§12).
- Never call a specific AI provider directly from Module 02's own code — only through `ClassificationEngine`, which in turn only calls the abstract `ClassificationProvider` (§25).

**MUST NOT be implemented until later modules (feature creep to explicitly avoid):**
- **Metadata Extraction** — pulling vendor/invoice number/amounts/dates/etc. out of the file. Module 03.
- **Duplicate Detection** — comparing `content_hash`/perceptual hash across files, version-chain logic. Module 04.
- **Naming** — generating `suggested_name`. Module 05.
- **Destination Selection** — generating `suggested_destination`. Module 05.
- **Confidence scoring** — computing `confidence_score`/`confidence_breakdown`/`tier` from the signals. Module 06.
- **Execution** — moving, renaming, or staging any file; approvals. Module 07.
- **Reporting** — writing to `Runtime/Reports/*`. Module 08 (Module 02 only writes to `Runtime/Logs/action_log.jsonl`, same as Module 01).

## 3. Inputs

- One `FileRecord` per file from Module 01, restricted to `status == "discovered"` (see §11 for why `"unreadable"` records are excluded, not force-classified).
- The physical file at `current_path`.
- `Rules/Classification Rules.md` — implemented directly in code, no generated config (same convention Module 01 established for `Rules/Ignore Rules.md`).
- Which `ClassificationProvider` is active (§25) — a simple default in v1, not a full config system (see §24).

## 4. Outputs

- `category` — a `Category` enum member (§14), set for every processed record.
- `classification_signals` — a `ClassificationSignals` object (§14), always present, never omitted, even when every signal is at its default (false/null).
- One `classify` action-log entry per file, now carrying mode, provider metadata, and timing (§12) in addition to category/signals.
- `List[FileRecord]`, same records, enriched — returned for Module 03 to consume next, mirroring Module 01's `build_ingest_queue()` return-list pattern.

## 5. Module Contract

*(Same template as `Release/Module01/MODULE_CONTRACT.md`. The internal Module 02 → Engine → Provider layering below is an implementation detail — it does not change this contract's INPUT/OUTPUT surface with the rest of the pipeline.)*

**INPUT — Receives:** `List[FileRecord]` from Module 01, filtered to `status == "discovered"`.

**OUTPUT — Produces:** `List[FileRecord]` (same records, enriched).

**Guarantees:**
- `category` is always a valid `Category` enum member for every record Module 02 processes — never left `None`.
- `classification_signals` is always a `ClassificationSignals` instance (never a bare dict, never missing) on every record Module 02 processes.

**DOES NOT MODIFY:**
- **Metadata Extraction (Module 03)** — `extracted_metadata`
- **Naming & Destination (Module 05)** — `suggested_name`, `suggested_destination`
- **Duplicate & Version Detection (Module 04)** — `duplicate_of`, `version_group_id`, `version_rank`
- **Confidence & Review (Module 06)** — `confidence_score`, `confidence_breakdown`, `tier`
- **Preview, Approval & Execution (Module 07)** — `processed_at`, `approved_by`, `approved_at`, `reversible`
- **Logging & Reporting (Module 08)** — `Runtime/Reports/*`
- **Module 01's own fields** — `file_id`, `source_id`, `original_name`, `original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`, `modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `batch_id` — read-only for Module 02.

## 6. Internal Workflow

Three layers now, not two:

```
Module 02 (batch orchestration)
      │  per FileRecord with status == "discovered"
      ▼
ClassificationEngine (per-file decision-making)
      │  decides: deterministic? AI-assisted? fallback?
      ▼
ClassificationProvider (raw classification call only)
```

1. **Module 02:** filters to `status == "discovered"`; passes every other record through untouched.
2. **Module 02** hands each remaining record to `ClassificationEngine.classify_file(record)`.
3. **Engine — cheap pass (deterministic):** extension/MIME lookup. If it yields a definitive category on its own, done — no deep pass, no provider call, mode = `"deterministic"`, `classification_signals` stays all-default.
4. **Engine — image split (deterministic):** for image-family extensions, runs the Screenshot-vs-Image heuristic (`core/images.py` + `core/exif.py`). Done — mode = `"deterministic"`, no provider call.
5. **Engine — text-bearing files:** attempts text extraction (`core/pdf.py`/`core/text.py`).
   - Text extracted → Engine builds a `ClassificationRequest` (mode: `"text"`) → calls the configured `ClassificationProvider.classify()` → receives a `ProviderResponse` → **Engine validates it** (§11) → on success, sets `category` and folds `ambiguous`/`multi_document_detected` into `ClassificationSignals`.
   - No extractable text → Engine renders the first page as an image → builds a `ClassificationRequest` (mode: `"vision"`) → same provider call and validation.
   - Extraction fails entirely (encrypted/locked) → Engine sets `category = Category.UNKNOWN`, `classification_signals.locked = True`, no provider call needed.
6. **Engine — deterministic signal checks**, run alongside step 5 for text-bearing files regardless of provider outcome: non-English detection (`core/text.py`) → `non_english_detected`/`detected_language`; no-extractable-text case sets `no_extractable_text = True` directly.
7. **Engine — provider unavailable / invalid response:** Engine applies the fallback strategy (§11) — never Module 02, never the provider itself.
8. Anything not matched anywhere above (extension recognized by Module 01 but absent from `Rules/Classification Rules.md`'s Pass 1 table) → `category = Category.UNKNOWN`, no signals set.
9. **Module 02:** persists the record (`save_file_record()`, unchanged from Module 01) and appends the `classify` action-log entry (§12), using the mode/timing/provider metadata the Engine returns alongside the classification itself.
10. **Module 02:** continues to the next record; any single-record failure at any layer is caught, logged, and never aborts the batch (same resilience pattern as `scan_source()`).

## 7. Classification Strategy

Cheap-first, tiered escalation: extension → deterministic image split → AI-assisted deep pass only when a deterministic answer isn't possible. Fallback ladder for the deep pass: specific business category → generic Document → Unknown — Document is the fallback *before* Unknown, never after. The full heuristics and category definitions are `Rules/Classification Rules.md`'s job, not restated here — the workflow above (§6) deliberately describes shape, not category names, keeping this separation clean (this trims the round-one review's item 2; see §26).

## 8. AI vs. Deterministic Responsibilities

| Responsibility | Deterministic | Judgment (via `ClassificationEngine` → `ClassificationProvider`) | Decided by |
|---|---|---|---|
| Extension/MIME cheap pass | ✅ | | Engine |
| Screenshot vs. Image split | ✅ | | Engine |
| Locked/encrypted detection | ✅ (library exception) | | Engine |
| Non-English detection | ✅ (`core/text.py`) | | Engine |
| Invoice/Resume/Bank Statement/Contract/Document/Unknown from text or image | | ✅ | Provider (Engine validates) |
| Ambiguity flag | | ✅ | Provider (Engine validates) |
| Multi-document flag | | ✅ (v1 — see §24) | Provider (Engine validates) |
| Mode selection (deterministic/text/vision) | — | — | **Engine only** |
| Fallback on provider failure/invalid response | — | — | **Engine only** |

The Provider never decides mode or fallback — it only answers the specific classification question it's asked, in the mode it's asked to answer it in. See §25.

## 9. Confidence Calculation

**Module 02 does not compute `confidence_score`, `confidence_breakdown`, or `tier`.** That remains fully owned by Module 06, per `Rules/Confidence Rules.md`'s explicit single-source-of-truth principle. Module 02's only obligation toward confidence is to emit an accurate `ClassificationSignals` object — the raw material for Module 06's classification-related deductions. See §23-B for why this split is preferred over letting Module 02 pre-compute a partial score.

## 10. Rules Interaction

`Rules/Classification Rules.md` is implemented directly in code — no YAML mirror, same convention established for `Rules/Ignore Rules.md`. When the rules change, only the rules doc and the code implementing it change; this architecture doc shouldn't need to. `Rules/Confidence Rules.md`'s deduction table is the reference for exactly which `ClassificationSignals` fields Module 02 must supply — the two rule docs and this module's contract are meant to be read together. The fixed `Category` enum (§14) is a typed mirror of `Rules/Classification Rules.md`'s category list — if the rules doc's list changes, the enum is updated by hand; the rules doc remains the source of truth for what the list *is*, the enum is just how code represents it safely.

## 11. Error Handling & Fallback Strategy

**General:** single-record failures at any layer never abort the batch — caught, logged, continue, same pattern as Module 01.

**Unreadable-vs-Unknown distinction (unchanged from round one):** files Module 01 already marked `status == "unreadable"` are passed through without a classification attempt — `category` stays `None`. This is deliberately distinct from `Category.UNKNOWN`: `UNKNOWN` means "we tried to classify a readable file and found no match"; an untouched `None` means "we never had readable bytes to try."

**Explicit fallback strategy (new, replaces the round-one "no automatic retry" aside with a full design):**

The `ClassificationEngine` — never the provider, never Module 02 — owns this decision entirely.

1. **Validation, every time:** every `ProviderResponse` is validated before being trusted: `category` must map to a real `Category` enum member; `ambiguous`/`multi_document_detected` must be actual booleans. A provider is expected to return `ClassificationResult.category` as a plain string (providers stay loosely typed at the boundary — see §25) — the Engine is what converts/validates that string into the internal `Category` enum, and it is the Engine's job, not the provider's, to reject anything that doesn't match.
2. **Failure modes recognized**, each with a distinct `fallback_reason` for logging (§12) — though v1 handles all three identically:
   - `"provider_unavailable"` — the provider couldn't be reached/invoked at all (meaningful for future network providers; not a real case for v1's `ClaudeLiveClassifier`, which is always "available" by construction).
   - `"invalid_response"` — the provider answered, but validation (step 1) failed.
   - `"provider_exception"` — the provider call raised.
3. **v1 fallback behavior (uniform across all three):** no retry. Fall straight to `category = Category.UNKNOWN`. Record `fallback_used = True` and the specific `fallback_reason` in the action-log entry's `details` — **not** in `ClassificationSignals`, because this is a fact about the classification *process*, not a fact about the file's content (kept symmetric with the file-content-only nature of `ClassificationSignals`).
4. **No new Confidence Rules.md deduction/hard-floor is needed for provider failure** — `Category.UNKNOWN` already forces `review_required` via the existing hard floor. Provider failure rides the same, already-approved path.
5. **No secondary-provider fallback chain in v1** — with exactly one provider (`ClaudeLiveClassifier`) actually implemented, there is nothing to fall back *to* except Unknown. The Engine's fallback step is designed to be extensible to a future provider chain (e.g. try a `RuleBasedClassifier` before giving up), but that chain is explicitly a Version 2+ enhancement, not built now (see §24).

**Other existing edge cases (unchanged):** password-protected/encrypted files → `Category.UNKNOWN`, `classification_signals.locked = True`, per `Rules/Classification Rules.md`'s existing edge case. Never crash the run on one bad file.

## 12. Logging

Extended action-log `classify` entry (extends the same extensible vocabulary Module 01 added `"discover"` to):

```json
{
  "batch_id": "...",
  "file_id": "...",
  "action": "classify",
  "from": "current_path",
  "to": null,
  "details": {
    "category": "Invoice",
    "signals": { "ambiguous": false, "multi_document_detected": false,
                 "no_extractable_text": false, "non_english_detected": false,
                 "detected_language": null, "locked": false },
    "mode": "text",
    "processing_time_ms": 842,
    "provider_metadata": {
      "provider_name": "claude_live",
      "model": "claude-sonnet-5",
      "provider_version": null,
      "latency_ms": 810,
      "reasoning": null
    },
    "fallback_used": false,
    "fallback_reason": null
  }
}
```

- `mode` — `"deterministic"` | `"text"` | `"vision"` — which path this file took (§6/§8).
- `processing_time_ms` — the Engine's own end-to-end timer for classifying this one file, always present regardless of mode.
- `provider_metadata` — present only when a provider was actually called (`null`/omitted for `mode: "deterministic"`); see §25 for the full shape and who measures `latency_ms`.
- `fallback_used`/`fallback_reason` — present and `false`/`null` in the normal case; populated per §11 when the fallback path was taken.
- **Privacy note (new — see §17):** if a provider's `reasoning` metadata is ever populated by a future provider, it must not echo raw sensitive file content (e.g. account numbers) into this log line — treat it with the same discipline `Build-out/03 Metadata Extraction.md` already requires for bank statement fields.
- No `Runtime/Reports/*` writing — Module 08's job, out of scope here (see Module Contract, §5).
- When Module 02 gets a CLI entry point, it should print a per-category summary plus mode/provider/timing rollups (e.g. "7 classified via text (avg 810ms, claude_live), 3 via deterministic pass, 1 via vision fallback, 0 fallbacks") — designed now, matching Module 01's UAT-driven CLI-summary pattern, implemented when Module 02 is actually built.

## 13. Database Changes (if required)

None beyond the new `FileRecord` field (§14) and its typed sub-model. `Database/Metadata/metadata_store.json`, `save_file_record()`, and `load_metadata_store()` are reused exactly as Module 01 built them — no new storage functions needed. `Database/FileIndex/`, `Database/History/`, and `Database/Learning/` remain untouched (Module 04/07 territory).

**Typed-field (de)serialization note (new):** `metadata_store.json` is plain JSON; `Category` (a `str`-mixin enum) and `ClassificationSignals` (a dataclass) both need a small, explicit reconstruction step on load that Module 01's simpler fields never needed:
- `Category(str, Enum)` members serialize automatically via `json.dumps` (they *are* string instances), but `load_metadata_store()`'s current `FileRecord(**raw_record)` reconstruction would hand back a plain `str`, not a `Category` member, unless the loader explicitly does `Category(raw_record["category"])` when not `None`.
- `ClassificationSignals` is a nested dataclass; `dataclasses.asdict()` (used by `_write_metadata_store()`) already flattens it to a plain dict correctly on write, but the loader needs `ClassificationSignals(**raw_record["classification_signals"])` (when present) to turn it back into an instance on read, rather than leaving a bare dict.
This is a real but small addition to `storage/database.py`'s load path when Module 02 is implemented — flagged here so it isn't missed, not applied now (no code is being touched in this design phase).

## 14. FileRecord Changes (if required)

**Two new/changed pieces are required — proposed here, not yet applied to `src/models/file_record.py`:**

**a) `Category` — a strongly-typed enum, replacing the plain `str` originally proposed:**
```
class Category(str, Enum):
    INVOICE = "Invoice"
    RESUME = "Resume"
    BANK_STATEMENT = "Bank Statement"
    CONTRACT = "Contract"
    DOCUMENT = "Document"
    IMAGE = "Image"
    SCREENSHOT = "Screenshot"
    APPLICATION = "Application"
    ARCHIVE = "Archive"
    VIDEO = "Video"
    AUDIO = "Audio"
    UNKNOWN = "Unknown"
```
`str, Enum` (not a plain `Enum`, and not `enum.StrEnum`, which is Python 3.11+ only — this project's sandbox runs 3.10) is chosen specifically so members serialize to JSON automatically as their string value, with no custom encoder needed — `json.dumps` treats a `Category` member as the string it already is.

`FileRecord.category` becomes `Optional[Category]` (was `Optional[str]`).

**b) `ClassificationSignals` — a dedicated model, replacing the plain dict originally proposed:**
```
@dataclass
class ClassificationSignals:
    ambiguous: bool = False
    multi_document_detected: bool = False
    no_extractable_text: bool = False
    non_english_detected: bool = False
    detected_language: Optional[str] = None
    locked: bool = False
```
`FileRecord.classification_signals` becomes `Optional[ClassificationSignals]` (was `dict`).

**Why strongly-typed here but `confidence_breakdown`/`extracted_metadata` stay dicts:** this is a deliberate asymmetry, not an oversight. `classification_signals` has a small, fixed, fully-known-in-advance shape (six named signals, defined once, here) — a dataclass costs nothing and buys real safety. `confidence_breakdown` is genuinely open-ended (an arbitrary, growing list of named deductions, one entry per applicable rule, shape not known in advance). `extracted_metadata` varies *by category* (Invoice's fields aren't Resume's) — a single fixed dataclass can't represent it without a category-keyed union of types, which is a heavier design question Module 03 should own when it's designed, not something to force here.

**Why this is necessary, not scope creep:** unchanged from round one — `Rules/Confidence Rules.md`'s deduction table needs these classification-time signals persisted for Module 06 to read later, and `category` alone can't carry them.

**This is a data-model change and will not be applied until explicitly approved** — consistent with "do not begin implementation."

## 15. Folder Structure Changes (if required)

None. `Build-out/02 Classification/` already exists. No new `Database/`, `Runtime/`, or `core/` subfolders are needed. `ClassificationEngine` and `ClassificationProvider` both live inside `src/pipeline/classification.py`, extending what's already scaffolded there — no new file, no new folder.

## 16. Test Strategy

- **Unit tests:** `classify_by_extension()` for every mapped extension; the Screenshot-vs-Image split against synthetic images; `ClassificationEngine` orchestration exercised with a **fake/stub `ClassificationProvider`** (a test double returning canned `ProviderResponse`s) — this is what makes the Engine's decision logic unit-testable without ever calling a real AI provider.
- **Fallback-specific unit tests (new):** a stub provider that raises an exception, a stub provider that returns an invalid category string, a stub provider that times out (simulated) — each must produce `category = Category.UNKNOWN`, the correct `fallback_reason`, and must not crash the batch.
- **Enum/dataclass validation tests (new):** `Category` rejects an unrecognized string (Engine-level validation, not enum-level — the enum itself just defines valid members); `ClassificationSignals` defaults are all false/null when constructed empty.
- **Integration tests:** real files from the existing `Samples/`/`Tests/` datasets already built for Module 01 — reused, not rebuilt. New Module-02-specific `Tests/` data likely needed: a password-protected PDF, a non-English document, a multi-invoice batch PDF, an ambiguous invoice/receipt.
- **UAT:** same real-end-user pattern as Module 01.
- **Regression:** full suite re-run after every change, same discipline as Module 01.
- **Contract tests:** assert every field outside Module 02's Module Contract guarantees is byte-identical before and after a record passes through Module 02.
- **Serialization round-trip tests (new, following §13):** a `FileRecord` with a real `Category` and `ClassificationSignals` survives a save-then-load cycle through `metadata_store.json` with types intact, not degraded to plain strings/dicts.

## 17. Security Considerations

- Password-protected/encrypted files: never attempt to bypass or brute-force — treat as `Unknown` + `locked`, per existing rules.
- **Provider content exposure:** unchanged from round one — v1's `ClaudeLiveClassifier` makes no network call, no new exposure. A future network-calling provider would send file content/extracted text externally; reviewed against the same privacy discipline as `Build-out/03 Metadata Extraction.md`'s bank-statement rule when that day comes.
- **Provider `reasoning` metadata exposure (new):** the optional free-text `reasoning` field in `ProviderMetadata` (§25) is a new surface that didn't exist in round one — if a future provider populates it with content derived from the file (e.g. quoting a snippet to justify its answer), that text flows into the action log verbatim. This must be treated with the same care as extracted content generally — no raw sensitive fields (account numbers, etc.) should end up there. Not a v1 concern for `ClaudeLiveClassifier` (which can simply leave `reasoning = None`), but a real constraint on any future provider implementation.
- No code-execution risk: text/vision extraction only reads bytes/renders pages, never executes file contents.
- Archive files are classified by extension alone in Pass 1 — no archive-parsing attack surface in this module at all.

## 18. Performance Considerations

- The deterministic passes remain as cheap as Module 01's per-file work.
- The AI deep pass is the expensive step — one provider call per text/vision-needing file. Keeping the extracted-text excerpt small bounds per-call cost/latency.
- **Observability enables future comparison (new, ties to §25's goal):** because every provider call now reports `latency_ms` and every file reports `processing_time_ms`, once a second provider exists these numbers become directly comparable — this was a stated goal of the provider-metadata extension and is worth calling out explicitly as the payoff for that design cost.
- **Known limitation for v1's provider specifically (new):** `latency_ms` is measured by the Engine wrapping the `classify()` call, which is meaningful for any real function-call boundary — but for `ClaudeLiveClassifier`, there isn't a conventional network round-trip to time; the number will reflect whatever wall-clock time the in-session judgment step takes, which may not be a meaningful basis for comparison until a real network-calling provider exists to compare it against. Not a defect, just a limit on what this metric tells you in v1.
- No batching/parallelization in v1 — sequential, matching Module 01's simplicity.

## 19. Known Edge Cases

Pulled from `Rules/Classification Rules.md` plus additions surfaced by this design pass:
- Zero-length extracted text after an apparently successful extraction — treat identically to the no-extractable-text path.
- A file's MIME type disagreeing with its extension — Pass 1 routes by extension only; MIME is supplementary context, never authoritative.
- An extension Module 01 considers supported but `Rules/Classification Rules.md`'s Pass 1 table doesn't map — falls through to `Category.UNKNOWN`; a contract test should catch this drift before it ships.
- A provider returning a syntactically valid but unrecognized category string (e.g. a typo or a category name from a different taxonomy) — caught by the Engine's validation step (§11), routed through the same fallback path as any other invalid response.

## 20. Dependencies on Module 01

Unchanged from round one. Reads (never writes) `current_path`, `extension`, `mime_type`, `size_bytes`, `status`, `file_id`; reuses `storage/database.py`/`storage/runtime_io.py` unchanged; no changes requested of Module 01 itself.

## 21. Dependencies for Later Modules

Unchanged from round one, updated for the typed model:
- **Module 03** depends on `category` (now a `Category` enum) and likely `classification_signals.no_extractable_text`.
- **Module 04** may find `category` useful for scoping comparisons — not a v1 commitment.
- **Module 05** depends on `category` for naming template/destination selection.
- **Module 06** depends on the full `ClassificationSignals` object for its deductions and hard floors.
- **Modules 07/08** have no direct dependency beyond the shared `FileRecord`.

## 22. Risks and Assumptions

| # | Risk / Assumption | Why it exists | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Three-layer split (Module 02 / Engine / Provider) adds structure for exactly one working provider | Requirement explicitly asks for a clean separation so fallback/mode logic never lives in a swappable provider | More classes/files to read for a v1 that only ever exercises one path | Keep the Engine's public surface to one method (`classify_file`); keep the Provider interface to one method (`classify`) — the layering costs two small classes, not a framework |
| 2 | `ClassificationSignals`/`Category` typed-model schema drift | Fixed shape defined once, here | If `Confidence Rules.md`'s deduction table changes to need a new signal, both this doc and the dataclass need updating together | Contract test (§16) asserting every signal `Confidence Rules.md` expects exists on `ClassificationSignals` |
| 3 | Today's "live judgment" provider pattern doesn't map cleanly onto a future network-API provider's retry/timeout/rate-limit needs | v1 assumes Claude is already in-session | Swapping providers later may need more work than "architecturally trivial" | Fallback strategy (§11) is designed provider-agnostically now; retry/timeout/rate-limit handling explicitly deferred to whichever future module implements a network-calling provider |
| 4 | The generous Document fallback could get noisy in practice | Fallback ladder deliberately favors Document over Unknown | `Documents/` could become a dumping ground over time | `Database/Learning/User Corrections.json` + ROADMAP.md Version 3 active learning — not a v1 concern |
| 5 (assumption) | The fixed v1 category list (and its `Category` enum mirror) is assumed stable enough | Taxonomy fixed during Module 01-era design | A new common file type would need both the rules doc and the enum updated together | Flagged, not solved now |
| 6 | Extension-vs-content mismatch isn't specifically handled | Module 02 trusts Module 01's `extension` field | A wrongly-renamed file could be misclassified without reaching the deep pass | Acceptable for v1; revisit if common in practice |
| 7 (new) | `latency_ms` isn't a meaningful comparison metric until a second provider exists | v1 only has `ClaudeLiveClassifier`, which has no real network boundary to time | The observability goal of §25/§18 is only partially realized in v1 | Accepted for v1 — the field exists and is measured consistently now so historical data is available the moment a second provider is added |

## 23. Alternative Architectures

### A. AI integration approach
*(Unchanged from round one — still recommending live in-session judgment for v1, with the Engine/Provider split now making the future swap to Direct API even more mechanical: only a new `ClassificationProvider` implementation is needed, the Engine's fallback/mode logic doesn't change at all.)*

| | Live in-session judgment (recommended) | Direct API integration | Rule-based only |
|---|---|---|---|
| Advantages | Zero API cost/key management, no network dependency | Works unattended, provider-swappable | Zero cost, fully deterministic |
| Disadvantages | Only works with an active Claude session | Needs secrets/network/retry handling | Lower accuracy on nuanced documents |
| Complexity | Low | Medium–high | Low–medium |
| Maintainability | High | Medium | Low over time |
| Scalability | Limited to on-demand/scheduled runs | High (enables Watch Folder) | High speed, low quality ceiling |

### B. Confidence calculation ownership
*(Unchanged — centralized in Module 06, per §9.)*

### C. Classification workflow shape
*(Unchanged — tiered/cheap-first, per §7.)*

### D. Engine/Provider separation (new — directly addresses this round's refinement 6)

| | Engine decides, Provider only classifies (recommended) | Provider owns its own fallback/mode logic | No separate Engine — Module 02 does it all inline |
|---|---|---|---|
| Advantages | Any provider can be swapped in without reimplementing fallback/mode logic; Engine's decision tree is unit-testable in isolation with a stub provider | Slightly fewer classes | Simplest possible file layout |
| Disadvantages | One more class to read | Every new provider must correctly reimplement fallback/retry/mode-selection semantics — high risk of inconsistent behavior across providers | Conflates batch orchestration with per-file decision logic; harder to unit-test the decision tree without also exercising persistence/logging |
| Complexity | Medium | Medium–high (per provider) | Low upfront, higher long-term (orchestration and decision logic tangled) |
| Maintainability | High — one place owns fallback policy | Low — policy duplicated/drifting per provider | Medium — works for one provider, degrades as more are added |
| Scalability | High — new providers are pure plug-ins | Low — new providers inherit the burden of reimplementing policy | Low — adding a second provider means untangling Module 02 first |

**Recommendation: Engine decides, Provider only classifies** — exactly what was requested. This is also what makes §23-A's Direct API alternative cheap to adopt later: a new `ClassificationProvider` subclass is the entire change; fallback and mode-selection policy is already centralized and doesn't need to move.

## 24. Version 1 Scope Validation

Unchanged conclusions from round one, confirmed still correct after this round's refinements:
- Multi-document detection stays provider-sourced (`ClassificationResult.multi_document_detected`), no dedicated structural analysis.
- Non-English detection and locked-file detection stay deterministic, in the Engine, reusing already-scaffolded `core/` modules.
- The Classification Interface (now Engine + Provider, two small pieces instead of one) is still not something to cut — still cheap relative to the value of never having to touch Module 02 to add a provider.
- **New for this round:** no multi-provider fallback chain in v1 (§11) — straight to `Category.UNKNOWN` on any failure. A provider chain is an explicit Version 2+ idea, not built now.

**Smallest V1, updated:** extension cheap pass + deterministic Screenshot/Image split + text deep pass (live judgment via `ClassificationEngine` → `ClaudeLiveClassifier`) + vision deep pass fallback for scanned PDFs + `Category.UNKNOWN` fallback (both for "no match" and for "provider failed") + `ClassificationSignals` limited to the six fields defined in §14 + `ProviderMetadata` populated with whatever `ClaudeLiveClassifier` can honestly report (`provider_name="claude_live"`, `model` if knowable, `provider_version=None`, `latency_ms` best-effort, `reasoning=None`) — nothing more elaborate.

## 25. AI Provider Abstraction

**Design only — nothing below is implemented.**

Three pieces, cleanly separated:

```
ClassificationEngine.classify_file(file) -> (Category, ClassificationSignals, mode, ProviderMetadata | None, processing_time_ms, fallback_used, fallback_reason)
        │
        │  (only when a deterministic answer isn't possible)
        ▼
ClassificationProvider.classify(request: ClassificationRequest) -> ProviderResponse
```

**`ClassificationRequest`** (extends the existing scaffold in `src/pipeline/classification.py`):
```
file_id: str
path: str
extracted_text: Optional[str]
mode: "text" | "vision"
mime_type: Optional[str]
```

**`ClassificationResult`** (the pure classification answer — extends the existing scaffold, unchanged from round one, kept deliberately narrow):
```
category: str                            # raw provider output — a plain string, not
                                           # yet the Category enum; see validation below
ambiguous: bool = False
multi_document_detected: bool = False
notes: str = ""
```

**`ProviderMetadata`** (new — observability, kept separate from the classification answer itself):
```
provider_name: str                        # e.g. "claude_live"
model: Optional[str] = None               # e.g. "claude-sonnet-5"; None if not meaningful
provider_version: Optional[str] = None
latency_ms: Optional[int] = None          # measured by the Engine wrapping the call —
                                           # see §18 for why this is provider-agnostic
                                           # and Engine-owned, not self-reported
reasoning: Optional[str] = None           # optional free-text rationale — see §17
                                           # privacy note before any provider populates this
```

**`ProviderResponse`** (new — the wrapper a provider actually returns):
```
result: ClassificationResult
metadata: ProviderMetadata
```

**Why `category` stays a plain `str` at the provider boundary, not the `Category` enum:** the provider (especially a future LLM-API provider, or today's live-judgment "provider") naturally produces free text — coupling the provider interface itself to an internal Python enum type would force every provider implementation to know about this codebase's type system. Instead, the **Engine** is the trust boundary: it receives a raw string, validates it against `Category`, and only a validated, typed `Category` member ever reaches `FileRecord`. An unrecognized string is exactly an `"invalid_response"` fallback case (§11), not a crash.

**`ClassificationProvider`** — the abstract contract, one method:
```
classify(request: ClassificationRequest) -> ProviderResponse
```
The provider performs classification only. It does not decide text-vs-vision mode (the Engine already decided that when building the request). It does not decide fallback behavior — if it can't classify, it raises (a well-defined exception, e.g. a provider-unavailable or provider-error condition), and the **Engine** catches this and applies §11's fallback strategy. The provider never itself returns something Unknown-like as a way of handling its own failure.

**Provider selection:** a simple default in v1 — e.g. a constant (`DEFAULT_PROVIDER = "claude_live"`) rather than a config file, consistent with "smallest V1" (§24). A real config surface only becomes worth building once a second provider actually exists.

**V1's concrete provider — `ClaudeLiveClassifier`:** fulfills `classify()` with no network call at all; Claude, already driving the run, reads the file and constructs the `ProviderResponse` directly (with `metadata.reasoning` left `None` and `metadata.latency_ms` best-effort per §18's known limitation).

**Future providers this enables (not implemented, only unblocked):** `ClaudeAPIClassifier`, `OpenAIClassifier`, `GeminiClassifier`, a `LocalLLMClassifier`, and a `RuleBasedClassifier` (formalizing Alternative C from §23-A as a real fallback/offline provider). Each implements the same `classify(request) -> ProviderResponse` signature. Neither Module 02 nor the Engine's fallback/mode logic changes to add one — only a new provider module plus flipping which provider is selected.

**Why this satisfies the requirement:** the Engine has zero Claude-specific code in it — it only ever calls "the configured provider's `classify()`," validates the response, and applies fallback policy uniformly regardless of which provider answered. The only place "Claude" appears at all is in the name and behavior of the one concrete v1 provider. Swapping to a network-based provider later is purely additive, and the Engine's fallback/mode-selection logic (§11, §6) doesn't need to change at all — this is a direct improvement over round one's design, where that guarantee was weaker because there was no Engine to hold the line.

---

## 26. Final Architecture Validation

Reviewing the design as refined (§1–25) against the six requested changes and against round one's Formal Architecture Review (previously §26). **Nothing in this section proposes further unapplied changes unless explicitly marked "still open" below** — this is a validation pass, not another round of deferred recommendations.

**Round-one findings, resolved:**
1. *`classification_signals` as a loosely-typed dict* — **Resolved.** Now `ClassificationSignals`, a dedicated dataclass (§14), with the asymmetry against `confidence_breakdown`/`extracted_metadata` explicitly justified rather than left implicit.
2. *§6 restating specific category names* — **Resolved.** §6/§7 now describe workflow shape only; category names live exclusively in `Rules/Classification Rules.md`.
3. *§25 and `src/README.md` describing the same idea at different formality levels* — **Still open, unchanged from round one, and intentionally not applied here:** this requires touching `src/README.md`, which stays out of scope for a design-only phase. Recommend applying when Module 02 implementation actually begins.
4. *Unreadable-vs-Unknown distinction being easy to lose* — **Still open by design, not a defect:** the distinction is kept (§11) and now has more surface area to get lost in (three layers instead of two) — recommend this be a docstring-level callout in `ClassificationEngine.classify_file()` specifically when implemented, not just this document.
5. *`ClassificationResult` answering two kinds of questions (category + structural flags)* — **Improved, not fully resolved by choice:** the new `ProviderResponse`/`ProviderMetadata` split (this round's change 3) already separates "the classification answer" from "how the call went," which is a cleaner cut than round one had. `ClassificationResult` itself still carries both `category` and `multi_document_detected` together — per §24's "smallest V1" reasoning, this remains an accepted, deliberate simplification, not an oversight.
6. *Naming inconsistency, `ClassifierProvider` vs. `Classification*`* — **Resolved.** This round's instructions used `ClassificationProvider` directly; adopted throughout.
7. *Responsibilities/Module Contract overlap* — **Confirmed still fine, no change needed**, same reasoning as round one.
8. *Document scope/lifecycle after freeze* — **Unchanged plan:** once frozen, `02 Classification.md` remains the short pointer; this document becomes the historical/frozen artifact, same relationship `Release/Module01/` has to `src/README.md`.

**New findings from this round's refinements (checked for, not just assumed clean):**
- The `Category`/`ClassificationSignals` (de)serialization gap (§13) is a genuine new implementation detail the typed-model change introduces that didn't exist when both fields were plain dict/str — documented, not blocking, since it's a small addition to an existing loader function.
- `ProviderMetadata.reasoning` is a new potential privacy surface that didn't exist in round one — documented in §17/§12, not a v1 risk today (v1's provider leaves it `None`), but a real constraint on future providers.
- `latency_ms`'s meaning is inherently limited for a live-judgment provider with no real network boundary — documented as a known limitation (§18, §22 risk 7), not a defect, and specifically *why* the metric still belongs in the design now (so historical baseline data exists once it becomes meaningful).
- The Engine/Provider split was checked against all three of this document's Alternative Architecture criteria (§23-D) and against how it interacts with §23-A (Direct API alternative) — it measurably lowers the cost of that future alternative, which is the point of doing it now rather than later.

No issues were found that require changing anything in §1–25 as currently written. The two "still open" items above (3 and 4) are explicitly deferred to implementation time, not to another design round — they don't block freezing the architecture, only remind whoever implements Module 02 to carry the intent through into code comments and `src/README.md`.

**The Module 02 architecture is frozen and ready for implementation.**
