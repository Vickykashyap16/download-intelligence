"""
Unit tests for core/media.py — Module 03's Audio embedded-tag reading.

Constructing a real audio file with embedded ID3-style tags purely in Python (no
system codec/encoder available in this sandbox) is impractical for a WAV/MP3 without
a real encoder, so the "tags present" case uses a monkeypatched `mutagen.File()` (a
standard, honest way to unit-test against an external library's return shape without
needing a real encoded audio stream) — the same pragmatic trade-off Module 02 made
when constructing synthetic in-memory images via PIL rather than real camera photos.
The "no tags, but a valid file" and "corrupted/unparseable file" cases use a real WAV
file (Python's stdlib `wave` module produces a genuinely valid, openable audio file)
and the existing synthetic placeholder fixture respectively — both real files, no
mocking needed.

Run with: pytest src/core/test_media.py -v
"""

import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.media import read_audio_tags

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _make_silent_wav(path: Path, seconds: float = 1.0) -> None:
    with wave.open(str(path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        frame_count = int(8000 * seconds)
        wav_file.writeframes(struct.pack("<h", 0) * frame_count)


def test_read_audio_tags_real_untagged_file_reports_duration_and_null_tags(tmp_path):
    """A genuinely valid, openable audio file with no embedded tags at all —
    duration is real (mutagen reads it from the stream itself), tag fields are None
    (not fabricated) — the honest "found some things, not others" case (§7)."""
    wav_path = tmp_path / "silent.wav"
    _make_silent_wav(wav_path, seconds=2.0)

    tags = read_audio_tags(str(wav_path))
    assert tags["duration"] == 2
    assert tags["track_title"] is None
    assert tags["artist"] is None
    assert tags["recording_date"] is None


def test_read_audio_tags_raises_for_unparseable_file(tmp_path):
    """A file mutagen can't open as audio at all — the caller (Engine) is expected to
    catch this and fall back, not this function. Uses the project's existing
    synthetic placeholder audio fixture (Tests/Small Batch/audio_clip.mp3, which is
    not real MPEG audio content — the same category of fixture that surfaced Module
    02's image-read-failure defect during its own integration testing)."""
    placeholder = _PROJECT_ROOT / "Tests" / "Small Batch" / "audio_clip.mp3"
    with pytest.raises(Exception):
        read_audio_tags(str(placeholder))


def test_read_audio_tags_reads_title_artist_date_when_present(tmp_path, monkeypatch):
    """Monkeypatches mutagen.File() to return a double shaped like mutagen's own
    "easy" tag interface (a dict-like `.tags` plus `.info.length`), to exercise the
    tag-reading logic against every field it's supposed to read without needing a
    real encoder. See this file's docstring for why this trade-off was made."""
    import src.core.media as media_module

    fake_audio = SimpleNamespace(
        tags={"title": ["Test Track"], "artist": ["Test Artist"], "date": ["2024-03-01"]},
        info=SimpleNamespace(length=183.4),
    )
    monkeypatch.setattr(media_module.mutagen, "File", lambda path, easy=True: fake_audio)

    tags = read_audio_tags("irrelevant/path.mp3")
    assert tags["track_title"] == "Test Track"
    assert tags["artist"] == "Test Artist"
    assert tags["recording_date"] == "2024-03-01"
    assert tags["duration"] == 183  # rounded


def test_read_audio_tags_raises_when_mutagen_returns_none(monkeypatch):
    """mutagen.File() legitimately returns None for a file it doesn't recognize at
    all as any supported audio format — treated the same as an outright failure by
    read_audio_tags(), not silently swallowed."""
    import src.core.media as media_module

    monkeypatch.setattr(media_module.mutagen, "File", lambda path, easy=True: None)

    with pytest.raises(ValueError):
        read_audio_tags("irrelevant/path.mp3")
