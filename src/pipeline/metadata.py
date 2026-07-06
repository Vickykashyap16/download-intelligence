"""
Metadata Extraction (Module 03). HYBRID module: deterministic passes + judgment (via
MetadataExtractionEngine -> MetadataExtractionProvider) for text/vision-dependent
categories.

Architecture: Build-out/03 Metadata Extraction/Module 03 Design.md (frozen)
Rules: the field taxonomy currently lives in this design document's §7 (see §10 for
the recommendation, still pending, to relocate it into Rules/Metadata Rules.md).

This module is layered exactly as frozen:
  Module 03 (batch orchestration, this file's extract_metadata_batch())
        -> MetadataExtractionEngine (per-file decision-making)
              -> MetadataExtractionProvider (raw structured-extraction call only)

Deliberately does NOT import anything from pipeline/classification.py beyond the
shared Category enum — MetadataExtractionEngine/Provider/exception classes are this
module's own, structurally similar to classification.py's by deliberate convention-
following, not by code sharing (Module 03 Design.md §21).
"""

import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from src.core.archive import summarize_contents
from src.core.exif import get_capture_date
from src.core.media import read_audio_tags
from src.core.pdf import extract_text as _pdf_extract_text
from src.core.pdf import render_page_as_image
from src.core.text import extract_text as _text_extract_text
from src.models.classification import Category
from src.models.file_record import FileRecord
from src.storage.database import save_file_record
from src.storage.runtime_io import append_action_log

# --- Metadata taxonomy (Module 03 Design.md §7). Implemented directly in code, no
# generated config, same convention established for Rules/Classification Rules.md —
# see design §10 for the (pending) recommendation to also promote this table into
# Rules/Metadata Rules.md. Category.UNKNOWN is deliberately absent from both maps:
# Module 03 never attempts extraction on it (see extract_metadata_batch() below). ---

REQUIRED_FIELDS: Dict[Category, Tuple[str, ...]] = {
    Category.INVOICE: ("vendor", "invoice_date"),
    Category.RESUME: ("candidate_name",),
    Category.BANK_STATEMENT: ("bank_name", "statement_period"),
    Category.CONTRACT: ("contract_type", "counterparty", "effective_date"),
    Category.DOCUMENT: ("best_guess_title",),
    Category.IMAGE: ("description",),
    Category.SCREENSHOT: ("context_description",),
    Category.APPLICATION: ("app_name",),
    Category.ARCHIVE: ("contents_summary",),
    Category.VIDEO: ("description",),
    Category.AUDIO: ("track_title",),
}

OPTIONAL_FIELDS: Dict[Category, Tuple[str, ...]] = {
    Category.INVOICE: ("invoice_number", "amount", "currency", "tax_type"),
    Category.RESUME: ("version_indicator", "last_modified_date"),
    Category.BANK_STATEMENT: ("account_last4",),
    Category.CONTRACT: ("term_length",),
    Category.DOCUMENT: ("document_date", "description"),
    Category.IMAGE: ("variant", "capture_date"),
    Category.SCREENSHOT: ("capture_date",),
    Category.APPLICATION: ("version", "platform"),
    Category.ARCHIVE: (),
    Category.VIDEO: ("duration", "content_date"),
    Category.AUDIO: ("artist", "duration", "recording_date"),
}

# Categories that never call a provider in v1 (§9 of the design) — fully deterministic,
# either because every field has a real deterministic source (Archive) or because no
# deterministic/judgment source exists at all yet for some fields (Video's duration/
# content_date, §9A) and the rest is filename-derived best-effort (never a guess about
# file *content*, just the literal filename — §19).
_DETERMINISTIC_ONLY_CATEGORIES = frozenset(
    {Category.ARCHIVE, Category.APPLICATION, Category.VIDEO, Category.AUDIO}
)

# Categories with one deterministic field (capture_date, via EXIF — tier 2 of §9A) and
# one or more judgment fields (vision-only, no text extraction attempted — §6 step 6).
_IMAGE_FAMILY_CATEGORIES = frozenset({Category.IMAGE, Category.SCREENSHOT})

# Everything else (Invoice, Resume, Bank Statement, Contract, Document) is entirely
# judgment-sourced via the text/vision deep pass (§6 step 5).


def required_fields(category: Category) -> Tuple[str, ...]:
    """Public accessor for a category's required field names (§7)."""
    return REQUIRED_FIELDS.get(category, ())


def optional_fields(category: Category) -> Tuple[str, ...]:
    """Public accessor for a category's optional field names (§7)."""
    return OPTIONAL_FIELDS.get(category, ())


def all_fields_for(category: Category) -> Tuple[str, ...]:
    """Every field name (required + optional) a category's `extracted_metadata`
    should have keys for — the closed taxonomy a provider's answer is validated
    against (§7's "prohibited metadata" rule, §12)."""
    return required_fields(category) + optional_fields(category)


def is_extraction_complete(category: Category, extracted_metadata: dict) -> bool:
    """Mechanical definition from §7: incomplete iff any required field is still
    null. Not a judgment call — exposed as its own function so both the Engine and
    tests can compute it identically, once."""
    return all(
        extracted_metadata.get(field_name) is not None
        for field_name in required_fields(category)
    )


# --- Deterministic helpers specific to this module (Application/Video filename
# parsing). Archive's summarize_contents() and Audio's read_audio_tags() live in
# core/archive.py and core/media.py respectively — these two are small enough, and
# specific enough to Module 03's own naming-adjacent logic, that they stay here
# rather than in a new core/ file (§16 only names core/archive.py and core/media.py
# as new files; filename parsing was never called out as needing its own module). ---

_VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)+$")
_PLATFORM_KEYWORDS = {
    "mac": "Mac", "macos": "Mac", "osx": "Mac",
    "win": "Windows", "windows": "Windows",
}


def _parse_application_filename(path: str) -> dict:
    """Best-effort app_name/version/platform from an installer's filename alone
    (§9's "Deterministic only in v1 — filename-pattern parsing, no provider call").
    Never raises — an unparseable filename just yields app_name=the filename stem and
    version/platform=None, which is an honest "found the name, not the rest," not a
    fabrication (§7's "never fabricate" rule)."""
    stem = Path(path).stem
    tokens = [token for token in re.split(r"[_\-\s]+", stem) if token]
    version = None
    platform = None
    name_tokens = []
    for token in tokens:
        if version is None and _VERSION_PATTERN.match(token):
            version = token
            continue
        lowered = token.lower()
        if platform is None and lowered in _PLATFORM_KEYWORDS:
            platform = _PLATFORM_KEYWORDS[lowered]
            continue
        name_tokens.append(token)
    app_name = " ".join(name_tokens).strip() or stem
    return {"app_name": app_name, "version": version, "platform": platform}


def _parse_video_filename(path: str) -> dict:
    """Video's `description` is filename-derived only in v1 (§9 — moved to the
    deterministic column during the design's third review: no provider call is ever
    made for Video). `duration`/`content_date` are unconditionally None — no tier-1/
    tier-3 timestamp source exists yet (§9A) and no video-tag/duration library is
    approved (§16/§27)."""
    return {"description": Path(path).stem, "duration": None, "content_date": None}


def _extract_audio_fields(path: str) -> dict:
    """Audio's deterministic pass (§9): embedded ID3-style tags via core/media.py's
    read_audio_tags() when the file can be read as audio at all, with a filename
    fallback for track_title specifically when no title tag exists — the same
    "literal, unaltered filename, not a guess" reasoning as Video's description
    (§19)."""
    tags = read_audio_tags(path)
    if tags.get("track_title") is None:
        tags["track_title"] = Path(path).stem
    return tags


# --- Provider boundary: the judgment/deep-pass contract. Design:
# Build-out/03 Metadata Extraction/Module 03 Design.md §23 (frozen). Deliberately a
# separate set of classes from pipeline/classification.py's — see this file's
# docstring and design §21 for why that's convention-following, not duplication. ---


@dataclass
class MetadataExtractionRequest:
    """What a MetadataExtractionProvider needs to answer a variable set of named
    fields for one file. `fields_requested` names only the judgment-dependent fields
    still outstanding for this category (§8) — never the fields a deterministic pass
    already filled, and never a field outside the category's taxonomy (§7)."""
    file_id: str
    path: str
    extracted_text: Optional[str]
    mode: Literal["text", "vision"]
    mime_type: Optional[str] = None
    fields_requested: List[str] = field(default_factory=list)


@dataclass
class ProviderMetadata:
    """Observability metadata about how a provider call went — kept separate from the
    raw field answers, same rationale as classification.py's identically-named,
    independently-defined class (design §21: no cross-import, deliberate convention
    reuse)."""
    provider_name: str
    model: Optional[str] = None
    provider_version: Optional[str] = None
    latency_ms: Optional[int] = None
    reasoning: Optional[str] = None


@dataclass
class ProviderResponse:
    """What MetadataExtractionProvider.extract() actually returns: the provider's raw
    field answers (`fields`, keyed by field name — only meaningful for the keys in
    the request's `fields_requested`, though the Engine validates this rather than
    trusting it, §12) plus the metadata about the call that produced it."""
    fields: Dict[str, object]
    metadata: ProviderMetadata


class ProviderUnavailableError(Exception):
    """Raised when a provider can't be reached/invoked at all — meaningful for a
    future network-based provider; not a real case for ClaudeLiveExtractor, which is
    always "available" by construction. Module 03's own exception type — not imported
    from pipeline/classification.py (design §21)."""


class ProviderError(Exception):
    """Raised when a provider was invoked but failed to produce a usable answer on
    its own terms. Module 03's own exception type — not imported from
    pipeline/classification.py (design §21)."""


class MetadataExtractionProvider(ABC):
    """The provider performs structured extraction only — nothing else. It does not
    decide which fields are deterministic (the caller already resolved those before
    building the request). It does not decide fallback behavior — if it can't answer,
    it raises (ProviderUnavailableError/ProviderError); MetadataExtractionEngine is
    what catches that and applies the fallback strategy (design §12)."""

    @abstractmethod
    def extract(self, request: MetadataExtractionRequest) -> ProviderResponse:
        """Extract the requested fields for one file and return the answer plus call
        metadata."""
        raise NotImplementedError


class ClaudeLiveExtractor(MetadataExtractionProvider):
    """V1's concrete provider. Fulfills extract() with no network call at all: Claude,
    already driving the run, reads the file and constructs the ProviderResponse
    directly — exactly the same documented-placeholder pattern as
    pipeline/classification.py's ClaudeLiveClassifier (see that class's docstring and
    src/README.md's "How Claude fits into code").

    All automated testing of MetadataExtractionEngine and Module 03's orchestration
    uses a FakeMetadataExtractionProvider test double instead (see
    test_metadata.py), exactly as the design's Test Strategy (§20) specifies.
    """

    def extract(self, request: MetadataExtractionRequest) -> ProviderResponse:
        raise NotImplementedError(
            "ClaudeLiveExtractor.extract() is fulfilled live by Claude during an "
            "agent-driven run, not by autonomous code — see this class's docstring "
            "and src/README.md's 'How Claude fits into code'. Tests should use a "
            "fake/stub MetadataExtractionProvider instead of instantiating this "
            "class."
        )


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


_MAX_ERROR_DETAIL_LENGTH = 300


def _sanitize_error(exc: Exception) -> str:
    """Turn a caught exception into a short, safe-to-log diagnostic string. Adopted
    from day one (design §12/§21 — "built in from the beginning rather than
    rediscovering the same gap Module 02's release audit found"), not reinvented:
    identical shape and reasoning to pipeline/classification.py's helper of the same
    name, but this module's own copy (no cross-module import, §21)."""
    message = f"{type(exc).__name__}: {exc}"
    if len(message) > _MAX_ERROR_DETAIL_LENGTH:
        message = message[:_MAX_ERROR_DETAIL_LENGTH] + "...(truncated)"
    return message


@dataclass
class EngineResult:
    """Everything MetadataExtractionEngine.extract_file() hands back to Module 03's
    batch orchestration for one file — enough to populate FileRecord.extracted_metadata
    and write a complete `extract_metadata` action-log entry (design §13) without
    Module 03 needing to know anything about how the answer was reached."""
    extracted_metadata: dict
    mode: Literal["deterministic", "text", "vision", "mixed"]
    processing_time_ms: int
    extraction_complete: bool = True
    provider_metadata: Optional[ProviderMetadata] = None
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    error_detail: Optional[str] = None
    redacted_fields: List[str] = field(default_factory=list)


class MetadataExtractionEngine:
    """Per-file decision-making, exactly as frozen (design §6/§8/§9/§9A/§12/§18/§23):
    looks up the required/optional field set for a record's category, computes every
    deterministic field before considering a provider call at all, invokes the
    configured MetadataExtractionProvider only for genuinely judgment-dependent
    fields, validates whatever comes back (including the Bank Statement
    `account_last4` digit-count check, §18), and owns the fallback strategy when a
    provider is unavailable or returns something untrustworthy. The provider itself
    never makes any of these decisions.
    """

    def __init__(self, provider: MetadataExtractionProvider):
        self._provider = provider

    def extract_file(self, record: FileRecord) -> EngineResult:
        """Extract metadata for one already-classified record. Callers (Module 03's
        batch orchestration) are responsible for only calling this on records with
        status == "discovered" and a real, non-Unknown category (design §3/§11) —
        the Engine itself does not re-check this, matching
        ClassificationEngine.classify_file()'s precedent of trusting its caller's
        filtering."""
        start = time.monotonic()
        category = record.category
        path = record.current_path
        fields = all_fields_for(category)

        if category in _DETERMINISTIC_ONLY_CATEGORIES:
            return self._extract_deterministic_only(category, path, fields, start)

        if category in _IMAGE_FAMILY_CATEGORIES:
            return self._extract_image_family(
                category, path, record.file_id, fields, start
            )

        # Invoice, Resume, Bank Statement, Contract, Document — entirely
        # judgment-sourced via the text/vision deep pass.
        return self._extract_text_bearing(category, path, record.file_id, fields, start)

    # --- Archive / Application / Video / Audio: no provider call, ever (§9) ---

    def _extract_deterministic_only(self, category: Category, path: str,
                                      fields: Tuple[str, ...], start: float) -> EngineResult:
        try:
            if category == Category.ARCHIVE:
                # A genuinely empty (but successfully opened) archive yields "" —
                # a found, honest value distinct from None ("couldn't read this
                # archive at all"). Collapsing the two into the same null would
                # make a rare-but-valid empty zip indistinguishable from a
                # corrupted one, both to Module 06's confidence math and to a
                # human reading the action log.
                values = {"contents_summary": summarize_contents(path)}
            elif category == Category.APPLICATION:
                values = _parse_application_filename(path)
            elif category == Category.VIDEO:
                values = _parse_video_filename(path)
            else:  # Category.AUDIO
                values = _extract_audio_fields(path)
        except Exception as exc:
            extracted = {field_name: None for field_name in fields}
            return EngineResult(
                extracted_metadata=extracted,
                mode="deterministic",
                processing_time_ms=_elapsed_ms(start),
                extraction_complete=is_extraction_complete(category, extracted),
                fallback_used=True,
                fallback_reason="extraction_failed",
                error_detail=_sanitize_error(exc),
            )
        extracted = {field_name: values.get(field_name) for field_name in fields}
        return EngineResult(
            extracted_metadata=extracted,
            mode="deterministic",
            processing_time_ms=_elapsed_ms(start),
            extraction_complete=is_extraction_complete(category, extracted),
        )

    # --- Image / Screenshot: capture_date deterministic (EXIF, §9A tier 2) + a
    # vision-only provider call for the remaining judgment field(s) ---

    def _extract_image_family(self, category: Category, path: str, file_id: str,
                                fields: Tuple[str, ...], start: float) -> EngineResult:
        values: dict = {}
        try:
            values["capture_date"] = get_capture_date(path)
        except Exception:
            # A single-field failure (§12) — capture_date stays None, the rest of
            # this record is unaffected. Never substitutes a filesystem timestamp
            # here (§9A: capture_date is tier-2-only, never tier-4).
            values["capture_date"] = None

        judgment_fields = [f for f in fields if f != "capture_date"]
        request = MetadataExtractionRequest(
            file_id=file_id, path=path, extracted_text=None, mode="vision",
            fields_requested=judgment_fields,
        )

        provider_start = time.monotonic()
        try:
            response = self._provider.extract(request)
        except (ProviderUnavailableError, ProviderError) as exc:
            return self._fallback_result(
                category, fields, values, "vision", start,
                fallback_reason="provider_exception", error_detail=_sanitize_error(exc),
            )
        except Exception as exc:
            return self._fallback_result(
                category, fields, values, "vision", start,
                fallback_reason="provider_exception", error_detail=_sanitize_error(exc),
            )
        response.metadata.latency_ms = _elapsed_ms(provider_start)

        validated, redacted = self._validate_and_merge(category, judgment_fields, response.fields)
        values.update(validated)

        extracted = {field_name: values.get(field_name) for field_name in fields}
        return EngineResult(
            extracted_metadata=extracted,
            mode="mixed",  # always both a deterministic (capture_date) and a
                            # judgment field for these two categories (§13)
            processing_time_ms=_elapsed_ms(start),
            extraction_complete=is_extraction_complete(category, extracted),
            provider_metadata=response.metadata,
            redacted_fields=redacted,
        )

    # --- Invoice / Resume / Bank Statement / Contract / Document: entirely
    # judgment-sourced, text-or-vision deep pass (§6 step 5, mirrors
    # ClassificationEngine's _extract() exactly) ---

    def _extract_text_bearing(self, category: Category, path: str, file_id: str,
                                fields: Tuple[str, ...], start: float) -> EngineResult:
        try:
            extracted_text, mode, has_content = self._extract_text_or_vision(path)
        except Exception as exc:
            extracted = {field_name: None for field_name in fields}
            return EngineResult(
                extracted_metadata=extracted,
                mode="text",
                processing_time_ms=_elapsed_ms(start),
                extraction_complete=is_extraction_complete(category, extracted),
                fallback_used=True,
                fallback_reason="extraction_failed",
                error_detail=_sanitize_error(exc),
            )

        if not has_content:
            extracted = {field_name: None for field_name in fields}
            return EngineResult(
                extracted_metadata=extracted,
                mode=mode,
                processing_time_ms=_elapsed_ms(start),
                extraction_complete=is_extraction_complete(category, extracted),
            )

        request = MetadataExtractionRequest(
            file_id=file_id, path=path, extracted_text=extracted_text, mode=mode,
            fields_requested=list(fields),
        )

        provider_start = time.monotonic()
        try:
            response = self._provider.extract(request)
        except (ProviderUnavailableError, ProviderError) as exc:
            return self._fallback_result(
                category, fields, {}, mode, start,
                fallback_reason="provider_exception", error_detail=_sanitize_error(exc),
            )
        except Exception as exc:
            return self._fallback_result(
                category, fields, {}, mode, start,
                fallback_reason="provider_exception", error_detail=_sanitize_error(exc),
            )
        response.metadata.latency_ms = _elapsed_ms(provider_start)

        validated, redacted = self._validate_and_merge(category, fields, response.fields)
        extracted = {field_name: validated.get(field_name) for field_name in fields}
        return EngineResult(
            extracted_metadata=extracted,
            mode=mode,
            processing_time_ms=_elapsed_ms(start),
            extraction_complete=is_extraction_complete(category, extracted),
            provider_metadata=response.metadata,
            redacted_fields=redacted,
        )

    def _extract_text_or_vision(self, path: str) -> Tuple[Optional[str], str, bool]:
        """Returns (extracted_text, mode, has_content) — byte-for-byte the same
        dispatch as pipeline/classification.py's ClassificationEngine._extract(),
        re-run independently rather than reused (design §21: Module 02 never
        persists extracted text/rendered bytes anywhere for Module 03 to reuse)."""
        extension = Path(path).suffix.lower()
        if extension == ".pdf":
            text = _pdf_extract_text(path)
            if text is not None:
                return text, "text", True
            render_page_as_image(path)  # fail-fast: raises if truly unrenderable
            return None, "vision", True
        text = _text_extract_text(path)
        return text, "text", text is not None

    def _validate_and_merge(self, category: Category, fields_requested,
                              raw_fields: Optional[Dict[str, object]]
                              ) -> Tuple[dict, List[str]]:
        """The Engine is the trust boundary between a provider's answer and
        `extracted_metadata` (design §12/§18) — mirrors
        ClassificationEngine._validate_category()'s role, generalized to a variable
        set of named fields instead of one fixed enum:

        - Any key not in `fields_requested` is dropped, never merged in — the closed-
          taxonomy privacy control (§7/§18), not just a data-integrity check.
        - Any value that isn't a plain str/int/float (JSON-safe, roughly-typed) is
          treated as not-found, not coerced or guessed (§12). `bool` is explicitly
          excluded even though Python's `bool` is technically an `int` subclass: no
          field in the taxonomy (§7) is defined as boolean, so a `True`/`False`
          answer is always a wrong-type response, never a legitimate value — treated
          as not-found like any other type mismatch (implementation audit F1, this
          module's version being audited for the first time). If a future category
          ever defines a genuinely boolean field, this exclusion would need revisiting
          alongside that taxonomy change — not a case that exists today.
        - Bank Statement's `account_last4` additionally passes the exact digit-count
          check (§18): more than 4 digits -> redacted to None, name (never value)
          recorded in `redacted_fields`; 4 digits or fewer (including empty) ->
          passes through unchanged.
        """
        validated: dict = {}
        for key, value in (raw_fields or {}).items():
            if key not in fields_requested:
                continue
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (str, int, float))
            ):
                continue
            validated[key] = value

        redacted: List[str] = []
        if category == Category.BANK_STATEMENT and "account_last4" in validated:
            value = validated["account_last4"]
            if value is not None:
                digits = "".join(ch for ch in str(value) if ch.isdigit())
                if len(digits) > 4:
                    validated["account_last4"] = None
                    redacted.append("account_last4")
        return validated, redacted

    def _fallback_result(self, category: Category, fields: Tuple[str, ...],
                          existing_values: dict, mode: str, start: float,
                          fallback_reason: str, error_detail: Optional[str]) -> EngineResult:
        """Shared by every provider-failure path (design §12): every judgment-
        dependent field for the affected call stays null; any deterministic value
        already found for this record (e.g. Image/Screenshot's capture_date) is
        preserved, not discarded, since a provider failure doesn't undo work a
        deterministic pass already completed."""
        extracted = {field_name: existing_values.get(field_name) for field_name in fields}
        return EngineResult(
            extracted_metadata=extracted,
            mode=mode,
            processing_time_ms=_elapsed_ms(start),
            extraction_complete=is_extraction_complete(category, extracted),
            fallback_used=True,
            fallback_reason=fallback_reason,
            error_detail=error_detail,
        )


# --- Module 03 batch orchestration: filtering, persistence, logging. This is the
# only layer that touches storage/*.py or Runtime/Logs directly — the Engine and
# Provider never do (design §5/§13). ---


def extract_metadata_batch(records: List[FileRecord],
                            provider: Optional[MetadataExtractionProvider] = None
                            ) -> List[FileRecord]:
    """Extract metadata for every already-classified record, persist the results, and
    log one `extract_metadata` action-log entry per file. Mirrors classify_batch()'s
    shape exactly: same records in, same records back out, enriched in place.

    Records with status != "discovered", or category is None/Category.UNKNOWN, are
    passed through completely untouched — extracted_metadata stays at its FileRecord
    default ({}). See design §3/§5/§11 for why Module 03 never attempts extraction on
    a file that was never meaningfully classified.

    `provider` defaults to ClaudeLiveExtractor() (v1's only real provider — design
    §16's "simple default in v1"). Tests inject a fake provider instead of relying on
    this default.
    """
    engine = MetadataExtractionEngine(provider or ClaudeLiveExtractor())

    for record in records:
        if record.status != "discovered" or record.category in (None, Category.UNKNOWN):
            continue

        try:
            engine_result = engine.extract_file(record)
        except Exception as unexpected_error:
            # Outer safety net: MetadataExtractionEngine already catches every
            # failure mode it knows about internally and returns a normal
            # EngineResult for all of them — this branch is only reached if
            # something entirely unanticipated slips through, and even then a
            # single bad file must never abort the batch (same resilience pattern
            # as scan_source()/classify_batch()).
            append_action_log(
                batch_id=record.batch_id,
                file_id=record.file_id,
                action="error",
                from_path=record.current_path,
                details={"stage": "metadata_extraction", "error": str(unexpected_error)},
            )
            continue

        record.extracted_metadata = engine_result.extracted_metadata
        save_file_record(record)

        fields = all_fields_for(record.category)
        fields_extracted = [
            f for f in fields if engine_result.extracted_metadata.get(f) is not None
        ]
        fields_missing = [
            f for f in fields if engine_result.extracted_metadata.get(f) is None
        ]

        details = {
            "category": record.category.value,
            "fields_extracted": fields_extracted,
            "fields_missing": fields_missing,
            "mode": engine_result.mode,
            "processing_time_ms": engine_result.processing_time_ms,
            "extraction_complete": engine_result.extraction_complete,
            "fallback_used": engine_result.fallback_used,
            "fallback_reason": engine_result.fallback_reason,
            "redacted_fields": engine_result.redacted_fields,
        }
        if engine_result.provider_metadata is not None:
            details["provider_metadata"] = asdict(engine_result.provider_metadata)
        if engine_result.error_detail is not None:
            details["error_detail"] = engine_result.error_detail

        append_action_log(
            batch_id=record.batch_id,
            file_id=record.file_id,
            action="extract_metadata",
            from_path=record.current_path,
            details=details,
        )

    return records
