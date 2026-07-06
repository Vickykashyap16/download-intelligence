"""
Deterministic module — no Claude judgment involved.

Hashing utilities. `sha256_file`/`sha256_text` are implemented for Module 01
(Watch & Ingest — content hashing and path-based file_id generation).
`perceptual_hash`/`hamming_distance` remain unimplemented: they belong to Module 04
(Duplicate & Version Detection).
"""

import hashlib
from pathlib import Path
from typing import Union

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
    """Return a perceptual hash (via `imagehash`) for near-duplicate image comparison.
    Not implemented — Module 04 (Duplicate & Version Detection) territory."""
    raise NotImplementedError("Module 04 (Duplicate & Version Detection) territory")


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Distance between two perceptual hashes.
    Not implemented — Module 04 (Duplicate & Version Detection) territory."""
    raise NotImplementedError("Module 04 (Duplicate & Version Detection) territory")
