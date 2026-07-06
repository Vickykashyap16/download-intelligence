"""
Unit tests for core/archive.py — Module 03's Archive content listing.

Run with: pytest src/core/test_archive.py -v
"""

import zipfile
from pathlib import Path

import pytest

from src.core.archive import list_top_level_entries, summarize_contents

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_list_top_level_entries_flat_files(tmp_path):
    archive_path = tmp_path / "flat.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("readme.txt", "hello")
        archive.writestr("photo.jpg", "fake bytes")

    assert list_top_level_entries(str(archive_path)) == ["readme.txt", "photo.jpg"]


def test_list_top_level_entries_deduplicates_nested_directory(tmp_path):
    archive_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("invoices/jan.pdf", "x")
        archive.writestr("invoices/feb.pdf", "x")
        archive.writestr("readme.txt", "x")

    entries = list_top_level_entries(str(archive_path))
    assert entries == ["invoices/", "readme.txt"]  # "invoices/" listed once, not twice


def test_list_top_level_entries_never_reads_entry_contents(tmp_path):
    """Only names are ever read — this test would still pass even if an entry's
    contents were corrupted/unreadable, proving no extraction is attempted (design
    §18's "no code-execution risk" / "no path-traversal attack surface" claim)."""
    archive_path = tmp_path / "corrupt_inside.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("valid_name_corrupt_content.bin", b"\x00\x01\x02not-real-data")

    assert list_top_level_entries(str(archive_path)) == ["valid_name_corrupt_content.bin"]


def test_list_top_level_entries_raises_for_corrupted_archive(tmp_path):
    not_a_zip = tmp_path / "fake.zip"
    not_a_zip.write_bytes(b"this is not a real zip file at all")

    with pytest.raises(Exception):
        list_top_level_entries(str(not_a_zip))


def test_summarize_contents_joins_entries(tmp_path):
    archive_path = tmp_path / "summary.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("a.txt", "x")
        archive.writestr("b.txt", "x")

    assert summarize_contents(str(archive_path)) == "a.txt, b.txt"


def test_summarize_contents_empty_archive_is_empty_string(tmp_path):
    archive_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive_path, "w"):
        pass  # zero entries — still a valid, openable archive

    assert summarize_contents(str(archive_path)) == ""


def test_list_top_level_entries_real_fixture():
    real_archive = _PROJECT_ROOT / "Tests" / "Small Batch" / "archive.zip"
    entries = list_top_level_entries(str(real_archive))
    assert isinstance(entries, list)
    assert len(entries) >= 1
