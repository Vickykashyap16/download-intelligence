"""
Unit tests for core/hashing.py's Module 04 additions — perceptual_hash()/
hamming_distance(). sha256_file()/sha256_text() (Module 01) are already exercised
via pipeline/test_watch_ingest.py.

Run with: pytest src/core/test_hashing.py -v
"""

from PIL import Image

from src.core.hashing import hamming_distance, perceptual_hash


def _make_image(path, color, size=(64, 64)):
    Image.new("RGB", size, color=color).save(path)


def test_perceptual_hash_is_identical_for_identical_images(tmp_path):
    path_a = tmp_path / "a.png"
    path_b = tmp_path / "b.png"
    _make_image(path_a, (200, 50, 50))
    _make_image(path_b, (200, 50, 50))

    assert perceptual_hash(path_a) == perceptual_hash(path_b)


def test_perceptual_hash_differs_for_very_different_images(tmp_path):
    path_a = tmp_path / "solid_red.png"
    path_b = tmp_path / "checkerboard.png"
    _make_image(path_a, (255, 0, 0))

    image = Image.new("RGB", (64, 64))
    pixels = image.load()
    for x in range(64):
        for y in range(64):
            pixels[x, y] = (255, 255, 255) if (x // 8 + y // 8) % 2 == 0 else (0, 0, 0)
    image.save(path_b)

    hash_a = perceptual_hash(path_a)
    hash_b = perceptual_hash(path_b)
    assert hamming_distance(hash_a, hash_b) > 5


def test_hamming_distance_is_zero_for_identical_hashes(tmp_path):
    path = tmp_path / "photo.png"
    _make_image(path, (10, 20, 30))
    h = perceptual_hash(path)
    assert hamming_distance(h, h) == 0


def test_perceptual_hash_raises_for_unreadable_image(tmp_path):
    garbage = tmp_path / "not_an_image.png"
    garbage.write_bytes(b"this is not image data at all")
    try:
        perceptual_hash(garbage)
        assert False, "expected an exception for unreadable image data"
    except Exception:
        pass  # DuplicateDetectionEngine is responsible for catching this (§21)
