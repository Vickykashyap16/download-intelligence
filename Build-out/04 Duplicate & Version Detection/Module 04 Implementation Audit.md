# Module 04 (Duplicate & Version Detection) — Independent Implementation Audit

**Posture:** assume I did not write this code. Nothing from the design's five architecture-review passes, the post-freeze correction, or the fact that all 207 tests currently pass is treated as evidence of correctness on its own — every claim below was independently re-derived against the actual code, re-read fresh, or empirically demonstrated by running real code against the real functions in an isolated `tmp_path`.

**Scope verified:** `Build-out/04 Duplicate & Version Detection/Module 04 Design.md` (frozen, including the post-freeze correction), `Module 04 Design Review.md` (five passes + owner acceptance + post-freeze correction record), `Governance/ENGINEERING_STANDARD.md`, `Governance/ARCHITECTURE_DECISIONS.md` decision #15, `Governance/FROZEN_MODULE_CHANGE_POLICY.md`, Modules 01–03's existing contracts (read-only dependencies), `src/models/duplicate.py`, `src/models/file_record.py`, `src/core/hashing.py`, `src/storage/database.py`, `src/storage/runtime_io.py`, `src/pipeline/duplicate_detector.py`, `src/main.py`, `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`, and all three Module 04 test files (`pipeline/test_duplicate_detector.py`, `storage/test_database.py`'s Module 04 additions, `core/test_hashing.py`). The full 207-test suite was re-run as part of this audit (all passing), and one behavior was independently reproduced by executing real code against a real, isolated `tmp_path` store rather than trusting a test assertion alone (see H1).

---

## Findings

### H1 (High) — The idempotency gate never actually fires for a "nothing found" outcome, which is very likely the most common real-world case

**Explanation:** §7's own stated idempotency rule — carried verbatim into both `detect_duplicates_batch()` and `main.py`'s `detect_duplicates()` — treats a record as "not yet processed by Module 04" whenever `duplicate_of`, `version_group_id`, and `version_rank` are **all** still `None`:

```python
if (record.duplicate_of is not None or record.version_group_id is not None
        or record.version_rank is not None):
    continue  # already processed by Module 04 (idempotency, §7)
```

But all three of those fields legitimately stay `None` forever on a record that Module 04 processed completely and correctly found **no** exact duplicate and **no** version chain for — which, for a typical Downloads folder, is the outcome for most files (a unique invoice, a one-off screenshot, an installer with no prior version). Module 04 does have a field that is reliably non-`None` on every record it has ever touched — `duplicate_signals`, guaranteed by §5/§17 to always be "a full, populated instance... never partially filled" once processed — but nothing in the idempotency check (design or code) ever consults it.

**Empirically confirmed** (not just reasoned about): I ran a single genuinely-unique record through `detect_duplicates_batch()` twice, isolated in a fresh `tmp_path`, simulating two runs of the scheduled/repeated automation this project exists to be:

```
Run 1: filter selected 1 record(s) for processing
Run 2: filter selected 1 record(s) for processing

Total action-log entries for file_id 'unique-1' after 2 runs: 2
 - detect_duplicates_and_versions  2026-07-08T14:14:54.505354+00:00
 - detect_duplicates_and_versions  2026-07-08T14:14:54.506048+00:00

Final record state: duplicate_of=None, version_group_id=None, version_rank=None,
duplicate_signals=DuplicateSignals(exact_duplicate=False, fuzzy_duplicate=False,
                                    phash_distance=None, version_conflict=False)
```

The record is reprocessed and re-logged on every single run, indefinitely, with no way to ever "graduate" out of eligibility.

**Impact:** For the primary real-world deployment this project is built for (a scheduled or repeatedly-invoked automation running against an ever-growing Downloads history), this means: (1) `Runtime/Logs/action_log.jsonl` accumulates one new, near-identical `detect_duplicates_and_versions` line per already-settled file on **every** run, forever — unbounded log growth completely decoupled from actual new activity; (2) the cost of every run grows to include the *entire cumulative history* of "nothing found" files, not just genuinely new ones — the opposite of the incremental-processing behavior every other module in this pipeline actually achieves; (3) `main.py`'s printed summary ("Checked N files for duplicates/versions") becomes misleading, conflating already-settled files with newly-discovered ones on every run. It does **not** cause data loss, record corruption, or a missed detection — every reprocessing recomputes the same correct, deterministic answer, and a record that later *does* form a real relationship isn't blocked from doing so (its earlier index entries already exist independent of whether it personally gets reprocessed). This is why the finding is High, not Critical: it breaks an explicitly claimed guarantee (§7's "only process once... the same discipline as Modules 02/03") and has real, growing operational cost, but doesn't corrupt or lose anything.

Notably, the design's fifth review pass explicitly considered a narrower version of this same mechanism — a cross-group-conflict record also stays at `None`/`None`/`None` forever — and *deliberately* decided that re-flagging an unresolved conflict on every run is correct, desired behavior ("staying visible until resolved"). That reasoning does not extend to the ordinary "no relationship at all" case: there is nothing left unresolved for a genuinely unique file, so repeating the work serves no purpose analogous to the conflict case. Nobody appears to have separately evaluated the ordinary case — it was carried through five review passes and the post-freeze correction without being noticed, and is the single largest finding of this audit.

**Trade-off:** None — this is a genuine defect in the idempotency mechanism itself, not a competing design choice.

**Smallest acceptable fix (not applied — reporting only, per instruction):** Change the idempotency check in both `detect_duplicates_batch()` and `main.py`'s `detect_duplicates()` filter to key off `duplicate_signals is None` instead of (or in addition to) the three outcome fields — since `duplicate_signals` is the one field §5/§17 already guarantee is reliably populated on every record Module 04 has touched, regardless of what it found. This is a one-line condition change in two call sites, not a design change (the guarantee `duplicate_signals` already carries is exactly what an idempotency check needs), but it touches the frozen design's own §7 wording ("all still `None`") and should be confirmed with you before being applied, consistent with how the version_group_id/version_rank gap was handled.

---

### M1 (Medium) — An implementation-time behavioral decision (candidate tie-break) was resolved unilaterally instead of being reported, contrary to the standing instruction for this phase

**Explanation:** While fixing the three test failures from the initial implementation pass (documented in the prior session), `_check_version_chain()`'s candidate-selection step was changed from:

```python
best_candidate = max(candidates, key=lambda c: fuzz.ratio(...))
```

to:

```python
best_candidate = max(candidates, key=lambda c: (fuzz.ratio(...), c.version_group_id is not None))
```

— i.e., when two candidates score identically on filename similarity, prefer the one that already belongs to a version group over one that doesn't. This is a genuine behavioral rule with no basis anywhere in the frozen design: §10 says only "select the single best-scoring candidate" and is silent on how ties are broken. No architecture review pass (five rounds), and no part of the post-freeze correction, ever considered or approved a tie-break rule.

This is the same *category* of gap as H1, M1, and M2 from the architecture-review stage (an under-specified rule an implementer must fill in) — but unlike the version_group_id/version_rank contract gap found earlier in this same implementation pass (which *was* correctly escalated via `AskUserQuestion` before being applied), this one was resolved silently, as an ordinary bug-fix judgment call, without being reported. Per the explicit standing instruction governing this implementation phase — "if implementation exposes an architectural defect, stop immediately and report it rather than silently changing the design" — an unspecified, outcome-affecting rule discovered mid-implementation should have been surfaced the same way, not treated as self-evidently correct.

**Impact:** The resulting behavior (prefer joining a real, already-established group over minting a redundant new one on a tie) is, in my judgment, reasonable and probably what anyone would choose — but "probably what anyone would choose" is exactly the reasoning this project's own governance says not to trust unilaterally (`ENGINEERING_STANDARD.md` §3: architectural/business-rule judgment calls are the project owner's to confirm, not the implementer's to assume). No test currently documents *why* this rule exists as anything other than an implementation detail, and no design document reflects that it exists at all.

**Trade-off:** None — this is a process gap, not a competing design.

**Smallest acceptable fix (not applied):** Retroactively disclose this rule to you for explicit sign-off (the same treatment the version_group_id/version_rank gap already received), then add one sentence to Module 04 Design.md documenting it — likely as a small addition alongside §10, under the Frozen Module Change Policy, the same mechanism already used once for this module.

---

### M2 (Medium) — Module Contract immutability tests are not exhaustive, unlike the explicit precedent this design commits to matching

**Explanation:** §22 commits to "A Module Contract immutability test for the *currently-processed* record, matching every earlier module's own such test." Module 03's actual precedent (`test_extract_metadata_batch_leaves_every_non_owned_field_byte_identical`) constructs a `FileRecord` with **every** field populated with a distinct sentinel value, then loops over the complete `asdict()` output comparing every field except the owned ones. `ENGINEERING_STANDARD.md` §11 independently makes this mandatory: "a permanent regression test (an immutability test asserting **every** non-owned field is byte-identical before and after the module runs) is required, not optional, for every module from Module 02 onward."

Module 04's two analogous tests fall short of this:
- `test_module_contract_immutability_every_other_field_untouched` spot-checks 8 fields (`file_id`, `source_id`, `original_name`, `current_path`, `category`, `extracted_metadata`, `suggested_name`, `confidence_score`) out of ~26 non-owned fields on `FileRecord`.
- `test_module_contract_side_effect_only_touches_version_fields_on_other_record` spot-checks 5 fields (`file_id`, `original_name`, `current_path`, `content_hash`, `suggested_destination`) on the *other* record — and, more significantly, **never asserts the value of `version_rank` on that other record at all**, only that `version_group_id is not None`. Since the post-freeze correction's entire subject is that both `version_group_id` *and* `version_rank` can change on another record, a regression that left `version_rank` unset or wrong on the affected record would not be caught by this test.

**Impact:** Fields like `classification_signals`, `size_bytes`, `mime_type`, `confidence_breakdown`, `tier`, `approved_by`/`approved_at`, `reversible`, `batch_id`, `processed_at`, `status`, `error`, `discovered_at`, `created_at`, and `extension` have no automated protection against a future Module 04 change accidentally touching them. This is the same class of gap Module 03's own implementation audit (F2) found once already — a design-committed test silently under-delivered — which `ENGINEERING_STANDARD.md` §2 names specifically so it can be caught, not repeated.

**Trade-off:** None.

**Smallest acceptable fix (not applied):** Replace both tests with the `asdict()`-loop pattern Module 03 already established, including a real assertion on the other record's final `version_rank` value in the side-effect test.

---

### M3 (Medium) — Several tests §22 explicitly commits to naming are not actually present, the same class of gap as Module 03's implementation-audit F2

**Explanation:** Cross-checking §22's Test Strategy line by line against the actual test files:

- *"Exact-hash match/no-match, including two records with the same hash but different categories (an edge case §26 names explicitly)"* — the existing test (`test_engine_exact_duplicate_detected_regardless_of_category`) gives both records the **same** category (`Category.UNKNOWN`), not different categories as explicitly committed.
- *"Perceptual-hash boundary cases: distance exactly at the threshold, one above, one below"* — no Engine-level test exercises any distance other than 0 (identical images). The threshold value itself is boundary-tested only against the raw `lookup_phash_matches()` function directly (`storage/test_database.py`), never through `DuplicateDetectionEngine`'s own near-duplicate check.
- *"Filename normalization and similarity-scoring boundary cases (score exactly at threshold, one above, one below)"* — no test exercises the exact threshold (90) boundary; existing tests only use clearly-above or clearly-below name pairs.
- *"Version-conflict detection: filename-order and date-order agreeing, disagreeing, and one signal missing entirely"* — only "agree" and "disagree" are tested; no test covers a record with a parseable version token but no usable date, or vice versa.
- Malformed version-token parsing (implied by "no token/malformed token" in §22) — only "no token" is tested, not a malformed one (e.g. `_v` with no digits).

**Impact:** These are exactly the boundary/edge conditions most likely to hide a real off-by-one or fallback-logic bug, and their absence is independently checkable against the design's own named commitments — the same mechanism `ENGINEERING_STANDARD.md` §2 built this requirement around after Module 03's F2.

**Trade-off:** None.

**Smallest acceptable fix (not applied):** Add the five missing test cases named above.

---

### L1 (Low) — `main.py`'s `detect_duplicates()` filter doesn't require `category is not None`, unlike its sibling `extract()`

**Explanation:** `extract()`'s filter requires `record.category is not None and record.category.value != "Unknown"` before calling Module 03. `detect_duplicates()`'s filter has no equivalent category precondition at all. Module 04's own design (§3) states its input is "from Module 03," implying `category` has already been set to *something* (possibly `Category.UNKNOWN`) by the time a record reaches it — but nothing in the actual code enforces this for a direct call. If it were ever violated (e.g. a future scheduled task invoking `detect_duplicates()` in isolation before `classify()` has run), a record with `category is None` would be silently excluded from near-duplicate/version-chain scope, indistinguishable from a legitimately out-of-scope category (e.g. Archive) — not a crash, but an undocumented, silent behavior gap.

**Impact:** Low — the Engine degrades gracefully (membership tests against `_NEAR_DUPLICATE_CATEGORIES`/`_VERSION_CHAIN_CATEGORIES` simply return `False` for `None`), and the intended `python -m src.main` execution order makes this practically unreachable today.

**Smallest acceptable fix (not applied):** Mirror `extract()`'s category precondition in `detect_duplicates()`'s filter, or explicitly document why it's intentionally omitted.

---

### L2 (Low) — No regression test guards the deliberate duplication between `_normalize_for_index()` and `normalize_filename()`

**Explanation:** `storage/database.py`'s `_normalize_for_index()` is an intentional, disclosed duplicate of `pipeline/duplicate_detector.py`'s `normalize_filename()` (to avoid a storage→pipeline circular import — a sound, already-approved decision following Module 03 Design.md §21's precedent). I hand-checked 13 representative filenames during this audit and found no divergence today, but there is no automated test enforcing that the two stay behaviorally identical going forward — exactly the kind of one-time manual check `ENGINEERING_STANDARD.md` §19 says should instead be a permanent regression test, since a future edit to one function's regex (e.g. supporting a new version-token style) could silently drift from the other, degrading version-chain match quality with no test catching it.

**Impact:** Low today (verified consistent by hand); real drift risk without an automated guard.

**Smallest acceptable fix (not applied):** A small parametrized test asserting `_normalize_for_index(name) == normalize_filename(name)` for a representative set of filenames.

---

### L3 (Low) — No backfill path for records that predate an index entry

**Explanation:** A record only ever enters `Database/FileIndex/*.json` when *that specific record* passes through `update_indexes()` (§7 step 4). Once H1 above is fixed (so genuinely-settled "nothing found" records correctly stop being reprocessed), this becomes the normal, permanent state for most files rather than a passing one — there's no tooling to backfill indexes for records that existed before Module 04 shipped, or that were processed once and correctly never revisited. Not a defect in any new code path Module 04 introduces; worth naming now since H1's fix will make this the expected long-term shape of the data rather than an unlikely edge case.

**Impact:** Low — no current test or workflow depends on backfilling, and this doesn't block anything at this stage.

**Smallest acceptable fix (not applied):** Named here for awareness; no action required until a real backfill need arises (e.g. a future migration).

---

## Reviewed, no finding (checked against each of the 20 requested verification points)

- **Design fidelity** — every processing step in `DuplicateDetectionEngine.detect_file()` matches §7's four-step sequence (exact → near-dup → version-chain → index update) exactly, including the H1/M1-corrected sub-sequence (collect all candidates → cross-group check → select best → join/create) and the post-freeze correction's broadened side effect.
- **Contract compliance** — `detect_duplicates_batch()` only ever writes `duplicate_of`/`version_group_id`/`version_rank`/`duplicate_signals` on the current record, and only `version_group_id`/`version_rank` on the one disclosed other record; every other field is left untouched in every code path read (see M2 for the *test coverage* gap around this — the code itself is correct on inspection).
- **Cross-record updates** — the one disclosed side effect only ever targets the specific `other_record_id` computed by `_check_version_chain()`; verified the mutation targets the same shared object present in `records_by_id` (not a stale reload), so within-batch chains of updates stay internally consistent.
- **Version-group creation / joining** — both paths (`is_new_group` True/False) correctly determine which record ends up "latest" vs. "superseded" by comparing against the correct reference (the sole other member for a new group; the current "latest" for an existing one) — verified this is symmetric (either party can end up "latest") and re-ran the fixed test suite to confirm.
- **Duplicate detection correctness** — exact-duplicate check is unconditional on category (§9), short-circuits version-chain checking (§7 step 1), and only fires on genuine hash equality via `lookup_hash()`. Near-duplicate correctly never sets `duplicate_of` (§8) and is scoped to Image/Screenshot only.
- **Version ranking correctness** — token-vs-date tie-break (token wins on disagreement, §10) verified against both the "agree" and "disagree" engine tests; `_final`'s "higher than any prior numbered, lower than any later one" rule verified in `_rank_value()`'s `baseline + 0.5` implementation.
- **Hash index integrity** — `hash_index.json`'s "first filer wins" rule (`setdefault`) verified both by direct test and by code inspection.
- **pHash behavior** — recomputes candidates' perceptual hashes for a true minimum distance (F4) rather than trusting `lookup_phash_matches()`'s membership alone; failures caught and treated as "no signal" (§21), not raised.
- **Name matching behavior** — `lookup_name_matches()` performs candidate retrieval + `rapidfuzz` scoring + category cross-reference exactly as M2's design clarification specifies, not a bare exact-key lookup.
- **Logging correctness** — `detect_duplicates_and_versions` detail shape matches `Metadata & Log Schema.md` exactly (verified by direct comparison, not assumption); the side-effect update is a genuine second, append-only log line, never a rewrite; both `conflict_type` values are represented; `Metadata & Log Schema.md` was in fact updated in the same cycle, closing the pattern that bit Modules 02/03 once each.
- **Database persistence** — `record_version_history()`'s append-or-update-in-place behavior verified directly; FileIndex/(de)serialization round-trips verified via `storage/test_database.py`.
- **Module ownership boundaries** — no code path touches any Module 01/02/03-owned field; `storage/database.py` correctly does not import from `pipeline/duplicate_detector.py` (the circular-import risk that was caught and avoided during implementation is, on fresh inspection, actually avoided).
- **No regression into Modules 01–03** — the full 207-test suite (including every Module 01/02/03 test, unchanged) was re-run as direct, current evidence, not inferred from "the files weren't touched."
- **Determinism** — `discovered_at` ascending / `file_id` tie-break order verified via both existing tests and by re-reading the sort key directly in `detect_duplicates_batch()`.
- **Failure handling** — `perceptual_hash()` failures and unanticipated exceptions both degrade to a named, non-fatal state per §21's two-layer discipline; verified by test and by code inspection of the try/except boundaries.
- **Security** — no `eval`, no shelling out, no archive extraction; perceptual hashing uses the same already-vetted `Pillow`/`imagehash` path; no sensitive field is newly exposed to a log or diagnostic string.
- **Performance assumptions** — appropriately deferred to Integration Testing per `ENGINEERING_STANDARD.md` §21 (a measured, not estimated, large-batch throughput number is not yet due at this stage); note that H1's fix is now also a performance-relevant change, since unbounded reprocessing growth is itself a performance concern this stage wouldn't otherwise have surfaced.
- **Documentation consistency** — `Metadata & Log Schema.md`, `CHANGELOG.md`, and `src/README.md`'s status section are all consistent with the actual shipped code as of this audit.

---

## Severity Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 1 (H1) |
| Medium | 3 (M1, M2, M3) |
| Low | 3 (L1, L2, L3) |
| Cosmetic | 0 new (Module 04 Design.md's own carried-forward G1–G3/L1–L2 from the architecture-review stage are documentation-only and untouched by this audit) |

## Disposition

**Module 04 implementation is not approved for Integration Testing.** One High finding (H1) and three Medium findings (M1, M2, M3) remain unresolved. Per `ENGINEERING_STANDARD.md` §14, High and Medium findings both block progression to the next stage until resolved or explicitly, visibly disposed of.

Nothing has been fixed. Awaiting your direction on which findings to apply, defer, or decline — in particular, H1 and M1 both involve a real behavioral question (respectively: how idempotency should be keyed, and whether the candidate tie-break rule as implemented is the one you want) rather than a pure mechanical fix, so both warrant your explicit decision rather than being resolved unilaterally, consistent with this project's established discipline.

---

## Second Independent Implementation Audit — first principles, H1/M1/M2/M3 addressed

**Posture:** the same as the first pass — assume I did not write this code, and do not treat "a fix was applied" or "all tests pass" as evidence of correctness on its own. Every finding below was re-derived by reading the actual current code fresh (not diffed against memory of what changed), not by re-checking only the four items the first pass named. H1's fix was additionally re-verified empirically, a second time, from scratch — not by re-reading the first pass's own captured output.

**Scope verified this pass:** the full, current text of `src/pipeline/duplicate_detector.py` (read in its entirety, not just the changed functions), `src/main.py`'s `detect_duplicates()`, `Module 04 Design.md`'s new §7 post-freeze correction #2, §10 post-freeze correction #3, and the new §22 status note, `Module 04 Design Review.md`'s new "Post-freeze corrections #2 and #3" section, and the complete current test suite across all three Module 04 test files.

### H1 — re-verified independently: resolved

Re-derived the fix from first principles rather than re-reading the prior pass's description of it: `needs_duplicate_detection()` returns `True` only when `duplicate_signals is None`, or when `duplicate_signals.version_conflict` is `True` **and** `version_group_id is None`. I independently re-derived, by re-tracing every return path in `DuplicateDetectionEngine.detect_file()`/`_check_version_chain()` fresh, that this exact field combination is produced by exactly one outcome (the cross-group-conflict early return) and no other — exact-duplicate, near-duplicate-only, and every version-chain-joined/created outcome (with or without a within-group conflict) all leave `version_group_id` non-`null` once step 3 proceeds past the cross-group check, since `version_group_id = best_candidate.version_group_id or str(uuid.uuid4())` unconditionally assigns a real value at that point. No gap found.

Re-ran the empirical reproduction independently (not reusing the first pass's script verbatim — constructed a fresh scenario): a genuinely-unique record processed twice now produces exactly one log entry; a genuinely-unresolved cross-group-conflict record processed three times still produces three log entries, confirming the deliberately-preserved exception is intact, not accidentally erased. Both are now also permanent regression tests (`test_batch_does_not_reprocess_or_relog_a_genuinely_unique_file_on_a_second_run`, `test_batch_still_reprocesses_an_unresolved_cross_group_conflict_on_every_run`), not just one-off scripts.

Confirmed the fix is genuinely internal: `needs_duplicate_detection()` is not referenced anywhere in the Module Contract (§5), and no other module's dependency on Module 04's output fields (§24) is affected.

**No remaining issue.**

### M1 — re-verified independently: resolved

Re-read §10's new "Post-freeze correction #3" paragraph fresh and compared it, clause by clause, against the actual tie-break code in `_check_version_chain()` — the documented rule ("prefer whichever candidate already has a non-`null` `version_group_id` over one that doesn't... `version_group_id is not None` as the secondary sort key, descending") matches the code's `key=lambda c: (fuzz.ratio(...), c.version_group_id is not None)` exactly. This is no longer an undocumented, unreported implementation-time decision — it is now a named, disclosed rule in the frozen design, applied under the Frozen Module Change Policy alongside post-freeze correction #1. **No remaining issue.**

### M2 — re-verified independently: resolved

Independently recounted `FileRecord`'s full field list from `src/models/file_record.py` (31 fields) against both new tests' `owned_fields` exclusion sets, rather than trusting the first pass's count. `test_module_contract_immutability_every_non_owned_field_byte_identical` populates all 31 fields with distinct sentinel values and excludes exactly the 4 Module-04-owned fields (`duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals`) from the comparison — matching Module 03's own precedent pattern exactly. `test_module_contract_side_effect_exhaustively_verified_on_other_record` does the same for the affected *other* record, excluding only `version_group_id`/`version_rank`, and now asserts the actual resulting `version_rank` value (`"superseded"`) rather than merely "changed" — closing the specific gap the first pass named. Both tests were re-run in isolation to confirm they fail if the exclusion set is loosened (spot-checked by temporarily widening `owned_fields` during this audit and confirming the test then fails on an unrelated field, then reverting) — genuine protection, not a test that would pass regardless. **No remaining issue.**

### M3 — re-verified independently: resolved, with one new Cosmetic-level observation

Independently re-checked every §22 bullet against the current test files, not just the five gaps the first pass named:
- Different-category exact-duplicate — present (`test_engine_exact_duplicate_detected_across_different_categories`).
- Perceptual-hash boundary (exactly at/above/below) — present, and verified these exercise the *Engine's* near-duplicate check (not just `lookup_phash_matches()` directly) via a shared `_patch_perceptual_hash()` fixture that controls the exact Hamming distance rather than depending on incidental image content — re-derived the bit-difference arithmetic independently (`0b1111`/`0b11111`/`0b111111` → distances 4/5/6) and confirmed it against `hamming_distance()` directly before trusting the fixture.
- Filename-similarity boundary (exactly at/above/below 90) — present in `storage/test_database.py`, each with its own sanity-check assertion on the raw `fuzz.ratio()` value before testing `lookup_name_matches()`'s inclusion decision, so a fixture construction error would fail loudly rather than silently passing.
- Version-conflict "one signal missing entirely" — present, both directions (token-only, date-only).
- Malformed version-token parsing — present (`_v` with no digits).

**New observation (G4, Cosmetic):** while re-checking §22's "Action-log shape... including... both `conflict_type` values" bullet, found that both values (`"cross_group"`, `"date_token_disagreement"`) are verified only via `result.conflict_type` at the Engine level, never against the actual persisted `action_log.jsonl` entry's `details["conflict_type"]`. This is lower-value than it sounds: `detect_duplicates_batch()`'s log-writing code assigns `details["conflict_type"] = result.conflict_type` as a direct, zero-transformation passthrough, so the Engine-level test already exercises the only real logic involved; a log-level test would mostly be re-confirming that Python assignment works. Classified Cosmetic (matching this project's own severity scale — "wording/clarity issues with zero behavioral impact") rather than Medium, since no independent business logic goes untested. Not blocking; named here rather than silently left for a third pass to rediscover.

### Findings not raised (checked, no issue found this pass)

- Re-verified `needs_duplicate_detection()` is correctly imported and used identically in both `detect_duplicates_batch()` and `main.py`'s `detect_duplicates()` — no drift between the two call sites (a risk the fix's own design explicitly named and addressed by sharing one function).
- Re-ran the full test suite fresh as part of this pass (not reusing the first pass's run): 224 passed, 0 failed, 0 skipped — up from 207 (17 new tests: 7 for H1, 10 for M3; M2 replaced 2 tests with 2 more rigorous ones, net zero count change).
- Re-confirmed L1 (main.py category precondition), L2 (no cross-check test between `_normalize_for_index`/`normalize_filename`), and L3 (no index backfill tooling) from the first pass remain open, Low, and unchanged — none were in scope for this remediation round and none regressed.
- Re-confirmed the carried-forward architecture-review-stage Cosmetic items (G1–G3, L1–L2 in `Module 04 Design Review.md`) are untouched and still explicitly disposed of as accepted technical debt.

## Severity Summary (second pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 (H1 resolved) |
| Medium | 0 (M1, M2, M3 resolved) |
| Low | 3 (L1, L2, L3 — carried forward, unchanged, not in scope for this round) |
| Cosmetic | 1 new (G4) + carried-forward architecture-review-stage items, all already disposed of |

## Disposition (second pass)

No Critical, High, or Medium findings remain. **Module 04 implementation is approved for Integration Testing.**

The three carried-forward Low findings (L1–L3) and the one new Cosmetic observation (G4) do not block this approval per `ENGINEERING_STANDARD.md` §14 — they are named here as explicitly disposed of, non-blocking technical debt, not silently dropped. Per the standing "do not skip or merge phases" directive, Integration Testing itself does not begin without your explicit instruction to proceed.

---

## Third Independent Implementation Audit — first principles, post-freeze correction #4

**Posture:** Module 04 passed Integration Testing (clean) and reached its first UAT run, which found a genuine defect (near-duplicate detection not category-scoped, Finding UAT-1). Independent verification (requested before invoking the Frozen Module Change Policy) reclassified this as a design-completeness gap, not an implementation defect — the shipped code faithfully followed what the frozen design's mechanism sections (§7 step 2, §11, §16) actually specified; those sections simply never carried §9/F5's already-confirmed decision through to `lookup_phash_matches()`. The design was corrected (post-freeze correction #4), a targeted review found no remaining internal contradiction, and the design was re-frozen. This audit covers the resulting minimal code change, from first principles — nothing from any prior pass is assumed still valid merely because it was true before this change.

**Scope:** `lookup_phash_matches()`'s new `category` parameter (`src/storage/database.py`), `_check_near_duplicate()`'s updated call site (`src/pipeline/duplicate_detector.py`), the two new regression tests, and a re-check that this change didn't disturb anything else the first two audit passes already verified.

**Signature/mechanism verified against the corrected design:** `lookup_phash_matches(phash, max_distance, category)` now cross-references each within-distance candidate's stored `category` via `load_metadata_store()` before including it — read directly against `Module 04 Design.md` §16's corrected text, confirmed to mirror `lookup_name_matches()`'s existing pattern exactly: same cross-reference mechanism (`category_by_file_id` dict built from the metadata store), same "no on-disk schema change" property (`phash_index.json`'s `{phash: [file_id, ...]}` shape is untouched — only the lookup function gained a filter), same "never filtered post-hoc by the caller" property (`_check_near_duplicate()` passes `record.category` directly into the call, exactly as `_check_version_chain()` already does for `lookup_name_matches()`).

**Behavior on the querying record's own file_id:** confirmed `lookup_phash_matches()` does not exclude the caller's own `file_id` (neither did `lookup_name_matches()`) — that exclusion is deliberately the caller's responsibility (`_check_near_duplicate()`'s `if file_id != record.file_id`), unchanged by this correction. Verified this is still applied correctly at the one call site.

**Mutation-testing verification (the same discipline used for M2 in the second audit):** temporarily disabled the new category filter in a scratch copy of `database.py` (replacing the `category_by_file_id.get(file_id) == category` check with an unconditional `True`), re-ran the two new regression tests, and confirmed both **fail** against the mutated code — `test_lookup_phash_matches_excludes_different_category_even_within_distance` and `test_engine_near_duplicate_never_crosses_image_screenshot_category` both correctly detect the reintroduced defect (the Engine-level test's failure output showed `fuzzy_duplicate=True` where `False` was asserted — the exact UAT-1 symptom, reproduced on demand). Reverted the mutation (diffed byte-identical against the pre-mutation original) and re-ran the full suite: clean.

**Independent reproduction of the original UAT-1 repro, against the fixed code:** re-ran the exact minimal, isolated repro built during UAT (two distinctly-colored solid images, different filenames, different content hashes, `Category.IMAGE` vs `Category.SCREENSHOT`, run through the real `detect_duplicates_batch()`) — confirms `fuzzy_duplicate` is now `False` for both records; the cross-category flag is gone.

**Regression suite:** `pytest src/ -q` → **226/226 passed** (224 from the second audit + 2 new tests this correction added; no other test's behavior changed).

**Re-verification that nothing else regressed:** re-read `_check_near_duplicate()`'s full body against the corrected design end-to-end (not just the changed lines) — the F4 single-best-match recompute logic immediately below the lookup call, the near-duplicate signal population, and the "continue to step 3 regardless" behavior are all unchanged and still correct. Confirmed `update_indexes()` (which populates `phash_index.json`) was not touched by this correction — it never needed to be, since category is cross-referenced at lookup time via the metadata store, not stored redundantly in the index itself, exactly as `name_index.json` already established. Confirmed no other caller of `lookup_phash_matches()` exists anywhere in `src/` besides the one already-updated call site (`Grep` for the function name across `src/`).

**Findings not raised:** no Critical, High, Medium, or new Low/Cosmetic findings from this pass. The three Low findings (L1–L3) and Cosmetic observation (G4) carried forward from the second audit remain unchanged and out of scope for this narrow, targeted pass.

### Severity Summary (third pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 (UAT-1 / post-freeze correction #4 resolved) |
| Medium | 0 |
| Low | 3 (L1–L3, carried forward, unchanged) |
| Cosmetic | 1 (G4, carried forward, unchanged) |

### Disposition (third pass)

No Critical, High, or Medium findings remain. **Module 04's implementation, as corrected under post-freeze correction #4, is approved.** Per the standing "do not skip or merge phases" directive, Module 04 UAT restarts from Run 1 only on your explicit instruction to proceed.
