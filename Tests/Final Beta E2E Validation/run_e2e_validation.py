"""
Final Beta E2E Validation — one full production-workflow run before beta.

Design: Phase F ("final engineering phase before external beta"), priority 3 —
"one final end-to-end validation using the production workflow: scan,
classify, extract, duplicate detection, naming, confidence scoring, preview,
execute, undo, reports." Explicitly **deterministic mode only** — TD-01's
real-key provider validation is separately tracked and deferred (see
TECHNICAL_DEBT_REGISTER.md's 2026-07-26 update); this run exercises exactly
today's shipped default (no live AI judgment provider configured), which is
also exactly what a beta user gets on first install before ever touching
`provider enable`.

What this script does, precisely, and why it's safe to run against this real
project folder:
  1. Builds a small, synthetic, throwaway dataset in a temp directory — never
     touches the real ~/Downloads folder or its 866 already-discovered real
     records.
  2. Writes a temporary `sources.yaml` pointing at that temp source/
     destination, and monkeypatches the three modules that each hold their
     own `_SOURCES_CONFIG_PATH` copy (`src.main`, `src.cli`,
     `src.pipeline.watch_ingest` — confirmed via `grep` to be the complete
     set) to read it instead of the real file.
  3. Isolates `database_module`/`runtime_io_module`'s storage path constants
     to the same temp directory (identical, proven pattern to
     `run_harness.py`/`run_production_validation.py`) — the real
     `Database/`/`Runtime/Logs/` are never opened for read or write.
  4. Drives the REAL `src.cli.main()` entry point — the exact function
     `python -m src.cli` invokes — through scan -> run -> preview -> execute
     -> undo -> report -> status, in that order, so this is a genuine
     end-to-end exercise of the production workflow, not a reimplementation
     of pipeline logic.
  5. Restores every monkeypatched module attribute in `finally`, regardless
     of outcome. The real `src/config/sources.yaml` is never opened for
     writing at any point (only isolated modules' in-memory path constants
     are reassigned) — verified by this script's own git-diff check at the
     end of `main()`.

Usage: python3 "Tests/Final Beta E2E Validation/run_e2e_validation.py"
"""

import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

_HARNESS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _HARNESS_DIR.parents[1]  # .../Tests/Final Beta E2E Validation -> Tests -> project root

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import src.storage.database as database_module  # noqa: E402
import src.storage.runtime_io as runtime_io_module  # noqa: E402
import src.main as main_module  # noqa: E402
import src.cli as cli_module  # noqa: E402
import src.pipeline.watch_ingest as watch_ingest_module  # noqa: E402


# --- Isolation (identical pattern to run_harness.py / run_production_validation.py) ---

def _isolate_storage(tmp_path: Path) -> Dict[str, Path]:
    original = {
        "metadata_store_path": database_module._METADATA_STORE_PATH,
        "hash_index_path": database_module._HASH_INDEX_PATH,
        "phash_index_path": database_module._PHASH_INDEX_PATH,
        "name_index_path": database_module._NAME_INDEX_PATH,
        "version_history_path": database_module._VERSION_HISTORY_PATH,
        "user_corrections_path": database_module._USER_CORRECTIONS_PATH,
        "action_log_path": runtime_io_module._ACTION_LOG_PATH,
        # Found during this script's own first run (2026-07-26): unlike
        # run_harness.py/run_production_validation.py, this script actually
        # calls execute()/undo() for real, which stages Runtime/Temp/<batch_id>/
        # plan.json (Module 07/08's crash-reconciliation mechanism,
        # storage/runtime_io.py) — a path this script had NOT been isolating.
        # That left 3 harmless (synthetic-data-only) stray directories in the
        # real Runtime/Temp/ before this fix; see the E2E validation report's
        # "environment notes" section for the cleanup record. Neither
        # run_harness.py nor run_production_validation.py needed this because
        # neither of them calls execute()/undo().
        "runtime_temp_path": runtime_io_module._RUNTIME_TEMP_PATH,
        # Found during this script's own second run (2026-07-26): `report`
        # (Module 08) writes through `runtime_io._RUNTIME_REPORTS_PATH`
        # (src/pipeline/reporting.py reads that same module attribute
        # directly, not its own copy) — a second isolation gap this script
        # had, alongside _RUNTIME_TEMP_PATH above. Missing this overwrote the
        # real Duplicate Report/Storage Report (pre-existing tracked files)
        # with this script's synthetic test data across several runs before
        # being caught; both were regenerated from the real, untouched
        # Database/ afterward — see the E2E validation report's "environment
        # notes" section for the full record.
        "runtime_reports_path": runtime_io_module._RUNTIME_REPORTS_PATH,
    }
    database_module._METADATA_STORE_PATH = tmp_path / "metadata_store.json"
    database_module._HASH_INDEX_PATH = tmp_path / "hash_index.json"
    database_module._PHASH_INDEX_PATH = tmp_path / "phash_index.json"
    database_module._NAME_INDEX_PATH = tmp_path / "name_index.json"
    database_module._VERSION_HISTORY_PATH = tmp_path / "version_history.json"
    database_module._USER_CORRECTIONS_PATH = tmp_path / "user_corrections.json"
    runtime_io_module._ACTION_LOG_PATH = tmp_path / "action_log.jsonl"
    runtime_io_module._RUNTIME_TEMP_PATH = tmp_path / "Temp"
    (tmp_path / "Temp").mkdir(parents=True, exist_ok=True)
    runtime_io_module._RUNTIME_REPORTS_PATH = tmp_path / "Reports"
    return original


def _restore_storage(original: Dict[str, Path]) -> None:
    database_module._METADATA_STORE_PATH = original["metadata_store_path"]
    database_module._HASH_INDEX_PATH = original["hash_index_path"]
    database_module._PHASH_INDEX_PATH = original["phash_index_path"]
    database_module._NAME_INDEX_PATH = original["name_index_path"]
    database_module._VERSION_HISTORY_PATH = original["version_history_path"]
    database_module._USER_CORRECTIONS_PATH = original["user_corrections_path"]
    runtime_io_module._ACTION_LOG_PATH = original["action_log_path"]
    runtime_io_module._RUNTIME_TEMP_PATH = original["runtime_temp_path"]


def _isolate_config(config_path: Path) -> Dict[str, Path]:
    original = {
        "main": main_module._SOURCES_CONFIG_PATH,
        "cli": cli_module._SOURCES_CONFIG_PATH,
        "watch_ingest": watch_ingest_module._SOURCES_CONFIG_PATH,
    }
    main_module._SOURCES_CONFIG_PATH = config_path
    cli_module._SOURCES_CONFIG_PATH = config_path
    watch_ingest_module._SOURCES_CONFIG_PATH = config_path
    return original


def _restore_config(original: Dict[str, Path]) -> None:
    main_module._SOURCES_CONFIG_PATH = original["main"]
    cli_module._SOURCES_CONFIG_PATH = original["cli"]
    watch_ingest_module._SOURCES_CONFIG_PATH = original["watch_ingest"]


# --- Dataset: small, synthetic, throwaway. Never touches the real ~/Downloads. ---

def _build_dataset(source_dir: Path) -> List[str]:
    """Returns the list of filenames created, for the report."""
    created: List[str] = []

    # Deterministic Image (no AI judgment needed — extension + non-screenshot
    # filename routes straight to Category.IMAGE per classification.py).
    try:
        from PIL import Image
        img = Image.new("RGB", (64, 48), color=(120, 160, 200))
        img.save(source_dir / "vacation_photo.jpg", format="JPEG")
    except ImportError:
        (source_dir / "vacation_photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200 + b"\xff\xd9")
    created.append("vacation_photo.jpg")

    # Exact byte-for-byte duplicate under a different name — exercises
    # Module 04's deterministic content-hash duplicate detection.
    shutil.copyfile(source_dir / "vacation_photo.jpg", source_dir / "vacation_photo_copy.jpg")
    created.append("vacation_photo_copy.jpg")

    # Deterministic Video (extension-mapped, no tag-reading library per TD-18
    # — safe to use minimal placeholder bytes).
    (source_dir / "family_clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    created.append("family_clip.mp4")

    # Deterministic Audio (extension-mapped).
    (source_dir / "voice_memo.mp3").write_bytes(b"ID3" + b"\x00" * 64)
    created.append("voice_memo.mp3")

    # Deterministic Application (extension-mapped).
    (source_dir / "SomeApp_Installer.dmg").write_bytes(b"\x00" * 64)
    created.append("SomeApp_Installer.dmg")

    # Deterministic Archive — a genuinely valid empty zip.
    with zipfile.ZipFile(source_dir / "project_backup.zip", "w") as zf:
        zf.writestr("readme.txt", "placeholder archive contents for E2E validation\n")
    created.append("project_backup.zip")

    # Ambiguous free text — no invoice/contract/receipt markers. Under
    # deterministic-only mode (no AI provider configured — today's shipped
    # default) this is EXPECTED to land on Category.UNKNOWN / review_required
    # per the disclosed TD-01 limitation, not a defect. Exercising this path
    # faithfully is part of the point of this validation.
    (source_dir / "random_notes.txt").write_text(
        "Grocery list: eggs, coffee, bread.\nCall Sam back about the weekend.\n",
        encoding="utf-8",
    )
    created.append("random_notes.txt")

    # OS-generated file that Rules/Ignore Rules.md says must never be treated
    # as a real download — confirms ignore-pattern handling survives the full
    # command chain, not just Module 01 in isolation.
    (source_dir / ".DS_Store").write_bytes(b"\x00" * 32)
    created.append(".DS_Store")

    return created


def _read_all_log_entries() -> List[dict]:
    return list(runtime_io_module.read_action_log_entries())


def _snapshot_store() -> Dict[str, dict]:
    # Note: ignored entries (.DS_Store, symlinks, directories, zero-byte,
    # unsupported extensions) never become a FileRecord at all — Module 01's
    # _skip() logs an action-log "skip" entry only (see watch_ingest.py). So
    # this snapshot will never contain .DS_Store; that absence, plus a
    # matching "skip" action-log entry, IS the correct, expected outcome —
    # verified separately via the action log, not via this function.
    records = database_module.load_metadata_store()
    return {
        r.file_id: {
            "original_name": r.original_name,
            "current_path": r.current_path,
            "category": r.category.value if r.category else None,
            "tier": r.tier,
            "confidence_score": r.confidence_score,
            "duplicate_of": r.duplicate_of,
            "exact_duplicate": bool(r.duplicate_signals.exact_duplicate) if r.duplicate_signals else None,
            "suggested_name": r.suggested_name,
            "processed_at": r.processed_at,
        }
        for r in records
    }


def main() -> int:
    run_started_at = datetime.now(timezone.utc).isoformat()
    findings: List[str] = []
    steps: List[dict] = []

    with tempfile.TemporaryDirectory(prefix="e2e_source_") as source_dir_str, \
         tempfile.TemporaryDirectory(prefix="e2e_dest_") as dest_dir_str, \
         tempfile.TemporaryDirectory(prefix="e2e_storage_") as storage_dir_str, \
         tempfile.TemporaryDirectory(prefix="e2e_config_") as config_dir_str:

        source_dir = Path(source_dir_str)
        dest_dir = Path(dest_dir_str)
        storage_dir = Path(storage_dir_str)
        config_path = Path(config_dir_str) / "sources.yaml"

        created_files = _build_dataset(source_dir)

        config_path.write_text(
            "sources:\n"
            # v1 hardcodes "downloads" as the single supported source_id
            # (load_source_config()'s own default, watch_ingest.py) — a
            # disclosed, deliberate v1 boundary (TD-11: single source only),
            # not something this validation script should work around.
            "  - source_id: downloads\n"
            f"    path: {source_dir}\n"
            "    type: local_folder\n"
            "    enabled: true\n"
            "    recursive: false\n"
            "execution_mode: manual\n"
            f"destination_root: {dest_dir}\n"
            "classification_provider: null\n"
            "extraction_provider: null\n"
            "ai_provider_consent: false\n",
            encoding="utf-8",
        )

        original_config = _isolate_config(config_path)
        original_storage = _isolate_storage(storage_dir)
        try:
            print(f"Source (throwaway): {source_dir}")
            print(f"Destination (throwaway): {dest_dir}")
            print(f"Storage (throwaway): {storage_dir}")
            print(f"Files created: {created_files}\n")

            def run_cmd(argv: List[str]) -> int:
                print(f"--- python -m src.cli {' '.join(argv)} ---")
                rc = cli_module.main(argv)
                print(f"(exit code {rc})\n")
                steps.append({"command": argv, "exit_code": rc})
                return rc

            run_cmd(["status"])
            run_cmd(["scan"])
            run_cmd(["run"])

            before_execute = _snapshot_store()
            run_cmd(["preview"])
            run_cmd(["execute", "-y"])
            after_execute = _snapshot_store()

            # --- Verify: auto-tier records actually moved on disk ---
            moved_count = 0
            for fid, rec in after_execute.items():
                before_rec = before_execute.get(fid)
                if before_rec and rec["processed_at"] and rec["current_path"] != before_rec["current_path"]:
                    moved_count += 1
                    if not Path(rec["current_path"]).exists():
                        findings.append(
                            f"DEFECT: {rec['original_name']} reports processed_at set and a new "
                            f"current_path ({rec['current_path']}), but no file exists there."
                        )
                    if Path(before_rec["current_path"]).exists():
                        findings.append(
                            f"DEFECT: {rec['original_name']} was reported moved, but the original "
                            f"file at {before_rec['current_path']} is still present (not a move)."
                        )
            print(f"Files actually moved by execute: {moved_count}")

            batch_ids = {e.get("batch_id") for e in _read_all_log_entries() if e.get("batch_id")}
            last_batch = sorted(b for b in batch_ids if b)[-1] if batch_ids else None
            if last_batch:
                run_cmd(["undo", "--last"])
            else:
                findings.append("No batch_id found in the isolated action log — cannot exercise undo.")

            after_undo = _snapshot_store()
            undone_count = 0
            for fid, rec in after_undo.items():
                moved_rec = after_execute.get(fid)
                before_rec = before_execute.get(fid)
                if moved_rec and before_rec and moved_rec["current_path"] != before_rec["current_path"]:
                    if rec["current_path"] == before_rec["current_path"] and Path(rec["current_path"]).exists():
                        undone_count += 1
                    else:
                        findings.append(
                            f"DEFECT: {rec['original_name']} was moved by execute but undo did not "
                            f"restore it to {before_rec['current_path']} (now: {rec['current_path']})."
                        )
            print(f"Files correctly restored by undo: {undone_count}")

            run_cmd(["report"])
            run_cmd(["status"])

            final_store = _snapshot_store()
            all_log_entries_pre = _read_all_log_entries()

            # --- Verify: .DS_Store was ignored — never became a FileRecord (Module 01's
            #     _skip() never calls build_file_record() for it), and a "skip" action-log
            #     entry with the matching reason was written instead. ---
            ds_store_entries = [r for r in final_store.values() if r["original_name"] == ".DS_Store"]
            if ds_store_entries:
                findings.append(
                    f"DEFECT: .DS_Store became a real FileRecord ({ds_store_entries}) — "
                    f"Ignore Rules.md says it must never be treated as a real download."
                )
            ds_store_skips = [
                e for e in all_log_entries_pre
                if e.get("action") == "skip" and str(e.get("from", "")).endswith(".DS_Store")
            ]
            if not ds_store_skips:
                findings.append(
                    "DEFECT: no 'skip' action-log entry was found for .DS_Store — expected exactly one."
                )

            # --- Verify: duplicate pair was detected ---
            dup_flagged = [
                r for r in final_store.values()
                if r["original_name"] in ("vacation_photo.jpg", "vacation_photo_copy.jpg")
                and r["exact_duplicate"]
            ]
            if len(dup_flagged) == 0:
                findings.append(
                    "DEFECT: neither vacation_photo.jpg nor vacation_photo_copy.jpg (byte-identical) "
                    "was flagged as an exact duplicate."
                )

            # --- Verify: ambiguous text file fell back to Unknown/review_required
            #     (expected under deterministic-only mode, not a defect) ---
            notes = [r for r in final_store.values() if r["original_name"] == "random_notes.txt"]
            notes_outcome = notes[0]["category"] if notes else None
            notes_tier = notes[0]["tier"] if notes else None

            # --- Verify: deterministic categories resolved correctly ---
            category_by_name = {r["original_name"]: r["category"] for r in final_store.values()}
            expected_categories = {
                "vacation_photo.jpg": {"Image", "Screenshot"},  # heuristic split, either is correct/deterministic
                "vacation_photo_copy.jpg": {"Image", "Screenshot"},
                "family_clip.mp4": {"Video"},
                "voice_memo.mp3": {"Audio"},
                "SomeApp_Installer.dmg": {"Application"},
                "project_backup.zip": {"Archive"},
            }
            for name, expected in expected_categories.items():
                actual = category_by_name.get(name)
                if actual not in expected:
                    findings.append(
                        f"DEFECT: {name} classified as {actual!r}, expected one of {sorted(expected)}."
                    )

            log_entries = _read_all_log_entries()
            action_counts: Dict[str, int] = {}
            for e in log_entries:
                action_counts[e.get("action", "?")] = action_counts.get(e.get("action", "?"), 0) + 1

            result = {
                "run_started_at": run_started_at,
                "run_finished_at": datetime.now(timezone.utc).isoformat(),
                "mode": "deterministic-only (ai_provider_consent: false — today's shipped default)",
                "files_created": created_files,
                "steps": steps,
                "files_moved_by_execute": moved_count,
                "files_restored_by_undo": undone_count,
                "random_notes_txt_outcome": {"category": notes_outcome, "tier": notes_tier},
                "final_category_by_name": category_by_name,
                "action_log_action_counts": action_counts,
                "findings": findings,
            }

        finally:
            _restore_storage(original_storage)
            _restore_config(original_config)

    out_dir = _PROJECT_ROOT / "Runtime" / "Validation" / ("e2e_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\nDone. Results written to: {out_dir / 'results.json'}")
    print(f"Findings: {len(findings)}")
    for f in findings:
        print(f"  - {f}")
    if not findings:
        print("  (none — full chain behaved as expected end-to-end)")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
