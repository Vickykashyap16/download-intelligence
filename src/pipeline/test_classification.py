"""
Unit tests for pipeline/classification.py — Module 02.

This file starts with the deterministic-pass tests (extension routing, screenshot
split, locked/non-English signals). Provider/Engine/orchestration tests are added in
the same file as those pieces are implemented, matching Module 01's
test_watch_ingest.py convention of one test file per pipeline module.

Run with: pytest src/pipeline/test_classification.py -v
"""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from src.models.classification import Category
import src.pipeline.watch_ingest as watch_ingest_module
import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.file_record import FileRecord
from src.pipeline.classification import (
    ClassificationEngine,
    ClassificationProvider,
    ClassificationRequest,
    ClassificationResult,
    ClaudeLiveClassifier,
    ProviderError,
    ProviderMetadata,
    ProviderResponse,
    ProviderUnavailableError,
    classify_batch,
    classify_by_extension,
    classify_screenshot_or_image,
    detect_non_english,
    is_locked,
    is_text_bearing,
    needs_screenshot_split,
)


class FakeClassificationProvider(ClassificationProvider):
    """Test double used throughout this suite (and reused by test_engine cases added
    later) — returns a canned ProviderResponse instead of ever calling a real provider,
    per the design's Test Strategy (§16)."""

    def __init__(self, response: ProviderResponse = None, raises: Exception = None):
        self._response = response
        self._raises = raises
        self.received_requests = []

    def classify(self, request: ClassificationRequest) -> ProviderResponse:
        self.received_requests.append(request)
        if self._raises is not None:
            raise self._raises
        return self._response

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SAMPLES = _PROJECT_ROOT / "Samples"


# --- classify_by_extension() ---

def test_classify_by_extension_application():
    assert classify_by_extension("installer.dmg") == Category.APPLICATION
    assert classify_by_extension("setup.pkg") == Category.APPLICATION
    assert classify_by_extension("app.exe") == Category.APPLICATION


def test_classify_by_extension_archive():
    assert classify_by_extension("backup.zip") == Category.ARCHIVE


def test_classify_by_extension_video():
    assert classify_by_extension("clip.mp4") == Category.VIDEO


def test_classify_by_extension_audio():
    assert classify_by_extension("song.mp3") == Category.AUDIO


def test_classify_by_extension_returns_none_for_images_and_text():
    """None here means "needs further routing," not Unknown — see the docstring."""
    assert classify_by_extension("photo.jpg") is None
    assert classify_by_extension("invoice.pdf") is None
    assert classify_by_extension("resume.docx") is None


def test_classify_by_extension_returns_none_for_unrecognized_extension():
    assert classify_by_extension("mystery.xyz") is None


def test_classify_by_extension_is_case_insensitive():
    assert classify_by_extension("ARCHIVE.ZIP") == Category.ARCHIVE


# --- needs_screenshot_split() / is_text_bearing() ---

def test_needs_screenshot_split_true_for_image_extensions():
    assert needs_screenshot_split("photo.jpg") is True
    assert needs_screenshot_split("photo.png") is True


def test_needs_screenshot_split_false_for_non_images():
    assert needs_screenshot_split("invoice.pdf") is False
    assert needs_screenshot_split("archive.zip") is False


def test_is_text_bearing_true_for_pdf_docx_txt():
    assert is_text_bearing("invoice.pdf") is True
    assert is_text_bearing("resume.docx") is True
    assert is_text_bearing("notes.txt") is True


def test_is_text_bearing_false_for_images_and_binaries():
    assert is_text_bearing("photo.jpg") is False
    assert is_text_bearing("app.exe") is False


# --- classify_screenshot_or_image() — real Samples/ files ---

def test_classify_screenshot_or_image_detects_real_screenshot_by_resolution_and_name():
    path = _SAMPLES / "Images" / "sample_screenshot_login_error.png"
    assert classify_screenshot_or_image(str(path)) == Category.SCREENSHOT


def test_classify_screenshot_or_image_detects_real_product_photo_as_image(tmp_path):
    """sample_product_photo.jpg is 800x600 (not a common screen resolution), has no
    marker filename, and has no camera EXIF (it's a synthetic Pillow-generated image).

    Post-freeze correction (PT-002, 2026-07-20): before this correction, "no camera
    EXIF" was an independent, sufficient trigger for Screenshot, so this fixture
    (despite its name) actually asserted Category.SCREENSHOT — a known, disclosed
    limitation at the time (see Release/Module02/KNOWN_LIMITATIONS.md), later directly
    confirmed against real-world content by validation (PATTERN_TRACKER.md PT-002,
    Confirmed Pattern). With that third condition removed
    (Build-out/02 Classification/Module 02 Post-Freeze Design Correction — PT-002.md),
    a fixture with no marker and no resolution match now correctly falls to the
    "Otherwise -> Image" default, matching both this test's name and real-world
    ground truth."""
    path = _SAMPLES / "Images" / "sample_product_photo.jpg"
    assert classify_screenshot_or_image(str(path)) == Category.IMAGE


def test_classify_screenshot_or_image_filename_marker_wins_immediately(tmp_path):
    from PIL import Image

    marked = tmp_path / "My Screenshot 2026.png"
    Image.new("RGB", (800, 600)).save(marked)
    assert classify_screenshot_or_image(str(marked)) == Category.SCREENSHOT


def test_classify_screenshot_or_image_true_photo_with_camera_exif_and_odd_dimensions(tmp_path):
    """A photo that has NONE of the three screenshot signals — no marker filename, an
    uncommon resolution, and real camera EXIF present — must classify as Image."""
    from PIL import Image

    photo = tmp_path / "vacation_pic.jpg"
    image = Image.new("RGB", (4032, 3024))  # a real phone camera resolution, not in
                                             # the common-screen-resolutions list
    exif = image.getexif()
    exif[271] = "Test Camera Co."  # Make
    exif[272] = "Model X"          # Model
    image.save(photo, exif=exif)

    assert classify_screenshot_or_image(str(photo)) == Category.IMAGE


# --- PT-002 regression tests (post-freeze correction, 2026-07-20) ---
# Synthetic fixtures for the real-world content shapes PATTERN_TRACKER.md PT-002
# directly confirmed as false positives under the old 3-condition logic: none of
# these have a marker filename or a common-screen-resolution match, and none have
# camera EXIF, so under the old logic they all incorrectly returned Screenshot.
# Under the corrected 2-condition logic they must all return Image. See
# Build-out/02 Classification/Module 02 Post-Freeze Design Correction — PT-002.md §8 (T2).

def test_classify_screenshot_or_image_scanned_document_photo_classifies_as_image(tmp_path):
    """A phone-camera scan of a paper document: generic filename, no marker, an
    uncommon resolution, and no EXIF (scanning apps typically strip or never write
    camera EXIF onto the processed output). PT-002 evidence: VL-002-1 / VL-003-1."""
    from PIL import Image

    scan = tmp_path / "IMG_20260714_scan.jpg"
    Image.new("RGB", (2481, 3508)).save(scan)  # A4 at 300dpi, not a screen resolution
    assert classify_screenshot_or_image(str(scan)) == Category.IMAGE


def test_classify_screenshot_or_image_synthetic_marketing_graphic_classifies_as_image(tmp_path):
    """A product/marketing graphic exported from a design tool: generic filename, no
    marker, an uncommon resolution, and no camera EXIF (it was never photographed)."""
    from PIL import Image

    graphic = tmp_path / "product_banner_final.png"
    Image.new("RGB", (1080, 1350)).save(graphic)  # common social-post size, not screen
    assert classify_screenshot_or_image(str(graphic)) == Category.IMAGE


def test_classify_screenshot_or_image_exif_stripped_messaging_photo_classifies_as_image(tmp_path):
    """A real personal photo re-encoded by a messaging app (e.g. WhatsApp), which
    strips EXIF and re-compresses to app-specific dimensions: generic filename, no
    marker, an uncommon (non-screen) resolution, and no EXIF."""
    from PIL import Image

    shared = tmp_path / "WhatsApp Image 2026-07-14 at 09.12.45.jpeg"
    Image.new("RGB", (1600, 1200)).save(shared)  # WhatsApp's typical re-encode size
    assert classify_screenshot_or_image(str(shared)) == Category.IMAGE


def test_classify_screenshot_or_image_disclosed_tradeoff_unmarked_uncommon_resolution_screenshot(tmp_path):
    """T4 (adversarial, disclosed trade-off): a genuine screenshot with neither a
    marker filename nor a common-screen-resolution match (e.g. cropped or resized
    before reaching Downloads) is, by design, indistinguishable at this layer from
    the Image fixtures above and now defaults to Image rather than Screenshot. This
    test exists to make that bounded, disclosed trade-off visible and monitored (see
    the design record's Risk Assessment and Acceptance Criteria), not to assert it
    is the "correct" outcome for this specific file."""
    from PIL import Image

    cropped_screenshot = tmp_path / "final_v2.png"
    Image.new("RGB", (1234, 987)).save(cropped_screenshot)  # cropped, no longer a
                                                             # standard screen size
    assert classify_screenshot_or_image(str(cropped_screenshot)) == Category.IMAGE


# --- is_locked() ---

def test_is_locked_false_for_normal_pdf():
    path = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    assert is_locked(str(path)) is False


def test_is_locked_false_for_non_pdf_text_bearing_file():
    path = _SAMPLES / "Documents" / "sample_generic_document_manual.txt"
    assert is_locked(str(path)) is False


def test_is_locked_true_for_encrypted_pdf(tmp_path):
    from pypdf import PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    plain = tmp_path / "plain.pdf"
    c = canvas.Canvas(str(plain), pagesize=letter)
    c.drawString(72, 750, "secret")
    c.save()

    encrypted = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.append(str(plain))
    writer.encrypt("password123")
    with open(encrypted, "wb") as f:
        writer.write(f)

    assert is_locked(str(encrypted)) is True


# --- detect_non_english() ---

def test_detect_non_english_false_for_english_text():
    non_english, language = detect_non_english(
        "This is a perfectly ordinary English sentence for testing purposes today."
    )
    assert non_english is False
    assert language == "en"


def test_detect_non_english_true_for_french_text():
    non_english, language = detect_non_english(
        "Ceci est une phrase ordinaire en français utilisée à des fins de test aujourd'hui."
    )
    assert non_english is True
    assert language == "fr"


def test_detect_non_english_false_when_language_cannot_be_determined():
    non_english, language = detect_non_english("")
    assert non_english is False
    assert language is None


# --- Provider boundary: dataclasses, ABC enforcement, ClaudeLiveClassifier placeholder ---

def test_classification_provider_cannot_be_instantiated_directly():
    """ABC enforcement: classify() is abstract, so the base class itself can't be
    instantiated — only a real subclass (ClaudeLiveClassifier, FakeClassificationProvider,
    a future provider) can be."""
    with pytest.raises(TypeError):
        ClassificationProvider()


def test_fake_provider_satisfies_the_abstract_interface():
    fake = FakeClassificationProvider(
        response=ProviderResponse(
            result=ClassificationResult(category="Invoice"),
            metadata=ProviderMetadata(provider_name="fake"),
        )
    )
    request = ClassificationRequest(
        file_id="f1", path="/tmp/invoice.pdf", extracted_text="some text", mode="text"
    )
    response = fake.classify(request)
    assert response.result.category == "Invoice"
    assert fake.received_requests == [request]


def test_claude_live_classifier_raises_documented_placeholder():
    """ClaudeLiveClassifier.classify() must never silently "work" as autonomous code —
    it's fulfilled live by Claude during a real run, not by a function body. This test
    locks in that it fails loudly and clearly rather than returning a fake answer."""
    provider = ClaudeLiveClassifier()
    request = ClassificationRequest(
        file_id="f1", path="/tmp/invoice.pdf", extracted_text="some text", mode="text"
    )
    with pytest.raises(NotImplementedError, match="fulfilled live by Claude"):
        provider.classify(request)


def test_classification_request_defaults_mime_type_to_none():
    request = ClassificationRequest(file_id="f1", path="/tmp/x.pdf", extracted_text=None, mode="vision")
    assert request.mime_type is None


def test_provider_response_carries_both_result_and_metadata():
    response = ProviderResponse(
        result=ClassificationResult(category="Resume", ambiguous=True),
        metadata=ProviderMetadata(provider_name="claude_live", model="claude-sonnet-5", latency_ms=42),
    )
    assert response.result.category == "Resume"
    assert response.result.ambiguous is True
    assert response.metadata.provider_name == "claude_live"
    assert response.metadata.latency_ms == 42
    assert response.metadata.reasoning is None


# --- ClassificationEngine ---

def _fake_engine(response=None, raises=None):
    provider = FakeClassificationProvider(response=response, raises=raises)
    return ClassificationEngine(provider), provider


def test_engine_deterministic_application():
    engine, provider = _fake_engine()
    result = engine.classify_file("installer.dmg", file_id="f1")
    assert result.category == Category.APPLICATION
    assert result.mode == "deterministic"
    assert result.classification_signals.ambiguous is False
    assert result.provider_metadata is None
    assert provider.received_requests == []  # never called for a deterministic path


def test_engine_deterministic_screenshot(tmp_path):
    from PIL import Image

    screenshot = tmp_path / "My Screenshot.png"
    Image.new("RGB", (800, 600)).save(screenshot)

    engine, provider = _fake_engine()
    result = engine.classify_file(str(screenshot), file_id="f2")
    assert result.category == Category.SCREENSHOT
    assert result.mode == "deterministic"
    assert provider.received_requests == []


def test_engine_unrecognized_extension_is_unknown_without_calling_provider(tmp_path):
    mystery = tmp_path / "mystery.xyz"
    mystery.write_text("nobody knows")

    engine, provider = _fake_engine()
    result = engine.classify_file(str(mystery), file_id="f3")
    assert result.category == Category.UNKNOWN
    assert result.mode == "deterministic"
    assert provider.received_requests == []


def test_engine_locked_pdf_never_calls_provider(tmp_path):
    from pypdf import PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    plain = tmp_path / "plain.pdf"
    c = canvas.Canvas(str(plain), pagesize=letter)
    c.drawString(72, 750, "secret")
    c.save()
    encrypted = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.append(str(plain))
    writer.encrypt("pw")
    with open(encrypted, "wb") as f:
        writer.write(f)

    engine, provider = _fake_engine()
    result = engine.classify_file(str(encrypted), file_id="f4")
    assert result.category == Category.UNKNOWN
    assert result.classification_signals.locked is True
    assert result.fallback_used is False  # locked isn't a "fallback" — it's a known signal
    assert provider.received_requests == []


def test_engine_text_deep_pass_success(tmp_path):
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    response = ProviderResponse(
        result=ClassificationResult(category="Invoice", ambiguous=False),
        metadata=ProviderMetadata(provider_name="claude_live", model="claude-sonnet-5"),
    )
    engine, provider = _fake_engine(response=response)

    result = engine.classify_file(str(invoice), file_id="f5")
    assert result.category == Category.INVOICE
    assert result.mode == "text"
    assert result.classification_signals.no_extractable_text is False
    assert result.provider_metadata is not None
    assert result.provider_metadata.provider_name == "claude_live"
    assert result.provider_metadata.latency_ms is not None  # Engine measured it
    assert len(provider.received_requests) == 1
    assert provider.received_requests[0].mode == "text"
    assert provider.received_requests[0].extracted_text is not None


def test_engine_vision_fallback_for_scanned_pdf(tmp_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    # A PDF with a real page but no text drawn on it (simulates a scanned/image-only
    # PDF — extract_text() will return None, so the Engine should fall to vision
    # mode). Must draw *something* non-text before saving: a canvas with zero drawing
    # operations at all produces a PDF with zero pages (confirmed during testing —
    # pdfplumber reports len(pdf.pages) == 0 for that case), which isn't a valid stand-
    # in for "one page, no text" and would make render_page_as_image() raise IndexError
    # instead of exercising the intended vision path.
    scanned = tmp_path / "scanned.pdf"
    c = canvas.Canvas(str(scanned), pagesize=letter)
    c.rect(100, 100, 50, 50, fill=1)  # a shape, not text — commits a real page
    c.save()

    response = ProviderResponse(
        result=ClassificationResult(category="Document"),
        metadata=ProviderMetadata(provider_name="claude_live"),
    )
    engine, provider = _fake_engine(response=response)
    result = engine.classify_file(str(scanned), file_id="f6")

    assert result.category == Category.DOCUMENT
    assert result.mode == "vision"
    assert result.classification_signals.no_extractable_text is True
    assert provider.received_requests[0].mode == "vision"
    assert provider.received_requests[0].extracted_text is None


def test_engine_non_pdf_text_bearing_with_no_content_skips_provider(tmp_path):
    empty_ish = tmp_path / "practically_empty.txt"
    empty_ish.write_text("   ")  # whitespace only -> extract_text() strips to ""  -> None

    engine, provider = _fake_engine()
    result = engine.classify_file(str(empty_ish), file_id="f7")
    assert result.category == Category.UNKNOWN
    assert result.classification_signals.no_extractable_text is True
    assert provider.received_requests == []  # nothing worth sending


def test_engine_fallback_on_provider_unavailable(tmp_path):
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    engine, provider = _fake_engine(raises=ProviderUnavailableError("network down"))

    result = engine.classify_file(str(invoice), file_id="f8")
    assert result.category == Category.UNKNOWN
    assert result.fallback_used is True
    assert result.fallback_reason == "provider_exception"
    # F3 (release audit, 2026-07-06): the actual exception message must survive into
    # EngineResult, not just the fixed reason code, so a real incident is diagnosable
    # from the action log alone.
    assert result.error_detail is not None
    assert "ProviderUnavailableError" in result.error_detail
    assert "network down" in result.error_detail


def test_engine_fallback_on_provider_error(tmp_path):
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    engine, provider = _fake_engine(raises=ProviderError("rate limited"))

    result = engine.classify_file(str(invoice), file_id="f9")
    assert result.category == Category.UNKNOWN
    assert result.fallback_used is True
    assert result.fallback_reason == "provider_exception"
    assert result.error_detail is not None
    assert "rate limited" in result.error_detail


def test_engine_fallback_on_invalid_category_response(tmp_path):
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    response = ProviderResponse(
        result=ClassificationResult(category="TotallyMadeUpCategory"),
        metadata=ProviderMetadata(provider_name="claude_live"),
    )
    engine, provider = _fake_engine(response=response)

    result = engine.classify_file(str(invoice), file_id="f10")
    assert result.category == Category.UNKNOWN
    assert result.fallback_used is True
    assert result.fallback_reason == "invalid_response"
    # No exception was raised here, but the offending value is still diagnostically
    # useful and safe to log (it's the provider's own answer, not file content).
    assert result.error_detail is not None
    assert "TotallyMadeUpCategory" in result.error_detail


def test_engine_fallback_on_extraction_failure(tmp_path):
    garbage = tmp_path / "garbage.pdf"
    garbage.write_bytes(b"%PDF-1.4 NOT REALLY A PDF \x00\x01\x02")

    engine, provider = _fake_engine()
    result = engine.classify_file(str(garbage), file_id="f11")
    assert result.category == Category.UNKNOWN
    assert result.fallback_used is True
    assert result.fallback_reason == "extraction_failed"
    assert provider.received_requests == []
    # F6 (release audit, 2026-07-06): a file whose extraction raised genuinely has no
    # extractable text — the signal must reflect that instead of staying at its
    # all-default False.
    assert result.classification_signals.no_extractable_text is True
    # F3: the real exception message must be captured, not just the reason code.
    assert result.error_detail is not None


def test_engine_processing_time_is_always_recorded():
    engine, provider = _fake_engine()
    result = engine.classify_file("installer.dmg", file_id="f12")
    assert isinstance(result.processing_time_ms, int)
    assert result.processing_time_ms >= 0


def test_engine_degrades_gracefully_if_ever_run_with_claude_live_classifier():
    """ClaudeLiveClassifier.classify() raises NotImplementedError by design (it's a
    documented placeholder — see its docstring). The Engine's provider-call error
    handling (design §11) catches ANY exception from the provider, including this one,
    and falls back to Unknown rather than propagating it — a deliberate safety
    property: even a misconfigured/placeholder provider can't crash a batch. This is
    not the normal way ClaudeLiveClassifier gets exercised (real runs use live Claude
    judgment, not this code path) — it's a defense-in-depth check."""
    engine = ClassificationEngine(ClaudeLiveClassifier())
    result = engine.classify_file(
        str(_SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"), file_id="f13"
    )
    assert result.category == Category.UNKNOWN
    assert result.fallback_used is True
    assert result.fallback_reason == "provider_exception"


# --- classify_batch() — Module 02's batch orchestration ---

def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


def _discovered_record(current_path: str, file_id: str = "f1", status: str = "discovered") -> FileRecord:
    return FileRecord(
        file_id=file_id, source_id="downloads", original_name=Path(current_path).name,
        original_path=current_path, current_path=current_path, extension=Path(current_path).suffix,
        status=status, batch_id="batch-1",
    )


def test_classify_batch_persists_category_and_signals(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _discovered_record("installer.dmg")

    response = None  # never used — deterministic path
    provider = FakeClassificationProvider(response=response)
    result = classify_batch([record], provider=provider)

    assert result[0].category == Category.APPLICATION
    assert result[0].classification_signals is not None

    loaded = database_module.load_metadata_store()
    assert loaded[0].category == Category.APPLICATION


def test_classify_batch_skips_unreadable_records_untouched(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _discovered_record("locked_file.pdf", status="unreadable")

    result = classify_batch([record], provider=FakeClassificationProvider())

    assert result[0].category is None
    assert result[0].classification_signals is None
    # Untouched records are never even saved by Module 02 — nothing to load:
    assert database_module.load_metadata_store() == []


def test_classify_batch_writes_a_classify_action_log_entry(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _discovered_record("archive.zip")

    classify_batch([record], provider=FakeClassificationProvider())

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    assert len(log_lines) == 1
    entry = json.loads(log_lines[0])
    assert entry["action"] == "classify"
    assert entry["details"]["category"] == "Archive"
    assert entry["details"]["mode"] == "deterministic"
    assert entry["details"]["fallback_used"] is False
    assert "provider_metadata" not in entry["details"]  # no provider was called


def test_classify_batch_logs_provider_metadata_when_a_provider_is_called(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    invoice_path = str(_SAMPLES / "Invoices" / "sample_invoice_amazon.pdf")
    record = _discovered_record(invoice_path)

    response = ProviderResponse(
        result=ClassificationResult(category="Invoice"),
        metadata=ProviderMetadata(provider_name="claude_live", model="claude-sonnet-5"),
    )
    classify_batch([record], provider=FakeClassificationProvider(response=response))

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entry = json.loads(log_lines[0])
    assert entry["details"]["provider_metadata"]["provider_name"] == "claude_live"
    assert entry["details"]["provider_metadata"]["model"] == "claude-sonnet-5"


def test_classify_batch_gracefully_falls_back_for_a_vanished_image_file(tmp_path, monkeypatch):
    """A file whose current_path no longer points to a readable file (e.g. deleted
    between Module 01's scan and Module 02 running) used to raise all the way out of
    ClassificationEngine.classify_file() for the deterministic image-split path,
    caught only by classify_batch()'s outer safety net — leaving the file entirely
    unclassified (category stayed None, an "error" log entry instead of a real
    "classify" entry). Found during Module 02 integration testing (Tests/Large
    Batch/'s synthetic .jpg/.png fixtures aren't real image content, which triggered
    this same path at a realistic batch volume) and fixed: classify_file() now wraps
    the image-split branch the same way it already wrapped the text-bearing branch,
    so this degrades to Category.UNKNOWN with a real classify log entry, exactly like
    every other known failure mode."""
    _isolate_storage(tmp_path, monkeypatch)
    vanished_image = _discovered_record(str(tmp_path / "does_not_exist.jpg"), file_id="gone")
    normal_record = _discovered_record("installer.dmg", file_id="fine")

    result = classify_batch([vanished_image, normal_record], provider=FakeClassificationProvider())

    # The batch didn't abort — the second, valid record was still classified:
    assert result[1].category == Category.APPLICATION
    # The vanished image file now degrades gracefully instead of being left blank:
    assert result[0].category == Category.UNKNOWN

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = {json.loads(line)["file_id"]: json.loads(line) for line in log_lines}
    assert entries["gone"]["action"] == "classify"
    assert entries["gone"]["details"]["fallback_used"] is True
    assert entries["gone"]["details"]["fallback_reason"] == "unreadable_content"
    # F3 (release audit, 2026-07-06): the actual exception (e.g. FileNotFoundError)
    # must reach the action log, not just the fixed reason code.
    assert "error_detail" in entries["gone"]["details"]
    assert entries["gone"]["details"]["error_detail"]
    assert entries["fine"]["action"] == "classify"
    assert "error_detail" not in entries["fine"]["details"]


def test_classify_batch_outer_safety_net_still_covers_truly_unanticipated_failures(tmp_path, monkeypatch):
    """With the image-split path now wrapped too (see the test above), every failure
    mode ClassificationEngine can anticipate degrades gracefully on its own —
    classify_batch()'s outer try/except is genuinely last-resort defense-in-depth now,
    not a substitute for real handling. Confirmed here by forcing a failure the Engine
    could never have anticipated (an internal routing function itself raising), which
    still can't crash the batch."""
    _isolate_storage(tmp_path, monkeypatch)
    import src.pipeline.classification as classification_module

    def _always_raises(path):
        raise RuntimeError("simulated totally unanticipated internal failure")

    monkeypatch.setattr(classification_module, "classify_by_extension", _always_raises)

    broken_record = _discovered_record("installer.dmg", file_id="broken")
    result = classify_batch([broken_record], provider=FakeClassificationProvider())

    assert result[0].category is None  # never classified — the Engine itself raised
    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines]
    assert entries[0]["action"] == "error"
    assert entries[0]["details"]["stage"] == "classification"


# --- Module Contract regression tests (design §16/§19 — promised but never built
# until the 2026-07-06 release audit, F2). Permanent guardrails against exactly the
# two failure modes that audit's findings surfaced. ---

def test_classify_batch_leaves_every_non_owned_field_byte_identical(tmp_path, monkeypatch):
    """Module Contract immutability test (design §16: "assert every field outside
    Module 02's Module Contract guarantees is byte-identical before and after a
    record passes through Module 02"). Previously only spot-checked a handful of
    named fields (see M02-F05 in Tests/Module 02 Integration Test Plan.md) — this is
    the general, exhaustive version the frozen design actually committed to, covering
    every field on FileRecord except the two Module 02 owns.

    Every non-owned field is set to a distinctive, non-default value up front,
    including fields later modules would normally own (e.g. suggested_name,
    confidence_score), to prove Module 02 doesn't touch them even if a future bug
    ever tried to."""
    _isolate_storage(tmp_path, monkeypatch)
    real_file = str(_PROJECT_ROOT / "Tests" / "Small Batch" / "archive.zip")

    record = FileRecord(
        file_id="contract-test-id",
        source_id="contract-source",
        original_name="archive.zip",
        original_path="arbitrary/original/path.zip",
        current_path=real_file,
        extension=".zip",
        mime_type="application/zip",
        size_bytes=12345,
        created_at="2020-01-01T00:00:00Z",
        modified_at="2020-01-02T00:00:00Z",
        content_hash="deadbeef" * 8,
        discovered_at="2020-01-03T00:00:00Z",
        status="discovered",
        error=None,
        category=None,
        classification_signals=None,
        extracted_metadata={"foo": "bar"},
        suggested_name="already_set_name.zip",
        suggested_destination="Documents/Somewhere",
        duplicate_of="some-other-file-id",
        version_group_id="vg-1",
        version_rank="latest",
        confidence_score=77,
        confidence_breakdown={"some_deduction": -5},
        tier="approval_required",
        batch_id="batch-contract-test",
        processed_at="2020-01-04T00:00:00Z",
        approved_by="user",
        approved_at="2020-01-05T00:00:00Z",
        reversible=False,
    )

    before = asdict(record)
    classify_batch([record], provider=FakeClassificationProvider())
    after = asdict(record)

    owned_fields = {"category", "classification_signals"}
    for field_name in before:
        if field_name in owned_fields:
            continue
        assert after[field_name] == before[field_name], (
            f"Module 02 modified {field_name!r}, which it does not own per "
            f"MODULE_CONTRACT.md's DOES NOT MODIFY list"
        )

    # Confirm Module 02 actually did its job on the two fields it does own —
    # otherwise this test would trivially pass by classify_batch() doing nothing.
    assert after["category"] == Category.ARCHIVE.value
    assert after["classification_signals"] is not None


def test_every_module01_supported_extension_is_routed_by_module02():
    """Extension-mapping drift test (design §19: "An extension Module 01 considers
    supported but Rules/Classification Rules.md's Pass 1 table doesn't map ... a
    contract test should catch this drift before it ships"). Iterates Module 01's
    real SUPPORTED_EXTENSIONS and confirms Module 02 routes every one of them
    somewhere meaningful -- a deterministic category, the screenshot/image split, or
    the text-bearing deep pass -- rather than silently falling through to the
    catch-all "no mapping found" Unknown path in ClassificationEngine.classify_file().

    This specific test would not have caught the F4 finding (.tar was missing from
    Module 02's map, but .tar isn't in Module 01's SUPPORTED_EXTENSIONS either, so
    it can't reach Module 02 today regardless) -- see
    test_extension_category_map_matches_rules_taxonomy() below for the complementary
    check that guards against that specific regression."""
    unrouted = []
    for extension in watch_ingest_module.SUPPORTED_EXTENSIONS:
        sample_path = f"file{extension}"
        routed = (
            classify_by_extension(sample_path) is not None
            or needs_screenshot_split(sample_path)
            or is_text_bearing(sample_path)
        )
        if not routed:
            unrouted.append(extension)

    assert unrouted == [], (
        f"Module 01 can discover {unrouted} but Module 02 has no routing for "
        f"{'them' if len(unrouted) > 1 else 'it'} — every extension in "
        f"watch_ingest.SUPPORTED_EXTENSIONS must be mapped in classification.py "
        f"(the extension map, the image extensions, or the text-bearing extensions), "
        f"or it will silently classify as Unknown with no Rules/Classification "
        f"Rules.md-backed reason."
    )


def test_extension_category_map_matches_rules_taxonomy():
    """Companion to the drift test above, guarding specifically against the F4
    regression (release audit, 2026-07-06): _EXTENSION_CATEGORY_MAP silently dropped
    .tar despite Rules/Classification Rules.md's Pass 1 table listing it under
    Archive, undetected until a manual audit found it. Rules/Classification Rules.md
    isn't machine-readable (no YAML mirror, by deliberate v1 design — see
    src/README.md), so this hardcodes the document's Pass 1 table as the expected
    mapping; if the Rules doc's table changes, this test and the doc need updating
    together, same discipline as the Category enum itself (design §10)."""
    expected_by_extension = {
        ".exe": Category.APPLICATION, ".dmg": Category.APPLICATION,
        ".pkg": Category.APPLICATION, ".msi": Category.APPLICATION,
        ".zip": Category.ARCHIVE, ".rar": Category.ARCHIVE,
        ".7z": Category.ARCHIVE, ".tar": Category.ARCHIVE, ".gz": Category.ARCHIVE,
        ".mp4": Category.VIDEO, ".mov": Category.VIDEO,
        ".mkv": Category.VIDEO, ".avi": Category.VIDEO,
        ".mp3": Category.AUDIO, ".wav": Category.AUDIO,
        ".m4a": Category.AUDIO, ".flac": Category.AUDIO,
    }
    for extension, expected_category in expected_by_extension.items():
        actual = classify_by_extension(f"file{extension}")
        assert actual == expected_category, (
            f"Rules/Classification Rules.md maps {extension} to {expected_category}, "
            f"but classify_by_extension() returned {actual}"
        )
