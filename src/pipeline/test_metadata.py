"""
Unit tests for pipeline/metadata.py — Module 03 (Metadata Extraction).

Structured the same way test_classification.py is: taxonomy tests, deterministic-
extractor tests, provider-boundary tests, MetadataExtractionEngine tests (one section
per category group — deterministic-only, image-family, text-bearing), fallback/
redaction/timestamp-hierarchy tests, then extract_metadata_batch() orchestration
tests, then the Module Contract and taxonomy-drift regression tests.

Run with: pytest src/pipeline/test_metadata.py -v
"""

import json
import re
from dataclasses import asdict
from pathlib import Path

import pytest

from src.models.classification import Category, ClassificationSignals
import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.file_record import FileRecord
from src.pipeline.metadata import (
    ClaudeLiveExtractor,
    MetadataExtractionEngine,
    MetadataExtractionProvider,
    MetadataExtractionRequest,
    OPTIONAL_FIELDS,
    ProviderError,
    ProviderMetadata,
    ProviderResponse,
    ProviderUnavailableError,
    REQUIRED_FIELDS,
    all_fields_for,
    extract_metadata_batch,
    is_extraction_complete,
    optional_fields,
    required_fields,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SAMPLES = _PROJECT_ROOT / "Samples"


class FakeMetadataExtractionProvider(MetadataExtractionProvider):
    """Test double used throughout this suite — returns a canned ProviderResponse
    instead of ever calling a real provider, per design §20's Test Strategy, mirroring
    test_classification.py's FakeClassificationProvider exactly."""

    def __init__(self, response: ProviderResponse = None, raises: Exception = None):
        self._response = response
        self._raises = raises
        self.received_requests = []

    def extract(self, request: MetadataExtractionRequest) -> ProviderResponse:
        self.received_requests.append(request)
        if self._raises is not None:
            raise self._raises
        return self._response


def _fake_engine(response=None, raises=None):
    provider = FakeMetadataExtractionProvider(response=response, raises=raises)
    return MetadataExtractionEngine(provider), provider


def _classified_record(current_path: str, category: Category, file_id: str = "f1",
                        status: str = "discovered", classification_signals=None) -> FileRecord:
    return FileRecord(
        file_id=file_id, source_id="downloads", original_name=Path(current_path).name,
        original_path=current_path, current_path=current_path,
        extension=Path(current_path).suffix, status=status, category=category,
        classification_signals=classification_signals or ClassificationSignals(),
        batch_id="batch-1",
    )


# --- Metadata taxonomy (§7) ---

def test_every_non_unknown_category_has_a_taxonomy_entry():
    """Taxonomy-drift guard (design §20): every category Module 03 is expected to
    process has a defined required-field list, and it's never empty — an empty
    required list would mean minimum-acceptable-extraction (§7) could never fail,
    silently defeating the "extraction_complete" concept."""
    for category in Category:
        if category == Category.UNKNOWN:
            continue
        assert category in REQUIRED_FIELDS, f"{category} missing from REQUIRED_FIELDS"
        assert category in OPTIONAL_FIELDS, f"{category} missing from OPTIONAL_FIELDS"
        assert len(required_fields(category)) >= 1, f"{category} has zero required fields"


def test_unknown_category_deliberately_excluded_from_taxonomy():
    assert Category.UNKNOWN not in REQUIRED_FIELDS
    assert Category.UNKNOWN not in OPTIONAL_FIELDS


def test_required_and_optional_fields_never_overlap_for_the_same_category():
    for category in Category:
        overlap = set(required_fields(category)) & set(optional_fields(category))
        assert overlap == set(), f"{category} lists {overlap} as both required and optional"


def test_all_fields_for_is_required_plus_optional():
    assert all_fields_for(Category.INVOICE) == required_fields(Category.INVOICE) + optional_fields(Category.INVOICE)


# --- Confidence Rules citation / design-doc drift guard (design §20, implementation
# audit F2): the taxonomy-drift test §20 committed to but that was never built. This
# implements it in two parts, since Rules/Confidence Rules.md doesn't itself
# enumerate field names — it cites a document as its source of truth for "required
# fields per category" — so the drift guard has to (a) confirm that citation still
# points at the current, correct source, and (b) confirm that source's own table
# still agrees with the code taxonomy field-for-field. Together these close the
# exact gap that let the citation silently drift onto a superseded document
# (the retired `03 Metadata Extraction.md` pointer note) until this audit caught it. ---

_CONFIDENCE_RULES_PATH = _PROJECT_ROOT / "Rules" / "Confidence Rules.md"
_DESIGN_DOC_PATH = _PROJECT_ROOT / "Build-out" / "03 Metadata Extraction" / "Module 03 Design.md"

_DESIGN_TABLE_CATEGORY_NAMES = {
    "Invoice": Category.INVOICE,
    "Resume": Category.RESUME,
    "Bank Statement": Category.BANK_STATEMENT,
    "Contract": Category.CONTRACT,
    "Document (generic)": Category.DOCUMENT,
    "Image / product photo": Category.IMAGE,
    "Screenshot": Category.SCREENSHOT,
    "Application (installer)": Category.APPLICATION,
    "Archive": Category.ARCHIVE,
    "Video": Category.VIDEO,
    "Audio": Category.AUDIO,
}


def _parse_design_doc_taxonomy_table() -> dict:
    """Parse §7 ("Per-category fields")'s markdown table directly out of Module 03
    Design.md, keyed by Category — the same table Rules/Confidence Rules.md's
    deduction math now cites as its source of truth. Scoped to the §7 table
    specifically (between its heading and the next `##` heading) so this can't be
    confused with §9's unrelated table, which also has a row starting with
    "Bank Statement"."""
    text = _DESIGN_DOC_PATH.read_text(encoding="utf-8")
    parsed = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("### Per-category fields"):
            in_table = True
            continue
        if in_table and line.startswith("##"):
            break
        if not in_table or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] not in _DESIGN_TABLE_CATEGORY_NAMES:
            continue
        required = re.findall(r"`([a-z0-9_]+)`", cells[1]) if len(cells) > 1 else []
        optional = re.findall(r"`([a-z0-9_]+)`", cells[2]) if len(cells) > 2 else []
        parsed[_DESIGN_TABLE_CATEGORY_NAMES[cells[0]]] = (set(required), set(optional))
    return parsed


def test_confidence_rules_metadata_citation_points_to_the_current_taxonomy_source():
    """Verifies Rules/Confidence Rules.md's "required fields defined per category"
    citation points at the current authoritative taxonomy source (Module 03
    Design.md §7), not a superseded document. This is the exact citation that had
    drifted onto the retired `03 Metadata Extraction.md` pointer note until the
    Module 03 implementation audit found and fixed it — this test exists so that
    drift can't happen silently again."""
    text = _CONFIDENCE_RULES_PATH.read_text(encoding="utf-8")
    match = re.search(r"required fields defined per category in `([^`]+)`", text)
    assert match is not None, (
        "Rules/Confidence Rules.md's citation sentence was not found at all — "
        "either the wording changed or the citation was removed."
    )

    cited_path = match.group(1)
    assert cited_path == "Build-out/03 Metadata Extraction/Module 03 Design.md", (
        f"Rules/Confidence Rules.md cites {cited_path!r}, not the current "
        "authoritative taxonomy source. If the taxonomy has since been promoted "
        "into Rules/Metadata Rules.md per Module 03 Design.md §10, update both the "
        "citation and this assertion together — don't let this test go stale too."
    )
    assert (_PROJECT_ROOT / cited_path).exists(), (
        f"Rules/Confidence Rules.md cites {cited_path!r}, which doesn't exist."
    )


def test_design_doc_taxonomy_table_matches_code_taxonomy_exactly():
    """The other half of the same drift guard: confirms §7's own table — the
    content the citation above actually points at — still agrees field-for-field
    with REQUIRED_FIELDS/OPTIONAL_FIELDS in code, rather than trusting the two were
    kept in sync by hand."""
    parsed = _parse_design_doc_taxonomy_table()

    for category in Category:
        if category == Category.UNKNOWN:
            continue
        assert category in parsed, f"{category} missing from Module 03 Design.md §7's table"
        design_required, design_optional = parsed[category]
        assert design_required == set(required_fields(category)), (
            f"{category}: Design.md §7 lists required {design_required}, "
            f"code defines {set(required_fields(category))} — taxonomy has drifted."
        )
        assert design_optional == set(optional_fields(category)), (
            f"{category}: Design.md §7 lists optional {design_optional}, "
            f"code defines {set(optional_fields(category))} — taxonomy has drifted."
        )


def test_is_extraction_complete_true_only_when_every_required_field_present():
    complete = {"vendor": "Amazon", "invoice_date": "2026-07-05", "amount": None}
    incomplete = {"vendor": "Amazon", "invoice_date": None, "amount": 5.0}
    assert is_extraction_complete(Category.INVOICE, complete) is True
    assert is_extraction_complete(Category.INVOICE, incomplete) is False


def test_is_extraction_complete_true_for_archive_which_has_no_optional_fields():
    assert optional_fields(Category.ARCHIVE) == ()
    assert is_extraction_complete(Category.ARCHIVE, {"contents_summary": "a, b"}) is True
    assert is_extraction_complete(Category.ARCHIVE, {"contents_summary": None}) is False


# --- Provider boundary: dataclasses, ABC enforcement, ClaudeLiveExtractor placeholder ---

def test_metadata_extraction_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        MetadataExtractionProvider()


def test_fake_provider_satisfies_the_abstract_interface():
    fake = FakeMetadataExtractionProvider(
        response=ProviderResponse(fields={"vendor": "Amazon"}, metadata=ProviderMetadata(provider_name="fake"))
    )
    request = MetadataExtractionRequest(
        file_id="f1", path="/tmp/invoice.pdf", extracted_text="some text", mode="text",
        fields_requested=["vendor"],
    )
    response = fake.extract(request)
    assert response.fields == {"vendor": "Amazon"}
    assert fake.received_requests == [request]


def test_claude_live_extractor_raises_documented_placeholder():
    provider = ClaudeLiveExtractor()
    request = MetadataExtractionRequest(
        file_id="f1", path="/tmp/invoice.pdf", extracted_text="some text", mode="text",
    )
    with pytest.raises(NotImplementedError, match="fulfilled live by Claude"):
        provider.extract(request)


def test_metadata_extraction_request_defaults():
    request = MetadataExtractionRequest(file_id="f1", path="/tmp/x.pdf", extracted_text=None, mode="vision")
    assert request.mime_type is None
    assert request.fields_requested == []


def test_provider_response_carries_fields_and_metadata():
    response = ProviderResponse(
        fields={"vendor": "Amazon", "amount": 42.5},
        metadata=ProviderMetadata(provider_name="claude_live", model="claude-sonnet-5", latency_ms=10),
    )
    assert response.fields["vendor"] == "Amazon"
    assert response.metadata.provider_name == "claude_live"
    assert response.metadata.reasoning is None


# --- Engine: deterministic-only categories (Archive, Application, Video, Audio) ---

def test_engine_archive_deterministic_no_provider_call():
    real_archive = str(_PROJECT_ROOT / "Tests" / "Small Batch" / "archive.zip")
    record = _classified_record(real_archive, Category.ARCHIVE, file_id="arc1")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.mode == "deterministic"
    assert result.extracted_metadata["contents_summary"]
    assert provider.received_requests == []
    assert result.extraction_complete is True


def test_engine_archive_empty_archive_is_found_not_null(tmp_path):
    """A genuinely empty (but successfully opened) archive is a found, complete
    result ("" — nothing to summarize) — distinct from a corrupted archive, which is
    null/incomplete/fallback. Collapsing the two would make a rare-but-valid empty
    zip indistinguishable from a corrupted one."""
    import zipfile

    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w"):
        pass

    record = _classified_record(str(empty_zip), Category.ARCHIVE, file_id="arc-empty")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.extracted_metadata["contents_summary"] == ""
    assert result.fallback_used is False
    assert result.extraction_complete is True  # "" is not None — found, just empty


def test_engine_archive_fallback_on_corrupted_archive(tmp_path):
    fake_zip = tmp_path / "corrupt.zip"
    fake_zip.write_bytes(b"not really a zip file at all")
    record = _classified_record(str(fake_zip), Category.ARCHIVE, file_id="arc-bad")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.fallback_used is True
    assert result.fallback_reason == "extraction_failed"
    assert result.extracted_metadata["contents_summary"] is None
    assert result.extraction_complete is False
    assert result.error_detail is not None
    assert provider.received_requests == []


def test_engine_application_filename_parsing_extracts_name_version_platform():
    record = _classified_record("Zoom_6.1_Mac.pkg", Category.APPLICATION, file_id="app1")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.mode == "deterministic"
    assert result.extracted_metadata["app_name"] == "Zoom"
    assert result.extracted_metadata["version"] == "6.1"
    assert result.extracted_metadata["platform"] == "Mac"
    assert provider.received_requests == []


def test_engine_application_filename_parsing_falls_back_to_stem_when_unparseable():
    record = _classified_record("installer123.exe", Category.APPLICATION, file_id="app2")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.extracted_metadata["app_name"] == "installer123"
    assert result.extracted_metadata["version"] is None
    assert result.extracted_metadata["platform"] is None


def test_engine_video_description_from_filename_no_provider_call_ever():
    record = _classified_record("Product_Demo_2026-07-05.mp4", Category.VIDEO, file_id="vid1")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.mode == "deterministic"
    assert result.extracted_metadata["description"] == "Product_Demo_2026-07-05"
    assert provider.received_requests == []


def test_engine_video_duration_and_content_date_always_null_in_v1():
    """§9A: no tier-1/tier-3 timestamp or duration source is implemented for Video —
    these fields must never be silently populated from anything, including
    FileRecord.modified_at."""
    record = _classified_record("clip.mov", Category.VIDEO, file_id="vid2")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.extracted_metadata["duration"] is None
    assert result.extracted_metadata["content_date"] is None


def test_engine_audio_recording_date_populated_when_tag_present(monkeypatch):
    import src.pipeline.metadata as metadata_module

    monkeypatch.setattr(
        metadata_module, "read_audio_tags",
        lambda path: {"track_title": "Song", "artist": "Artist", "duration": 200, "recording_date": "2023-01-01"},
    )
    record = _classified_record("track.mp3", Category.AUDIO, file_id="aud1")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.extracted_metadata["recording_date"] == "2023-01-01"
    assert result.extracted_metadata["track_title"] == "Song"
    assert provider.received_requests == []


def test_engine_audio_track_title_falls_back_to_filename_when_tag_absent(monkeypatch):
    import src.pipeline.metadata as metadata_module

    monkeypatch.setattr(
        metadata_module, "read_audio_tags",
        lambda path: {"track_title": None, "artist": None, "duration": None, "recording_date": None},
    )
    record = _classified_record("track_two.mp3", Category.AUDIO, file_id="aud2")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.extracted_metadata["track_title"] == "track_two"  # filename fallback (§19)
    assert result.extracted_metadata["recording_date"] is None  # never filesystem-sourced (§9A)


def test_engine_audio_fallback_on_unparseable_file():
    placeholder = str(_PROJECT_ROOT / "Tests" / "Small Batch" / "audio_clip.mp3")
    record = _classified_record(placeholder, Category.AUDIO, file_id="aud-bad")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.fallback_used is True
    assert result.fallback_reason == "extraction_failed"
    assert result.extracted_metadata["track_title"] is None


# --- Engine: Image / Screenshot (capture_date deterministic + vision provider call) ---

def test_engine_screenshot_mixed_mode_vision_request_excludes_capture_date():
    screenshot = _SAMPLES / "Images" / "sample_screenshot_login_error.png"
    response = ProviderResponse(
        fields={"context_description": "Login error dialog"},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(screenshot), Category.SCREENSHOT, file_id="ss1")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.mode == "mixed"
    assert result.extracted_metadata["context_description"] == "Login error dialog"
    assert len(provider.received_requests) == 1
    request = provider.received_requests[0]
    assert request.mode == "vision"
    assert "capture_date" not in request.fields_requested  # deterministic field, never requested


def test_engine_image_capture_date_never_falls_back_to_filesystem_time(tmp_path):
    from PIL import Image

    photo = tmp_path / "no_exif_photo.jpg"
    Image.new("RGB", (4032, 3024)).save(photo)  # a real resolution, genuinely no EXIF
    response = ProviderResponse(
        fields={"description": "a photo", "variant": None},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(photo), Category.IMAGE, file_id="img1")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["capture_date"] is None  # never silently substituted (§9A)


def test_engine_image_capture_date_populated_from_real_exif(tmp_path):
    from PIL import Image

    photo = tmp_path / "vacation.jpg"
    image = Image.new("RGB", (4032, 3024))
    exif = image.getexif()
    exif[271] = "Test Camera Co."       # Make
    exif[36867] = "2024:05:01 10:00:00"  # DateTimeOriginal
    image.save(photo, exif=exif)

    response = ProviderResponse(
        fields={"description": "a vacation photo"}, metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(photo), Category.IMAGE, file_id="img2")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["capture_date"] == "2024:05:01 10:00:00"


def test_engine_image_family_fallback_preserves_already_found_capture_date(tmp_path):
    """A provider failure must not discard a deterministic value the Engine already
    found before calling the provider (§12)."""
    from PIL import Image

    photo = tmp_path / "vacation2.jpg"
    image = Image.new("RGB", (4032, 3024))
    exif = image.getexif()
    exif[271] = "Test Camera Co."
    exif[36867] = "2024:05:01 10:00:00"
    image.save(photo, exif=exif)

    record = _classified_record(str(photo), Category.IMAGE, file_id="img-fail")
    engine, provider = _fake_engine(raises=ProviderUnavailableError("down"))

    result = engine.extract_file(record)
    assert result.fallback_used is True
    assert result.extracted_metadata["capture_date"] == "2024:05:01 10:00:00"  # preserved
    assert result.extracted_metadata["description"] is None  # judgment field, fell back


# --- Engine: text-bearing judgment categories (Invoice, Resume, Bank Statement,
# Contract, Document) ---

def test_engine_invoice_text_deep_pass_success():
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    response = ProviderResponse(
        fields={"vendor": "Amazon", "invoice_date": "2026-07-05", "amount": 1499.00, "currency": "INR"},
        metadata=ProviderMetadata(provider_name="claude_live", model="claude-sonnet-5"),
    )
    record = _classified_record(str(invoice), Category.INVOICE, file_id="inv1")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.mode == "text"
    assert result.extracted_metadata["vendor"] == "Amazon"
    assert result.extracted_metadata["amount"] == 1499.00
    assert result.extraction_complete is True
    assert result.provider_metadata.latency_ms is not None
    assert len(provider.received_requests) == 1
    assert set(provider.received_requests[0].fields_requested) == set(all_fields_for(Category.INVOICE))


def test_engine_resume_text_deep_pass_success():
    resume = _SAMPLES / "Documents" / "sample_resume_jordan_patel.docx"
    response = ProviderResponse(
        fields={"candidate_name": "Jordan Patel", "version_indicator": "v9"},
        metadata=ProviderMetadata(provider_name="claude_live"),
    )
    record = _classified_record(str(resume), Category.RESUME, file_id="res1")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["candidate_name"] == "Jordan Patel"
    assert result.extraction_complete is True


def test_engine_bank_statement_success_with_valid_account_last4():
    bank_pdf = _SAMPLES / "Documents" / "sample_bank_statement_chase.pdf"
    response = ProviderResponse(
        fields={"bank_name": "Chase", "statement_period": "2026-06", "account_last4": "4321"},
        metadata=ProviderMetadata(provider_name="claude_live"),
    )
    record = _classified_record(str(bank_pdf), Category.BANK_STATEMENT, file_id="bs1")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["account_last4"] == "4321"
    assert result.redacted_fields == []


def test_engine_contract_and_document_generic_success():
    contract = _SAMPLES / "Documents" / "sample_contract_nda.pdf"
    response = ProviderResponse(
        fields={"contract_type": "NDA", "counterparty": "Acme Corp", "effective_date": "2026-07-01"},
        metadata=ProviderMetadata(provider_name="claude_live"),
    )
    record = _classified_record(str(contract), Category.CONTRACT, file_id="con1")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["counterparty"] == "Acme Corp"

    manual = _SAMPLES / "Documents" / "sample_generic_document_manual.txt"
    response2 = ProviderResponse(
        fields={"best_guess_title": "User Manual: Espresso Machine"},
        metadata=ProviderMetadata(provider_name="claude_live"),
    )
    record2 = _classified_record(str(manual), Category.DOCUMENT, file_id="doc1")
    engine2, provider2 = _fake_engine(response=response2)
    result2 = engine2.extract_file(record2)
    assert result2.extracted_metadata["best_guess_title"] == "User Manual: Espresso Machine"


def test_engine_vision_fallback_for_scanned_pdf(tmp_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    scanned = tmp_path / "scanned.pdf"
    c = canvas.Canvas(str(scanned), pagesize=letter)
    c.rect(100, 100, 50, 50, fill=1)  # a shape, not text — commits a real page
    c.save()

    response = ProviderResponse(
        fields={"best_guess_title": "Scanned document"},
        metadata=ProviderMetadata(provider_name="claude_live"),
    )
    record = _classified_record(str(scanned), Category.DOCUMENT, file_id="doc-scanned")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.mode == "vision"
    assert provider.received_requests[0].mode == "vision"
    assert provider.received_requests[0].extracted_text is None


def test_engine_non_pdf_text_bearing_with_no_content_skips_provider(tmp_path):
    empty_ish = tmp_path / "practically_empty.txt"
    empty_ish.write_text("   ")

    record = _classified_record(str(empty_ish), Category.DOCUMENT, file_id="doc-empty")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.extracted_metadata["best_guess_title"] is None
    assert result.extraction_complete is False
    assert provider.received_requests == []


# --- Fallback-specific tests ---

def test_engine_fallback_on_provider_unavailable_for_text_bearing():
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    record = _classified_record(str(invoice), Category.INVOICE, file_id="inv-fail1")
    engine, provider = _fake_engine(raises=ProviderUnavailableError("network down"))

    result = engine.extract_file(record)
    assert result.fallback_used is True
    assert result.fallback_reason == "provider_exception"
    assert result.error_detail is not None
    assert "network down" in result.error_detail
    assert all(value is None for value in result.extracted_metadata.values())
    assert result.extraction_complete is False


def test_engine_fallback_on_provider_error_for_text_bearing():
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    record = _classified_record(str(invoice), Category.INVOICE, file_id="inv-fail2")
    engine, provider = _fake_engine(raises=ProviderError("rate limited"))

    result = engine.extract_file(record)
    assert result.fallback_used is True
    assert result.fallback_reason == "provider_exception"
    assert "rate limited" in result.error_detail


def test_engine_fallback_on_extraction_failure_for_text_bearing(tmp_path):
    garbage = tmp_path / "garbage.pdf"
    garbage.write_bytes(b"%PDF-1.4 NOT REALLY A PDF \x00\x01\x02")

    record = _classified_record(str(garbage), Category.INVOICE, file_id="inv-garbage")
    engine, provider = _fake_engine()

    result = engine.extract_file(record)
    assert result.fallback_used is True
    assert result.fallback_reason == "extraction_failed"
    assert provider.received_requests == []
    assert result.error_detail is not None


def test_engine_degrades_gracefully_if_ever_run_with_claude_live_extractor():
    engine = MetadataExtractionEngine(ClaudeLiveExtractor())
    record = _classified_record(
        str(_SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"), Category.INVOICE, file_id="inv-live",
    )
    result = engine.extract_file(record)
    assert result.fallback_used is True
    assert result.fallback_reason == "provider_exception"


# --- Closed taxonomy / type validation (§12/§18) ---

def test_provider_extra_unrequested_field_is_dropped_not_merged():
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    response = ProviderResponse(
        fields={"vendor": "Amazon", "invoice_date": "2026-07-05", "ssn": "123-45-6789"},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(invoice), Category.INVOICE, file_id="inv-extra")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert "ssn" not in result.extracted_metadata
    assert result.extracted_metadata["vendor"] == "Amazon"


def test_provider_wrong_type_field_treated_as_not_found():
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    response = ProviderResponse(
        fields={"vendor": "Amazon", "invoice_date": "2026-07-05", "amount": ["not", "a", "number"]},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(invoice), Category.INVOICE, file_id="inv-wrongtype")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["amount"] is None


# --- Boolean-value validation (implementation audit F1): Python's `bool` is a
# subclass of `int`, so a naive `isinstance(value, (str, int, float))` check would
# wrongly accept True/False as a valid field value. No field in the taxonomy (§7) is
# boolean, so every bool must be treated as not-found, exactly like any other
# wrong-type answer (§12). ---

def test_provider_boolean_true_value_treated_as_not_found():
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    response = ProviderResponse(
        fields={"vendor": True, "invoice_date": "2026-07-05"},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(invoice), Category.INVOICE, file_id="inv-bool-true")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["vendor"] is None
    assert result.extracted_metadata["invoice_date"] == "2026-07-05"


def test_provider_boolean_false_value_treated_as_not_found():
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    response = ProviderResponse(
        fields={"vendor": "Amazon", "invoice_date": False},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(invoice), Category.INVOICE, file_id="inv-bool-false")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["invoice_date"] is None
    assert result.extracted_metadata["vendor"] == "Amazon"


def test_provider_mixed_valid_and_boolean_fields_only_boolean_dropped():
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    response = ProviderResponse(
        fields={
            "vendor": "Amazon", "invoice_date": "2026-07-05",
            "amount": 1499.00, "currency": True,
        },
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(invoice), Category.INVOICE, file_id="inv-bool-mixed")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["vendor"] == "Amazon"
    assert result.extracted_metadata["invoice_date"] == "2026-07-05"
    assert result.extracted_metadata["amount"] == 1499.00
    assert result.extracted_metadata["currency"] is None


def test_provider_boolean_judgment_field_does_not_overwrite_valid_deterministic_metadata(tmp_path):
    """A boolean returned for a judgment field must not disturb a sibling
    deterministic field already found for the same record (Image/Screenshot's
    capture_date, §9A) — the rejection is scoped to the one bad key, exactly like
    any other type-validation failure (§12)."""
    from PIL import Image

    photo = tmp_path / "vacation_bool.jpg"
    image = Image.new("RGB", (4032, 3024))
    exif = image.getexif()
    exif[271] = "Test Camera Co."
    exif[36867] = "2024:05:01 10:00:00"
    image.save(photo, exif=exif)

    response = ProviderResponse(
        fields={"description": True}, metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(photo), Category.IMAGE, file_id="img-bool")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["capture_date"] == "2024:05:01 10:00:00"  # untouched
    assert result.extracted_metadata["description"] is None  # boolean rejected


# --- Redaction-specific tests (§18's exact digit-count rule) ---

def test_redaction_5_digit_account_last4_is_redacted():
    bank_pdf = _SAMPLES / "Documents" / "sample_bank_statement_chase.pdf"
    response = ProviderResponse(
        fields={"bank_name": "Chase", "statement_period": "2026-06", "account_last4": "123456789"},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(bank_pdf), Category.BANK_STATEMENT, file_id="bs-redact")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["account_last4"] is None
    assert result.redacted_fields == ["account_last4"]


def test_redaction_4_digit_account_last4_passes_through_unchanged():
    bank_pdf = _SAMPLES / "Documents" / "sample_bank_statement_chase.pdf"
    response = ProviderResponse(
        fields={"bank_name": "Chase", "statement_period": "2026-06", "account_last4": "4321"},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(bank_pdf), Category.BANK_STATEMENT, file_id="bs-pass")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["account_last4"] == "4321"
    assert result.redacted_fields == []


def test_redaction_empty_account_last4_passes_through_not_counted_as_redacted():
    bank_pdf = _SAMPLES / "Documents" / "sample_bank_statement_chase.pdf"
    response = ProviderResponse(
        fields={"bank_name": "Chase", "statement_period": "2026-06", "account_last4": None},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(bank_pdf), Category.BANK_STATEMENT, file_id="bs-empty")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["account_last4"] is None
    assert result.redacted_fields == []


def test_redaction_scoped_only_to_account_last4_not_other_long_numeric_fields():
    """Proves the check is scoped to Bank Statement's account_last4 only — a long
    digit string in a *different* category's numeric field must never be redacted
    (design §18's over-engineering-avoidance reasoning, verified directly)."""
    invoice = _SAMPLES / "Invoices" / "sample_invoice_amazon.pdf"
    response = ProviderResponse(
        fields={"vendor": "Amazon", "invoice_date": "2026-07-05", "invoice_number": "123456789012"},
        metadata=ProviderMetadata(provider_name="fake"),
    )
    record = _classified_record(str(invoice), Category.INVOICE, file_id="inv-redact-scope")
    engine, provider = _fake_engine(response=response)

    result = engine.extract_file(record)
    assert result.extracted_metadata["invoice_number"] == "123456789012"


# --- extract_metadata_batch() — Module 03's batch orchestration ---

def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


def test_extract_metadata_batch_persists_extracted_metadata(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    real_archive = str(_PROJECT_ROOT / "Tests" / "Small Batch" / "archive.zip")
    record = _classified_record(real_archive, Category.ARCHIVE, file_id="batch-arc1")

    result = extract_metadata_batch([record], provider=FakeMetadataExtractionProvider())

    assert result[0].extracted_metadata["contents_summary"]
    loaded = database_module.load_metadata_store()
    assert loaded[0].extracted_metadata["contents_summary"]


def test_extract_metadata_batch_skips_unknown_category_untouched(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _classified_record("mystery.xyz", Category.UNKNOWN, file_id="unknown1")

    result = extract_metadata_batch([record], provider=FakeMetadataExtractionProvider())

    assert result[0].extracted_metadata == {}
    assert database_module.load_metadata_store() == []


def test_extract_metadata_batch_skips_none_category_untouched(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _classified_record("whatever.pdf", None, file_id="none-cat")
    record.category = None

    result = extract_metadata_batch([record], provider=FakeMetadataExtractionProvider())

    assert result[0].extracted_metadata == {}
    assert database_module.load_metadata_store() == []


def test_extract_metadata_batch_skips_non_discovered_status(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    record = _classified_record("locked.pdf", Category.UNKNOWN, file_id="unreadable1", status="unreadable")

    result = extract_metadata_batch([record], provider=FakeMetadataExtractionProvider())

    assert result[0].extracted_metadata == {}
    assert database_module.load_metadata_store() == []


def test_extract_metadata_batch_writes_an_extract_metadata_action_log_entry(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    real_archive = str(_PROJECT_ROOT / "Tests" / "Small Batch" / "archive.zip")
    record = _classified_record(real_archive, Category.ARCHIVE, file_id="batch-log1")

    extract_metadata_batch([record], provider=FakeMetadataExtractionProvider())

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    assert len(log_lines) == 1
    entry = json.loads(log_lines[0])
    assert entry["action"] == "extract_metadata"
    assert entry["details"]["category"] == "Archive"
    assert entry["details"]["mode"] == "deterministic"
    assert "contents_summary" in entry["details"]["fields_extracted"]
    assert entry["details"]["fallback_used"] is False
    assert entry["details"]["redacted_fields"] == []
    assert entry["details"]["extraction_complete"] is True
    assert "provider_metadata" not in entry["details"]  # no provider was called


def test_extract_metadata_batch_logs_provider_metadata_when_a_provider_is_called(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    invoice_path = str(_SAMPLES / "Invoices" / "sample_invoice_amazon.pdf")
    record = _classified_record(invoice_path, Category.INVOICE, file_id="batch-inv1")

    response = ProviderResponse(
        fields={"vendor": "Amazon", "invoice_date": "2026-07-05"},
        metadata=ProviderMetadata(provider_name="claude_live", model="claude-sonnet-5"),
    )
    extract_metadata_batch([record], provider=FakeMetadataExtractionProvider(response=response))

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entry = json.loads(log_lines[0])
    assert entry["details"]["provider_metadata"]["provider_name"] == "claude_live"
    assert "vendor" in entry["details"]["fields_extracted"]
    assert "invoice_number" in entry["details"]["fields_missing"]


def test_extract_metadata_batch_logs_redacted_fields_when_redaction_occurs(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    bank_path = str(_SAMPLES / "Documents" / "sample_bank_statement_chase.pdf")
    record = _classified_record(bank_path, Category.BANK_STATEMENT, file_id="batch-bs1")

    response = ProviderResponse(
        fields={"bank_name": "Chase", "statement_period": "2026-06", "account_last4": "123456789"},
        metadata=ProviderMetadata(provider_name="claude_live"),
    )
    extract_metadata_batch([record], provider=FakeMetadataExtractionProvider(response=response))

    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entry = json.loads(log_lines[0])
    assert entry["details"]["redacted_fields"] == ["account_last4"]
    assert "account_last4" in entry["details"]["fields_missing"]


def test_extract_metadata_batch_outer_safety_net_still_covers_unanticipated_failures(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    import src.pipeline.metadata as metadata_module

    def _always_raises(record):
        raise RuntimeError("simulated totally unanticipated internal failure")

    monkeypatch.setattr(MetadataExtractionEngine, "extract_file", _always_raises)

    real_archive = str(_PROJECT_ROOT / "Tests" / "Small Batch" / "archive.zip")
    broken_record = _classified_record(real_archive, Category.ARCHIVE, file_id="broken")

    result = extract_metadata_batch([broken_record], provider=FakeMetadataExtractionProvider())

    assert result[0].extracted_metadata == {}  # never touched — Engine itself raised
    log_lines = (tmp_path / "action_log.jsonl").read_text().strip().splitlines()
    entries = [json.loads(line) for line in log_lines]
    assert entries[0]["action"] == "error"
    assert entries[0]["details"]["stage"] == "metadata_extraction"


def test_extract_metadata_batch_does_not_abort_on_a_single_bad_file(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    real_archive = str(_PROJECT_ROOT / "Tests" / "Small Batch" / "archive.zip")
    bad_zip = tmp_path / "corrupt.zip"
    bad_zip.write_bytes(b"not a real zip")

    bad_record = _classified_record(str(bad_zip), Category.ARCHIVE, file_id="bad")
    good_record = _classified_record(real_archive, Category.ARCHIVE, file_id="good")

    result = extract_metadata_batch([bad_record, good_record], provider=FakeMetadataExtractionProvider())

    assert result[0].extracted_metadata["contents_summary"] is None
    assert result[1].extracted_metadata["contents_summary"]


# --- Module Contract regression test (design §20, built in from the start rather
# than added after a future audit finds it missing — §21) ---

def test_extract_metadata_batch_leaves_every_non_owned_field_byte_identical(tmp_path, monkeypatch):
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
        category=Category.ARCHIVE,
        classification_signals=ClassificationSignals(ambiguous=True),
        extracted_metadata={},
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
    extract_metadata_batch([record], provider=FakeMetadataExtractionProvider())
    after = asdict(record)

    owned_fields = {"extracted_metadata"}
    for field_name in before:
        if field_name in owned_fields:
            continue
        assert after[field_name] == before[field_name], (
            f"Module 03 modified {field_name!r}, which it does not own per "
            f"Module 03 Design.md §5's DOES NOT MODIFY list"
        )

    # Confirm Module 03 actually did its job — otherwise this test would trivially
    # pass by extract_metadata_batch() doing nothing.
    assert after["extracted_metadata"] != before["extracted_metadata"]
    assert after["extracted_metadata"]["contents_summary"]
