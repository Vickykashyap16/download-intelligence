# Release Notes — Module 03 (Metadata Extraction)

```
Pipeline Version:  0.3.0
Module Version:    1.0.0
Date:              2026-07-06
Status:            Frozen, approved, feature-complete
```

See `Release/VERSIONS.md` for how Pipeline Version and Module Version relate (each module versions independently; the pipeline number tracks overall project maturity, not a function of module numbers).

**Deployment model, stated plainly (same distinction Module 02's release record draws for `ClaudeLiveClassifier`):** Module 03 is production-ready *for interactive, Claude-assisted operation* — every judgment-dependent field is answered live by Claude during an agent-driven session, exactly as `ClaudeLiveExtractor`'s design intends. It is **not** production-ready for autonomous/unattended operation: no `MetadataExtractionProvider` exists that can extract text/vision-dependent fields without a live Claude session in the loop, and building one is explicitly out of scope for v1. Running `extract_metadata_batch()` outside a live session is safe — every judgment-dependent field gracefully falls back to `null` rather than crashing or guessing — but it will not produce real extracted values. See `KNOWN_LIMITATIONS.md` and `MODULE_CONTRACT.md`'s "Provider boundary" section.

This is the third module of the Downloads Intelligence pipeline. It takes every `FileRecord` Module 02 assigned a real, non-`Unknown` category to, and extracts a closed, per-category set of metadata fields (`extracted_metadata`) — via deterministic passes for categories with a real machine-readable source (Archive contents, Application/Video filenames, Audio ID3 tags, Image/Screenshot EXIF), and a text/vision deep pass backed by live Claude judgment for everything genuinely content-dependent (Invoice, Resume, Bank Statement, Contract, Document, plus Image/Screenshot's judgment fields).

## Features implemented

- A closed per-category metadata taxonomy (`REQUIRED_FIELDS`/`OPTIONAL_FIELDS`, `src/pipeline/metadata.py`) for all 11 non-`Unknown` categories — any field a provider returns outside this taxonomy is dropped, never merged, never persisted. Mechanical `is_extraction_complete()` definition: incomplete iff any required field is still `null`.
- Fully deterministic extraction, never touching a provider, for Archive (nested-directory-aware `zipfile.namelist()` contents summary, entry contents never decompressed), Application and Video (filename-pattern parsing, honest `null` on an unparseable name rather than a fabricated guess), and Audio (embedded ID3-style tags via `mutagen`, filename fallback for `track_title` only when no title tag exists).
- Deterministic + judgment "mixed" mode for Image/Screenshot: `capture_date` sourced only from EXIF (tier 2 of the four-tier timestamp hierarchy, `Module 03 Design.md` §9A), with a vision-only provider call for the remaining judgment field(s) — `capture_date` never falls back to a filesystem timestamp.
- Four-tier timestamp source hierarchy (embedded content metadata → EXIF → container/format metadata → filesystem timestamps), with tier 4 (filesystem) never written by Module 03 at all — reserved for Module 05's own naming-time fallback.
- Text/vision deep pass for Invoice/Resume/Bank Statement/Contract/Document, backed by the same three-layer architecture as Module 02, deliberately not code-shared: `extract_metadata_batch()` (batch orchestration) → `MetadataExtractionEngine` (per-file decision-making) → `MetadataExtractionProvider` (raw structured extraction only).
- `ClaudeLiveExtractor` — v1's real provider, a documented placeholder fulfilled live by Claude during an agent-driven run (no network call, no autonomous code execution of judgment) — the same pattern as `ClaudeLiveClassifier`.
- Structural, provider-independent redaction: Bank Statement's `account_last4` is redacted to `null` (with only the field name, never the value, logged in `redacted_fields`) whenever the value contains more than 4 digits — a trust-boundary check at `MetadataExtractionEngine._validate_and_merge()`, not a prompt instruction.
- Explicit, auditable fallback strategy: provider unavailable, provider exception, or a malformed/corrupted file at the deterministic layer all degrade gracefully — judgment fields stay `null`, any deterministic value already found (e.g. Image's EXIF `capture_date`) is preserved, never discarded, and the batch never aborts on a single file's failure.
- Expanded action-log detail per extraction: category, fields extracted/missing, mode, processing time, `extraction_complete`, fallback fields, `redacted_fields` (always present, even empty), and provider metadata (name/model/version/latency/reasoning) when a provider was actually invoked.
- CLI extension (`src/main.py`'s `extract()`) — loads classified-but-unextracted records, runs `extract_metadata_batch()`, and prints a full summary (mode counts, provider call count, fallback/incomplete counts, per-file redaction/incompleteness notes) read back from the action log for accuracy. Mirrors `classify()`'s exact shape; both gained an optional `provider=` parameter so a real (UAT/production) run can supply live judgment explicitly.
- Two new `core/` modules: `core/archive.py` (zip contents listing, entry-content-safe) and `core/media.py` (audio ID3 tag reading via `mutagen`).

## Bugs fixed

- **Boolean values silently accepted as valid metadata (found during the independent implementation audit, 2026-07-06 — F1).** `isinstance(value, (str, int, float))`'s type check is `True` for Python `bool` (a subclass of `int`), so a provider returning `True`/`False` for any field would have been merged into `extracted_metadata` as a valid value — no field in the entire taxonomy is boolean-shaped, so this was always a wrong-type answer the validation should have caught. Fixed: `_validate_and_merge()` now explicitly excludes `bool` before the `isinstance` check. Four regression tests added (`True` rejected, `False` rejected, a mixed valid+boolean response drops only the boolean field, a boolean judgment-field answer doesn't disturb a sibling deterministic field already found).
- **The taxonomy-drift regression test the design committed to (§20) was never built (found during the independent implementation audit — F2).** No test existed verifying `Rules/Confidence Rules.md`'s citation of the metadata taxonomy pointed at a real, current document — the same class of gap Module 02's own release audit had already caught once (its F4). Fixed: two regression tests added — one asserting the citation points at the current authoritative doc (`Module 03 Design.md`, not a superseded pointer), one parsing §7's markdown table directly and cross-checking it field-for-field against the code taxonomy.
- **`Rules/Confidence Rules.md` cited the superseded pre-design pointer doc (found during the independent implementation audit — F3).** Updated the citation only (`Module 03 Design.md` §7); no deduction values, tiers, or hard floors were changed.
- **`extract_metadata` was entirely undocumented in the canonical `Metadata & Log Schema.md` (found during the independent release audit, 2026-07-06 — F2 of `RELEASE_AUDIT.md`).** The same category of gap the schema doc's own text says was already caught once for Module 02's `classify` action type had recurred for Module 03's `extract_metadata`. Fixed: the schema doc now documents `extract_metadata`'s full `details` shape, mirroring how `classify` is documented one entry above it.
- **The project's real `Database/Metadata/metadata_store.json` and `Runtime/Logs/action_log.jsonl` contained synthetic debug data (found during the independent release audit — F1 of `RELEASE_AUDIT.md`).** An earlier ad-hoc debugging script (run during this module's own implementation-audit troubleshooting) wrote directly to the project's real, hardcoded storage paths instead of an isolated tmp path. Investigated in two stages, both fully evidenced in `RELEASE_AUDIT.md`; the complete pre-cleanup state was archived (not deleted) to `~ARCHIVE~/Module03_release_cleanup_2026-07-06/` before either file was reset to its clean, empty, "first real run" state.
- **`src/README.md`'s Status section didn't mention Module 03 at all (found during the independent release audit — F4 of `RELEASE_AUDIT.md`).** Still described Module 03 as "not started" while the module was a complete, tested release candidate. Fixed: added a Module 03 status bullet mirroring the Module 01/02 bullets, and corrected "remaining build order" to start at Module 04.

## Breaking changes

None. This is the third module in the pipeline; Module 01's and Module 02's contracts are unaffected (Module 03 only ever reads their fields, never rewrites them — see `MODULE_CONTRACT.md`). `FileRecord.extracted_metadata` already existed as a field (added when `FileRecord` was first modeled); this release is the first to actually populate it, not a schema change.

## Improvements

- Design-phase process identical in rigor to Module 02's: a senior-architect design review (`Module 03 Design Review.md`) found one Medium-High business-rule finding (the required/optional taxonomy needed explicit owner sign-off, not silent inference) and three further Medium findings (redaction precision, redaction scope, Video's date-fallback disclosure), all resolved before a second independent architecture review (`Module 03 Design Review 2.md`) confirmed zero Critical/High/Medium findings remained and froze the design.
- `Rules/Confidence Rules.md`'s deduction math now has an automated, permanent guard against the exact class of citation/taxonomy drift that had to be caught manually once already (Module 02's own release audit, F4) — the drift-guard tests added for F2 above.
- New `Tests/Module 03 Metadata/` dataset built for integration testing: a real ID3-tagged MP3 and a real untagged MP3 (genuine audio via `ffmpeg`), a real EXIF-bearing JPEG (genuine camera metadata via Pillow), a multi-entry nested-directory ZIP, a corrupted-but-valid-extension ZIP, and two realistically-named installer files — reused unchanged from `Samples/`/existing `Tests/` datasets wherever those already covered a scenario.
- Full three-tier validation discipline carried through from design to release: a senior-architect design review, an independent implementation audit (2 Medium findings resolved), a 59-case integration test plan (0 implementation defects — 4 test-harness bugs found, confirmed, and fixed), a 20-requirement live-judgment UAT (0 defects, including a deliberately adversarial redaction test), and a final independent release audit (5 findings, all resolved or explicitly disposed of — see `Release/Module03/RELEASE_AUDIT.md`).

---

## Post-freeze correction #1 (2026-07-26) — TD-01 v0.9: opt-in autonomous Claude API MetadataExtractionProvider

**Severity:** High-impact gap resolution, not a defect (`TECHNICAL_DEBT_REGISTER.md` TD-01). **Module Version:** patched, `1.0.0` → `1.1.0` (MINOR, per `Release/VERSIONS.md`'s own convention — additive, not a bug fix, and not a contract change).

**What changed:** `src/providers/claude.py`'s `ClaudeAPIExtractor` — a real, non-interactive `MetadataExtractionProvider` implementation, mirroring `ClaudeAPIClassifier`'s structure exactly (this module's own design §21 precedent: independently defined, convention-following, never code-shared with Module 02's equivalent) — registered under `"claude"` via the new `src/providers/registry.py`. `ClaudeLiveExtractor` (this module's own documented interactive-session placeholder) is **completely untouched** and remains the default whenever no autonomous provider is opted into. `ProviderMetadata` (defined in `src/pipeline/metadata.py`, this module's own independent copy) gained one new optional field, `token_usage: Optional[Dict[str, int]] = None`, mirroring `pipeline/classification.py`'s identical addition — additive with a default, no existing call site affected.

**Why this belongs to Module 03's own contract boundary, not a separate system:** `MetadataExtractionProvider` (`Module 03 Design.md §23`) was designed as the same kind of deliberate swap point Module 02's `ClassificationProvider` is. This correction is that swap happening for the first time on this module's side too — `MetadataExtractionEngine`, `extract_metadata_batch()`, and every downstream module are provably untouched (full regression suite plus a scope-diff check).

**Not enabled by default:** requires both `ai_provider_consent: true` (written only by `python -m src.cli provider enable`, outside this module) and a real `ANTHROPIC_API_KEY`. `main.py`'s `_resolve_provider_for_extraction()` returns `None` otherwise, letting `extract_metadata_batch()`'s own pre-existing `provider or ClaudeLiveExtractor()` default apply unchanged — verified directly with a dedicated test proving the resolver never itself constructs the placeholder.

**Design record:** `Build-out/02 Classification/TD-01 Provider Architecture — Design Package.md` (same design package Module 02's correction #2 references — TD-01 spans both modules by its own register entry).

**Scope:** `src/providers/` (shared with Module 02's correction, new), `src/cli.py`'s `provider` subcommand (shared), `src/main.py`'s extraction resolver, `src/config/sources.yaml`'s `extraction_provider` key, and the one additive `ProviderMetadata.token_usage` field in this module's own `src/pipeline/metadata.py`. No other line of this module's code was touched.

**Regression tests added:** shared with Module 02's correction (`src/providers/test_registry.py`, `src/providers/test_claude.py` — the extractor's own tests included in that same 26-test file, mocking the `anthropic` client), plus this module's share of the 12 new CLI provider tests and 13 new `main.py` resolver tests (the extraction-specific half of each). Full suite: **889/889**.

**Verification performed:** identical acceptance-criteria evidence to Module 02's correction #2 (`Tests/Provider Evaluation Harness/TD-01 v0.9 Validation Report.md`) — the harness's `extract_metadata_batch()` stage is exercised by the same real-provider dry run and fake-oracle-provider test run.

**Disclosed, not swept under this entry:** same gap as Module 02's correction #2 — no `ANTHROPIC_API_KEY` was available in the implementation environment, so no real Claude API extraction call was ever made. `TECHNICAL_DEBT_REGISTER.md`'s TD-01 (which names both modules) is **partially resolved**, not closed.

**`MODULE_STATUS.md` intentionally left unchanged** — point-in-time snapshot convention. `Release/VERSIONS.md` is this module's current, authoritative version.

**Full narrative:** `CHANGELOG.md`'s 2026-07-26 entry; `Tests/Provider Evaluation Harness/TD-01 v0.9 Validation Report.md`; Module 02's own `RELEASE_NOTES.md` correction #2 for the classification-side detail.
