# Module 05 UAT — Run 1 Summary (stopped on a genuine finding)

**Timestamp:** 2026-07-09_034717
**Batch:** real `src/main.py` CLI run — `scan()` → `classify(provider=live_judgment)` → `extract(provider=live_judgment)` → `detect_duplicates()` → `suggest_naming()`
**Source folder:** `/tmp/uat_m05_downloads` (external, ephemeral, real files — not preserved after this session, same convention as Modules 01–04's UATs)
**Isolation:** `Database`/`Runtime` paths monkeypatched to a fresh `/tmp` tree for this run; `src/config/sources.yaml`'s `path` was temporarily set to the UAT source folder and restored to `null` immediately after this run stopped.

## Dataset (19 entries, 17 discoverable)

| File | Real content | Category (real judgment / deterministic) |
|---|---|---|
| `Invoice_Amazon_Order.pdf` / `(1).pdf` | Real invoice text (byte-identical pair) | Invoice — exact-duplicate test |
| `Bank_Statement_Chase_June.pdf` / `June_Bank_Records_2026.pdf` | Real statement text, same bank/period, different account | Bank Statement — naming-collision test |
| `NDA_Contract_Acme.pdf` | Real NDA text | Contract |
| `Resume_Taylor_Kim_v1.pdf` / `_v2.pdf` | Real resume text, version-token filenames | Resume — version-chain test |
| `User_Manual_Espresso.pdf` | Real manual text | Document |
| `IMG_5521.jpg` | Real camera EXIF (Make/Model), solid-color test swatch | Image (deterministic) |
| `Screenshot_2026-07-05_Error.png` | No EXIF, blank content, screenshot-marker filename | Screenshot (deterministic) |
| `Slack_4.36.140_Mac.dmg` | — | Application (deterministic) |
| `ProjectFiles_Backup.zip` | Real zip, 3 entries | Archive (deterministic) |
| `Vacation_Clip.mp4` | Real ffmpeg-generated mp4 | Video (deterministic) |
| `Voice_Memo.mp3` | Real ID3 tags via ffmpeg | Audio (deterministic) |
| `Corrupted_Invoice.pdf` | Malformed PDF bytes | Unknown — real extraction-failure recovery |
| `Confidential_Agreement.pdf` | Real password-protected PDF (`pypdf` encryption) | Unknown — real locked-file path |
| `invoice_📄_final_—_v2.pdf` | Real invoice text, adversarial filename (emoji, em-dash) | Invoice |
| `Mystery_Data.xyz` | — | Skipped (`unsupported_extension`) |
| `Empty_File.pdf` | 0 bytes | Skipped (`zero_byte`) |

## Live judgment disclosure (ENGINEERING_STANDARD.md §6.3)

Every category/field judgment below was made by this same Claude session that implemented Module 05 and built these fixtures — not a blind, independent panel. Judgments were grounded in genuinely real, inspected file content (real extracted PDF text, read via `src/core/pdf.py` before judging; real pixel content for the two image files), not fabricated after the fact, and several deliberately exercise honest "nothing to report" outcomes (e.g. Screenshot's blank content judged as having no legible context to describe, rather than a fabricated guess) — but this is still a small, single-session sample and should not be read as statistically meaningful judgment-quality validation.

## What was verified before the stop

- Real `scan()`: 17 discovered, 2 skipped, correctly reconciling (`zero_byte`, `unsupported_extension`).
- Real live-judgment classification: 9 real provider calls (every text-bearing candidate); `Confidential_Agreement.pdf` and `Corrupted_Invoice.pdf` both correctly reached `Category.UNKNOWN` via real locked-file/malformed-file recovery paths, **never calling the provider at all** — genuine, not provider-routed.
- Real live-judgment extraction: 11 real provider calls (9 judgment categories + Image + Screenshot's vision fields); `Screenshot_2026-07-05_Error.png` correctly shows `[incomplete]` (its required `context_description` genuinely left absent by honest judgment).
- Real Module 04: `Invoice_Amazon_Order.pdf` correctly flagged as an exact duplicate of its `(1)` sibling; `Resume_Taylor_Kim_v1.pdf`/`_v2.pdf` correctly formed a version chain (v1 superseded, v2 latest).
- Real Module 05: every one of the 17 records received a real `suggested_name`/`suggested_destination`/`naming_signals`. Naming-collision handling confirmed genuinely (`Bank_Statement_Chase_June.pdf` / `June_Bank_Records_2026.pdf`, same bank/period from independently-judged real content, correctly suffixed `_2`). Exact-duplicate override (`~ARCHIVE~/Duplicates/`) and superseded-version override (`~ARCHIVE~/Old Versions/`) both confirmed against real Module-04 output, naming not short-circuited in either case. `Category.UNKNOWN` handling confirmed for both real-Unknown files (`Unsorted_` prefix, `Unknown/` destination). No unhandled exception anywhere in the run.

## Finding UAT-1 (Medium) — see full detail in `Tests/Module 05 UAT Plan.md`

Real, multi-word field values (a vendor name, a counterparty name, a candidate name, a document title, an archive contents summary) lose their internal word spacing entirely rather than having it converted to underscores, because `sanitize_filename()`'s whitelist strips every disallowed character (including spaces) instead of replacing them — producing run-together, harder-to-read results (`"Northwind Traders"` → `"Northwindtraders"`, `"Acme Industries"` → `"Acmeindustries"`, `"Taylor Kim"` → `"Taylorkim"`, `"Espresso Machine EM-200 User Manual"` → `"Espressomachineem-200usermanual"`) for the majority of real, multi-word field values observed in this run (8 of 17 discovered files, 7 of ~11 judgment-derived-content files).

**Run stopped here per the standing instruction — not fixed, not worked around.**
