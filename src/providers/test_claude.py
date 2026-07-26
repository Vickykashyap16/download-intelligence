"""
Unit tests for src/providers/claude.py — TD-01 v0.9's real Claude API
provider.

Never makes a real network request, per this project's existing "tests never
depend on a live provider" convention (see e.g. ClaudeLiveClassifier's own
docstring, and this file's own module docstring). Every test mocks the
`anthropic` client at the level `claude.py` itself calls it: `_client()` is
monkeypatched to return a small fake object exposing `.messages.create()`,
which either returns a canned fake response object (mirroring the small
subset of the real `anthropic.types.Message` shape this module actually
reads: `.content`, `.usage.input_tokens`/`.usage.output_tokens`) or raises a
real `anthropic` exception instance to test this module's own exception
mapping.

Run with: pytest src/providers/test_claude.py -v
"""

import json

import anthropic
import httpx
import pytest

import src.providers.claude as claude_module
import src.providers.registry as registry_module
from src.pipeline.classification import ClassificationRequest
from src.pipeline.classification import ProviderError as ClassificationProviderError
from src.pipeline.classification import (
    ProviderUnavailableError as ClassificationProviderUnavailableError,
)
from src.pipeline.metadata import MetadataExtractionRequest
from src.pipeline.metadata import ProviderError as ExtractionProviderError
from src.pipeline.metadata import ProviderUnavailableError as ExtractionProviderUnavailableError


# --- Fakes -------------------------------------------------------------------


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens=100, output_tokens=20):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeMessage:
    """Stands in for anthropic.types.Message — only the attributes
    claude.py's _response_text()/_token_usage() actually read."""

    def __init__(self, text, usage=None):
        self.content = [_FakeTextBlock(text)]
        self.usage = usage if usage is not None else _FakeUsage()


class _FakeMessagesEndpoint:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.received_kwargs = None

    def create(self, **kwargs):
        self.received_kwargs = kwargs
        if self._raises is not None:
            raise self._raises
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response=None, raises=None):
        self.messages = _FakeMessagesEndpoint(response=response, raises=raises)


def _patch_client(monkeypatch, response=None, raises=None):
    fake_client = _FakeAnthropicClient(response=response, raises=raises)
    monkeypatch.setattr(claude_module, "_client", lambda: fake_client)
    return fake_client


def _httpx_request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


# --- Registration (import-time side effect) ----------------------------------


def test_importing_module_registers_claude_under_both_registries():
    assert "claude" in registry_module.registered_classification_providers()
    assert "claude" in registry_module.registered_extraction_providers()


def test_registered_claude_classification_factory_produces_correct_type():
    resolved = registry_module.resolve_classification_provider("claude")
    assert isinstance(resolved, claude_module.ClaudeAPIClassifier)


def test_registered_claude_extraction_factory_produces_correct_type():
    resolved = registry_module.resolve_extraction_provider("claude")
    assert isinstance(resolved, claude_module.ClaudeAPIExtractor)


# --- _require_api_key() / _client() ------------------------------------------


def test_require_api_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ClassificationProviderUnavailableError) as excinfo:
        claude_module._require_api_key()
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)


def test_require_api_key_returns_key_when_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    assert claude_module._require_api_key() == "sk-test-123"


def test_classify_raises_provider_unavailable_when_key_missing(monkeypatch):
    """No _client() mock needed — the missing-key check happens before any
    client is constructed, exactly mirroring the real unconfigured-provider
    path exercised end-to-end by the Provider Evaluation Harness dry run."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    classifier = claude_module.ClaudeAPIClassifier()
    request = ClassificationRequest(
        file_id="f1", path="/tmp/does-not-matter.txt",
        extracted_text="some text", mode="text",
    )
    with pytest.raises(ClassificationProviderUnavailableError):
        classifier.classify(request)


# --- _extract_json_object() ---------------------------------------------------


def test_extract_json_object_parses_plain_json():
    parsed = claude_module._extract_json_object('{"category": "Document"}')
    assert parsed == {"category": "Document"}


def test_extract_json_object_strips_markdown_fence():
    parsed = claude_module._extract_json_object('```json\n{"category": "Document"}\n```')
    assert parsed == {"category": "Document"}


def test_extract_json_object_strips_bare_fence_no_language_tag():
    parsed = claude_module._extract_json_object('```\n{"category": "Image"}\n```')
    assert parsed == {"category": "Image"}


def test_extract_json_object_raises_value_error_on_non_json():
    with pytest.raises(ValueError):
        claude_module._extract_json_object("not json at all")


def test_extract_json_object_raises_value_error_on_json_array():
    with pytest.raises(ValueError):
        claude_module._extract_json_object("[1, 2, 3]")


# --- ClaudeAPIClassifier.classify() -------------------------------------------


def test_classify_text_mode_sends_extracted_text_and_parses_result(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    response_json = json.dumps({
        "category": "Document", "ambiguous": False,
        "multi_document_detected": False, "notes": "a legal filing",
    })
    fake_client = _patch_client(monkeypatch, response=_FakeMessage(response_json))

    classifier = claude_module.ClaudeAPIClassifier()
    request = ClassificationRequest(
        file_id="f1", path="/tmp/legal_form.pdf",
        extracted_text="Articles of Association...", mode="text",
    )
    result = classifier.classify(request)

    assert result.result.category == "Document"
    assert result.result.ambiguous is False
    assert result.result.notes == "a legal filing"
    assert result.metadata.provider_name == "claude_api"
    assert result.metadata.model == claude_module._MODEL
    assert result.metadata.token_usage == {"input_tokens": 100, "output_tokens": 20}
    # The extracted text must actually have been sent, not silently dropped.
    sent_content = fake_client.messages.received_kwargs["messages"][0]["content"]
    assert "Articles of Association" in sent_content[0]["text"]


def test_classify_vision_mode_sends_image_block(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    image_path = tmp_path / "screenshot.jpg"
    image_path.write_bytes(b"\xff\xd8\xff" + b"0" * 100)  # minimal JPEG-ish header
    response_json = json.dumps({
        "category": "Screenshot", "ambiguous": False,
        "multi_document_detected": False, "notes": "",
    })
    fake_client = _patch_client(monkeypatch, response=_FakeMessage(response_json))

    classifier = claude_module.ClaudeAPIClassifier()
    request = ClassificationRequest(
        file_id="f2", path=str(image_path), extracted_text=None, mode="vision",
    )
    result = classifier.classify(request)

    assert result.result.category == "Screenshot"
    sent_content = fake_client.messages.received_kwargs["messages"][0]["content"]
    assert sent_content[0]["type"] == "image"
    assert sent_content[0]["source"]["media_type"] == "image/jpeg"


def test_classify_oversized_image_raises_classification_provider_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    image_path = tmp_path / "huge.jpg"
    image_path.write_bytes(b"0" * (claude_module._MAX_IMAGE_BYTES + 1))
    _patch_client(monkeypatch)  # never reached — the size check raises first

    classifier = claude_module.ClaudeAPIClassifier()
    request = ClassificationRequest(
        file_id="f3", path=str(image_path), extracted_text=None, mode="vision",
    )
    with pytest.raises(ClassificationProviderError) as excinfo:
        classifier.classify(request)
    assert "too large" in str(excinfo.value)


def test_classify_connection_error_maps_to_provider_unavailable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    _patch_client(monkeypatch, raises=anthropic.APIConnectionError(request=_httpx_request()))
    classifier = claude_module.ClaudeAPIClassifier()
    request = ClassificationRequest(
        file_id="f4", path="/tmp/x.txt", extracted_text="text", mode="text",
    )
    with pytest.raises(ClassificationProviderUnavailableError):
        classifier.classify(request)


def test_classify_rate_limit_error_maps_to_provider_unavailable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    resp = httpx.Response(429, request=_httpx_request())
    _patch_client(monkeypatch, raises=anthropic.RateLimitError("rate limited", response=resp, body=None))
    classifier = claude_module.ClaudeAPIClassifier()
    request = ClassificationRequest(
        file_id="f5", path="/tmp/x.txt", extracted_text="text", mode="text",
    )
    with pytest.raises(ClassificationProviderUnavailableError):
        classifier.classify(request)


def test_classify_other_anthropic_error_maps_to_provider_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    resp = httpx.Response(400, request=_httpx_request())
    _patch_client(monkeypatch, raises=anthropic.BadRequestError("bad request", response=resp, body=None))
    classifier = claude_module.ClaudeAPIClassifier()
    request = ClassificationRequest(
        file_id="f6", path="/tmp/x.txt", extracted_text="text", mode="text",
    )
    with pytest.raises(ClassificationProviderError):
        classifier.classify(request)


def test_classify_unparseable_response_maps_to_provider_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    _patch_client(monkeypatch, response=_FakeMessage("this is not json"))
    classifier = claude_module.ClaudeAPIClassifier()
    request = ClassificationRequest(
        file_id="f7", path="/tmp/x.txt", extracted_text="text", mode="text",
    )
    with pytest.raises(ClassificationProviderError) as excinfo:
        classifier.classify(request)
    assert "unparseable" in str(excinfo.value)


def test_classify_missing_optional_fields_default_sensibly(monkeypatch):
    """A minimal, technically-valid response missing ambiguous/notes/etc.
    must not crash — parsed.get() defaults apply."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    _patch_client(monkeypatch, response=_FakeMessage(json.dumps({"category": "Unknown"})))
    classifier = claude_module.ClaudeAPIClassifier()
    request = ClassificationRequest(
        file_id="f8", path="/tmp/x.txt", extracted_text="text", mode="text",
    )
    result = classifier.classify(request)
    assert result.result.category == "Unknown"
    assert result.result.ambiguous is False
    assert result.result.notes == ""


# --- ClaudeAPIExtractor.extract() ---------------------------------------------


def test_extract_text_mode_requests_only_named_fields(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    response_json = json.dumps({"vendor": "Acme Corp", "invoice_date": "2026-01-15"})
    fake_client = _patch_client(monkeypatch, response=_FakeMessage(response_json))

    extractor = claude_module.ClaudeAPIExtractor()
    request = MetadataExtractionRequest(
        file_id="f9", path="/tmp/invoice.pdf", extracted_text="Invoice #123...",
        mode="text", fields_requested=["vendor", "invoice_date"],
    )
    result = extractor.extract(request)

    assert result.fields == {"vendor": "Acme Corp", "invoice_date": "2026-01-15"}
    assert result.metadata.provider_name == "claude_api"
    assert result.metadata.token_usage == {"input_tokens": 100, "output_tokens": 20}
    system_prompt = fake_client.messages.received_kwargs["system"]
    assert '"vendor"' in system_prompt
    assert '"invoice_date"' in system_prompt


def test_extract_vision_mode_sends_image_block(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"\xff\xd8\xff" + b"0" * 100)
    _patch_client(monkeypatch, response=_FakeMessage(json.dumps({"description": "a sunset"})))

    extractor = claude_module.ClaudeAPIExtractor()
    request = MetadataExtractionRequest(
        file_id="f10", path=str(image_path), extracted_text=None,
        mode="vision", fields_requested=["description"],
    )
    result = extractor.extract(request)
    assert result.fields == {"description": "a sunset"}


def test_extract_connection_error_maps_to_extraction_provider_unavailable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    _patch_client(monkeypatch, raises=anthropic.APIConnectionError(request=_httpx_request()))
    extractor = claude_module.ClaudeAPIExtractor()
    request = MetadataExtractionRequest(
        file_id="f11", path="/tmp/x.txt", extracted_text="text",
        mode="text", fields_requested=["candidate_name"],
    )
    with pytest.raises(ExtractionProviderUnavailableError):
        extractor.extract(request)


def test_extract_unparseable_response_maps_to_extraction_provider_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    _patch_client(monkeypatch, response=_FakeMessage("not json"))
    extractor = claude_module.ClaudeAPIExtractor()
    request = MetadataExtractionRequest(
        file_id="f12", path="/tmp/x.txt", extracted_text="text",
        mode="text", fields_requested=["candidate_name"],
    )
    with pytest.raises(ExtractionProviderError):
        extractor.extract(request)


def test_extract_no_fields_requested_still_builds_valid_prompt(monkeypatch):
    """fields_requested=[] is a real, legitimate input (e.g. a category with
    nothing left to ask after the deterministic pass) — must not crash
    building the system prompt."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    _patch_client(monkeypatch, response=_FakeMessage("{}"))
    extractor = claude_module.ClaudeAPIExtractor()
    request = MetadataExtractionRequest(
        file_id="f13", path="/tmp/x.txt", extracted_text="text",
        mode="text", fields_requested=[],
    )
    result = extractor.extract(request)
    assert result.fields == {}


# --- Independent exception vocabularies (design §21) --------------------------


def test_classification_and_extraction_provider_errors_are_distinct_types():
    """The two modules deliberately do not share exception classes — a
    regression here (e.g. someone "helpfully" unifying them) would silently
    violate design §21's convention-following-not-sharing pattern."""
    assert ClassificationProviderError is not ExtractionProviderError
    assert ClassificationProviderUnavailableError is not ExtractionProviderUnavailableError
