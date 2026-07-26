# TD-01 Production Validation Plan

**Date:** 2026-07-26 · **Status:** Planning only — nothing below has been executed, no API call has been made, no cost has been incurred.
**Governing instruction:** "We are entering a Production Validation phase for TD-01. The goal is not to build new functionality. The goal is to verify that the newly implemented Claude provider actually improves the product when compared with the existing deterministic pipeline. Follow the Engineering Change Playbook. Phase 1 — Production Validation Plan. Produce a validation plan only... Do not execute any API calls. Do not consume any paid tokens."
**Depends on:** `ENGINEERING_CHANGE_PLAYBOOK.md` (process this plan operates under), `REAL_WORLD_VALIDATION_PLAN.md` / `METRICS_DEFINITION.md` / `DATASET_GUIDELINES.md` / `BENCHMARK_SPECIFICATION.md` (existing frameworks this plan reuses rather than re-invents), `Tests/Provider Evaluation Harness/TD-01 v0.9 Validation Report.md` (what was already validated — architecture, wiring, fallback behavior — and what was explicitly left open: real-key judgment quality), `Rules/Confidence Rules.md` (tier thresholds), `TECHNICAL_DEBT_REGISTER.md` TD-01 (the item this validation closes the remaining gap on).

---

## 0. Where this sits in the Engineering Change Playbook

TD-01 v0.9 already completed stages 1–7 (Observation → Regression) and a first pass at stage 8 (Validation) — the harness dry run in `TD-01 v0.9 Validation Report.md` proved the architecture, consent flow, and fallback behavior are correct, but explicitly disclosed one open item: *"this validation cycle proves the architecture... it does not prove Claude actually produces good classifications/extractions on real files... requires a user-supplied `ANTHROPIC_API_KEY` and a real harness run."*

This Production Validation phase is that outstanding piece of stage 8, not a new change. Per `ENGINEERING_CHANGE_PLAYBOOK.md` §4, real-world re-validation is **required** (not optional) here because two of its three trigger conditions are already met: TD-01 is classified High severity, and the change touches classification and metadata-extraction logic directly. §4 also specifies the minimum bar for when it's triggered: reconstruct or gather a dataset with clear fidelity, execute the real pipeline code (not a simulation) in isolated state, and produce a full before/after diff of every affected record. Sections 2 and 4 below are built to satisfy exactly that bar.

This document is Phase 1 only: the plan. No dataset has been touched, no provider call has been made, no code has changed. Phase 2 (execution) requires separate, explicit authorization after this plan is reviewed — the same staged-authorization posture already used for C2 (`C2 First Live Run Plan.md`) and required by `REAL_WORLD_VALIDATION_PLAN.md` throughout.

---

## 1. Prerequisites

### 1.1 Anthropic API key configuration

- `ANTHROPIC_API_KEY` must be set as an environment variable in whatever shell actually runs the validation. It is never written to `src/config/sources.yaml` or any other project file — confirmed by the code itself (`src/providers/claude.py`'s `_client()` reads only the environment variable) and by `sources.yaml`'s own inline comment: *"The API key itself is never stored in this file."*
- The provider is switched on only through the sanctioned CLI path: `python -m src.cli provider enable` — never by hand-editing `sources.yaml`. This command is already built and tested (TD-01 v0.9): it shows a mandatory disclosure (what gets sent, that it costs real money, that a key must be set) and requires an explicit typed confirmation before writing `ai_provider_consent: true`.
- Key presence is checked structurally, never by printing the value: `python -m src.cli provider status` reports whether consent is on and whether a key is set, without ever displaying it. This plan does not require the key's value to be shared with Claude in chat, written into any report, or logged anywhere — "key present: yes/no" is the only fact that should ever appear in this validation's evidence trail.
- The key belongs to the project owner and is supplied by them, in their own environment, at execution time — not before.

### 1.2 Safety checks

- **Scope ceiling for this phase: scan → run (classify/extract) → preview only.** No `execute` step under any circumstance — nothing gets moved, renamed, or deleted, mirroring `REAL_WORLD_VALIDATION_PLAN.md` §6's stop conditions and the staged-authorization posture C2 already established.
- **Isolated storage, reusing the already-fixed harness mechanism.** The comparison run's writes go through the same isolate/restore pattern `run_harness.py` uses (`_isolate_storage()`/`_restore_storage()`, backed by `tempfile.TemporaryDirectory()`), which has its own regression test proving real storage paths are restored even on an error path. This keeps every write out of the real production `Database/Metadata/metadata_store.json` (866 real records) and `Runtime/Logs/action_log.jsonl` (7,423 lines) — verified after execution by confirming those two files are byte-identical before and after (`git status`/hash comparison), not assumed.
- **All existing non-negotiables apply unchanged:** nothing is ever deleted; every action must remain reversible; superseded files get archived, never removed. This phase performs no file-system mutation of any kind, so these guarantees are structurally satisfied rather than merely intended.
- **Privacy:** `DATASET_GUIDELINES.md` §2 governs what this validation's own report may contain — structural facts only (`file_id`, `category`, `tier`, `confidence_score`, `confidence_breakdown` deduction *names*, token counts, timestamps), never full file content, real account/ID numbers, real names other than the operator's, or a verbatim excerpt from a real document. The two named real-world difficult cases (the legal filing, the payment-screen screenshot) are exactly the kind of content this rule exists for.
- **The disable path gets exercised, not just assumed to exist.** After the comparison run, `python -m src.cli provider disable` is run and confirmed to return `ai_provider_consent` to `false` — validating the actual rollback mechanism (§6) rather than taking its correctness on faith.
- **No shortcuts around the opt-in gate.** This phase uses the standard `provider enable` flow exactly as any real user would — no bypass, no direct construction of `ClaudeAPIClassifier`/`ClaudeAPIExtractor`, no test-only code path introduced to force a live call.

### 1.3 Cost estimation before execution

- Reuses `run_harness.py`'s existing, already-tested cost model — no new estimation code needs to be written for this phase. Pricing table (`_PRICE_PER_MILLION_TOKENS_USD`): `claude-sonnet-5` at $3.00/million input tokens, $15.00/million output tokens. `_estimate_cost()` returns `None` (not a silently-wrong `$0.00`) if a model has no pricing entry — that discipline is reused unchanged.
- Each provider call is bounded: `max_tokens=512` per call (classify and extract are separate calls), input text truncated to `_MAX_TEXT_CHARS`, vision-mode images bounded by `_MAX_IMAGE_BYTES`. Deterministic-by-extension files (Archive, Application, Video by extension, etc.) never reach a provider call at all and cost nothing.
- **Procedure, to run before any paid call is made:** (1) finalize the dataset per §2 below; (2) count exactly how many files in it are provider-eligible (text-bearing or vision-mode — i.e. exclude anything deterministic); (3) compute a worst-case bound (every eligible file hits the 512-token output cap on both calls) and an expected-case estimate (based on the short, single-document prompt sizes already visible in `claude.py`'s system prompts); (4) present both figures as a dollar range to the project owner; (5) require an explicit go-ahead — reusing the harness's own mandatory confirmation-prompt mechanism (`main()`'s `-y`/interactive-confirmation gate), not a new one.
- Given the dataset size this plan proposes (§2 — dozens of files, not the full 866-record production store), the expected cost is small — low single-digit dollars at the stated pricing — but the exact figure is computed and shown at execution time, never assumed here.

### 1.4 Rate-limit strategy

- Confirmed directly from `src/providers/claude.py` (lines ~227 and ~295): a `RateLimitError` is caught in the same `except` clause as a connection error and converted straight into `ClassificationProviderUnavailableError`/`ExtractionProviderUnavailableError` — **there is no retry and no backoff.** This is `TECHNICAL_DEBT_REGISTER.md` TD-31, an already-disclosed, intentional v1 limitation ("Revisit alongside TD-01").
- The practical consequence for this validation: a rate-limited file falls back to `Category.UNKNOWN`/null fields exactly as if the provider had never been consulted — indistinguishable in the metrics from "no key configured" unless the action log is checked. That makes rate-limit avoidance a *measurement-integrity* issue for this phase, not just an operational nuisance: an undetected rate limit would understate the provider's true accuracy.
- **Strategy is prevention, not recovery**, since recovery doesn't exist in the current code:
  - Process files strictly sequentially — this is already how the pipeline and the harness work; no concurrent provider calls exist anywhere in the codebase to disable.
  - Keep the validation dataset small (§2 proposes dozens of files, not hundreds) — deliberately conservative relative to typical Anthropic API rate limits for a single-key, low-volume script.
  - After the run, scan the isolated action log specifically for `fallback_reason: "provider_exception"` entries whose error text indicates a rate limit, and exclude those files from the accuracy/quality metrics — reported separately as "not actually exercised," never folded into "the provider tried and got it wrong" (mirrors the same accuracy-definition discipline `run_harness.py`'s own docstring already establishes).
  - Running this validation at full real-Downloads scale (866+ files) is explicitly **out of scope** for this phase — TD-31 would need to be addressed first if that scale is ever attempted with a live key.

---

## 2. Validation dataset

Two components, combined, per the governing instruction's "use the existing real Downloads dataset where appropriate" plus the six named difficult cases.

### 2.1 The existing real Downloads dataset — bounded, sampled subset

The real production `Database/Metadata/metadata_store.json` already contains **866 real records** from the user's actual `/Users/vicky/Downloads` folder (populated by the earlier local scan — `Local Scan Execution Guide.md`), entirely under deterministic-only conditions (`ai_provider_consent` has been `false` for the store's entire existence). Current real category distribution:

| Category | Count |
|---|---|
| Image | 431 |
| Unknown | 321 |
| Archive | 56 |
| Video | 29 |
| Application | 22 |
| Screenshot | 5 |
| Audio | 2 |

The 321 real `Unknown` records are exactly the population TD-01 exists to affect — real files that never got a judgment pass. Re-processing all 866 is unnecessary and counter to §1.3/§1.4's cost and rate-limit discipline, since Image/Archive/Video/Application records are almost entirely resolved deterministically already and would never reach a provider call. This plan proposes:

- **A stratified sample of 20–30 records from the 321 real `Unknown` records** — stratified by original file extension (structural metadata only, no content needs to be read to stratify), drawn by a fixed, documented, reproducible method (e.g. every Nth `file_id` in sorted order, or a fixed random seed recorded in the eventual results) so the sample is auditable, not hand-picked to flatter the outcome.
- **A small control sample from already-correct deterministic categories** — roughly 10 records each from the real `Image` and `Application` populations (chosen specifically because §2.2 below already covers Screenshot as a named difficult case) — to test for regression, not just improvement (§5, S2).

All of this runs against an **isolated copy** of `Database`/`Runtime` (§1.2), never the real store directly, so the existing 866-record production data is read once (to build the sample list) and never re-written by this validation.

### 2.2 The six previously identified difficult cases

| Case | Source | Sourcing note |
|---|---|---|
| **INC-34 legal document** | Real file, found during `Tests/C2 Sandbox Product Validation Report.md` Finding 1 — a 16-page Indian MCA corporate filing (Form INC-34, e-AOA), previously fell back to `Unknown`. | Use the real file if still present at `/Users/vicky/Desktop/sample`; if not, the harness's already-built synthetic stand-in (`legal_form.pdf`, documented as mirroring this exact case) is the disclosed fallback. |
| **Renamed/resized screenshot** | Real file, Finding 2 of the same report — a payment-app screenshot with a random UUID filename and 590×1280 dimensions (outside `_COMMON_SCREEN_RESOLUTIONS`), previously fell back to generic `Image`. Contains financial details (amount, partial account/card numbers) — elevated privacy sensitivity, already flagged in the C2 report. | Same real-file-first, synthetic-fallback (`b3f0a1c2-....jpg`) sourcing note as above. Per §1.2, only structural facts about this file (category, tier) may ever appear in the resulting report — never its visible content. |
| **Invoice** | No confirmed real example exists yet — the real dataset has zero `Invoice`-category records (expected, since Invoice requires a judgment pass never yet run against real data). | Resolved at execution time, not presumed here: first check whether any of the §2.1 sampled real `Unknown` records is actually an invoice on inspection; if none is found, use a synthetic invoice-shaped fixture. Whichever path is used is disclosed plainly in the eventual results — this plan does not pre-select one to make the outcome look cleaner. |
| **Contract** | Same situation as Invoice. | Same resolution approach as Invoice, disclosed the same way. |
| **Images** | Real, already well-represented — 431 real `Image` records already classified correctly by the deterministic path. | Covered by the §2.1 control sample (~10 records) — tests that the provider doesn't regress a case that already works, not just whether it helps. |
| **Applications** | Real, already well-represented — 22 real `Application` records already classified correctly by the deterministic path. | Covered by the §2.1 control sample (~10 records) — same regression-testing purpose as Images. |

Total dataset size across §2.1 and §2.2: roughly **40–50 files** — small enough to keep §1.3's cost and §1.4's rate-limit exposure conservative, large enough to produce a real, defensible before/after comparison rather than an anecdote.

### 2.3 Privacy handling for this dataset

This is **Live Validation Data**, not Benchmark Corpus Data (`DATASET_GUIDELINES.md` §2 vs. §3) — real files, read in place, never copied into the project vault, never anonymized-and-committed. The one rule that governs everything written about it: *read real files freely, exactly as the product already does; write down structure and outcomes, never content* (`DATASET_GUIDELINES.md` §6).

---

## 3. Metrics to collect

Every metric below reuses an existing, already-defined formula (`METRICS_DEFINITION.md`) or an already-implemented computation (`run_harness.py`) — nothing here is a new metric invented for this plan.

| # | Metric | Formula / source |
|---|---|---|
| 1 | **Unknown %** | `METRICS_DEFINITION.md` §2.5 — Unknown-category files ÷ total files processed. Reported for Before and After on the identical file set (§4). |
| 2 | **Extraction completeness** | `METRICS_DEFINITION.md` §2.2 — required fields populated (non-null) ÷ total required fields, per category. Computed directly from `extracted_metadata`, no operator spot-check needed to detect a null. |
| 3 | **Naming quality** | `run_harness.py`'s existing `naming_quality` metric — fraction of files whose suggested name required no fallback fields (`naming_signals.fields_fell_back` empty). Equivalent in spirit to `METRICS_DEFINITION.md` §2.3's Naming Acceptance Rate, but computed automatically since this phase has no approval/edit step. |
| 4 | **Confidence distribution** | `METRICS_DEFINITION.md` §3.3 — histogram of `confidence_score` and `confidence_breakdown` deduction frequency, per category, Before vs. After. |
| 5 | **Auto / Approval / Review %** | Direct tier counts against `Rules/Confidence Rules.md`'s thresholds (95–100 `auto`, 80–94 `approval_required`, below 80 `review_required`). |
| 6 | **Processing time** | `METRICS_DEFINITION.md` §4.2 — files/second per stage, Before vs. After. The After run is expected to be slower (real network latency per call) — reported as a fact, not treated as a defect. |
| 7 | **Token usage** | Already logged per call (`ClassificationProviderMetadata.token_usage` / `ExtractionProviderMetadata.token_usage`, an additive field shipped in TD-01 v0.9). Summed input/output tokens across the After run. |
| 8 | **Estimated API cost** | `run_harness.py`'s `_estimate_cost()`, computed from the real token usage the After run actually logs — reported alongside the §1.3 pre-run estimate as a stated-vs-actual comparison, not just a projection. |

All metrics reported with raw counts alongside percentages (`METRICS_DEFINITION.md` §1 — "42/45, 93.3%," never a bare percentage), broken out per category wherever the sample size makes that meaningful.

---

## 4. Side-by-side comparison

**Before TD-01** and **After TD-01** are computed on the *identical* file set (§2) — the real records already in the production store (their existing, already-computed deterministic-only values) versus those same records re-processed with the Claude provider enabled, in isolated storage. This same-file-set requirement is what `ENGINEERING_CHANGE_PLAYBOOK.md` §4 means by "a full before/after diff... of every affected record," not a comparison across two different populations.

Report format:

| Metric | Before TD-01 | After TD-01 | Delta |
|---|---|---|---|
| Unknown % | NN/NN (NN.N%) | NN/NN (NN.N%) | ±NN.N pp |
| Extraction completeness (per category) | NN/NN (NN.N%) | NN/NN (NN.N%) | ±NN.N pp |
| Naming quality | NN/NN (NN.N%) | NN/NN (NN.N%) | ±NN.N pp |
| Confidence distribution (mean / median) | NN / NN | NN / NN | ±NN |
| Auto % | NN/NN (NN.N%) | NN/NN (NN.N%) | ±NN.N pp |
| Approval-required % | NN/NN (NN.N%) | NN/NN (NN.N%) | ±NN.N pp |
| Review-required % | NN/NN (NN.N%) | NN/NN (NN.N%) | ±NN.N pp |
| Processing time (files/sec) | NN.NN | NN.NN | ±NN.NN |
| Token usage (input / output) | n/a (no provider) | NN / NN | n/a |
| Estimated API cost | $0.00 | $N.NN (actual, from token usage) | +$N.NN |

Plus a separate, named pass/fail line for each of the four qualitative difficult cases:

| Case | Before TD-01 | After TD-01 | Resolved? |
|---|---|---|---|
| INC-34 legal document | Unknown | (category assigned) | Y/N |
| Renamed/resized screenshot | Image (misclassified) | (category assigned) | Y/N |
| Invoice | Unknown | (category assigned) | Y/N |
| Contract | Unknown | (category assigned) | Y/N |

This table is populated only during Phase 2 execution — every cell above is a placeholder, not a projection.

---

## 5. Success criteria — defined before any run

### 5.1 Safety criteria (zero-tolerance, block acceptance regardless of quality results — mirrors `REAL_WORLD_VALIDATION_PLAN.md` §9's A1/A2/A3 treatment)

| # | Criterion | Threshold |
|---|---|---|
| S1 | Data-loss / unauthorized-action findings | Zero. Real production `Database/`/`Runtime/` files confirmed byte-identical before and after (§1.2). |
| S2 | Control-group regression (§2.1's Image/Application sample) | Zero files that were correctly classified Before become incorrectly classified After. |
| S3 | Auto-tier correctness on the control group | No decrease. A provider that makes `auto` less safe is a blocking regression regardless of any Unknown-rate improvement elsewhere. |

Any run failing S1, S2, or S3 stops immediately and is escalated to the project owner before any further validation proceeds — these are safety criteria, not quality criteria, and are held to a stricter standard than everything below.

### 5.2 Quality criteria (the actual question this phase exists to answer)

| # | Criterion | Threshold |
|---|---|---|
| Q1 | Unknown Rate reduction on the §2.1 Unknown-sample subset | Reduced by at least 30 percentage points. |
| Q2 | Naming-fallback rate reduction on the same subset | Reduced by at least 20 percentage points. |
| Q3 | Extraction-completeness improvement on the same subset | Improved by at least 25 percentage points. |
| Q4 | Named difficult cases (§2.2) resolve to their documented correct category | All of: INC-34 → Document, screenshot → Screenshot, Invoice example → Invoice, Contract example → Contract. Reported individually, not blended into an aggregate. |

### 5.3 Cost / operational criteria

| # | Criterion | Threshold |
|---|---|---|
| C1 | Actual API cost for the full validation run | Under $5.00 (starting ceiling; confirmed against the §1.3 pre-run estimate before the run begins, and against the real post-run token-usage total afterward). |
| C2 | Rate-limit-induced silent fallbacks (§1.4) | Zero undetected. Any that occur are identified via the action log and excluded from Q1–Q4's accuracy calculations, reported separately, never counted as "the provider tried and got it wrong." |

**What "success" means here:** meeting S1–S3 is mandatory to consider the run valid at all. Meeting Q1–Q4 and C1–C2 is what would actually justify recommending TD-01's provider for real, everyday use — but a run that meets S1–S3 and *fails* some of Q1–Q4 is still a complete, valid, reportable result, not a failed validation. This mirrors `REAL_WORLD_VALIDATION_PLAN.md` §10's own explicit rule: this framework does not modify or tune the pipeline to pass its own criteria. The honest answer is the deliverable, whichever way the numbers land.

---

## 6. Risk assessment

### 6.1 Privacy implications

Real file content — including the payment-screenshot's financial details and the legal filing's corporate/personal details — is sent to Anthropic's API for any file processed in text or vision mode. This is a real, new-in-kind exposure relative to today's shipped default (where no file ever leaves the local machine without a live, interactively-driven Claude session already looking at it) — the same category of exposure the TD-01 consent flow was built specifically to gate, now actually exercised against real content instead of only test fixtures for the first time.

Mitigations already in place: the opt-in `provider enable` disclosure/confirmation (§1.1); `DATASET_GUIDELINES.md`'s rule that this validation's own report may only ever contain structural facts, never real content (§1.2, §2.3). Residual risk outside this project's control: Anthropic's own API data-handling and retention policy governs whatever content is actually sent — the project owner should be comfortable with that policy before authorizing Phase 2, independent of anything this plan can mitigate internally.

### 6.2 Failure modes

| Failure mode | What happens | Mitigation |
|---|---|---|
| Rate limiting | Silent fallback to `Unknown`/null (no retry — TD-31) | §1.4's prevention strategy; post-run action-log audit excludes these from accuracy metrics. |
| Malformed/unparseable API response | `ClassificationProviderError`/`ExtractionProviderError` → same safe fallback | Already unit-tested (`test_claude.py`'s unparseable-response cases); no new risk introduced by this validation. |
| API key exposure | Key leaked into a file, log, or report | Never stored outside the environment variable; never printed by `provider status`; this plan's own evidence trail records only "key present: yes/no." |
| Network/connection failure mid-run | Same safe per-file fallback; batch does not halt | Covered by Module 02/03's existing outer-safety-net guarantee, already tested. |
| Cost overrun | Real spend exceeds expectation | §1.3's mandatory pre-run estimate + confirmation gate; §5.3's C1 ceiling. |
| Isolation leak (writes touch real production data) | Would corrupt the real 866-record store / real action log | Reuses the harness's already-fixed, regression-tested isolate/restore mechanism rather than new isolation code; explicitly verified byte-identical after the run, not assumed. |

### 6.3 Rollback procedure

This phase never runs `execute` — no file is ever moved, renamed, or deleted on the real filesystem, so there is nothing to "undo" in the traditional sense. Two things are actually reversible here, and both are already built and tested:

- **Config rollback:** `python -m src.cli provider disable` restores `ai_provider_consent: false` immediately — returning to today's exact shipped default. Required to be run and confirmed at the end of Phase 2 (§1.2), not just assumed to work.
- **Data rollback:** all writes during the comparison run happen inside isolated temp storage (`tempfile.TemporaryDirectory()`); the entire "rollback" is that directory's normal cleanup, since nothing real was ever touched.

### 6.4 Safe disable path

Already implemented and covered by TD-01 v0.9's own test suite — this plan requires no new disable mechanism, only that the existing one be explicitly exercised once as part of closing out Phase 2, per §1.2. The disable path is also the direct answer to "what if the After results look worse than Before": no code change is required to revert — the pipeline returns to its long-standing, already-proven-safe default the moment consent is turned off.

---

## 7. What this plan deliberately does not do

It does not run any code, make any API call, or spend any money — every number in §4's comparison table is a placeholder. It does not select the final Invoice/Contract example (§2.2) — that's a small, disclosed decision made at execution time, not pre-committed here to avoid the appearance of picking a favorable case. It does not change the pipeline in any way to make it more likely to pass §5's criteria — per `REAL_WORLD_VALIDATION_PLAN.md` §10's same standing rule, restated here because it applies directly to TD-01's own provider. It does not authorize Phase 2 — that is a separate, explicit decision for the project owner, after reviewing this plan.

---

**Stopping here per the governing instruction. Awaiting review and separate authorization before Phase 2 (execution) begins.**
