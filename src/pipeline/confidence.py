"""
Confidence & Review. DETERMINISTIC module (no Claude judgment) — the whole point of
this step is a fixed, auditable formula instead of an AI-reported number.

Architecture: Build-out/06 Confidence & Review/06 Confidence & Review.md
Rules: Rules/Confidence Rules.md (implemented directly — no generated config in v1, see CHANGELOG.md)

Scaffold only: signatures defined, no logic yet.
"""

from dataclasses import dataclass, field


@dataclass
class ConfidenceResult:
    score: int                      # 0-100, after clipping
    breakdown: dict = field(default_factory=dict)   # named deduction -> value
    tier: str = "review_required"   # auto | approval_required | review_required


def compute_score(deduction_flags: dict) -> ConfidenceResult:
    """Apply Rules/Confidence Rules.md: start at 100, subtract each applicable
    deduction (respecting per-deduction caps), clip to [0, 100], look up the tier,
    then apply the hard floors (which can only push the tier down, never up).
    `deduction_flags` is produced by upstream steps (classification/metadata/naming),
    e.g. {"missing_required_field": 2, "near_duplicate_fuzzy_match": True, ...}."""
    raise NotImplementedError
