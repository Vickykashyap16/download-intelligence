# Module 03 (Metadata Extraction) — Independent Release Audit

**Posture:** performed as if the auditor did not build Module 03. Nothing below is accepted on the strength of a prior review's conclusion — every claim was re-verified directly against current source: `src/pipeline/metadata.py`, `src/models/file_record.py`, `src/storage/database.py`, `src/storage/runtime_io.py`, `Rules/Confidence Rules.md`, `Rules/Classification Rules.md`, `Rules/Naming Rules.md`, `Rules/Folder Rules.md`, `Build-out/03 Metadata Extraction/Module 03 Design.md`, `Module 03 Design Review.md`, `Module 03 Design Review 2.md`, `Module 03 Implementation Audit.md`, `Tests/Module 03 Integration Test Plan.md`, `Tests/Module 03 UAT Plan.md`, `Release/Module01/MODULE_CONTRACT.md`, `Release/Module02/MODULE_CONTRACT.md`, `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`, `src/README.md`, `Release/VERSIONS.md`, `Release/DEPENDENCY_DIAGRAM.md`, and the actual on-disk state of `Database/` and `Runtime/`.

**Full suite re-run fresh during this audit: 161/161 passing.**

---

## Findings

### F1 — Medium: the project's real `Database/`/`Runtime/` files contain synthetic debug data, not the pristine "empty until first real run" state the project's own conventions promise

`Database/Metadata/metadata_store.json` currently holds two records (`sample_product_photo.jpg`, `sample_screenshot_login_error.png`) with `source_id: "dbg2"`, `batch_id: "2026-07-06_095533"`. `Runtime/Logs/action_log.jsonl` holds 16 matching lines (`discover`/`classify`/`extract_metadata` entries) from the same batch, plus two earlier `discover`-only lines from batch `2026-07-06_095020`.

**Root cause:** an ad-hoc debug script run during this engagement's implementation-audit troubleshooting (verifying `_validate_and_merge()` behavior and log shapes live) called `scan_source()`/`classify_batch()`/`extract_metadata_batch()` directly against this project's real, hardcoded storage paths instead of isolating them to a tmp path — unlike every integration-test and UAT script, which correctly isolated storage via `monkeypatch`. This is a gap in my own debugging discipline during that session, not a defect in Module 03's implementation.

**Why it matters:** `CLAUDE.md`'s own folder map states `Database/`/`Runtime/` are "Empty until first real run." They are not. `save_file_record()` upserts by `file_id` and never truncates the store, so these synthetic entries will sit alongside a user's real first run indefinitely unless cleared now — a real release candidate shouldn't ship with fabricated history already in its live database.

**Impact:** cosmetic to Module 03's code (no test relies on these files; every automated test isolates its own storage) but real to the state of the release candidate itself — a genuine independent auditor reviewing "the complete release candidate," as instructed, would flag live database/log pollution before calling anything frozen.

**Trade-off:** none. Every polluted entry is verifiably synthetic (`source_id: "dbg2"`, filenames pulled from `Samples/Images/`, `provider_name: "fake"`) — there is no real user data at risk, so resetting these two files carries none of the risk the project's "never permanently delete anything" non-negotiable is meant to guard against (that rule protects discovered/classified user files and archived versions, not a debug script's own throwaway output).

**Smallest fix:** reset `Database/Metadata/metadata_store.json` to `[]` and truncate `Runtime/Logs/action_log.jsonl` to empty, restoring the documented "empty until first real run" state. Not applied — awaiting your approval per your instruction not to fix anything automatically.

---

### F2 — Medium: `extract_metadata` is entirely undocumented in the canonical `Metadata & Log Schema.md` — the exact class of gap this doc says was already caught once, recurring

`Build-out/08 Logging & Reporting/Metadata & Log Schema.md`'s action-log section lists `discover`, `classify`, `archive_duplicate`, `archive_superseded_version`, `skip`, `error`, `undo` — but not `extract_metadata`, despite it being a real, shipped, heavily-tested action type `extract_metadata_batch()` writes for every processed file (verified: `grep -n "extract_metadata"` against this doc returns zero matches).

The doc's own text states: *"`classify` had been in use since Module 02 shipped but was never added here... Documentation gap found and fixed during the Module 02 release audit, 2026-07-06."* The same gap has now recurred for Module 03's action type, in the same document, on the same day.

**Why it matters:** this is the single canonical reference for the action log's shape — the doc a Module 08 (Logging & Reporting) builder would read to know what action types and detail shapes exist to summarize. Right now it's silently incomplete for the module currently being released, which is exactly the kind of drift that's cheap to catch now and easy to miss later once Module 08 is being built against it.

**Impact:** no runtime effect (nothing in the current codebase reads this doc programmatically), but it's a real completeness gap in release documentation and a direct risk to Module 08's future correctness.

**Trade-off:** none — this is additive documentation, not a business-logic change.

**Smallest fix:** add `extract_metadata` to the documented action-value list, describing its `details` shape (`category`, `fields_extracted`, `fields_missing`, `mode`, `processing_time_ms`, `extraction_complete`, `fallback_used`, `fallback_reason`, `redacted_fields`, plus `provider_metadata` when a provider was called and `error_detail` when a fallback occurred) — mirroring exactly how `classify` is already documented one bullet above it. Not applied — awaiting approval.

---

### F3 — Low: `Metadata & Log Schema.md` still cites the superseded pointer doc for the `extracted_metadata` field list

Line 88: *"`extracted_metadata` shape varies by category — see field lists in `03 Metadata Extraction.md`."* This is the same short pre-design pointer doc the Implementation Audit's F3 already found stale and redirected `Rules/Confidence Rules.md` away from (missing Image's `capture_date`, merges Video/Audio, "counterparties" vs `counterparty`) — but this sibling citation, in a different document, wasn't updated in that pass.

**Impact:** a future reader following this specific citation lands on a document already known to be incorrect. No code or business-logic effect.

**Trade-off:** none.

**Smallest fix:** update the citation to `Build-out/03 Metadata Extraction/Module 03 Design.md §7`, matching the fix already applied to `Rules/Confidence Rules.md`. Not applied — awaiting approval.

---

### F4 — Medium: `src/README.md`'s Status section doesn't mention Module 03 at all — the project's primary implementation-status doc is stale

Line 62 still reads: *"Everything else is still scaffold. Remaining build order per `Build-out/`: `metadata.py` (Module 03) next, then `duplicate_detector.py` (04)..."* — despite Module 03 being fully implemented, unit-tested (161/161), integration-tested (59/59), UAT'd, and under release review at the time of this audit.

**Why it matters:** this file is the first place a reader (or a future Claude session) would look to understand what's actually built. As written, it actively misstates reality — claiming Module 03 hasn't been started when it's a completed release candidate.

**Impact:** documentation-only; no code or data effect. But high visibility — this is the same file Module 01 and Module 02 each received a dedicated status bullet in in their own turn.

**Trade-off:** none.

**Smallest fix:** add a Module 03 status bullet mirroring the existing Module 01/02 bullets' format (architecture summary, test counts, pointer to `Release/Module03/` once it exists), and update "remaining build order" to start at `duplicate_detector.py` (04). Not applied — awaiting approval.

---

### F5 — Low: `Rules/Naming Rules.md`'s Contract/Audio templates don't cleanly match Module 03's actual taxonomy field names

Contract's naming template placeholder is `{PartyName}`, but Module 03's real taxonomy field is `counterparty`. Audio's documented fallback template is `{Description}_{Date}`, but Audio's taxonomy (`REQUIRED_FIELDS`/`OPTIONAL_FIELDS` in `metadata.py`) has no `description` field at all — only `track_title`, `artist`, `duration`, `recording_date`. Unlike `Rules/Confidence Rules.md` (now regression-tested against the taxonomy per the Implementation Audit's F2 fix), nothing checks `Naming Rules.md`'s placeholders against real field names.

**Why it matters:** no functional impact today — Module 05 (Naming & Destination) doesn't exist yet, and `Naming Rules.md` is explicitly marked "a draft to react to, not a locked spec." But it's a real mismatch a Module 05 implementer will have to resolve, and it costs nothing to flag now rather than rediscover later.

**Impact:** none today; a latent Module 05 design question.

**Trade-off:** fixing `Naming Rules.md` now is arguably premature given it's explicitly a pre-Module-05 draft; noting it is proportionate, changing it isn't clearly this audit's place.

**Smallest fix:** none required for Module 03's release. Recommend carrying this forward as a named item for Module 05's design phase rather than editing `Rules/Naming Rules.md` now. Not applied — informational only.

---

## Reviewed, no finding (re-verified fresh, not trusted from prior review)

- **Design fidelity:** `REQUIRED_FIELDS`/`OPTIONAL_FIELDS` in `metadata.py` match `Module 03 Design.md` §7 field-for-field, for all 11 non-Unknown categories — independently re-read both side by side, not just re-run the existing drift-guard test.
- **F1–F4 from the Implementation Audit:** all four re-verified resolved directly against current source — boolean exclusion present in `_validate_and_merge()`; the two drift-guard tests exist and pass; `Rules/Confidence Rules.md` line 21 now cites `Module 03 Design.md`; `Module 03 Design.md` §13's JSON example includes `extraction_complete` and no longer shows a misleading always-present `error_detail: null`.
- **Module Contract correctness:** `extract_metadata_batch()` only ever writes `record.extracted_metadata`; every other `FileRecord` field is read-only from Module 03's perspective — confirmed by direct code read, not just by re-citing the existing contract test.
- **Cross-module compatibility (Module 01/02):** `Release/Module01/MODULE_CONTRACT.md` and `Release/Module02/MODULE_CONTRACT.md` re-read fresh; no field either module owns is written by Module 03; both contracts' "DOES NOT MODIFY" lists are accurate against `metadata.py`'s actual read/write surface.
- **Privacy/redaction correctness:** `_validate_and_merge()`'s account_last4 digit-count rule (>4 digits → `null` + name-only logging; ≤4 including empty → pass through) re-read line-by-line against §18 — exact match, scoped correctly to Bank Statement only.
- **Timestamp correctness:** `capture_date` sourced only from `get_capture_date()` (EXIF, tier 2), Video's `content_date`/`duration` unconditionally `None`, Audio's `recording_date` from tier-1 tags only — no tier-4 (filesystem) substitution anywhere in `metadata.py`.
- **Serialization:** `asdict()`/`json.loads()` round-trip confirmed for `extracted_metadata` (plain dict, no typed reconstruction needed, matches `_reconstruct_typed_fields()`'s deliberate omission of this field).
- **Security:** `core/archive.py`'s `summarize_contents()` only calls `zipfile.namelist()` — no entry decompression — re-confirmed by direct read.
- **Performance:** re-confirmed via the Integration Test Plan's measured 75-file/0.280s result; nothing in `metadata.py` suggests a different result today (unchanged since that measurement).
- **Regression coverage:** 161/161 passing fresh (re-run during this audit, not reused from a prior report). `test_metadata.py`'s taxonomy-drift tests (Implementation Audit F2's fix) re-run and pass.
- **UAT evidence quality:** `Runtime/UAT/Module03_UAT_2026-07-06_100928/` re-read fresh — real external folder, real CLI entry point (`scan()`/`classify()`/`extract()`), genuine live-judgment providers, and a deliberately adversarial redaction test (the full real account number fed as the "live" answer) rather than only well-behaved cases. Evidence is concrete (grep-verified zero matches for the unredacted account number, real EXIF/ID3 timestamps), not asserted.
- **`Release/VERSIONS.md`/`Release/DEPENDENCY_DIAGRAM.md`:** both re-read fresh; Module 03 correctly still shows "Not started" (that ledger only tracks *released* status, and release artifacts haven't been generated yet) and the dependency chain is unchanged and correctly linear.
- **Future Module 04 (Duplicate & Version Detection) compatibility:** `content_hash`/`duplicate_of`/`version_group_id`/`version_rank` are all Module 01/04 territory, untouched by Module 03 — confirmed no collision.
- **Future Module 06 (Confidence & Review) compatibility:** the taxonomy `Confidence Rules.md`'s deduction math depends on is now correctly cited and regression-tested against drift (Implementation Audit F2).
- **Future Module 07 (Preview, Approval & Execution) compatibility:** Module 03 never touches `processed_at`/`approved_by`/`approved_at`/`reversible` — confirmed absent from its write surface.

---

## Severity Summary (original pass)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 3 (F1, F2, F4) |
| Low | 2 (F3, F5) |
| Cosmetic | 0 |

---

## Remediation (second pass — Medium findings only, per instruction)

Applied smallest-possible fixes to F1, F2, F4. F3 and F5 (Low) were explicitly excluded from this round's scope and remain open by instruction, not oversight.

**F1 — resolved, verified.** `Database/Metadata/metadata_store.json` reset to `[]` (both records had `source_id: "dbg2"` — 100% of the file's content was confirmed synthetic). `Runtime/Logs/action_log.jsonl`'s 6 lines tied to those same two `dbg2` file_ids (batch `2026-07-06_095533`: 2 `discover` + 2 `classify` + 2 `extract_metadata`) were removed. No archived UAT evidence touched (`Runtime/UAT/*` untouched, confirmed by directory listing).

**New discovery surfaced during remediation, not yet acted on:** the action log's remaining 10 lines (batches `2026-07-06_095020` and `2026-07-06_095313`) are *also* clearly synthetic debug output — their file_ids don't correspond to any record in the now-empty `metadata_store.json`, and their paths point at `Samples/Invoices/` and `Tests/Mixed Downloads/` test fixtures, not real user files — but none of them carry a `source_id: "dbg2"` tag anywhere I can verify (the action log format doesn't record `source_id`, and their `FileRecord`s no longer exist to check directly). Since your instruction scoped this fix specifically to "confirmed synthetic debug entries (source_id: 'dbg2')," these 10 lines were left in place rather than removed on my own judgment — flagging for your direction rather than silently expanding or silently ignoring.

**F2 — resolved, verified.** `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`'s action-log section now documents `extract_metadata` with its full `details` shape, mirroring exactly how `classify` is documented one entry above it. Verified via direct grep against `src/pipeline/*.py` that the only action values the codebase actually writes are `discover`, `classify`, `extract_metadata`, `skip`, `error` — all five are now documented (plus `archive_duplicate`/`archive_superseded_version`/`undo`, reserved for future modules and already present). No remaining undocumented action type.

**F4 — resolved, verified.** `src/README.md`'s Status section now has a Module 03 bullet mirroring the Module 01/02 bullets' format (architecture, test counts, release-record pointer), and "remaining build order" now correctly starts at `duplicate_detector.py` (04) instead of listing `metadata.py` (03) as not yet started.

### Verification

- Full suite: **161/161 passing** (unchanged).
- Module 01–03 isolated (`test_watch_ingest.py` + `test_classification.py` + `test_metadata.py`): **118/118 passing**, identical to pre-remediation counts — confirms F1/F2/F4 (all outside `src/pipeline/*.py`) had zero effect on module behavior.
- Documentation consistency re-check: no remaining reference anywhere in `Build-out/`, `src/`, or top-level docs claims Module 03 "hasn't started" or is "next" to build, other than inside this audit's and the Implementation Audit's own historical-finding text (correctly describing what *was* found, not current state). `Release/VERSIONS.md`/`Release/DEPENDENCY_DIAGRAM.md` correctly still show Module 03 as "Not started" under that ledger's own stated convention (tracks *released*/versioned status only, and release artifacts haven't been generated yet — this is accurate, not stale).

---

## Remediation (third pass — remaining Low findings + the additional log-entry discovery)

**F3 — resolved, verified.** `Build-out/08 Logging & Reporting/Metadata & Log Schema.md` line 88's citation updated from the superseded `03 Metadata Extraction.md` to `Module 03 Design.md` §7, with a note pointing at the Implementation Audit's F3 for why the old doc is superseded. Documentation-only; no business logic touched.

**F5 — resolved, verified, by disposition rather than by editing `Naming Rules.md`.** Per instruction, `Rules/Naming Rules.md` was left untouched — it's explicitly a pre-Module-05 draft, and Module 05 doesn't exist yet to authoritatively resolve the placeholder-to-field-name mapping. The finding is now recorded in the newly-created `Release/Module03/KNOWN_LIMITATIONS.md`, explicitly stating the Contract `{PartyName}`/`counterparty` and Audio `{Description}` mismatches will be addressed during Module 05's design, mirroring the format Module 02's own `KNOWN_LIMITATIONS.md` established.

**Additional log-entry discovery — investigated and resolved.** The 10 action-log lines left in place after Stage 1 (batches `2026-07-06_095020`/`2026-07-06_095313`) were investigated for proof of synthetic origin before any further action, per instruction not to remove them without high confidence:
- Every path referenced points into this vault's own internal fixture directories (`Samples/Invoices/`, `Tests/Mixed Downloads/`) — all pre-existing, named test fixtures built earlier in this engagement for Module 01/02 validation, confirmed still present on disk with matching names.
- `src/config/sources.yaml`'s configured source path is `null` — confirmed by direct read — meaning no real production scan could ever have produced these entries; only a debug script calling `scan_source()` directly with a hardcoded fixture path could have.
- `CLAUDE.md` states explicitly this vault is "the build/planning workspace, not the user's real Downloads folder" — there is no legitimate scenario in which a genuine first real run would scan these paths.
- None of their `file_id`s appear anywhere in `metadata_store.json` (empty since Stage 1) — no persisted `FileRecord` backs any of them.
- Their timestamps (09:50:21, 09:53:13) cluster tightly with the confirmed `dbg2` debug session (09:55:33) the same morning.

This combination (internal-fixture-only paths + a `null` real source path + explicit project framing + no backing record + timestamp proximity to a confirmed debug session) was judged to meet the "high confidence" bar. Before removal, the complete pre-cleanup state of both files was archived to `~ARCHIVE~/Module03_release_cleanup_2026-07-06/` (`metadata_store_original.json`, `action_log_original.jsonl`, and a `README.md` explaining the full two-stage cleanup and its evidence) — this also retroactively closes a gap from Stage 1, where the `dbg2` cleanup was applied without first archiving, at your direction at the time; the complete original state (all 16 lines / both records) is now preserved there regardless. `Runtime/Logs/action_log.jsonl` is now empty, matching `Database/Metadata/metadata_store.json`'s `[]` — both files restored to the documented "empty until first real run" state. No archived UAT evidence (`Runtime/UAT/*`) was touched.

### Verification

- Full suite: **161/161 passing** (unchanged — none of this pass touched `src/pipeline/*.py`).
- Module 01–03 isolated: **118/118 passing** (unchanged).
- Documentation consistency re-check: no remaining stale citation to the superseded `03 Metadata Extraction.md` pointer doc anywhere outside historical audit text describing past findings; `Release/Module03/KNOWN_LIMITATIONS.md` now exists and correctly cross-references this audit; `Release/VERSIONS.md`/`Release/DEPENDENCY_DIAGRAM.md` still correctly show Module 03 as "Not started" under that ledger's own released-status-only convention (release artifacts proper — `MODULE_CONTRACT.md`, `RELEASE_NOTES.md`, `MODULE_STATUS.md`, `PRODUCTION_CHECKLIST.md` — have still not been generated).
- Repository state: `Database/Metadata/metadata_store.json` = `[]`; `Runtime/Logs/action_log.jsonl` = empty; both confirmed via direct read. `~ARCHIVE~/Module03_release_cleanup_2026-07-06/` holds the complete original pre-cleanup state of both files.

---

## Severity Summary (final)

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| Cosmetic | 0 |

## Disposition

All five findings (F1–F5) are resolved or explicitly, transparently disposed of: F1, F2, F3, and the additional log-entry discovery fixed directly; F4 fixed directly; F5 resolved by recording it in `Release/Module03/KNOWN_LIMITATIONS.md` as deferred to Module 05's design, per instruction not to edit `Naming Rules.md` prematurely. No change was made to `src/pipeline/metadata.py`, Module 03's architecture, or any business rule at any point in this audit or its remediation. Full test suite and isolated Module 01–03 suite both pass unchanged throughout.

No Critical, High, Medium, or Low findings remain.

**Module 03 is approved for release artifact generation.**
