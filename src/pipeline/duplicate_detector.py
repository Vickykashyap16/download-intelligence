"""
Duplicate & Version Detection (Module 04). DETERMINISTIC module — no Claude judgment,
no Provider (Module 04 Design.md §14: every decision here is a computation over
already-extracted, already-structured data — hash equality, perceptual-hash distance,
filename similarity, version-token/date comparison — never a judgment call requiring
content understanding).

Architecture: Build-out/04 Duplicate & Version Detection/Module 04 Design.md (frozen)

Two layers, not three (§6): this file's `detect_duplicates_batch()` (batch
orchestration: filtering, persistence, logging — the only layer that touches
storage/*.py or Runtime/Logs directly for orchestration-level concerns) ->
`DuplicateDetectionEngine` (per-file decision-making; calls the FileIndex lookup
functions directly, since there is no Provider layer to shield storage access behind
the way Modules 02/03's Engines are shielded from it).
"""

import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from src.core.hashing import hamming_distance, perceptual_hash
from src.models.classification import Category
from src.models.duplicate import DuplicateSignals
from src.models.file_record import FileRecord
from src.storage.database import (
    load_metadata_store,
    lookup_hash,
    lookup_name_matches,
    lookup_phash_matches,
    record_version_history,
    save_file_record,
)
from src.storage.database import update_indexes as _update_indexes
from src.storage.runtime_io import append_action_log

# Module 04 Design.md §11 — confirmed default, a configurable implementation
# parameter (§15), not an architectural constant.
_MAX_PHASH_DISTANCE = 5

# PT-003 post-freeze correction (Module 04 Post-Freeze Design Correction —
# PT-003.md §6): a configurable implementation parameter, not an architectural
# constant, following the same disclosed-parameter convention as
# _MAX_PHASH_DISTANCE above. Used only by the identical-normalized-name branch
# of version-chain candidacy corroboration (see
# DuplicateDetectionEngine._has_corroborating_version_signal()) — the smaller of
# two same-category, identically-named files' sizes must be at least this
# fraction of the larger's for the pair to qualify without an explicit version
# token. 0.5 == no more than a 2x size difference.
_VERSION_SIZE_PROXIMITY_RATIO = 0.5

# Module 04 Design.md §9 — confirmed v1 scope.
_NEAR_DUPLICATE_CATEGORIES = frozenset({Category.IMAGE, Category.SCREENSHOT})
_VERSION_CHAIN_CATEGORIES = frozenset({
    Category.INVOICE, Category.RESUME, Category.BANK_STATEMENT, Category.CONTRACT,
    Category.DOCUMENT, Category.IMAGE, Category.SCREENSHOT,
})


# --- Filename helpers (§6 — live here, not core/, since they're specific to this
# module's own naming/version logic; same rationale Module 03 used for its own
# filename-parsing helpers). ---

_NUMBERED_TOKEN_SUFFIX = re.compile(r"[_\-\s]*\(?v\.?(\d+)\)?$", re.IGNORECASE)
_FINAL_TOKEN_SUFFIX = re.compile(r"[_\-\s]*final$", re.IGNORECASE)
_VERSION_TOKEN_SUFFIX = re.compile(
    r"([_\-\s]*\(?v\.?\d+\)?|[_\-\s]*final)$", re.IGNORECASE
)
_SEPARATOR_RUN = re.compile(r"[_\-\s]+")


def normalize_filename(name: str) -> str:
    """Strip extension, a trailing explicit version token, and separators, for
    similarity comparison (§6). E.g. "Resume_v9.pdf" and "Resume_v8.pdf" both
    normalize to "resume"."""
    stem = Path(name).stem
    stem = _VERSION_TOKEN_SUFFIX.sub("", stem)
    stem = _SEPARATOR_RUN.sub(" ", stem).strip().lower()
    return stem


def parse_version_token(name: str) -> Optional[Tuple[str, int]]:
    """Extract an explicit version indicator from a filename, if present (§6/§10).
    Returns ("numbered", N) for _v1/_v2/etc., ("final", 0) for _final, or None if no
    recognizable token is present. Numbered is checked first, since a name could
    plausibly end in "..._final" without a preceding number, but never both."""
    stem = Path(name).stem
    numbered = _NUMBERED_TOKEN_SUFFIX.search(stem)
    if numbered:
        return ("numbered", int(numbered.group(1)))
    if _FINAL_TOKEN_SUFFIX.search(stem):
        return ("final", 0)
    return None


# Category-appropriate date field, in priority order, per category (§12 — mirrors
# Module 03's own timestamp-hierarchy discipline: a real, category-specific date is
# preferred over a filesystem timestamp).
_DATE_FIELD_BY_CATEGORY: Dict[Category, Tuple[str, ...]] = {
    Category.INVOICE: ("invoice_date",),
    Category.RESUME: ("last_modified_date",),
    Category.BANK_STATEMENT: ("statement_period",),
    Category.CONTRACT: ("effective_date",),
    Category.DOCUMENT: ("document_date",),
    Category.IMAGE: ("capture_date",),
    Category.SCREENSHOT: ("capture_date",),
}


def best_available_date(record: FileRecord) -> Optional[str]:
    """The category-appropriate extracted-metadata date field if present, else
    `modified_at` (tier-4 fallback, same "flagged, not authoritative" treatment
    Module 03's timestamp hierarchy already established) (§6/§12)."""
    for field_name in _DATE_FIELD_BY_CATEGORY.get(record.category, ()):
        value = record.extracted_metadata.get(field_name)
        if value:
            return value
    return record.modified_at


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


@dataclass
class EngineResult:
    """Everything DuplicateDetectionEngine.detect_file() hands back to
    detect_duplicates_batch() for one file — enough to populate FileRecord's
    duplicate_of/version_group_id/version_rank/duplicate_signals and write a
    complete `detect_duplicates_and_versions` action-log entry without the batch
    orchestration needing to know how the answer was reached."""
    duplicate_of: Optional[str] = None
    version_group_id: Optional[str] = None
    version_rank: Optional[str] = None
    duplicate_signals: DuplicateSignals = field(default_factory=DuplicateSignals)
    match_type: Optional[str] = None            # "exact" | "fuzzy" | "version" | None
    conflict_type: Optional[str] = None         # "date_token_disagreement" | "cross_group" | None
    conflicting_group_ids: List[str] = field(default_factory=list)
    # The one disclosed side effect (§4/§7, post-freeze correction): a different,
    # already-processed record's version_group_id and/or version_rank may need to
    # change. `other_record_id` names which one; `other_record_needs_group_id`
    # means its version_group_id must be set to this result's version_group_id
    # (first-time group creation only); `other_record_version_rank` is its new
    # rank, when it's changing (may be "latest" or "superseded" — a first-time
    # pairing can go either way depending on which of the two is actually newer).
    other_record_id: Optional[str] = None
    other_record_needs_group_id: bool = False
    other_record_version_rank: Optional[str] = None
    processing_time_ms: int = 0


class DuplicateDetectionEngine:
    """Per-file decision-making (§6/§7) — fully deterministic, no Provider (§14)."""

    def detect_file(self, record: FileRecord, records_by_id: Dict[str, FileRecord]) -> EngineResult:
        """Detect duplicate/version relationships for one already-classified record.
        Callers (`detect_duplicates_batch()`) are responsible for only calling this
        on records with status == "discovered" that haven't already been processed
        by Module 04 (§7's idempotency gate) — the Engine itself does not re-check
        this, matching ClassificationEngine/MetadataExtractionEngine's precedent of
        trusting its caller's filtering.

        `records_by_id` is every record known so far (loaded once by the batch
        orchestration, §20 — avoids reloading the full store per file), including
        records from earlier in the same batch that have already been processed and
        indexed this run.
        """
        start = time.monotonic()
        signals = DuplicateSignals()

        # --- Step 1: exact-duplicate (always runs, every category, §7 step 1) ---
        if record.content_hash is not None:
            existing_file_id = lookup_hash(record.content_hash)
            if existing_file_id is not None and existing_file_id != record.file_id:
                signals.exact_duplicate = True
                return EngineResult(
                    duplicate_of=existing_file_id,
                    duplicate_signals=signals,
                    match_type="exact",
                    processing_time_ms=_elapsed_ms(start),
                )

        category = record.category

        # --- Step 2: near-duplicate (Image/Screenshot only, §7 step 2) ---
        if category in _NEAR_DUPLICATE_CATEGORIES:
            self._check_near_duplicate(record, records_by_id, signals)

        # --- Step 3: version-chain check (scoped categories only, §7 step 3, §9) ---
        if category in _VERSION_CHAIN_CATEGORIES:
            version_result = self._check_version_chain(record, records_by_id, signals)
            if version_result is not None:
                version_result.duplicate_signals = signals
                version_result.processing_time_ms = _elapsed_ms(start)
                return version_result

        return EngineResult(
            duplicate_signals=signals,
            match_type="fuzzy" if signals.fuzzy_duplicate else None,
            processing_time_ms=_elapsed_ms(start),
        )

    # --- Step 2 helper ---

    def _check_near_duplicate(self, record: FileRecord, records_by_id: Dict[str, FileRecord],
                                signals: DuplicateSignals) -> None:
        try:
            phash = perceptual_hash(record.current_path)
        except Exception:
            return  # couldn't determine — honest "no signal", not a guess (§21)

        candidate_ids = [
            file_id for file_id in lookup_phash_matches(phash, _MAX_PHASH_DISTANCE, record.category)
            if file_id != record.file_id
        ]
        if not candidate_ids:
            return

        # F4: keep only the single nearest candidate. lookup_phash_matches() returns
        # file_ids, not distances (§16's frozen signature), so the true minimum
        # distance among the returned candidates is recomputed here — a small,
        # disclosed recompute cost (§20), not a correctness concern. candidate_ids is
        # already category-scoped (post-freeze correction #4, §9/F5) — every candidate
        # here shares record.category, so no further category check is needed below.
        best_distance: Optional[int] = None
        for candidate_id in candidate_ids:
            candidate = records_by_id.get(candidate_id)
            if candidate is None or not candidate.current_path:
                continue
            try:
                candidate_phash = perceptual_hash(candidate.current_path)
            except Exception:
                continue
            distance = hamming_distance(phash, candidate_phash)
            if best_distance is None or distance < best_distance:
                best_distance = distance

        if best_distance is not None:
            signals.fuzzy_duplicate = True
            signals.phash_distance = best_distance

    # --- PT-003 post-freeze correction: version-chain candidacy corroboration
    # (Module 04 Post-Freeze Design Correction — PT-003.md §6). ---

    def _has_corroborating_version_signal(self, record: FileRecord, candidate: FileRecord,
                                            normalized_name: str) -> bool:
        """A second, corroborating signal, independent of the fuzz.ratio()
        similarity score lookup_name_matches() already applied, required before a
        same-category, above-threshold candidate is accepted into version-chain
        candidacy. Closes the confirmed false-positive mechanism
        (PATTERN_TRACKER.md PT-003): near-miss-similar generic template names
        (e.g. "Mark Sheet 10th"/"Mark Sheet 12th", "image (2)"/"image (42)") no
        longer qualify on filename similarity alone.

        Satisfied by EITHER:
          (a) an explicit version token on at least one side — a strong,
              structural, intentional signal that needs no further
              corroboration, OR
          (b) an identical normalized filename AND a size-proximity check — an
              identical name alone is not evidence of a version relationship
              (it is equally consistent with a generic, uncustomized filename
              shared by two unrelated files, Round 1 review Finding E1), so it
              must be corroborated by size, a signal derived from content
              rather than name.

        `size_bytes` is `Optional[int]` — if either side lacks a value, the
        proximity check cannot be evaluated and fails conservatively (does not
        qualify), the same "incomplete evidence does not assert a relationship"
        default already used elsewhere in this design. Two zero-byte files are
        treated as unambiguously equal in size (special-cased to avoid a
        division by zero), not merely proximate.
        """
        if parse_version_token(record.original_name) is not None:
            return True
        if parse_version_token(candidate.original_name) is not None:
            return True

        if normalized_name != normalize_filename(candidate.original_name):
            return False

        size_a = record.size_bytes
        size_b = candidate.size_bytes
        if size_a is None or size_b is None:
            return False

        larger = max(size_a, size_b)
        if larger == 0:
            return True
        smaller = min(size_a, size_b)
        return (smaller / larger) >= _VERSION_SIZE_PROXIMITY_RATIO

    # --- Step 3 helper (H1/M1-corrected sequencing) ---

    def _check_version_chain(self, record: FileRecord, records_by_id: Dict[str, FileRecord],
                               signals: DuplicateSignals) -> Optional[EngineResult]:
        normalized_name = normalize_filename(record.original_name)
        category = record.category

        candidate_ids = [
            file_id for file_id in lookup_name_matches(normalized_name, category)
            if file_id != record.file_id
        ]
        candidates = [
            records_by_id[file_id] for file_id in candidate_ids if file_id in records_by_id
        ]

        # PT-003 post-freeze correction (Module 04 Post-Freeze Design Correction —
        # PT-003.md §6): lookup_name_matches() has already applied the filename-
        # similarity threshold (fuzz.ratio() >= _NAME_SIMILARITY_THRESHOLD) and the
        # category scope — but similarity alone is not sufficient evidence of a
        # genuine version relationship (PATTERN_TRACKER.md PT-003, both confirmed
        # false-positive mechanisms). Require a corroborating signal, independent
        # of the similarity score itself, before a candidate is accepted.
        candidates = [
            candidate for candidate in candidates
            if self._has_corroborating_version_signal(record, candidate, normalized_name)
        ]
        if not candidates:
            return None

        # H1/M1: collect all above-threshold candidates (lookup_name_matches()
        # already applied the threshold, §16/M2) and inspect the COMPLETE set for
        # cross-version-group membership BEFORE narrowing to a single best match.
        # `null` never counts as a distinct existing group (M1).
        non_null_group_ids = sorted({
            candidate.version_group_id for candidate in candidates
            if candidate.version_group_id is not None
        })

        if len(non_null_group_ids) > 1:
            # Cross-group conflict (F3) — do not merge, flag, stop.
            signals.version_conflict = True
            return EngineResult(
                match_type="version",
                conflict_type="cross_group",
                conflicting_group_ids=non_null_group_ids,
            )

        # No conflict — select the single best-scoring candidate (F4). Candidates
        # were already filtered to same-category/above-threshold by
        # lookup_name_matches(); scoring here is cheap (pure string comparison, no
        # file I/O) and only re-derives which one is best, not whether any qualify.
        # Tie-break (§10, post-freeze correction #3): prefer a candidate that
        # already belongs to a version group over an ungrouped one when scores are
        # equal — joining an existing group is always at least as correct as
        # minting a redundant new one, and without this the choice would depend on
        # arbitrary index-iteration order. Formally documented in Module 04
        # Design.md §10 (Independent Implementation Audit finding M1) — this is no
        # longer an undisclosed implementation-only judgment call.
        best_candidate = max(
            candidates,
            key=lambda c: (
                fuzz.ratio(normalized_name, normalize_filename(c.original_name)),
                c.version_group_id is not None,
            ),
        )

        is_new_group = best_candidate.version_group_id is None
        version_group_id = best_candidate.version_group_id or str(uuid.uuid4())

        # Every other already-processed member of this group (post-freeze
        # correction: for a brand-new group, that's just best_candidate itself —
        # its version_group_id is set as part of this same step, §7 step 3.4).
        if is_new_group:
            group_members = [best_candidate]
        else:
            group_members = [
                c for c in records_by_id.values()
                if c.version_group_id == version_group_id and c.file_id != record.file_id
            ]

        # The specific other record being compared against, and whose rank may
        # flip as this module's one disclosed side effect (§4/§7, post-freeze
        # correction). For a brand-new group that's best_candidate itself; for an
        # existing group it's whichever member currently holds "latest" (every
        # other member is already "superseded" and unaffected — at most one
        # member is ever "latest" at a time), which need not be best_candidate
        # itself if a different group member happens to score the same on name
        # similarity.
        if is_new_group:
            reference = best_candidate
        else:
            reference = next((m for m in group_members if m.version_rank == "latest"), None)

        rank, conflict, other_rank = self._determine_rank(record, reference, group_members)
        signals.version_conflict = conflict

        return EngineResult(
            version_group_id=version_group_id,
            version_rank=rank,
            match_type="version",
            conflict_type="date_token_disagreement" if conflict else None,
            other_record_id=reference.file_id if reference is not None else None,
            other_record_needs_group_id=is_new_group,
            other_record_version_rank=other_rank,
        )

    def _determine_rank(self, record: FileRecord, reference: Optional[FileRecord],
                          group_members: List[FileRecord]
                          ) -> Tuple[str, bool, Optional[str]]:
        """Determine whether `record` is the new "latest" or "superseded" relative
        to `reference` (the specific other record it's being compared against —
        either a brand-new group's sole other member, or an existing group's
        current "latest"), and what `reference`'s own rank becomes as a result
        (this module's one disclosed side effect, §4/§7 post-freeze correction).

        Returns (record's rank, conflict, reference's new rank). The third value
        is `None` only when `reference` is missing (defensive — an existing group
        with no member currently marked "latest" should not occur once groups are
        consistently maintained) — nothing is compared or updated in that case;
        `record` is treated as trivially latest."""
        if reference is None:
            return "latest", False, None

        all_numbered_values = [
            value for member in (group_members + [record])
            for value in [self._numbered_value(member)] if value is not None
        ]

        new_rank_value = self._rank_value(record, all_numbered_values)
        old_rank_value = self._rank_value(reference, all_numbered_values)
        token_says_new_is_latest = (
            new_rank_value > old_rank_value
            if new_rank_value is not None and old_rank_value is not None else None
        )

        new_date = best_available_date(record)
        old_date = best_available_date(reference)
        date_says_new_is_latest = (
            new_date > old_date if new_date is not None and old_date is not None else None
        )

        conflict = (
            token_says_new_is_latest is not None
            and date_says_new_is_latest is not None
            and token_says_new_is_latest != date_says_new_is_latest
        )

        # Tie-break default (§10): filename token wins on conflict (a human-authored
        # version number is treated as more deliberate than a possibly-unreliable
        # date); else whichever signal is available; else the newly-discovered
        # record defaults to latest (deterministic, not a guess about content).
        if token_says_new_is_latest is not None:
            new_is_latest = token_says_new_is_latest
        elif date_says_new_is_latest is not None:
            new_is_latest = date_says_new_is_latest
        else:
            new_is_latest = True

        if new_is_latest:
            return "latest", conflict, "superseded"
        return "superseded", conflict, "latest"

    def _numbered_value(self, member: FileRecord) -> Optional[int]:
        token = parse_version_token(member.original_name)
        if token and token[0] == "numbered":
            return token[1]
        return None

    def _rank_value(self, member: FileRecord, all_numbered_values: List[int]) -> Optional[float]:
        """Numeric rank for version-token comparison (§10). A numbered token is its
        own value; `_final` ranks higher than any numbered version already known at
        comparison time, but lower than any later-numbered version discovered
        afterward — achieved by valuing it at (current max numbered value) + 0.5,
        so a genuinely higher number introduced later still exceeds it."""
        token = parse_version_token(member.original_name)
        if token is None:
            return None
        kind, value = token
        if kind == "numbered":
            return float(value)
        baseline = max(all_numbered_values) if all_numbered_values else 0
        return float(baseline) + 0.5


# --- Module 04 batch orchestration: filtering, persistence, logging. This is the
# only layer that touches storage/*.py or Runtime/Logs directly for orchestration-
# level concerns (§6) — the Engine calls the FileIndex lookup functions directly for
# its own per-file decision-making, since there is no Provider layer here (§14). ---


def needs_duplicate_detection(record: FileRecord) -> bool:
    """True if Module 04 has not yet settled `record` (§7, post-freeze correction
    #2 — Independent Implementation Audit finding H1).

    The reliable "has Module 04 touched this at all" signal is `duplicate_signals`
    itself: §5/§17 already guarantee it is always populated with a full, real
    instance once Module 04 has processed a record, regardless of what (if
    anything) was found — unlike `duplicate_of`/`version_group_id`/`version_rank`,
    which can all legitimately stay `None` forever after a fully correct run that
    found no exact duplicate and no version chain (very likely the single most
    common real-world outcome). The one narrow, deliberately-preserved exception:
    a record stuck in the unresolved cross-version-group-conflict state (§7 step
    3.3 — `duplicate_signals.version_conflict` True *and* `version_group_id` still
    `None`, and only that combination) remains eligible for re-examination on
    every run, matching the fifth architecture-review pass's own explicit decision
    that this state should stay visible rather than be silently skipped — v1 has
    no tooling to resolve a cross-group conflict any other way.

    Shared by `detect_duplicates_batch()` and `main.py`'s CLI filter so the rule
    lives in exactly one place, not duplicated across call sites.
    """
    if record.duplicate_signals is None:
        return True
    return record.duplicate_signals.version_conflict and record.version_group_id is None


def detect_duplicates_batch(records: List[FileRecord]) -> List[FileRecord]:
    """Detect duplicate/version relationships for every already-classified record,
    persist the results, and log one `detect_duplicates_and_versions` action-log
    entry per file. Mirrors classify_batch()/extract_metadata_batch()'s shape, with
    one disclosed exception (§4): a different, earlier-processed record's
    `version_group_id` and/or `version_rank` may also be updated as a side effect.

    Records are processed in a fixed, deterministic order — `discovered_at`
    ascending, `file_id` (lexicographic) as the final tie-break for identical
    timestamps (F1, §7) — so re-running the same batch always produces the same
    result. Records already settled by Module 04 are skipped — see
    `needs_duplicate_detection()` for the precise idempotency rule (§7, post-freeze
    correction #2).
    """
    records_by_id: Dict[str, FileRecord] = {r.file_id: r for r in load_metadata_store()}
    for r in records:
        records_by_id[r.file_id] = r  # ensure the same live objects the caller holds

    engine = DuplicateDetectionEngine()
    ordered_records = sorted(records, key=lambda r: (r.discovered_at or "", r.file_id))

    for record in ordered_records:
        if record.status != "discovered":
            continue
        if not needs_duplicate_detection(record):
            continue  # already settled by Module 04 (idempotency, §7, post-freeze correction #2)

        try:
            result = engine.detect_file(record, records_by_id)
        except Exception as unexpected_error:
            # Outer safety net — DuplicateDetectionEngine already catches every
            # failure mode it knows about internally (§21); this branch is only
            # reached if something entirely unanticipated slips through, and even
            # then a single bad file must never abort the batch.
            append_action_log(
                batch_id=record.batch_id,
                file_id=record.file_id,
                action="error",
                from_path=record.current_path,
                details={"stage": "duplicate_detection", "error": str(unexpected_error)},
            )
            continue

        record.duplicate_of = result.duplicate_of
        record.version_group_id = result.version_group_id
        record.version_rank = result.version_rank
        record.duplicate_signals = result.duplicate_signals
        save_file_record(record)

        # Side effect (§4/§7, post-freeze correction): a different, already-
        # processed record's version_group_id and/or version_rank may be updated —
        # never any other field. `other_record_needs_group_id` covers first-time
        # group creation; `other_record_version_rank` covers a rank flip (either
        # direction — the newly-arriving record isn't always the newer one).
        other_record = None
        if result.other_record_id is not None:
            other_record = records_by_id.get(result.other_record_id)
            if other_record is not None:
                changed = False
                if result.other_record_needs_group_id and other_record.version_group_id is None:
                    other_record.version_group_id = result.version_group_id
                    changed = True
                if (result.other_record_version_rank is not None
                        and other_record.version_rank != result.other_record_version_rank):
                    other_record.version_rank = result.other_record_version_rank
                    changed = True
                if changed:
                    save_file_record(other_record)
                    record_version_history(result.version_group_id, other_record, other_record.version_rank)
                else:
                    other_record = None  # nothing actually changed — no second log line

        _update_indexes(record)

        if result.version_group_id is not None:
            record_version_history(result.version_group_id, record, result.version_rank)

        details = {
            "duplicate_of": result.duplicate_of,
            "version_group_id": result.version_group_id,
            "version_rank": result.version_rank,
            "match_type": result.match_type,
            "phash_distance": result.duplicate_signals.phash_distance,
            "version_conflict": result.duplicate_signals.version_conflict,
            "conflict_type": result.conflict_type,
            "processing_time_ms": result.processing_time_ms,
        }
        if result.conflict_type == "cross_group":
            details["conflicting_group_ids"] = result.conflicting_group_ids
        append_action_log(
            batch_id=record.batch_id,
            file_id=record.file_id,
            action="detect_duplicates_and_versions",
            from_path=record.current_path,
            details=details,
        )

        # A side-effect update gets its own, second, append-only log line (§18) —
        # never a rewrite of the affected record's own prior log entry. Both keys
        # below may be present together (a first-time pairing that also flips the
        # other record's rank) or just one (joining an existing group without a
        # rank change, or a rank flip within an already-existing group).
        if other_record is not None:
            side_effect_details = {
                "version_group_id": result.version_group_id,
                "version_rank": other_record.version_rank,
            }
            if result.other_record_needs_group_id:
                side_effect_details["joined_by"] = record.file_id
            if other_record.version_rank == "superseded":
                side_effect_details["superseded_by"] = record.file_id
            append_action_log(
                batch_id=record.batch_id,
                file_id=other_record.file_id,
                action="detect_duplicates_and_versions",
                from_path=other_record.current_path,
                details=side_effect_details,
            )

    return records
