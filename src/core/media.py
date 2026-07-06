"""
Deterministic module — no Claude judgment involved.

Embedded audio-tag reading for Module 03 (Metadata Extraction)'s Audio category —
`track_title`, `artist`, `duration`, `recording_date`. Uses `mutagen` (pure-Python,
no system binary dependency, actively maintained), proposed and approved in
Build-out/03 Metadata Extraction/Module 03 Design.md §16.

`recording_date` is tier 1 of the timestamp source hierarchy (Module 03 Design.md
§9A) — the highest-priority tier, since it comes from a tag the recording device/
software itself wrote about its own content, not a filesystem timestamp.

Video tag/duration reading is deliberately NOT included here, and has no equivalent
module in v1: no library dependency is approved for it (Module 03 Design.md
§9A/§16/§27) — a robust solution generally needs a system binary (`ffprobe`) that
isn't guaranteed present in every environment this project runs in. Video's
`duration`/`content_date` fields stay unconditionally `null` in v1, handled entirely
in src/pipeline/metadata.py without calling into any core/ module for them.

Implemented for Module 03 — its only current consumer.
"""

from typing import Optional

import mutagen


def read_audio_tags(path: str) -> dict:
    """Return whatever of track_title/artist/duration/recording_date embedded tags
    provide, each None if the tag is absent. Never raises for a validly-openable audio
    file that simply has no tags (or no tags of a particular kind) — only for a file
    mutagen can't open as audio at all (corrupted, or not really an audio file despite
    its extension), which the caller's per-record error handling (Module 03
    Design.md §12) is expected to catch.

    Uses mutagen's "easy" tag interface (`easy=True`), which normalizes tag names
    across formats (ID3/MP4/FLAC/etc.) to a common, small vocabulary — "title",
    "artist", "date" — so this function doesn't need format-specific branching.
    """
    audio = mutagen.File(path, easy=True)
    if audio is None:
        raise ValueError(f"mutagen could not open {path!r} as an audio file")

    def _first(key: str) -> Optional[str]:
        values = audio.tags.get(key) if audio.tags else None
        return values[0] if values else None

    duration_seconds = None
    if getattr(audio, "info", None) is not None:
        length = getattr(audio.info, "length", None)
        duration_seconds = round(length) if length is not None else None

    return {
        "track_title": _first("title"),
        "artist": _first("artist"),
        "duration": duration_seconds,
        "recording_date": _first("date"),
    }
