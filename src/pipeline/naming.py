"""
Naming & Destination (Module 05). DETERMINISTIC module — no Claude judgment, no
Provider (Module 05 Design.md §17, confirmed §29 item 11): every decision here is a
computation over already-structured data (a category label, a dict of already-
extracted string/number values, Module 04's already-computed signals) — never a
judgment call requiring content understanding. Module 05 never opens a file, never
reads bytes, never looks at an image.

Architecture: Build-out/05 Naming & Destination/Module 05 Design.md (frozen, all 12
architectural decisions resolved and recorded in its §29).

Two layers, not three (§6): this file's `suggest_naming_and_destination_batch()`
(batch orchestration: filtering, persistence, logging) -> `NamingEngine` (per-file
decision-making: build filename -> sanitize -> resolve within-batch collision ->
resolve destination; fully deterministic).
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from src.models.classification import Category
from src.models.file_record import FileRecord
from src.models.naming import NamingSignals
from src.storage.database import save_file_record
from src.storage.runtime_io import append_action_log

# --- Category -> destination folder mapping (Rules/Folder Rules.md, §14). No
# pipeline-ordering problem here, unlike `tier` (§8) — category has existed since
# Module 02, so this table is unconditionally usable. ---

_CATEGORY_FOLDER: Dict[Category, str] = {
    Category.INVOICE: "Finance/",
    Category.BANK_STATEMENT: "Finance/",
    Category.CONTRACT: "Documents/",
    Category.RESUME: "Documents/",
    Category.DOCUMENT: "Documents/",
    Category.IMAGE: "Images/",
    Category.SCREENSHOT: "Images/Screenshots/",
    Category.APPLICATION: "Applications/",
    Category.ARCHIVE: "Archives/",
    Category.VIDEO: "Videos/",
    Category.AUDIO: "Audio/",
    Category.UNKNOWN: "Unknown/",
}

_ARCHIVE_DUPLICATES_PATH = "~ARCHIVE~/Duplicates/"
_ARCHIVE_OLD_VERSIONS_PATH = "~ARCHIVE~/Old Versions/"


def _determine_override(record: FileRecord) -> Optional[str]:
    """Single source of truth for which Module 04 override (if any) applies to this
    record (§14): "exact_duplicate" | "superseded_version" | None. Consumed by both
    `resolve_destination()` and `NamingEngine.suggest_file()` so the destination
    actually returned and the `override_applied` value actually logged can never
    independently drift apart — previously each recomputed this check separately
    (Module 05 Implementation Audit, L2)."""
    if record.duplicate_of is not None:
        return "exact_duplicate"
    if record.version_rank == "superseded":
        return "superseded_version"
    return None


def resolve_destination(record: FileRecord) -> str:
    """Category -> folder mapping (Rules/Folder Rules.md), with Module 04's
    duplicate/version overrides taking precedence regardless of category (§14) —
    mirroring Module 04's own "exact-duplicate detection runs regardless of
    category" precedent. Confirmed (§29 item 1): never depends on `tier` — the
    "don't move a review_required file" behavior is Module 07's execution-time gate
    (§8), not something Module 05 can know at this point in the pipeline.
    """
    override = _determine_override(record)
    if override == "exact_duplicate":
        return _ARCHIVE_DUPLICATES_PATH
    if override == "superseded_version":
        return _ARCHIVE_OLD_VERSIONS_PATH
    return _CATEGORY_FOLDER.get(record.category, "Unknown/")


# --- Template field-mapping (§10/§11, confirmed §29 items 4, 5, 7, 8, 9). Every
# category not given its own bespoke filler below uses `_SIMPLE_TEMPLATES`: a
# required field missing gets the general "Unknown_X" placeholder (recorded in
# naming_signals per §11's adopted Rules/Naming Rules.md convention — "missing
# fields get a safe fallback... never left blank"); an optional field referenced by
# the template is treated identically (still a real template slot, still gets an
# "Unknown_X" placeholder when absent) — no category outside the 5 explicitly
# decided in the review (Invoice/Resume/Archive/Video/Audio) was flagged as needing
# different treatment (§10's table marks them all "Clean match"), so the general
# rule applies to them unmodified. ---

_SIMPLE_TEMPLATES: Dict[Category, List[Tuple[str, Optional[Tuple[str, str]]]]] = {
    Category.BANK_STATEMENT: [
        ("field", ("bank_name", "Unknown_BankName")),
        ("literal", "Statement"),
        ("field", ("statement_period", "Unknown_Period")),
    ],
    Category.CONTRACT: [
        ("field", ("contract_type", "Unknown_ContractType")),
        ("field", ("counterparty", "Unknown_Counterparty")),
        ("field", ("effective_date", "Unknown_EffectiveDate")),
    ],
    Category.DOCUMENT: [
        ("field", ("best_guess_title", "Unknown_Title")),
        ("field", ("document_date", "Unknown_Date")),
    ],
    Category.IMAGE: [
        ("field", ("description", "Unknown_Description")),
        ("field", ("variant", "Unknown_Variant")),
    ],
    Category.SCREENSHOT: [
        ("literal", "Screenshot"),
        ("field", ("context_description", "Unknown_Context")),
        ("field", ("capture_date", "Unknown_Date")),
    ],
    Category.APPLICATION: [
        ("field", ("app_name", "Unknown_AppName")),
        ("field", ("version", "Unknown_Version")),
        ("field", ("platform", "Unknown_Platform")),
    ],
}


def _fill_simple_template(
    record: FileRecord, spec: List[Tuple[str, Optional[Tuple[str, str]]]]
) -> Tuple[List[str], List[str]]:
    components: List[str] = []
    fields_fell_back: List[str] = []
    for kind, value in spec:
        if kind == "literal":
            components.append(value)
            continue
        field_name, fallback_label = value
        raw = record.extracted_metadata.get(field_name)
        if raw is not None:
            components.append(str(raw))
        else:
            components.append(fallback_label)
            fields_fell_back.append(field_name)
    return components, fields_fell_back


# --- The 5 categories the architectural decision review explicitly resolved
# (§29 items 4, 5, 7, 8, 9) — each needed bespoke treatment because the general
# "insert Unknown_X" rule either had no valid taxonomy field to point at (Invoice's
# old {DocSubtype}, Archive's {Date}), was a composite of two independent fields
# with no priority rule (Resume's {VersionOrDate}), or referenced a nonexistent
# field entirely (Audio's old fallback template). ---


def _fill_invoice(record: FileRecord) -> Tuple[List[str], List[str]]:
    """§29 item 4: `{Vendor}_{InvoiceNumber}_{Date}`, falling back to
    `{Vendor}_{Date}` when `invoice_number` is absent — an optional enrichment
    field that is OMITTED when absent, not replaced with a placeholder (so its
    absence is not recorded in naming_signals; omission is a structural template
    choice, not a fallback to a placeholder value, §11)."""
    fields_fell_back: List[str] = []
    vendor = record.extracted_metadata.get("vendor")
    if vendor is not None:
        vendor_component = str(vendor)
    else:
        vendor_component = "Unknown_Vendor"
        fields_fell_back.append("vendor")

    invoice_date = record.extracted_metadata.get("invoice_date")
    if invoice_date is not None:
        date_component = str(invoice_date)
    else:
        date_component = "Unknown_Date"
        fields_fell_back.append("invoice_date")

    components = [vendor_component]
    invoice_number = record.extracted_metadata.get("invoice_number")
    if invoice_number is not None:
        components.append(str(invoice_number))
    components.append(date_component)
    return components, fields_fell_back


def _fill_resume(record: FileRecord) -> Tuple[List[str], List[str]]:
    """§29 item 9: `Resume_{CandidateName}_{VersionOrDate}` — `version_indicator`
    takes priority when present, falling back to `last_modified_date`, falling back
    to the literal "Unknown" only when neither is present. When both are absent,
    BOTH real taxonomy field names are recorded individually — never the synthetic
    label "version_or_date" (Module 05 Implementation Audit M1) — applying §5's
    already-established "one entry per affected field" rule exactly the same way
    every other multi-required-field category already does (Invoice, Bank
    Statement, Contract, Document all record one entry per missing field, never a
    combined label). Using `last_modified_date` successfully (only one of the two
    absent) is still a real, honest value, not a placeholder, and is never recorded
    (§11)."""
    fields_fell_back: List[str] = []
    candidate_name = record.extracted_metadata.get("candidate_name")
    if candidate_name is not None:
        name_component = str(candidate_name)
    else:
        name_component = "Unknown_CandidateName"
        fields_fell_back.append("candidate_name")

    version_indicator = record.extracted_metadata.get("version_indicator")
    last_modified_date = record.extracted_metadata.get("last_modified_date")
    if version_indicator is not None:
        version_or_date_component = str(version_indicator)
    elif last_modified_date is not None:
        version_or_date_component = str(last_modified_date)
    else:
        version_or_date_component = "Unknown"
        fields_fell_back.append("version_indicator")
        fields_fell_back.append("last_modified_date")

    return ["Resume", name_component, version_or_date_component], fields_fell_back


def _tier4_date_component(record: FileRecord) -> Tuple[str, bool]:
    """`modified_at` (Module 01, tier-4) fallback for a category with no usable
    category-specific date field at all (§29 items 5/7 — Archive, Video). Returns
    (component, used_placeholder). `used_placeholder` is True only when
    `modified_at` itself is also unavailable, forcing the literal "Unknown_Date"
    placeholder — recorded in naming_signals, by the real field name that actually
    had no value (`modified_at` — a real `FileRecord` field, not the synthetic
    label "date", Module 05 Implementation Audit M1), only in that case;
    successfully using `modified_at` is a real, honest value, not a placeholder
    (§11), the same "flagged, not authoritative" treatment Module 03/04's own
    timestamp hierarchies already established, never itself logged as a
    fallback_used-style event.

    `modified_at` is a full ISO-8601 timestamp (e.g. "2026-07-05T14:31:40Z"), not
    already a bare date — the first 10 characters (`YYYY-MM-DD`) are used, matching
    `Rules/Naming Rules.md`'s general rule ("Dates always in YYYY-MM-DD format"),
    the same rule every category-specific date field is already expected to comply
    with. This is applying an existing, general rule to a new date source, not a
    new one.
    """
    if record.modified_at is not None:
        return str(record.modified_at)[:10], False
    return "Unknown_Date", True


def _fill_archive(record: FileRecord) -> Tuple[List[str], List[str]]:
    """§29 item 5: `{ContentsSummary}_{Date}` — Archive has no date field of any
    kind in its taxonomy, so `{Date}` always falls to `modified_at` (tier-4)."""
    fields_fell_back: List[str] = []
    contents_summary = record.extracted_metadata.get("contents_summary")
    if contents_summary is not None:
        summary_component = str(contents_summary)
    else:
        summary_component = "Unknown_ContentsSummary"
        fields_fell_back.append("contents_summary")

    date_component, used_placeholder = _tier4_date_component(record)
    if used_placeholder:
        fields_fell_back.append("modified_at")

    return [summary_component, date_component], fields_fell_back


def _fill_video(record: FileRecord) -> Tuple[List[str], List[str]]:
    """§29 item 7: `{Description}_{Date}` — `{Date}` maps to `content_date`, always
    `null` in v1 (no video-tag library approved), so it falls to `modified_at`
    (tier-4), the same rule as Archive."""
    fields_fell_back: List[str] = []
    description = record.extracted_metadata.get("description")
    if description is not None:
        description_component = str(description)
    else:
        description_component = "Unknown_Description"
        fields_fell_back.append("description")

    date_component, used_placeholder = _tier4_date_component(record)
    if used_placeholder:
        fields_fell_back.append("modified_at")

    return [description_component, date_component], fields_fell_back


def _fill_audio(record: FileRecord) -> Tuple[List[str], List[str]]:
    """§29 item 8: `{TrackTitle}_{Artist}`, falling back to
    `{TrackTitle}_{RecordingDate}` when `artist` is absent, falling back further to
    `{TrackTitle}` alone when `recording_date` is also absent — the second slot is
    OMITTED in that last case, not placeholder-filled, so it is never recorded in
    naming_signals (§11, same omission treatment as Invoice's `invoice_number`).
    `track_title` is required and Module 03 always populates it (filename-stem
    fallback, `metadata.py`'s `_extract_audio_fields()`) — the "Unknown_TrackTitle"
    branch below is defensive only."""
    fields_fell_back: List[str] = []
    track_title = record.extracted_metadata.get("track_title")
    if track_title is not None:
        title_component = str(track_title)
    else:
        title_component = "Unknown_TrackTitle"
        fields_fell_back.append("track_title")

    components = [title_component]
    artist = record.extracted_metadata.get("artist")
    recording_date = record.extracted_metadata.get("recording_date")
    if artist is not None:
        components.append(str(artist))
    elif recording_date is not None:
        components.append(str(recording_date))
    # else: omit the second slot entirely — track_title alone.

    return components, fields_fell_back


def _fill_unknown(record: FileRecord) -> Tuple[List[str], List[str]]:
    """`UNSORTED_{OriginalName}` — `original_name` is a Module 01 field, always
    populated, never a `Category.UNKNOWN` fallback concern. `{OriginalName}` uses
    the filename stem only; the extension is appended once, uniformly, by
    `build_filename()` for every category (§6)."""
    stem = Path(record.original_name).stem if record.original_name else "Unknown"
    return ["UNSORTED", stem], []


_BESPOKE_FILLERS: Dict[Category, Callable[[FileRecord], Tuple[List[str], List[str]]]] = {
    Category.INVOICE: _fill_invoice,
    Category.RESUME: _fill_resume,
    Category.ARCHIVE: _fill_archive,
    Category.VIDEO: _fill_video,
    Category.AUDIO: _fill_audio,
    Category.UNKNOWN: _fill_unknown,
}


def build_filename_components(record: FileRecord) -> Tuple[List[str], List[str]]:
    """(components, fields_fell_back) for `record`'s category, per §10/§11's
    confirmed per-category field mapping. Components are raw (unsanitized,
    unjoined) — `build_filename()` is responsible for joining and sanitizing them
    and for appending the extension, so every category is handled uniformly for
    those concerns regardless of its own template shape."""
    category = record.category
    bespoke = _BESPOKE_FILLERS.get(category)
    if bespoke is not None:
        return bespoke(record)
    spec = _SIMPLE_TEMPLATES.get(category)
    if spec is not None:
        return _fill_simple_template(record, spec)
    # Defensive only (§21) — every real Category member is covered above, since
    # Rules/Naming Rules.md and Rules/Folder Rules.md cover every member.
    stem = Path(record.original_name).stem if record.original_name else "Unknown"
    return [stem], []


# --- Sanitization (§12, confirmed §29 item 6). ---

_ALLOWED_CHARS = re.compile(r"[^A-Za-z0-9_\-]")
_WHITESPACE_RUN = re.compile(r"\s+")
_MAX_STEM_LENGTH = 80


def _normalize_whitespace(value: str) -> str:
    """Design §12, post-freeze correction #1: every run of one or more whitespace
    characters (spaces, tabs, newlines, and other Unicode whitespace matched by
    `\\s`) becomes a single "_", applied BEFORE the whitelist filter below. Without
    this step, whitespace was silently stripped like any other disallowed
    character, running multi-word field values together (e.g. "Northwind Traders"
    -> "Northwindtraders") — a real design-completeness gap discovered during UAT
    (Finding UAT-1), not an implementation defect (the prior behavior matched the
    frozen design's text exactly). A run of whitespace adjacent to an existing "_"
    does not double it: `sanitize_filename()`'s existing segment-split-and-filter
    step (splitting on "_", dropping empty segments) already collapses any doubled
    or stray "_" this substitution could introduce, so no separate de-duplication
    is needed here."""
    return _WHITESPACE_RUN.sub("_", str(value))


def _strip_disallowed(value: str) -> str:
    """Whitelist-only character filtering: letters, digits, underscore, and hyphen
    pass through; every other character (including all Unicode outside that set)
    is stripped, not replaced or rejected. A closed, structurally enforced
    boundary — directly closes the path-injection concern (§19): path separators,
    `..`, and every other traversal-relevant character are excluded by
    construction, not by enumeration. Whitespace is normalized to "_" by
    `_normalize_whitespace()` before this function ever sees it (post-freeze
    correction #1), so it never reaches this step as whitespace."""
    return _ALLOWED_CHARS.sub("", str(value))


def _truncate_longest_segment(segments: List[str]) -> List[str]:
    """If the assembled stem (segments joined by "_") would exceed ~80 characters,
    the single longest segment is truncated first, preserving every other segment
    intact — never a whole-string truncation, never a reject/flag (§12). Iterates
    (truncate the current-longest segment, drop it entirely if it's truncated to
    empty, recheck) rather than a single pass, so the ~80-character cap is always
    actually enforced even when no single segment's own length can absorb the full
    overflow (several comparably-large segments) — a single pass could previously
    leave the assembled name over budget and could leave a stray empty segment that
    rendered as a leading/doubled "_" once joined (Module 05 Implementation Audit,
    M2). Each iteration strictly shortens the total length or removes a segment, so
    this always terminates."""
    segments = [s for s in segments if s]
    while segments:
        stem_length = sum(len(s) for s in segments) + (len(segments) - 1)
        if stem_length <= _MAX_STEM_LENGTH:
            break
        overflow = stem_length - _MAX_STEM_LENGTH
        longest_index = max(range(len(segments)), key=lambda i: len(segments[i]))
        new_length = max(0, len(segments[longest_index]) - overflow)
        if new_length == 0:
            segments.pop(longest_index)
        else:
            segments[longest_index] = segments[longest_index][:new_length]
    return segments


def sanitize_filename(stem: str) -> str:
    """§12, confirmed (whitespace handling corrected post-freeze correction #1):
    whitespace-to-"_" normalization, then whitelist-only character filtering, then
    naive per-word (underscore-delimited-segment) Title_Case with no exceptions
    list — e.g. "NDA" -> "Nda" (`str.capitalize()`'s exact behavior, matching the
    design's own worked example) — then longest-segment truncation at the
    ~80-character boundary. Operates on an already-assembled, extension-free,
    underscore-joined stem; `build_filename()` is responsible for joining raw
    template components with "_" before calling this."""
    normalized = _normalize_whitespace(stem)
    stripped = _strip_disallowed(normalized)
    segments = [segment for segment in stripped.split("_") if segment]
    segments = _truncate_longest_segment(segments)
    return "_".join(segment.capitalize() for segment in segments)


def build_filename(record: FileRecord) -> Tuple[str, List[str]]:
    """Fill `record`'s category-appropriate naming template (§10/§11), sanitize it
    (§12), and append the original extension — the original file extension is
    always preserved (general rule, `Rules/Naming Rules.md`). Within-batch collision
    resolution (§13) is a separate, later step, applied by the caller. Returns
    (filename_with_extension, fields_fell_back). `Category.UNKNOWN` is processed
    identically to every other category (§12: no separate sanitization code path)."""
    components, fields_fell_back = build_filename_components(record)
    raw_stem = "_".join(str(c) for c in components if c not in (None, ""))
    sanitized_stem = sanitize_filename(raw_stem) or "Unknown"

    extension = record.extension or Path(record.original_name or "").suffix or ""
    if extension and not extension.startswith("."):
        extension = f".{extension}"

    return f"{sanitized_stem}{extension}", fields_fell_back


# --- Within-batch collision resolution (§9/§13). Real-filesystem collision
# detection against the destination library is explicitly out of scope for this
# module — Module 07 is responsible for the authoritative check at execution time. ---


def _split_extension(name: str) -> Tuple[str, str]:
    path = Path(name)
    return path.stem, path.suffix


def resolve_within_batch_collision(
    name: str, destination: str, seen_this_batch: Dict[Tuple[str, str], int]
) -> str:
    """If another record already processed in this same batch produced the
    identical `(suggested_name, suggested_destination)` pair, append `_2`, `_3`,
    etc. before the extension — never overwrite (§13). `seen_this_batch` is a
    per-batch counter dict, mutated by the caller across the whole batch, so
    re-running an identical batch always assigns the same suffixes (§7, confirmed
    §29 item 12's deterministic processing order)."""
    key = (destination, name)
    count = seen_this_batch.get(key, 0)
    seen_this_batch[key] = count + 1
    if count == 0:
        return name
    stem, extension = _split_extension(name)
    return f"{stem}_{count + 1}{extension}"


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


@dataclass
class EngineResult:
    """Everything NamingEngine.suggest_file() hands back to
    suggest_naming_and_destination_batch() for one file — enough to populate
    FileRecord's suggested_name/suggested_destination/naming_signals and write a
    complete `suggest_naming_and_destination` action-log entry without the batch
    orchestration needing to know how the answer was reached."""
    suggested_name: str
    suggested_destination: str
    naming_signals: NamingSignals = field(default_factory=NamingSignals)
    override_applied: Optional[str] = None   # "exact_duplicate" | "superseded_version" | None
    collision_suffix_applied: bool = False
    processing_time_ms: int = 0


class NamingEngine:
    """Per-file decision-making (§6/§7) — fully deterministic, no Provider (§17,
    confirmed §29 item 11)."""

    def suggest_file(
        self, record: FileRecord, seen_this_batch: Dict[Tuple[str, str], int]
    ) -> EngineResult:
        """Suggest a name and destination for one already-classified,
        already-duplicate/version-checked record. Callers
        (`suggest_naming_and_destination_batch()`) are responsible for only calling
        this on records with `status == "discovered"` and a non-None `category`
        (§3/§7 step 1, including `Category.UNKNOWN`) — the Engine itself does not
        re-check this, matching every earlier module's Engine's precedent of
        trusting its caller's filtering."""
        start = time.monotonic()

        name, fields_fell_back = build_filename(record)
        destination = resolve_destination(record)
        override_applied = _determine_override(record)

        name_before_collision = name
        name = resolve_within_batch_collision(name, destination, seen_this_batch)

        return EngineResult(
            suggested_name=name,
            suggested_destination=destination,
            naming_signals=NamingSignals(fields_fell_back=fields_fell_back),
            override_applied=override_applied,
            collision_suffix_applied=(name != name_before_collision),
            processing_time_ms=_elapsed_ms(start),
        )


# --- Module 05 batch orchestration: filtering, persistence, logging. This is the
# only layer that touches storage/*.py or Runtime/Logs directly (§6) — the Engine
# never does, since there is no Provider layer here either. ---


def suggest_naming_and_destination_batch(records: List[FileRecord]) -> List[FileRecord]:
    """Suggest a name and destination for every already-classified,
    already-duplicate/version-checked record, persist the results, and log one
    `suggest_naming_and_destination` action-log entry per file. Mirrors
    detect_duplicates_batch()'s shape: same records in, same records back out,
    enriched in place, no disclosed side effect on any other record (§5) —
    within-batch collision resolution (§13) reads other records in the same batch
    but never writes to them.

    Records are processed in the same deterministic order Module 04 already
    established — `discovered_at` ascending, `file_id` (lexicographic) as the
    final tie-break — confirmed §29 item 12, so re-running the same batch always
    assigns the same collision suffixes.

    Records with `status != "discovered"` or `category is None` are left
    completely untouched (§7 step 1/§26) — unlike Module 03, `Category.UNKNOWN` is
    NOT skipped (§3). Filtering out records Module 05 has already processed (so a
    second run doesn't re-suggest a name for a record that already has one) is the
    caller's responsibility (mirrors Module 02/03's `category is None`/
    `extracted_metadata == {}` precedent, not Module 04's special-cased
    `needs_duplicate_detection()`, since `suggested_name` is unambiguously null
    only pre-processing and always a real, non-empty string afterward — no
    "legitimately stays null forever" case exists here the way it does for Module
    04's `duplicate_of`/`version_group_id`/`version_rank`).
    """
    seen_this_batch: Dict[Tuple[str, str], int] = {}
    ordered_records = sorted(records, key=lambda r: (r.discovered_at or "", r.file_id))

    for record in ordered_records:
        if record.status != "discovered" or record.category is None:
            continue

        engine = NamingEngine()
        try:
            result = engine.suggest_file(record, seen_this_batch)
        except Exception as unexpected_error:
            # Outer safety net — a single bad file must never abort the batch,
            # the same resilience pattern every earlier module already establishes
            # (§21).
            append_action_log(
                batch_id=record.batch_id,
                file_id=record.file_id,
                action="error",
                from_path=record.current_path,
                details={"stage": "naming_and_destination", "error": str(unexpected_error)},
            )
            continue

        record.suggested_name = result.suggested_name
        record.suggested_destination = result.suggested_destination
        record.naming_signals = result.naming_signals
        save_file_record(record)

        details = {
            "suggested_name": result.suggested_name,
            "suggested_destination": result.suggested_destination,
            "fields_fell_back": result.naming_signals.fields_fell_back,
            "collision_suffix_applied": result.collision_suffix_applied,
            "override_applied": result.override_applied,
            "processing_time_ms": result.processing_time_ms,
        }
        append_action_log(
            batch_id=record.batch_id,
            file_id=record.file_id,
            action="suggest_naming_and_destination",
            from_path=record.current_path,
            details=details,
        )

    return records
