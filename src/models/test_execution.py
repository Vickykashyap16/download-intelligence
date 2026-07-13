"""
Unit tests for models/execution.py (ApprovalDecisionType, ApprovalDecision,
PreviewRow) — Module 07 (Preview, Approval & Execution), WP-1.

Run with: pytest src/models/test_execution.py -v
"""

import json

from src.models.classification import Category
from src.models.execution import ApprovalDecision, ApprovalDecisionType, PreviewRow


# --- ApprovalDecisionType ---

def test_approval_decision_type_has_all_three_v1_values():
    expected = {"approve_as_suggested", "approve_with_edit", "reject"}
    actual = {member.value for member in ApprovalDecisionType}
    assert actual == expected


def test_approval_decision_type_members_are_plain_strings():
    """str, Enum mixin — every member IS a str instance, matching Category's
    established precedent (models/classification.py)."""
    assert isinstance(ApprovalDecisionType.REJECT, str)
    assert ApprovalDecisionType.REJECT == "reject"


def test_approval_decision_type_serializes_to_json_without_a_custom_encoder():
    payload = {"decision": ApprovalDecisionType.APPROVE_WITH_EDIT}
    serialized = json.dumps(payload)
    assert serialized == '{"decision": "approve_with_edit"}'


def test_approval_decision_type_construction_from_string_round_trips():
    assert ApprovalDecisionType("reject") is ApprovalDecisionType.REJECT
    assert ApprovalDecisionType("approve_as_suggested") is ApprovalDecisionType.APPROVE_AS_SUGGESTED


# --- ApprovalDecision ---

def test_approval_decision_as_suggested_has_no_edit_fields():
    decision = ApprovalDecision(file_id="f1", decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED)
    assert decision.file_id == "f1"
    assert decision.decision is ApprovalDecisionType.APPROVE_AS_SUGGESTED
    assert decision.edited_name is None
    assert decision.edited_destination is None


def test_approval_decision_with_edit_carries_both_edit_fields():
    decision = ApprovalDecision(
        file_id="f2",
        decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_name="Renamed_Invoice.pdf",
        edited_destination="Finance/",
    )
    assert decision.decision is ApprovalDecisionType.APPROVE_WITH_EDIT
    assert decision.edited_name == "Renamed_Invoice.pdf"
    assert decision.edited_destination == "Finance/"


def test_approval_decision_with_edit_allows_only_one_field_edited():
    """An edit can touch just the name, just the destination, or both — the
    dataclass itself doesn't require both (Module 07 Design.md §10 step 2: "new
    name and/or destination")."""
    name_only = ApprovalDecision(
        file_id="f3", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_name="Only_Name_Changed.pdf",
    )
    assert name_only.edited_name == "Only_Name_Changed.pdf"
    assert name_only.edited_destination is None

    destination_only = ApprovalDecision(
        file_id="f4", decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
        edited_destination="Documents/",
    )
    assert destination_only.edited_name is None
    assert destination_only.edited_destination == "Documents/"


def test_approval_decision_reject_has_no_edit_fields():
    decision = ApprovalDecision(file_id="f5", decision=ApprovalDecisionType.REJECT)
    assert decision.decision is ApprovalDecisionType.REJECT
    assert decision.edited_name is None
    assert decision.edited_destination is None


# --- PreviewRow ---

def test_preview_row_construction_with_all_required_fields():
    row = PreviewRow(
        file_id="f6",
        original_name="invoice.pdf",
        suggested_name="Amazon_2026-07-05.pdf",
        current_path="/Users/vicky/Downloads/invoice.pdf",
        suggested_destination="Finance/",
        category=Category.INVOICE,
        confidence_score=92,
        tier="approval_required",
    )
    assert row.file_id == "f6"
    assert row.original_name == "invoice.pdf"
    assert row.suggested_name == "Amazon_2026-07-05.pdf"
    assert row.current_path == "/Users/vicky/Downloads/invoice.pdf"
    assert row.suggested_destination == "Finance/"
    assert row.category == Category.INVOICE
    assert row.confidence_score == 92
    assert row.tier == "approval_required"


def test_preview_row_override_defaults_to_none():
    """No override applies -> the normal category-to-destination mapping — the
    "nothing unusual" default, mirroring ClassificationSignals/DuplicateSignals/
    NamingSignals's own established convention."""
    row = PreviewRow(
        file_id="f7", original_name="a.pdf", suggested_name="A.pdf",
        current_path="/tmp/a.pdf", suggested_destination="Documents/",
        category=Category.DOCUMENT, confidence_score=95, tier="auto",
    )
    assert row.override is None


def test_preview_row_override_accepts_exact_duplicate():
    """Uses the exact vocabulary already established by Module 05's own action-log
    details.override_applied field (Metadata & Log Schema.md)."""
    row = PreviewRow(
        file_id="f8", original_name="dup.pdf", suggested_name="Dup.pdf",
        current_path="/tmp/dup.pdf", suggested_destination="~ARCHIVE~/Duplicates/",
        category=Category.DOCUMENT, confidence_score=90, tier="auto",
        override="exact_duplicate",
    )
    assert row.override == "exact_duplicate"


def test_preview_row_override_accepts_superseded_version():
    row = PreviewRow(
        file_id="f9", original_name="Resume_v8.pdf", suggested_name="Resume_v8.pdf",
        current_path="/tmp/Resume_v8.pdf", suggested_destination="~ARCHIVE~/Old Versions/",
        category=Category.RESUME, confidence_score=88, tier="auto",
        override="superseded_version",
    )
    assert row.override == "superseded_version"


def test_preview_row_review_required_tier_carries_no_override_of_its_own():
    """review_required-ness is read directly off `tier`, not encoded as a fourth
    override value (Module 07 Design.md §11A step 1 — checked first, absolute,
    before any destination/override is even resolved)."""
    row = PreviewRow(
        file_id="f10", original_name="unknown.bin", suggested_name="unknown.bin",
        current_path="/tmp/unknown.bin", suggested_destination="Unknown/",
        category=Category.UNKNOWN, confidence_score=40, tier="review_required",
    )
    assert row.tier == "review_required"
    assert row.override is None
