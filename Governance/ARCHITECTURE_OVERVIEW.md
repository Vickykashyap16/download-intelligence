# Architecture Overview — Downloads Intelligence Pipeline

```
Pipeline Version:  0.7.0
Modules released:  01–07 (Module 08 not yet started)
Audience:          A new engineer (human or Claude) joining this project cold
Purpose:           Explain the whole system from first principles, in one document
```

This document is new, permanent project documentation. It does not replace or modify any existing file — `Governance/ARCHITECTURE_DECISIONS.md`, `Governance/ENGINEERING_STANDARD.md`, each module's `MODULE_CONTRACT.md`, and `Rules/*.md` remain the authoritative sources for the things this document summarizes. Where this document says "see X," that is a real cross-reference, not decoration — go there for the full text, the worked examples, and the historical reasoning. This document's job is to be the one place that explains how everything fits together, so reading it first should make everything else legible rather than requiring dozens of documents to be read before the shape of the project makes sense.

---

## 1. Executive Summary

### What Downloads Intelligence is

An AI-powered Downloads folder assistant that understands what a file *is* by reading its actual content — not just its extension — and files it away classified, renamed, deduplicated, and version-checked, with a mandatory human approval step before anything on disk actually moves. It is built as an **Automation** (not a hosted service): when it runs, it runs *as* Claude, inside a live Claude session, acting on the user's real Downloads folder with the user watching and approving.

### Vision

Downloads folders accumulate messy, randomly-named files with no consistent structure: duplicates, several versions of the same document, and a flat pile of invoices, resumes, screenshots, contracts, installers, and everything else. Finding anything later is hard, and cleaning it up by hand is tedious enough that most people never do it. The project's goal is to make that folder self-organizing — correctly classified, consistently named, deduplicated, and routed to a sensible destination — without ever silently doing something a human would have wanted to check first, and without ever risking data loss along the way. See `README.md` for the full problem statement and goals.

### Design philosophy

Four convictions run through every module built so far, and are the right lens for understanding any design or implementation decision in this codebase:

1. **Contracts, not trust.** Every module states exactly what it receives, what it produces, which fields it owns, and — critically — which fields it must never touch. Later modules depend only on that stated contract, never on another module's implementation details. This is what let seven modules get built, one at a time, without any of them accidentally breaking one another (`Governance/ARCHITECTURE_DECISIONS.md` decisions 2, 3, 15).
2. **Deterministic before AI, honesty over guessing.** Every module exhausts real, deterministic sources of truth (a file extension, an EXIF tag, a hash) before ever calling on Claude's judgment, and when genuinely uncertain, every module says so explicitly (`Category.UNKNOWN`, a `null` field, a `review_required` tier) rather than fabricating a confident-looking answer. A wrong answer that looks confident is more dangerous than an honest "I don't know," because it can silently propagate through the rest of the pipeline (decisions 6, 7, 19).
3. **Reversibility as the default, not an afterthought.** Nothing is ever permanently deleted. Every mutating action is logged immediately, in enough detail that undoing it is just replaying the log backwards. This is a project non-negotiable (`CLAUDE.md`), not a nice-to-have.
4. **Process discipline that produces real evidence, not paperwork.** Every module passes through the same nine-stage lifecycle — design, review, freeze, implement, audit, integration test, UAT, audit, release — with no stage skipped and no finding auto-fixed without explicit approval. This has repeatedly caught real defects before they shipped (see §6 and §9), which is the actual justification for the overhead, not process for its own sake.

---

## 2. End-to-End Pipeline

### The chain (Module 01 → Module 08)

```
 ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐
 │ Module 01 │──▶│ Module 02 │──▶│ Module 03 │──▶│ Module 04 │
 │  Watch &  │   │Classifica-│   │ Metadata  │   │Duplicate &│
 │  Ingest   │   │   tion    │   │Extraction │   │  Version  │
 └───────────┘   └───────────┘   └───────────┘   └───────────┘
                                                          │
      ┌───────────────────────────────────────────────────┘
      ▼
 ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐
 │ Module 05 │──▶│ Module 06 │──▶│ Module 07 │──▶│ Module 08 │
 │  Naming & │   │Confidence │   │ Preview,  │   │ Logging & │
 │Destination│   │ & Review  │   │Approval & │   │ Reporting │
 │           │   │           │   │ Execution │   │(not built)│
 └───────────┘   └───────────┘   └───────────┘   └───────────┘
```

Strictly linear by design (decision 17) — each module depends only on the one immediately before it, no branching, no parallel stages. Module 08 writes throughout the run (the action log receives entries starting with Module 01), but its *report-generation* role sits at the end. Full diagram and notes: `Release/DEPENDENCY_DIAGRAM.md`.

### What each module receives and produces

| Module | Receives | Produces / owns |
|---|---|---|
| **01 — Watch & Ingest** | A configured Source (`src/config/sources.yaml`) — a directory path, `source_id`, execution mode. Pipeline entry point; no upstream `FileRecord`s. | `file_id`, `source_id`, `original_name`/`original_path`, `current_path`, `extension`, `mime_type`, `size_bytes`, `created_at`/`modified_at`, `content_hash`, `discovered_at`, `status`, `error`, `batch_id`. |
| **02 — Classification** | `FileRecord`s from Module 01 with `status == "discovered"`. | `category` (a `Category` enum, including `UNKNOWN`), `classification_signals` (ambiguity, multi-document, no-text, non-English, locked). |
| **03 — Metadata Extraction** | Records with `status == "discovered"` and a real, non-`Unknown` `category`. | `extracted_metadata` — a closed-taxonomy dict, exactly the required+optional fields for that category, honest `null` where not found. |
| **04 — Duplicate & Version Detection** | Every `status == "discovered"` record (not gated on category — exact-duplicate detection runs on everything). | `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals`. The only module allowed a disclosed side effect on a *different* record (updating its `version_group_id`/`version_rank` when a version chain is detected). |
| **05 — Naming & Destination** | Records with `status == "discovered"` and `category is not None` (Unknown included). | `suggested_name`, `suggested_destination` (root-relative, unresolved), `naming_signals`. |
| **06 — Confidence & Review** | Records with `category is not None` and `suggested_name is not None` (confirms Module 05 already ran). | `confidence_score` (0–100), `confidence_breakdown`, `tier` (`auto` / `approval_required` / `review_required`). |
| **07 — Preview, Approval & Execution** | Records eligible per tier/idempotency, plus an externally-supplied `ApprovalDecision` set and a configured `destination_root`. | `current_path` (updated after a real move), `processed_at`, `approved_by`, `approved_at`, `reversible`. The pipeline's only filesystem-mutating stage. |
| **08 — Logging & Reporting** | Not yet built. Per design intent: reads `action_log.jsonl`/`metadata_store.json` to produce Daily/Weekly Summary and Duplicate/Storage reports. | `Runtime/Reports/*` — no `FileRecord` fields (read-only aggregation). |

### How `FileRecord` evolves through the pipeline

`FileRecord` is one shared, growing data structure — a single record per real file, upserted by its permanent `file_id` on every save. It is never replaced or recreated across the pipeline; each module enriches the same object. Every field is owned by exactly one module (decision 2), so "what does this field mean right now" is always answerable by asking which module has run so far:

```
Module 01 runs   → file_id, paths, hashes, timestamps, status         populated
Module 02 runs   → + category, classification_signals                 populated
Module 03 runs   → + extracted_metadata                                populated
Module 04 runs   → + duplicate_of, version_group_id/rank, signals      populated
Module 05 runs   → + suggested_name, suggested_destination, signals    populated
Module 06 runs   → + confidence_score, confidence_breakdown, tier      populated
Module 07 runs   → + current_path (updated), processed_at,
                     approved_by, approved_at, reversible               populated
```

A field left at its dataclass default (`None`, `{}`, or `true` for `reversible`) means "the module that owns it hasn't processed this record yet" — never ambiguous, never a placeholder for something else. The one deliberately meaningful exception is `category`: `None` means Module 01 never had readable bytes to try, while `Category.UNKNOWN` means Module 02 tried on a readable file and found no match — these are different states and every downstream module must respect the distinction (decision 7). The full field list and ownership grouping live in `src/models/file_record.py`, whose field comments state, module by module, exactly who populates what.

---

## 3. System Architecture

### Major components

- **`src/pipeline/`** — one module per pipeline stage, the actual business logic. Each file's docstring states whether it's a **deterministic module** (pure code, fully testable, no judgment calls — hashing, EXIF reads, ignore filtering, JSON/log I/O, file moves) or a **judgment module** (needs Claude's live understanding of file content — classification, metadata extraction). This split is deliberate and load-bearing: it's what makes deterministic code testable without needing a live Claude session in every test run (`src/README.md`, "How Claude fits into code").
- **`src/models/`** — shared data shapes: `FileRecord` (the one cross-module record), plus per-module signal dataclasses (`ClassificationSignals`, `DuplicateSignals`, `NamingSignals`) and batch/execution structures.
- **`src/storage/`** — all reads/writes to `Database/` and `Runtime/`: `database.py` (metadata store, FileIndex, version history, user corrections) and `runtime_io.py` (action log, temp staging).
- **`src/core/`** — reusable, stateless building blocks used by multiple pipeline modules: hashing (SHA-256, perceptual hash, Hamming distance), PDF text extraction, non-PDF text extraction + language detection, image dimensions/format, EXIF reads.
- **`src/main.py`** — the CLI entry point (`python src/main.py scan` etc.) that wires each module's batch function together for Manual/Scheduled execution.

### `src/` layout

```
src/
├── main.py                    — CLI entry point, one function per pipeline stage
├── config/
│   └── sources.yaml            — the one real runtime config file (source path,
│                                  execution mode, destination_root)
├── pipeline/                    — one file per Build-out step (numeric prefixes
│   ├── watch_ingest.py            dropped; Build-out/ already documents ordering)
│   ├── classification.py
│   ├── metadata.py
│   ├── duplicate_detector.py
│   ├── naming.py
│   ├── confidence.py
│   ├── execution.py
│   └── reporting.py             — Module 08's home; not yet implemented
├── storage/
│   ├── database.py              — Database/ reads/writes
│   └── runtime_io.py            — Runtime/ reads/writes (action log, temp staging)
├── models/
│   ├── file_record.py           — the shared FileRecord dataclass
│   ├── classification.py, duplicate.py, naming.py, execution.py, batch.py
└── core/
    ├── hashing.py, pdf.py, text.py, images.py, exif.py, archive.py, media.py
```

Each module's own `test_<module>.py` lives colocated next to it (pytest convention), deliberately not in a folder called `tests/` — that name is already used by the top-level `Tests/` folder, which means something different (end-to-end validation datasets, not unit tests). See `src/README.md` for the full, current per-module status (what's implemented, test counts, known testability limitations).

### `Database/` — persistent storage

```
Database/
├── Metadata/metadata_store.json     — one cumulative JSON array, every file
│                                       ever discovered, upserted by file_id
├── FileIndex/
│   ├── hash_index.json               — content_hash → file_id (exact-duplicate lookup)
│   ├── name_index.json               — normalized filename → file_id (version-chain lookup)
│   └── phash_index.json              — perceptual hash → file_id (near-duplicate lookup)
├── History/version_history.json     — recorded version-chain relationships
└── Learning/User Corrections.json   — every human edit/rejection, captured
                                        passively (never read back — see §4)
```

Plain JSON in v1, deliberately (decision 12) — no SQLite, no other database engine. At this project's actual v1 scale (one user's Downloads folder, scanned on demand or on a schedule) a real database engine's operational complexity isn't justified by anything JSON can't already do. A SQLite migration is explicitly named as `ROADMAP.md` Version 2 scope, not a drop-in swap — it would be its own architectural decision requiring its own design review.

### `Runtime/` — operational output

```
Runtime/
├── Logs/action_log.jsonl        — one append-only, JSON-lines file, every action
├── Reports/                      — Module 08's output (Daily/Weekly Summary,
│                                   Duplicate Report, Storage Report) — empty
│                                   until Module 08 is built
├── Temp/<batch_id>/plan.json    — in-flight batch staging (Module 07), cleared
│                                   once the batch reaches a terminal state
└── UAT/Module0N_UAT_<timestamp>/ — archived evidence from every module's real
                                    UAT run (metadata store, action log, terminal
                                    output, summary — one folder per run)
```

### `Rules/` — the living business rules

Five documents, meant to be edited directly when *behavior* needs to change, independent of any module's architecture: `Classification Rules.md` (categories, the two-pass extension/text classification logic), `Naming Rules.md` (filename templates by category), `Folder Rules.md` (the flat 8-folder destination taxonomy), `Confidence Rules.md` (the points-based deduction/tier formula and hard floors), `Ignore Rules.md` (what Watch & Ingest skips entirely). Each module's design document formalizes a taxonomy a rules doc will eventually own, but the rules doc — not the design doc, and not this file — is the single source of truth for the actual business logic. See `src/README.md`'s "Why config/ is nearly empty" for why these are read directly by code rather than mirrored into machine-readable config in v1.

### `Governance/` — project-wide process and decisions

Seven documents, each with a distinct, non-overlapping purpose: `ENGINEERING_STANDARD.md` (the lifecycle every module follows — summarized in §9 below), `ARCHITECTURE_DECISIONS.md` (the permanent decision ledger — summarized in §6), `PIPELINE_CONTRACT_VERIFICATION.md` (the 13-check release gate), `FROZEN_MODULE_CHANGE_POLICY.md` (what happens if a defect surfaces in an already-frozen module), `DOCUMENT_GROWTH_POLICY.md` (when/how governance documents split as the project grows), `GOVERNANCE_REVIEW.md` (review history of this framework itself), `PROJECT_ROADMAP.md` (one-page pipeline build status — distinct from the top-level `ROADMAP.md`, which is feature scope). This document (`ARCHITECTURE_OVERVIEW.md`) is new and additive to this set — a synthesis layer sitting above the other seven, not a replacement for any of them.

### `Release/` — per-module release packages

`Release/Module<NN>/` holds each module's frozen contract, audits, test results, and release notes (structure detailed in §9). `Release/VERSIONS.md` is the single authoritative ledger for every module's current version and the overall Pipeline Version. `Release/DEPENDENCY_DIAGRAM.md` is the pipeline chain diagram reproduced (with commentary) in §2 above.

---

## 4. Core Data Model

### `FileRecord` lifecycle

One `FileRecord` per real, physical file, identified by a permanent `file_id` — an arbitrary UUID4, assigned once at first discovery, **never** derived from the file's path or its byte content (decision 1). This was a deliberate choice between two rejected alternatives: a path-derived ID would break the moment Module 07 moves or renames a file; a content-derived ID would silently merge two different physical files with identical content onto one record, before Module 04 ever gets a chance to decide what to do about the duplicate. `content_hash` and `current_path` are kept as separate, independently-meaningful fields specifically so identity, content, and location can each change independently without corrupting the others.

A re-scan of a file that hasn't changed updates the existing record in place (Module 01's own fields only); a re-scan of a file whose content has genuinely changed resets every downstream-owned field to its default, deliberately re-entering the whole pipeline's reprocessing path — because no other mechanism in this pipeline can otherwise detect or correct a stale downstream field once it's been left non-`None` (Module 01's `MODULE_CONTRACT.md`, "Post-freeze correction #1").

### Metadata store

`Database/Metadata/metadata_store.json` is one cumulative JSON array — never a per-scan snapshot, never auto-truncated (decision 11). `save_file_record()` upserts by `file_id`: load the full store, replace or append the one record, write the full store back. This is simple and correct, but it is also an explicitly disclosed O(N×M) cost — every single save reads, scans, and rewrites the *entire* store, and every batch-processing module calls it once per file in its own loop. Not a problem at v1 test volumes (fine at 75 files); the first thing worth optimizing (batch-level load/write instead of per-file) if store size or batch frequency ever grows materially. Every future module's own batch orchestration is expected to call `save_file_record()` the same way and re-disclose this same cost as its own problem too, not treat it as fully owned by whichever module first raised it.

### Action log

`Runtime/Logs/action_log.jsonl` — one append-only JSON-lines file, one line per action, across every module (decision 10). Every line shares a minimal shape (`batch_id`, `file_id`, `action`, `from`, `to`, `timestamp`, `approved_by`) plus an `action`-specific `details` object. JSON-lines specifically (not one large JSON array) means a crash mid-write only ever corrupts the last, incomplete line, never the whole log. The action vocabulary has grown one value per module as needed (`discover`, `classify`, `extract_metadata`, `detect_duplicates_and_versions`, `suggest_naming_and_destination`, `score_confidence`, `move_rename`, `archive_duplicate`, `archive_superseded_version`, `reject`, `error`, `undo`) — every new value must be added to the canonical schema doc (`Build-out/08 Logging & Reporting/Metadata & Log Schema.md`) in the *same* release cycle that introduces it; this was missed twice early on and is now an explicit standing rule (`ENGINEERING_STANDARD.md` §10). The log is never rotated or pruned in v1 — flagged as a `Version 2` concern if it ever becomes one.

### Learning database

`Database/Learning/User Corrections.json` captures every human edit or rejection made at Module 07's approval step — passive capture only. Nothing reads it back or auto-applies it (`Non-Guarantee NG6`, stated directly in Module 07's `MODULE_CONTRACT.md`). Turning this into active learning (adjusting classification/naming/destination defaults from accumulated correction history) is explicitly `ROADMAP.md` Version 3 scope, not built.

### Runtime temp files

`Runtime/Temp/<batch_id>/plan.json` exists only for the duration of an in-flight Module 07 batch. It is staged **incrementally, one record immediately before that record's own execution** — never as a separate "resolve the whole batch, then execute the whole batch" pass (decision 24) — specifically so the staged and executed destination path can never diverge, which matters because crash-recovery reconciliation matches a leftover plan entry against the action log by exact string equality. It is cleared once the batch reaches a terminal state. This is the one piece of the persistence model that is genuinely transient — nothing outside a single batch's execution depends on it surviving.

---

## 5. Module Responsibilities

Each module below is summarized to the level a new engineer needs to work near it without misusing it. The authoritative version of every line here is that module's own `Release/Module<NN>/MODULE_CONTRACT.md` — read it before writing code that depends on a specific field or edge case.

### Module 01 — Watch & Ingest
**Purpose:** Scan the configured Source's top level, discover supported/stable/non-ignored files, and mint the permanent identity record for each one. **Inputs:** a configured Source (path, `source_id`, execution mode) — the pipeline's entry point. **Outputs:** `List[FileRecord]` (one per discovered file) plus `List[SkippedEntry]` (ignored/unstable/unsupported entries, never passed downstream). **Owns:** `file_id`, `source_id`, path fields, `extension`/`mime_type`/`size_bytes`, timestamps, `content_hash`, `discovered_at`, `status`, `error`, `batch_id`. **Guarantees:** never touches any later module's fields on first discovery or an unchanged re-scan; resets downstream fields to default only when content genuinely changed. Version 1.0.1 (one post-freeze patch — see §9's worked example).

### Module 02 — Classification
**Purpose:** Determine what kind of file this is — by extension/MIME first, then live Claude judgment over extracted text or rendered image where needed. **Inputs:** `FileRecord`s with `status == "discovered"`. **Outputs:** the same records enriched with `category`/`classification_signals`. **Owns:** `category`, `classification_signals`. **Guarantees:** every processed record gets a real `Category` (never left `None`); `Category.UNKNOWN` is an honest "tried and failed," never a fabricated guess. No autonomous provider exists — real judgment requires a live Claude session (disclosed explicitly, not left implicit).

### Module 03 — Metadata Extraction
**Purpose:** Pull structured fields (vendor, dates, amounts, names) out of a classified file's actual content, per a closed, category-specific taxonomy. **Inputs:** records with a real, non-`Unknown` `category`. **Outputs:** `extracted_metadata` — exactly the required+optional fields for that category, no more, no less. **Owns:** `extracted_metadata`. **Guarantees:** a closed taxonomy enforced structurally (any out-of-taxonomy field a provider returns is dropped before it ever reaches storage); Bank Statement's `account_last4` redacted to `null` past 4 digits, enforced the same way — both hold regardless of whether the provider itself behaves well.

### Module 04 — Duplicate & Version Detection
**Purpose:** Find exact duplicates (content hash), near-duplicate images (perceptual hash), and version chains (filename similarity + version tokens/dates) against everything already filed. **Inputs:** every `status == "discovered"` record, not gated on category. **Outputs:** `duplicate_of`, `version_group_id`/`version_rank`, `duplicate_signals`. **Owns:** those four fields, plus — the pipeline's one disclosed exception — may update `version_group_id`/`version_rank` on a *different*, earlier-processed record when a version chain is detected. **Guarantees:** fully deterministic (same input + same accumulated index state → same output, verified with reversed input order); no Provider of any kind — every decision is a computation over already-structured data.

### Module 05 — Naming & Destination
**Purpose:** Turn a classified, metadata-enriched record into a clean, consistent filename and a (root-relative, unresolved) destination folder. **Inputs:** records with `category is not None` (Unknown included — every classified record gets a suggestion). **Outputs:** `suggested_name`, `suggested_destination`, `naming_signals`. **Owns:** those three fields. **Guarantees:** fully deterministic; within-batch filename collisions resolved (real-filesystem collision detection is explicitly Module 07's job, not this module's); no Provider, no `tier` awareness (Module 06 hasn't run yet at this point in the chain).

### Module 06 — Confidence & Review
**Purpose:** Score every record's suggested outcome and assign it to a tier that determines how much human oversight it needs before filing. **Inputs:** records with `suggested_name is not None` (confirms Module 05 already ran, so every upstream signal is in its final state). **Outputs:** `confidence_score` (0–100), `confidence_breakdown`, `tier` (`auto`/`approval_required`/`review_required`). **Owns:** those three fields. **Guarantees:** fully deterministic, no cross-record dependency within a batch, no Provider — the narrowest architectural surface of any module built so far, since it only reads *other modules' already-finished judgments*, never file content or bytes itself. Formula and hard floors: `Rules/Confidence Rules.md`.

### Module 07 — Preview, Approval & Execution
**Purpose:** Show the whole batch's proposed outcome, obtain (or forgo, for `auto`-tier) an explicit human decision per record, then actually move/rename/archive real files — the pipeline's only filesystem-mutating stage. **Inputs:** records eligible per the tier gate and CLI-level idempotency (`processed_at is None`), an externally-supplied `ApprovalDecision` set, a configured `destination_root`. **Outputs:** real filesystem moves via `Path.rename()` only; `current_path`/`processed_at`/`approved_by`/`approved_at`/`reversible`. **Owns:** those five fields — the only fields any module writes on a record other than its "home" enrichment stage. **Guarantees:** `review_required` records are never executed, unconditionally, even against a forged decision (checked first, absolutely, inside `evaluate_gate()`); every executed batch is fully undoable by replaying its own log lines in reverse; no Provider of any kind — a human decision is a categorically different kind of input than an AI judgment call, so it's modeled as a plain data structure, not an Engine/Provider pair. Full detail: §7 below and `Release/Module07/MODULE_CONTRACT.md`.

### Module 08 — Logging & Reporting (not yet built)
Per its `Build-out/08 Logging & Reporting/` design references: read-only aggregation over `action_log.jsonl`/`metadata_store.json` to produce `Runtime/Reports/*` (Daily/Weekly Summary, Duplicate/Storage Report). Writes no `FileRecord` field. `Governance/PROJECT_ROADMAP.md` explicitly flags this as "a new kind of read-only aggregation work this pipeline hasn't done before" — its complexity relative to Modules 01–07 is not yet well-calibrated.

---

## 6. Architecture Decisions (summary)

`Governance/ARCHITECTURE_DECISIONS.md` contains 24 numbered, dated, append-only decisions in full Context/Decision/Why/Trade-offs/Consequences form — this section groups and summarizes them by theme so a new engineer knows what exists and why, without needing to read all 24 before starting. **Always read the source document before relying on a decision's exact wording** — this summary intentionally compresses nuance the original preserves.

**Identity and ownership (decisions 1–3, 11).** `file_id` is a permanent, arbitrary UUID (never path- or content-derived) so identity survives a file being moved and never accidentally merges two distinct files. Every `FileRecord` field has exactly one owning module, stated in both directions (that module's "Guarantees," every other module's "DOES NOT MODIFY") — the mechanism that lets seven modules share one growing record with no locks or transactions, just a documented and independently-tested convention. This is what makes an immutability regression test ("every non-owned field is byte-identical before and after") a mechanically checkable fact rather than a matter of trust.

**The Engine/Provider pattern, and its deliberate limits (decisions 4–6, 22).** Judgment-dependent modules (02, 03) are layered batch-function → Engine (deterministic decision logic, fully testable) → Provider (the raw judgment call, an ABC — `ClaudeLiveClassifier`/`ClaudeLiveExtractor` in production, a fake in tests). This cleanly separates "is the decision logic right" from "was the judgment right." Deliberately **not** code-shared between Module 02 and Module 03 even though they're structurally near-identical — coupling two modules' internals would create a hidden dependency neither module's own contract discloses. Fully deterministic modules (04, 05, 06) skip the pattern entirely, since none of their decisions require reading and understanding content. Module 07 skips it for a third, different reason: it depends on a *human decision*, not AI judgment, so a plain `ApprovalDecision` data structure is used instead of a Provider ABC — building a Provider layer for something that isn't a judgment-quality question would be a category error.

**Honesty over guessing (decisions 6, 7, 19).** Deterministic sources are always exhausted before any provider call — never spend judgment-call cost on something already knowable for certain. When a module genuinely can't determine an answer, the result is an explicit `Unknown`/`null`, never a fabricated best guess — and every fallback preserves any other value already legitimately found, names *why* it fell back, and captures a sanitized diagnostic string, not just a bare "failed" flag.

**Privacy (decisions 8–9).** Module 03's `extracted_metadata` is bound by a closed taxonomy per category — any field name a provider returns outside that list is dropped structurally, at the trust boundary, not merely requested via prompt instruction. Bank Statement's `account_last4` gets an exact, deterministic redaction rule (strip non-digits, redact past 4 remaining digits) rather than a qualitative "looks sensitive" judgment call — both verified adversarially, not just against well-behaved test doubles.

**Storage philosophy (decisions 10–12).** One append-only JSON-lines action log; one cumulative JSON metadata store upserted by `file_id`; plain JSON everywhere in v1, no database engine, with the O(N×M) `save_file_record()` cost openly disclosed rather than hidden — a deliberate "avoid over-engineering for v1 volumes" choice, not an oversight (the same discipline that also rejected a blanket redaction scanner and a dedicated destination-config file).

**Versioning and process (decisions 13–17).** Each module has its own independent semver; a separate Pipeline Version is bumped once per module release, never auto-derived. `MODULE_CONTRACT.md` is the only part of a module's design later modules may depend on — internal architecture is free to change without being a breaking change, as long as the contract's behavior holds. A frozen module is not touched except for a project-owner-authorized defect fix or a deliberate new version — "I thought of a nicer way to do this" is never sufficient justification on its own. The pipeline is strictly linear in v1 (no branching, no parallelism), because that's the simplest structure that satisfies the actual requirement.

**Error handling (decision 18, expanded in §7 below).** Two layers, always: the Engine catches every anticipated failure mode and converts it to a named fallback; the batch-orchestration layer wraps that in one more try/except as a last-resort safety net so one bad file never aborts an entire batch.

**Module-07-specific decisions (20–24).** `destination_root` is a new key in the existing `sources.yaml`, not a new config file or an environment variable — the smallest change consistent with the project's existing convention. `reject` is the action-log value for a human declining a suggestion (distinct from Module 01's `skip`, which means something categorically different). An edited destination overrides even an exact-duplicate/superseded-version archive placement — because the entire point of the `approval_required` tier is to let a human catch and correct exactly this kind of automatic misjudgment; `review_required` remains the sole, absolute exception, since no destination is ever resolved for such a record regardless of any decision. `execute_batch()` stages `plan.json` one record immediately before executing that record, never as a separate whole-batch pass, specifically so a crash can never leave the staged and executed destination path diverging.

---

## 7. Error Handling Philosophy

### Layer 1 vs. Layer 2

Every module applies two layers of defense, consistently (decision 18):

- **Layer 1 — the Engine's own anticipated-failure handling.** Every *specifically anticipated* failure mode (a provider is unavailable, a provider raises, content is malformed) is caught inside the module's Engine and converted into a normal, named fallback result — an honest `Unknown`/`null`, a recorded `fallback_reason`, a sanitized diagnostic string. This is precise because the failure mode is understood well enough in advance to handle it specifically.
- **Layer 2 — the batch-orchestration safety net.** No anticipated-failure list is ever complete. The outer batch loop wraps each per-file Engine call in one more try/except, purely as a last resort: log an `error` action, continue to the next file, never abort the whole batch because of one file's genuinely unanticipated problem.

Both layers are required from a module's first implementation, not added reactively after a real crash — this was learned the hard way once (Module 02's release audit finding F3, the origin of the now-standard `_sanitize_error()` helper) and is now a standing rule for every module going forward, not something each module has to rediscover.

### Recovery: crash reconciliation (Module 07)

Module 07 is the only module whose failure modes include "the process itself died mid-batch" (a real OS crash, not a caught exception), because it's the only module doing real, external, stateful work (filesystem moves). `reconcile_batch()` runs unconditionally, first, at the start of every `execute_batch()` call, and classifies every leftover `Runtime/Temp/<batch_id>/plan.json` entry into exactly one of four states:

- **`ALREADY_TERMINAL`** — the record's `FileRecord.processed_at` is already set; nothing to do.
- **`SAFE_TO_RETRY`** — no matching `move_rename`/`archive_*` log line exists for this plan entry; the move never happened (or never completed), so it's safe to attempt fresh.
- **`REPAIRED`** — a matching log line *does* exist (the move genuinely happened) but the `FileRecord`'s own owned fields were never persisted (the crash landed between the filesystem move and the database write); the record is repaired by writing those fields now, without re-attempting the move.
- **`INCONSISTENT_ERROR`** — neither of the above resolves cleanly; surfaced rather than guessed at.

This is why decision 24 (incremental, one-record-at-a-time `plan.json` staging) matters so much: it's what guarantees the staged `to` path and the actually-executed `to` path can never diverge, which is the exact string `reconcile_batch()` depends on to tell `SAFE_TO_RETRY` apart from `REPAIRED` correctly.

### Undo

No trash folder, no backup copy — the action log line *is* the undo mechanism. Undoing a batch means replaying its own `move_rename`/`archive_duplicate`/`archive_superseded_version` log lines in reverse-chronological order, with `from`/`to` swapped. `reversible = false` is a narrow, explicit, surfaced-for-human-review exception — a collision-suffixed move, or a move that landed inside `~ARCHIVE~/` — never a silent failure to record what happened. No file is ever permanently deleted by any code path in this module, on any path, including every failure path.

### The single most safety-critical guarantee in the pipeline

A record with `tier == "review_required"` is never moved or renamed, unconditionally — checked first, absolutely, reading `tier` directly off the live `FileRecord`, never a cached value from the preview stage — even against a forged or mistaken `ApprovalDecision`. This is re-verified at the CLI boundary specifically because `execute()`'s `decisions` parameter is the first external surface through which a forged decision could plausibly arrive from outside the module's own control.

---

## 8. Persistence Model

| Category | Location | Lifecycle |
|---|---|---|
| **Persisted, cumulative, source of truth** | `Database/Metadata/metadata_store.json`, `Database/FileIndex/*.json`, `Database/History/version_history.json`, `Database/Learning/User Corrections.json` | Grows across every run this project has ever made; never auto-truncated. This is the record of everything the pipeline knows. |
| **Persisted, append-only log** | `Runtime/Logs/action_log.jsonl` | Every mutating action, ever, in order. Never rotated or pruned in v1. This is what undo, reconciliation, and (eventually) Module 08's reports all read. |
| **Runtime only, transient** | `Runtime/Temp/<batch_id>/plan.json` | Exists only for the duration of one in-flight Module 07 batch; cleared once that batch reaches a terminal state. Never a long-term record of anything. |
| **Generated, derived, safe to regenerate** | `Runtime/Reports/*` (Module 08's future output) | Computed entirely from the action log and metadata store; nothing else depends on a report file persisting, so it can always be regenerated from source data. |
| **Archived, historical evidence** | `Runtime/UAT/Module0N_UAT_<timestamp>/` | Snapshots of real validation runs, kept for audit purposes, never modified after being written. |

**What should never be modified manually:** `Database/Metadata/metadata_store.json`, `Database/FileIndex/*.json`, `Database/History/version_history.json`, and `Runtime/Logs/action_log.jsonl`. Every guarantee this pipeline makes — reversibility, crash reconciliation, ownership-boundary immutability, the audit trail itself — depends on these files containing exactly what the pipeline's own code produced. A manual edit to the metadata store could silently desynchronize it from the action log (making undo compute the wrong reversal); a manual edit to the action log could make a completed move look unreconciled (or vice versa) the next time `reconcile_batch()` runs. If a value in either file is genuinely wrong, the correct fix is a code-level correction in the owning module (per `Governance/FROZEN_MODULE_CHANGE_POLICY.md` if that module is already frozen), never a hand edit to the data file.

---

## 9. Extension Guide

### How to add a new module

Follow `Governance/ENGINEERING_STANDARD.md`'s nine-stage lifecycle in order, with no stage skipped and no stage's findings auto-fixed without explicit project-owner approval:

```
Design → Architecture review → Freeze → Implementation →
Independent implementation audit → Integration testing →
User Acceptance Testing → Independent release audit
  (incl. mandatory 13-check Pipeline Contract Verification gate) → Release
```

Concretely, in order: write `Build-out/<NN> <Name>/Module <NN> Design.md` stating the module's Purpose and Module Contract shape, every field/action-log type it introduces (cross-checked against every upstream contract for collisions), which decisions are architectural versus business-rule judgment calls, a concrete Test Strategy, and an explicit list of responsibilities reserved for later modules. Get at least one independent architecture review round (two if the first found any Medium-or-higher finding). Get explicit project-owner approval to freeze. Implement exactly what the frozen design specifies. Get an independent implementation audit. Write and execute a real Integration Test Plan against the real upstream chain. Write and execute a real UAT plan against a real external folder with live Claude judgment for any judgment-dependent step. Get a final release audit (the qualitative review plus the mechanical 13-check PCV gate). Only then generate the `Release/Module<NN>/` package and update `Release/VERSIONS.md`, `Release/DEPENDENCY_DIAGRAM.md`, `CHANGELOG.md`, and `src/README.md`.

### Rules every module must follow

- **Never modify a frozen module.** Modules 01–06 are frozen; only a project-owner-authorized genuine-defect fix or a deliberate new version release may touch them (decision 16, `Governance/FROZEN_MODULE_CHANGE_POLICY.md`).
- **Own your fields, and only your fields.** State them explicitly in both directions in `MODULE_CONTRACT.md`; back every non-owned field with a real immutability regression test, not a code-review-only check (decision 2, `ENGINEERING_STANDARD.md` §11).
- **Don't do a later module's job.** State what you deliberately do *not* do, even when it would be easy to add — a module's contract is only meaningful if its scope stayed bounded (decision 3).
- **Exhaust deterministic sources before any provider call**, and default to your own Engine/Provider classes rather than importing a sibling module's, unless a specific, disclosed reason argues for sharing (decisions 5, 6).
- **Never fabricate an answer.** Honest `Unknown`/`null` plus a named, disclosed fallback reason, always (decisions 7, 19).
- **Two layers of error handling from day one** — Engine-level anticipated-failure handling, plus a batch-level outer safety net (decision 18, §7 above).
- **Update the canonical schema doc in the same release cycle** that introduces a new field or action-log type — this has already been missed twice and is now a standing, explicit rule (`ENGINEERING_STANDARD.md` §10).

### Testing expectations

Unit tests use `tmp_path`/`monkeypatch` fixtures, never the real `Database/`/`Runtime/` paths — this exact discipline slipping in eight test functions is what caused Module 07's own real, disclosed test-isolation defect (found, reported, and fixed before UAT began). The full combined suite must pass at 100% before any stage is reported complete. Integration testing validates the module against every real upstream module's actual output, end-to-end, not just in unit-test isolation. UAT validates the complete real user experience — a realistic external folder, the real CLI, and live Claude judgment for any judgment-dependent step (never a canned/routing fake, which is reserved for integration testing only). Full detail: `ENGINEERING_STANDARD.md` §6.

### Release lifecycle

A module's release package (`Release/Module<NN>/`) always contains, at minimum: `MODULE_CONTRACT.md`, `MODULE_STATUS.md` (a permanent, point-in-time snapshot, never updated after generation — `Release/VERSIONS.md` is what stays current), `IMPLEMENTATION_AUDIT.md`, `TEST_RESULTS.md`, `RELEASE_AUDIT.md`, `RELEASE_NOTES.md`, `RELEASE_SUMMARY.md`, `KNOWN_LIMITATIONS.md`, `PRODUCTION_CHECKLIST.md`. A release is not begun until the release audit has concluded with zero unresolved Critical/High/Medium/Low findings (or every remaining Low is explicitly, visibly disposed of). See `ENGINEERING_STANDARD.md` §8–9 for the exact document set and versioning rules.

---

## 10. Current State

### Released modules

| # | Module | Version | Status |
|---|---|---|---|
| 01 | Watch & Ingest | 1.0.1 | Released — one post-freeze patch (a re-scan idempotency defect, Critical, found via Module 06's UAT and fixed under the Frozen Module Change Policy) |
| 02 | Classification | 1.0.0 | Released |
| 03 | Metadata Extraction | 1.0.0 | Released |
| 04 | Duplicate & Version Detection | 1.0.0 | Released |
| 05 | Naming & Destination | 1.0.0 | Released |
| 06 | Confidence & Review | 1.0.0 | Released |
| 07 | Preview, Approval & Execution | 1.0.0 | Released |
| 08 | Logging & Reporting | — | Not started |

**Current Pipeline Version: 0.7.0.** 568/568 regression tests passing across the whole suite. Authoritative, always-current ledger: `Release/VERSIONS.md`.

### Current capabilities

End-to-end, today: a real scan of a Downloads-like folder, live-Claude classification, metadata extraction, exact/near-duplicate and version-chain detection, consistent renaming and destination suggestion, points-based confidence scoring and tiering, a human-reviewed batch preview, approval-gated real filesystem execution (move/rename/archive), immediate audit logging of every action, passive capture of every human correction, and full reversibility via undo (batch or single-action granularity). This is a genuinely complete "a file lands, gets organized correctly, with a human in the loop" cycle for a single source folder.

### Known limitations

- **No autonomous provider exists for any judgment-dependent step.** Modules 02/03's real judgment quality requires a live, agent-driven Claude session; running unattended is safe (fallbacks degrade gracefully) but not functional for real content understanding (`ENGINEERING_STANDARD.md` §16's two-claim "Production Ready" distinction).
- **Learning is passive-only.** `Database/Learning/User Corrections.json` captures every correction but nothing reads it back (`NG6`) — the system does not currently get smarter from correction history.
- **No Module 08 yet** — no periodic Daily/Weekly Summary or Duplicate/Storage report exists; the only visibility into pipeline activity today is the raw action log.
- **Single-source only** (multi-source is `ROADMAP.md` Version 3 scope), **plain JSON storage** (SQLite migration is Version 2 scope, not built), and the **O(N×M) `save_file_record()` cost** (decision 11) — disclosed, not yet remediated, and worth re-checking before Module 08, since it will read the same store.

A deeper, evaluative pass on these and other findings (technical debt, repository hygiene, module coupling, performance projections at 10k/100k files, and ranked recommendations) exists as a separate document: `Governance/PROJECT_RETROSPECTIVE_2026-07-13.md`. That document is opinion and assessment; this document is structural fact — read that one for "what should change," this one for "how does this actually work."

### Future roadmap

**Version 2** (next, once v1 is proven): Scheduled execution mode wired in earnest; `Documents/` subfolder expansion once real volume justifies it; a possible SQLite migration; multi-document PDF splitting; per-person/per-company subfolders. **Version 3** (later): real-time Watch Folder execution mode (a background daemon); multi-source support (Desktop, Google Drive, OneDrive, Dropbox); active learning from accumulated corrections. **Immediately next in the linear chain:** Module 08 (Logging & Reporting) — not yet started. Full detail: `ROADMAP.md`.

---

*This document does not modify any existing file. It is new, permanent project documentation, cross-referencing rather than duplicating `Governance/ARCHITECTURE_DECISIONS.md`, `Governance/ENGINEERING_STANDARD.md`, every module's `MODULE_CONTRACT.md`, `Rules/*.md`, `Release/VERSIONS.md`, `Release/DEPENDENCY_DIAGRAM.md`, `README.md`, `ROADMAP.md`, and `src/README.md`. No code was modified. Module 08 was not begun.*
