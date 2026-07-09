"""
Shared data shape owned by Module 05 (Naming & Destination).

Split out from file_record.py the same way duplicate.py's DuplicateSignals is —
file_record.py describes the FileRecord shape itself, not each module's own type
definitions. Imported into file_record.py for the `naming_signals` field.

See Build-out/05 Naming & Destination/Module 05 Design.md §5/§11/§29 item 3 for the
full rationale: unlike Module 02/03's fallback deductions (cheaply recomputable by
Module 06 directly from extracted_metadata's null-ness against the taxonomy), Module
06's "-10 per fallback used" naming deduction has no equivalent free recomputation
path without re-running Module 05's own template logic, so a first-class field is
needed — mirroring ClassificationSignals/DuplicateSignals's established pattern
(always a full, populated instance once Module 05 has processed a record, never
partially filled in — confirmed §5's guarantee).
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class NamingSignals:
    """Module 05's raw, honest signal about which naming-template fields had to fall
    back to a placeholder value — the material Module 06 turns into
    confidence_score/confidence_breakdown (Rules/Confidence Rules.md's "-10 per
    fallback used" naming deduction) later. Module 05 never computes a score itself.

    `fields_fell_back` names every real field (by its actual field name, e.g.
    "vendor" — never the template placeholder, e.g. "{Vendor}", and never an
    invented/synthetic label describing the template slot) that had no value and
    so contributed to the template using its documented "Unknown_X" placeholder
    instead of a real one. One entry per affected field — applied literally: when a
    single template slot's fallback depends on more than one field being checked
    (e.g. Resume's `{VersionOrDate}` slot checks `version_indicator` then
    `last_modified_date`) and ALL of them are absent, EVERY field actually checked
    is recorded individually, the same "one entry per affected field" treatment
    every other multi-field category already gets (Invoice's `vendor`/
    `invoice_date`, Bank Statement's `bank_name`/`statement_period`, etc.) — never
    a single combined label like "version_or_date" (corrected, Module 05
    Implementation Audit M1). When the real field ultimately checked is a Module 01
    field rather than a Module 03 taxonomy field (Archive/Video's date slot has no
    taxonomy field of its own at all and falls through to `modified_at`), the real
    field name `modified_at` is recorded — still a real, greppable field name, just
    not one of Module 03's `extracted_metadata` keys.

    Deliberately does NOT include fields that used a real, lower-tier fallback
    SOURCE successfully (e.g. Archive/Video's `modified_at` tier-4 date, Resume's
    `last_modified_date` when `version_indicator` is absent) — those are honest,
    non-placeholder values, not the "fell back to a placeholder value" case this
    signal exists to flag (Design §11/§16). Also does not include an optional
    enrichment field that was simply omitted from the template rather than
    replaced with a placeholder (e.g. Invoice's `invoice_number` when absent,
    Design §29 item 4) — omission is a structural template choice, not a
    placeholder substitution.

    Empty when no fallback occurred — a freshly-constructed NamingSignals() is
    always a valid, complete "no fallback needed" record, the same "nothing
    unusual" default every sibling signals class uses (ClassificationSignals,
    DuplicateSignals).
    """

    fields_fell_back: List[str] = field(default_factory=list)
