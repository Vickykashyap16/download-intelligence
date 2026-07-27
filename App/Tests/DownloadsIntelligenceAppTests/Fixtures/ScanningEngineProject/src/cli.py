"""Fixture stand-in for the real src/cli.py, used only by ScanViewModelTests
to exercise the real `python3 -m src.cli run` subprocess path end-to-end —
including live concurrent polling of the metadata store while the process
is still running — without requiring the actual Python engine.

This intentionally does NOT reuse EngineBridgeTests' `FakeEngineProject`
fixture: that fixture's own `run` branch already has a fixed, different
job (returning exit code 3, for ProcessRunnerTests' exit-code-classification
coverage) that this file must not disturb.

`run`'s behavior below deliberately mirrors the real, source-confirmed shape
of `src/cli.py`'s own `run` subcommand (Finding 4, WP-GUI-04's
pre-implementation analysis):

1. A "scan" phase that produces no observable metadata-store change for a
   short, deliberate window (the real `scan()` only appends records after
   its whole directory walk returns), then appends every newly discovered
   record.
2. A "post-scan" phase that mutates each of those records' `category`,
   then `suggested_name`, then `tier` — one record at a time, with a real
   file write (a full read-modify-write of metadata_store.json, matching
   the real `save_file_record()`'s own confirmed contract) after each
   change, so a real, live poller has something genuine to observe
   incrementally.
"""
import json
import os
import sys
import time

STORE_PATH = os.path.join("Database", "Metadata", "metadata_store.json")

FILE_IDS = ["scan-fixture-a", "scan-fixture-b", "scan-fixture-c"]

PLAN = {
    "scan-fixture-a": {"category": "Invoice", "suggested_name": "invoice_a.pdf", "tier": "auto"},
    "scan-fixture-b": {"category": "Resume", "suggested_name": "resume_b.pdf", "tier": "auto"},
    "scan-fixture-c": {"category": "Document", "suggested_name": "document_c.pdf", "tier": "review_required"},
}


def load_store():
    if not os.path.exists(STORE_PATH):
        return []
    with open(STORE_PATH) as handle:
        return json.load(handle)


def save_store(records):
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w") as handle:
        json.dump(records, handle)


def upsert(records, record):
    for index, existing in enumerate(records):
        if existing["file_id"] == record["file_id"]:
            records[index] = record
            return
    records.append(record)


def base_record(file_id):
    return {
        "file_id": file_id,
        "source_id": "downloads",
        "original_name": f"{file_id}.pdf",
        "original_path": f"/Users/fixture/Downloads/{file_id}.pdf",
        "current_path": f"/Users/fixture/Downloads/{file_id}.pdf",
        "extension": ".pdf",
        "mime_type": "application/pdf",
        "size_bytes": 1024,
        "created_at": "2026-07-27T10:00:00Z",
        "modified_at": "2026-07-27T10:00:00Z",
        "content_hash": f"hash-{file_id}",
        "discovered_at": "2026-07-27T10:00:00Z",
        "status": "discovered",
    }


def cmd_run():
    # Phase 1: simulate scan()'s whole-directory walk — no observable
    # change happens during this window (Finding 4).
    time.sleep(0.6)

    records = load_store()
    for file_id in FILE_IDS:
        upsert(records, base_record(file_id))
        save_store(records)
        time.sleep(0.05)

    # Phase 2: simulate classify() -> suggest_naming() -> score_confidence()
    # (extract()/detect_duplicates() are omitted here since neither
    # contributes an unambiguous-after-success marker field; Finding 4
    # already establishes category/suggested_name/tier as the three real
    # trigger fields), one field at a time, one record at a time, with a
    # real full-file rewrite after every single change.
    for field in ("category", "suggested_name", "tier"):
        for file_id in FILE_IDS:
            records = load_store()
            for record in records:
                if record["file_id"] == file_id:
                    record[field] = PLAN[file_id][field]
            save_store(records)
            time.sleep(0.05)

    print("fixture run complete")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("fixture: no command given", file=sys.stderr)
        return 2

    if args[0] == "run":
        return cmd_run()

    print(f"fixture: unrecognized command {args[0]!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
