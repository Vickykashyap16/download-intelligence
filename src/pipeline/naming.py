"""
Naming & Destination. DETERMINISTIC module (no Claude judgment) — once category +
extracted metadata are known (from classification.py/metadata.py), filling a template
and looking up a destination is pure string/rules logic.

Architecture: Build-out/05 Naming & Destination/05 Naming & Destination.md
Rules: Rules/Naming Rules.md, Rules/Folder Rules.md (implemented directly — no generated
config in v1, see CHANGELOG.md)

Scaffold only: signatures defined, no logic yet.
"""

from typing import Optional


def build_filename(category: str, fields: dict, original_extension: str) -> str:
    """Fill Rules/Naming Rules.md's template for this category from `fields`.
    Missing fields use the documented fallback values. Sanitizes per general naming
    rules (Title_Case_With_Underscores, max_length, etc.)."""
    raise NotImplementedError


def resolve_destination(category: str, tier: str) -> Optional[str]:
    """Look up Rules/Folder Rules.md's category -> destination mapping, applying
    overrides: review_required -> None (not moved), exact_duplicate/superseded_version
    -> their ~ARCHIVE~/ paths."""
    raise NotImplementedError


def resolve_collision(destination: str, filename: str) -> str:
    """If `filename` already exists in `destination`, append _2, _3, ... per
    Rules/Naming Rules.md. Never overwrite."""
    raise NotImplementedError
