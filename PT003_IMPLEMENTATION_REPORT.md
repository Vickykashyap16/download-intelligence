# PT-003 Implementation Report

**Date:** 2026-07-23
**Scope:** implementation of the approved PT-003 design only (`Build-out/04 Duplicate & Version Detection/Module 04 Post-Freeze Design Correction — PT-003.md`, Revision 2, APPROVE per Round 2 review). Governed by `ENGINEERING_CHANGE_PLAYBOOK.md` and `Governance/FROZEN_MODULE_CHANGE_POLICY.md`.
**Status:** Implementation and regression testing complete. Per explicit instruction, **no validation performed and no release documentation updated** in this cycle — stopping here as directed.
**Escalation check:** implementation did not require changing any Module 04 contract, did not require any architectural change, and did not expand beyond the approved design. No stop condition was triggered.

---

## 1. Implementation Summary

The approved design's corroborating-signal requirement (§6 of the design package) was implemented entirely inside `DuplicateDetectionEngine._check_version_chain()` and one new private helper method on the same class, in `src/pipeline/duplicate_detector.py`. No other file in `src/` was modified.

**Design decision made during implementation (not a scope expansion):** the design package left open whether the corroboration check would live in `storage/database.py` (inside `lookup_name_matches()`) or in `pipeline/duplicate_detector.py` (as a post-filter on `lookup_name_matches()`'s results). The post-filter approach was chosen, because `_check_version_chain()` already holds full `FileRecord` objects for every candidate (via `records_by_id`) — both `original_name` (for token parsing) and `size_bytes` (for the size-proximity check) are already available there with no new data plumbing required. This let the entire correction stay inside one file, touching zero database/storage code and leaving `lookup_name_matches()`'s signature, behavior, and its own existing test (`test_lookup_name_matches_is_category_scoped`) completely unchanged — a smaller footprint than the design package's own text speculated might be needed, not a larger one.

**What changed, precisely:**
1. A new module-level constant, `_VERSION_SIZE_PROXIMITY_RATIO = 0.5`, alongside the existing `_MAX_PHASH_DISTANCE`, following the same "configurable implementation parameter" convention and citation discipline as the existing constant.
2. A new private method, `DuplicateDetectionEngine._has_corroborating_version_signal(record, candidate, normalized_name)`, implementing exactly the two-branch condition from design §6: an explicit version token on either side is sufficient alone; otherwise an identical normalized name is required, further corroborated by a size-proximity check (`min(size_a, size_b) / max(size_a, size_b) >= 0.5`), with the two disclosed edge cases from the design handled explicitly — `size_bytes is None` on either side fails conservatively (does not qualify), and both sizes being `0` is special-cased to pass (avoiding the division-by-zero the round-2 review identified).
3. `_check_version_chain()` now filters its `candidates` list through this method immediately after building it from `lookup_name_matches()`'s results, before the existing `if not candidates: return None` check and before the cross-group-conflict logic runs. No other line in `_check_version_chain()`, `_determine_rank()`, `detect_file()`, or `detect_duplicates_batch()` was touched.

**Public behavior preserved:** every code path unrelated to version-chain candidacy (exact-duplicate detection, near-duplicate/phash detection, rank determination, cross-group-conflict handling once candidates are established, batch orchestration, logging, idempotency) is byte-for-byte unchanged. `lookup_name_matches()` and `_NAME_SIMILARITY_THRESHOLD` in `storage/database.py` are unchanged. No `FileRecord` field, no `MODULE_CONTRACT.md` guarantee, and no downstream module (05–08) was touched.

---

## 2. Files Changed

| File | Change |
|---|---|
| `src/pipeline/duplicate_detector.py` | +73 lines. Added `_VERSION_SIZE_PROXIMITY_RATIO` constant, added `_has_corroborating_version_signal()` method, added a 3-line filter step inside `_check_version_chain()`. No line outside these three additions was modified. |
| `src/pipeline/test_duplicate_detector.py` | +216/-16 lines (net +200). Updated 4 existing test fixtures (`test_engine_cross_group_conflict_flags_and_does_not_merge`, `test_engine_m1_null_group_never_counts_as_distinct_cross_group`, `test_engine_all_null_candidates_proceeds_as_ordinary_creation`, `test_batch_still_reprocesses_an_unresolved_cross_group_conflict_on_every_run`) to add matching `size_bytes` values, per the design's own Regression Impact analysis (§9), which anticipated this exact need. Added 9 new tests implementing the design's Test Plan (§10, T1–T12, consolidated to 9 distinct scenarios — some of the design's numbered items share one fixture). |

No other file was created, modified, or deleted. `src/storage/database.py` is unchanged. No `Rules/`, `Release/Module04/`, or `Governance/` document was modified in this cycle (release documentation update was explicitly out of scope for this step).

---

## 3. Test Results

New tests added (all passing), mapped to the design's Test Plan:

| Test | Design ref | Outcome asserted |
|---|---|---|
| `test_version_chain_near_miss_template_name_without_token_does_not_group` | T2 (Run 002 shape) | No group forms |
| `test_version_chain_near_miss_generic_increment_without_token_does_not_group` | T3 (Run 003 shape) | No group forms |
| `test_version_chain_identical_name_with_similar_size_and_no_token_groups` | T4 | Group forms |
| `test_version_chain_organic_rename_without_token_or_identical_name_does_not_group` | T1 (disclosed R1 trade-off) | No group forms |
| `test_version_chain_identical_generic_name_with_dissimilar_size_does_not_group` | T9 (Finding E1) | No group forms |
| `test_version_chain_identical_generic_name_with_similar_size_groups_as_disclosed_residual` | T10 (disclosed R6 residual) | Group forms |
| `test_version_chain_identical_name_with_missing_size_on_one_side_does_not_group` | T11 (R7, `size_bytes is None`) | No group forms |
| `test_version_chain_identical_name_with_both_sizes_zero_groups_without_error` | T12 (zero-byte edge case) | Group forms, no exception raised |
| `test_version_chain_explicit_token_still_sufficient_without_size_data` | Confirms token branch unaffected | Group forms with `size_bytes=None` on both sides |

All 9 pass. `src/pipeline/test_duplicate_detector.py` in isolation: **56 passed** (was 47 before this change — 4 fixtures updated in place, 9 new tests added: 47 + 9 = 56).

---

## 4. Regression Results

Full project-wide suite, executed via `python3 -m pytest src/ -q`:

```
729 passed in 4.01s
```

Baseline before this change (post-PT-002, per `PT002_VALIDATION_REPORT.md` and `PATTERN_TRACKER.md`) was **720 passing**. 720 + 9 new PT-003 tests = **729** — the count matches exactly, confirming no test was silently lost, skipped, or newly failing anywhere in the suite, and no unrelated module regressed.

The four fixtures updated in §2 were verified to still exercise their original intent (cross-group-conflict flagging, M1's null-group non-counting, batch re-examination idempotency) — each still reaches and asserts the same downstream behavior it did before, now via the token/size-corroborated path instead of the identical-name-only path.

---

## 5. Risk Assessment

No new risk beyond what the approved design already disclosed and accepted:

- **R1 (design §8):** a genuine version chain using neither an explicit token nor an identical filename is not detected. Confirmed present in the implementation as designed (`test_version_chain_organic_rename_without_token_or_identical_name_does_not_group`) — not a defect, a disclosed and accepted trade-off.
- **R6 (design §8):** two unrelated files sharing both a generic identical name and a coincidentally similar size still group. Confirmed present as designed (`test_version_chain_identical_generic_name_with_similar_size_groups_as_disclosed_residual`) — the narrowed, disclosed residual, not eliminated by design.
- **R7 (design §8):** a record with `size_bytes is None` cannot qualify via the identical-name branch. Confirmed present as designed (`test_version_chain_identical_name_with_missing_size_on_one_side_does_not_group`).
- **R2 (design §8, `resolve_precedence()` tier-exemption gap):** unchanged by this implementation — out of scope for this cycle, as the design itself stated. No new exposure introduced; this implementation reduces (does not eliminate) how often that pre-existing gap can be reached, exactly as the design predicted.
- **No new risk identified during implementation.** The zero-byte division-by-zero the round-2 review caught was already fixed in the design package before this implementation began (`larger == 0` special case), and is directly covered by `test_version_chain_identical_name_with_both_sizes_zero_groups_without_error`.

---

## 6. Rollback Confirmation

Confirmed consistent with the design's Rollback Plan (§13): the change is fully isolated to three additions in one file (`duplicate_detector.py`) — a constant, a method, and a 3-line filter call. Reverting is mechanical: delete the constant, delete the method, and remove the filter step (restoring `candidates` to flow directly from the `records_by_id[file_id] for file_id in candidate_ids` list into the existing `if not candidates: return None` check). No other file's production code depends on `_has_corroborating_version_signal()` or `_VERSION_SIZE_PROXIMITY_RATIO`. No data migration is required for rollback — as the design noted, `version_group_id`/`version_rank` values written under the corrected logic would not automatically revert, and any such records would need case-by-case review if rollback occurred after real use; this has not occurred, since no validation or real-world run has been performed against this implementation yet.

**Rollback has not been exercised or needed.** This confirmation is a readiness statement, not a report of an actual rollback event.

---

## Stop condition check (per instruction)

No module contract was modified. No architectural change was introduced. No module other than Module 04 was touched. Scope was not expanded beyond the approved design. **No STOP condition was triggered** — implementation proceeded to completion as authorized.

**Per explicit instruction, stopping here.** No validation run has been performed against this implementation, and no release documentation (`Release/Module04/`, `Release/VERSIONS.md`, `PATTERN_TRACKER.md`, `CHANGELOG.md`, etc.) has been updated. Both remain open, authorized future steps.
