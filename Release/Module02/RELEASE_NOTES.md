# Release Notes — Module 02 (Classification)

```
Pipeline Version:  0.2.0
Module Version:    1.0.0
Date:              2026-07-06
Status:            Frozen, approved, feature-complete
```

See `Release/VERSIONS.md` for how Pipeline Version and Module Version relate (each module versions independently; the pipeline number tracks overall project maturity, not a function of module numbers).

**Deployment model, stated plainly:** Module 02 is production-ready *for interactive, Claude-assisted operation* — every deep-pass classification is answered live by Claude during an agent-driven session, exactly as `ClaudeLiveClassifier`'s design intends. It is **not** production-ready for autonomous/unattended operation: no `ClassificationProvider` exists that can classify a text- or vision-dependent file without a live Claude session in the loop, and building one is explicitly out of scope for v1 (`Build-out/02 Classification/Module 02 Design.md` §23-A, §25). Running `classify_batch()` outside a live session is safe — every judgment-dependent file gracefully falls back to `Category.UNKNOWN` rather than crashing or guessing — but it will not produce real classifications. See `KNOWN_LIMITATIONS.md` and `MODULE_CONTRACT.md`'s "Provider boundary" section. (This distinction was previously implicit in a single Known Limitations bullet; made explicit here and across the release record after an independent audit — `Release/Module02/RELEASE_AUDIT.md`, finding F1 — found the earlier unqualified "production-ready" wording could be read as claiming autonomous readiness it doesn't have.)

This is the second module of the Downloads Intelligence pipeline. It takes every `FileRecord` Module 01 discovered, determines what kind of file it is (`Category`), and produces a set of raw signals (`ClassificationSignals`) for later modules to act on — via a deterministic fast path for unambiguous extensions, and a text/vision deep pass backed by live Claude judgment for everything else.

## Features implemented

- Deterministic classification for extension-mapped categories (Application, Archive, Video, Audio) — never touches a provider.
- Deterministic Screenshot-vs-Image split for image-family extensions, per `Rules/Classification Rules.md`'s filename-marker / screen-resolution / camera-EXIF heuristic.
- Deterministic password-protection detection for PDFs (`is_locked()`), short-circuiting before any provider call.
- Deterministic non-English detection (`detect_non_english()`) from already-extracted text.
- Text/vision deep pass for PDF/DOCX/TXT content, backed by a three-layer architecture: `classify_batch()` (Module 02's batch orchestration) → `ClassificationEngine` (per-file decision-making: deterministic vs. AI vs. fallback) → `ClassificationProvider` (raw classification only) — exactly per the frozen design (`Build-out/02 Classification/Module 02 Design.md`).
- `ClaudeLiveClassifier` — v1's real provider, a documented placeholder fulfilled live by Claude during an agent-driven run (no network call, no autonomous code execution of judgment).
- Explicit, auditable fallback strategy: provider unavailable, provider error, or an invalid/unrecognized category response all degrade gracefully to `Category.UNKNOWN` with a specific `fallback_reason`, never a crash.
- Strongly typed `Category` enum and `ClassificationSignals` dataclass (`src/models/classification.py`), replacing the design's original generic dict/str proposals per the approved refinement round.
- Typed-field (de)serialization in `storage/database.py` so `Category`/`ClassificationSignals` round-trip correctly through `metadata_store.json`.
- Expanded action-log detail per classification: category, signals, mode (`deterministic`/`text`/`vision`), processing time, fallback fields, and provider metadata (name/model/version/latency/reasoning) when a provider was actually invoked.
- CLI extension (`src/main.py`'s `classify()`) — loads discovered-but-unclassified records, runs `classify_batch()`, and prints a full summary (category counts, mode counts, fallback count) read back from the action log for accuracy.

## Bugs fixed

- **Unwrapped image-read failures in `ClassificationEngine.classify_file()` (found during integration testing, 2026-07-06).** The deterministic image-split branch had no error handling, unlike the text-bearing branch — a file with unreadable/non-image content (corrupted download, truncated transfer, or a synthetic placeholder fixture at test time) raised uncaught, caught only by `classify_batch()`'s outer safety net, leaving the file with `category=None` instead of a graceful fallback. Fixed: the branch now wraps `classify_screenshot_or_image()` the same way the text-bearing branch already wrapped its own file-access calls, degrading to `Category.UNKNOWN` with `fallback_reason="unreadable_content"`. Regression test added; full unit suite re-confirmed at 90/90.
- **Fallback paths discarded the actual exception message (found during the independent release audit, 2026-07-06 — F3).** `extraction_failed`/`unreadable_content`/`provider_exception`/`invalid_response` fallbacks only ever recorded a fixed reason string, with no way to tell *why* a specific file failed short of reproducing it by hand. Fixed: added `EngineResult.error_detail` (a sanitized, length-bounded exception message or offending value), populated on every fallback path and included in the `classify` action-log entry's `details.error_detail`.
- **`no_extractable_text` signal left at its default `False` on the `extraction_failed` fallback path, despite the file genuinely having no usable text (found during the independent release audit, 2026-07-06 — F6).** The same real-world condition ("we got no usable text from this file") produced a different signal value depending on which failure mode was hit. Masked in practice by `Category.UNKNOWN`'s existing hard floor (`Rules/Confidence Rules.md` always routes Unknown to `review_required` regardless of signals), so never user-visible — fixed anyway for signal accuracy, since `classification_signals` is documented as the raw material Module 06 reads independent of category.
- **`.tar` missing from `_EXTENSION_CATEGORY_MAP` despite being listed under Archive in `Rules/Classification Rules.md`'s Pass 1 table (found during the independent release audit, 2026-07-06 — F4).** Currently unreachable in practice (Module 01's `SUPPORTED_EXTENSIONS` doesn't ingest `.tar` yet), so no user-visible impact — fixed anyway, and now guarded by a permanent regression test (`test_extension_category_map_matches_rules_taxonomy`) so the Rules doc and the code can't silently diverge again.

## Breaking changes

None. This is the second module in the pipeline; Module 01's contract is unaffected (Module 02 only ever reads Module 01's fields, never rewrites them — see `MODULE_CONTRACT.md`). The `Category`/`ClassificationSignals` fields on `FileRecord` are new additions, not changes to existing fields.

## Improvements

- Design-phase refinement round (approved before implementation) upgraded the original design's `classification_signals: dict` to a typed `ClassificationSignals` dataclass, `category: str` to a `Category` enum, extended the provider response with `ProviderMetadata` for observability, expanded logging to include mode/provider/processing time, designed an explicit fallback strategy, and introduced `ClassificationEngine` as a dedicated decision-making layer between Module 02 and the provider — all six refinements fully implemented as approved.
- `core/pdf.py`, `core/text.py`, `core/images.py`, `core/exif.py` implemented from stubs, backing Module 02's content-reading needs (PDF text/rendering/encryption via `pdfplumber`/`pypdf`, DOCX/TXT text via `python-docx`, language detection via `langdetect`, image dimensions/format/EXIF via Pillow).
- New `Tests/Module 02 Classification/` dataset built for integration testing (password-protected PDF, non-English invoice, ambiguous invoice/receipt, simulated multi-document PDF, scanned/vision-mode PDF, a second resume) — reused for both the Integration Test Plan and available for future regression use.
- **Two design-committed tests, promised by `Build-out/02 Classification/Module 02 Design.md` §16/§19 but never implemented until the independent release audit (F2), added as permanent regression tests:** a Module Contract immutability test (`test_classify_batch_leaves_every_non_owned_field_byte_identical` — every `FileRecord` field outside Module 02's ownership is set to a distinctive value and asserted unchanged after `classify_batch()`) and an extension-mapping drift test (`test_every_module01_supported_extension_is_routed_by_module02` — every extension Module 01 can discover is asserted to be routed somewhere meaningful by Module 02, not silently falling through to an unmapped Unknown).
