"""
Confidence & Review (Module 06). DETERMINISTIC module — no Claude judgment, no
Provider (Module 06 Design.md §2, confirmed): every decision is arithmetic over
already-structured data produced by Modules 01-05. Module 06 never opens a file,
never reads bytes, never makes a new judgment call about what a file *is*.

Architecture: Build-out/06 Confidence & Review/Module 06 Design.md (frozen, plus one
post-freeze correction to compute_score()'s sign — see Module 06 Design Review.md's
"Post-freeze correction" section and CHANGELOG.md).
Rules: Rules/Confidence Rules.md (implemented directly here — not restated or
altered, only mapped to source fields, per Design.md §12/§19).

Two layers, not three (§9): this file's score_confidence_batch() (batch
orchestration: filtering, persistence, logging) -> ConfidenceEngine (per-file
decision-making: compute deductions -> sum -> clip -> look up tier -> apply hard
floors; fully deterministic, no Provider).
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from src.models.classification import Category
from src.models.classification import ClassificationSignals
from src.models.duplicate import DuplicateSignals
from src.models.file_record import FileRecord
from src.models.naming import NamingSignals
from src.storage.database import save_file_record
from src.storage.runtime_io import append_action_log

# --- Required/optional field taxonomy (Design.md §10) — an independent, disclosed,
# cross-checked table, NOT an import from pipeline/metadata.py's REQUIRED_FIELDS/
# OPTIONAL_FIELDS (Governance/ARCHITECTURE_DECISIONS.md decisions 15/5: a module's
# internal constants are not part of its MODULE_CONTRACT.md, and a later module must
# not depend on them directly — real, disclosed duplication is preferred over a
# hidden cross-module coupling). Sourced from and matching
# Build-out/03 Metadata Extraction/Module 03 Design.md §7 (the frozen, authoritative
# taxonomy `Rules/Confidence Rules.md` itself cites) — not from metadata.py's code.
# Cross-checked against pipeline/metadata.py's real, current constants by a
# dedicated regression test (test_confidence.py) — that test's own verification
# purpose only, never read from this production code path (§10).
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
# Category.UNKNOWN deliberately absent from both maps (Design.md §12): "no taxonomy
# entry" for it, mirroring extracted_metadata's own {} default for records Module 03
# never processed — the missing-field deductions simply contribute nothing for such
# records, immaterial since the Unknown-category hard floor (§13) already forces
# review_required regardless of the arithmetic.


def required_fields(category: Category) -> Tuple[str, ...]:
    """Public accessor for a category's required field names (§10), mirroring
    pipeline/metadata.py's own accessor shape by convention, not by import."""
    return REQUIRED_FIELDS.get(category, ())


def optional_fields(category: Category) -> Tuple[str, ...]:
    """Public accessor for a category's optional field names (§10)."""
    return OPTIONAL_FIELDS.get(category, ())


# --- Deduction values (§12, Rules/Confidence Rules.md — values owned by the rules
# doc, not restated/altered here beyond this direct mapping). Every value below is
# stored as a positive magnitude at the constant-definition level and applied as a
# negative int in confidence_breakdown (matching Rules/Confidence Rules.md's own
# worked example and Metadata & Log Schema.md's stored-breakdown example, both of
# which show negative dict values, e.g. "missing_required_field:invoice_number": -8). ---

_AMBIGUOUS_CLASSIFICATION_DEDUCTION = 15
_NO_EXTRACTABLE_TEXT_DEDUCTION = 30
_REQUIRED_FIELD_DEDUCTION = 8
_REQUIRED_FIELD_CAP = 30
_OPTIONAL_FIELD_DEDUCTION = 2
_OPTIONAL_FIELD_CAP = 10
_NAMING_FALLBACK_DEDUCTION = 10
_FUZZY_DUPLICATE_DEDUCTION = 20
_VERSION_CONFLICT_DEDUCTION = 25
_NON_ENGLISH_CONTENT_DEDUCTION = 10
_LOCKED_FILE_DEDUCTION = 40

# --- Tier lookup (§13) ---

_TIER_AUTO = "auto"
_TIER_APPROVAL_REQUIRED = "approval_required"
_TIER_REVIEW_REQUIRED = "review_required"

# Strictness ranking for "clamps down, never raises" (§13) — higher is stricter.
_TIER_STRICTNESS = {
    _TIER_AUTO: 0,
    _TIER_APPROVAL_REQUIRED: 1,
    _TIER_REVIEW_REQUIRED: 2,
}


def lookup_tier(score: int) -> str:
    """Three-band lookup (§13), applied to the clipped score before any hard floor."""
    if score >= 95:
        return _TIER_AUTO
    if score >= 80:
        return _TIER_APPROVAL_REQUIRED
    return _TIER_REVIEW_REQUIRED


def _stricter(tier_a: str, tier_b: str) -> str:
    """The stricter (lower-throughput) of two tiers — review_required is stricter
    than approval_required, which is stricter than auto (§13)."""
    if _TIER_STRICTNESS[tier_a] >= _TIER_STRICTNESS[tier_b]:
        return tier_a
    return tier_b


# --- Hard floor table (§13) — trigger, minimum tier forced, log identifier. Four
# rows, not five: "Unknown category" and "Corrupted file" share one identical,
# indistinguishable trigger (Design.md §2.4's corollary) and are implemented and
# logged as a single hard floor, never as two separate hard_floors_applied entries
# for the same fact. Table order is significant — apply_hard_floors() walks this
# list in order, and hard_floors_applied's own entries are returned in this same
# order (§9, §16). ---


def _trigger_unknown_category(record: FileRecord) -> bool:
    return record.category == Category.UNKNOWN


def _trigger_fuzzy_duplicate(record: FileRecord) -> bool:
    signals = record.duplicate_signals
    return signals is not None and signals.fuzzy_duplicate


def _trigger_multi_document(record: FileRecord) -> bool:
    signals = record.classification_signals
    return signals is not None and signals.multi_document_detected


def _trigger_locked_file(record: FileRecord) -> bool:
    signals = record.classification_signals
    return signals is not None and signals.locked


# (log identifier, minimum tier forced, trigger function) — fixed row order, §13.
_HARD_FLOORS: Tuple[Tuple[str, str, "callable"], ...] = (
    ("unknown_category", _TIER_REVIEW_REQUIRED, _trigger_unknown_category),
    ("fuzzy_duplicate", _TIER_APPROVAL_REQUIRED, _trigger_fuzzy_duplicate),
    ("multi_document_detected", _TIER_REVIEW_REQUIRED, _trigger_multi_document),
    ("locked_file", _TIER_REVIEW_REQUIRED, _trigger_locked_file),
)


def apply_hard_floors(record: FileRecord, tier: str) -> Tuple[str, List[str]]:
    """Walk every hard floor in §13's table exactly once and, for each one,
    evaluate its trigger condition against `record`. Returns
    (new_tier, hard_floors_applied): new_tier is `tier` clamped down (never
    raised) by the minimum of every hard floor whose trigger was true, and
    hard_floors_applied is the list of those same triggered floors' log
    identifiers, in the table's fixed row order (§9). This single walk is the
    sole source of both the tier-clamping decision and the logging data — there
    is no second, separate computation of "which floors applied" anywhere else
    (post-freeze M1 fix: the tier decision and the log record are two views of
    the same walk, not two independent facts that could drift apart)."""
    new_tier = tier
    hard_floors_applied: List[str] = []
    for identifier, minimum_tier, trigger in _HARD_FLOORS:
        if trigger(record):
            hard_floors_applied.append(identifier)
            new_tier = _stricter(new_tier, minimum_tier)
    return new_tier, hard_floors_applied


# --- Deductions (§12) ---


def _apply_capped_field_deductions(
    deductions: Dict[str, int],
    record: FileRecord,
    field_names: Tuple[str, ...],
    key_prefix: str,
    per_field_magnitude: int,
    cap_magnitude: int,
) -> None:
    """Walk `field_names` (§10's fixed field order for this category) and record
    one confidence_breakdown entry per missing field: full nominal (negative)
    value while the category's running subtotal stays within its cap, and
    exactly 0 — never omitted — for every field once the cap is reached (§12's
    "Cap representation" note, user-approved fix M3). The two field-list
    categories (required, optional) are always capped independently by the
    caller passing each one through its own call."""
    running_subtotal = 0
    for field_name in field_names:
        if record.extracted_metadata.get(field_name) is not None:
            continue
        key = f"{key_prefix}:{field_name}"
        if running_subtotal + per_field_magnitude <= cap_magnitude:
            deductions[key] = -per_field_magnitude
            running_subtotal += per_field_magnitude
        else:
            deductions[key] = 0


def compute_deductions(record: FileRecord) -> Dict[str, int]:
    """Walk every rule in §12's table, return only the deductions that actually
    applied (an empty dict when none did). Enforces the -30 required-field / -10
    optional-field category caps itself, before returning (§12's "Cap
    representation" note, user-approved fix M3)."""
    deductions: Dict[str, int] = {}

    classification_signals = record.classification_signals or ClassificationSignals()
    duplicate_signals = record.duplicate_signals or DuplicateSignals()
    naming_signals = record.naming_signals or NamingSignals()

    if classification_signals.ambiguous:
        deductions["ambiguous_classification"] = -_AMBIGUOUS_CLASSIFICATION_DEDUCTION
    if classification_signals.no_extractable_text:
        deductions["no_extractable_text"] = -_NO_EXTRACTABLE_TEXT_DEDUCTION

    _apply_capped_field_deductions(
        deductions,
        record,
        required_fields(record.category),
        "missing_required_field",
        _REQUIRED_FIELD_DEDUCTION,
        _REQUIRED_FIELD_CAP,
    )
    _apply_capped_field_deductions(
        deductions,
        record,
        optional_fields(record.category),
        "missing_optional_field",
        _OPTIONAL_FIELD_DEDUCTION,
        _OPTIONAL_FIELD_CAP,
    )

    for fallback_field in naming_signals.fields_fell_back:
        deductions[f"naming_fallback:{fallback_field}"] = -_NAMING_FALLBACK_DEDUCTION

    if duplicate_signals.fuzzy_duplicate:
        deductions["fuzzy_duplicate"] = -_FUZZY_DUPLICATE_DEDUCTION
    if duplicate_signals.version_conflict:
        deductions["version_conflict"] = -_VERSION_CONFLICT_DEDUCTION

    if classification_signals.non_english_detected:
        deductions["non_english_content"] = -_NON_ENGLISH_CONTENT_DEDUCTION
    if classification_signals.locked:
        deductions["locked_file"] = -_LOCKED_FILE_DEDUCTION

    return deductions


def compute_score(deductions: Dict[str, int]) -> int:
    """100 + sum(deductions.values()), clipped to [0, 100] (post-freeze
    correction — see Module 06 Design Review.md). Every value in `deductions` is
    already negative (matching Rules/Confidence Rules.md's own worked example:
    {"missing_required_field:invoice_number": -8, "naming_fallback:vendor": -10}
    -> 100 + (-8) + (-10) = 82), so adding them to 100 performs the subtraction.
    Unconditional and exact: compute_deductions() already enforces both caps
    before returning, so this sum always equals the true, capped score
    reduction — this function performs no capping logic of its own."""
    score = 100 + sum(deductions.values())
    return max(0, min(100, score))


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


@dataclass
class EngineResult:
    """Everything ConfidenceEngine.score_file() hands back to
    score_confidence_batch() for one file — enough to populate FileRecord's
    confidence_score/confidence_breakdown/tier and write a complete
    score_confidence action-log entry without the batch orchestration needing to
    know how the answer was reached."""
    confidence_score: int
    confidence_breakdown: Dict[str, int] = field(default_factory=dict)
    tier: str = _TIER_REVIEW_REQUIRED
    hard_floors_applied: List[str] = field(default_factory=list)
    processing_time_ms: int = 0


class ConfidenceEngine:
    """Per-file decision-making (§9) — fully deterministic, no Provider (§2,
    confirmed)."""

    def score_file(self, record: FileRecord) -> EngineResult:
        """Score one already-named, already-duplicate/version-checked record.
        Callers (score_confidence_batch()) are responsible for only calling this
        on records that pass §11's eligibility filter — the Engine itself does
        not re-check this, matching every earlier module's Engine's precedent of
        trusting its caller's filtering."""
        start = time.monotonic()

        deductions = compute_deductions(record)
        score = compute_score(deductions)
        tier = lookup_tier(score)
        tier, hard_floors_applied = apply_hard_floors(record, tier)

        return EngineResult(
            confidence_score=score,
            confidence_breakdown=deductions,
            tier=tier,
            hard_floors_applied=hard_floors_applied,
            processing_time_ms=_elapsed_ms(start),
        )


# --- Module 06 batch orchestration: filtering, persistence, logging. This is the
# only layer that touches storage/*.py or Runtime/Logs directly (§9) — the Engine
# never does, since there is no Provider layer here either. ---


def score_confidence_batch(records: List[FileRecord]) -> List[FileRecord]:
    """Score every eligible record, persist the results, and log one
    score_confidence action-log entry per file. Mirrors
    suggest_naming_and_destination_batch()'s shape: same records in, same
    records back out, enriched in place, no disclosed side effect on any other
    record (§7) — unlike Module 05, Module 06 doesn't even read other records in
    the same batch (§7's determinism guarantee: no record's output value depends
    on batch order).

    Records are processed in the same deterministic order every module since
    Module 04 has used — discovered_at ascending, file_id (lexicographic) as the
    final tie-break (§11) — preserved purely for log-ordering consistency with
    the rest of the pipeline, not because any output value depends on it here.

    Eligibility filter (§11 step 1, confirmed): status == "discovered" and
    category is not None and suggested_name is not None. Filtering out records
    Module 06 has already processed (so a second run doesn't re-score a record
    that already has a confidence_score) is the caller's responsibility — a
    separate, CLI-level re-run/idempotency filter (confidence_score is None),
    mirroring suggest_naming()'s own CLI-level idempotency check (§11, §24).
    """
    ordered_records = sorted(records, key=lambda r: (r.discovered_at or "", r.file_id))

    for record in ordered_records:
        if (
            record.status != "discovered"
            or record.category is None
            or record.suggested_name is None
        ):
            continue

        engine = ConfidenceEngine()
        try:
            result = engine.score_file(record)
        except Exception as unexpected_error:
            # Outer safety net — a single bad file must never abort the batch,
            # the same resilience pattern every earlier module already
            # establishes (§18).
            append_action_log(
                batch_id=record.batch_id,
                file_id=record.file_id,
                action="error",
                from_path=record.current_path,
                details={"stage": "score_confidence", "error": str(unexpected_error)},
            )
            continue

        record.confidence_score = result.confidence_score
        record.confidence_breakdown = result.confidence_breakdown
        record.tier = result.tier
        save_file_record(record)

        details = {
            "confidence_score": result.confidence_score,
            "confidence_breakdown": result.confidence_breakdown,
            "tier": result.tier,
            "hard_floors_applied": result.hard_floors_applied,
            "processing_time_ms": result.processing_time_ms,
        }
        append_action_log(
            batch_id=record.batch_id,
            file_id=record.file_id,
            action="score_confidence",
            from_path=record.current_path,
            details=details,
        )

    return records
