# Runtime

Everything the automation writes while actually running, as opposed to `Database/` (durable structured records the pipeline depends on) and `Build-out/`/`Rules/` (documentation). Grouped here per the src/ restructure so "operational output" has one clear home.

- `Logs/` — machine-readable `action_log.jsonl` (the undo mechanism). See `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`.
- `Reports/` — human-readable summaries: `Daily Summary/`, `Weekly Summary/`, `Duplicate Report/`, `Storage Report/`.
- `Temp/` — working state for an in-progress batch (e.g. `Runtime/Temp/<batch_id>/`), so a batch that crashes mid-execution can resume or be cleanly discarded instead of leaving `Database/`/the destination folders in an inconsistent half-done state. Cleared once a batch completes successfully.

Nothing here yet — placeholders until the first real run.
