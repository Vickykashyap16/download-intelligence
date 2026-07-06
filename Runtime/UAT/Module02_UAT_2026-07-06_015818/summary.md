# Module 02 UAT — Run 1 (2026-07-06, batch/run `2026-07-06_015818`)

First real user-acceptance test of Module 02, run exactly as production would: Module 01's real `scan_source()` against an external, temporary Downloads-like folder (`/tmp/uat_m02_downloads`, not preserved — ephemeral sandbox path, same convention as Module 01's UAT), followed by Module 02's real `classify_batch()` using **live Claude judgment as the actual `ClassificationProvider`** — Claude read each text-bearing file's real extracted content and produced its own category judgment, exactly matching what `ClaudeLiveClassifier` describes doing in a genuine run, rather than a scripted/fake canned response. Plan: `Tests/Module 02 UAT Plan.md`.

## Test data
18 entries in `/tmp/uat_m02_downloads`: 2 invoices (one clean, one messy multi-currency), a bank statement, a contract (NDA), a generic document (espresso machine manual), a resume, a real screenshot (macOS-style filename), a camera-style photo filename with no camera EXIF, a video, an archive, an application installer, an audio file, a malformed PDF, a password-protected PDF, a non-English (French) invoice, a genuinely ambiguous invoice/receipt, plus `.DS_Store` and a `.torrent` file expected to be skipped by Module 01.

## Result

**Module 01 scan:** 16 discovered, 2 skipped (`.DS_Store` → `system_file`, `movie_download.torrent` → `unsupported_extension`) — 18 total, reconciles exactly, matching the plan's expectation.

**Module 02 classification:** All 16 discovered files received a final category. Live provider was invoked exactly 8 times — precisely the 8 text-bearing files that needed real judgment; the other 8 (video/archive/application/audio deterministic-extension files, 2 image-split files, 1 locked PDF, 1 malformed PDF) never reached the provider, as designed.

| File | Category | Signals | Judgment notes |
|---|---|---|---|
| `Amazon_Order_Invoice_2026.pdf` | Invoice | — | Clean, unambiguous |
| `Chase_Statement_June2026.pdf` | Bank Statement | — | Clean |
| `NDA_signed_copy.pdf` | Contract | — | Clean |
| `facture_boulangerie.pdf` | Invoice | `non_english_detected=True`, `detected_language="fr"` | Correctly classified despite non-English content; language signal set independently by the Engine, doesn't block classification |
| `inv_09234_multicur.pdf` | Invoice | — | Multi-currency, terse vendor formatting — still unambiguous |
| `payment_confirmation.pdf` | Invoice | `ambiguous=True` | Document literally reads "RECEIPT / INVOICE" and describes a completed payment rather than an outstanding bill — genuinely reads more like a receipt. No dedicated Receipt category exists in v1's taxonomy, so Invoice is the closest fit; flagged `ambiguous` for Module 06 to weigh later. This is the intended judgment-quality test case. |
| `user_manual_v3.txt` | Document | — | Generic, non-business-type document — correctly landed in the generic bucket rather than Unknown |
| `JordanPatel_Resume_2026.docx` | Resume | — | Clean |
| `Confidential_Agreement.pdf` | Unknown | `locked=True` | Correctly detected as locked deterministically, before any provider call — `fallback_used=False` (locked is a known signal, not a fallback, per design §11) |
| `download_error.pdf` | Unknown | — | Extraction failed deterministically (malformed PDF) — `fallback_used=True`, `fallback_reason="extraction_failed"`; provider never called |
| `Screen Shot 2026-07-04 at 3.42.11 PM.png` | Screenshot | — | Filename marker match |
| `IMG_4821.jpg` | Screenshot | — | No camera EXIF present (synthetic test image) — correctly follows the already-documented heuristic limitation (a real camera photo without EXIF would also land here; see `KNOWN_LIMITATIONS.md`), not a new defect |
| `product_demo_final.mp4` | Video | — | Deterministic |
| `project_files.zip` | Archive | — | Deterministic |
| `SomeApp_Installer.dmg` | Application | — | Deterministic |
| `voice_memo.mp3` | Audio | — | Deterministic |

Full raw output in `metadata_store.json` and `action_log.jsonl` in this folder; `terminal_output.txt` for the exact console output from both the scan and classification steps.

## Judgment quality assessment

Every category assigned matches what a person reading the actual file content would call it. The one deliberately hard case (`payment_confirmation.pdf`) was correctly flagged `ambiguous=True` rather than confidently misclassified either way — this is exactly the kind of signal Module 06 (Confidence & Review) is designed to consume later, not a failure. The non-English invoice was classified correctly despite its French content, with the language signal captured independently. No file was left without a category or signals; no exception occurred during either the scan or classification phase.

## Differences from expected behavior found

None. Every outcome matched `Tests/Module 02 UAT Plan.md`'s expected-outcomes section exactly, including the already-documented Screenshot-heuristic limitation for `IMG_4821.jpg` (expected and called out in the plan itself, not a new finding).

## Verdict

Module 02's classification logic — including live Claude judgment quality on realistic, deliberately messy files — performs correctly end-to-end. No defects found during this UAT run (the one defect this module has produced, the unwrapped image-read failure, was found during the earlier Integration Test Plan execution and fixed/re-verified before this UAT began — see `CHANGELOG.md` and `Tests/Module 02 Integration Test Plan.md` Section 10). Ready to proceed to release artifact production (Task 71).
