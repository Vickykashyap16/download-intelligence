"""
Shared data shapes owned by Module 02 (Classification).

Split out from file_record.py (rather than defined inline there) for the same reason
batch.py is separate: file_record.py should describe the FileRecord shape itself, not
carry every module's own type definitions. Imported into file_record.py for the
`category`/`classification_signals` fields.

See Build-out/02 Classification/Module 02 Design.md §14 for the full rationale,
including why these are strongly-typed while confidence_breakdown/extracted_metadata
stay plain dicts (fixed, small, fully-known-in-advance shape here; open-ended or
category-varying shape there).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Category(str, Enum):
    """The fixed v1 category taxonomy — see Rules/Classification Rules.md, which
    remains the source of truth for what this list *is*. This enum is a typed mirror
    of that list for code; if the rules doc's category list changes, this enum is
    updated by hand to match.

    Deliberately `str, Enum` (not a plain Enum, and not enum.StrEnum — that's Python
    3.11+ only, and this project targets 3.10): members ARE string instances, so
    json.dumps() serializes them as their plain string value automatically, with no
    custom encoder needed.
    """

    INVOICE = "Invoice"
    RESUME = "Resume"
    BANK_STATEMENT = "Bank Statement"
    CONTRACT = "Contract"
    DOCUMENT = "Document"
    IMAGE = "Image"
    SCREENSHOT = "Screenshot"
    APPLICATION = "Application"
    ARCHIVE = "Archive"
    VIDEO = "Video"
    AUDIO = "Audio"
    UNKNOWN = "Unknown"


@dataclass
class ClassificationSignals:
    """Module 02's raw, honest signals about how confident its classification is —
    the material Module 06 turns into confidence_score/confidence_breakdown/tier later.
    Module 02 never computes a score itself (Rules/Confidence Rules.md is Module 06's
    single source of truth for that math) — it only reports what it observed.

    Every field defaults to the "nothing unusual" value, so a freshly-constructed
    ClassificationSignals() is always a valid, complete "no signals apply" record —
    Module 02 never has a reason to leave this partially filled in.
    """

    ambiguous: bool = False
    multi_document_detected: bool = False
    no_extractable_text: bool = False
    non_english_detected: bool = False
    detected_language: Optional[str] = None
    locked: bool = False
