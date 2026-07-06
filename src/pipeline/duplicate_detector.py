"""
Duplicate & Version Detection. DETERMINISTIC module (no Claude judgment).

Architecture: Build-out/04 Duplicate & Version Detection/04 Duplicate & Version Detection.md

Uses core/hashing.py + storage/database.py's FileIndex lookups. Entirely computable —
the only judgment call (is this "really" a new version or an unrelated file with the
same name) is handled by the deterministic tie-break rules below, with disagreements
just lowering confidence (Rules/Confidence Rules.md) rather than needing Claude to decide.
Scaffold only: signatures defined, no logic yet.
"""

from typing import Optional


def find_exact_duplicate(sha256: str) -> Optional[str]:
    """Return the file_id of an exact duplicate already filed, if any."""
    raise NotImplementedError


def find_near_duplicate_images(phash: str) -> list:
    """Return file_ids of near-duplicate images (perceptual hash within threshold)."""
    raise NotImplementedError


def find_version_chain(filename: str) -> list:
    """Return file_ids of previously filed files with a similar normalized name —
    candidates for the same version_group_id."""
    raise NotImplementedError


def determine_latest(candidates: list) -> dict:
    """Given a version chain, decide rank (latest/superseded) per
    Rules/Folder Rules.md's version-detection priority: explicit version number in
    filename -> modified date -> created date. Returns {file_id: rank}. If version
    number and file dates disagree, this is flagged (not silently resolved) for the
    confidence deduction in Rules/Confidence Rules.md."""
    raise NotImplementedError
