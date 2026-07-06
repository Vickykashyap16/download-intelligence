"""
Unit tests for core/text.py.

Run with: pytest src/core/test_text.py -v
"""

from pathlib import Path

from src.core.text import detect_language, extract_text

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_RESUME = _PROJECT_ROOT / "Samples" / "Documents" / "sample_resume_jordan_patel.docx"
_SAMPLE_TXT = _PROJECT_ROOT / "Samples" / "Documents" / "sample_generic_document_manual.txt"


def test_extract_text_reads_real_docx():
    text = extract_text(str(_SAMPLE_RESUME))
    assert text is not None
    assert "Jordan Patel" in text or "Resume" in text.lower() or len(text) > 0


def test_extract_text_reads_real_txt():
    text = extract_text(str(_SAMPLE_TXT))
    assert text is not None
    assert len(text) > 0


def test_extract_text_returns_none_for_unsupported_extension(tmp_path):
    unsupported = tmp_path / "notes.xyz"
    unsupported.write_text("some content")
    assert extract_text(str(unsupported)) is None


def test_extract_text_returns_none_for_empty_txt(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    assert extract_text(str(empty)) is None


def test_detect_language_identifies_english():
    result = detect_language(
        "This is a clear, ordinary sentence written in English for testing purposes."
    )
    assert result == "en"


def test_detect_language_identifies_non_english():
    result = detect_language(
        "Ceci est une phrase claire et ordinaire écrite en français à des fins de test."
    )
    assert result == "fr"


def test_detect_language_returns_none_for_unusable_text():
    # Too short/ambiguous for langdetect to produce a confident result.
    result = detect_language("")
    assert result is None
