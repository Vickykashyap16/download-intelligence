"""
Deterministic module — no Claude judgment involved.

Archive top-level content listing for Module 03 (Metadata Extraction)'s Archive
category. Lists top-level entry *names* only — never extracts, decompresses, or
opens any entry's contents, per Build-out/03 Metadata Extraction/Module 03 Design.md
§18: full archive extraction (and the path-traversal/zip-bomb risk that comes with
it) is explicitly out of scope for v1's "best-effort contents summary."

Distinct from core/hashing.py (fingerprinting) and core/images.py/core/exif.py
(image-specific) — this module is about a .zip's own internal structure.

Implemented for Module 03 — its only current consumer. Module 02's Archive handling
(classification.py) is extension-only and never opens the file at all; this is the
pipeline's first actual look inside an archive's structure.
"""

import zipfile
from typing import List


def list_top_level_entries(path: str) -> List[str]:
    """Return top-level entry names inside a .zip archive, in the archive's own
    order, deduplicated. A top-level directory (e.g. "invoices/photo.jpg") is
    represented once as "invoices/", not once per nested file. Raises if the archive
    can't be opened at all (corrupted, or not really a zip despite its extension) —
    the caller's per-record error handling (Module 03 Design.md §12) is expected to
    catch this and leave `contents_summary` null, not crash the batch.
    """
    top_level: List[str] = []
    seen = set()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if "/" in name:
                top_name = name.split("/", 1)[0] + "/"
            else:
                top_name = name
            if top_name not in seen:
                seen.add(top_name)
                top_level.append(top_name)
    return top_level


def summarize_contents(path: str) -> str:
    """Human-readable, comma-joined summary of top-level entries — Archive's
    `contents_summary` field (Module 03 Design.md §7). Returns "" for a genuinely
    empty archive (zero entries) rather than raising — an empty zip is a valid,
    openable archive, just one with nothing to summarize; the caller treats "" the
    same as any other falsy/uninformative value when deciding whether the field
    counts as "found" (Module 03 Design.md §7's "never fabricate" rule — an empty
    string here is an honest description of an empty archive, not a guess)."""
    entries = list_top_level_entries(path)
    return ", ".join(entries)
