# Module 06 (Confidence & Review) — User Acceptance Testing Plan

Follows the exact UAT methodology established by `Tests/Module 04 UAT Plan.md` and
`Tests/Module 05 UAT Plan.md` (per `Governance/ENGINEERING_STANDARD.md` §6.3): a realistic
external Downloads-style folder outside the project, the real `src/main.py` CLI entry points
end to end, and — for Modules 02/03 — live Claude judgment as the actual provider (never a
canned/routing fake; that pattern is Integration-Testing-only, already used and closed out in
`Tests/Module 06 Integration Test Plan.md`). Module 06 itself uses the real, deterministic
`score_confidence_batch()`/`ConfidenceEngine` implementation, with no Provider — Module 06
Design.md §2 confirms it has none.

## Why this has to be a real, external, multi-run pipeline

Module 06's own unit tests and Integration Testing already exercise every deduction rule and
hard floor against controlled/fake inputs. What neither can validate is whether Module 06's
scoring feels *right* against real, messy, judgment-derived content flowing through the full
Module 01→06 chain exactly as an actual end user would run it — including the parts of the
system UAT is specifically positioned to catch that unit/integration testing structurally
cannot: real provider judgment quality (with its disclosed self-graded-sample caveat, per
§6.3), and multi-run behavior (idempotency, determinism) against the *real* `Database/`/
`Runtime/`, not an isolated harness. This UAT's own Run 1 is a direct example of exactly that
last case: a genuine defect that only a real, repeated, end-to-end CLI invocation against the
live project database could surface (see Execution Results below).

## Test data

External folder: `/tmp/uat_m06_downloads/` (outside the project, ephemeral, not preserved past
this session) — 25 entries, 23 discoverable / 2 deliberately skipped (Module 01 skip path:
`zero_byte_file.pdf`, `mystery_notes.xyz`). Built to organically exercise every Module 06
deduction and all four hard floors through real, live-judged content rather than engineered
fixtures wherever possible:

- **Invoice family (6):** a clean, complete invoice (`Invoice_Northwind_Traders.pdf`); a
  sparse draft missing vendor/invoice_number/amount/currency/tax_type
  (`Invoice_Sparse_Draft.pdf`, real `missing_required_field`+`missing_optional_field`+
  `naming_fallback` stacking); a genuinely ambiguous invoice/receipt hybrid
  (`Receipt_Or_Invoice_Ambiguous.pdf`, real `ambiguous_classification`); a real French-language
  invoice (`Facture_Boulangerie_Paris.pdf`, real `non_english_content` via `langdetect`); a
  real three-invoice batch on three pages (`Batch_Invoices_Merged.pdf`, real
  `multi_document_detected` hard floor); an adversarial-filename invoice (emoji + em-dash:
  `invoice_🧾_northstar_—_v2.pdf`).
- **Resume version chain (2):** `Resume_Morgan_Ellis_v1.pdf`/`_v2.pdf`, genuinely different
  content (added role, added `last_modified_date`).
- **Bank Statement pair (2):** `BankStatement_Chase_June2026.pdf` and a `_copy` filename
  variant — intended as a byte-identical exact-duplicate pair; turned out not to be (see Run 1
  notes below) but still real, valid coverage.
- **Contract version chain with a genuine content-driven conflict (2):**
  `Contract_ServiceAgreement_v1.pdf`/`_v2.pdf` — v2's real extracted `effective_date`
  (January 15, 2026) is genuinely earlier than v1's (March 1, 2026), deliberately engineered
  through real document text (not fabricated metadata) to produce a real
  `date_token_disagreement`/`version_conflict`.
- **Near-duplicate images (2):** `Product_Shot_Front.jpg`/`Product_Shot_Angle.jpg`, similar
  Pillow-drawn compositions, real perceptual-hash distance 4 (threshold 5) — real
  `fuzzy_duplicate` hard floor + deduction. (Both were classified `Screenshot`, not `Image`, by
  the real deterministic Screenshot-vs-Image heuristic — see Run 1 notes.)
- **Document (1):** `Document_Employee_Handbook.pdf`, all fields present.
- **Screenshot (1):** `Screenshot_Login_Error.png`, no EXIF (as real screenshots typically
  lack), real vision-judged `context_description`.
- **Locked (1):** `Confidential_Payroll_Statement.pdf`, real password-encrypted PDF (via
  `pypdf`) — real `is_password_protected()` detection, never reaches a provider.
- **Corrupted (1):** `Corrupted_Invoice_Damaged.pdf`, genuinely malformed bytes that raise a
  real `PdfminerException` on extraction — real `Category.UNKNOWN`/`no_extractable_text` path.
- **No-extractable-text (1):** `Scan_Blank_Page.pdf`, a real PDF with an empty page.
- **Deterministic-only categories (4):** `Zoom_Installer_6.1.2.dmg` (Application),
  `Project_Archive_2026.zip` (Archive, real zip with real member files), `Family_Vacation_Clip.mp4`
  (Video), `Voice_Memo_070826.mp3` (Audio, real ID3 tags via a real `ffmpeg`-encoded MP3 +
  `mutagen`).
- **Skip path (2):** `zero_byte_file.pdf` (0 bytes), `mystery_notes.xyz` (unsupported
  extension).

## Steps (planned)

1. Temporarily edit `src/config/sources.yaml` to point at `/tmp/uat_m06_downloads`, restore to
   `path: null` immediately after the run (same convention as Modules 04/05's own UATs).
2. Real `main.scan()`.
3. Real `main.classify(provider=...)` — a purpose-built `ClassificationProvider` whose
   `classify()` returns literal, per-file live judgments formed by reading each real file's
   actual generated content (not a filename-substring routing fake).
4. Real `main.extract(provider=...)` — same live-judgment pattern via a purpose-built
   `MetadataExtractionProvider`, respecting each category's real required/optional taxonomy
   and the Bank Statement closed-taxonomy privacy rule (§7/§18).
5. Real, deterministic `main.detect_duplicates()` (Module 04, no provider).
6. Real, deterministic `main.suggest_naming()` (Module 05, no provider).
7. Real, deterministic `main.score_confidence()` (Module 06, no provider) — the primary
   subject of this UAT.
8. Idempotency: re-invoke all six real CLI functions a second time against the same real
   `Database`/`Runtime`, expecting every stage to report nothing left to do.
9. Determinism: a reversed-input-order rerun in an isolated copy of the store, comparing
   `confidence_score`/`confidence_breakdown`/`tier` for byte-identical results per `file_id`.
10. Archive `metadata_store.json`, `action_log.jsonl`, terminal output, and a summary document
    under `Runtime/UAT/Module06_UAT_<timestamp>/`.

## Expected outcomes

Every Module 06 deduction rule and all four hard floors triggered at least once by real,
live-judged content; a full spread across all three tiers; `confidence_breakdown`/
`hard_floors_applied` arithmetically and logically correct against `Rules/Confidence Rules.md`;
clean idempotent and deterministic reruns; no crash on the corrupted/locked/adversarial-filename
files.

## Pass / Fail

Pass if every expected outcome holds with no Critical/High/Medium finding. Per standing
project instruction, a genuine defect found at any point stops the run immediately — reported,
not fixed — rather than completing the plan.

---

## Execution Results (Run 1, 2026-07-11, archived at `Runtime/UAT/Module06_UAT_2026-07-11_162320/`)

Run 1 executed the real six-stage pipeline (steps 1–7) in full and **stopped** during step 8
(idempotency) on a genuine, severe finding — in **Module 01**, not Module 06.

### What was verified clean before the stop (steps 1–7, complete)

**Real scan:** 25 entries seen, 23 discovered, 2 skipped (`zero_byte_file.pdf`,
`mystery_notes.xyz`) — correct.

**Real live classification (13 real provider calls):** every PDF's category judged by reading
its actual generated text; `Batch_Invoices_Merged.pdf` correctly judged
`multi_document_detected=True` (three distinct invoice blocks on three pages);
`Receipt_Or_Invoice_Ambiguous.pdf` correctly judged `ambiguous=True`; the French invoice
correctly classified `Invoice` despite the language. Confirmed by direct code inspection
(`classification.py`) that `is_locked()`/no-content/malformed-PDF cases never reach the
provider at all — `Confidential_Payroll_Statement.pdf` (locked), `Scan_Blank_Page.pdf`
(no extractable text), and `Corrupted_Invoice_Damaged.pdf` (real `PdfminerException` on a
genuinely malformed file) were all correctly routed to `Category.UNKNOWN` deterministically,
with zero provider calls.

**Organic finding, not a defect:** both `Product_Shot_*.jpg` files — generated via Pillow,
carrying no camera EXIF — were classified `Screenshot`, not `Image`, by
`classify_screenshot_or_image()`'s real third condition ("no camera EXIF data" →
`Screenshot`, confirmed by direct code read of `classification.py` lines 100–112). This is
real, documented, correct Module 02 behavior, not a bug — it means this dataset does not
organically produce an `Image`-category record (not required by the UAT's dimension list; a
disclosed, honest limitation, not a gap that blocks anything).

**Real live metadata extraction (16 real provider calls):** every judgment field for every
non-Unknown-category record supplied by reading real content; the Bank Statement provider
call deliberately withheld balance/transaction figures present in the source text (closed
taxonomy privacy rule, §7/§18) even though nothing in the harness would have stopped it from
being asked for them. One self-corrected harness authoring error (not a module defect, same
established distinction as prior Integration Testing sessions): the first-draft judgment for
the two `Product_Shot_*.jpg` files used `Image`'s field names (`description`/`variant`)
instead of the real assigned category's (`Screenshot`'s `context_description`), discovered
via a first execution, corrected, and Run 1 restarted from the top before any further
verification — a fresh real scan/classify/extract/detect/name/score, not a partial patch.

**Real Module 04 (deterministic):** `Contract_ServiceAgreement_v2.pdf` correctly flagged
`version_conflict`/`date_token_disagreement` — the deliberately-engineered content-driven date
disagreement (v2's real effective date earlier than v1's) resolved correctly.
`Product_Shot_Front.jpg` correctly flagged `fuzzy_duplicate` at `phash_distance=4` (threshold
5). **Organic finding, not a defect:** `Resume_Morgan_Ellis_v2.pdf` also came back
`version_conflict`/`date_token_disagreement`, which was not the intended design (v1/v2 were
meant to be a clean, non-conflicting chain). Root-caused by direct inspection of the real
action log and file mtimes: `v1` has no real `last_modified_date` field (the content never
states one), so `best_available_date()`'s tiered fallback (§9A) correctly falls back to
`v1`'s filesystem `modified_at` — which, because both files were generated within the same
UAT session, is today's date (2026-07-11) — genuinely later than `v2`'s real stated content
date (2026-05-10). The token says v2 is newer; the resolved dates say v1 is "newer." This is
real, correct, fully-documented tiered-fallback behavior (§9A) interacting with an
under-specified test file (no explicit `last_modified_date` on v1), not a defect — a valuable,
organic confirmation of how easy it is for a real-world file lacking a content date to produce
a genuine-looking version conflict via mtime fallback. `BankStatement_Chase_June2026.pdf`/
`_copy.pdf` were also intended as a byte-identical exact-duplicate pair but, on inspection
(`sha256sum`, `cmp`), turned out not to be byte-identical (`reportlab`'s PDF writer embeds a
per-second creation timestamp) — they were instead grouped as a real, clean (non-conflicting)
version chain via Module 04's fuzzy-filename-similarity matching (`_check_version_chain()`'s
`fuzz.ratio()` path, not an explicit `_v1`/`_v2` token). Confirmed, separately, that
`exact_duplicate` carries no Module 06 scored deduction at all (absent from both
`confidence.py` and `Rules/Confidence Rules.md`'s table) — so this substitution costs no
Module 06 coverage dimension.

**Real Module 05 (deterministic):** naming fallbacks correctly applied wherever a real field
was missing (`vendor`, `capture_date` ×3, `version_indicator`/`last_modified_date`,
`platform`); the superseded/older side of every version chain correctly routed to
`~ARCHIVE~/Old Versions/`; a real collision suffix applied where two Screenshot-fallback names
coincided; `Category.UNKNOWN` records correctly routed to `Unknown/Unsorted_...`.

**Real Module 06 — every dimension the user's instruction required, verified arithmetically
against `Rules/Confidence Rules.md`, all correct:**

| Dimension | Real file(s) | Result |
|---|---|---|
| `ambiguous_classification` (−15) | `Receipt_Or_Invoice_Ambiguous.pdf` | 100−15−2−2=81, `approval_required` ✓ |
| `no_extractable_text` (−30) | `Corrupted_Invoice_Damaged.pdf`, `Scan_Blank_Page.pdf` | 70/70, `review_required` (hard floor `unknown_category`) ✓ |
| `missing_required_field` (−8 ea.) | `Invoice_Sparse_Draft.pdf` | −8 (vendor) ✓ |
| `missing_optional_field` (−2 ea.) | most files | every count verified against real extracted fields ✓ |
| `naming_fallback` (−10 ea.) | `Invoice_Sparse_Draft.pdf`, `Resume_v1`, `Product_Shot_*`, `Screenshot_Login_Error.png`, `Zoom_Installer` | every occurrence matches `naming_signals.fields_fell_back` ✓ |
| `fuzzy_duplicate` (−20) | `Product_Shot_Front.jpg` | 100−2−10−20=68 ✓ |
| `version_conflict` (−25) | `Contract_ServiceAgreement_v2.pdf` (engineered), `Resume_Morgan_Ellis_v2.pdf` (organic) | 75, 73 ✓ |
| `non_english_content` (−10) | `Facture_Boulangerie_Paris.pdf` | 100−10=90, `approval_required` — a fully-complete, real French invoice correctly capped just under `auto` purely by language ✓ |
| `locked_file` (−40) | `Confidential_Payroll_Statement.pdf` | 100−40=60; **both** `unknown_category` and `locked_file` hard floors correctly applied to the same record (two independently-true facts, not a double-count of one fact — confirmed against `confidence.py`'s own comment distinguishing this from the single-hard-floor-per-fact rule) ✓ |
| Hard floor: `unknown_category` | `Confidential_Payroll_Statement.pdf`, `Corrupted_Invoice_Damaged.pdf`, `Scan_Blank_Page.pdf` | all forced to `review_required` regardless of score ✓ |
| Hard floor: `fuzzy_duplicate` | `Product_Shot_Front.jpg` | correctly a *minimum* ceiling (`approval_required`), not a fixed override — raw score 68 correctly still landed the stricter `review_required` ✓ |
| Hard floor: `multi_document_detected` | `Batch_Invoices_Merged.pdf` | raw score 96 (which alone reads as `auto`) correctly forced down to `review_required` ✓ |
| Hard floor: `locked_file` | `Confidential_Payroll_Statement.pdf` | ✓ (see above) |
| Tier assignment | all 23 | 9 `auto` / 5 `approval_required` / 9 `review_required` — full spread ✓ |
| `confidence_breakdown` accuracy | all 23 | every entry hand-verified against real `extracted_metadata`/`classification_signals`/`duplicate_signals` ✓ |
| `hard_floors_applied` accuracy | all 23 | verified against the real `score_confidence` action-log entries (this field is log-only by design, mirroring Module 03's `fallback_reason` precedent — not a `FileRecord` field — confirmed by direct code read, not a defect) ✓ |
| Serialization | all 23 | `confidence_score`/`confidence_breakdown`/`tier` round-tripped correctly through `metadata_store.json` ✓ |
| Logging | all 23 | one `score_confidence` action-log entry per record, correct `details` ✓ |
| Adversarial input | `invoice_🧾_northstar_—_v2.pdf` | processed cleanly end-to-end, 98/`auto` ✓ |
| Corrupted file | `Corrupted_Invoice_Damaged.pdf` | ✓ (see above) |
| Cap behavior | — | **structurally cannot be organically triggered by real content under the current taxonomy** — max real `missing_required_field` exposure is Contract's 3 fields (−24, under the −30 cap); max real `missing_optional_field` exposure is Invoice's 4 fields (−8, under the −10 cap). Confirmed by direct inspection of `Module 03 Design.md` §7's taxonomy table. Cap enforcement itself remains fully verified at the unit level (Module 06's own test suite) and was already disclosed as not independently re-derivable through real content in `Tests/Module 06 Integration Test Plan.md` — this UAT reconfirms the same structural fact rather than re-deriving it. Not a gap; an honest, disclosed limit of what real content can prove. |
| Ownership boundaries | all 23 | no non-Module-06 field was altered by `score_confidence()` (spot-checked against pre/post extraction/naming/duplicate fields) ✓ |

### Finding UAT-1 — Critical

**What happened:** step 8 (idempotency) re-invoked all six real `main.py` CLI functions a
second time against the same real, fully-processed `Database`/`Runtime`. `scan()` alone was
expected to report zero new discoveries and leave everything else untouched. Instead, all 23
already-fully-scored records were silently reset — `category`, `extracted_metadata`,
`duplicate_of`/`version_group_id`/`version_rank`, `duplicate_signals`, `suggested_name`/
`suggested_destination`, `naming_signals`, `confidence_score`/`confidence_breakdown`/`tier` all
reverted to their `FileRecord` defaults — and every downstream stage then silently reprocessed
all 23 files from scratch. Because `classify()`/`extract()` were correctly called with no
provider this second time (mirroring an ordinary non-live CLI invocation), every file's
classification fell back to `Category.UNKNOWN`, and the final re-score showed 19 of 23 files
newly forced to `review_required` via a spurious `unknown_category` hard floor — including
files that had legitimately scored a clean 100/`auto` moments earlier.

**Root cause (confirmed by direct code inspection, not inferred):**
`_build_record()` in `src/pipeline/watch_ingest.py` (Module 01) constructs a fresh
`FileRecord` on every scan, explicitly naming only Module 01's own owned fields. When
`find_by_current_path()` locates an existing record for the same file (correctly reusing its
`file_id`/`original_name`/`original_path`/`discovered_at`, exactly as Module 01's Module
Contract promises), every downstream-owned field is left un-carried-forward and therefore
reset to its dataclass default — even when the existing record already has all of them fully
populated from a completed Module 02–06 run. `save_file_record()` in
`src/storage/database.py` then performs a literal whole-object upsert
(`records[index] = record`), so this freshly-defaulted record silently *replaces* the
fully-processed one. This is **not gated on whether the file's content actually changed** —
`content_changed` is computed but used only for an action-log detail flag, never to skip the
destructive overwrite — so it fires on every re-scan of every already-processed file, changed
or not, which is the single most common real-world invocation pattern this tool has (a
user or a scheduled task running it again before reviewing pending approvals).

**Classification:** primarily a **design defect**. Module 01's frozen `Release/Module01/
MODULE_CONTRACT.md` "DOES NOT MODIFY" section states every downstream field is left at its
`FileRecord` default "on every record it produces" — worded, and verified ("direct inspection
of every field in `metadata_store.json` after both real UAT runs"), only from a first-discovery
point of view. Neither Module 01's Design nor its Module Contract ever addresses what should
happen on a re-scan of a file whose downstream fields are already populated; Module 01's own
UAT never exercised that path either. The implementation faithfully implements this
incomplete contract, so `_build_record()`/`save_file_record()` are not contradicting their own
spec — they're correctly implementing a spec that was never complete. Not a Module 06 defect:
Module 06 (and Modules 02–05's own CLI-level idempotency filters, `category is None`/
`confidence_score is None`/etc.) all behaved exactly as designed given the state Module 01
handed them.

**Severity: Critical.** This silently destroys all classification/extraction/duplicate/
naming/confidence work for every already-processed file on every re-scan, unconditionally —
directly undermining CLAUDE.md's own non-negotiable that every action must be reversible/safe
and the entire "human approval step before anything moves" premise this tool exists for: a
file already sitting in a user's pending-approval queue would silently revert to `Unknown`/
`review_required` the next time the tool runs, including an unattended scheduled run
(`src/config/sources.yaml`'s own `execution_mode: scheduled` option). It also retroactively
affects an already-frozen, already-audited, already-released module (Module 01) — every
subsequent module's UAT (02 through 05) ran its own single-pass real pipeline and never
happened to invoke `scan()` a second time against an already-fully-scored store, so this gap
went undetected until Module 06's own idempotency check specifically required it.

**Recommended smallest correction (reported, not applied):**
1. In `_build_record()` (`watch_ingest.py`), when `existing_record` is found, carry forward
   every downstream-owned field from `existing_record` onto the newly-constructed
   `FileRecord` (`category`, `classification_signals`, `extracted_metadata`, `duplicate_of`,
   `version_group_id`, `version_rank`, `duplicate_signals`, `suggested_name`,
   `suggested_destination`, `naming_signals`, `confidence_score`, `confidence_breakdown`,
   `tier`, `processed_at`, `approved_by`, `approved_at`, `reversible`) instead of leaving them
   at their dataclass defaults — preserves Module 01's Module Contract INPUT/OUTPUT surface
   (it still never *sets* another module's fields) while no longer discarding completed work
   on a re-scan.
2. Alternatively or additionally, `save_file_record()` could perform a field-level merge
   (only overwrite fields the calling module owns) rather than a whole-object replace — more
   centralized, but touches shared infrastructure (`storage/database.py`) used by all six
   modules and would need a broader review of every call site.
Either requires the Frozen Module Change Policy process (Module 01 is released): a scoped
design correction to `Module 01 Design.md`/`MODULE_CONTRACT.md`, review, re-freeze, minimal
implementation change, a new regression test (at minimum: "re-scanning an unchanged file whose
downstream fields are already fully populated preserves them byte-for-byte"), and a fresh
Module 01 Independent Implementation Audit, before Module 06 UAT can safely restart Run 1.

### Housekeeping performed after the stop

The real `Database/Metadata/metadata_store.json`, `Database/FileIndex/*.json`,
`Database/History/version_history.json`, and `Runtime/Logs/action_log.jsonl` were reset to
their pristine empty state — undoing the corruption this finding's own reproduction caused to
the live project database, not a fix to the underlying defect (both `watch_ingest.py` and
`database.py` are untouched). `src/config/sources.yaml` was restored to `path: null`. Run 1's
real, clean results (before the corrupting second `scan()` call) are fully preserved in
`Runtime/UAT/Module06_UAT_2026-07-11_162320/`.

### Disposition

**Module 06 UAT is not approved to proceed.** Steps 1–7 (the entirety of Module 06's own
scoring logic, every deduction, every hard floor, every tier) are verified clean. Step 8
(idempotency) surfaced Finding UAT-1, a Critical, previously-undiscovered defect in Module 01.
Pending the user's decision on Finding UAT-1 before this UAT can restart Run 1.

---

## Run 2 — Restart (2026-07-11, archived at `Runtime/UAT/Module06_UAT_2026-07-11_232902_restart/`)

Restarted from Run 1, per the project owner's explicit approval, only after the full Frozen
Module Change Policy correction cycle for Finding UAT-1 was complete: independent root-cause
verification, Module 01 design/contract correction (post-freeze correction #1), implementation,
regression tests, a targeted Independent Implementation Audit, `Release/VERSIONS.md` updated to
Module 01 `v1.0.1`, and a fresh 13-check Pipeline Contract Verification gate — all clean and
separately approved before this restart began. **Not a resume**: the external dataset,
`Database/Metadata`, `Database/FileIndex`, `Database/History`, and
`Runtime/Logs/action_log.jsonl` were all rebuilt/reset from scratch before Run 2 started —
nothing carried over from Run 1's stopped state. Only variable that changed versus Run 1: Module
01 `v1.0.0` → `v1.0.1`. Same external dataset design (regenerated fresh from the same generator
script, same real content), same live-judgment methodology for Modules 02/03, same real Module
01→06 CLI chain, same real, unmodified Modules 02–06 code.

**Steps 1–6 (real scan → classify → extract → detect_duplicates → suggest_naming →
score_confidence): clean, 23/23 files.** Every deduction rule and all four hard floors triggered
by real content again; tier spread 9 `auto` / 5 `approval_required` / 9 `review_required`;
`confidence_breakdown`/`hard_floors_applied` hand-verified arithmetically against
`Rules/Confidence Rules.md` for every one of the 23 records, zero discrepancies. (Individual
per-file scores differ slightly from Run 1's own table in a few places — expected and immaterial:
Run 2's live-judgment answers were re-authored fresh against freshly-regenerated files rather than
reusing Run 1's exact judgment values verbatim, so minor honest differences in, e.g., which
optional field reads as present vs. absent are real, not a defect. What matters — every deduction
rule, every hard floor, and the full three-tier spread — is exercised and arithmetically correct
either way.)

**Step 7 (idempotency): clean — the exact scenario that failed catastrophically in Run 1.** A
second real `scan()` against the same already-fully-scored `Database` correctly reported nothing
new, and all five downstream CLI functions (`classify`/`extract`/`detect_duplicates`/
`suggest_naming`/`score_confidence`) correctly reported nothing left to do. A full field-by-field
diff of `metadata_store.json` before/after confirmed every field of every one of the 23 records
byte-identical except `batch_id` (Module 01's own field, which correctly refreshes on every
scan) — no downstream-owned field was touched.

**Step 8/9 (content-change re-scan): clean.** `Document_Employee_Handbook.pdf` was genuinely
rewritten with different real content (new text, new `content_hash`). A re-scan correctly
preserved `file_id` while updating `content_hash`, and correctly reset all 17 downstream-owned
fields (`category`, `extracted_metadata`, `suggested_name`, `confidence_score`/
`confidence_breakdown`/`tier`, `duplicate_of`/`version_group_id`/`version_rank`, etc.) to their
defaults, confirmed directly against the real persisted record. The record then correctly
re-entered and completed the full Module 02→06 pipeline exactly like a first-discovery file, with
no code change needed anywhere downstream — self-healing via the existing null-based eligibility
filters, exactly as the approved design specifies.

**Step 10 (determinism/logging/serialization/Module Contract boundaries): clean.** Determinism
reconfirmed (reversed on-disk record order, isolated store, byte-identical
`confidence_score`/`confidence_breakdown`/`tier` for all 23 records). Serialization reconfirmed
(every typed field — `Category` enum, `ClassificationSignals`/`DuplicateSignals`/`NamingSignals`
dataclasses, `confidence_score`/`confidence_breakdown`/`tier`'s real Python types — round-trips
correctly across two independent disk reloads). Logging reconfirmed (full six-stage per-file
lifecycle in correct order; `score_confidence` action-log `details` shape matches
`Module 06 Design.md` §16 exactly). Module Contract ownership boundaries reconfirmed (every
Module-06-scored record already had its Module 01–05 fields populated before Module 06 ran).
Full regression suite: **352/352 passing**, unchanged throughout this run.

**One self-caught harness error, disclosed per this project's standing convention — not a module
defect:** the first attempt at the determinism check isolated the metadata-store path but not the
action-log path, briefly writing 23 duplicate `score_confidence` entries into the real
`Runtime/Logs/action_log.jsonl`. Caught immediately by inspecting the log; corrected by removing
exactly those 23 entries and re-deriving the one legitimately-missing entry (the post-content-
change re-score for `Document_Employee_Handbook.pdf`) through real code rather than hand-editing
JSON, then the determinism check was redone with both paths correctly isolated.
`metadata_store.json` itself was never affected at any point (confirmed via diff against a
pre-cleanup snapshot). Full detail in `Runtime/UAT/Module06_UAT_2026-07-11_232902_restart/summary.md`.

### Housekeeping performed after Run 2

`Database/Metadata/metadata_store.json`, `Database/FileIndex/*.json`,
`Database/History/version_history.json`, and `Runtime/Logs/action_log.jsonl` reset to pristine
empty state; `src/config/sources.yaml` restored to `path: null`; the external
`/tmp/uat_m06_downloads_restart/` folder is ephemeral and not preserved past this session, per the
same convention every prior module UAT has followed. `git status` confirmed zero changes to any
`src/pipeline/*.py` file during this run — only the archive folder and this document were added.

### Disposition (supersedes nothing above — Run 1's record stands as history)

**No Critical, High, Medium, Low, or Cosmetic finding.** All ten dimensions required for this
restart are verified clean with direct evidence. **Module 06 UAT is approved to proceed to
Release Audit** — pending the project owner's separate, explicit approval to begin it. Per
standing instruction, Release Audit has not been started as part of this restart.
