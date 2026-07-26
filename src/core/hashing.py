"""
Deterministic module — no Claude judgment involved.

Hashing utilities. `sha256_file`/`sha256_text` are implemented for Module 01
(Watch & Ingest — content hashing and path-based file_id generation).
`perceptual_hash`/`hamming_distance` are implemented for Module 04
(Duplicate & Version Detection — near-duplicate image comparison, Module 04
Design.md §11). The specific algorithm/parameters chosen here (imagehash's default
`phash`, 8x8 hash size) are an implementation detail, not part of any Module
Contract (§5, §11A) — a future change to either would be a storage/index migration
event for Database/FileIndex/phash_index.json, not a contract change.
"""

import hashlib
from pathlib import Path
from typing import Union

import imagehash
from PIL import Image

_CHUNK_SIZE = 65536   # 64 KB — read in chunks so large files don't need to fit in memory


def sha256_file(path: Union[str, Path]) -> str:
    """Return the SHA-256 hex digest of the file's contents at `path`.

    Raises:
        OSError: if the file can't be opened/read (permission denied, locked, etc.).
            Callers are expected to catch this and record the failure rather than
            let it propagate (see pipeline/watch_ingest.py build_file_record()).
    """
    digest = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    """Return the SHA-256 hex digest of a text value (e.g. an absolute path) — used
    for deterministic IDs that don't depend on being able to read file contents."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def perceptual_hash(path: Union[str, Path]) -> str:
    """Return a perceptual hash (via `imagehash.phash`, default 8x8 hash size) for
    near-duplicate image comparison, as a hex string suitable for JSON storage in
    Database/FileIndex/phash_index.json.

    Raises:
        Exception: if the file can't be opened/decoded as an image (Pillow's
            UnidentifiedImageError, a truncated/corrupted file, etc.). Callers
            (DuplicateDetectionEngine) are expected to catch this and treat the
            near-duplicate check as "couldn't determine" for this file, not let it
            propagate (Module 04 Design.md §21).
    """
    with Image.open(path) as image:
        return str(imagehash.phash(image))


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Distance between two perceptual hashes produced by `perceptual_hash()` — the
    number of differing bits. Smaller means more visually similar (Module 04
    Design.md §11).

    Explicitly cast to a native `int` (BUG-001, found during C2's first real run):
    `ImageHash.__sub__()` computes this via `numpy.count_nonzero()`, whose return
    type has varied across numpy versions — some return a native Python `int`,
    others a numpy integer scalar (`numpy.int64`/`numpy.intp`). Without this cast,
    this function's actual runtime return type silently depended on whichever
    numpy version happened to be installed, even though it was always annotated
    `-> int` — and a numpy scalar stored into `DuplicateSignals.phash_distance`
    (pipeline/duplicate_detector.py) crashes `json.dumps()` in
    `storage/database.py`'s `_write_metadata_store()` with "Object of type int64
    is not JSON serializable" the first time a batch actually needs to persist a
    near-duplicate result. `int(...)` is a value-preserving, not lossy, cast here:
    the underlying value is already a whole number count of differing bits.
    """
    return int(imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b))
