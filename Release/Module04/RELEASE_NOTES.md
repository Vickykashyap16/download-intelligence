# Release Notes — Module 04 (Duplicate & Version Detection)

```
Pipeline Version:  0.4.0
Module Version:    1.0.0
Date:              2026-07-08
Status:            Frozen, approved, feature-complete
```

See `Release/VERSIONS.md` for how Pipeline Version and Module Version relate (each module versions independently; the pipeline number tracks overall project maturity, not a function of module numbers).

**Deployment model, stated plainly:** unlike Modules 02/03, this framing is simpler for Module 04 — there is no provider, live or autonomous, of any kind (`Module 04 Design.md` §14). Every decision Module 04 makes (hash equality, perceptual-hash distance, filename similarity, version-token/date comparison) is a deterministic computation over already-structured data. Module 04 is Production Ready for both interactive Claude-assisted operation and unattended/scheduled operation identically — there is no judgment-dependent behavior that degrades or falls back differently between the two. See `MODULE_CONTRACT.md`'s "Provider boundary" section.

This is the fourth module of the Downloads Intelligence pipeline. It takes every `FileRecord` Module 03 has processed (`status == "discovered"`) and detects two relationships against everything already known to the pipeline: exact duplication (content-hash equality, every category) and versioning (filename/date-signal similarity, scoped to categories where "an updated copy of the same document" is meaningful), plus a separate near-duplicate image signal (perceptual hash, Image/Screenshot only). It records these as raw signals and facts — never a destination decision, confidence score, or file move, all of which remain reserved for Modules 05–07.

## Features implemented

- Exact-duplicate detection via `content_hash` (SHA-256, already computed by Module 01) — runs on every discovered record regardless of category, treated as a certain fact (`duplicate_of`), never merely a signal.
- Near-duplicate detection via perceptual hash (`imagehash`, max Hamming distance 5), scoped to Image/Screenshot, with Image and Screenshot strictly non-overlapping categories — recorded only as a signal (`duplicate_signals.fuzzy_duplicate`/`phash_distance`), never as `duplicate_of`.
- Version-chain detection via filename normalization + `rapidfuzz` similarity scoring (threshold 90) plus version-token/date comparison, scoped to Invoice/Resume/Bank Statement/Contract/Document/Image/Screenshot.
- A new `duplicate_signals` field (`DuplicateSignals`, `src/models/duplicate.py`) mirroring `classification_signals`'s pattern exactly — always a full, populated instance once Module 04 has processed a record.
- `Database/FileIndex/` (`hash_index.json`, `phash_index.json`, `name_index.json`) and `Database/History/version_history.json` — first real implementation of structures reserved since Module 01's schema was first drafted.
- Deterministic, defined batch-processing order (`discovered_at` ascending, `file_id` lexicographic tie-break) so re-running the same batch, or the same batch in a different input order, always produces the same result.
- Cross-group conflict handling: a new record whose above-threshold version-chain candidates span two different pre-existing `version_group_id`s is flagged (`conflict_type: "cross_group"`, both conflicting group IDs logged) and left unassigned — never auto-merged.
- A correct idempotency model: a record Module 04 has already fully processed (found something or found nothing) is never re-selected on a later run, with one precisely-scoped, deliberate exception — an unresolved cross-group conflict remains eligible for re-examination on every run until resolved.
- Fully deterministic — no Provider layer at all, a deliberate departure from Modules 02/03's pattern (§14).
- CLI wiring (`src/main.py`'s `detect_duplicates()`) — loads every discovered record still awaiting duplicate/version detection, runs `detect_duplicates_batch()`, and prints a summary (exact/near-duplicate/version-chain/conflict counts, per-file notes) read back from the action log.
- `core/hashing.py` gained `perceptual_hash()`/`hamming_distance()`, implemented from stubs, using the already-approved `imagehash` dependency.

## Bugs fixed

Four post-freeze design corrections were applied during this module's lifecycle, all approved by the project owner and documented in `Build-out/04 Duplicate & Version Detection/Module 04 Design.md`/`Module 04 Design Review.md` with dated, non-destructive addenda (see `CHANGELOG.md` for the full stage-by-stage history):

- **Post-freeze correction #1 (implementation-discovered defect).** §7 step 3.4's first-time-group-creation logic requires the matched candidate's `version_group_id` to be set alongside its `version_rank`, but the frozen Module Contract had only disclosed `version_rank` as updatable on another record. Approved: the disclosed side-effect exception was broadened to cover both fields (never any other).
- **Post-freeze correction #2 (first Independent Implementation Audit, finding H1 — High).** The idempotency check originally keyed on `duplicate_of`/`version_group_id`/`version_rank` all being `None` never actually fired for a "nothing found" outcome — very likely the single most common real-world result — causing unbounded reprocessing and log growth on every subsequent run. Fixed: the check now keys off `duplicate_signals is not None`, with the already-approved cross-group-conflict state preserved as the one deliberate exception.
- **Post-freeze correction #3 (first Independent Implementation Audit, finding M1 — Medium).** An undisclosed, unreported implementation-time tie-break rule for equally-scored version-chain candidates was retroactively disclosed and formally added to §10 (prefer an already-grouped candidate over an ungrouped one on a tie).
- **Post-freeze correction #4 (discovered during UAT, Finding UAT-1 — High; independently reclassified as a design-completeness gap, not an implementation defect).** Near-duplicate detection (`lookup_phash_matches()`) was never category-scoped, contradicting the frozen design's own confirmed requirement that Image and Screenshot never group for either near-duplicate or version-chain detection — the version-chain half was correctly implemented; the near-duplicate half never received the same treatment. Fixed: `lookup_phash_matches()` extended to accept `category` directly, mirroring `lookup_name_matches()`'s already-established pattern; no change to `phash_index.json`'s on-disk shape.

Two Medium findings from the final Release Audit — both documentation-completeness gaps (`CHANGELOG.md` missing several stages' dated entries; `src/README.md`'s status bullet stale), no behavioral or contract defect — were also found and resolved; see `RELEASE_AUDIT.md`.

## Breaking changes

None. This is the fourth module in the pipeline; Modules 01, 02, and 03's contracts are unaffected — Module 04 only ever reads their fields, never rewrites them (see `MODULE_CONTRACT.md`). `duplicate_of`/`version_group_id`/`version_rank` already existed as reserved, unpopulated `FileRecord` fields since Module 01's schema was first drafted; this release is the first to actually populate them. `duplicate_signals` is a genuinely new field, additive only.

## Improvements

- Design-phase process at the same rigor as Modules 02/03: five independent architecture-review passes (`Module 04 Design Review.md`) found and resolved 1 High (H1 — an internal contradiction between the "single best match" and "cross-group conflict" rules), 4 Medium, 3 Low, and multiple Cosmetic findings before freeze.
- Independent Implementation Audit performed three times: the first pass found 1 High + 3 Medium findings (idempotency, an undisclosed tie-break rule, non-exhaustive immutability tests, missing committed test cases), all resolved and re-verified clean on the second pass; the third pass verified post-freeze correction #4's fix from first principles, including mutation testing to confirm the new regression tests are genuinely load-bearing.
- Integration Testing (`Tests/Module 04 Integration Test Plan.md`) ran a real four-module batch across 31 named cases spanning functional, cross-module-contract, idempotency, version-chain, conflict-handling, category-separation, determinism, logging, persistence, and performance dimensions — zero implementation defects (2 test-harness bugs found and fixed instead).
- UAT ran twice: an initial run stopped immediately on discovering a genuine, independently-reproduced defect (Finding UAT-1) rather than continuing or auto-fixing, per the standing instruction; a full restart from Run 1, after the design-correction cycle, completed cleanly across all four planned runs (initial batch, idempotency re-run, a new-arrivals run exercising both chain-joining and a real cross-group conflict, and a final idempotency re-check) — archived at `Runtime/UAT/Module04_UAT_2026-07-08_211306/`.
- A final independent Release Audit (`RELEASE_AUDIT.md`) covering all 13 `Governance/PIPELINE_CONTRACT_VERIFICATION.md` checks plus a qualitative review — 2 Medium documentation findings, both resolved and independently re-verified before this release package was generated.
