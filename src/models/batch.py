"""
Shared data shape for one scan run ("batch").

A batch is the unit `batch_id` refers to throughout the schema and the action log —
see Build-out/08 Logging & Reporting/Metadata & Log Schema.md.
"""

from dataclasses import dataclass, field
from typing import List

from src.models.file_record import FileRecord


@dataclass
class Batch:
    batch_id: str
    source_id: str
    started_at: str
    finished_at: str = None
    files: List[FileRecord] = field(default_factory=list)

    # Rollup counts — filled in by step 08, mirrored into the Daily Summary.
    scanned: int = 0
    auto_filed: int = 0
    approval_required: int = 0
    review_required: int = 0
    duplicates_found: int = 0
    versions_archived: int = 0
    errors: int = 0
