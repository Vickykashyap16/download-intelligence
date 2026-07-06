"""
Deterministic module — no Claude judgment involved.

Image inspection helpers (dimensions, format) used by pipeline/classification.py for
the Screenshot-vs-Image split (Rules/Classification Rules.md: "image dimensions match a
common device/screen resolution"). Distinct from core/hashing.py (hash algorithms) and
core/exif.py (camera metadata) — this module is about the image itself, not its
fingerprint or metadata.

Implemented for Module 02 (Classification) — its only current consumer.
"""

from typing import Tuple

from PIL import Image

# Common device/screen resolutions (width, height) — both orientations included since a
# screenshot could be captured in either. This specific list is an implementation-level
# addition made while building Module 02: Rules/Classification Rules.md names the
# *signal* ("dimensions match a common device/screen resolution") but doesn't enumerate
# resolutions itself. Kept here rather than promoted into Rules/Classification Rules.md
# for now — flag to the project owner if this should move there for auditability.
_COMMON_SCREEN_RESOLUTIONS = {
    (1920, 1080), (1080, 1920),   # 1080p desktop/mobile
    (2560, 1440), (1440, 2560),   # 1440p desktop
    (3840, 2160), (2160, 3840),   # 4K desktop
    (1366, 768), (768, 1366),     # common laptop
    (1440, 900), (900, 1440),     # common laptop
    (2880, 1800), (1800, 2880),   # Retina laptop
    (1170, 2532), (2532, 1170),   # iPhone (e.g. 13/14)
    (1284, 2778), (2778, 1284),   # iPhone Plus/Max
    (2048, 2732), (2732, 2048),   # iPad Pro
}


def get_dimensions(path: str) -> Tuple[int, int]:
    """Return (width, height) in pixels."""
    with Image.open(path) as image:
        return image.size


def matches_screen_resolution(dimensions: Tuple[int, int]) -> bool:
    """True if `dimensions` matches a common device/screen resolution — one of the
    Screenshot-vs-Image signals in Rules/Classification Rules.md."""
    return tuple(dimensions) in _COMMON_SCREEN_RESOLUTIONS


def get_format(path: str) -> str:
    """Return the actual image format (png/jpeg/etc.) by inspecting file contents via
    Pillow, not just trusting the extension."""
    with Image.open(path) as image:
        return (image.format or "").lower()
