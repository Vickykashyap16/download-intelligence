"""
Claude API provider (TD-01 v0.9). Design:
`Build-out/02 Classification/TD-01 Provider Architecture — Design Package.md`
§4 (v0.9 recommendation) / §7 (compatibility analysis).

Real, non-interactive implementations of `ClassificationProvider`
(`src/pipeline/classification.py`) and `MetadataExtractionProvider`
(`src/pipeline/metadata.py`) that call the Claude API over the network —
unlike `ClaudeLiveClassifier`/`ClaudeLiveExtractor`, which are documented
placeholders that only "execute" inside a live, human-driven Claude
conversation. Registers both classes into `src.providers.registry` under the
key `"claude"` as an import-time side effect (see that module's docstring),
so importing this file is what activates the provider — `src/main.py` does
this once, at the top of the file.

Opt-in only, by construction of the surrounding system, not by anything in
this file itself: `main.py`'s default-resolution logic only ever calls
`resolve_classification_provider()`/`resolve_extraction_provider()` when
`ai_provider_consent: true` is set in `src/config/sources.yaml` (written only
by `python -m src.cli provider enable`'s explicit confirmation flow — see
`cli.py`). This file has no opinion about consent; it is a provider
implementation, not a policy — consistent with `ClassificationProvider`'s own
existing docstring ("the provider performs classification only — nothing
else... does not decide fallback behavior").

Never called by any automated test with a real network request — every test
in `test_claude_provider.py` mocks the `anthropic` client, matching this
project's existing "tests never depend on a live provider" convention
(`ClaudeLiveClassifier`'s own docstring makes the same point for the
interactive-session placeholder).
"""

import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic

from src.core.pdf import render_page_as_image
from src.models.classification import Category
from src.pipeline.classification import (
    ClassificationProvider,
    ClassificationRequest,
    ClassificationResult,
)
from src.pipeline.classification import ProviderError as ClassificationProviderError
from src.pipeline.classification import ProviderMetadata as ClassificationProviderMetadata
from src.pipeline.classification import ProviderResponse as ClassificationProviderResponse
from src.pipeline.classification import (
    ProviderUnavailableError as ClassificationProviderUnavailableError,
)
from src.pipeline.metadata import MetadataExtractionProvider, MetadataExtractionRequest
from src.pipeline.metadata import ProviderError as ExtractionProviderError
from src.pipeline.metadata import ProviderMetadata as ExtractionProviderMetadata
from src.pipeline.metadata import ProviderResponse as ExtractionProviderResponse
from src.pipeline.metadata import ProviderUnavailableError as ExtractionProviderUnavailableError
from src.providers.registry import register_classification_provider, register_extraction_provider

# Model string per this environment's own documented Claude API model names
# (see this session's system context) — a plain module constant, not
# read from config in v0.9 (§7's Test Plan: no config surface for model
# choice was part of the approved v0.9 scope; revisit alongside a future
# registry entry if per-provider model selection becomes a real need).
_MODEL = "claude-sonnet-5"

# Defensive bounds, not platform guarantees — kept generous enough that no
# real Downloads-folder file should realistically hit them in ordinary use,
# but present so a single oversized file degrades to ProviderError (caught,
# logged, falls back to Unknown/null fields per the existing contract) rather
# than sending an unbounded payload or an unbounded API bill.
_MAX_TEXT_CHARS = 20_000
_MAX_IMAGE_BYTES = 4 * 1024 * 1024  # ~4MB raw; base64 + JSON overhead stays
                                     # comfortably under typical API request
                                     # size limits for a single image block.

_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
}

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _require_api_key() -> str:
    """Reads `ANTHROPIC_API_KEY` from the environment (the Anthropic SDK's
    own default lookup — deliberately not re-implemented, just checked
    proactively here so a missing key fails clearly, before any API call,
    with a message specific to this project rather than the SDK's generic
    one). Never reads a key from `src/config/sources.yaml` or anywhere else
    — the key is never written to disk by this project (§ "Risk assessment"
    of the design package)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ClassificationProviderUnavailableError(
            "ANTHROPIC_API_KEY is not set. The Claude API provider requires "
            "it as an environment variable — set it before running, or run "
            "'python -m src.cli provider disable' to turn the opt-in "
            "provider back off."
        )
    return api_key


def _client() -> "anthropic.Anthropic":
    return anthropic.Anthropic(api_key=_require_api_key())


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Parses a model response that should be a single JSON object, tolerant
    of the common case where the model wraps it in a markdown code fence
    despite being asked not to. Raises `ValueError` (not one of this
    project's `ProviderError`/`ProviderUnavailableError` types — callers
    wrap it into the correct one for their own module, since classification
    and extraction have independently-defined exception classes, §21) on
    anything that still isn't valid JSON after stripping fences."""
    stripped = _JSON_FENCE.sub("", text.strip()).strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def _response_text(response: "anthropic.types.Message") -> str:
    """Concatenates every text content block in a Messages API response —
    in practice always exactly one for the prompts this file sends, but
    written to handle more than one without assuming."""
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )


def _token_usage(response: "anthropic.types.Message") -> Optional[Dict[str, int]]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
    }


def _image_content_block(path: str, provider_error_cls) -> Dict[str, Any]:
    """Builds a Messages API image content block from `path`. A `.pdf` is
    rendered to a PNG first (`core/pdf.py`'s `render_page_as_image()` — the
    same function `ClassificationEngine`'s own vision-mode dispatch already
    fails-fast on if the page truly can't be rendered); any other path is
    read as raw image bytes directly (the case for Module 03's Image/
    Screenshot family, whose `MetadataExtractionRequest.path` already points
    at a real image file — vision mode there is never a PDF).

    `provider_error_cls` is passed in rather than imported once at module
    level because this helper is shared by both the classifier (which only
    ever calls it for a PDF, and needs `ClassificationProviderError` on
    failure) and the extractor (which needs `ExtractionProviderError`) —
    each module's own independently-defined exception type, per §21."""
    extension = Path(path).suffix.lower()
    if extension == ".pdf":
        data = render_page_as_image(path)
        media_type = "image/png"
    else:
        data = Path(path).read_bytes()
        media_type = _IMAGE_MEDIA_TYPES.get(extension, "image/jpeg")

    if len(data) > _MAX_IMAGE_BYTES:
        raise provider_error_cls(
            f"image too large to send to the Claude API ({len(data)} bytes > "
            f"{_MAX_IMAGE_BYTES} limit) — left unclassified/unextracted for "
            "this file, same as any other provider failure."
        )

    encoded = base64.standard_b64encode(data).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": encoded},
    }


# --- Classification ---------------------------------------------------------

_VALID_CATEGORY_VALUES = ", ".join(category.value for category in Category)

_CLASSIFICATION_SYSTEM_PROMPT = (
    "You are classifying a file for a personal Downloads-folder organizing "
    "tool. Respond with ONLY a single JSON object, no other text, no markdown "
    "fences, with exactly these keys: "
    '"category" (one of: ' + _VALID_CATEGORY_VALUES + '), '
    '"ambiguous" (true/false — true if the file genuinely could belong to '
    "more than one category), "
    '"multi_document_detected" (true/false — true only if this single file '
    "visibly contains more than one distinct, unrelated document), "
    '"notes" (a short string, may be empty). '
    "If you cannot confidently determine a specific category, answer "
    '"Unknown" rather than guessing — an honest Unknown is preferred over a '
    "confident wrong answer. Most files never reach you at all (extension-"
    "based rules already resolve them); you are only asked to classify "
    "genuinely ambiguous, judgment-dependent content."
)


class ClaudeAPIClassifier(ClassificationProvider):
    """TD-01 v0.9's real, non-interactive `ClassificationProvider`. See this
    module's docstring for the opt-in/consent boundary (enforced by the
    caller, not here) and for why no automated test ever exercises a real
    network call through this class."""

    def classify(self, request: ClassificationRequest) -> ClassificationProviderResponse:
        client = _client()

        if request.mode == "vision":
            content = [
                _image_content_block(request.path, ClassificationProviderError),
                {"type": "text", "text": "Classify this file."},
            ]
        else:
            text = (request.extracted_text or "")[:_MAX_TEXT_CHARS]
            content = [{"type": "text", "text": f"Classify this file. Its extracted text:\n\n{text}"}]

        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=512,
                system=_CLASSIFICATION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
            raise ClassificationProviderUnavailableError(str(exc)) from exc
        except anthropic.AnthropicError as exc:
            raise ClassificationProviderError(str(exc)) from exc

        try:
            parsed = _extract_json_object(_response_text(response))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ClassificationProviderError(f"unparseable response: {exc}") from exc

        result = ClassificationResult(
            category=str(parsed.get("category", "")),
            ambiguous=bool(parsed.get("ambiguous", False)),
            multi_document_detected=bool(parsed.get("multi_document_detected", False)),
            notes=str(parsed.get("notes") or ""),
        )
        metadata = ClassificationProviderMetadata(
            provider_name="claude_api",
            model=_MODEL,
            provider_version=anthropic.__version__,
            token_usage=_token_usage(response),
        )
        return ClassificationProviderResponse(result=result, metadata=metadata)


# --- Metadata extraction -----------------------------------------------------

_EXTRACTION_INSTRUCTION_TEMPLATE = (
    "You are extracting structured metadata from a file for a personal "
    "Downloads-folder organizing tool. Respond with ONLY a single JSON "
    "object, no other text, no markdown fences, with exactly these keys: "
    "{fields}. For any field you cannot confidently determine, use JSON "
    "null rather than guessing — an honest null is preferred over a "
    "fabricated value. Every value must be a plain string or number, never "
    "a boolean, an object, or a list."
)


class ClaudeAPIExtractor(MetadataExtractionProvider):
    """TD-01 v0.9's real, non-interactive `MetadataExtractionProvider`.
    Mirrors `ClaudeAPIClassifier`'s structure exactly — see that class's and
    this module's docstrings."""

    def extract(self, request: MetadataExtractionRequest) -> ExtractionProviderResponse:
        client = _client()

        fields_list = ", ".join(f'"{name}"' for name in request.fields_requested)
        system_prompt = _EXTRACTION_INSTRUCTION_TEMPLATE.format(fields=fields_list or "(none requested)")

        if request.mode == "vision":
            content = [
                _image_content_block(request.path, ExtractionProviderError),
                {"type": "text", "text": "Extract the requested fields from this file."},
            ]
        else:
            text = (request.extracted_text or "")[:_MAX_TEXT_CHARS]
            content = [{
                "type": "text",
                "text": f"Extract the requested fields from this file's text:\n\n{text}",
            }]

        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": content}],
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
            raise ExtractionProviderUnavailableError(str(exc)) from exc
        except anthropic.AnthropicError as exc:
            raise ExtractionProviderError(str(exc)) from exc

        try:
            parsed = _extract_json_object(_response_text(response))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ExtractionProviderError(f"unparseable response: {exc}") from exc

        metadata = ExtractionProviderMetadata(
            provider_name="claude_api",
            model=_MODEL,
            provider_version=anthropic.__version__,
            token_usage=_token_usage(response),
        )
        # No filtering/type-validation here beyond what JSON parsing already
        # guarantees — MetadataExtractionEngine._validate_and_merge() is the
        # actual trust boundary (design §12/§18) and already drops anything
        # outside fields_requested or the wrong type; duplicating that logic
        # here would be exactly the kind of drift-risking duplication this
        # project's own PT-002/PT-003 postmortems warn against.
        return ExtractionProviderResponse(fields=parsed, metadata=metadata)


# --- Registration (import-time side effect — see module docstring) ---------

register_classification_provider("claude", ClaudeAPIClassifier)
register_extraction_provider("claude", ClaudeAPIExtractor)
