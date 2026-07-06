"""
Unit tests for core/pdf.py. Uses real PDF files from Samples/ (created for Module 01's
validation, reused here) plus small synthetic files created on the fly for the
password-protected and malformed cases.

Run with: pytest src/core/test_pdf.py -v
"""

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from src.core.pdf import extract_text, is_password_protected, render_page_as_image

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_INVOICE = _PROJECT_ROOT / "Samples" / "Invoices" / "sample_invoice_amazon.pdf"


def test_extract_text_reads_real_invoice_text():
    text = extract_text(str(_SAMPLE_INVOICE))
    assert text is not None
    assert "AMAZON" in text.upper()
    assert "Invoice" in text


def test_extract_text_returns_none_for_a_blank_page(tmp_path):
    blank_pdf = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(blank_pdf), pagesize=letter)
    c.save()  # a page with nothing drawn on it — no extractable text

    assert extract_text(str(blank_pdf)) is None


def test_render_page_as_image_returns_a_valid_png(tmp_path):
    image_bytes = render_page_as_image(str(_SAMPLE_INVOICE))
    assert image_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic number
    assert len(image_bytes) > 100


def test_is_password_protected_false_for_normal_pdf():
    assert is_password_protected(str(_SAMPLE_INVOICE)) is False


def test_is_password_protected_true_for_encrypted_pdf(tmp_path):
    source_pdf = tmp_path / "plain.pdf"
    c = canvas.Canvas(str(source_pdf), pagesize=letter)
    c.drawString(72, 750, "Confidential contents")
    c.save()

    encrypted_pdf = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.append(str(source_pdf))
    writer.encrypt("secret-password")
    with open(encrypted_pdf, "wb") as f:
        writer.write(f)

    assert is_password_protected(str(encrypted_pdf)) is True


def test_extract_text_raises_on_genuinely_malformed_pdf(tmp_path):
    """Module 02's error handling (Engine-level) is responsible for catching this —
    core/pdf.py itself is expected to raise on a file that isn't really a PDF, not
    silently return None (which is reserved for "opened fine, no text" — see the
    module docstring)."""
    garbage = tmp_path / "not_really_a_pdf.pdf"
    garbage.write_bytes(b"%PDF-1.4 GARBAGE NOT A REAL PDF STRUCTURE \x00\x01\x02\xff\xfe")

    with pytest.raises(Exception):
        extract_text(str(garbage))
