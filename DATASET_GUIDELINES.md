# Dataset Guidelines — Real-World Validation

**Date:** 2026-07-20 · **Status:** Framework design — governs data not yet collected
**Companion to:** `REAL_WORLD_VALIDATION_PLAN.md` (the process this data feeds), `BENCHMARK_SPECIFICATION.md` (how a subset of this data becomes a reusable, repeated-release benchmark corpus)

This document governs two different kinds of data, which must not be confused with each other:

- **Live Validation Data** — the operator's real, actual Downloads folder, used once (or across several real sessions) to answer "does this work on my real files." Ephemeral by design.
- **Benchmark Corpus Data** — a small number of anonymized, checked-into-the-vault datasets, derived from real-world patterns but stripped of anything sensitive, used to compare pipeline behavior consistently release over release (`BENCHMARK_SPECIFICATION.md`).

Conflating these two is the single easiest way to accidentally commit sensitive real data into this project's permanent, version-controlled record. This document exists specifically to prevent that.

---

## 1. Core privacy principle

Running the pipeline against a real Downloads folder exposes it to nothing it doesn't already see in ordinary use — reading file content locally, as part of a live Claude session, is the product's normal operating mode (`README.md`'s own workflow description). **What changes during validation is not what the pipeline reads — it's what gets written down afterward.** A validation report, a finding, or a benchmark dataset is a new, durable artifact this project didn't previously have, and every guideline below governs that artifact, not the pipeline's ordinary operation.

## 2. Live Validation Data — rules

### 2.1 Where it lives

Live validation runs against the operator's actual Downloads folder, in place, exactly as Manual mode is designed to operate — never copied into the project vault first. The project's own `Database/`/`Runtime/` structure already stores only metadata and logs, never raw file copies (`Governance/ARCHITECTURE_DECISIONS.md`'s consistent pattern throughout every module) — validation follows the same rule. If a validation run needs its own isolated evidence trail, use a dedicated `Runtime/Validation/<timestamp>/` archive (mirroring the existing `Runtime/UAT/Module<NN>_UAT_<timestamp>/` convention) containing the resulting metadata store snapshot, action log, and findings report — never a copy of the source files themselves.

### 2.2 What never gets written into project documentation

No failure report, findings summary, or CHANGELOG-style entry may ever contain: full file contents, real account/routing/card numbers, real government ID numbers, full real names of anyone other than the operator, real street addresses, real dollar amounts tied to an identifiable real transaction, or a verbatim excerpt from a real sensitive document. This is a direct extension of Module 03's own existing `account_last4`-style redaction convention (`Build-out/03 Metadata Extraction/Module 03 Design.md`) applied to validation reporting instead of extracted metadata.

### 2.3 What's safe and useful to record instead

Everything `METRICS_DEFINITION.md` and `REAL_WORLD_VALIDATION_PLAN.md` §8 actually need is already structural, not content-based: `file_id`, `category`, `tier`, `confidence_score`, `confidence_breakdown` (deduction *names*, not the underlying values), action types, timestamps, and the operator's edit-reason tag (§5.3 of `REAL_WORLD_VALIDATION_PLAN.md`). None of this requires quoting a document's real content. When a specific example is genuinely needed to illustrate a finding, describe its *shape* ("a bank statement PDF where the vendor field extracted as null") rather than its *content*.

### 2.4 Retention

Live Validation Data's `Runtime/Validation/<timestamp>/` archives follow the same retention posture as `Runtime/UAT/` archives already do — kept as the project's audit trail, not deleted (per `CLAUDE.md`'s non-negotiables), but understood to contain metadata/logs only, never raw file copies, so retaining them indefinitely carries none of the exposure that retaining actual documents would.

## 3. Benchmark Corpus Data — rules

Unlike Live Validation Data, a Benchmark Corpus dataset is meant to be reused, referenced, and checked into the project vault permanently (`BENCHMARK_SPECIFICATION.md`) — which makes its privacy bar meaningfully higher, not lower.

### 3.1 Anonymization is mandatory before a file enters the corpus

No file derived from a real document may enter `Tests/` (or wherever the benchmark corpus is ultimately stored, per `BENCHMARK_SPECIFICATION.md`) without first being anonymized. Anonymization here means: real names replaced with clearly-fictional placeholder names, real account/ID numbers replaced with structurally-valid but fake values (same digit count/format, never a real issued number), real dollar amounts either replaced or left as round, clearly-illustrative numbers, real addresses replaced with fictional-but-plausible ones, and any content unique enough to identify a real person or institution removed or genericized.

This mirrors `Tests/README.md`'s own existing standing instruction — *"same privacy care as production: no real bank account numbers, etc."* — which this document formalizes into an explicit process rather than a one-line reminder.

### 3.2 Two acceptable sourcing paths

- **Path A — Synthetic construction from a real pattern.** The operator describes the *shape* of a real scenario (e.g. "I have a folder with three years of overlapping resume versions and a lot of screenshot clutter") and a new, fully synthetic dataset is built to match that shape, containing zero bytes of real content. This is the preferred path — it carries zero residual privacy risk because nothing real ever touches the corpus.
- **Path B — Redaction of a real file.** Used only when a specific real document's *structure* (not its content) is genuinely hard to reproduce synthetically — for instance, an unusual real PDF layout that a synthetic file wouldn't faithfully exercise. Every field of real, identifying content is replaced per §3.1 before the file leaves Live Validation status. This path requires a second-person or deliberate re-review step before the file is committed — never a single pass by whoever is in a hurry to finish the benchmark — because it is the one path where a real document is the starting point.

### 3.3 What the corpus is not allowed to contain, ever

Real financial account numbers, real tax IDs/SSNs/national ID numbers, real medical information, real legal case details tied to an identifiable person, or any file the operator would not be comfortable existing in a version-controlled, potentially long-lived project folder indefinitely. If there's any doubt, the file does not go in the corpus — Path A (fully synthetic) is always available as a fallback with zero risk.

## 4. Dataset collection process

### 4.1 For Live Validation

1. Identify a real Downloads folder to validate against (the operator's own, or, if collecting evidence across more than one real-world environment, another consenting person's — see §5).
2. Confirm the folder is genuinely representative — not pre-cleaned or staged for the test. A folder tidied up in advance defeats the entire purpose of this milestone (`VERSION_09_PLAN.md`'s core goal is observing real, uncontrolled conditions).
3. Run validation per `VALIDATION_CHECKLIST.md`, capturing evidence per §2 of this document.
4. Archive the run under `Runtime/Validation/<timestamp>/` and file findings per `REAL_WORLD_VALIDATION_PLAN.md` §8.

### 4.2 For Benchmark Corpus construction

1. Identify a small number of distinct real-world "shapes" worth having permanent, repeatable coverage for — `BENCHMARK_SPECIFICATION.md` §2 defines the initial set (e.g. a finance-heavy folder, a media-heavy folder, a long-neglected multi-month backlog).
2. For each shape, build a dataset via Path A (preferred) or Path B (§3.2) of this document.
3. Independently review the finished dataset for any residual real/identifying content before it's committed — this review is itself a checklist item in `BENCHMARK_SPECIFICATION.md`'s dataset manifest requirements, not an informal step.
4. Register the dataset in the benchmark manifest (`BENCHMARK_SPECIFICATION.md` §3) with its known answer key (ground truth) recorded alongside it.

## 5. If validation ever involves anyone other than the project owner

Everything above assumes the operator validating the tool is also the owner of the files being processed. If real-world validation is ever extended to a second person's real Downloads folder (a natural next step once `PRODUCT_ROADMAP.md`'s Distribution track becomes relevant), that person's explicit, informed consent is required before their files are processed for validation purposes, and §2's rules apply with zero exceptions to anything derived from their data — this is also the first moment `PRODUCT_ROADMAP.md` §8's flagged gap (no documented data-handling/privacy policy) stops being a future concern and starts being a blocking one. Out of scope for this v0.9.0 framework, which assumes single-operator, single-owner validation only, but flagged here so it isn't rediscovered as a surprise later.

## 6. Summary — the one rule that matters most

**Read real files freely, exactly as the product already does. Write down structure and outcomes, never content.** Every other guideline in this document is a specific application of that one sentence.
