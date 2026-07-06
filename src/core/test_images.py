"""
Unit tests for core/images.py.

Run with: pytest src/core/test_images.py -v
"""

from pathlib import Path

from PIL import Image

from src.core.images import get_dimensions, get_format, matches_screen_resolution

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PHOTO = _PROJECT_ROOT / "Samples" / "Images" / "sample_product_photo.jpg"
_SAMPLE_SCREENSHOT = _PROJECT_ROOT / "Samples" / "Images" / "sample_screenshot_login_error.png"


def test_get_dimensions_reads_real_photo():
    assert get_dimensions(str(_SAMPLE_PHOTO)) == (800, 600)


def test_get_dimensions_reads_real_screenshot():
    assert get_dimensions(str(_SAMPLE_SCREENSHOT)) == (1920, 1080)


def test_get_format_detects_jpeg_by_content():
    assert get_format(str(_SAMPLE_PHOTO)) == "jpeg"


def test_get_format_detects_png_by_content():
    assert get_format(str(_SAMPLE_SCREENSHOT)) == "png"


def test_matches_screen_resolution_true_for_common_resolution():
    assert matches_screen_resolution((1920, 1080)) is True


def test_matches_screen_resolution_false_for_arbitrary_photo_dimensions():
    assert matches_screen_resolution((800, 600)) is False


def test_get_format_works_even_if_extension_lies(tmp_path):
    """A PNG saved with a .jpg extension — get_format() must trust content, not name."""
    mislabeled = tmp_path / "actually_a_png.jpg"
    Image.new("RGB", (10, 10)).save(mislabeled, format="PNG")
    assert get_format(str(mislabeled)) == "png"
