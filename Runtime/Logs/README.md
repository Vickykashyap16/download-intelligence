# Logs

Machine-readable execution records only — not human-readable summaries (those live in `Runtime/Reports/`), and not build/planning docs (those live in `Build-out/`).

- `action_log.jsonl` — append-only, one JSON line per file action. Created on first real run. This is the undo mechanism: every move/rename records its original path.

Schema details: `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`.

Nothing here yet — this folder is a placeholder until the first run.
