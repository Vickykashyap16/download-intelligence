# Benchmark Specification — Real-World Validation

**Date:** 2026-07-20 · **Status:** Framework design — no benchmark dataset has been built yet
**Companion to:** `REAL_WORLD_VALIDATION_PLAN.md` (the process), `METRICS_DEFINITION.md` (what gets measured), `DATASET_GUIDELINES.md` §3 (how benchmark datasets must be built and anonymized)

`REAL_WORLD_VALIDATION_PLAN.md` governs a single point-in-time question: does the pipeline work on real data, right now. This document governs a different, longer-lived question: **as the pipeline changes over future releases, does it get better, stay the same, or quietly regress?** Answering that requires something Live Validation Data structurally can't provide — a fixed, repeatable dataset with a known answer key, run identically against every future release and compared on equal footing.

---

## 1. Relationship to `Tests/`

This benchmark corpus is a sibling to `Tests/`, not a replacement for it. `Tests/README.md`'s existing five folders (`Small Batch`, `Mixed Downloads`, `Duplicate Files`, `Corrupted Files`, `Large Batch`) are **scenario-based** — each isolates one pipeline capability. The benchmark corpus defined here is **composite-based** — each dataset simulates an entire realistic Downloads folder as a whole, the way `Mixed Downloads` gestures at but doesn't commit to being a permanent, versioned, scored comparison point. `Tests/` continues to serve unit/integration/UAT per-module validation exactly as it always has; the benchmark corpus exists specifically to serve the cross-release comparison need this milestone introduces. Recommended home once datasets exist: `Tests/Benchmark Corpus/`, keeping the existing `Tests/` folder as the single home for all executable validation data rather than creating a new top-level folder.

## 2. The initial benchmark scenario set

Five named scenarios, chosen to cover the realistic "shapes" a Downloads folder takes that no single existing `Tests/` folder represents in combination. Each is a standalone dataset with its own manifest (§3) and answer key (§4).

| Scenario ID | Name | What it simulates | Why it matters |
|---|---|---|---|
| BM-01 | **Finance-Heavy** | Months of invoices, bank statements, and receipts accumulated without filing — the category mix `Rules/Confidence Rules.md` and `Rules/Naming Rules.md` were most built around | Tests extraction accuracy and naming/destination quality where the stakes (financial records) are highest |
| BM-02 | **Document Churn** | Multiple overlapping version chains (resumes, contracts with redlines) plus a few exact re-downloads mixed in | Tests Module 04's version-vs-duplicate distinction under realistic ambiguity, not the clean single-chain example in `Tests/Duplicate Files/` |
| BM-03 | **Media-Heavy** | A large volume of screenshots, photos, and a few videos, mixed with the occasional misfiled document | Tests the screenshot-heuristic false-positive risk already disclosed in `TECHNICAL_DEBT_REGISTER.md` TD-16, and Module 03's disclosed video-metadata gap (TD-18) |
| BM-04 | **Long-Neglected Backlog** | A large (100+ file), multi-month, uncleaned folder — closer to `Tests/Large Batch/` in volume but with realistic category variety rather than volume alone | Tests whether the accepted-at-test-scale trade-offs (`TECHNICAL_DEBT_REGISTER.md` TD-03/TD-04/TD-06) actually surface at real accumulated scale |
| BM-05 | **Adversarial Mix** | Corrupted/locked files, zero-byte files, unusual extensions, and ambiguous edge-case content deliberately included alongside ordinary files | Tests that `Tests/Corrupted Files/`-style edge cases don't just work in isolation but don't destabilize a realistic mixed batch |

Each scenario is built per `DATASET_GUIDELINES.md` §3.2, Path A (synthetic construction from a described real shape) preferred; Path B (redacted real file) only where structurally necessary and only after the required review step.

## 3. Dataset manifest — required for every benchmark scenario

Every benchmark dataset is accompanied by a manifest file (`Tests/Benchmark Corpus/<scenario-id>/MANIFEST.md`) recording, at minimum:

```
Scenario ID / Name:
Date constructed:
Sourcing path used (A: synthetic / B: redacted-real):
If Path B — privacy review completed by (name/date), per DATASET_GUIDELINES.md §3.2:
Total file count:
Category breakdown (count per category):
Known duplicate/version relationships (count and description, not file content):
Known corrupted/locked/zero-byte files (count):
Deliberately ambiguous or edge-case files included (count and general description):
Anonymization method applied (per DATASET_GUIDELINES.md §3.1):
```

The manifest is what makes a benchmark dataset trustworthy across time — a future session picking this project back up must be able to verify a dataset's composition and privacy provenance without re-deriving it from scratch, the same reasoning behind every other canonical schema/contract document this project already maintains.

## 4. Answer key (ground truth) requirement

Every benchmark dataset ships with a fixed, pre-recorded answer key — the correct category, expected key metadata fields, correct duplicate/version relationships, and an expected tier range for every file — established once, at construction time, by the same process `REAL_WORLD_VALIDATION_PLAN.md` §5 describes (the file's actual "owner," in this case whoever constructed the synthetic scenario with a specific intended answer in mind). Unlike Live Validation Data, this answer key does not change between runs — that fixed-ness is exactly what makes cross-release comparison possible (§6). The answer key is stored alongside the manifest, using the same content restrictions as `DATASET_GUIDELINES.md` §2.3 (structural facts — category, tier, relationship — never sensitive values, which shouldn't exist in this corpus in the first place per §3.1's anonymization requirement).

## 5. Benchmark run procedure

Running "the benchmark suite" means running every scenario in §2 through the real pipeline (same CLI entry points, same Manual-mode process as Live Validation) and scoring each against its own answer key using `METRICS_DEFINITION.md`'s formulas. Unlike Live Validation, no live operator judgment call is needed to establish ground truth per file — it already exists in the manifest — so a benchmark run can be performed by a non-developer operator purely by following `VALIDATION_CHECKLIST.md`'s benchmark-run steps, without needing subject-matter familiarity with the (synthetic) files involved.

A benchmark run does **not** substitute for Live Validation — it cannot exercise §5.4 of `REAL_WORLD_VALIDATION_PLAN.md`'s independence principle, since the "ground truth" here was authored by whoever built the scenario, not an independent file owner reacting to real files. Its value is different and complementary: perfect repeatability across releases, which real, ever-changing Downloads folders cannot offer.

## 6. Cross-release comparison methodology

### 6.1 Results ledger

Every benchmark run's results are appended — never overwritten — to a results ledger, mirroring `Release/VERSIONS.md`'s own append-only, never-rewrite-history convention:

`Tests/Benchmark Corpus/RESULTS_LEDGER.md`

```
## <Pipeline Version> — <date> — Scenario <ID>

Classification Accuracy:        NN/NN (NN.N%)
Metadata Field Accuracy:        NN/NN (NN.N%)
Naming Acceptance Rate:         NN/NN (NN.N%)
Destination Acceptance Rate:    NN/NN (NN.N%)
Duplicate/Version Precision:    NN/NN (NN.N%)
Duplicate/Version Recall:       NN/NN (NN.N%) [lower bound]
Auto-Tier Correctness:          NN/NN (NN.N%)
Reliability Fault Rate:         NN/NN batch-halting, NN/NN contained
Throughput (files/sec, per stage): [table]

Findings filed: [links/IDs per REAL_WORLD_VALIDATION_PLAN.md §8]
Compared against: <prior Pipeline Version's same-scenario entry, or "first run — no baseline">
Regressions flagged: [none / list]
```

One entry per scenario per pipeline version that runs the suite — not one blended entry per version, so a regression specific to BM-03 (media-heavy) doesn't get diluted into an average that still looks fine.

### 6.2 What counts as a regression

A metric for a given scenario is flagged as a **regression** if it drops below its own immediately-prior-version value by more than a small, expected-noise margin (recommended starting margin: 5 percentage points for percentage-based metrics, or any increase at all for the Reliability Fault Rate or a drop below 100% for Auto-Tier Correctness / Reversibility — those two have zero acceptable regression, mirroring `REAL_WORLD_VALIDATION_PLAN.md` §9's A2/A3 treatment of the same metrics in the live-validation context). This margin is explicitly tunable once more than two data points exist — stated here as a starting point, not a permanent constant, in the same spirit as `Rules/Confidence Rules.md`'s own tuning note.

### 6.3 What happens when a regression is flagged

A flagged regression is filed as a finding per `REAL_WORLD_VALIDATION_PLAN.md` §8, at a severity no lower than Medium, and is routed to the project owner before that release is considered validated — a release does not get to claim "benchmarked" status with a known, unreviewed regression sitting in the ledger, mirroring this project's existing standing rule that no finding is silently dropped (`Governance/ENGINEERING_STANDARD.md` §14, Low-and-above disposition requirement).

### 6.4 Why this is separate from unit-test regression testing

The existing 716-test unit suite (`Governance/ENGINEERING_STANDARD.md` §19) already guards against *code-level* regressions — a function that used to return X now returns Y. The benchmark suite guards against a different, harder-to-catch class: *behavioral* regression that no unit test would ever catch because every individual function is still working exactly as designed — for instance, a well-intentioned confidence-weight tuning change (anticipated explicitly by `Rules/Confidence Rules.md`'s own tuning note) that inadvertently pushes more real files into `review_required` than before. Unit tests verify the code does what it's designed to do; the benchmark suite verifies the design still produces good real-world outcomes after a change.

## 7. Benchmark suite cadence

Recommended, not mandated by this framework: run the full benchmark suite (a) before any release that follows a change to `Rules/*.md` business logic or any module's scoring/matching/naming behavior, and (b) at minimum once per future pipeline version bump, so the results ledger never has a gap wide enough to make a regression's origin ambiguous. Live Validation (`REAL_WORLD_VALIDATION_PLAN.md`) has no fixed cadence — it's driven by real usage — but the benchmark suite's value depends on being run consistently, the same reasoning behind the unit suite's own "re-run after every change" standing rule.

## 8. What this specification deliberately does not do

It does not build the five benchmark datasets — that's dataset-construction work, explicitly out of scope for this planning-only phase (per this milestone's own stated constraints). It does not run a benchmark suite or populate the results ledger with real numbers. It does not pick a final home directory with certainty (`Tests/Benchmark Corpus/` is a recommendation, consistent with existing `Tests/` conventions, not a decision this document is authorized to make unilaterally). All three are natural first steps once this framework is approved, not something this document does on its own.
