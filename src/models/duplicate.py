"""
Shared data shape owned by Module 04 (Duplicate & Version Detection).

Split out from file_record.py the same way classification.py's ClassificationSignals
is — file_record.py describes the FileRecord shape itself, not each module's own type
definitions. Imported into file_record.py for the `duplicate_signals` field.

See Build-out/04 Duplicate & Version Detection/Module 04 Design.md §17 for the full
rationale: this mirrors ClassificationSignals's pattern exactly (always a full,
populated instance once Module 04 has processed a record, never partially filled),
and records only the single best-scoring match per detection type (§17, F4) — never a
list of several simultaneous candidates. `version_conflict` is deliberately reused for
both a within-group filename-token/date disagreement and a cross-group conflict (two
or more candidates already belonging to different existing version groups) — the two
are distinguished only in the action log's `conflict_type` detail, never here (§17, F3).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DuplicateSignals:
    """Module 04's raw, honest signals about duplicate/version relationships it
    found — the material Module 06 turns into confidence_score/confidence_breakdown/
    tier later (Rules/Confidence Rules.md's near-duplicate and version-conflict
    deductions/hard floors). Module 04 never computes a score itself.

    Every field defaults to the "nothing unusual" value, so a freshly-constructed
    DuplicateSignals() is always a valid, complete "no signals apply" record.
    """

    exact_duplicate: bool = False
    fuzzy_duplicate: bool = False
    phash_distance: Optional[int] = None
    version_conflict: bool = False
