# Learning

Where user corrections get captured, so future versions can learn from them. Moved under `Database/` in the `src/`-era restructure — it's persistent structured data the pipeline writes, same category as `Metadata/`, `FileIndex/`, and `History/`.

## v1 scope: passive collection only
v1 does **not** auto-apply learned corrections — that's a later-version feature (see `ROADMAP.md`). What v1 *does* do is cheap and worth building from day one: every time the user edits or rejects a suggestion during `07 Preview, Approval & Execution`, log the correction here. That way, by the time learning logic is worth building, there's already real data to learn from instead of starting from zero.

## `User Corrections.json`
One entry per correction:

```json
{
  "file_id": "uuid",
  "field": "category | filename | destination",
  "suggested_value": "Contract",
  "corrected_value": "Legal Document",
  "category": "Contract",
  "timestamp": "2026-07-05T14:32:00Z"
}
```
