# Pre-build Context — Downloads Intelligence

*(Note: this folder is still named "00 Pre-build context & examples" for historical reasons — the example files it originally held now live in `Samples/` instead. Can't rename the folder in this workspace; the name is just stale, the content isn't.)*

## 1. What are we building?

**Build type:** Automation (a repeatable process run with Claude in this folder — not a packaged plugin, not a hosted app).

## 2. Goal

An AI-powered Downloads folder assistant that understands file *contents*, not just extensions. It classifies, renames, deduplicates, and files every new download into the right place — with a human approval step before anything moves.

## 3. Core problem

Downloads folders accumulate messy, randomly-named files: duplicates, multiple versions of the same document, and mixed types (invoices, resumes, screenshots, contracts, installers) all dumped in one place. Finding anything later is hard.

## 4. Perfect output

For each new file in Downloads:
- Correct category (Invoice, Resume, Bank Statement, Contract, Document, Image, Screenshot, Application, Archive, Video, Audio, Unknown)
- A clear, descriptive filename following a consistent convention
- A suggested destination folder
- A confidence score driving how much approval is required
- A duplicate/version check against what's already been filed
- A full audit trail (metadata JSON + log entry) so every move is reversible
- A Daily Summary report after each run (see `Runtime/Reports/`)

## 5. Examples

Real example files now live in `Samples/` (not this folder — see `Samples/README.md`), organized by canonical type (Invoices, Images, Videos, Documents) rather than dropped in loose here. Until they're added, the spec below documents expected input/output pairs from the brief:

- `invoice.pdf` → `GST_Invoice_Amazon_2026-07-05.pdf`
- `IMG_8293.jpg` → `Coffee_Table_Black.jpg`
- `Resume_v8.pdf` + `Resume_v9.pdf` → keep v9 as latest, archive v8

## 6. Inputs

Raw files landing in the OS Downloads folder — any type: PDF, DOCX, images (JPG/PNG/HEIC), screenshots, ZIP/archives, video, audio, installers (.exe/.dmg/.pkg), unknown/misc.

## 7. High-level pipeline

```
New File
  → Watch Downloads folder
  → Identify file type
  → Understand file contents (AI if needed)
  → Extract metadata
  → Detect duplicates
  → Suggest new filename
  → Suggest destination folder
  → Show preview
  → User approval
  → Move/Rename
  → Generate logs & metadata
```

Mapped to 8 build sub-systems (see `Build-out/01`–`08`):

| # | Sub-system | Covers |
|---|---|---|
| 01 | Watch & Ingest | Detect new files, filter partial/temp downloads, queue for processing |
| 02 | Classification | File type ID + AI content understanding → category |
| 03 | Metadata Extraction | Pull structured fields per category (vendor, dates, amounts, names...) |
| 04 | Duplicate & Version Detection | Hash-based dupes, perceptual-hash near-dupes, version chains |
| 05 | Naming & Destination | Generate filename + suggest destination folder |
| 06 | Confidence & Review | Score the suggestion, route to auto / approval / review-required |
| 07 | Preview, Approval & Execution | Show batch preview, get user approval, move/rename, stay reversible |
| 08 | Logging & Reporting | Action log, metadata JSON, Reports (Daily/Weekly Summary, Duplicate/Storage Report) |

## 8. Features (v1) — from brief

1. Watch the Downloads folder.
2. Classify: Invoice, Resume, Bank Statement, Contract, Document (generic), Image, Screenshot, Application, Archive, Video, Audio, Unknown.
3. Generate better filenames (see naming conventions doc).
4. Detect duplicate downloads (exact + near-duplicate).
5. Detect newer versions (e.g. `Resume_v8` vs `Resume_v9`) → keep latest, archive older.
6. Suggest destination folders — see `Rules/Folder Rules.md` for the current (simplified) taxonomy; this superseded the more granular per-category folder list originally sketched here.
7. Confidence score: 95–100 `auto` · 80–94 `approval_required` · <80 `review_required` (left in original location, flagged — no dedicated folder; see `Rules/Folder Rules.md`).
8. Generate metadata JSON per file.
9. Maintain logs.
10. Never permanently delete files.
11. Every action must be reversible.
12. Produce a Daily Summary report per run (see `Runtime/Reports/`).

## 9. Tools per step (research notes)

| Step | Candidate tools |
|---|---|
| Watch & Ingest | `watchdog` (Python) or `chokidar` (Node) for real-time watching; or a simple scheduled scan via Cowork's `schedule` skill if a background watcher isn't feasible in this environment |
| Classification | File extension + MIME sniffing (`python-magic`/stdlib `mimetypes`) as a first pass; Claude (text + vision) for content-based classification of ambiguous files |
| Metadata Extraction | `pdfplumber`/`PyPDF2` for PDF text; `Pillow`/`exifread` for image EXIF; Claude for structured field extraction (vendor, invoice #, dates, amounts, names) |
| Duplicate Detection | `hashlib` SHA-256 for exact dupes; `imagehash` (pHash) for near-duplicate images |
| Version Detection | Filename pattern matching (`_v1`, `_v2`, `_final`), `rapidfuzz`/`difflib` for name similarity, mtime/date comparison |
| Naming & Destination | Claude + template rules per category |
| Logging | JSON Lines (`.jsonl`) append-only log; `Database/FileIndex/` JSON files (or SQLite later) for fast hash/dup lookups |

*(Revisit this list once real example files are in hand — actual file types on hand may shift tool choices.)*

## 10. Human vs Claude per step

| Step | Primary owner | Why |
|---|---|---|
| Watch & Ingest | Claude | Mechanical — detecting files, filtering noise |
| Classification | Claude (human refines taxonomy over time) | Objective pattern-matching; human only adjusts categories/edge cases as they emerge |
| Metadata Extraction | Claude | Pure data extraction, no taste involved |
| Duplicate & Version Detection | Claude (human can override "latest") | Mostly objective; occasional semantic override needed |
| Naming & Destination | Claude proposes, human sets the rules initially | Human owns taste — naming style and folder taxonomy are subjective and affect how *they* find files later |
| Confidence & Review | Claude computes, human sets thresholds | Human decides how conservative/risk-tolerant to be |
| Preview, Approval & Execution | **Human** | This is the step that most affects the person using the output — nothing moves without their say-so |
| Logging & Reporting | Claude | Fully mechanical |

## 11. Anything else to remember

- Never delete anything — superseded versions go to `~ARCHIVE~/Old Versions/`, not the trash.
- Every move must be reversible via the action log (original path is always recorded).
- This vault (`Download Intelligence /`) is the **build workspace**; the actual Downloads folder being organized is a separate real folder on the user's Mac, connected when the automation runs.

## 12. Design review updates (2026-07-05)

A follow-up review refined the v1 architecture before implementation:

- **Storage split:** `Database/Metadata/` (current state), `Database/FileIndex/` (hash/name lookups), `Database/History/` (version lineage) — replaces the earlier single "Registry."
- **Rules extracted:** `Rules/Classification Rules.md`, `Rules/Folder Rules.md`, `Rules/Confidence Rules.md`, `Rules/Ignore Rules.md` — modular, editable without touching this spec or the numbered Build-out docs.
- **Logs vs. Reports split:** `Logs/` is machine-readable only (`action_log.jsonl`); `Reports/` holds human-readable Daily/Weekly/Duplicate/Storage summaries.
- **Tests/ added:** `Small Batch/`, `Mixed Downloads/`, `Duplicate Files/`, `Corrupted Files/`, `Large Batch/` — populate in that priority order.
- **Destination taxonomy simplified:** 8 flat top-level folders (Documents, Finance, Images incl. Screenshots, Videos, Audio, Applications, Archives, Unknown) instead of per-category subfolders. Documents/ subfolders documented for later, not pre-built.
- **Confidence scoring formalized:** fixed point deductions + hard floors, fully auditable — see `Rules/Confidence Rules.md`. No more "AI reports a percentage."
- **Execution modes:** Manual (v1 default) → Scheduled (cheap follow-on) → Watch Folder (deferred, real-time daemon is a bigger lift than the core pipeline justifies yet).
- **Learning/ added:** `User Corrections.json` passively captures every user edit/rejection starting in v1, so learning logic has real data once it's built (v2+).
- **Source abstraction:** Watch & Ingest is designed around a "Source" concept (v1 = Downloads only) so Desktop/Drive/OneDrive/Dropbox can be added later without a pipeline redesign.
