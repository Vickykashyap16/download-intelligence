# 08 Logging & Reporting

## Purpose
Leave a full, reversible audit trail of every file the automation touches, and recap each run/period in plain language.

*(Exact schemas live in `Build-out/08 Logging & Reporting/Metadata & Log Schema.md` — this note covers what gets logged/reported and where.)*

## Input
Every executed action from step 07, plus per-file metadata from steps 02–06.

## Output
- One metadata record per file, in `Database/Metadata/`
- Lookup indexes, in `Database/FileIndex/`
- Version lineage, in `Database/History/`
- One append-only machine-readable log line per action, in `Runtime/Logs/action_log.jsonl`
- Human-readable summaries, in `Runtime/Reports/` (Daily Summary, Weekly Summary, Duplicate Report, Storage Report)

## Logic
1. **Database (Metadata/FileIndex/History)** — written/updated the moment a file is processed, whether auto-filed, approved, or sent to review. This is the permanent record used for future duplicate/version checks and reporting.
2. **Logs (`action_log.jsonl`)** — append-only, one line (JSON) per action, tagged with a `batch_id` shared by every file processed in the same run. This is what makes undo possible. Machine-readable only — never rendered directly to the user.
3. **Reports** — generated from Database + Logs, for humans to read:
   - **Daily Summary** — after each day's run(s): files scanned, auto-filed, approval-required, review-required, duplicates found, versions archived, errors.
   - **Weekly Summary** — rollup of the week's Daily Summaries, trends over time.
   - **Duplicate Report** — running view of duplicates/near-duplicates found and what happened to them.
   - **Storage Report** — space used per destination folder/category, growth over time.

## Edge cases
- A file processed twice (re-scanned before being moved) → update its existing `Database/Metadata/` record rather than duplicating it.
- Log/report write fails → never let a logging or reporting failure block the actual file move; surface the failure in the next Daily Summary instead.

## Open questions
- Retention: keep `Runtime/Logs/action_log.jsonl` forever (recommended, it's small/text) — but revisit if it grows large enough to need periodic archiving into `Database/History/`.
