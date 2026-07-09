# Module 05 (Naming & Destination) — Independent Implementation Audit

**Posture:** assume I did not write this code. Nothing from the design's twelve-decision review, the fresh independent design review that preceded freeze, or the fact that all 276 tests currently pass is treated as evidence of correctness on its own — every claim below was independently re-derived against the actual code (re-read fresh from disk), re-run, or empirically demonstrated by executing real code against the real functions, mirroring the rigor `Module 04 Implementation Audit.md` established as this project's own precedent (mutation-style verification where a finding's severity depends on it, not just a single passing/failing assertion taken at face value).

**Scope verified:** `Build-out/05 Naming & Destination/Module 05 Design.md` (frozen, all 12 items resolved, re-read in full this pass), `Governance/ENGINEERING_STANDARD.md`, `Governance/ARCHITECTURE_DECISIONS.md` (all 19 decisions), `Governance/PIPELINE_CONTRACT_VERIFICATION.md`, `Governance/FROZEN_MODULE_CHANGE_POLICY.md`, `Release/Module01–04/MODULE_CONTRACT.md` (all four, read fresh), `Release/VERSIONS.md`, `Release/DEPENDENCY_DIAGRAM.md`, `Rules/Naming Rules.md`, `Rules/Folder Rules.md`, `Rules/Confidence Rules.md`, `src/models/naming.py`, `src/models/file_record.py`, `src/storage/database.py`, `src/storage/runtime_io.py`, `src/pipeline/naming.py`, `src/main.py`, `src/pipeline/duplicate_detector.py` (Module 04, for structural precedent comparison), `src/pipeline/test_naming.py`, `src/storage/test_database.py`'s Module 05 additions, `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`, `CHANGELOG.md`, `src/README.md`, and `Build-out/04 Duplicate & Version Detection/Module 04 Implementation Audit.md` (for format/rigor precedent). The full 276-test suite was re-run fresh as part of this audit (all passing). `git diff main --stat` was independently inspected to confirm the real, on-disk change set matches exactly what's disclosed — no Module 01–04 source file was touched (only `__pycache__` bytecode noise, not source). Two findings below (M2, L1) were confirmed by executing real code against constructed inputs, not by reasoning about the code alone.

---

## Findings

### M1 (Medium) — `naming_signals.fields_fell_back` records synthetic, non-taxonomy field names for Resume and Video, contradicting its own documented contract

**Explanation:** `src/models/naming.py`'s `NamingSignals` docstring states the field's contract precisely: *"`fields_fell_back` names every template field (by its taxonomy field name, e.g. `"vendor"` — never the template placeholder, e.g. `"{Vendor}"`)."* This is a real, specific guarantee — not vague — and it is Module 05's own documented promise to Module 06, which will eventually build `confidence_breakdown` keys like `"naming_fallback:<field>"` from this list (`Rules/Confidence Rules.md`'s worked example: `"naming_fallback:vendor": -10"`).

Two of the twelve categories violate this guarantee, confirmed by executing the real code:

- **Video** (`_fill_video()`/`_tier4_date_component()`): when `modified_at` is also unavailable, `"date"` is appended to `fields_fell_back` — but Video's real taxonomy field (confirmed against `src/pipeline/metadata.py`'s `OPTIONAL_FIELDS[Category.VIDEO]`) is `content_date`, not `date`. `"date"` is not a taxonomy field name for any category.
- **Resume** (`_fill_resume()`): when both `version_indicator` and `last_modified_date` are absent, `"version_or_date"` is appended — again not a real taxonomy field name (`REQUIRED_FIELDS`/`OPTIONAL_FIELDS[Category.RESUME]` are `candidate_name`, `version_indicator`, `last_modified_date`).

Empirically confirmed (not just read):
```
VIDEO name: Productdemo_Unknown_Date.mp4 fields_fell_back: ['date']
RESUME name: Resume_Jordanpatel_Unknown.pdf fields_fell_back: ['version_or_date']
```

Archive's own `"date"` label (`_fill_archive()`) is a milder version of the same pattern, but is more defensible: Archive's real taxonomy (confirmed empirically: `REQUIRED_FIELDS[Category.ARCHIVE] = ('contents_summary',)`, `OPTIONAL_FIELDS[Category.ARCHIVE] = ()`) has no date field of any kind to name correctly in the first place, so *some* synthetic label is structurally unavoidable there — Video's case is different because a real, correctly-named taxonomy field (`content_date`) does exist and simply wasn't used.

**Root cause:** the fallback-recording code for Video and Resume's composite slots was written to describe the *template slot* ("the date part," "the version-or-date part") rather than the *specific taxonomy field that failed to supply a value* — an inconsistency between the docstring's precise promise (written to match `ClassificationSignals`/`DuplicateSignals`'s existing, real-field-name convention) and the two bespoke fillers' actual behavior for these two categories specifically.

**Impact:** Contained, not severe — `fields_fell_back` still correctly reports *that* a fallback occurred and *how many* fields were affected, which is what drives the `-10`-per-fallback deduction's arithmetic. What's degraded is traceability: a future reader of `confidence_breakdown` (a user reviewing why a file scored what it did, or Module 06's own implementer) sees `"naming_fallback:version_or_date"` or `"naming_fallback:date"` — neither of which is greppable against `extracted_metadata`'s real keys, weakening exactly the auditability this field was designed to provide (§11 of the design: "the module that causes a deduction-worthy event is the one that must supply the auditable signal for it"). No test currently locks in the *correctness* of these specific strings against the taxonomy — `test_resume_composite_falls_back_to_literal_unknown_when_both_absent` and `test_archive_falls_back_to_unknown_date_when_modified_at_also_missing` both assert the current (inconsistent) strings as if they were the intended contract, which would make a future "fix" look like a regression to an unwary test-runner.

**Trade-off:** None for Video (a strictly more precise label, `"content_date"`, is directly available and costs nothing). For Resume and Archive's composite/absent-field cases, no single existing taxonomy field name is fully accurate either (the point is that *two* fields, or *no* field, were checked) — a synthetic label is arguably unavoidable there, but should be explicitly disclosed as an exception in `NamingSignals`'s docstring rather than silently contradicting its own stated rule.

**Smallest acceptable fix (not applied):** Rename Video's recorded label from `"date"` to `"content_date"` (a one-line change, `_fill_video()`). For Resume's `"version_or_date"` and Archive's `"date"`, either (a) amend `NamingSignals`'s docstring to explicitly disclose these as named, deliberate composite/no-field exceptions to the "taxonomy field name" rule, or (b) pick a more specific convention (e.g. record both candidate field names for Resume's composite: nothing candidate to report for Archive since none exists). This is a business-rule-adjacent judgment call (which convention Module 06 should expect), not purely mechanical — worth your explicit direction rather than a unilateral pick.

---

### M2 (Medium) — `sanitize_filename()`'s longest-segment truncation does not guarantee the ~80-character cap, and can introduce a stray/doubled underscore, when overflow exceeds the single longest segment's own length

**Explanation:** §12 (confirmed) states: *"if the filled-and-sanitized name... exceeds ~80 characters, the single longest field value is truncated first, preserving the template's overall structure and every other field intact."* The implementation (`_truncate_longest_segment()`) truncates exactly one segment, exactly once, clamping to a minimum of 0 characters (`new_length = max(0, len(segments[longest_index]) - overflow)`) — it never checks whether that single truncation was actually sufficient, and never truncates a second segment if not.

Empirically confirmed by constructing an input with several large, comparably-sized segments (a realistic shape for a category with two or three lengthy Claude-derived text fields, e.g. Contract's `contract_type`/`counterparty`, or Document's `best_guess_title`):
```
Input: 5 segments x 20 chars = 104 characters
Result: '_Xxxxxxxxxxxxxxxxxxxx_Xxxxxxxxxxxxxxxxxxxx_Xxxxxxxxxxxxxxxxxxxx_Xxxxxxxxxxxxxxxxxxxx'
Result length: 84  (still over the ~80-character cap)
```
The first segment was truncated to zero length (its full 20 characters absorbed into the 24-character overflow, with 4 characters of overflow left over and nowhere else to go), leaving an empty string in the segment list. `"_".join(...)` then renders that empty segment as a bare, leading underscore — a second, related cosmetic defect (a doubled/leading `_` that wouldn't occur if the empty segment were dropped rather than joined).

**Root cause:** the algorithm assumes the single longest segment's own length is always ≥ the total overflow — true whenever the template has one dominant long field and the rest are short (the case the committed test, `test_sanitize_filename_truncates_longest_segment_over_80_chars`, exercises: a 100-char segment plus two short bookends), but not true in general. No test exercises multiple large, comparably-sized segments.

**Impact:** Low-to-moderate likelihood in practice — most templates have 2–3 segments and typically one Claude-derived field dominates (e.g. Document's `best_guess_title`, Contract's `contract_type`+`counterparty`), but Contract in particular has two independently-Claude-derived text fields (`contract_type`, `counterparty`) plus a short date, making a "no single segment can absorb the whole overflow" scenario plausible, not purely theoretical. When it occurs: the resulting filename can exceed the documented ~80-character soft cap by an unbounded amount (worse with more/larger segments), and can contain a stray leading or doubled underscore — neither a crash, a security issue, nor data loss, but a real, demonstrated deviation from §12's own stated guarantee, and a filename shape a downstream reviewer or Module 07 wouldn't expect from a "sanitized" name.

**Trade-off:** A multi-pass version (truncate the longest segment; if still over budget, truncate the new-longest segment; repeat) is a small, mechanical, deterministic extension of the exact same rule already approved (§29 item 6) — not a new business rule, since "truncate the longest segment(s) until it fits" is a direct, non-controversial extension of "truncate the longest segment," not a competing design. Dropping empty segments before the final join is likewise a small, non-controversial correctness fix, not a new rule.

**Smallest acceptable fix (not applied):** Make `_truncate_longest_segment()` iterative (repeat the longest-segment truncation until the total is ≤80 or every segment is empty), and filter out empty-string segments before `"_".join(...)` in `sanitize_filename()`. Both are confined to `sanitize_filename()`/`_truncate_longest_segment()`; no other function's behavior needs to change.

---

### M3 (Medium) — §22's Test Strategy commitment ("the fallback path for every required and optional field," for every category) is not fulfilled for at least four categories, the same class of gap `Module 04 Design.md`'s own implementation audit (M3) found and required to be closed

**Explanation:** Cross-checked `Module 05 Design.md` §22's committed test strategy — *"Template-filling correctness for every category, using the confirmed real field mappings... **including the fallback path for every required and optional field**"* — line by line against `src/pipeline/test_naming.py`'s actual coverage per category:

| Category | Fallback-path test(s) present? |
|---|---|
| Invoice | Yes (both required fields, plus the optional-omission case) |
| Resume | Yes (both branches of the composite, plus the double-absent case) |
| Bank Statement | **No** — only `test_bank_statement_clean_match` (all fields present); `bank_name`/`statement_period` missing is never exercised |
| Contract | **No** — only `test_contract_uses_counterparty_not_party_name` (all fields present); no missing-field case at all |
| Document | Partial — `document_date` (optional) missing is tested; `best_guess_title` (required) missing is **not** |
| Image | **No** — only `test_image_clean_match` (all fields present); neither `description` (required) nor `variant` (optional) missing is tested |
| Screenshot | **No** — only `test_screenshot_clean_match` (all fields present); `context_description`/`capture_date` missing is never exercised |
| Application | **No** — only `test_application_clean_match` (all fields present, and see L1 below); `app_name`/`version`/`platform` missing is never exercised |
| Archive | Yes | Video | Yes | Audio | Yes | Unknown | N/A (no `extracted_metadata` dependency) |

Four categories (Bank Statement, Contract, Image, Screenshot, Application — five, not four) have **zero** fallback-path coverage at all, and Document is missing coverage for its required field. This is the identical class of gap `Module 04 Implementation Audit.md`'s M3 finding described for that module ("test cases §22 explicitly commits to naming are not actually present") — a design-committed test coverage promise silently under-delivered, which `ENGINEERING_STANDARD.md` §2 names specifically as a recurring risk worth independently checking, not assuming from a high pass count.

**Impact:** The `_SIMPLE_TEMPLATES`/`_fill_simple_template()` fallback path (the general "Unknown_X" substitution mechanism, confirmed correct by direct code inspection and by the categories that *do* test it) is shared code across all six `_SIMPLE_TEMPLATES` categories, so the risk of an actual undetected defect is lower than if each category had bespoke fallback logic — but the *mapping* from category to field name to fallback label (e.g. that Bank Statement's `bank_name` really does fall back to `"Unknown_BankName"` and is recorded as `"bank_name"`, not `"BankName"` or something else) is category-specific data that a shared-code argument doesn't itself verify. This is exactly the gap class this project's own governance says a design-committed test list exists to make independently checkable, rather than trusting "the mechanism is shared, so it's probably fine."

**Trade-off:** None — straightforward, mechanical test additions using the exact same pattern already established for the eight categories that do have coverage.

**Smallest acceptable fix (not applied):** Add one missing-required-field test each for Bank Statement, Contract, Image, Screenshot, Application, and Document's `best_guess_title`, plus a missing-optional-field test for Image's `variant`, Screenshot's `capture_date`, and Application's `version`/`platform` — nine to eleven small additions to `test_naming.py`, following the exact shape of `test_invoice_missing_required_fields_get_unknown_fallback()`.

---

### L1 (Low) — `test_application_clean_match`'s assertion is a weak, unnecessary hedge on a deterministic outcome, the same class of gap as Module 04's carried-forward G4

**Explanation:** `assert name == "Zoom_6.1_Mac.pkg" or name == "Zoom_61_Mac.pkg"` hedges between two possible outcomes, but the actual behavior is fully deterministic: `sanitize_filename()`'s whitelist (`[^A-Za-z0-9_\-]`) strips `.` unconditionally, so `"6.1"` always becomes `"61"`. Empirically confirmed: `build_filename()` on this exact input always returns `"Zoom_61_Mac.pkg"`, never the other branch. Comparable to Module 04's own G4 finding (a test verifying less than it could, though for a different underlying reason there).

**Impact:** Low — the test still passes/fails correctly today, but the OR-hedge means a future regression that broke period-stripping (e.g. someone widening the character whitelist) could produce `"Zoom_6.1_Mac.pkg"` and this test would still pass, silently losing its power to catch that specific class of regression.

**Smallest acceptable fix (not applied):** Replace the OR with the single correct, deterministic assertion: `assert name == "Zoom_61_Mac.pkg"`.

---

### L2 (Low) — Override-applied detection is independently duplicated between `resolve_destination()` and `NamingEngine.suggest_file()`, with no test guarding the two against drift

**Explanation:** `resolve_destination(record)` and `NamingEngine.suggest_file()` each independently re-check `record.duplicate_of is not None` then `record.version_rank == "superseded"`, in the same order, to decide (respectively) the destination folder and the logged `override_applied` value. They agree today because both were written from the same design paragraph (§14) at the same time, but nothing enforces that they stay in agreement if one is ever edited without the other — the same class of risk Module 04's own audit named (L2 there: `_normalize_for_index()`/`normalize_filename()`), where duplicated logic across a module boundary is an accepted, disclosed trade-off *only when a regression test guards it*. No such test exists here (existing tests check `resolve_destination()`'s override behavior and `NamingEngine`'s `override_applied` reporting separately, never asserting they agree for the same record).

**Impact:** Low today (verified consistent by direct inspection); real drift risk without an automated guard, since a future change to one override condition (e.g. adding a new override type) could be applied to only one of the two call sites.

**Smallest acceptable fix (not applied):** A small parametrized test asserting, for a representative set of override/no-override records, that `NamingEngine.suggest_file(record, {}).override_applied` is non-`None` if and only if `resolve_destination(record)` differs from the plain category mapping.

---

### C1 (Cosmetic) — `_SIMPLE_TEMPLATES`'s type annotation doesn't accurately describe `"literal"` entries

**Explanation:** `_SIMPLE_TEMPLATES: Dict[Category, List[Tuple[str, Optional[Tuple[str, str]]]]]` states every spec entry's second element is `Optional[Tuple[str, str]]`, but a `("literal", "Statement")`-style entry's second element is a plain `str`, not a 2-tuple or `None`. Zero runtime impact (Python doesn't enforce this), and the logic that consumes it (`_fill_simple_template()`) handles both shapes correctly by branching on `kind` first.

**Smallest acceptable fix (not applied):** Widen the annotation to `Tuple[str, Union[str, Tuple[str, str]]]`, or introduce a small `TemplateSpec` type alias for clarity. Purely cosmetic; may be fixed on the spot per `ENGINEERING_STANDARD.md` §14's Cosmetic-severity allowance, at your discretion.

---

## Reviewed, no finding (checked against each of the 15 requested verification points)

- **Design fidelity** — every processing step in `NamingEngine.suggest_file()`/`suggest_naming_and_destination_batch()` matches §7's six-step sequence exactly (skip ineligible → build filename → sanitize → resolve destination → resolve within-batch collision → persist and log); `resolve_destination()`'s signature correctly drops `tier` per §8/§29 item 1, confirmed by direct inspection — no `tier` parameter or reference anywhere in `naming.py`.
- **Module Contract compliance** — `suggested_name`/`suggested_destination`/`naming_signals` are the only fields ever assigned by `suggest_naming_and_destination_batch()`; verified by direct code inspection and by the exhaustive `asdict()`-loop immutability test (`test_module_contract_immutability_every_non_owned_field_byte_identical`), which — unlike Module 04's own first-pass implementation (which needed a follow-up Medium finding, M2, to reach this rigor) — was built exhaustively from the start, covering every field on `FileRecord` except the three owned ones.
- **Ownership boundaries / no scope creep into Modules 01–04** — `git diff main --stat` independently confirms the only real source changes are `src/models/naming.py` (new), `src/models/file_record.py` (additive field only), `src/storage/database.py` (additive deserialization branch + docstring), `src/storage/runtime_io.py` (docstring only), `src/pipeline/naming.py` (full rewrite of Module 05's own file), `src/main.py` (new `suggest_naming()` function, additive), plus test/documentation files. No `pipeline/watch_ingest.py`, `pipeline/classification.py`, `pipeline/metadata.py`, or `pipeline/duplicate_detector.py` source was touched (only harmless `__pycache__` bytecode noise from re-running tests). Every upstream field Module 05 reads (`original_name`, `modified_at`, `category`, `extracted_metadata`, `duplicate_of`, `version_group_id`, `version_rank`, `duplicate_signals`) is traceable to an explicit guarantee in the corresponding frozen `MODULE_CONTRACT.md` (all four re-read fresh this pass) — no undocumented, implicit upstream assumption found.
- **Determinism** — `discovered_at` ascending / `file_id` lexicographic tie-break, identical to Module 04's own established order, verified both by direct inspection of the sort key and by `test_batch_deterministic_order_reruns_assign_same_collision_suffixes`/`test_batch_tie_break_by_file_id_for_identical_discovered_at`.
- **Naming template fidelity** — every category's field mapping in `_SIMPLE_TEMPLATES`/`_BESPOKE_FILLERS` matches §10's resolved table exactly, cross-checked field-by-field against both the design table and `src/pipeline/metadata.py`'s real `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` ground truth (not the design doc's prose description of it) — confirmed for all twelve categories. See M1/M3 above for the two sub-issues found within this area.
- **Sanitization behavior** — whitelist-only character stripping, naive per-segment `.capitalize()`, and the "NDA"→"Nda" worked example all verified correct by direct test and by construction (the regex excludes exactly letters/digits/underscore/hyphen). See M2 above for the one genuine gap found (multi-segment truncation).
- **Collision handling** — within-batch-only scope confirmed (no filesystem read anywhere in `naming.py`); `_2`/`_3` suffixing verified correct for 2 and 3+ colliding records, and correctly scoped per-destination (`(destination, name)` as the dict key, not `name` alone) via `test_within_batch_collision_different_destinations_do_not_collide`.
- **`naming_signals` behavior** — always populated (default-constructed `NamingSignals()` when no fallback occurred, never `None` for a processed record), confirmed by test and by `EngineResult`'s `field(default_factory=NamingSignals)`. See M1 above for the one content-accuracy gap found (two categories' recorded field names).
- **Database serialization** — round-trip verified by `test_save_and_load_round_trips_naming_signals` and `test_load_handles_records_module_05_never_touched`; `_reconstruct_typed_fields()`'s new branch mirrors `duplicate_signals`'s existing treatment exactly.
- **Logging** — `suggest_naming_and_destination`'s `details` shape (`suggested_name`, `suggested_destination`, `fields_fell_back`, `collision_suffix_applied`, `override_applied`, `processing_time_ms`) matches `Metadata & Log Schema.md`'s documented shape exactly, verified by direct side-by-side comparison — no `fallback_used`/`provider_metadata` keys, correctly, since Module 05 has no Provider (§17).
- **CLI wiring** — `main.py`'s `suggest_naming()` filter (`status == "discovered" and category is not None and suggested_name is None`) correctly includes `Category.UNKNOWN` (unlike `extract()`'s filter, which correctly excludes it) — verified against §3's explicit requirement; wired into `__main__` after `detect_duplicates()`, before nothing (Module 06 not yet implemented).
- **Regression coverage** — full suite re-run fresh as part of this audit: **276 passed, 0 failed, 0 skipped** (matching the count claimed in `CHANGELOG.md`/`src/README.md`, independently re-verified rather than trusted).
- **Documentation consistency** — `CHANGELOG.md`'s Module 05 entry, `src/README.md`'s status bullet, `Metadata & Log Schema.md`'s updated example and action-type documentation, and `Rules/Naming Rules.md`'s five revised templates are all mutually consistent with each other and with the actual shipped code as of this audit; `src/README.md` correctly states Module 05 is "not yet validated... awaiting your approval to begin the Independent Implementation Audit" (accurate as of the start of this audit) and `Release/VERSIONS.md` correctly still shows Module 05 as "Not started" (accurate — version-ledger updates happen at Release per `ENGINEERING_STANDARD.md` §8, not at Implementation Audit; no discrepancy).
- **Security (path-injection, §19)** — the adversarial tests (`test_sanitize_filename_never_produces_path_traversal_sequences`, `test_build_filename_adversarial_extracted_metadata_never_produces_traversal`) confirm `../../etc/passwd`-style input never survives sanitization; independently re-confirmed by inspection that `_ALLOWED_CHARS`'s whitelist structurally excludes `/` and `.` (so `..` cannot appear) regardless of exceptions list completeness — a closed boundary, not an enumerated blacklist.

---

## Severity Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 3 (M1, M2, M3) |
| Low | 2 (L1, L2) |
| Cosmetic | 1 (C1) |

## Disposition

**Module 05 implementation is not approved for Integration Testing.** Three Medium findings (M1, M2, M3) remain unresolved. Per `ENGINEERING_STANDARD.md` §14, Medium findings block progression to the next stage until resolved or explicitly, visibly disposed of.

Nothing has been fixed — no code was modified during this audit, per your explicit instruction. M1 in particular involves a real business/convention question (what Module 06 should be able to expect from `fields_fell_back`'s exact string values for Resume/Archive's composite-fallback cases) rather than a purely mechanical fix, so it warrants your explicit decision rather than being resolved unilaterally, consistent with this project's established discipline. M2 and M3 are more mechanical (an algorithm correctness fix and a set of straightforward test additions, respectively) but are still reported rather than applied, per the standing instruction for this phase.

Awaiting your direction on which findings to apply, defer, or decline before implementation work resumes.

---

## Second Independent Implementation Audit — first principles, M1/M2/M3/L1/L2 addressed

**Posture:** the same as the first pass — assume I did not write this code, and do not treat "a fix was applied" or "all tests pass" as evidence of correctness on its own. Every finding below was re-derived by reading the actual current code fresh (`src/pipeline/naming.py`, `src/models/naming.py`, `src/pipeline/test_naming.py`, all read in full, not diffed against memory of what changed), not by re-checking only the five items the first pass named. M2's fix was additionally re-verified by mutation testing — reconstructing the exact pre-fix algorithm in isolation and confirming the new regression tests genuinely fail against it (not just pass against the fix).

**Scope verified this pass:** the full, current text of `src/pipeline/naming.py`, `src/models/naming.py`, `src/pipeline/test_naming.py`; `git diff main --stat` (excluding `__pycache__`) re-confirmed the change set is still scoped to exactly the files Module 05 owns or is disclosed to touch — no governance document, module contract, release document, or `Module 05 Design.md` itself was modified this round, consistent with your explicit instruction.

### M1 — re-verified independently: resolved

Re-derived the fix from first principles rather than re-reading the prior pass's description of it. `_fill_resume()` now appends both `"version_indicator"` and `"last_modified_date"` (both real, taxonomy-verified field names — re-confirmed against `src/pipeline/metadata.py`'s `REQUIRED_FIELDS`/`OPTIONAL_FIELDS[Category.RESUME]`) when both are absent, rather than the synthetic `"version_or_date"` label — and I independently confirmed this is the same "one entry per affected field" treatment already used, untouched, by every other multi-required-field category in the same file (Invoice, Bank Statement, Contract), not a new convention invented for Resume alone.

`_tier4_date_component()` now returns the real field name `"modified_at"` (a genuine `FileRecord` field, verified against `src/models/file_record.py`) instead of the synthetic `"date"`, consumed identically by both `_fill_archive()` and `_fill_video()`. Re-verified this doesn't change *when* a fallback is recorded — only *what string* is recorded — by re-tracing both functions' control flow: `contents_summary`/`description`'s own required-field fallback is unaffected (a separate, correctly-named `"contents_summary"`/`"description"` entry), and `content_date`'s own silent, honest-fallback-to-`modified_at` case (Video only) still correctly records nothing when `modified_at` is available, confirmed empirically:
```
Resume both-absent:            ('Resume_Jordan_Unknown.pdf', ['version_indicator', 'last_modified_date'])
Archive modified_at missing:   ('X_Unknown_Date.pdf', ['modified_at'])
Video modified_at missing:     ('X_Unknown_Date.pdf', ['modified_at'])
Video modified_at present:     ('X_2026-01-01.pdf', [])   # correctly empty — honest fallback, not a placeholder
```
No genuine design ambiguity was found requiring escalation: every fix applied is a direct, mechanical application of §5's own already-stated "one entry per affected field, real field name" rule to the two places that previously deviated from it — not an invented convention. `NamingSignals`'s docstring was updated to state this precisely (still an implementation-file docstring, not the frozen design document). **No remaining issue.**

### M2 — re-verified independently: resolved

Re-read `_truncate_longest_segment()`'s new iterative body fresh and independently re-derived its termination property (each iteration either strictly shortens a segment or removes one entirely, and the loop only continues while total length exceeds the cap, so it cannot loop forever) rather than trusting the prior pass's reasoning. `sanitize_filename()`'s empty-segment handling is now inside the loop itself (`segments.pop(longest_index)` when a segment truncates to zero), not a separate post-hoc filter, so no segment ever reaches the final `"_".join(...)` in an empty state.

**Mutation-testing verification** (the same discipline this project's own `Module 04 Implementation Audit.md` established for its M2 finding): reconstructed the exact pre-fix single-pass algorithm in an isolated scratch script and ran the two new regression tests' actual assertions against it:
```
OLD result: '_Xxxxxxxxxxxxxxxxxxxx_Xxxxxxxxxxxxxxxxxxxx_Xxxxxxxxxxxxxxxxxxxx_Xxxxxxxxxxxxxxxxxxxx'  (len 84)
New test 1 (len<=80) would FAIL against OLD code
New test 2 (no __ / leading/trailing _) would FAIL against OLD code
```
Both new tests correctly fail against the reconstructed old behavior and pass against the current code — genuine, load-bearing protection, not tests that would pass regardless. Re-ran the pre-existing single-large-segment test (`test_sanitize_filename_truncates_longest_segment_over_80_chars`) to confirm the iterative rewrite didn't regress the original, simpler case — still passes, converges in one iteration as before. **No remaining issue.**

### M3 — re-verified independently: resolved

Independently re-checked §22's "the fallback path for every required and optional field" commitment against the current `test_naming.py`, category by category, rather than trusting the prior pass's table:
- Bank Statement — `test_bank_statement_missing_required_fields_get_unknown_fallback` now present (both required fields).
- Contract — `test_contract_missing_required_fields_get_unknown_fallback` now present (all three required fields).
- Document — `test_document_missing_required_title_gets_unknown_fallback` now present (the previously-missing required-field case; the optional `document_date` case already existed).
- Image — `test_image_missing_description_gets_unknown_fallback` (required) and `test_image_missing_variant_gets_unknown_fallback` (optional) now present.
- Screenshot — `test_screenshot_missing_context_description_gets_unknown_fallback` (required) and `test_screenshot_missing_capture_date_gets_unknown_fallback` (optional) now present.
- Application — `test_application_missing_required_app_name_gets_unknown_fallback` (required) and `test_application_missing_optional_fields_get_unknown_fallback` (both optional fields) now present.

All twelve categories now have committed fallback-path coverage for every required and optional field referenced by their template. No category outside those named in the fix instruction was touched, per scope. **No remaining issue.**

**Test-authoring note (not a product defect, disclosed for completeness):** the first attempt at three of these new tests (Bank Statement, Contract, Application) asserted the wrong expected casing — e.g. `"Unknown_BankName"` instead of the actual, correct `"Unknown_Bankname"` — because a multi-word fallback label is itself subject to the same per-segment `capitalize()` flattening as any other multi-word segment (the same, already-accepted "NDA"→"Nda" cosmetic cost named in §12). This was caught immediately by the regression suite itself (3 failures on first run) and corrected before this audit pass — confirming the sanitization behavior is correct and the test suite is doing real work, not merely asserting whatever the code happens to produce.

### L1 — re-verified independently: resolved

`test_application_clean_match` now asserts the single deterministic outcome (`"Zoom_61_Mac.pkg"`) with no hedge. Re-confirmed empirically (not re-trusting the fixed test alone) that `"6.1"` deterministically sanitizes to `"61"` given the whitelist's unconditional stripping of `.`. **No remaining issue.**

### L2 — re-verified independently: resolved (duplication removed, not merely guarded)

Confirmed the fix took the stronger of the two options your instruction offered — removing the duplication entirely via a new shared `_determine_override()` helper — rather than the lighter drift-guard-test-only option, and independently verified this doesn't change either public function's behavior: `resolve_destination()`'s only remaining logic is translating `_determine_override()`'s three possible outputs into a destination string; `NamingEngine.suggest_file()` now calls the same helper directly for `override_applied` instead of recomputing the two-condition check inline. Re-ran the override/destination test matrix by hand for a third case beyond what the committed test covers (both `duplicate_of` and `version_rank == "superseded"` set simultaneously — not reachable in practice per Module 04's own mutual-exclusivity guarantee, §26, but worth checking the tie-break behavior anyway): `duplicate_of` correctly takes precedence in both functions identically, since both now route through the same helper's same check order. The new regression test (`test_override_detection_shared_between_destination_and_engine`) was independently re-run and confirmed to actually call both `resolve_destination()` and `NamingEngine.suggest_file()` on the same record and compare them, not just call each in isolation. **No remaining issue.**

### Findings not raised (checked, no new issue found this pass)

- Re-ran the full test suite fresh as part of this pass (not reusing the prior run's count): **290 passed, 0 failed, 0 skipped** — up from 276 (14 net new: 2 Video/Archive `modified_at`-missing tests, 9 M3 fallback-path tests, 3 M2 truncation-edge-case tests, 1 L2 drift-guard test = 15 new, minus 1 test removed — `test_resume_composite_...`/`test_archive_falls_back_...`/`test_application_clean_match` were edited in place, not added, so the net addition is 14).
- Re-confirmed the Module Contract immutability test (`test_module_contract_immutability_every_non_owned_field_byte_identical`) still passes unmodified and untouched by any of these fixes — none of M1/M2/M3/L1/L2 touch which fields Module 05 owns, only the *content* of `naming_signals`/`suggested_name` and *how* they're computed internally.
- Re-confirmed via `git diff main --stat` that no Module 01–04 source file, governance document, module contract, or release document was touched this round — only `src/pipeline/naming.py`, `src/models/naming.py`, and `src/pipeline/test_naming.py` (plus the audit document itself).
- Re-confirmed C1 (Cosmetic, `_SIMPLE_TEMPLATES`'s type-annotation inaccuracy) remains open, unchanged, and out of scope for this round — not included in your approval list.
- Checked whether M1's fix (Resume now recording two entries instead of one for the same underlying "no version/date available" event) creates any double-counting risk for Module 06's future `-10`-per-fallback deduction: confirmed this is *not* a regression relative to existing behavior — Invoice already records two entries (`vendor`, `invoice_date`) for two independently-missing required fields, and Resume's case is exactly the same shape (two independently-checked fields both missing), so Module 06 will deduct `-10` per entry consistently across every category, not specially for Resume. This is a direct, foreseeable consequence of the fix, not a new defect — flagged here for visibility since it changes the deduction *arithmetic* for this specific edge case (was effectively -10 for the combined "no version/date" case, is now -20, one per field), which is a legitimate side effect of the fix you approved, not an unrelated finding.

## Severity Summary (second pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 0 (M1, M2, M3 resolved) |
| Low | 0 (L1, L2 resolved) |
| Cosmetic | 1 (C1, carried forward, unchanged, not in scope for this round) |

## Disposition (second pass)

No Critical, High, or Medium findings remain. **Module 05 is approved for Integration Testing.**

The one carried-forward Cosmetic item (C1) does not block this approval per `ENGINEERING_STANDARD.md` §14 — named here as explicitly disposed of, non-blocking technical debt, not silently dropped. One arithmetic consequence of the M1 fix is disclosed above (Resume's double-absent case now deducts `-10` twice instead of once, once Module 06 exists to consume it) — not a defect, but worth your awareness since it's a behavior change from what the original (buggy) implementation would have produced.

Per the standing "do not skip or merge phases" directive, Integration Testing itself does not begin without your explicit instruction to proceed.

---

## Third Independent Implementation Audit — post-freeze correction #1 (whitespace-to-underscore sanitization fix)

**Posture:** the same as the first two passes — assume I did not write this code, and do not treat "the fix looks right," "the new tests pass," or the first two audit passes' own conclusions as evidence of correctness on their own. Everything below was independently re-derived against the actual current code (`src/pipeline/naming.py`, read fresh in full this pass, not diffed against memory of the prior two passes), re-run, or empirically demonstrated by executing real code — including a fresh mutation-testing check specifically for this fix, the same discipline this project applied to M2's fix in the second pass.

**Trigger:** Module 05 UAT's first real run (`Tests/Module 05 UAT Plan.md`, Finding UAT-1, Medium) discovered that `sanitize_filename()` silently stripped internal whitespace rather than converting it to `_`, undermining the module's own "human-readable filename" purpose for the majority of real, multi-word field values observed in that run. Independently verified (before any fix) as a design-completeness gap, not an implementation defect — confirmed against `Build-out/05 Naming & Destination/Module 05 Design.md` §12's frozen text, which the pre-fix implementation matched exactly. Approved by the project owner as a post-freeze design correction (`Governance/FROZEN_MODULE_CHANGE_POLICY.md`).

**Scope verified this pass:** `Build-out/05 Naming & Destination/Module 05 Design.md` §12 and §22 (both re-read fresh, confirming the new "Post-freeze correction #1" note and the updated confirmed rule); `Rules/Naming Rules.md`'s corrected general rule text; `CHANGELOG.md`'s new dated entry; the full current text of `src/pipeline/naming.py`'s sanitization section (`_normalize_whitespace()`, `_strip_disallowed()`, `sanitize_filename()`); `src/pipeline/test_naming.py`'s 7 new whitespace regression tests plus a re-read of the surrounding sanitization test block for interaction effects; `git status`/`git diff --stat` (excluding `.DS_Store`/`__pycache__`) to independently confirm the touched-file set matches exactly what's disclosed.

### Design-fix fidelity

Re-read §12's new confirmed rule fresh and independently compared it, clause by clause, against the actual implementation rather than trusting the CHANGELOG's own description of the fix:
- **Order of operations:** §12 confirms whitespace normalization runs *before* the whitelist filter. Independently confirmed in code: `sanitize_filename()` calls `_normalize_whitespace(stem)` first, then passes the result into `_strip_disallowed()` — the order is correct and matches the frozen text exactly, not reversed or interleaved.
- **What counts as "whitespace":** §12 says "spaces, tabs, newlines, and other Unicode whitespace." Independently confirmed the regex (`re.compile(r"\s+")`) matches Python's standard Unicode-aware `\s` class for `str` input (not `re.ASCII`-restricted) — verified empirically with a non-breaking space (U+00A0) input, which converted correctly, not left untouched or double-counted as a "disallowed character to strip" by the later whitelist step.
- **Every other §12 rule is unchanged:** independently re-read the whitelist character set (`_ALLOWED_CHARS`, unchanged), Title_Case (`str.capitalize()` per segment, unchanged), and truncation (`_truncate_longest_segment()`, unchanged, still the iterative M2-fixed version) — confirmed byte-for-byte identical to the pre-fix code except for the two new lines in `sanitize_filename()`'s body and the two new/modified docstrings. No collateral change to any other function.

### Fresh empirical verification (not re-trusting the fix's own claims)

Re-ran real code against constructed inputs independently, not reusing the CHANGELOG's or the design note's own worked examples verbatim:
```
'Foo   $$$  Bar'              -> 'Foo_Bar'              # whitespace normalized, non-whitespace disallowed chars still stripped, no stray "_"
'../../etc/passwd Report'     -> 'Etcpasswd_Report'      # §19 path-injection guarantee independently re-confirmed still holds with the new step in place
'NDA_Acme'                    -> 'Nda_Acme'              # pre-existing acronym-casing cosmetic cost (§12) unaffected by this fix
```
The path-injection case is the one genuinely new risk surface this fix could plausibly have introduced (a new regex substitution running earlier in the pipeline) — independently confirmed it does not reopen §19's guarantee: `/` and `..` are not whitespace, so `_normalize_whitespace()` never touches them, and they still reach `_strip_disallowed()`'s whitelist unchanged, which still excludes them by construction.

**Mutation-testing verification** (same discipline as M2's second-pass verification): reconstructed the exact pre-fix `sanitize_filename()` (whitespace falling through to the whitelist filter and being stripped, not converted) in an isolated scratch script, and ran the three most direct new regression tests' actual assertions against it:
```
'Northwind Traders'   -> OLD: 'Northwindtraders'   (test expects 'Northwind_Traders')   -> FAILS against OLD code
'Espresso    Machine' -> OLD: 'Espressomachine'    (test expects 'Espresso_Machine')    -> FAILS against OLD code
'Tab\tSeparated\tValue' -> OLD: 'Tabseparatedvalue' (test expects 'Tab_Separated_Value') -> FAILS against OLD code
```
All three fail against the reconstructed pre-fix code and pass against the current code — genuine, load-bearing protection against a regression to the old behavior, not tests that would pass regardless of the fix.

### Interaction with prior fixes (M1/M2/M3/L1/L2, second-pass) — re-checked, no regression

- **M2 (truncation):** independently re-ran `test_sanitize_filename_enforces_cap_when_overflow_exceeds_single_longest_segment` and `test_sanitize_filename_never_leaves_stray_or_doubled_underscore_after_truncation` fresh — both still pass. Traced why: whitespace normalization happens before the split-into-segments step that truncation operates on, so truncation always sees already-underscore-delimited segments regardless of whether the original delimiter was a real space or an already-existing `_` — no behavioral coupling between the two fixes.
- **M1 (real field names in `naming_signals`):** unaffected — `naming_signals.fields_fell_back` records field names, never the sanitized string content, so this fix cannot touch it. Independently re-ran `test_resume_composite_falls_back_to_literal_unknown_when_both_absent` and the Video/Archive `modified_at` tests — unchanged, still passing.
- **L2 (`_determine_override()`):** unaffected — sanitization runs on `suggested_name`, entirely independent of override/destination logic. Independently re-ran `test_override_detection_shared_between_destination_and_engine` — unchanged, still passing.
- **The M3 fallback-path tests' asserted placeholder casing** (e.g. `"Unknown_Bankname"`, `"Unknown_Contracttype"`) — these placeholder labels (`"BankName"`, `"ContractType"`) contain no whitespace to begin with (they're written as camel-case, not space-separated), so `_normalize_whitespace()` is a no-op on them; independently re-ran all nine M3 tests fresh — unchanged, still asserting the same correct casing, confirming this fix does not alter the already-accepted acronym/multi-word-label-casing cosmetic cost.

### Findings

**None.** No Critical, High, Medium, Low, or new Cosmetic finding was identified during this pass. The fix is a minimal, correctly-ordered, correctly-scoped addition that does exactly what the corrected §12 now specifies, verified independently rather than assumed, with genuine (not merely passing) regression coverage.

### Regression suite

Re-ran the full suite fresh as part of this audit (not reusing a previously reported count): **297 passed, 0 failed, 0 skipped** — up from 290 (7 net new: the whitespace-normalization regression tests). `git status`/`git diff --stat` independently re-confirmed the touched-file set is exactly: `Build-out/05 Naming & Destination/Module 05 Design.md` (§12/§22 correction), `Rules/Naming Rules.md` (general rule correction), `CHANGELOG.md` (new dated entry), `src/pipeline/naming.py` (the fix), `src/pipeline/test_naming.py` (new tests), plus this audit document — no Module 01–04 source, no governance document, no module contract, and no release document touched.

### Carried-forward items

C1 (Cosmetic, `_SIMPLE_TEMPLATES`'s type-annotation inaccuracy) remains open, unchanged, out of scope for this round — not raised again, not silently dropped, consistent with its disposition in the second pass.

## Severity Summary (third pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| Cosmetic | 1 (C1, carried forward, unchanged, not in scope for this round) |

## Disposition (third pass)

No Critical, High, or Medium findings. **Module 05's post-freeze correction #1 is verified sound and Module 05 UAT is approved to restart from Run 1**, per the standing "do not skip or merge phases" directive and your explicit instruction. No implementation code was modified during this audit itself — this pass is verification only.
