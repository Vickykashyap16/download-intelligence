"""
Shared data shapes owned by Module 07 (Preview, Approval & Execution).

Split out from file_record.py the same way classification.py/duplicate.py/naming.py's
signal types are — file_record.py describes the FileRecord shape itself, not each
module's own type definitions. Unlike those three siblings, none of the types here are
persisted onto FileRecord or the metadata store: `PreviewRow` is preview_batch()'s
transient, in-memory output (WP-3), `ApprovalDecision` is an external input Module
07 consumes, never a field this module writes back onto FileRecord (Module 07 Design.md
§2/§8.1), `GateResult` is evaluate_gate()'s transient, in-memory output (WP-4,
§13), `MoveResult` is perform_move()'s transient, in-memory output (WP-5, §12/§14),
and `ExecutionOutcome` is `ExecutionEngine.execute_file()`'s own transient,
in-memory output (WP-7, §9) — composed entirely from `GateResult`/`MoveResult`
rather than introducing new business vocabulary. `ReconciliationOutcome`/
`ReconciliationReport` (WP-8, §13A) are the one exception to "transient, in-memory
only" among the types in this file: `reconcile_batch()`'s per-file classification
of a leftover `plan.json` entry against the action log and `FileRecord.processed_at`
does, for its `REPAIRED` outcome, cause a real `save_file_record()` write — the
report itself is still a transient, in-memory summary of what reconciliation did,
never persisted anywhere in its own right, the same way `MoveResult` describes a
real mutation without being the mutation's own storage record. Added here in
isolation (WP-1/WP-4/WP-5/WP-7/WP-8, Module 07 Implementation Plan.md) — no batch
orchestration, no Database/Runtime I/O logic of its own (though, unlike its
siblings, `MoveResult`/`ReconciliationReport` *describe the outcome of* a real
filesystem mutation or `FileRecord` repair — the mutation itself happens in
`pipeline/execution.py`'s `perform_move()`/`reconcile_batch()`, never here).

`UndoOutcome`/`UndoReport` (WP-11, §15) are the same kind of exception, for the
same reason: `undo_single_action()`'s `UNDONE` outcome causes a real file move
plus `save_file_record()` write; its `SKIPPED_MISSING`/`SKIPPED_COLLISION`/
`SKIPPED_NO_RECORD` outcomes each cause a real `log_error()` write. The report
itself remains a transient, in-memory summary, never persisted in its own right.

See Build-out/07 Preview, Approval & Execution/Module 07 Design.md §2 (architectural
decision: no Engine/Provider pattern for Module 07 — a plain ApprovalDecision input
instead), §9 (preview_batch()'s PreviewRow output; ExecutionEngine's six-step
sequence), §13 (evaluate_gate()'s GateResult output), §12/§14 (perform_move()'s
MoveResult output), §13A (reconcile_batch()'s five-step reconciliation
procedure and its ReconciliationOutcome/ReconciliationReport output), and §15
(undo_batch()'s reverse-chronological replay and its UndoOutcome/UndoReport
output) for the full rationale. Also see Governance/ARCHITECTURE_DECISIONS.md
decision 22, which records §2's decision as a permanent, cross-module
architectural pattern.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from src.models.classification import Category


class ApprovalDecisionType(str, Enum):
    """The three possible outcomes of a human (or the `auto`-tier default) deciding
    what to do with a suggested filing (Module 07 Design.md §10 step 2: "approve-as-
    suggested, approve-with-edit (new name and/or destination), or reject/skip").

    `REJECT` uses the exact action-log value confirmed by Open Decision OD-2's
    resolution (`Governance/ARCHITECTURE_DECISIONS.md` decision 21) — the design's
    own text predates that resolution and still reads "reject/skip" in places; this
    enum uses the single, now-confirmed term rather than carrying that ambiguity
    forward into code. Deliberately `str, Enum` (not a plain Enum): members ARE
    string instances, matching `Category`'s own established precedent
    (`src/models/classification.py`) so no custom JSON encoder is ever needed if a
    later work package chooses to serialize a decision for logging/debugging.
    """

    APPROVE_AS_SUGGESTED = "approve_as_suggested"
    APPROVE_WITH_EDIT = "approve_with_edit"
    REJECT = "reject"


@dataclass
class ApprovalDecision:
    """A single, already-made decision about one file, consumed (never interactively
    requested) by Module 07's execution gate (Module 07 Design.md §2/§13). This is
    the plain data-structure input that replaces a Provider for Module 07's human-
    approval step (§2, confirmed as `Governance/ARCHITECTURE_DECISIONS.md` decision
    22) — not a class hierarchy, not an ABC.

    `edited_name`/`edited_destination` are only meaningful when `decision ==
    ApprovalDecisionType.APPROVE_WITH_EDIT`; both stay `None` for the other two
    decision types. This dataclass does not validate that combination itself — §13's
    execution gate (a later work package) is where that behavior is enforced, exactly
    as `FileRecord`'s own dataclass doesn't self-validate cross-field invariants
    either. The mechanism that actually produces a set of these (an interactive chat
    table, a generated markup file, or something else) is explicitly out of scope
    here and everywhere else in Module 07's design (Open Decision OD-3, §2/§26) —
    this type is deliberately indifferent to how it was produced.
    """

    file_id: str
    decision: ApprovalDecisionType
    edited_name: Optional[str] = None
    edited_destination: Optional[str] = None


@dataclass
class PreviewRow:
    """One record's row in `preview_batch()`'s output (Module 07 Design.md §9): "one
    `PreviewRow` per eligible record: everything a reviewer needs to decide (old/new
    name, old/new destination, category, confidence, tier, which `Folder Rules.md`
    override applies)." Pure data — `preview_batch()` itself (a later work package)
    is what actually constructs these from a `FileRecord`; this dataclass only
    defines the shape.

    Field-by-field mapping to §9's six named items:
    - old name / new name       -> `original_name` / `suggested_name`
    - old destination / new     -> `current_path` / `suggested_destination` — the
      destination -> file's real, current location right now (mirroring
      `FileRecord.current_path`'s own meaning) versus Module 05's suggested,
      root-relative destination folder (e.g. `"Finance/"`).
    - category / confidence /   -> `category` / `confidence_score` / `tier`,
      tier                          matching `FileRecord`'s own field types exactly.
    - which override applies    -> `override`

    `original_name`, `suggested_name`, `current_path`, `suggested_destination`,
    `category`, `confidence_score`, and `tier` are typed as required (not Optional)
    because a `PreviewRow` is only ever built from a record that has already passed
    Module 07's own eligibility filter (§5: `category is not None`, `suggested_name
    is not None`, `confidence_score is not None` i.e. `tier` populated) — at that
    point in the pipeline these values are guaranteed present on the source
    `FileRecord`, so this type is deliberately more precise than `FileRecord`'s own
    `Optional[...]` typing for the same fields (which must stay `Optional` because
    `FileRecord` also represents records earlier in the pipeline, before Modules
    02/05/06 have run).

    `override` uses the exact vocabulary already established by Module 05's own
    action-log `details.override_applied` field (`Build-out/08 Logging & Reporting/
    Metadata & Log Schema.md`): `"exact_duplicate"` | `"superseded_version"` | `None`.
    A `review_required` record never reaches destination resolution at all (§11A
    step 1, absolute) and so never has an override value of its own kind here either
    — `review_required`-ness is read directly off `tier`, not encoded as a fourth
    override value. Populating this field from a specific record (§11A's four-step
    precedence order) is a later work package's responsibility (WP-2); this
    dataclass only reserves the slot, defaulting to `None` (no override — the normal
    category-to-destination mapping applies), the same "nothing unusual" default
    convention `ClassificationSignals`/`DuplicateSignals`/`NamingSignals` already use.
    """

    file_id: str
    original_name: str
    suggested_name: str
    current_path: str
    suggested_destination: str
    category: Category
    confidence_score: int
    tier: str
    override: Optional[str] = None


class GateResult(str, Enum):
    """The five fixed outcomes of `evaluate_gate()` (Module 07 Design.md §13,
    restated precisely from §0.4's invariant table) — WP-4, the module's own
    "highest-consequence decision point" (`Module 07 Implementation Plan.md`).

    Deliberately `str, Enum`, matching `ApprovalDecisionType`/`Category`'s own
    established precedent, for the same reason: members ARE string instances, so
    no custom JSON encoder is ever needed if a later work package logs a gate
    outcome for debugging.

    Maps directly onto §13's pseudocode branches, in the exact order they appear
    there:
    - `LEAVE_UNCHANGED_REVIEW_REQUIRED` — `tier == "review_required"` (I2:
      unconditional, no exception — checked first, before any decision is even
      consulted, so a forged/mistaken `ApprovalDecision` for such a record can
      never change this outcome).
    - `EXECUTE_AS_AUTO` — `tier == "auto"` (G4: no human decision needed).
    - `EXECUTE_AS_USER` — `tier == "approval_required"`, a recorded
      `ApprovalDecision` exists, and it is not `REJECT` (G4: `approved_by =
      "user"`, using the edited name/destination if `APPROVE_WITH_EDIT`
      supplied them — resolving that edit into an actual path remains WP-2's
      `resolve_destination_path()`'s job, performed later by whatever composes
      this gate's result, WP-7's `ExecutionEngine`).
    - `DECLINE_LOGGED` — `tier == "approval_required"`, a recorded
      `ApprovalDecision` exists, and it IS `REJECT` (Open Decision OD-2,
      resolved as `ARCHITECTURE_DECISIONS.md` decision 21 — logging the decline
      itself is WP-6's job; this gate only identifies that it must happen).
    - `LEAVE_UNCHANGED_NO_DECISION` — `tier == "approval_required"` and no
      recorded `ApprovalDecision` exists yet for this record ("absent decision
      is never treated as consent" — §13's own explicit rule).
    """

    LEAVE_UNCHANGED_REVIEW_REQUIRED = "leave_unchanged_review_required"
    EXECUTE_AS_AUTO = "execute_as_auto"
    EXECUTE_AS_USER = "execute_as_user"
    DECLINE_LOGGED = "decline_logged"
    LEAVE_UNCHANGED_NO_DECISION = "leave_unchanged_no_decision"


@dataclass
class MoveResult:
    """The outcome of one `perform_move()` call (Module 07 Design.md §12/§14,
    WP-5) — the Layer-1 "anticipated failure... converted into a normal, named
    fallback result" `ARCHITECTURE_DECISIONS.md` decision 18 requires, applied
    here to the first real filesystem mutation this pipeline performs.

    `success=True` -> `final_path` is set (the real, confirmed post-move
    location; always equal to the `destination` `perform_move()` was called
    with, since this module's move is a single atomic rename, never a
    multi-step operation that could land somewhere else) and `error_detail` is
    `None`. `success=False` -> `final_path` is `None` (the file did not move —
    it is still at its original `source` path, `perform_move()` never leaves a
    record claiming a location the file isn't actually at, §14) and
    `error_detail` carries a sanitized diagnostic string, mirroring
    `ARCHITECTURE_DECISIONS.md` decision 19's "never guess, disclose why"
    fallback shape.

    Deliberately carries no `FileRecord` field of any kind (not `file_id`, not
    `current_path`) — updating `FileRecord.current_path`/`processed_at`/etc.
    after a successful move is `ExecutionEngine`'s job (§9 step 6, WP-7's
    scope), never `perform_move()`'s own. This is structural, not just
    documented: `perform_move()` (see `pipeline/execution.py`) takes only
    `source`/`destination` paths, never a `FileRecord`, so it has no way to
    touch one even if it wanted to.
    """

    success: bool
    final_path: Optional[str] = None
    error_detail: Optional[str] = None


@dataclass
class ExecutionOutcome:
    """The per-file outcome of one `ExecutionEngine.execute_file()` call (Module 07
    Design.md §9, WP-7) — composed entirely from the already-existing `GateResult`
    (WP-4) and `MoveResult` (WP-5) types rather than introducing new business
    vocabulary of its own. Not named in the Implementation Plan's WP-7 "Owned
    components" list (only `ExecutionEngine` itself is named there) — added because
    `execute_file()` needs some return value for its own unit tests to assert
    against and for the not-yet-implemented WP-9 batch orchestration to eventually
    build its summary counts from (§10 step 4); composing two already-existing types
    is a smaller addition than inventing a new outcome vocabulary from scratch.
    Disclosed here rather than silently decided, the same "flagged, not silently
    assumed" discipline WP-5's own `resolve_available_destination()` addition
    already followed.

    `gate_result` is always populated — exactly `evaluate_gate()`'s own return
    value for this record, unchanged.

    `move_result` is `None` whenever no execution was attempted at all — i.e.
    `gate_result` is `LEAVE_UNCHANGED_REVIEW_REQUIRED`, `LEAVE_UNCHANGED_NO_
    DECISION`, or `DECLINE_LOGGED`. `move_result` is populated whenever
    `gate_result` is `EXECUTE_AS_AUTO`/`EXECUTE_AS_USER` and destination
    resolution/collision-check/folder-creation/move was actually attempted.
    `move_result.success` distinguishes a confirmed-successful filing
    (`current_path`/`processed_at`/etc. were updated) from an anticipated Layer-1
    failure at any of those stages (§14) — for the two failure cases that occur
    before `perform_move()` is ever actually called (a §22 path-escape rejection,
    or a bounded collision-suffix budget exhausted, §12/§14), `move_result` is a
    synthetically constructed `MoveResult(success=False, error_detail=...)`, not
    `perform_move()`'s own return value — `MoveResult`'s fields (`success`/
    `final_path`/`error_detail`) already express exactly the "did the file end up
    filed, and if not why" shape these anticipated failures need, so no third,
    narrower failure-shape type is introduced for them; this is a deliberate,
    disclosed reuse of `MoveResult` slightly beyond its original "one
    `perform_move()` call" framing (§12/§14, WP-5), not a silent scope change to
    `perform_move()` or `MoveResult` themselves, neither of which is modified by
    WP-7.
    """

    gate_result: GateResult
    move_result: Optional[MoveResult] = None


class ReconciliationOutcome(str, Enum):
    """The four terminal classifications `reconcile_batch()` (WP-8, §13A) can
    reach for one leftover `plan.json` entry, matching §13A's own numbered
    steps 2-4 exactly (step 1 is the match lookup itself, not a terminal
    outcome; step 4 has two distinct terminal sub-outcomes, `REPAIRED` and
    `INCONSISTENT_ERROR`, which is why the Implementation Plan describes this
    as a "four-way classification" despite §13A naming only steps 2/3/4).

    Deliberately `str, Enum`, matching every other outcome enum in this file
    (`ApprovalDecisionType`/`GateResult`) — members ARE string instances, so
    no custom JSON encoder is needed if a later work package logs or displays
    a reconciliation outcome.

    - `ALREADY_TERMINAL` — §13A step 2: a matching log entry exists and
      `FileRecord.processed_at` is already set. The operation completed
      fully before the crash; nothing to reconcile.
    - `SAFE_TO_RETRY` — §13A step 3: no matching log entry exists and
      `processed_at` is still `None`. The operation was never attempted (or
      staged but not reached); safe to retry from scratch.
    - `REPAIRED` — §13A step 4, disk-confirms-present sub-case: a matching
      log entry exists, `processed_at` is still `None` (crash between the
      log write and the `FileRecord` save), and the file is really at the
      log's `to` path. `FileRecord` is repaired from the log entry.
    - `INCONSISTENT_ERROR` — §13A step 4, disk-disagrees sub-case: a
      matching log entry exists, `processed_at` is still `None`, but the
      file is NOT at the log's `to` path (the log claims completion the disk
      doesn't confirm). Logged as an `error`; the record is left with
      `processed_at == None` so it remains eligible for a clean retry.
    """

    ALREADY_TERMINAL = "already_terminal"
    SAFE_TO_RETRY = "safe_to_retry"
    REPAIRED = "repaired"
    INCONSISTENT_ERROR = "inconsistent_error"


@dataclass
class ReconciliationReport:
    """The complete outcome of one `reconcile_batch(batch_id)` call (WP-8,
    §13A) — a transient, in-memory summary of what reconciliation did (or
    found there was nothing to do), keyed by `file_id`. Not itself persisted
    anywhere; `REPAIRED` outcomes are the only ones with a real, separate,
    persisted side effect (`save_file_record()`), and `INCONSISTENT_ERROR`
    outcomes have a real, separate, persisted side effect of their own
    (`log_error()`) — this report exists so a caller (WP-9's batch
    orchestration, or a test) can inspect what happened without re-deriving
    it from `Database/`/`Runtime/Logs/` after the fact.

    Not named in the Implementation Plan's own WP-8 "Owned components" list
    by this exact shape (only `ReconciliationReport` is named, with no field
    shape specified) — `outcomes: Dict[str, ReconciliationOutcome]` is a
    disclosed implementation-time judgment call, following the same
    `Dict[str, ...]` keyed-by-`file_id` convention already established by
    `evaluate_gate()`'s own `decisions: Dict[str, ApprovalDecision]`
    parameter (WP-4) and `duplicate_detector.py`'s `records_by_id`.

    An empty `outcomes` dict (`batch_id` present, nothing else) is the
    correct, valid result when `reconcile_batch()` finds no leftover
    `plan.json` for `batch_id` at all — not an error, not distinguished from
    "reconciled zero entries because the plan was empty" (an edge case with
    the same correct handling either way: nothing to do).
    """

    batch_id: str
    outcomes: Dict[str, ReconciliationOutcome] = field(default_factory=dict)


class UndoOutcome(str, Enum):
    """The terminal classification `undo_single_action()` (WP-11, §15) reaches
    for one move-type action-log entry, mirroring `ReconciliationOutcome`'s own
    shape/style (WP-8) — `str, Enum` for the same "no custom JSON encoder
    needed" reason every other outcome enum in this file already states.

    - `UNDONE` — the file was successfully moved back to its pre-move
      location and the `FileRecord`'s five WP-7-owned fields were reset
      (§13A's closing paragraph / §15's own "interaction with the idempotency
      mechanism" bullet).
    - `SKIPPED_IRREVERSIBLE` — `FileRecord.reversible` is `False` for this
      record. §15's own text: "`reversible = false`... means 'replaying this
      specific entry mechanically is not guaranteed safe without a human
      double-checking first,' and `undo_batch()` surfaces this rather than
      silently attempting it." Nothing is touched — no move, no `FileRecord`
      write, no `undo` log entry.
    - `SKIPPED_MISSING` — the log entry's own `to` path is not where the
      file actually is right now (already moved/deleted by something outside
      this pipeline since the original action, or already undone). Logged as
      an `error`, mirroring `reconcile_batch()`'s own "log claims completion,
      disk disagrees" anomaly handling (§13A step 4b) — the same disclosed
      "never guess, always disclose" discipline (`ARCHITECTURE_DECISIONS.md`
      decision 19), applied here instead of silently skipping.
    - `SKIPPED_COLLISION` — the file's original (`from`) location is no
      longer free — something else now occupies it (an unrelated event since
      the original move; §15 does not define a collision-suffix strategy for
      restoration, so this is treated as a Layer-1-style anticipated failure,
      never a silent overwrite of whatever is there now, matching §12/§14's
      "never a silent overwrite" discipline applied here to restoration
      instead of fresh filing). Logged as an `error`.
    - `SKIPPED_NO_RECORD` — a defensive branch: the log entry's `file_id` has
      no `FileRecord` in the metadata store at all. Structurally shouldn't be
      reachable (mirrors `reconcile_batch()`'s own identically-named
      defensive branch, §13A), logged rather than silently absorbed.
    - `FAILED` — every pre-check passed (reversible, source present at `to`,
      destination free at `from`) but the actual restore move itself still
      failed (e.g. a genuine OS-level error arising between the check and the
      move, or a permissions failure) — `perform_move()`'s own `MoveResult(
      success=False, ...)`, mirroring `ExecutionEngine.execute_file()`'s own
      step-4 move-failure handling (§12/§14) applied here to restoration
      instead of fresh filing. Logged as an `error`.
    """

    UNDONE = "undone"
    SKIPPED_IRREVERSIBLE = "skipped_irreversible"
    SKIPPED_MISSING = "skipped_missing"
    SKIPPED_COLLISION = "skipped_collision"
    SKIPPED_NO_RECORD = "skipped_no_record"
    FAILED = "failed"


@dataclass
class UndoReport:
    """The complete outcome of one `undo_batch(batch_id)` call (WP-11, §15) —
    a transient, in-memory summary, keyed by `file_id`, mirroring
    `ReconciliationReport`'s own shape/rationale exactly (WP-8): `UNDONE`/
    `SKIPPED_MISSING`/`SKIPPED_COLLISION`/`SKIPPED_NO_RECORD` outcomes each
    have their own real, separate, persisted side effect (a restored file
    plus `save_file_record()`, or a `log_error()` entry) — this report exists
    so a caller (a future CLI/UI, or a test) can inspect what happened
    without re-deriving it from `Database/`/`Runtime/Logs/` after the fact.

    Not named in the Implementation Plan's own WP-11 "Owned components" list
    by this exact shape (only `undo_batch(batch_id)`/`undo_single_action(
    log_entry)` are named, with no return-type shape specified for either) —
    a disclosed implementation-time judgment call, following the same
    precedent `ReconciliationReport` itself already established for the
    identical situation at WP-8.

    An empty `outcomes` dict (`batch_id` present, nothing else) is the
    correct, valid result when the batch has no move-type log entries to
    undo at all (e.g. every record in it was `review_required` or declined).
    """

    batch_id: str
    outcomes: Dict[str, UndoOutcome] = field(default_factory=dict)
