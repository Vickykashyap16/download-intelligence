# src/

Implementation code for Downloads Intelligence. This is the scaffold only — module bodies are stubs (`NotImplementedError`) until built one at a time, per the plan. See `CHANGELOG.md` for when this was added and why (the frozen architecture originally had no code folder), and for the two refinement passes since.

## Language: Python 3

Chosen because every tool identified during design (`Rules/*.md`, `Build-out/00 Pre-build context & examples/Pre-build context.md` §9) is Python-native: `python-magic`/`mimetypes` for MIME sniffing, `pdfplumber` for PDF text, `Pillow`/`exifread` for image EXIF, `hashlib` + `imagehash` for exact/near-duplicate detection, `rapidfuzz` for filename similarity. There's no part of this pipeline that plays to a different language's strengths, and Python is already preinstalled in the sandbox this runs in.

## How Claude fits into "code"

This is an **Automation** (build type), not a service with its own AI calls. When the user asks Claude to scan Downloads, **Claude is the one running**, so the modules below split into two kinds:

- **Deterministic modules** — pure code, no judgment calls: hashing, EXIF reads, ignore-pattern filtering, JSON/log I/O, file moves. Fully implementable and testable without Claude in the loop.
- **Judgment modules** — the actual classification, content-based metadata extraction, and destination/naming calls that need to *read and understand* a file. These modules define a clear request/response contract (e.g. `ClassificationRequest` in → `ClassificationResult` out) but don't call any LLM API internally. Claude fills in the judgment step live during a run and passes the result back in. This keeps the deterministic code testable in isolation (feed it a fake `ClassificationResult`, check the rest of the pipeline behaves) while keeping the actual understanding step exactly where the architecture always said it belonged — with Claude, live, per file.

Each `pipeline/*.py` module's docstring says which kind it is. **Keep this separation** — it's what makes the deterministic modules independently testable and the judgment modules swappable later (e.g. if a future version wants to call an API directly instead of relying on a live Claude session).

## Layout

```
src/
├── main.py                 — entry point: `python src/main.py scan` (Manual mode)
├── requirements.txt         — pinned dependencies
├── config/                  — sources.yaml only (see "Why config/ is nearly empty" below)
├── pipeline/                 — one module per Build-out step (numeric order dropped — Build-out/ already documents it)
│   ├── watch_ingest.py         (Build-out 01)
│   ├── classification.py       (Build-out 02)
│   ├── metadata.py             (Build-out 03)
│   ├── duplicate_detector.py   (Build-out 04)
│   ├── naming.py               (Build-out 05)
│   ├── confidence.py           (Build-out 06)
│   ├── execution.py            (Build-out 07)
│   └── reporting.py            (Build-out 08 — writes logs, Daily Summary, batch summaries, execution reports)
├── storage/                  — reads/writes Database/ and Runtime/
│   ├── database.py
│   └── runtime_io.py
├── models/                   — shared data shapes
│   ├── file_record.py
│   └── batch.py
└── core/                      — reusable components used by multiple pipeline modules
    ├── hashing.py               — sha256, perceptual hash, hamming distance
    ├── pdf.py                   — PDF text extraction + scanned-page rendering
    ├── text.py                  — non-PDF text extraction (.docx/.txt/.rtf) + language detection
    ├── images.py                — dimensions, format, screen-resolution matching
    └── exif.py                  — camera metadata reads
```

## Why `config/` is nearly empty

Earlier scaffold had YAML mirrors of every `Rules/*.md` file. Decision on refinement: **not for v1.** `Rules/` stays the single source of truth while the business rules are still evolving — mirroring them into generated config right now would mean every rule tweak needs updating in two places, which is exactly the kind of drift this project has already caught itself in once (see `CHANGELOG.md`, the "stale documentation" fixes from the second design review). v1 code reads and implements `Rules/*.md` directly. Machine-readable config is deferred to a future version, once the rules have stabilized enough that mirroring them stops being a moving target.

`config/sources.yaml` is the one exception — it's runtime/deployment configuration (which folder to watch, which execution mode), not a mirror of a business-rule document, so it stays.

The four deprecated `config/*_rules.yaml` files are comment-only placeholders (can't be deleted from this workspace) pointing back here.

## Deliberately not named `tests/`
Unit tests for this code will live as colocated `test_*.py` files next to each module (pytest convention) once real logic exists — not in a folder called `tests/`, to avoid colliding with the vault's existing top-level `Tests/` (which means something different: end-to-end validation datasets, not unit tests).

## Status
- **`pipeline/watch_ingest.py` (Module 01) — implemented, validated (automated tests + two UAT passes), and approved.** Along with the parts of `storage/database.py`, `storage/runtime_io.py`, and `core/hashing.py` it depends on. `file_id` is a permanent UUID4 assigned once at discovery (never derived from path or content — see `CHANGELOG.md` for why that matters once Module 07 starts moving files), with `content_hash` and `current_path` as separate fields for duplicate comparison and live-location tracking respectively. Tests: `pipeline/test_watch_ingest.py` (13 passing). Skip reasons use a specific vocabulary (`system_file`, `temporary_download`, `ignored_pattern`, etc. — see `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`), and `src/main.py`'s CLI output reports a full scan summary (discovered + skipped + reasons + generated-file locations) — both added after the first UAT pass surfaced the original generic `ignored_name` reason and discovered-only terminal output as gaps. UAT artifacts archived under `Runtime/UAT/`.
- **`pipeline/classification.py` (Module 02) — implemented, validated (automated tests + integration test plan + a live-judgment UAT run), and approved.** Three-layer architecture: `classify_batch()` (batch orchestration) → `ClassificationEngine` (deterministic-vs-AI-vs-fallback decision-making) → `ClassificationProvider` (raw classification only, an ABC — `ClaudeLiveClassifier` is v1's real implementation, a documented placeholder fulfilled live by Claude during a run; `FakeClassificationProvider` is the test double). Along with `core/pdf.py`, `core/text.py`, `core/images.py`, `core/exif.py` (all implemented from stubs) and the typed-field (de)serialization Module 02 added to `storage/database.py`. `Category` (enum) and `ClassificationSignals` (dataclass) live in `models/classification.py`. Tests: `pipeline/test_classification.py` (48 passing) plus supporting `core/`/`models/`/`storage/` tests (93 total across the whole suite, including Module 01's). See `Release/Module02/` for the full release record, including `RELEASE_AUDIT.md`/`RELEASE_AUDIT_2.md` — one defect (unwrapped image-read failures in the Engine) was found during integration testing and fixed before release; a further independent release audit before freeze found and resolved 3 High and 3 Medium findings. Production-ready for interactive Claude-assisted operation only — no autonomous `ClassificationProvider` exists yet (see `Release/Module02/KNOWN_LIMITATIONS.md`).
- **`pipeline/metadata.py` (Module 03) — implemented, validated (automated tests + integration test plan + a live-judgment UAT run), and approved.** Three-layer architecture, deliberately not code-shared with Module 02's: `extract_metadata_batch()` (batch orchestration) → `MetadataExtractionEngine` (per-file deterministic/judgment/fallback decision-making) → `MetadataExtractionProvider` (raw structured extraction only, an ABC — `ClaudeLiveExtractor` is v1's real implementation, the same documented-placeholder pattern as `ClaudeLiveClassifier`; `FakeMetadataExtractionProvider` is the test double). A closed per-category field taxonomy (`REQUIRED_FIELDS`/`OPTIONAL_FIELDS`) drives required/optional validation, a four-tier timestamp source hierarchy, and a structural redaction check on Bank Statement's `account_last4`. Along with `core/archive.py` and `core/media.py` (new for this module). Tests: `pipeline/test_metadata.py` (57 passing) plus the full suite (161 total, including Modules 01–02's). See `Release/Module03/` for the full release record — `IMPLEMENTATION_AUDIT.md` (2 Medium findings resolved before integration testing), `RELEASE_AUDIT.md` (3 Medium + 2 Low findings resolved or explicitly disposed of before freeze), and `RELEASE_SUMMARY.md` for a one-page pointer to the rest. Pipeline Version 0.3.0 as of this release (`Release/VERSIONS.md`).
- Everything else is still scaffold. Remaining build order per `Build-out/`: `duplicate_detector.py` (04) next, then `naming.py` (05), `confidence.py` (06), `execution.py` (07), `reporting.py` (08).

## Known testability limitations
- `storage/database.py` and `storage/runtime_io.py` compute their file paths from hardcoded, project-relative constants (`_METADATA_STORE_PATH`, `_ACTION_LOG_PATH`) rather than accepting an injectable base path. Tests work around this with `monkeypatch` (see `pipeline/test_watch_ingest.py`). Public accessors `metadata_store_path()`/`action_log_path()` now exist (added for the CLI summary) but only expose the path — they don't make it injectable. A cleaner fix — passing a base path into these modules instead of hardcoding it — is worth considering once more modules depend on them.
- `pipeline/watch_ingest.py`'s `is_stable()` takes `interval_seconds` as a default parameter bound to `STABILITY_CHECK_INTERVAL_SECONDS` at function-definition time, not read live from the module constant. `test_watch_ingest.py`'s `monkeypatch.setattr(..., "STABILITY_CHECK_INTERVAL_SECONDS", 0)` therefore doesn't actually skip the real 0.5s sleep — harmless today (the suite runs in ~1s regardless), but worth fixing (e.g. `monkeypatch.setattr(is_stable, "__defaults__", (STABILITY_CHECKS, 0))`, or refactoring `is_stable` to read the module constant directly instead of via a default arg) before more `scan_source()`-based tests get added. Found during Module 01 UAT validation; not fixed as part of that review since it's a test-harness issue, not a defect in `watch_ingest.py`'s actual behavior.
