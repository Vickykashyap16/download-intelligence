# Reports

Human-readable summaries — for reading, not for the automation to parse. Machine-readable execution records live separately in `Runtime/Logs/action_log.jsonl`.

- `Daily Summary/` — one recap per day the automation runs: files scanned, auto-filed, approval-required, review-required, duplicates found, versions archived, errors. In Manual mode there's typically one batch per day; if multiple scans happen in a day, the daily file rolls all of them up. File: `Daily Summary/summary_YYYY-MM-DD.md`.
- `Weekly Summary/` — rollup of the week's Daily Summaries: totals, trends (e.g. review-required rate climbing/falling), any recurring error. File: `Weekly Summary/summary_YYYY-Www.md`.
- `Duplicate Report/` — a running view of duplicates/near-duplicates found and what happened to them (archived, kept, overridden by the user). Useful for spotting patterns, e.g. the same file getting re-downloaded repeatedly.
- `Storage Report/` — current space used per destination folder/category: a cumulative aggregate over every file discovered so far, computed fresh from the metadata store on every run (not a persisted history or trend line — see `Governance/ARCHITECTURE_DECISIONS.md` decision 28). Useful for noticing e.g. Screenshots quietly eating disk space.

## Format
Markdown, generated from `Runtime/Logs/action_log.jsonl` and `Database/Metadata/`. See `Build-out/08 Logging & Reporting/Metadata & Log Schema.md` for the underlying schema these are built from.

Nothing here yet — these populate after the first real run(s).
