# Module 05 (Naming & Destination) — UAT Plan

Real end-to-end acceptance test of the complete Module 01 → 02 → 03 → 04 → 05 pipeline, run the way an actual user would experience it: a realistic, external, Downloads-style folder, scanned by Module 01's real `scan_source()`, classified by Module 02 and metadata-extracted by Module 03 using **live Claude judgment as the actual providers** (exactly as `Tests/Module 03 UAT Plan.md`/`Tests/Module 04 UAT Plan.md` established), duplicate/version-detected by Module 04's real `detect_duplicates_batch()` (no provider — fully deterministic, §14), and named/routed by Module 05's real `suggest_naming_and_destination_batch()` (no provider — fully deterministic, §17) — every stage its real, unmodified, already-frozen-or-audited implementation, no shortcut.

## Why this has to be a real, external, multi-run pipeline

`Tests/Module 05 Integration Test Plan.md` already proved the plumbing works using a routing fake provider for Modules 02/03. What that plan explicitly could not cover is whether Module 05's naming/destination output holds up against genuinely realistic, judgment-derived real-world content — real vendor names, real people's names, real document titles — the way an actual user's Downloads folder would produce them, rather than the plan's own deliberately simple, engineered field values.

## Test data

A new, external folder — `/tmp/uat_m05_downloads` (outside the project, ephemeral, not preserved after the run, same convention as Modules 01–04's UATs) — 19 entries, 17 discoverable, covering: an exact-duplicate invoice pair, a real version chain (Resume, two real versions with genuinely different content), a naming-collision pair (two real Bank Statement PDFs, independently judged to the same bank/period from different account content), every remaining v1 category (Contract, Document, Image, Screenshot, Application, Archive, Video, Audio), a real corrupted/malformed PDF, a real password-protected PDF, an adversarial filename (emoji, em-dash), and two files exercising Module 01's skip path (zero-byte, unsupported extension). Full file-by-file list, real extracted content, and the complete real console transcript are in the archived run folder (see below).

## Steps (planned)

1. **Module 01 (real scan):** `src/main.py`'s real `scan()`, pointed at `/tmp/uat_m05_downloads` via a temporary `src/config/sources.yaml` edit (restored immediately after this run), against isolated `Database`/`Runtime` paths.
2. **Live classification (real judgment):** every text-bearing file's real extracted content (read via `src/core/pdf.py`, inspected before judging), judged live and wired into a `ClassificationProvider` built for this run, passed to `classify(provider=...)`.
3. **Live metadata extraction (real judgment):** every judgment-dependent field, including real visual inspection of the two image-family files, wired into a `MetadataExtractionProvider` built for this run, passed to `extract(provider=...)`.
4. **Module 04 (real, deterministic, no provider):** `detect_duplicates()` — the actual frozen implementation.
5. **Module 05 (real, deterministic, no provider):** `suggest_naming()` — the actual, second-audit-approved implementation.
6. **Repeat runs (planned):** a second `suggest_naming()` invocation with no new files, to prove CLI-level idempotency; an adversarial-filename-focused inspection; a full field-by-field naming-template/fallback/sanitization/collision/override/serialization/logging review across every discovered category.
7. **Archive:** `metadata_store.json`, `action_log.jsonl`, `version_history.json`, `hash_index.json`, `phash_index.json`, `name_index.json`, `terminal_output.txt`, and `summary.md` under `Runtime/UAT/Module05_UAT_<timestamp>/`.

## Expected outcomes

17 discovered, 2 skipped, reconciling exactly; every deterministic category gets its outcome with zero provider calls; every judgment-needing file gets a real, defensible category/extraction; the exact-duplicate pair resolves via `duplicate_of` and routes to `~ARCHIVE~/Duplicates/`; the version chain resolves via `version_rank`, superseded routes to `~ARCHIVE~/Old Versions/`; both overrides leave naming fully, normally computed; the naming-collision pair correctly gets a `_2` suffix; every category's naming template produces a real, human-readable filename from real judgment-derived content, sanitized safely, with the original extension preserved; every genuinely missing field is recorded by its real taxonomy field name and renders its documented placeholder; a repeat `suggest_naming()` call does nothing; no unhandled exception anywhere in the run.

## Pass / Fail

Pass if every outcome above holds against the real implementation with no Critical/High/Medium finding. Per your standing instruction: if UAT discovers a genuine implementation or design defect, stop immediately, do not fix it, and report the finding with severity/root cause/impact/smallest fix instead of completing the plan.

---

## Execution Results (Run 1, 2026-07-09, archived at `Runtime/UAT/Module05_UAT_2026-07-09_034717/`)

**Run 1 was executed in full through Module 05 and stopped there.** A genuine, real, systemically-reproducible finding was discovered on this very first pass, evidenced directly by real, live-judgment-derived content rather than constructed to expose it — the same "discovered through genuine real-world use, not engineered to fail" character as Module 04 UAT's own Finding UAT-1.

### Finding UAT-1 (Medium) — Multi-word field values lose their internal word spacing entirely, rather than becoming underscore-separated, undermining Module 05's own stated "human-readable filename" purpose for the majority of real content observed in this run

**What was observed (real, not constructed):** Every real, judgment-derived, multi-word field value produced by this run's real live-Claude-judgment classification/extraction step lost its internal spaces entirely when Module 05 sanitized it — the words ran together rather than being separated by underscores:

| Real field value (real judgment, real extracted content) | Real `suggested_name` produced |
|---|---|
| Vendor `"Northwind Traders"` (`invoice_📄_final_—_v2.pdf`, real extracted PDF text) | `Northwindtraders_2026-07-04.pdf` |
| Counterparty `"Acme Industries"` (`NDA_Contract_Acme.pdf`, real extracted PDF text) | `Nda_Acmeindustries_2026-06-15.pdf` |
| Candidate name `"Taylor Kim"` (`Resume_Taylor_Kim_v1.pdf`/`_v2.pdf`, real extracted PDF text) | `Resume_Taylorkim_Unknown.pdf` / `Resume_Taylorkim_V2.pdf` |
| Document title `"Espresso Machine EM-200 User Manual"` (`User_Manual_Espresso.pdf`, real extracted PDF text) | `Espressomachineem-200usermanual_Unknown_Date.pdf` |
| Track title `"Voice Memo Draft"` + artist `"Taylor Kim"` (`Voice_Memo.mp3`, real ID3 tags) | `Voicememodraft_Taylorkim.mp3` |
| Image description `"Solid blue-gray color swatch"` (real, live-inspected image content) | `Solidblue-graycolorswatch_Blue.jpg` |
| Archive summary `"notes.txt, assets/"` (real zip listing, `src/core/archive.py`) | `Notestxtassets_2026-07-08.zip` |

**8 of the 17 discovered files (47%), and 7 of the ~11 files with real judgment-derived text content, are directly affected** — this is not a rare edge case; it is the dominant outcome for any real vendor name, person's name, or descriptive title with more than one word, which is the common case for real-world Downloads content, not an unusual one.

**Root cause:** `src/pipeline/naming.py`'s `_strip_disallowed()`/`sanitize_filename()` implements `Module 05 Design.md` §12's confirmed rule exactly as written: *"every other character (including whitespace and all Unicode outside that set) is stripped, not replaced or rejected."* This is faithful, byte-for-byte-compliant implementation — **not an implementation defect**. The design's own §12 explicitly names and accepts one cosmetic cost of this rule (acronym case-flattening, `"NDA"` → `"Nda"`), but never separately named or weighed the much broader, more materially impactful consequence of the *same* "strip, don't replace" mechanism applied to internal whitespace: any multi-word value loses its word boundaries entirely, rather than gaining the underscore separators `Rules/Naming Rules.md`'s own governing convention name — `Title_Case_With_Underscores` — implies spaces should become. `Rules/Naming Rules.md`'s own general rule text (*"`Title_Case_With_Underscores` — no spaces, no special characters"*) is genuinely ambiguous between two readings: "spaces are forbidden and disappear" (what the code does) versus "spaces become underscores, consistent with the convention's own name" (what a reader would more naturally expect from a convention explicitly named "...With_Underscores"). This is a **design-completeness gap**, not a business-rule violation and not an implementation bug: the specific mechanism chosen in §12 (uniform strip-everything-disallowed, applied identically to punctuation and to word-separating whitespace) technically satisfies the letter of both `Rules/Naming Rules.md` and `Module 05 Design.md` §12, but does not deliver on the naming convention's own evident intent for the common case of multi-word real-world values, and this specific, high-impact consequence was not separately surfaced, weighed, or explicitly accepted during the 12-item architectural decision review (only the narrower acronym-casing example was) or during either of the two Independent Implementation Audits (which correctly verified the implementation *matches* §12, not whether §12 itself, once exercised against realistic multi-word content, still serves the module's own stated purpose).

**Impact:** No data loss, no crash, no security issue, no violated hard guarantee (uniqueness, non-blank output, extension preservation, and path-traversal safety all still hold — confirmed in this same run). The impact is entirely a real-world **readability/usability regression against the module's own stated purpose** (`Module 05 Design.md` §1: *"a human-readable filename"*): `"Northwindtraders_2026-07-04.pdf"` and `"Espressomachineem-200usermanual_Unknown_Date.pdf"` are materially harder for a real end user to read at a glance than `"Northwind_Traders_2026-07-04.pdf"` or `"Espresso_Machine_Em-200_User_Manual_Unknown_Date.pdf"` would be — and this affects the majority of real, multi-word content this run actually produced, not a rare edge case. Every downstream consumer of `suggested_name` (a human reviewing Module 07's eventual preview, Module 08's Daily Summary report) inherits this same readability cost.

**Trade-off:** None identified for the smallest fix below — converting whitespace to an underscore before the whitelist strip is not a new business rule; it is a direct, natural extension of `Rules/Naming Rules.md`'s own already-named convention (`Title_Case_With_Underscores`), and would not change any other confirmed §12 behavior (punctuation still strips, `NDA`→`Nda` case-flattening still applies, the ~80-character truncation and collision-suffix logic are both unaffected since they already operate on the underscore-segmented form).

**Smallest acceptable fix (not applied — reporting only, per instruction):** In `sanitize_filename()`, convert runs of whitespace to a single `"_"` *before* applying `_strip_disallowed()`'s existing whitelist filter (e.g. `re.sub(r"\s+", "_", value)` as a new first step), so `"Northwind Traders"` becomes `"Northwind_Traders"` rather than `"Northwindtraders"`, while every other confirmed §12 rule (punctuation stripping, capitalize()-based Title_Case, longest-segment truncation) continues to apply unchanged. This is a one-line addition to one function, requires no change to any template's field mapping, and does not touch `Rules/Naming Rules.md`'s own text (its existing wording is compatible with either reading; only the code's specific interpretation of it changes). Because this changes `sanitize_filename()`'s output for any value that previously contained whitespace, it is a genuine behavior change under `Governance/FROZEN_MODULE_CHANGE_POLICY.md` and should go through that policy's process (severity classification, your explicit approval, a scoped re-audit, and a new regression test asserting the underscore-conversion behavior) rather than being silently patched — consistent with why this finding is being reported and not fixed here.

**Severity: Medium** — a real, systemic, but non-catastrophic defect (readability, not correctness/safety), per `Governance/ENGINEERING_STANDARD.md` §14's shared severity scale ("a designed behavior [is present and functions] but a real defect [in what it actually delivers against the module's own purpose] " — the closest of the defined tiers; not Critical/High since no data loss, crash, or hard-guarantee violation occurred, and not Low since the observed impact rate across this run's real content was the majority case, not a rare corner).

### What was verified before the stop (see `Runtime/UAT/Module05_UAT_2026-07-09_034717/summary.md` for full detail)

- **Real scan:** 17 discovered, 2 skipped (`zero_byte`, `unsupported_extension`), reconciling exactly against the 19-entry dataset.
- **Live classification, real judgment:** 9 real provider calls; `Confidential_Agreement.pdf` (real password-protected PDF) and `Corrupted_Invoice.pdf` (real malformed bytes) both correctly reached `Category.UNKNOWN` via genuine locked-file/malformed-file recovery — **never calling the provider at all**, confirmed real, not provider-routed.
- **Live extraction, real judgment:** 11 real provider calls; `Screenshot_2026-07-05_Error.png`'s genuinely blank content was honestly judged as having nothing legible to describe (required field left absent, not fabricated) — real `[incomplete]` extraction confirmed.
- **Real Module 04:** exact-duplicate pair (`Invoice_Amazon_Order.pdf`/`(1).pdf`) and a real version chain (`Resume_Taylor_Kim_v1.pdf`/`_v2.pdf`, v1 superseded / v2 latest) both correctly detected from real, independently-judged content.
- **Real Module 05 (everything except the sanitization finding above):**
  - **Naming-collision handling** ✓ — `Bank_Statement_Chase_June.pdf`/`June_Bank_Records_2026.pdf`, independently judged to the same real `bank_name`/`statement_period` from genuinely different account content, correctly produced a `_2`-suffixed collision.
  - **Duplicate override** ✓ — `Invoice_Amazon_Order.pdf` routed to `~ARCHIVE~/Duplicates/`, `override_applied == "exact_duplicate"`, naming still fully computed from real content.
  - **Superseded-version override** ✓ — `Resume_Taylor_Kim_v1.pdf` routed to `~ARCHIVE~/Old Versions/`, `override_applied == "superseded_version"`, naming still fully computed.
  - **`Category.UNKNOWN` handling** ✓ — both real-Unknown files correctly received `UNSORTED_`-prefixed names and `Unknown/` destinations.
  - **Fallback behavior, correct field names (M1's fix confirmed with real content)** ✓ — `Resume_Taylor_Kim_v1.pdf` correctly recorded `["version_indicator", "last_modified_date"]` (both real field names, not a synthetic label) when my genuine judgment left both absent; `Screenshot_2026-07-05_Error.png` correctly recorded `["context_description", "capture_date"]`; `User_Manual_Espresso.pdf` correctly recorded `["document_date"]`.
  - **Serialization** ✓ — every record's `naming_signals` round-tripped as a real typed instance through the real on-disk store.
  - **Logging** ✓ — every `suggest_naming_and_destination` entry matched the documented shape.
  - **Adversarial filename** ✓ — `invoice_📄_final_—_v2.pdf` (emoji, em-dash) processed without incident; its own vendor value (`"Northwind Traders"`) is itself part of Finding UAT-1 above, but the filename's own special characters caused no crash or path-traversal issue.
  - **No unhandled exception anywhere in the run** ✓.
- **Application/Archive/Video/Audio (fully deterministic, no judgment)** ✓ — `Slack_4.36.140_Mac.dmg` (`app_name`/`version`/`platform` correctly filename-parsed), `ProjectFiles_Backup.zip` (real zip listing correctly summarized, itself also affected by UAT-1's punctuation-and-space stripping — see table above), `Vacation_Clip.mp4` (filename-stem description), `Voice_Memo.mp3` (real ID3 tags correctly read).

### Not yet reached (per the standing "stop immediately" instruction)

CLI-level idempotency (a repeat `suggest_naming()` call), a dedicated deep-dive on every remaining category's sanitization boundary case, and any further planned scenario beyond what Run 1 already exercised were not reached — the run was stopped at the point Finding UAT-1 was confirmed, not completed further.

**Disposition: Module 05 UAT is not approved to proceed.** This finding is pending your decision — likely remediation under `Governance/FROZEN_MODULE_CHANGE_POLICY.md` (the smallest acceptable fix above, applied only with your explicit approval, followed by a scoped re-audit and regression test), then a UAT restart from Run 1, mirroring exactly how Module 04's own UAT-1 finding was resolved. Per the original instruction, stopping here — no fix applied, no Release Audit begun.

---

## Execution Results (Restart Run 1, 2026-07-09, archived at `Runtime/UAT/Module05_UAT_2026-07-09_041725/`)

Following your approval, Finding UAT-1 was resolved as **post-freeze correction #1** under `Governance/FROZEN_MODULE_CHANGE_POLICY.md`: `Build-out/05 Naming & Destination/Module 05 Design.md` §12 corrected (whitespace now converts to `_` before the whitelist filter, every other §12 rule unchanged), `Rules/Naming Rules.md` corrected to match, `CHANGELOG.md` given a new dated entry, `sanitize_filename()` patched (one new normalization step), 7 new regression tests added (multiple consecutive spaces, tabs, mixed whitespace, leading/trailing whitespace, interaction with pre-existing underscores, Unicode whitespace), full suite re-run clean (297/297), and a fresh, from-first-principles third Independent Implementation Audit found no Critical/High/Medium/Low/new-Cosmetic finding (`Build-out/05 Naming & Destination/Module 05 Implementation Audit.md`, "Third Independent Implementation Audit" section).

**Module 05 UAT then restarted from Run 1**, per the standing "do not skip or merge phases" directive. This restart reused the exact same external dataset (`/tmp/uat_m05_downloads`) and the exact same live-judgment classification/extraction answers as the original (stopped) Run 1 — verbatim, not re-judged — so the corrected sanitization logic is the only variable between the two runs, isolating the fix's effect precisely.

### Finding UAT-1 — confirmed resolved

All 8 previously-affected files now produce correctly underscore-separated names:

| File | Before (original Run 1) | After (Restart Run 1) |
|---|---|---|
| `invoice_📄_final_—_v2.pdf` | `Northwindtraders_2026-07-04.pdf` | `Northwind_Traders_2026-07-04.pdf` |
| `NDA_Contract_Acme.pdf` | `Nda_Acmeindustries_2026-06-15.pdf` | `Nda_Acme_Industries_2026-06-15.pdf` |
| `Resume_Taylor_Kim_v1.pdf` | `Resume_Taylorkim_Unknown.pdf` | `Resume_Taylor_Kim_Unknown.pdf` |
| `Resume_Taylor_Kim_v2.pdf` | `Resume_Taylorkim_V2.pdf` | `Resume_Taylor_Kim_V2.pdf` |
| `User_Manual_Espresso.pdf` | `Espressomachineem-200usermanual_Unknown_Date.pdf` | `Espresso_Machine_Em-200_User_Manual_Unknown_Date.pdf` |
| `Voice_Memo.mp3` | `Voicememodraft_Taylorkim.mp3` | `Voice_Memo_Draft_Taylor_Kim.mp3` |
| `IMG_5521.jpg` | `Solidblue-graycolorswatch_Blue.jpg` | `Solid_Blue-gray_Color_Swatch_Blue.jpg` |
| `ProjectFiles_Backup.zip` | `Notestxtassets_2026-07-08.zip` | `Notestxt_Assets_2026-07-08.zip` |

### Everything else reproduced identically to the original Run 1

Real `scan()`: 17 discovered, 2 skipped, same reconciliation. Real live-judgment classification (9 calls) and extraction (11 calls): same categories, same fields, same honest incomplete-extraction outcome for the genuinely blank Screenshot fixture. Real Module 04: same exact-duplicate pair, same version chain. Real Module 05: same naming-collision suffix (`Bank_Statement_Chase_June.pdf` / `June_Bank_Records_2026.pdf` → `_2`), same exact-duplicate override (`~ARCHIVE~/Duplicates/`), same superseded-version override (`~ARCHIVE~/Old Versions/`), same `Category.UNKNOWN` handling, same fallback field names recorded (`version_indicator`/`last_modified_date` for Resume; `context_description`/`capture_date` for Screenshot; `document_date` for the Document). No unhandled exception.

### Dimensions verified this restart that the original stop had not reached

- **Idempotency (Run 2):** a second `suggest_naming()` call against the same processed batch changed 0 records and appended 0 new action-log entries — confirmed via direct before/after comparison of `suggested_name` across all 17 records and the action-log line count.
- **A dedicated, deeper adversarial-sanitization pass** (13 constructed inputs beyond what the real dataset exercised): nested path traversal (`../../../etc/passwd`, Windows-style `..\..\`), script-injection-style content (`<script>alert(1)</script>`), reserved/special characters (`:`, `*`, `?`, `|`), a 200-character overflow input (correctly capped at ≤80), whitespace-only input (correctly empty), empty input, multi-line input, a zero-width-space (U+200B) input (confirmed correctly *not* treated as whitespace by the `\s`-based normalization — stripped by the whitelist like any other disallowed character, not converted to `_`, verifying the fix's scope is precisely "matches Python's `\s`," not "any invisible-looking character"), and mixed tab-plus-traversal content. Every case: no `/`, no `..`, no crash, correct length cap, correct empty-string handling — §19's path-injection guarantee holds with the new whitespace-normalization step in place, not reopened by it.

### Disposition (Restart Run 1)

No Critical, High, Medium, Low, or new Cosmetic finding. **Module 05 UAT is approved — the restart is complete and clean.** `src/config/sources.yaml` restored to its original state (`path: null`) immediately after the run. Per the standing "do not skip or merge phases" directive, the Release Audit is not begun as part of this run — awaiting your explicit instruction to proceed.
