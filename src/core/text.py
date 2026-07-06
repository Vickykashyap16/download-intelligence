"""
Deterministic module — no Claude judgment involved.

Text extraction for non-PDF text-bearing files (.docx, .txt), used by
pipeline/classification.py (deep pass) and, later, pipeline/metadata.py. PDFs are
handled separately in core/pdf.py, which has its own library and scanned-page
fallback case.

Implemented for Module 02 (Classification) — its only current consumer.

Note: `.rtf` isn't in Module 01's SUPPORTED_EXTENSIONS
(src/pipeline/watch_ingest.py) as of this writing, so a FileRecord with extension
".rtf" never actually reaches this module in practice today. extract_text() still
handles it (as a best-effort plain-text read) rather than raising, in case Module 01's
supported list is ever extended — cheap to support, nothing depends on it yet.
"""

from pathlib import Path
from typing import Optional

import docx
from langdetect import LangDetectException, detect


def extract_text(path: str) -> Optional[str]:
    """Return extracted text from a .docx/.txt/.rtf file, or None if the file can't
    be read as text at all (or is empty once extracted)."""
    extension = Path(path).suffix.lower()

    if extension == ".docx":
        document = docx.Document(path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    elif extension in (".txt", ".rtf"):
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    else:
        return None

    text = text.strip()
    return text if text else None


def detect_language(text: str) -> Optional[str]:
    """Best-effort language detection — feeds the non_english_detected classification
    signal (Rules/Confidence Rules.md's non_english_content deduction). Returns None
    (rather than raising) when the text is too short/ambiguous for langdetect to call —
    a genuine "don't know," not a failure the caller needs to handle specially."""
    try:
        return detect(text)
    except LangDetectException:
        return None
