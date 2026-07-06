"""
Deterministic module — no Claude judgment involved.

Reads/writes Database/ (Metadata/, FileIndex/, History/, Learning/). Plain JSON in v1 —
see Database/README.md for the planned SQLite migration path if this gets slow.

Module 01 (Watch & Ingest) scope: `load_metadata_store()` and `save_file_record()` are
implemented, since every module needs basic Metadata read/write. FileIndex/History/
Learning functions remain unimplemented — they belong to Module 04 (Duplicate & Version
Detection) and Module 07 (Preview, Approval & Execution) respectively, and Module 01
does not touch them.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from src.models.classification import Category, ClassificationSignals
from src.models.file_record import FileRecord

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_METADATA_STORE_PATH = _PROJECT_ROOT / "Database" / "Metadata" / "metadata_store.json"


def metadata_store_path() -> Path:
    """Public accessor for where metadata_store.json lives — for callers (e.g. the
    CLI) that want to tell the user where their generated metadata ended up without
    reaching into the module's underlying path constant directly."""
    return _METADATA_STORE_PATH


def _ensure_metadata_store_exists() -> None:
    """Create an empty metadata_store.json the first time it's needed."""
    _METADATA_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _METADATA_STORE_PATH.exists():
        _METADATA_STORE_PATH.write_text("[]", encoding="utf-8")


def _reconstruct_typed_fields(raw_record: dict) -> dict:
    """Turn the plain JSON forms of Module 02's typed fields back into real objects.

    `asdict()` (used by `_write_metadata_store()`) already flattens a nested
    `ClassificationSignals` dataclass into a plain dict on write, and a `Category`
    enum member serializes to its plain string value automatically (it's a `str`
    subclass) — neither needs special handling to WRITE. But `json.loads()` on the
    way back in only ever produces plain dicts/strings, never dataclass instances or
    enum members, so this step is required on every load — see
    Build-out/02 Classification/Module 02 Design.md §13 for why.
    """
    if raw_record.get("category") is not None:
        raw_record["category"] = Category(raw_record["category"])
    if raw_record.get("classification_signals") is not None:
        raw_record["classification_signals"] = ClassificationSignals(
            **raw_record["classification_signals"]
        )
    return raw_record


def load_metadata_store() -> List[FileRecord]:
    """Load all FileRecords from Database/Metadata/metadata_store.json."""
    _ensure_metadata_store_exists()
    raw_records = json.loads(_METADATA_STORE_PATH.read_text(encoding="utf-8"))
    return [FileRecord(**_reconstruct_typed_fields(raw_record)) for raw_record in raw_records]


def _write_metadata_store(records: List[FileRecord]) -> None:
    """Overwrite metadata_store.json with `records`. v1 rewrites the whole file each
    time (see Database/README.md) — fine at this volume, not worth optimizing yet."""
    _METADATA_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(record) for record in records]
    _METADATA_STORE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_file_record(record: FileRecord) -> None:
    """Insert or update (by file_id) a single FileRecord in the metadata store.

    metadata_store.json is the complete, cumulative record of every file this
    automation has ever discovered — not a per-scan/per-batch snapshot. Every call
    loads the full existing store, upserts this one record, and writes the full
    store back; records from earlier batches are never dropped.
    """
    records = load_metadata_store()
    for index, existing_record in enumerate(records):
        if existing_record.file_id == record.file_id:
            records[index] = record
            break
    else:
        records.append(record)
    _write_metadata_store(records)


def find_by_current_path(current_path: str) -> Optional[FileRecord]:
    """Return the existing FileRecord whose current_path matches, if any.

    Used by Module 01 to recognize "I've already discovered this file and it hasn't
    moved yet" across repeated scans, so re-scanning doesn't mint a new file_id (and
    therefore a duplicate Database entry) for a file that's simply still sitting
    where it was last seen. This is a re-identification convenience for Module 01
    only — it is NOT duplicate detection (Module 04's job is comparing content_hash
    across DIFFERENT current_paths to find copies; this function only ever matches
    the exact same path).

    v1 implementation is a linear scan of the full store — fine at v1 volume (see
    Database/README.md); revisit if this ever shows up as a bottleneck.
    """
    for record in load_metadata_store():
        if record.current_path == current_path:
            return record
    return None


# --- Database/FileIndex/ — Module 04 (Duplicate & Version Detection) territory ---

def lookup_hash(sha256: str) -> Optional[str]:
    """Return the file_id already filed under this exact hash, if any."""
    raise NotImplementedError("Module 04 (Duplicate & Version Detection) territory")


def lookup_phash_matches(phash: str, max_distance: int) -> List[str]:
    """Return file_ids of images within max_distance of this perceptual hash."""
    raise NotImplementedError("Module 04 (Duplicate & Version Detection) territory")


def lookup_name_matches(normalized_name: str) -> List[str]:
    """Return file_ids of previously filed files with a similar normalized name."""
    raise NotImplementedError("Module 04 (Duplicate & Version Detection) territory")


def update_indexes(record: FileRecord) -> None:
    """Add a newly filed record's hash/phash/name into Database/FileIndex/."""
    raise NotImplementedError("Module 04 (Duplicate & Version Detection) territory")


# --- Database/History/ — Module 04 (Duplicate & Version Detection) territory ---

def record_version_history(version_group_id: str, record: FileRecord, rank: str) -> None:
    """Append this file's rank (latest/superseded) to its version group's lineage."""
    raise NotImplementedError("Module 04 (Duplicate & Version Detection) territory")


# --- Database/Learning/ — Module 07 (Preview, Approval & Execution) territory ---

def log_user_correction(file_id: str, field_name: str, suggested_value: str,
                         corrected_value: str, category: str) -> None:
    """Append a correction entry to Database/Learning/User Corrections.json."""
    raise NotImplementedError("Module 07 (Preview, Approval & Execution) territory")
