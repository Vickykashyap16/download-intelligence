"""
Deterministic module — no Claude judgment involved.

Reads image EXIF data, used by pipeline/classification.py (Screenshot vs. Image
split — "no camera EXIF data present" signal) and, later, pipeline/metadata.py
(capture date/camera data).

Implemented for Module 02 (Classification) — its only current consumer. Uses
Pillow's own EXIF support (Image.getexif() + PIL.ExifTags.TAGS) rather than a
separate `exifread` dependency — Pillow already covers what Module 02 needs, so
`exifread` was dropped from src/requirements.txt as an unnecessary second library
for the same result.
"""

from typing import Optional

from PIL import Image
from PIL.ExifTags import TAGS

_CAMERA_TAGS = {"Make", "Model", "LensModel", "FocalLength"}


def read_exif(path: str) -> dict:
    """Return whatever EXIF tags are present, keyed by human-readable tag name (may
    be an empty dict for screenshots/edited images with no camera metadata)."""
    with Image.open(path) as image:
        raw_exif = image.getexif()
    return {TAGS.get(tag_id, tag_id): value for tag_id, value in raw_exif.items()}


def get_capture_date(path: str) -> Optional[str]:
    """Convenience accessor: the EXIF capture date if present, else None."""
    exif = read_exif(path)
    return exif.get("DateTimeOriginal") or exif.get("DateTime")


def has_camera_metadata(path: str) -> bool:
    """True if EXIF contains a lens/camera model tag — one of the Screenshot vs. Image
    signals in Rules/Classification Rules.md."""
    exif = read_exif(path)
    return any(tag in exif for tag in _CAMERA_TAGS)
