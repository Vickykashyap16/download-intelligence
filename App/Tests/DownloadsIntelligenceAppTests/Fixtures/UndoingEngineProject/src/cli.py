"""Fixture stand-in for the real src/cli.py, used only by
UndoViewModelTests to exercise the real `python3 -m src.cli undo --last`
subprocess path end-to-end — including the real action-log write this work
package's result state depends on — without requiring the actual Python
engine.

Deliberately independent from `ExecutingEngineProject` (WP-GUI-07's own
already-frozen fixture, "do not disturb another work package's fixture"):
this fixture starts *already post-execute* — its `metadata_store.json` and
seeded `Runtime/Logs/action_log.jsonl` represent a batch that has already
been filed, exactly the state `UndoViewModel` actually finds itself
constructed against (immediately after an Execute result is on screen).

`undo`'s behavior below mirrors the real, source-confirmed shape of
`src/cli.py`'s own `undo` subcommand and `src/pipeline/execution.py`'s
`undo_batch()`/`undo_single_action()` (this work package's own dependency
verification): `--last` targets the batch of the most recent action-log
entry by timestamp, across the whole log
(`_most_recent_batch_id_from_entries()`); a bare positional argument targets
that literal `batch_id` instead. Each of that batch's `move_rename` entries
is reversed in timestamp-descending order — restored files get a real
`undo` action-log entry (`from`/`to` swapped relative to the original
entry, mirroring `log_undo()`) and have their metadata record reset to
`status: "scored"`, `processed_at: null`; the one fixture record whose
`file_id` is `"restore-conflict"` (simulating something already occupying
the file's original location) is left unmoved and logged with a real
`error` action entry instead — proving this work package's per-file
isolation requirement against a real subprocess, not just the pure
`UndoResultProjection` unit tests.
"""
import json
import os
import sys

STORE_PATH = os.path.join("Database", "Metadata", "metadata_store.json")
LOG_PATH = os.path.join("Runtime", "Logs", "action_log.jsonl")

RESTORE_CONFLICT_FILE_ID = "restore-conflict"
MOVE_LOG_ACTIONS = {"move_rename", "archive_duplicate", "archive_superseded_version"}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path) as handle:
        return json.load(handle)


def save_store(records):
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w") as handle:
        json.dump(records, handle)


def read_action_log_entries():
    if not os.path.exists(LOG_PATH):
        return []
    entries = []
    with open(LOG_PATH) as handle:
        for line in handle:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def append_action_log(entry):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as handle:
        handle.write(json.dumps(entry) + "\n")


def most_recent_batch_id(entries):
    # Mirrors `src/cli.py`'s own `_most_recent_batch_id_from_entries()`: the
    # max-timestamp entry across the *entire* action log, no action-type
    # filtering.
    if not entries:
        return None
    return max(entries, key=lambda entry: entry["timestamp"])["batch_id"]


def cmd_undo(args):
    entries = read_action_log_entries()

    if "--last" in args:
        target_batch_id = most_recent_batch_id(entries)
    else:
        positional = [arg for arg in args if not arg.startswith("--")]
        target_batch_id = positional[0] if positional else None

    if target_batch_id is None:
        print("fixture: nothing to undo")
        return 0

    # Undo the most recent action first, mirroring `undo_batch()`'s own
    # timestamp-descending ordering.
    batch_move_entries = sorted(
        (entry for entry in entries if entry["batch_id"] == target_batch_id and entry["action"] in MOVE_LOG_ACTIONS),
        key=lambda entry: entry["timestamp"],
        reverse=True,
    )

    records = load_json(STORE_PATH, [])
    records_by_id = {record["file_id"]: record for record in records}
    undo_timestamp = "2026-08-01T11:00:00Z"

    for original_entry in batch_move_entries:
        file_id = original_entry["file_id"]

        if file_id == RESTORE_CONFLICT_FILE_ID:
            append_action_log({
                "batch_id": target_batch_id,
                "file_id": file_id,
                "action": "error",
                "from": original_entry["to"],
                "to": None,
                "timestamp": undo_timestamp,
                "approved_by": "user",
                "details": {"error_detail": "Something already exists at the original location"},
            })
            continue

        append_action_log({
            "batch_id": target_batch_id,
            "file_id": file_id,
            "action": "undo",
            "from": original_entry["to"],
            "to": original_entry["from"],
            "timestamp": undo_timestamp,
            "approved_by": "user",
            "details": {"reversed_action": original_entry["action"]},
        })

        record = records_by_id.get(file_id)
        if record is not None:
            record["status"] = "scored"
            record["current_path"] = original_entry["from"]
            record["processed_at"] = None
            record["batch_id"] = None
            record["approved_by"] = None

    save_store(records)
    print("fixture undo complete")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("fixture: no command given", file=sys.stderr)
        return 2

    if args[0] == "undo":
        return cmd_undo(args[1:])

    print(f"fixture: unrecognized command {args[0]!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
