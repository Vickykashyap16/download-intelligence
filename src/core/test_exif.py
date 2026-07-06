"""
Unit tests for core/exif.py.

Run with: pytest src/core/test_exif.py -v
"""

from pathlib import Path

from PIL import Image

from src.core.exif import get_capture_date, has_camera_metadata, read_exif

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PHOTO = _PROJECT_ROOT / "Samples" / "Images" / "sample_product_photo.jpg"


def test_read_exif_returns_empty_dict_for_synthetic_image():
    """Samples/Images/*.jpg were generated with Pillow — no camera ever touched them,
    so there should be no EXIF tags at all. This is also the expected real-world case
    for a screenshot (see has_camera_metadata below)."""
    assert read_exif(str(_SAMPLE_PHOTO)) == {}


def test_has_camera_metadata_false_when_no_exif_present():
    assert has_camera_metadata(str(_SAMPLE_PHOTO)) is False


def test_get_capture_date_none_when_no_exif_present():
    assert get_capture_date(str(_SAMPLE_PHOTO)) is None


def test_has_camera_metadata_true_when_camera_tags_present(tmp_path):
    photo_with_exif = tmp_path / "photo_with_camera_exif.jpg"
    image = Image.new("RGB", (100, 100), color=(120, 80, 40))
    exif = image.getexif()
    # Tag 271 = Make, 272 = Model (standard EXIF tag IDs)
    exif[271] = "Test Camera Co."
    exif[272] = "Model X"
    image.save(photo_with_exif, exif=exif)

    assert has_camera_metadata(str(photo_with_exif)) is True
    tags = read_exif(str(photo_with_exif))
    assert tags.get("Make") == "Test Camera Co."
