"""
Deterministic module — no Claude judgment involved.

PDF-specific text extraction and page rendering, used by pipeline/classification.py
(deep pass) and, later, pipeline/metadata.py. Split out from generic text handling
(core/text.py) because PDFs need their own library (`pdfplumber`) and have the
scanned-image fallback case that plain text files don't.

Implemented for Module 02 (Classification) — its only current consumer.

Error-handling convention (see Build-out/02 Classification/Module 02 Design.md §11):
these functions raise on a genuinely unopenable/malformed PDF rather than silently
returning None — None is reserved for the well-defined "opened fine, no extractable
text" case (e.g. a scanned PDF), which the caller is expected to treat differently
(fall back to render_page_as_image()) from an outright failure (which the caller's own
per-file error handling is expected to catch, log, and continue past).
"""

import io
from typing import Optional

import pdfplumber
from pypdf import PdfReader


def extract_text(path: str, max_pages: int = 2) -> Optional[str]:
    """Return extracted text from a PDF (first `max_pages` pages via `pdfplumber`), or
    None if no text could be extracted (a scanned/image-only PDF — caller should fall
    back to render_page_as_image() for Claude vision instead)."""
    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[:max_pages]
        text_parts = [page.extract_text() or "" for page in pages]
    combined = "\n".join(text_parts).strip()
    return combined if combined else None


def render_page_as_image(path: str, page_number: int = 0) -> bytes:
    """Render a PDF page with no extractable text as a PNG image, for Claude vision
    classification. Used when extract_text() returns None."""
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[page_number]
        page_image = page.to_image(resolution=150)
        buffer = io.BytesIO()
        page_image.original.save(buffer, format="PNG")
        return buffer.getvalue()


def is_password_protected(path: str) -> bool:
    """True if the PDF can't be opened without a password — feeds the `locked`
    classification signal (Rules/Confidence Rules.md's locked/password-protected
    deduction). Checked via pypdf's own encryption flag, which doesn't require
    attempting a full parse — cheap and doesn't risk raising on the encrypted case."""
    reader = PdfReader(path)
    return reader.is_encrypted
