# 07 Preview, Approval & Execution

## Purpose
The human checkpoint: show what's about to happen, get a decision, then execute — reversibly.

## Input
All scored/tiered suggestions from one batch (one Watch & Ingest run).

## Output
Executed moves/renames for approved files; an execution record per action feeding into 08 Logging & Reporting.

## Logic
1. **Preview** — present the whole batch as a table: old name → new name, old location → new destination, category, confidence, tier.
   - `auto` tier rows pre-checked.
   - `approval_required` rows unchecked, need individual confirmation.
   - `review_required` rows shown separately as "needs your attention" — these stay in their original location and are never pre-filed anywhere (no dedicated review folder in v1; see `Rules/Folder Rules.md`).
2. **Approval** — user can approve all pre-checked at once, edit any suggested name/destination inline, or reject/skip individual files (skipped files stay untouched in Downloads). Any edit to a suggested category/filename/destination is logged to `Database/Learning/User Corrections.json` — v1 doesn't act on these automatically, but collecting them now means there's real data once learning logic gets built (see `Database/Learning/README.md`).
3. **Execution** — for each approved file:
   - Move + rename in one step.
   - Record the original path/name before the move (this *is* the undo mechanism — no separate trash/backup copy needed since nothing is ever deleted).
4. **Never delete.** Duplicates and superseded versions are moved to `~ARCHIVE~/`, not removed.

## Reversibility
Every executed action is fully reversible by replaying its log entry in reverse (new path/name → original path/name). A "batch undo" should be possible by reversing every action tied to one `batch_id`.

## Edge cases
- Destination folder doesn't exist yet → create it as part of execution (folder-creation is safe/idempotent, not a destructive action).
- User edits a suggested name to something that collides with an existing file → re-run the collision check before executing.
- Execution fails partway through a batch (e.g. permissions error) → log the failure per-file, continue with the rest of the batch, surface failures clearly in that day's `Runtime/Reports/Daily Summary/` entry rather than silently stopping.

## Open questions
- Preferred approval interface: a simple text/table review in chat, or a generated file (e.g. a markdown/CSV preview) the user reviews before saying "go"? Worth deciding once we're ready to build this step.
