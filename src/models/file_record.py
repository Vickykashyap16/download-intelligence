"""
Shared data shape for a single file's metadata record.

Mirrors the schema in Build-out/08 Logging & Reporting/Metadata & Log Schema.md,
which is kept in sync with this file by hand (this file wins if they ever drift —
see CHANGELOG.md for the file_id redesign that prompted this note).

Fields are grouped by which module owns/populates them, so it's obvious at a glance
what Module 01 does and doesn't touch.
"""

from dataclasses import dataclass, field
from typing import Optional

from src.models.classification import Category, ClassificationSignals
from src.models.duplicate import DuplicateSignals


@dataclass
class FileRecord:
    # --- Identity (Module 01 assigns once; never recomputed from location — see
    # generate_new_file_id() / find_by_current_path() in pipeline/watch_ingest.py and
    # CHANGELOG.md for why) ---
    file_id: str            # permanent, arbitrary (UUID4) — assigned once at first discovery
    source_id: str
    original_name: str      # fixed at first discovery, never updated
    original_path: str      # fixed at first discovery, never updated
    current_path: str       # live location — Module 01 sets it at discovery, Module 07
                             # updates it after every move/rename. Always read this field
                             # (not original_path) to find where a file actually is right now.

    # --- Basic file info (Module 01 / Watch & Ingest) ---
    extension: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: Optional[str] = None    # ISO timestamp, filesystem creation time
    modified_at: Optional[str] = None   # ISO timestamp, filesystem modification time
    content_hash: Optional[str] = None  # SHA-256 of file content, when readable — used by
                                         # Module 04 to compare records and find duplicates.
                                         # NOT part of file_id (see above).

    # --- Ingest tracking (Module 01) ---
    discovered_at: Optional[str] = None   # ISO timestamp of FIRST discovery — preserved
                                           # across re-scans, not refreshed on every scan
    status: str = "discovered"            # discovered | unreadable
    error: Optional[str] = None           # populated when status == "unreadable"

    # --- Classification (Module 02) ---
    category: Optional[Category] = None   # None = Module 01 never had readable bytes to
                                           # try (status == "unreadable"); Category.UNKNOWN =
                                           # Module 02 tried on a readable file and found no
                                           # match. These are deliberately different — see
                                           # Build-out/02 Classification/Module 02 Design.md §11.
    classification_signals: Optional[ClassificationSignals] = None   # None until Module 02
                                           # processes this record; always a full
                                           # ClassificationSignals instance afterward, never
                                           # partially filled in.

    # --- Metadata Extraction (Module 03) ---
    extracted_metadata: dict = field(default_factory=dict)   # shape varies by category

    # --- Naming & Destination (Module 05) ---
    suggested_name: Optional[str] = None
    suggested_destination: Optional[str] = None

    # --- Duplicate & Version Detection (Module 04) ---
    duplicate_of: Optional[str] = None
    version_group_id: Optional[str] = None
    version_rank: Optional[str] = None   # "latest" | "superseded"
    duplicate_signals: Optional[DuplicateSignals] = None   # None until Module 04
                                           # processes this record; always a full
                                           # DuplicateSignals instance afterward, never
                                           # partially filled in (Module 04 Design.md §17).

    # --- Confidence & Review (Module 06) ---
    confidence_score: Optional[int] = None            # 0-100
    confidence_breakdown: dict = field(default_factory=dict)   # named deduction -> value
    tier: Optional[str] = None   # auto | approval_required | review_required

    # --- Batch / execution tracking ---
    batch_id: Optional[str] = None
    processed_at: Optional[str] = None   # set once the full pipeline finishes filing this record
    approved_by: Optional[str] = None    # "auto" | "user"
    approved_at: Optional[str] = None
    reversible: bool = True
