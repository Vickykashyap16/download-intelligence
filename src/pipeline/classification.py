"""
Classification (Module 02). HYBRID module: deterministic passes + judgment (via
ClassificationEngine -> ClassificationProvider) for the deep pass.

Architecture: Build-out/02 Classification/Module 02 Design.md (frozen)
Rules: Rules/Classification Rules.md, Rules/Confidence Rules.md (implemented directly —
no generated config in v1, see CHANGELOG.md)

This module is layered exactly as frozen:
  Module 02 (batch orchestration, this file's classify_batch())
        -> ClassificationEngine (per-file decision-making)
              -> ClassificationProvider (raw classification call only)

Deterministic functions in this section are pure code — no provider/Claude involved.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from src.core.images import get_dimensions, matches_screen_resolution
from src.core.pdf import is_password_protected
from src.core.pdf import extract_text as _pdf_extract_text
from src.core.pdf import render_page_as_image
from src.core.text import detect_language
from src.core.text import extract_text as _text_extract_text
from src.models.classification import Category, ClassificationSignals
from src.models.file_record import FileRecord
from src.storage.database import save_file_record
from src.storage.runtime_io import append_action_log

# --- Rules/Classification Rules.md Pass 1, implemented directly (see src/README.md
# "Why config/ is nearly empty"). Keep in sync with that document by hand. ---
#
# Archive set (.zip/.rar/.7z/.tar/.gz) intentionally matches Rules/Classification
# Rules.md's full Pass 1 list, not just Module 01's current SUPPORTED_EXTENSIONS
# (which only ingests .zip today — see watch_ingest.py). Found and fixed during the
# 2026-07-06 release audit: .tar was missing from this map entirely, an undetected
# drift against the Rules doc (see CHANGELOG.md and Release/Module02/RELEASE_AUDIT.md,
# F4). Deliberate decision: .rar/.7z/.gz/.tar stay mapped here ahead of Module 01
# adding them, so the moment Module 01's SUPPORTED_EXTENSIONS catches up to the full
# Rules taxonomy, Module 02 already routes them correctly with no follow-up change
# needed — forward-compatible, not dead code masquerading as coverage. See
# test_extension_category_map_matches_rules_taxonomy() for the regression test that
# now guards this against silently drifting again.

_EXTENSION_CATEGORY_MAP = {
    ".exe": Category.APPLICATION, ".dmg": Category.APPLICATION,
    ".pkg": Category.APPLICATION, ".msi": Category.APPLICATION,
    ".zip": Category.ARCHIVE, ".rar": Category.ARCHIVE,
    ".7z": Category.ARCHIVE, ".tar": Category.ARCHIVE, ".gz": Category.ARCHIVE,
    ".mp4": Category.VIDEO, ".mov": Category.VIDEO,
    ".mkv": Category.VIDEO, ".avi": Category.VIDEO,
    ".mp3": Category.AUDIO, ".wav": Category.AUDIO,
    ".m4a": Category.AUDIO, ".flac": Category.AUDIO,
}

# Image-family extensions that need the Screenshot-vs-Image split rather than a
# direct category. Matches Module 01's SUPPORTED_EXTENSIONS image group exactly
# (src/pipeline/watch_ingest.py) — Rules/Classification Rules.md also lists .heic,
# which Module 01 doesn't currently ingest, so it can't reach this module in practice;
# noted rather than silently dropped.
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff"}

# Text-bearing extensions that need the deep pass. Rules/Classification Rules.md also
# lists .doc/.rtf, neither of which is in Module 01's SUPPORTED_EXTENSIONS, so — same
# as .heic above — they can't actually arrive here today.
_TEXT_BEARING_EXTENSIONS = {".pdf", ".docx", ".txt"}

_SCREENSHOT_FILENAME_MARKERS = ("screenshot", "screen shot", "cleanshot", "snip")


def classify_by_extension(path: str) -> Optional[Category]:
    """Pass 1 (deterministic): returns a definitive Category for extensions where the
    extension alone is 100% sufficient (Application/Archive/Video/Audio). Returns None
    for anything needing a closer look — image-family extensions (see
    needs_screenshot_split()) or text-bearing extensions (a deep pass). None here does
    NOT by itself mean Unknown — the caller (ClassificationEngine) decides what to do
    next; a None that doesn't match any further routing becomes Unknown there, not here.
    """
    extension = Path(path).suffix.lower()
    return _EXTENSION_CATEGORY_MAP.get(extension)


def needs_screenshot_split(path: str) -> bool:
    """True for image-family extensions, meaning the Screenshot-vs-Image heuristic
    (classify_screenshot_or_image(), below) needs to run."""
    return Path(path).suffix.lower() in _IMAGE_EXTENSIONS


def is_text_bearing(path: str) -> bool:
    """True for extensions that need the text/vision deep pass rather than a
    deterministic answer."""
    return Path(path).suffix.lower() in _TEXT_BEARING_EXTENSIONS


def classify_screenshot_or_image(path: str) -> Category:
    """The actual Screenshot-vs-Image split (Rules/Classification Rules.md): Screenshot
    if the filename looks like one, OR dimensions match a common screen resolution.
    Otherwise Image. Fully deterministic — no provider call. Only meaningful for paths
    where needs_screenshot_split() is True; callers are expected to check that first.

    Post-freeze correction (PT-002, 2026-07-20 — see
    `Build-out/02 Classification/Module 02 Post-Freeze Design Correction — PT-002.md`
    for the full design record, `Governance/FROZEN_MODULE_CHANGE_POLICY.md` for the
    process this change was made under): a third condition — "no camera EXIF data
    present" — previously stood as an independent, sufficient trigger for Screenshot.
    Real-world validation (`PATTERN_TRACKER.md` PT-002, Confirmed Pattern across two
    independent runs) directly confirmed this negative signal is not specific to
    screenshots: scanned document photos, product/marketing graphics, AI-generated
    images, and ordinary personal photos re-encoded or EXIF-stripped by messaging apps
    all lack camera EXIF just as often as a real screen capture does, and none of them
    triggered the filename-marker or resolution-match conditions either — so the old
    third condition alone routed all of them to Screenshot before this function's own
    documented "Otherwise -> Image" default was ever reached. Removed rather than
    reweighted: no other cheap, deterministic corroborating signal exists at this
    layer (this split is deliberately provider-free — see design), so requiring EXIF
    absence to co-occur with something else was not achievable without either
    reintroducing the same over-broad behavior in a different shape or crossing into
    content-understanding territory this layer is not meant to do.

    Disclosed trade-off (not eliminated, carried forward — see the design record's
    Risk Assessment and Acceptance Criteria): a genuine screenshot with neither a
    marker filename nor dimensions matching `_COMMON_SCREEN_RESOLUTIONS` (e.g.
    cropped, resized, or renamed before reaching Downloads) now defaults to Image
    rather than Screenshot. This is a new, bounded, disclosed possibility, not a
    silently accepted one — `has_camera_metadata()` remains correctly implemented and
    available in `src/core/exif.py`; it is simply no longer consulted here as an
    independent, sufficient signal.
    """
    if _looks_like_screenshot_filename(Path(path).name):
        return Category.SCREENSHOT
    if matches_screen_resolution(get_dimensions(path)):
        return Category.SCREENSHOT
    return Category.IMAGE


def _looks_like_screenshot_filename(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in _SCREENSHOT_FILENAME_MARKERS)


def is_locked(path: str) -> bool:
    """True if this file can't be read due to password protection. Only meaningful for
    PDFs in v1 — Module 01's other text-bearing extensions (.docx/.txt) have no such
    concept, so this returns False for them rather than attempting a check that
    doesn't apply."""
    if Path(path).suffix.lower() == ".pdf":
        return is_password_protected(path)
    return False


def detect_non_english(text: str) -> Tuple[bool, Optional[str]]:
    """Deterministic non-English signal from already-extracted text. Returns
    (non_english_detected, detected_language) — both default-shaped for
    ClassificationSignals's matching fields. A language that can't be determined at
    all (None from core/text.py's detect_language()) is treated as "not flagged" —
    absence of a confident signal isn't the same as a positive non-English finding."""
    language = detect_language(text)
    non_english_detected = language is not None and language != "en"
    return non_english_detected, language


# --- Provider boundary: the judgment/deep-pass contract. Design:
# Build-out/02 Classification/Module 02 Design.md §25 (frozen). ---


@dataclass
class ClassificationRequest:
    """What a ClassificationProvider needs to make the deep-pass judgment call."""
    file_id: str
    path: str
    extracted_text: Optional[str]     # from core/pdf.py or core/text.py, may be None
    mode: Literal["text", "vision"]
    mime_type: Optional[str] = None


@dataclass
class ClassificationResult:
    """The pure classification answer a provider returns. `category` is deliberately a
    plain str, not the Category enum — providers (especially a future LLM-API
    provider) naturally produce free text; the ClassificationEngine is the trust
    boundary that validates/converts this into a real Category member (see §25's
    "why category stays a plain str at the provider boundary")."""
    category: str
    ambiguous: bool = False
    multi_document_detected: bool = False
    notes: str = ""


@dataclass
class ProviderMetadata:
    """Observability metadata about how a provider call went — kept separate from
    ClassificationResult so "what is this file" and "how/who answered it" don't get
    conflated in one object."""
    provider_name: str
    model: Optional[str] = None
    provider_version: Optional[str] = None
    latency_ms: Optional[int] = None   # measured by ClassificationEngine wrapping the
                                        # call, not self-reported by the provider — see
                                        # design §18 for why this is provider-agnostic
    reasoning: Optional[str] = None    # optional free-text rationale — see design §17
                                        # privacy note before any provider populates this


@dataclass
class ProviderResponse:
    """What ClassificationProvider.classify() actually returns: the answer plus the
    metadata about the call that produced it."""
    result: ClassificationResult
    metadata: ProviderMetadata


class ProviderUnavailableError(Exception):
    """Raised when a provider can't be reached/invoked at all — meaningful for a
    future network-based provider (connection refused, service outage); not a real
    case for ClaudeLiveClassifier, which is always "available" by construction."""


class ProviderError(Exception):
    """Raised when a provider was invoked but failed to produce a usable answer on its
    own terms (e.g. it errored internally, was rate-limited, or rejected the request).
    Distinct from an invalid-but-structurally-present response, which
    ClassificationEngine catches through its own validation, not via this exception."""


class ClassificationProvider(ABC):
    """The provider performs classification only — nothing else. It does not decide
    text-vs-vision mode (the caller already decided that when building the request).
    It does not decide fallback behavior — if it can't classify, it raises
    (ProviderUnavailableError/ProviderError); ClassificationEngine is what catches
    that and applies the fallback strategy (design §11). A provider must never itself
    return something Unknown-like as a way of handling its own failure."""

    @abstractmethod
    def classify(self, request: ClassificationRequest) -> ProviderResponse:
        """Classify one file and return the answer plus call metadata."""
        raise NotImplementedError


class ClaudeLiveClassifier(ClassificationProvider):
    """V1's concrete provider. Fulfills classify() with no network call at all: Claude,
    already driving the run (this is an Automation build type — see CLAUDE.md), reads
    the file and constructs the ProviderResponse directly, exactly matching the
    judgment-module pattern described in src/README.md.

    This is why calling this method as ordinary Python code is not meaningful: the
    "implementation" of the judgment step is Claude's own live reasoning during an
    agent-driven run, not a function body that can execute autonomously. This method
    therefore raises NotImplementedError with a clear explanation, exactly as
    classify_by_extension() did before Module 01 implemented its own real logic — it
    is a documented placeholder, not an unfinished piece of engineering work.

    All automated testing of ClassificationEngine and Module 02's orchestration uses a
    FakeClassificationProvider test double instead (see test_classification.py),
    exactly as the design's Test Strategy (§16) specifies — this is what makes the
    deterministic parts of Module 02 fully testable without ever needing a live Claude
    session in the loop.
    """

    def classify(self, request: ClassificationRequest) -> ProviderResponse:
        raise NotImplementedError(
            "ClaudeLiveClassifier.classify() is fulfilled live by Claude during an "
            "agent-driven run, not by autonomous code — see this class's docstring "
            "and src/README.md's 'How Claude fits into code'. Tests should use a "
            "fake/stub ClassificationProvider instead of instantiating this class."
        )


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


_MAX_ERROR_DETAIL_LENGTH = 300


def _sanitize_error(exc: Exception) -> str:
    """Turn a caught exception into a short, safe-to-log diagnostic string.

    Added during the 2026-07-06 release audit (F3): every fallback path previously
    discarded the actual exception message, leaving the action log with only a fixed
    reason string (e.g. "extraction_failed") and no way to tell a PdfStreamError apart
    from a permissions problem apart from anything else without reproducing the
    failure by hand. This closes that gap.

    Exception messages from this module's dependencies (pdfplumber/pypdf/python-docx/
    PIL) describe file-structure/parsing state — "Stream has ended unexpectedly",
    "cannot identify image file" — not file content. Truncated defensively anyway,
    consistent with the design's existing privacy discipline for provider `reasoning`
    (§17): if a future core/ dependency's exception ever echoes part of a file's
    actual bytes/text, this keeps only a bounded, non-sensitive-by-construction prefix
    in the log rather than an unbounded, unreviewed string.
    """
    message = f"{type(exc).__name__}: {exc}"
    if len(message) > _MAX_ERROR_DETAIL_LENGTH:
        message = message[:_MAX_ERROR_DETAIL_LENGTH] + "...(truncated)"
    return message


@dataclass
class EngineResult:
    """Everything ClassificationEngine.classify_file() hands back to Module 02's
    batch orchestration for one file — enough to populate the FileRecord and write a
    complete `classify` action-log entry (design §12) without Module 02 needing to
    know anything about how the answer was reached."""
    category: Category
    classification_signals: ClassificationSignals
    mode: Literal["deterministic", "text", "vision"]
    processing_time_ms: int
    provider_metadata: Optional[ProviderMetadata] = None
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    error_detail: Optional[str] = None   # sanitized diagnostic string, populated on
                                          # every fallback path that has something to
                                          # say beyond the fixed reason code (added
                                          # 2026-07-06 release audit, F3) — None for
                                          # the normal/success case and for the
                                          # locked-file case (not a failure, a known
                                          # signal; see design §11)


class ClassificationEngine:
    """Per-file decision-making, exactly as frozen (design §6/§8/§11/§25): decides
    deterministic vs. AI-assisted classification, invokes the configured
    ClassificationProvider only when a deterministic answer isn't possible, validates
    whatever comes back, and owns the fallback strategy when a provider is unavailable
    or returns something untrustworthy. The provider itself never makes any of these
    decisions — see ClassificationProvider's docstring.
    """

    def __init__(self, provider: ClassificationProvider):
        self._provider = provider

    def classify_file(self, path: str, file_id: str) -> EngineResult:
        """Classify one file. `path` must be a supported, stable, readable file (the
        caller — Module 02's batch orchestration — is responsible for only calling
        this on records Module 01 marked status == "discovered"; see design §11 for
        why "unreadable" records are never passed to the Engine at all)."""
        start = time.monotonic()

        category = classify_by_extension(path)
        if category is not None:
            return self._deterministic_result(category, start)

        if needs_screenshot_split(path):
            # classify_screenshot_or_image() opens the file (via PIL, for dimensions/
            # EXIF) — a file that vanished, was truncated, or simply isn't real image
            # content despite its extension (e.g. a placeholder/corrupted download)
            # raises here. Integration testing (Tests/Large Batch/, whose .jpg/.png
            # fixtures are synthetic placeholder bytes, not real images) surfaced this
            # as an uncaught path — previously only classify_batch()'s outer safety
            # net kept it from crashing the batch, at the cost of leaving the file
            # entirely unclassified (category stays None, an "error" log entry
            # instead of a real "classify" entry). Wrapped here so unreadable image
            # content degrades the same way every other known failure mode does:
            # Category.UNKNOWN with a real classify log entry, not a silent gap.
            try:
                category = classify_screenshot_or_image(path)
            except Exception as exc:
                return EngineResult(
                    category=Category.UNKNOWN,
                    classification_signals=ClassificationSignals(),
                    mode="deterministic",
                    processing_time_ms=_elapsed_ms(start),
                    fallback_used=True,
                    fallback_reason="unreadable_content",
                    error_detail=_sanitize_error(exc),
                )
            return self._deterministic_result(category, start)

        if is_text_bearing(path):
            return self._classify_text_bearing(path, file_id, start)

        # Recognized by Module 01, but absent from every Rules/Classification
        # Rules.md Pass 1 entry Module 02 knows about — Unknown, no signals. See
        # classify_by_extension()'s docstring for why a None here isn't itself Unknown
        # until it reaches this final, no-further-routing-possible point.
        return self._deterministic_result(Category.UNKNOWN, start)

    def _deterministic_result(self, category: Category, start: float) -> EngineResult:
        return EngineResult(
            category=category,
            classification_signals=ClassificationSignals(),
            mode="deterministic",
            processing_time_ms=_elapsed_ms(start),
        )

    def _classify_text_bearing(self, path: str, file_id: str, start: float) -> EngineResult:
        # The locked-check and the extraction attempt are both "can we even look at
        # this file's content" questions, and both can raise on a genuinely malformed
        # file (e.g. a .pdf that isn't really a PDF at all — confirmed during testing:
        # pypdf's PdfReader raises PdfStreamError on such a file, not just a clean
        # "not encrypted" answer). Both are wrapped in the same boundary so neither can
        # crash classify_file() — see the comment on the except clause below for how
        # this fits the frozen fallback_reason vocabulary.
        try:
            if is_locked(path):
                return EngineResult(
                    category=Category.UNKNOWN,
                    classification_signals=ClassificationSignals(locked=True),
                    mode="text",
                    processing_time_ms=_elapsed_ms(start),
                )
            extracted_text, mode, has_content = self._extract(path)
        except Exception as exc:
            # A genuinely malformed file (is_locked()/core/pdf.py/core/text.py raised)
            # — not one of the three provider-failure fallback reasons from design §11
            # (this happens before any provider is even considered), but handled with
            # the same "never crash the batch, always land on Unknown" discipline.
            # Flagged to the project owner as a small, documented extension of the
            # fallback_reason vocabulary beyond the three named in the frozen design.
            #
            # no_extractable_text=True here (fixed during the 2026-07-06 release audit,
            # F6): a file whose extraction raised is, factually, a file we got no usable
            # text from — exactly the condition this signal exists to capture. Leaving
            # it at its all-default False (as this branch previously did) made the same
            # real-world condition produce a different signal value depending on which
            # failure mode was hit, not on anything true about the file. Category.UNKNOWN's
            # existing hard floor already forced review_required either way (see
            # Rules/Confidence Rules.md), so this was never user-visible — but the signal
            # itself was inaccurate, which matters the moment anything reads
            # classification_signals independent of category. See
            # Release/Module02/RELEASE_AUDIT.md, F6.
            return EngineResult(
                category=Category.UNKNOWN,
                classification_signals=ClassificationSignals(no_extractable_text=True),
                mode="text",
                processing_time_ms=_elapsed_ms(start),
                fallback_used=True,
                fallback_reason="extraction_failed",
                error_detail=_sanitize_error(exc),
            )

        if not has_content:
            # Nothing to send a provider — e.g. a non-PDF text-bearing file with no
            # extractable text at all (no vision fallback exists for those types).
            return EngineResult(
                category=Category.UNKNOWN,
                classification_signals=ClassificationSignals(no_extractable_text=True),
                mode=mode,
                processing_time_ms=_elapsed_ms(start),
            )

        no_extractable_text = extracted_text is None  # True only for the PDF vision case
        non_english_detected, detected_language = (False, None)
        if extracted_text:
            non_english_detected, detected_language = detect_non_english(extracted_text)

        request = ClassificationRequest(
            file_id=file_id, path=path, extracted_text=extracted_text, mode=mode,
        )

        provider_start = time.monotonic()
        try:
            response = self._provider.classify(request)
        except (ProviderUnavailableError, ProviderError) as exc:
            return self._fallback_result(
                mode, start, no_extractable_text, non_english_detected,
                detected_language, fallback_reason="provider_exception",
                error_detail=_sanitize_error(exc),
            )
        except Exception as exc:
            # Any other unexpected exception from a provider is still a provider
            # failure from the Engine's point of view — same fallback treatment,
            # logged with the same reason rather than crashing classify_file().
            return self._fallback_result(
                mode, start, no_extractable_text, non_english_detected,
                detected_language, fallback_reason="provider_exception",
                error_detail=_sanitize_error(exc),
            )
        provider_latency_ms = _elapsed_ms(provider_start)

        validated_category = self._validate_category(response.result.category)
        if validated_category is None:
            # No exception was raised here — the provider answered, but with a
            # category string that doesn't map to a real Category member. Still
            # diagnostically useful to log the actual offending value (this is the
            # provider's own answer, not file content, so no sanitization concern —
            # see F3's error_detail addition, Release/Module02/RELEASE_AUDIT.md).
            return self._fallback_result(
                mode, start, no_extractable_text, non_english_detected,
                detected_language, fallback_reason="invalid_response",
                error_detail=f"unrecognized category from provider: {response.result.category!r}",
            )

        response.metadata.latency_ms = provider_latency_ms
        signals = ClassificationSignals(
            ambiguous=response.result.ambiguous,
            multi_document_detected=response.result.multi_document_detected,
            no_extractable_text=no_extractable_text,
            non_english_detected=non_english_detected,
            detected_language=detected_language,
            locked=False,
        )
        return EngineResult(
            category=validated_category,
            classification_signals=signals,
            mode=mode,
            processing_time_ms=_elapsed_ms(start),
            provider_metadata=response.metadata,
        )

    def _fallback_result(self, mode: str, start: float, no_extractable_text: bool,
                          non_english_detected: bool, detected_language: Optional[str],
                          fallback_reason: str, error_detail: Optional[str] = None) -> EngineResult:
        """Shared by every provider-failure path (design §11): always Category.UNKNOWN,
        no retry, no secondary-provider chain in v1 — see design §11/§24.

        `error_detail` (added 2026-07-06 release audit, F3): optional sanitized
        diagnostic string — the actual exception message or offending value, not just
        the fixed `fallback_reason` code — so a future production incident can be
        root-caused from the action log alone. See _sanitize_error()'s docstring.
        """
        return EngineResult(
            category=Category.UNKNOWN,
            classification_signals=ClassificationSignals(
                no_extractable_text=no_extractable_text,
                non_english_detected=non_english_detected,
                detected_language=detected_language,
            ),
            mode=mode,
            processing_time_ms=_elapsed_ms(start),
            fallback_used=True,
            fallback_reason=fallback_reason,
            error_detail=error_detail,
        )

    def _extract(self, path: str) -> Tuple[Optional[str], str, bool]:
        """Returns (extracted_text, mode, has_content).

        - PDF with extractable text -> (text, "text", True)
        - PDF with no extractable text but a renderable page -> (None, "vision", True)
        - Non-PDF text-bearing file with text -> (text, "text", True)
        - Non-PDF text-bearing file with no text -> (None, "text", False)

        Note (implementation-time finding, not fixed here): the frozen
        ClassificationRequest contract (design §25) carries `path`/`mode`/
        `extracted_text` but no rendered image bytes. For v1's live-judgment provider
        this is fine — Claude has direct file access and can look at `path` itself
        when mode == "vision". A future network-based vision provider would need
        actual image bytes passed some other way; this method only validates that the
        page *can* be rendered (a fail-fast check via render_page_as_image()) without
        threading the bytes anywhere yet. Flagged for whoever builds that provider.
        """
        extension = Path(path).suffix.lower()
        if extension == ".pdf":
            text = _pdf_extract_text(path)
            if text is not None:
                return text, "text", True
            render_page_as_image(path)  # fail-fast: raises if truly unrenderable
            return None, "vision", True
        text = _text_extract_text(path)
        return text, "text", text is not None

    @staticmethod
    def _validate_category(raw_category: str) -> Optional[Category]:
        """The Engine is the trust boundary between a provider's free-text answer and
        the internal Category enum (design §25) — an unrecognized string is exactly
        the "invalid_response" fallback case, not a crash."""
        try:
            return Category(raw_category)
        except ValueError:
            return None


# --- Module 02 batch orchestration: filtering, persistence, logging. This is the only
# layer that touches storage/*.py or Runtime/Logs directly — ClassificationEngine and
# ClassificationProvider never do (design §5/§13). ---


def classify_batch(records: List[FileRecord],
                    provider: Optional[ClassificationProvider] = None) -> List[FileRecord]:
    """Classify every record Module 01 discovered, persist the results, and log one
    `classify` action-log entry per file. Mirrors Module 01's build_ingest_queue()
    shape: same records in, same records back out, enriched in place.

    Records with status != "discovered" (Module 01's "unreadable" files) are passed
    through completely untouched — category/classification_signals stay None. See
    design §11 for why this is deliberately different from Category.UNKNOWN.

    `provider` defaults to ClaudeLiveClassifier() (v1's only real provider — design
    §24/§25's "simple default, not a config system"). Tests inject a fake provider
    instead of relying on this default.
    """
    engine = ClassificationEngine(provider or ClaudeLiveClassifier())

    for record in records:
        if record.status != "discovered":
            continue

        try:
            engine_result = engine.classify_file(record.current_path, record.file_id)
        except Exception as unexpected_error:
            # Outer safety net: ClassificationEngine already catches every failure
            # mode it knows about (locked files, extraction errors, unreadable image
            # content, provider exceptions, invalid responses) internally and returns
            # a normal EngineResult for all of them — this branch is only reached if
            # something entirely unanticipated slips through (e.g. a record whose
            # current_path is malformed in a way that breaks path handling itself,
            # before any of the Engine's own routing even begins), and even then a
            # single bad file must never abort the batch (same resilience pattern as
            # Module 01's scan_source()).
            append_action_log(
                batch_id=record.batch_id,
                file_id=record.file_id,
                action="error",
                from_path=record.current_path,
                details={"stage": "classification", "error": str(unexpected_error)},
            )
            continue

        record.category = engine_result.category
        record.classification_signals = engine_result.classification_signals
        save_file_record(record)

        details = {
            "category": engine_result.category.value,
            "signals": asdict(engine_result.classification_signals),
            "mode": engine_result.mode,
            "processing_time_ms": engine_result.processing_time_ms,
            "fallback_used": engine_result.fallback_used,
            "fallback_reason": engine_result.fallback_reason,
        }
        if engine_result.provider_metadata is not None:
            details["provider_metadata"] = asdict(engine_result.provider_metadata)
        if engine_result.error_detail is not None:
            details["error_detail"] = engine_result.error_detail

        append_action_log(
            batch_id=record.batch_id,
            file_id=record.file_id,
            action="classify",
            from_path=record.current_path,
            details=details,
        )

    return records
