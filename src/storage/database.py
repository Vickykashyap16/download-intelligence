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
import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from rapidfuzz import fuzz

from src.core.hashing import hamming_distance, perceptual_hash
from src.models.classification import Category, ClassificationSignals
from src.models.duplicate import DuplicateSignals
from src.models.file_record import FileRecord
from src.models.naming import NamingSignals

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_METADATA_STORE_PATH = _PROJECT_ROOT / "Database" / "Metadata" / "metadata_store.json"
_HASH_INDEX_PATH = _PROJECT_ROOT / "Database" / "FileIndex" / "hash_index.json"
_PHASH_INDEX_PATH = _PROJECT_ROOT / "Database" / "FileIndex" / "phash_index.json"
_NAME_INDEX_PATH = _PROJECT_ROOT / "Database" / "FileIndex" / "name_index.json"
_VERSION_HISTORY_PATH = _PROJECT_ROOT / "Database" / "History" / "version_history.json"

# Module 04 Design.md §10/§15: a configurable implementation parameter, not an
# architectural constant — lives here (not Rules/) until a future governance
# cleanup relocates it alongside Module 03's still-pending Rules/Metadata Rules.md
# recommendation. Lives in storage/database.py rather than pipeline/duplicate_detector.py
# because `lookup_name_matches()`'s frozen signature (normalized_name, category only —
# no threshold parameter) requires the threshold to be applied internally here, not
# passed in by the caller the way `lookup_phash_matches()`'s max_distance is.
_NAME_SIMILARITY_THRESHOLD = 90


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
    """Turn the plain JSON forms of every module's typed FileRecord fields back into
    real objects: `category`/`classification_signals` (Module 02), `duplicate_signals`
    (Module 04), `naming_signals` (Module 05).

    `asdict()` (used by `_write_metadata_store()`) already flattens a nested
    dataclass into a plain dict on write, and a `Category` enum member serializes to
    its plain string value automatically (it's a `str` subclass) — none of these need
    special handling to WRITE. But `json.loads()` on the way back in only ever
    produces plain dicts/strings, never dataclass instances or enum members, so this
    step is required on every load for every typed field — see
    Build-out/02 Classification/Module 02 Design.md §13 for why.
    """
    if raw_record.get("category") is not None:
        raw_record["category"] = Category(raw_record["category"])
    if raw_record.get("classification_signals") is not None:
        raw_record["classification_signals"] = ClassificationSignals(
            **raw_record["classification_signals"]
        )
    if raw_record.get("duplicate_signals") is not None:
        raw_record["duplicate_signals"] = DuplicateSignals(**raw_record["duplicate_signals"])
    if raw_record.get("naming_signals") is not None:
        raw_record["naming_signals"] = NamingSignals(**raw_record["naming_signals"])
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


# --- Database/FileIndex/ — Module 04 (Duplicate & Version Detection) territory.
# Implemented per Build-out/04 Duplicate & Version Detection/Module 04 Design.md §16. ---

def _load_index(path: Path, default):
    """Load a Database/FileIndex/*.json (or History/*.json) file, or return `default`
    if it doesn't exist yet (Database/README.md — these start as empty placeholders
    until the first real run)."""
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_index(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def lookup_hash(sha256: str) -> Optional[str]:
    """Return the file_id already filed under this exact hash, if any (§16 —
    hash_index.json is a plain `{sha256: file_id}` dict, an O(1) lookup, since
    content_hash equality is certain/cryptographic, §8)."""
    index: Dict[str, str] = _load_index(_HASH_INDEX_PATH, {})
    return index.get(sha256)


def lookup_phash_matches(phash: str, max_distance: int, category: Category) -> List[str]:
    """Return file_ids of previously filed, same-category images within max_distance of
    this perceptual hash (§16, post-freeze correction #4). `phash_index.json` can't be a
    single dict access, since "within distance N" isn't a dict-key operation; scans
    every stored entry and computes Hamming distance, same discipline as §20's disclosed
    linear-scan cost. Mirrors `lookup_name_matches()`'s exact treatment: category isn't
    stored in `phash_index.json` itself, so each within-distance candidate's `category`
    is cross-referenced against the metadata store, and only same-category candidates
    are returned — never filtered post-hoc by the caller. This closes the gap Module 04
    UAT's Finding UAT-1 identified (near-duplicate detection was not category-scoped,
    contradicting §9/F5's confirmed requirement that Image and Screenshot never group,
    for near-duplicate detection exactly as much as for version-chain detection)."""
    index: Dict[str, List[str]] = _load_index(_PHASH_INDEX_PATH, {})
    if not index:
        return []

    category_by_file_id = {
        record.file_id: record.category for record in load_metadata_store()
    }

    matches: List[str] = []
    for stored_phash, file_ids in index.items():
        if hamming_distance(phash, stored_phash) > max_distance:
            continue
        for file_id in file_ids:
            if category_by_file_id.get(file_id) == category:
                matches.append(file_id)
    return matches


def lookup_name_matches(normalized_name: str, category: Category) -> List[str]:
    """Return file_ids of previously filed, same-category files with a similar
    normalized name (§16, F2, M2). `name_index.json` is a candidate-retrieval index,
    not the fuzzy matcher itself — an exact-key lookup alone would only ever find
    byte-identical normalized names. This scans every stored key, scores it against
    `normalized_name` via `rapidfuzz.fuzz.ratio()` (§10), and only for keys clearing
    `_NAME_SIMILARITY_THRESHOLD` does it check each candidate file_id's actual stored
    `category` (cross-referenced against the metadata store, since the index itself
    doesn't store category) before including it — matching only same-category
    candidates, never filtered post-hoc by the caller."""
    index: Dict[str, List[str]] = _load_index(_NAME_INDEX_PATH, {})
    if not index:
        return []

    category_by_file_id = {
        record.file_id: record.category for record in load_metadata_store()
    }

    matches: List[str] = []
    for stored_name, file_ids in index.items():
        if fuzz.ratio(normalized_name, stored_name) < _NAME_SIMILARITY_THRESHOLD:
            continue
        for file_id in file_ids:
            if category_by_file_id.get(file_id) == category:
                matches.append(file_id)
    return matches


def update_indexes(record: FileRecord) -> None:
    """Add a newly filed record's hash/phash/name into Database/FileIndex/ (§16),
    called unconditionally at the end of processing a record (§7 step 4) regardless
    of whether any match was found, so future records can be compared against it.

    Perceptual hash and normalized name aren't stored anywhere on `FileRecord`
    (§17 — `duplicate_signals` carries only a distance/boolean, never the raw
    value), so this recomputes them from the file itself for image-family
    categories. A small, disclosed recompute cost (§20) — not a correctness
    concern, since both are pure functions of the file's own current content/name.
    """
    if record.content_hash is not None:
        hash_index: Dict[str, str] = _load_index(_HASH_INDEX_PATH, {})
        hash_index.setdefault(record.content_hash, record.file_id)
        _write_index(_HASH_INDEX_PATH, hash_index)

    if record.category in (Category.IMAGE, Category.SCREENSHOT) and record.current_path:
        try:
            phash = perceptual_hash(record.current_path)
        except Exception:
            phash = None
        if phash is not None:
            phash_index: Dict[str, List[str]] = _load_index(_PHASH_INDEX_PATH, {})
            phash_index.setdefault(phash, [])
            if record.file_id not in phash_index[phash]:
                phash_index[phash].append(record.file_id)
            _write_index(_PHASH_INDEX_PATH, phash_index)

    if record.original_name:
        normalized = _normalize_for_index(record.original_name)
        name_index: Dict[str, List[str]] = _load_index(_NAME_INDEX_PATH, {})
        name_index.setdefault(normalized, [])
        if record.file_id not in name_index[normalized]:
            name_index[normalized].append(record.file_id)
        _write_index(_NAME_INDEX_PATH, name_index)


_VERSION_TOKEN_SUFFIX = re.compile(r"[_\-\s]*\(?v\.?(\d+)\)?$|[_\-\s]*final$", re.IGNORECASE)
_SEPARATOR_RUN = re.compile(r"[_\-\s]+")


def _normalize_for_index(name: str) -> str:
    """Strip extension, a trailing explicit version token, and separators, for
    name_index.json keying and similarity comparison. A small, deliberately
    independent copy of `pipeline/duplicate_detector.py`'s `normalize_filename()` of
    the same behavior — storage/database.py cannot import from
    pipeline/duplicate_detector.py without inverting this project's established
    storage->pipeline dependency direction (duplicate_detector.py itself imports
    this module's lookup/update functions), so this follows Module 03 Design.md
    §21's precedent: independent, convention-following duplication across a module
    boundary, not code-sharing. Kept intentionally tiny so drift risk is low."""
    stem = Path(name).stem
    stem = _VERSION_TOKEN_SUFFIX.sub("", stem)
    stem = _SEPARATOR_RUN.sub(" ", stem).strip().lower()
    return stem


# --- Database/History/ — Module 04 (Duplicate & Version Detection) territory ---

def record_version_history(version_group_id: str, record: FileRecord, rank: str) -> None:
    """Append this file's rank (latest/superseded) to its version group's lineage
    (§16 — one entry per version_group_id, `files` list appended/updated per file_id
    every time a version-chain relationship is created or a rank changes)."""
    history: Dict[str, dict] = _load_index(_VERSION_HISTORY_PATH, {})
    group = history.setdefault(
        version_group_id, {"version_group_id": version_group_id, "files": []}
    )
    entry = {
        "file_id": record.file_id,
        "filename": record.original_name,
        "rank_at_time": rank,
        "superseded_at": _now_iso() if rank == "superseded" else None,
    }
    for index, existing in enumerate(group["files"]):
        if existing["file_id"] == record.file_id:
            group["files"][index] = entry
            break
    else:
        group["files"].append(entry)
    _write_index(_VERSION_HISTORY_PATH, history)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# --- Database/Learning/ — Module 07 (Preview, Approval & Execution) territory ---

def log_user_correction(file_id: str, field_name: str, suggested_value: str,
                         corrected_value: str, category: str) -> None:
    """Append a correction entry to Database/Learning/User Corrections.json."""
    raise NotImplementedError("Module 07 (Preview, Approval & Execution) territory")
