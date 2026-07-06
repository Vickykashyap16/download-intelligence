"""
Unit tests for models/classification.py (Category, ClassificationSignals).

Run with: pytest src/models/test_classification.py -v
"""

import json

from src.models.classification import Category, ClassificationSignals


def test_category_has_all_twelve_v1_values():
    expected = {
        "Invoice", "Resume", "Bank Statement", "Contract", "Document",
        "Image", "Screenshot", "Application", "Archive", "Video", "Audio", "Unknown",
    }
    actual = {member.value for member in Category}
    assert actual == expected


def test_category_members_are_plain_strings():
    """str, Enum mixin — every member IS a str instance, not just str-like."""
    assert isinstance(Category.INVOICE, str)
    assert Category.INVOICE == "Invoice"


def test_category_serializes_to_json_without_a_custom_encoder():
    payload = {"category": Category.BANK_STATEMENT}
    serialized = json.dumps(payload)
    assert serialized == '{"category": "Bank Statement"}'


def test_category_construction_from_string_round_trips():
    assert Category("Invoice") is Category.INVOICE
    assert Category("Unknown") is Category.UNKNOWN


def test_classification_signals_defaults_are_all_unremarkable():
    signals = ClassificationSignals()
    assert signals.ambiguous is False
    assert signals.multi_document_detected is False
    assert signals.no_extractable_text is False
    assert signals.non_english_detected is False
    assert signals.detected_language is None
    assert signals.locked is False


def test_classification_signals_can_be_constructed_with_specific_values():
    signals = ClassificationSignals(locked=True, ambiguous=True)
    assert signals.locked is True
    assert signals.ambiguous is True
    # Untouched fields stay at their defaults:
    assert signals.non_english_detected is False
    assert signals.detected_language is None
