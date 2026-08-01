"""Fixture stand-in for the real src/cli.py, used only by
ExecuteViewModelTests to exercise the real `python3 -m src.cli execute -y`
subprocess path end-to-end — including the real action-log write this work
package's result state depends on — without requiring the actual Python
engine.

Deliberately does not reuse ScanningEngineProject's own fixture (a different,
already-frozen job for ScanViewModelTests) or EngineBridgeTests'
FakeEngineProject (a different, already-frozen job for ProcessRunnerTests) —
the same "do not disturb another work package's fixture" precedent both of
those fixtures' own doc comments establish for each other.

`execute`'s behavior below mirrors the real, source-confirmed shape of
`src/cli.py`'s own `execute` subcommand and `src/pipeline/execution.py`'s
`evaluate_gate()`/`execute_batch()` (this work package's own dependency
verification): only `tier == "auto"` records not already `status ==
"executed"` are eligible; each eligible record is either "filed" (a real
`move_rename` action-log entry, `to` pointing at a destination path built
from its own `suggested_destination` + `suggested_name`, `status` flipped to
`executed`) or, for the one fixture record whose `file_id` is
`"auto-locked"` (simulating a deliberately locked/deleted file), left
unmoved and logged with a real `error` action entry instead — proving this
work package's per-file isolation requirement against a real subprocess, not
just the pure `ExecuteResultProjection` unit tests.
"""
import json
import os
import sys

STORE_PATH = os.path.join("Database", "Metadata", "metadata_store.json")
LOG_PATH = os.path.join("Runtime", "Logs", "action_log.jsonl")

LOCKED_FILE_ID = "auto-locked"


def load_store():
    if not os.path.exists(STORE_PATH):
        return []
    with open(STORE_PATH) as handle:
        return json.load(handle)


def save_store(records):
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w") as handle:
        json.dump(records, handle)


def append_action_log(entry):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as handle:
        handle.write(json.dumps(entry) + "\n")


def cmd_execute(args):
    # Mirrors `src/cli.py`'s own two flags — `-y`/`--yes` and `--debug` —
    # exactly what `EngineCommand.execute(yes:debug:).argv` ever produces;
    # this fixture does not need to actually branch on them (this work
    # package always invokes with `-y`, never interactively) but parses them
    # so an unrecognized-argument crash is never mistaken for a real
    # execute-time defect.
    yes = "-y" in args or "--yes" in args
    debug = "--debug" in args
    _ = (yes, debug)

    records = load_store()
    batch_id = "fixture-batch-1"

    for record in records:
        if record.get("tier") != "auto" or record.get("status") == "executed":
            continue

        file_id = record["file_id"]
        if file_id == LOCKED_FILE_ID:
            append_action_log({
                "batch_id": batch_id,
                "file_id": file_id,
                "action": "error",
                "from": record["current_path"],
                "to": None,
                "timestamp": "2026-08-01T10:00:00Z",
                "approved_by": "auto",
                "details": {"error_detail": "Permission denied"},
            })
            continue

        destination_folder = record.get("suggested_destination") or "Unknown/"
        destination_name = record.get("suggested_name") or record["original_name"]
        to_path = "/Users/fixture/Organized Downloads/" + destination_folder + destination_name

        append_action_log({
            "batch_id": batch_id,
            "file_id": file_id,
            "action": "move_rename",
            "from": record["current_path"],
            "to": to_path,
            "timestamp": "2026-08-01T10:00:00Z",
            "approved_by": "auto",
            "details": {},
        })

        record["status"] = "executed"
        record["current_path"] = to_path
        record["processed_at"] = "2026-08-01T10:00:00Z"
        record["batch_id"] = batch_id
        record["approved_by"] = "auto"

    save_store(records)
    print("fixture execute complete")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("fixture: no command given", file=sys.stderr)
        return 2

    if args[0] == "execute":
        return cmd_execute(args[1:])

    print(f"fixture: unrecognized command {args[0]!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
