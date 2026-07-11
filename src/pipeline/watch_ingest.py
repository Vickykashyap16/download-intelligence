"""
Watch & Ingest (Module 01). DETERMINISTIC module (no Claude judgment).

Architecture: Build-out/01 Watch & Ingest/01 Watch & Ingest.md
Rules: Rules/Ignore Rules.md (implemented directly — no generated config in v1,
see CHANGELOG.md)

Scans the top level of a configured Source's directory (Manual mode only, v1),
filters ignored/unstable/unsupported entries, assigns a permanent file_id (reusing
an existing one if this exact path was already discovered) plus a content hash for
every supported file, and returns FileRecords ready for pipeline/classification.py
(Module 02).

Explicitly out of scope here (later modules' responsibility): AI classification,
filename generation, moving/renaming files, duplicate detection.
"""

import mimetypes
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from src.core.hashing import sha256_file, sha256_text
from src.models.file_record import FileRecord
from src.storage.database import find_by_current_path, save_file_record
from src.storage.runtime_io import append_action_log

# --- Rules/Ignore Rules.md, implemented directly (see src/README.md "Why config/ is
# nearly empty"). Keep these in sync with that document by hand. ---

# Suffix matches -> reason "temporary_download" (in-progress/partial browser downloads)
IGNORED_DOWNLOAD_SUFFIXES = (".crdownload", ".part", ".tmp", ".download", ".!ut", ".opdownload")
# Exact filename matches -> reason "system_file" (OS/Finder/Explorer junk, not something
# the user downloaded)
IGNORED_SYSTEM_FILENAMES = {".DS_Store", "Thumbs.db", "desktop.ini", "Icon\r", ".localized"}
STABILITY_CHECKS = 2                      # number of stable-size reads before treating a file as complete
STABILITY_CHECK_INTERVAL_SECONDS = 0.5

# --- Module 01 supported file types (initial v1 list, per implementation spec).
# Narrower than the full category taxonomy in Rules/Classification Rules.md (e.g. no
# .exe/.msi yet) — see the "Assumptions" note in this module's accompanying writeup. ---

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image", ".tiff": "image",
    ".docx": "docx",
    ".txt": "text",
    ".zip": "archive",
    ".mp4": "video", ".mov": "video", ".mkv": "video", ".avi": "video",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".flac": "audio",
    ".dmg": "application", ".pkg": "application",
}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCES_CONFIG_PATH = _PROJECT_ROOT / "src" / "config" / "sources.yaml"


@dataclass
class SkippedEntry:
    """A file or folder Module 01 chose not to queue. Kept separate from FileRecord
    on purpose — we don't build a record for things we're not going to process, but
    we do keep a lightweight trace of why, for the action log and for visibility."""
    path: str
    reason: str   # "symlink" | "directory" | "system_file" | "temporary_download" |
                  # "ignored_pattern" | "zero_byte" | "unstable" | "unsupported_extension"
                  # ("ignored_pattern" is reserved for any future ignore rule that isn't
                  # an exact filename or suffix match — no current v1 rule produces it.)


@dataclass
class IngestResult:
    """Full output of one scan: what's ready for Module 02, plus everything that
    wasn't, for auditability."""
    batch_id: str
    source_id: str
    records: List[FileRecord] = field(default_factory=list)
    skipped: List[SkippedEntry] = field(default_factory=list)


def make_batch_id() -> str:
    """Timestamp-based batch identifier, e.g. '2026-07-05_143200'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")


def load_source_config(source_id: str = "downloads") -> dict:
    """Read src/config/sources.yaml and return the config entry for `source_id`.

    Raises:
        ValueError: if execution_mode isn't 'manual' (the only mode Module 01/v1
            supports), the source isn't found, isn't enabled, or has no path set.
    """
    with open(_SOURCES_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    execution_mode = config.get("execution_mode")
    if execution_mode != "manual":
        raise ValueError(
            f"Only execution_mode: manual is supported in v1 "
            f"(config/sources.yaml has '{execution_mode}')"
        )

    for source in config.get("sources", []):
        if source.get("source_id") == source_id:
            if not source.get("enabled", False):
                raise ValueError(f"Source '{source_id}' is disabled in config/sources.yaml")
            if not source.get("path"):
                raise ValueError(
                    f"Source '{source_id}' has no path set in config/sources.yaml — "
                    "fill in the real Downloads folder path before scanning"
                )
            return source

    raise ValueError(f"Source '{source_id}' not found in config/sources.yaml")


def classify_ignored_name(name: str) -> Optional[str]:
    """Return the specific ignore reason for `name` per Rules/Ignore Rules.md, or
    `None` if `name` isn't ignored by filename/pattern at all.

    - `"system_file"` — exact match against known OS/Finder/Explorer junk
      (`.DS_Store`, `Thumbs.db`, ...) — not something the user downloaded.
    - `"temporary_download"` — suffix match against known in-progress/partial
      download markers (`.crdownload`, `.part`, ...) — the file isn't finished yet.
    - `"ignored_pattern"` — reserved for a future ignore rule that's neither an exact
      filename nor a suffix (e.g. a wildcard/regex pattern). No current v1 rule in
      Rules/Ignore Rules.md produces this; kept so the reason taxonomy has somewhere
      to grow without another rename later.
    """
    if name in IGNORED_SYSTEM_FILENAMES:
        return "system_file"
    if any(name.endswith(suffix) for suffix in IGNORED_DOWNLOAD_SUFFIXES):
        return "temporary_download"
    return None


def is_ignored_name(name: str) -> bool:
    """True if `name` matches an ignored filename or suffix from Rules/Ignore Rules.md.

    Thin convenience wrapper around `classify_ignored_name()` for callers that only
    need the yes/no answer, not which specific reason applied.
    """
    return classify_ignored_name(name) is not None


def get_extension(path: Path) -> str:
    """Lowercased file extension including the leading dot, e.g. '.pdf'."""
    return path.suffix.lower()


def is_supported_extension(extension: str) -> bool:
    """True if `extension` is in the v1 supported-type list (SUPPORTED_EXTENSIONS)."""
    return extension in SUPPORTED_EXTENSIONS


def is_zero_byte(path: Path) -> bool:
    """True if the file has no content — treated as a failed/incomplete download per
    Rules/Ignore Rules.md. Returns False (rather than raising) if the file can't be
    stat'd here; a real problem reading it will surface from the caller's own attempt."""
    try:
        return path.stat().st_size == 0
    except OSError:
        return False


def is_stable(path: Path, checks: int = STABILITY_CHECKS,
              interval_seconds: float = STABILITY_CHECK_INTERVAL_SECONDS) -> bool:
    """True if the file's size doesn't change across `checks` reads, `interval_seconds`
    apart — i.e. it's done being written. This still matters in Manual mode: a scan
    triggered on demand can land in the middle of an in-progress download."""
    try:
        previous_size = path.stat().st_size
    except OSError:
        return False
    for _ in range(checks - 1):
        time.sleep(interval_seconds)
        try:
            current_size = path.stat().st_size
        except OSError:
            return False
        if current_size != previous_size:
            return False
        previous_size = current_size
    return True


def get_mime_type(path: Path) -> Optional[str]:
    """Best-effort MIME type from the standard library — 'if available' per the
    Module 01 spec. Returns None for types Python's mimetypes doesn't recognize."""
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type


def get_created_at(stat_result) -> str:
    """ISO timestamp for filesystem creation time. Falls back to metadata-change time
    (st_ctime) on platforms without a true birth time — st_birthtime is macOS/BSD-only;
    Linux has no creation-time concept at the filesystem level."""
    timestamp = getattr(stat_result, "st_birthtime", stat_result.st_ctime)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def get_modified_at(stat_result) -> str:
    """ISO timestamp for filesystem modification time."""
    return datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat()


def generate_new_file_id() -> str:
    """A fresh, permanent, arbitrary file_id (UUID4).

    Deliberately NOT derived from the file's path or content — see the "Identity"
    comment block in models/file_record.py and CHANGELOG.md for the full trade-off
    discussion (path-derived IDs break once Module 07 moves/renames the file;
    content-derived IDs collide two genuinely different files with identical bytes
    onto one record before Module 04 gets to decide what to do about it). Once
    assigned, a file_id is carried forward in the record and never recomputed.
    """
    return str(uuid.uuid4())


def build_file_record(path: Path, source_id: str, batch_id: str) -> Tuple[FileRecord, bool]:
    """Assemble a FileRecord for a supported, stable, non-ignored file.

    Returns (record, content_changed) — `content_changed` is True if a record already
    existed at this current_path with a different content_hash than what was just
    computed (content changed in place, or a different file landed at the same name).
    The caller is responsible for logging that; this function stays focused on
    building the record.

    Re-identification: before minting a new file_id, checks Database/Metadata (via
    find_by_current_path()) for a record already discovered at this exact path. If
    found, reuses its file_id and original_name/original_path/discovered_at (a file
    still sitting where it was last seen is the SAME tracked file, not a new one) —
    this is what makes repeated manual scans idempotent instead of piling up
    duplicate Database entries for a file nobody's moved yet.

    Post-freeze correction #1 (2026-07-11 — see "01 Watch & Ingest.md" and
    Release/Module01/MODULE_CONTRACT.md for the full rationale): when an existing
    record is found, it is updated IN PLACE for Module 01's own fields only — never
    reconstructed from scratch — so every downstream-owned field (Modules 02–07's,
    per MODULE_CONTRACT.md's DOES NOT MODIFY list) it may already carry survives a
    re-scan untouched. The one disclosed exception: if content_hash has genuinely
    changed, those same downstream-owned fields are explicitly reset to their
    FileRecord defaults (_reset_downstream_owned_fields()) so the record re-enters
    Modules 02–06's existing null-based reprocessing path exactly like a
    first-discovery record — the only mechanism anywhere in this pipeline that ever
    re-selects a record for processing.

    Attempts to read file contents for the SHA-256 content hash; if that fails
    (locked/unreadable), still returns a record — with status='unreadable' and the
    error recorded — rather than raising, per the "do not crash the pipeline"
    requirement. Only ever sets the fields Module 01 owns; everything from
    classification onward is either left exactly as it was (unchanged content) or
    explicitly reset to its default (changed content) — never freshly computed here.
    """
    resolved_path = path.resolve()
    current_path = str(resolved_path)
    stat_result = resolved_path.stat()
    now = datetime.now(timezone.utc).isoformat()

    existing_record = find_by_current_path(current_path)

    content_hash: Optional[str] = None
    status = "discovered"
    error: Optional[str] = None
    try:
        content_hash = sha256_file(resolved_path)
    except OSError as read_error:
        status = "unreadable"
        error = str(read_error)

    content_changed = bool(
        existing_record
        and existing_record.content_hash
        and content_hash
        and existing_record.content_hash != content_hash
    )

    if existing_record is not None:
        record = existing_record
        record.current_path = current_path
        record.extension = get_extension(resolved_path)
        record.mime_type = get_mime_type(resolved_path)
        record.size_bytes = stat_result.st_size
        record.created_at = get_created_at(stat_result)
        record.modified_at = get_modified_at(stat_result)
        record.content_hash = content_hash
        record.status = status
        record.error = error
        record.batch_id = batch_id
        # file_id, source_id, original_name, original_path, discovered_at are
        # intentionally left untouched — already correct on the existing object.

        if content_changed:
            _reset_downstream_owned_fields(record)
    else:
        record = FileRecord(
            file_id=generate_new_file_id(),
            source_id=source_id,
            original_name=resolved_path.name,
            original_path=current_path,
            current_path=current_path,
            extension=get_extension(resolved_path),
            mime_type=get_mime_type(resolved_path),
            size_bytes=stat_result.st_size,
            created_at=get_created_at(stat_result),
            modified_at=get_modified_at(stat_result),
            content_hash=content_hash,
            discovered_at=now,
            status=status,
            error=error,
            batch_id=batch_id,
        )

    return record, content_changed


def _reset_downstream_owned_fields(record: FileRecord) -> None:
    """Reset every downstream-owned field (Modules 02–07's, per MODULE_CONTRACT.md's
    DOES NOT MODIFY list) to its FileRecord dataclass default, in place, on `record`.

    Post-freeze correction #1 (2026-07-11). Only ever called from
    build_file_record()'s content_changed branch — deliberately not a
    general-purpose helper, so a future caller doesn't reach for this outside the
    one condition it was designed for. Named explicitly, field by field, rather
    than re-constructing a fresh FileRecord and copying the identity fields across,
    so the exact set of fields this resets is visible in one place and trivially
    diffable against MODULE_CONTRACT.md's own DOES NOT MODIFY list.
    """
    record.category = None
    record.classification_signals = None
    record.extracted_metadata = {}
    record.suggested_name = None
    record.suggested_destination = None
    record.naming_signals = None
    record.duplicate_of = None
    record.version_group_id = None
    record.version_rank = None
    record.duplicate_signals = None
    record.confidence_score = None
    record.confidence_breakdown = {}
    record.tier = None
    record.processed_at = None
    record.approved_by = None
    record.approved_at = None
    record.reversible = True


def scan_source(source_path: str, source_id: str = "downloads",
                 batch_id: Optional[str] = None) -> IngestResult:
    """Scan the top level of `source_path` (no recursion, v1 — see Rules/Ignore
    Rules.md "Source scope") and return an IngestResult: FileRecords ready for
    Module 02, plus everything skipped along the way.

    Never lets a single bad entry stop the scan — any unexpected failure while
    processing one entry is caught, recorded, and scanning continues.
    """
    batch_id = batch_id or make_batch_id()
    result = IngestResult(batch_id=batch_id, source_id=source_id)
    directory = Path(source_path)

    if not directory.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_path}")

    for entry in sorted(directory.iterdir()):
        try:
            _process_entry(entry, source_id, batch_id, result)
        except Exception as unexpected_error:  # a single bad entry must not stop the scan
            result.skipped.append(SkippedEntry(path=str(entry), reason=f"error: {unexpected_error}"))
            append_action_log(
                batch_id=batch_id,
                file_id=sha256_text(str(entry.resolve())),
                action="error",
                from_path=str(entry),
                details={"error": str(unexpected_error)},
            )

    return result


def _process_entry(entry: Path, source_id: str, batch_id: str, result: IngestResult) -> None:
    """Decide what to do with one directory entry and update `result` accordingly."""
    if entry.is_symlink():
        # Checked first, before is_dir()/is_file() follow the link: a symlink inside
        # the source directory can point anywhere on disk, including outside it
        # entirely. Silently following it would hash and record the path of whatever
        # it points to (and, once Module 07 exists, could move/rename that target) —
        # not something this automation should ever do without the user explicitly
        # opting in. Skipped unconditionally in v1; not a v1 requirement to support
        # following symlinks, so there's no taxonomy to design around it yet.
        _skip(entry, "symlink", batch_id, result)
        return

    if entry.is_dir():
        _skip(entry, "directory", batch_id, result)
        return

    ignored_reason = classify_ignored_name(entry.name)
    if ignored_reason is not None:
        _skip(entry, ignored_reason, batch_id, result)
        return

    if is_zero_byte(entry):
        _skip(entry, "zero_byte", batch_id, result)
        return

    if not is_stable(entry):
        _skip(entry, "unstable", batch_id, result)
        return

    extension = get_extension(entry)
    if not is_supported_extension(extension):
        _skip(entry, "unsupported_extension", batch_id, result)
        return

    record, content_changed = build_file_record(entry, source_id, batch_id)
    result.records.append(record)

    if record.status == "unreadable":
        append_action_log(
            batch_id=batch_id, file_id=record.file_id, action="error",
            from_path=record.current_path, details={"error": record.error},
        )
    else:
        details = {"content_changed_since_last_scan": True} if content_changed else None
        append_action_log(
            batch_id=batch_id, file_id=record.file_id, action="discover",
            from_path=record.current_path, details=details,
        )


def _skip(entry: Path, reason: str, batch_id: str, result: IngestResult) -> None:
    """Record a skipped entry (not queued, no FileRecord) and log it."""
    result.skipped.append(SkippedEntry(path=str(entry), reason=reason))
    append_action_log(
        batch_id=batch_id,
        file_id=sha256_text(str(entry.resolve())),
        action="skip",
        from_path=str(entry),
        details={"reason": reason},
    )


def build_ingest_queue(source_path: str, source_id: str = "downloads") -> List[FileRecord]:
    """Run scan_source() and persist every discovered FileRecord to
    Database/Metadata/, returning just the records for Module 02 (skipped entries
    stay out of the returned list — see IngestResult for the full picture)."""
    result = scan_source(source_path, source_id)
    for record in result.records:
        save_file_record(record)
    return result.records
