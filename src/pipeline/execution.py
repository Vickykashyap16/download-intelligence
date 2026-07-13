"""
Preview, Approval & Execution. HYBRID module: deterministic execution + the human
(not Claude) makes the approval call. This is the human checkpoint.

Architecture: Build-out/07 Preview, Approval & Execution/07 Preview, Approval & Execution.md

`build_preview()` and `execute_approved()` are pure code. The actual approve/edit/reject
decision comes from the user during a live run — this module doesn't decide FOR them.
Scaffold only: signatures defined, no logic yet.

--- Implementation note (added by WP-1, Module 07 Implementation Plan.md) ---
The canonical architecture is now Build-out/07 Preview, Approval & Execution/Module 07
Design.md (frozen 2026-07-12), which formally supersedes the pointer note referenced
above without deleting it (Governance/DOCUMENT_GROWTH_POLICY.md). The frozen design's
own function names (`preview_batch()`, `execute_batch()`, `ExecutionEngine`,
`log_user_correction()`) differ from `build_preview()`/`execute_approved()`/
`log_rejected_edit()` below, which predate that design and remain untouched,
unimplemented stubs pending their own later work packages (WP-3, WP-9, WP-10
respectively — see the Implementation Plan for the full decomposition). Only
`needs_execution()` below is WP-1's own addition; no other function in this file was
touched to add it.

--- Implementation note (added by WP-2, Module 07 Implementation Plan.md) ---
`resolve_precedence()`, `_reject_path_escape()`, and `resolve_destination_path()`
below are WP-2's own addition (§11/§11A/§22). No other function in this file —
including `needs_execution()` above — was touched to add them.

--- Implementation note (added by the WP-2 correction, `ARCHITECTURE_DECISIONS.md`
decision 23) --- `resolve_destination_path()`'s edited-destination handling has
been corrected to match decision 23: an edited destination is now honored
uniformly across every `override_type`, including `exact_duplicate`/
`superseded_version` — `review_required` remains the sole exception, and it never
reaches this function at all (§11A step 1). This replaces the interim,
self-flagged implementation-time judgment call the original WP-2 pass made (an
edit could never redirect an archive placement) — see `Module 07 Design.md`'s
"WP-2 Ambiguity Resolution: Edited Destination vs. Archive Override" addendum for
the full analysis. `resolve_precedence()` and `_reject_path_escape()` were not
touched by this correction.

--- Implementation note (added by WP-3, Module 07 Implementation Plan.md) ---
`preview_batch()` below is WP-3's own addition (§9, §10 step 1) — the frozen
design's pure, read-only preview-generation function. It is a different function
from the pre-existing `build_preview()` stub further down this file (which
predates the frozen design, renders a *display* table, and remains an
untouched, unimplemented stub — see the WP-1 note above). No other function in
this file was touched to add `preview_batch()`.

--- Implementation note (added by WP-4, Module 07 Implementation Plan.md) ---
`evaluate_gate()` below is WP-4's own addition (§13, restated from §0.4's
invariant table) — the module's own "highest-consequence decision point"
(`Module 07 Implementation Plan.md`), deliberately implemented and tested in
isolation before WP-7 wires it into `ExecutionEngine`. No other function in this
file was touched to add it.

--- Implementation note (added by WP-5, Module 07 Implementation Plan.md) ---
`check_real_collision()`, `apply_collision_suffix()`, `resolve_available_
destination()`, `perform_move()`, and `ensure_destination_folder()` below are
WP-5's own addition (§12, §14) — this module's first real filesystem mutation.
`resolve_available_destination()` is a scope clarification beyond the
Implementation Plan's own four literally-named "Owned components," added to make
WP-5's own Plan-specified acceptance criterion ("collision persists after the
bounded suffix-attempt budget is exhausted -> degrades to a named, logged
failure") actually testable within this work package, rather than left
untestable until WP-7 exists — flagged explicitly, not silently decided (see
its own docstring and the WP-5 implementation audit for the full disclosure).
Deliberately implemented using `Path.rename()` only, never `shutil.move()`/
`shutil.copy2()` — see `perform_move()`'s own docstring for why this is a
G1/§12 safety requirement, not a style preference. No other function in this
file was touched to add any of these five.

--- Implementation note (added by WP-6, Module 07 Implementation Plan.md) ---
`log_move()`, `log_error()`, and `log_decline()` below are WP-6's own addition
(§17/§25) — the logging helpers that wire the already-implemented
`append_action_log()` (`src/storage/runtime_io.py`, Module 01's own scope,
reused as-is per §17: "no new logging mechanism") for every action type this
module introduces: `move_rename` / `archive_duplicate` /
`archive_superseded_version` (all three via `log_move()`, selected by
`override_type`), `error`, and the new OD-2 value `reject`
(`ARCHITECTURE_DECISIONS.md` decision 21). `undo`'s own writer remains WP-11's
scope, untouched here. No other function in this file was touched to add these
three, and `append_action_log()` itself was not modified — only called.

--- Implementation note (added by WP-7, Module 07 Implementation Plan.md) ---
`ExecutionEngine` below is WP-7's own addition (§9) — the per-file orchestration
unit composing `evaluate_gate()` (WP-4), `resolve_precedence()`/`resolve_
destination_path()` (WP-2), `resolve_available_destination()`/`ensure_
destination_folder()`/`perform_move()` (WP-5), and `log_move()`/`log_error()`/
`log_decline()` (WP-6) into the fixed six-step sequence §9 specifies: gate ->
resolve destination -> collision re-check -> move -> log -> update record. None
of the six composed functions/their WP-1–6 module-level logic were modified to
add this — `ExecutionEngine.execute_file()` only calls them, in the fixed order
§9 requires. `ExecutionOutcome` (`src/models/execution.py`) is this work
package's one disclosed addition beyond the Plan's literal "Owned components"
list (`ExecutionEngine` alone) — see its own docstring for the full disclosure.
`current_path`/`processed_at`/`approved_by`/`approved_at`/`reversible` are
written in exactly one place in the entire WP-1–7 codebase: `execute_file()`'s
own step 6, below, and only after a confirmed-successful move (§8/§9 step 6).
No other function in this file was touched to add `ExecutionEngine`.

--- Implementation note (added by WP-8, Module 07 Implementation Plan.md) ---
`reconcile_batch()` below is WP-8's own addition (§13A, §18) — "the single
most novel piece of logic in this design" (§28 Risks), implemented and tested
in isolation against synthetically constructed `plan.json`/log/record
fixtures, independent of WP-7's actual runtime behavior (though several tests
also exercise it against WP-7's own real output, to verify requirement #10:
that a repaired `FileRecord` state is indistinguishable from one a real,
uninterrupted `ExecutionEngine.execute_file()` call would have produced).
Implements §13A's five-step reconciliation procedure exactly, via the raw
`Runtime/Temp/`/`Runtime/Logs/` I/O primitives WP-8 also added to
`src/storage/runtime_io.py` (`stage_batch_temp()`/`clear_batch_temp()` —
filling in their pre-existing, already-scaffolded stubs — plus the newly
added `write_batch_plan()`/`read_batch_plan()`/`read_action_log_entries()`).
`reconcile_batch()` is the only function in this file that calls
`src.storage.database`'s `load_metadata_store()`/`save_file_record()`
directly — every earlier WP-1–7 function operates on an already-in-hand
`FileRecord` its caller supplies, never loading or saving the store itself.
None of WP-1–7's own functions were modified to add this — `reconcile_batch()`
only calls `check_real_collision()` (WP-5, reused unmodified) and
`log_error()` (WP-6, reused unmodified) alongside the new WP-8 I/O
primitives. `reconcile_batch()` is not wired into any automatic call site by
this work package — invoking it at the start of a real batch run remains
WP-9's orchestration responsibility (§13A: "resolved... on the next run
before any new execution is attempted"); WP-8's own scope is limited to
`reconcile_batch()` existing as a correct, independently callable and
testable unit.

--- Implementation note (added by the WP-7 correction, approved High-severity
finding recorded during WP-9 scoping) --- `ExecutionEngine.execute_file()`'s
step 6 now also calls `save_file_record()` immediately after its five field
mutations — matching `reconcile_batch()`'s own already-approved mutate-then-
persist pattern for the identical field set. Before this correction, step 6
only ever mutated the in-memory `FileRecord`; nothing on the normal (non-
crash-repair) path ever persisted it, so every successful execution's own
bookkeeping was lost the moment the process exited. `current_path`/
`processed_at`/`approved_by`/`approved_at`/`reversible` remain written in
exactly two places in the file (`execute_file()` step 6, `reconcile_batch()`'s
`REPAIRED` branch) — both now also persist via `save_file_record()` at the
same site the mutation happens, never a third, separate call site.

--- Implementation note (added by WP-9, Module 07 Implementation Plan.md) ---
`execute_batch()` below is WP-9's own addition (§7/§9/§14, `ARCHITECTURE_
DECISIONS.md` decision 24), together with its two private helpers
`_validate_library_root()` and `_stage_plan_entry_for_record()`. None of
WP-1–8's own functions were modified to add it (beyond the WP-7 correction
disclosed immediately above, approved separately before this work package
began) — `execute_batch()` only calls already-implemented WP-1/WP-2/WP-5/
WP-7/WP-8 functions (`reconcile_batch()`, `needs_execution()`,
`resolve_precedence()`, `resolve_destination_path()`,
`resolve_available_destination()`, `write_batch_plan()`/`read_batch_plan()`,
`clear_batch_temp()`, `ExecutionEngine.execute_file()`, `log_error()`), never
reimplementing any of their logic. Gate evaluation, destination resolution's
final word, collision handling's final word, the actual move, action logging,
and `FileRecord` mutation/persistence all still happen exactly once each, all
inside `ExecutionEngine.execute_file()` — `execute_batch()` calls
`resolve_precedence()`/`resolve_destination_path()`/
`resolve_available_destination()` a *second* time per executing record, but
only for incremental `plan.json` staging purposes (decision 24 requires
this), never to decide or short-circuit what `ExecutionEngine` itself will
do. This is a disclosed, accepted double-computation cost of decision 24's
own design, not a duplication of business logic.

A structural point verified directly against the frozen design during this
work package's own implementation (not previously exercised, since nothing
before WP-9 ever called `reconcile_batch()` from live orchestration code):
`reconcile_batch()` loads and mutates its *own*, independently-fetched
`FileRecord` copies via `load_metadata_store()` — never the objects held in
whatever list its caller passes to it — so a `REPAIRED` record's persisted
fix is invisible to `execute_batch()`'s own in-memory `records` unless
explicitly synced back. `execute_batch()` therefore re-reads the metadata
store immediately after calling `reconcile_batch()` and copies the five
already-decided, already-persisted WP-7-owned fields onto the matching
in-memory objects before making any `needs_execution()` decision — a
synchronization step, not a new field-mutation decision, so it does not
duplicate WP-7/WP-8's own ownership of those fields' *values*.

--- Implementation note (added by WP-10, Module 07 Implementation Plan.md) ---
`capture_user_correction()` below is WP-10's own addition (§19/G7) — a
disclosed addition beyond the Plan's literal "Owned components" bullet, which
names only `log_user_correction()` (`src/storage/database.py`) and "a call
site invoked wherever an ApprovalDecision of type approve_with_edit or reject
is processed," without naming a specific function for that call site. This
function is that call site, following the same "frozen artifact wins over
descriptive Plan prose, disclose the addition" precedent already established
at WP-2/WP-3/WP-5/WP-8/WP-9 for their own equivalent disclosed additions.

Per the Implementation Plan's own explicit text, this package has "no
dependency on WP-2 through WP-9" and "could be implemented any time after
WP-1... a leaf." Consistent with that: `capture_user_correction()` is not
called from anywhere else in this file — not from `ExecutionEngine.
execute_file()`, not from `execute_batch()` — and no WP-1–9 function was
modified to add it. It exists as a complete, independently callable,
independently tested unit, ready to be invoked at the actual moment a human's
`ApprovalDecision` is first recorded (§10 step 2: "before execution") —
wherever Open Decision OD-3's still-undecided interactive mechanism, or its
own later CLI wiring (WP-12), ultimately produces one. Wiring an actual call
site into that not-yet-built mechanism is explicitly out of this work
package's own scope, the same way `reconcile_batch()`'s own WP-8 docstring
already disclosed that invoking *it* at batch startup was left for WP-9.

**Disclosed judgment call — what a `reject` correction's `field`/
`corrected_value` represent.** `Database/Learning/README.md`'s schema
restricts `field` to `"category" | "filename" | "destination"`, but a
`REJECT` decision doesn't target any one of those three — it declines the
entire suggested filing at once, and `ApprovalDecision` (WP-1) carries no
field that names what, specifically, was rejected. Module 07 Design.md §19
only says a correction is logged "once per edited/rejected field," without
resolving what "field" means for a decision that isn't about any single
field. This function resolves it as: `field="category"` (category is the
root signal `Rules/Folder Rules.md`'s mapping derives the rest of the
suggestion from, per §11A/§8.1) with `suggested_value` set to the record's
own `category.value` and `corrected_value=None` — honestly representing "no
specific alternative was proposed," not an invented placeholder string. This
is a disclosed interpretation of an underspecified rule, exactly the "flagged,
not silently assumed" treatment already applied to §15's imprecise "original
location" wording (WP-7/WP-8) and §11A's edited-destination-vs-archive-
override ambiguity (the WP-2 correction) — not a silent guess.

**Disclosed judgment call — only an actual change is captured.** For
`APPROVE_WITH_EDIT`, a correction is logged for `edited_name`/
`edited_destination` only when it is both set *and* different from the
record's own `suggested_name`/`suggested_destination` — an edit UI action
that happens to resubmit the original suggestion unchanged is not a
correction (G7 says "any edit... is captured," and an edit that changes
nothing is not, in substance, an edit). This mirrors `log_move()`'s own
already-established `name_differed_from_suggestion`/`destination_differed_
from_suggestion` comparison (WP-6) — the same "compare the outcome to the
original suggestion directly" discipline, applied here at correction-capture
time instead of at move-logging time.

--- Implementation note (added by WP-11, Module 07 Implementation Plan.md) ---
`log_undo()`, `undo_single_action()`, and `undo_batch()` below are WP-11's own
addition (§15) — the exact functional inverse of WP-7's `ExecutionEngine`,
built once that forward path was stable and independently audited, per the
Implementation Plan's own stated sequencing rationale. Reuses (never
reimplements): `perform_move()` (WP-5, the actual restore-move mechanics),
`check_real_collision()` (WP-5, checking the restore destination is free),
`read_action_log_entries()` (WP-8, reading the batch's own history back),
`load_metadata_store()`/`save_file_record()` (WP-1/WP-7-correction, reading
and persisting the reset `FileRecord`), `log_error()` (WP-6, the three
anomaly branches), and `_MOVE_LOG_ACTIONS` (WP-8's own constant, reused
verbatim to identify which log entries are even undoable). None of WP-1–10's
own functions were modified to add this.

**Disclosed addition — `log_undo()`.** Not named in the Plan's own "Owned
components" list (only `undo_batch()`/`undo_single_action()` are named), but
required by the same "exactly one typed wrapper per action, all funneling
through `append_action_log()`" architecture `log_move()`/`log_error()`/
`log_decline()` already established at WP-6 — `undo_single_action()` calling
`append_action_log()` directly would be the first exception to that pattern
anywhere in this file, not a defect exactly, but an inconsistency avoided
here rather than introduced.

**Disclosed addition — the `"undo"` action's own `details` shape.**
`Metadata & Log Schema.md` already reserves `action: "undo"` in its enum (has
done since Module 07's own action vocabulary was first drafted) but — unlike
every other action in that list — never defined its `details` shape, the one
action the schema doc itself never got around to drafting at implementation
time. This work package drafts it now, the same "drafted at this action's own
implementation time" discipline the schema doc's own text already describes
for every other action: `details: {"reversed_action": <the original
move_rename/archive_duplicate/archive_superseded_version action being
undone>}`. `approved_by` is hardcoded `"user"` for every `undo` entry — the
same structural reasoning `log_decline()` already established for `reject`
(§17): undo is inherently a deliberate human action in this design (there is
no automatic-undo code path anywhere in v1, per NG7/§15), so there is no
second value this could ever legitimately carry.

**Disclosed judgment call — why a forward-order replay is unsafe, made
concrete.** §15 states reverse-chronological order is necessary "because a
version-chain archive and a subsequent rename of the 'new latest' file could
otherwise be replayed out of order and produce a different final state," but
does not spell out the exact mechanism. Worked through here: if file A is
archived at T1 to make room for file B, which is then renamed into A's
now-vacated original location at T2 (T2 > T1), a **forward**-order replay
would attempt to restore A to that same location *before* undoing B's rename
— but B is still sitting there, since its own undo (T2) hasn't run yet. This
function's own restore-collision check (`check_real_collision()`, see
`SKIPPED_COLLISION` in `UndoOutcome`'s own docstring) would then correctly
refuse to overwrite B, but the *point* of reverse-chronological order is that
this collision should never arise in the first place under correct
operation: undoing T2 first vacates that path, so undoing T1 second finds it
free. A dedicated test constructs exactly this scenario and asserts the
forward-order replay hits `SKIPPED_COLLISION` for A while the real,
reverse-order `undo_batch()` implementation succeeds for both.

**Disclosed judgment call — what `undo_single_action()` does if handed a
non-move-type log entry.** §15 only ever describes undoing `move_rename`/
`archive_duplicate`/`archive_superseded_version` lines. `undo_single_action()`
raises `ValueError` for any other `action` value, mirroring `log_move()`'s
own established "an invalid input here is always a caller error, raise
loudly" precedent (WP-6) rather than silently no-op'ing — `undo_batch()`
itself never triggers this, since it pre-filters to `_MOVE_LOG_ACTIONS`
before calling `undo_single_action()` for each entry.

--- Implementation note (added by WP-13, Module 07 Implementation Plan.md;
resolves Design Review finding L2) --- Every `batch_id` this file writes to
the action log (`log_move()`/`log_error()`/`log_decline()`/`log_undo()`, via
`ExecutionEngine`/`execute_batch()`/`undo_batch()`) is `record.batch_id` —
the value `FileRecord.batch_id` already carries, set once by Module 01 at
discovery time and read-only ever after (`ARCHITECTURE_DECISIONS.md`
decision 2's ownership model; `src/models/file_record.py` line 87). Module 07
never mints, derives, or overrides a `batch_id` of its own — the same
by-precedent convention every `*_batch()` function since Module 04 already
follows (no module-specific `batch_id` parameter; it is always read off the
records being processed, e.g. `execute_batch()`'s own `records[0].batch_id`).
This note makes that precedent explicit for Module 07's own design record,
per Design Review finding L2 ("the action log's batch_id source for Module
07's own entries is never explicitly stated... resolves cleanly by
precedent") — no code or behavior changed to add this note.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

from src.models.execution import (
    ApprovalDecision,
    ApprovalDecisionType,
    ExecutionOutcome,
    GateResult,
    MoveResult,
    PreviewRow,
    ReconciliationOutcome,
    ReconciliationReport,
    UndoOutcome,
    UndoReport,
)
from src.models.file_record import FileRecord
from src.storage.database import load_metadata_store, log_user_correction, save_file_record
from src.storage.runtime_io import (
    append_action_log,
    clear_batch_temp,
    read_action_log_entries,
    read_batch_plan,
    write_batch_plan,
)

# --- §11A precedence / §11 destination resolution (WP-2, Module 07 Implementation
# Plan.md). Mirrors, but deliberately does not import, pipeline/naming.py's own
# _determine_override()/_ARCHIVE_DUPLICATES_PATH/_ARCHIVE_OLD_VERSIONS_PATH — both
# modules independently encode the same Rules/Folder Rules.md override table, per
# ARCHITECTURE_DECISIONS.md decision 5's "convention-following, not coupling"
# precedent (Module 03 vs. Module 02's own near-identical Engine/Provider classes). ---

_ARCHIVE_DUPLICATES_PATH = "~ARCHIVE~/Duplicates/"
_ARCHIVE_OLD_VERSIONS_PATH = "~ARCHIVE~/Old Versions/"


def needs_execution(record: FileRecord) -> bool:
    """True if Module 07 has not yet successfully executed `record` (Module 07
    Design.md §13A, resolves Design Review finding M2).

    The sole recognition signal is `record.processed_at is None` — mirroring Module
    04's `needs_duplicate_detection()` precedent (`pipeline/duplicate_detector.py`)
    of a dedicated function rather than a bare inline field check scattered across
    call sites, but with a simpler rule: unlike `duplicate_of`/`version_group_id`/
    `version_rank`, which can all legitimately stay `None` forever after a correct
    Module 04 run, `processed_at` has no legitimate permanent-`None`-after-execution
    case (§13A) — every record Module 07 successfully executes gets a real
    timestamp, and every record it doesn't execute keeps `processed_at == None`
    indefinitely until it is. `approved_by`/`approved_at`/`current_path` are set
    atomically alongside `processed_at` and are never checked independently for
    idempotency purposes (§13A) — `processed_at` alone is authoritative.

    This function only implements §13A's non-crash-interrupted recognition rule.
    The crash-mid-batch reconciliation procedure §13A also defines (leftover
    `Runtime/Temp/<batch_id>/plan.json` reconciled against the action log, with the
    real filesystem as the tie-breaker) is a separate, later work package (WP-8) —
    not implemented here.

    Intended to be applied at CLI-level eligibility selection (§5), the same way
    Module 06's own `confidence_score is None` check keeps an already-scored record
    from re-entering `score_confidence_batch()` — before a record ever reaches
    `preview_batch()` or `ExecutionEngine` (both later work packages).
    """
    return record.processed_at is None


def resolve_precedence(record: FileRecord) -> str:
    """Determines which of Module 07 Design.md §11A's four fixed, mutually
    exclusive outcomes applies to `record`, checked in the exact order §11A
    specifies (resolves Design Review finding M3):

    1. `tier == "review_required"` -> `"review_required"`. Checked first,
       absolute, no exception (I8).
    2. *(only reached if step 1 did not apply)* `duplicate_of is not None` ->
       `"exact_duplicate"`.
    3. *(only reached if step 2 did not apply)* `version_rank == "superseded"` ->
       `"superseded_version"`.
    4. *(only reached if none of the above apply)* -> `"normal"` (the ordinary
       category -> destination mapping applies).

    Independently re-derives the override from Module 04's own raw fields
    (`duplicate_of`, `version_rank`) rather than trusting Module 05's already-
    resolved `suggested_destination` string — the same "verify at the trust
    boundary, don't just trust the input" discipline §13's tier gate already
    applies to `tier`, applied here too (§11A). Steps 2/3 intentionally duplicate,
    rather than import, `pipeline/naming.py`'s own `_determine_override()` check —
    see this file's module-level comment for why.

    Called on every record before any destination is resolved for it (§11A). A
    `"review_required"` result means the record must be left completely
    unchanged; it must never be passed to `resolve_destination_path()`.
    """
    if record.tier == "review_required":
        return "review_required"
    if record.duplicate_of is not None:
        return "exact_duplicate"
    if record.version_rank == "superseded":
        return "superseded_version"
    return "normal"


def _reject_path_escape(component: str, field_name: str) -> None:
    """Rejects a path component that could escape the destination library root
    (Module 07 Design.md §22): an absolute path, or any `..` path segment. Raises
    `ValueError` rather than silently stripping/sanitizing — an adversarial or
    malformed value here is anomalous input that should fail loudly, not be
    silently rewritten into something that might still be wrong (the same "never
    guess" philosophy `ARCHITECTURE_DECISIONS.md` decision 19 already applies to
    fallback values, applied here to a security-relevant input class instead).

    Deliberately does not reject a literal `~` character — `"~ARCHIVE~/Duplicates/"`
    is a real, valid, non-expanding literal folder name (Rules/Folder Rules.md).
    `pathlib` never expands `~` on its own the way a shell does, so no special
    handling is needed to let it through.
    """
    as_path = Path(component)
    if as_path.is_absolute():
        raise ValueError(
            f"{field_name} {component!r} is an absolute path — rejected to avoid "
            f"escaping the destination library root (§22)."
        )
    if ".." in as_path.parts:
        raise ValueError(
            f"{field_name} {component!r} contains a '..' path segment — rejected to "
            f"avoid escaping the destination library root (§22)."
        )


def resolve_destination_path(
    record: FileRecord,
    library_root: Union[str, Path],
    override_type: str,
    edited_name: Optional[str] = None,
    edited_destination: Optional[str] = None,
) -> Path:
    """Resolves the real, absolute filesystem path a record should be filed at
    (Module 07 Design.md §11): `library_root / suggested_destination /
    suggested_name`, or the edited equivalents (§8.1). Pure — performs no
    filesystem access of any kind; the real, execution-time collision re-check
    against the destination folder's actual current contents is a later work
    package's responsibility (WP-5, §12), not this function's.

    `override_type` must be one of `resolve_precedence()`'s own four return
    values — call it first. This function does not compute precedence itself and
    defensively refuses `"review_required"` (§11A step 1: such a record is left
    completely unchanged and never has a destination resolved for it at all;
    calling this function for one is always a caller error).

    Destination-folder resolution, by `override_type` (`ARCHITECTURE_DECISIONS.md`
    decision 23, resolving the WP-2 implementation audit's Medium finding):
    - `"exact_duplicate"` -> `edited_destination` if supplied, else the fixed
      `~ARCHIVE~/Duplicates/` path (Rules/Folder Rules.md: "never the normal
      destination" — read, per decision 23, as governing Module 05's *automatic*
      mapping, not a human's later, explicit `APPROVE_WITH_EDIT` choice).
    - `"superseded_version"` -> `edited_destination` if supplied, else the fixed
      `~ARCHIVE~/Old Versions/` path, same reasoning.
    - `"normal"` -> `edited_destination` if supplied, else `record.suggested_
      destination` (the ordinary category mapping Module 05 already computed).

    An edited destination is therefore honored uniformly regardless of
    `override_type` — there is exactly one exception, `"review_required"`, and it
    is enforced structurally (the guard immediately above) rather than as a
    destination-folder rule, because a `review_required` record never reaches this
    function at all (§11A step 1, absolute, no exception). §8.1's edited-value
    substitution is unqualified in the frozen design; decision 23 confirms no
    unstated exception for the archive-override cases was ever intended (full
    six-dimension analysis: `Module 07 Design.md`'s "WP-2 Ambiguity Resolution"
    addendum).

    Filename resolution is independent of `override_type`: `edited_name` if
    supplied, else `record.suggested_name`. An edited *name* is always honored
    regardless of which destination-folder rule applies — renaming a file doesn't
    undermine the destination-folder safety behavior the override exists to
    enforce.

    Both the resolved destination-folder component and the resolved filename
    component are checked for path escape (§22, `_reject_path_escape()`) before
    being joined into an absolute path.
    """
    if override_type == "review_required":
        raise ValueError(
            "resolve_destination_path() must never be called for a "
            "review_required record (§11A step 1, absolute) — the caller should "
            "have already left this record completely unchanged."
        )

    if override_type == "exact_duplicate":
        default_destination = _ARCHIVE_DUPLICATES_PATH
    elif override_type == "superseded_version":
        default_destination = _ARCHIVE_OLD_VERSIONS_PATH
    elif override_type == "normal":
        default_destination = record.suggested_destination
    else:
        raise ValueError(f"Unrecognized override_type: {override_type!r}")

    # Decision 23: an edited destination is honored uniformly across every
    # override_type reached here — review_required (the sole exception) was
    # already rejected above and never reaches this line.
    destination_component = (
        edited_destination if edited_destination is not None else default_destination
    )

    name_component = edited_name if edited_name is not None else record.suggested_name

    _reject_path_escape(destination_component, "destination")
    _reject_path_escape(name_component, "name")

    return Path(library_root) / destination_component / name_component


def preview_batch(records: List[FileRecord]) -> List[PreviewRow]:
    """Builds one `PreviewRow` per eligible record — everything a reviewer needs
    to decide (Module 07 Design.md §9, §10 step 1): old/new name, old/new
    destination, category, confidence, tier, which `Rules/Folder Rules.md`
    override applies. Pure — no filesystem, log, or Database writes of any kind;
    safe to call repeatedly on the same input with no state change (§9's own
    stated property).

    Assumes `records` has already passed §5's CLI-level eligibility filter
    (`category`/`suggested_name`/`confidence_score` all populated, i.e. `tier`
    populated) — the same "caller has already filtered" convention every earlier
    module's own `*_batch()` function uses (e.g. `score_confidence_batch()` does
    not re-check `classification_signals is not None` either); this function does
    not re-validate eligibility itself.

    For each record, `resolve_precedence()` (§11A) determines which of the four
    fixed outcomes applies, and the row's `suggested_destination`/`override`
    fields are populated accordingly:
    - `"review_required"` -> `override=None` (a `review_required` record's
      `tier` alone already signals this — it is never encoded as a fourth
      override value, `PreviewRow`'s own docstring). `suggested_destination` is
      shown as Module 05's own, as-yet-unadjusted suggestion — informational
      only, since no destination is ever actually resolved for such a record
      (§11A step 1, absolute) and it will never be filed there.
    - `"exact_duplicate"` -> `override="exact_duplicate"`, `suggested_destination`
      is the fixed `~ARCHIVE~/Duplicates/` path — Module 07's own,
      independently-re-derived destination (§11A's "verify at the trust
      boundary" discipline), shown to the reviewer even if it happens to differ
      from Module 05's own `suggested_destination` string.
    - `"superseded_version"` -> `override="superseded_version"`,
      `suggested_destination` is the fixed `~ARCHIVE~/Old Versions/` path, same
      reasoning.
    - `"normal"` -> `override=None`, `suggested_destination` is
      `record.suggested_destination` unchanged (the ordinary category mapping
      Module 05 already computed).

    Deliberately does not take a `library_root` parameter and never calls
    `resolve_destination_path()` — at preview time there is no edit yet to
    apply (§10 step 1 precedes step 2's approval/edit step) and `PreviewRow`
    itself has no absolute-path field (only the root-relative destination-folder
    string a reviewer needs to recognize where a file would land, mirroring
    Module 05's own `suggested_destination` convention of staying root-relative,
    `Module 05 Design.md` §9). Turning a row's destination into a real,
    absolute filesystem path remains exclusively `resolve_destination_path()`'s
    job, performed later, at actual execution time.

    Tier-based grouping ("`auto` pre-checked / `approval_required` unchecked /
    `review_required` needs your attention", §10 step 1) is not performed by
    this function — each row's own `tier` field carries the information a later
    renderer needs to group by; the actual grouped/checked presentation is
    explicitly out of this package's scope, deferred to whatever OD-3 mechanism
    eventually renders it (`Module 07 Implementation Plan.md` WP-3).
    """
    rows = []
    for record in records:
        override_type = resolve_precedence(record)

        if override_type == "exact_duplicate":
            override_field: Optional[str] = "exact_duplicate"
            destination_field = _ARCHIVE_DUPLICATES_PATH
        elif override_type == "superseded_version":
            override_field = "superseded_version"
            destination_field = _ARCHIVE_OLD_VERSIONS_PATH
        else:
            # "review_required" and "normal" both leave override unset and show
            # Module 05's own suggested_destination unchanged — for
            # review_required this is purely informational (§11A step 1: no
            # destination is ever actually resolved for such a record).
            override_field = None
            destination_field = record.suggested_destination

        rows.append(PreviewRow(
            file_id=record.file_id,
            original_name=record.original_name,
            suggested_name=record.suggested_name,
            current_path=record.current_path,
            suggested_destination=destination_field,
            category=record.category,
            confidence_score=record.confidence_score,
            tier=record.tier,
            override=override_field,
        ))
    return rows


_VALID_TIERS = ("review_required", "auto", "approval_required")


def evaluate_gate(
    record: FileRecord,
    decisions: Dict[str, ApprovalDecision],
) -> GateResult:
    """Module 07's execution gate (Module 07 Design.md §13, restated precisely
    from §0.4's invariant table) — "the single most safety-critical piece of
    code in this module" (§28), implemented and tested in isolation (this
    package, WP-4) before WP-7 wires it into `ExecutionEngine`.

    Reads `record.tier` **directly off the `FileRecord` passed in**, never from
    a cached/precomputed "is this row checked" boolean handed in from the
    preview stage (§13's own explicit, binding requirement, restated at line
    228 of the design) — the same "verify at the trust boundary, don't just
    trust the input" discipline `ARCHITECTURE_DECISIONS.md` decisions 8/9
    already established, applied here to G3/I2, the one condition that must
    never be bypassable by any upstream mistake, including a hypothetical bug
    in whatever UI eventually implements OD-3. This is why the signature takes
    a `FileRecord`, not a `PreviewRow` or any other precomputed shape — a
    `PreviewRow`'s own `tier` field is a copy made at preview time, and using
    it here instead would reintroduce exactly the cached-boolean shortcut §13
    forbids.

    `decisions` is a `Dict[str, ApprovalDecision]` keyed by `file_id`, mirroring
    the established `records_by_id: Dict[str, FileRecord]` convention already
    used by `pipeline/duplicate_detector.py`'s own per-file lookup pattern — an
    implementation-time judgment call (the frozen design only says "an
    `ApprovalDecision` set," §5, without specifying a container shape), noted
    here rather than silently decided. Looked up by `record.file_id`; "absent"
    means no key for that `file_id` exists in the dict.

    Implements §13's pseudocode exactly, branch for branch:

        if record.tier == "review_required":
            leave record completely unchanged            # I2 — unconditional, no exception
        elif record.tier == "auto":
            execute with approved_by = "auto"             # G4
        elif record.tier == "approval_required":
            if a recorded ApprovalDecision exists for this record:
                if decision == reject/skip:
                    log the decline (Open Decision OD-2), leave record unchanged
                else:
                    execute with approved_by = "user"      # G4, using edited name/destination if provided
            else:
                leave record completely unchanged          # absent decision is never treated as consent

    `"reject/skip"` in the pseudocode above is the single, now-confirmed
    `ApprovalDecisionType.REJECT` value (Open Decision OD-2, resolved as
    `ARCHITECTURE_DECISIONS.md` decision 21 — `ApprovalDecisionType`'s own
    docstring already documents this collapsing of the design's pre-resolution
    wording into one confirmed term).

    **I2/G3 adversarial guarantee, made structurally true, not just tested:**
    the `review_required` branch is checked first and returns immediately,
    before `decisions` is ever consulted — so a maliciously or mistakenly
    constructed `ApprovalDecision` present in `decisions` for a
    `review_required` record's `file_id` can never change this function's
    outcome. There is no code path in this function that reads `decisions`
    before it has already ruled out `tier == "review_required"`.

    **Tiers other than the three §13 pseudocode names (including `None`) are a
    caller error, not a silently-guessed outcome.** §5's CLI-level eligibility
    filter guarantees `tier` is always populated with one of the three valid
    values by the time a record legitimately reaches this function; an
    unrecognized value here means that guarantee was violated somewhere
    upstream. Consistent with `resolve_destination_path()`'s own established
    "fail loudly on caller error, never guess" precedent in this same file, this
    is raised as a `ValueError` rather than silently mapped to any
    `GateResult` — silently guessing here (in either direction, execute or
    leave-unchanged) would mask a genuine upstream contract violation rather
    than surface it, and this function's entire purpose is to never let an
    ambiguous case resolve itself unnoticed.
    """
    if record.tier not in _VALID_TIERS:
        raise ValueError(
            f"evaluate_gate() received a record (file_id={record.file_id!r}) "
            f"with tier={record.tier!r}, not one of {_VALID_TIERS!r} — §5's "
            f"eligibility filter should have excluded this record before it "
            f"ever reached the gate; this is a caller error, not a case this "
            f"function will guess an outcome for."
        )

    if record.tier == "review_required":
        return GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED  # I2 — unconditional, no exception

    if record.tier == "auto":
        return GateResult.EXECUTE_AS_AUTO  # G4

    # record.tier == "approval_required"
    decision = decisions.get(record.file_id)
    if decision is None:
        return GateResult.LEAVE_UNCHANGED_NO_DECISION  # absent decision is never treated as consent
    if decision.decision == ApprovalDecisionType.REJECT:
        return GateResult.DECLINE_LOGGED
    return GateResult.EXECUTE_AS_USER  # G4, using edited name/destination if provided


# --- §12/§14 collision re-check & filesystem move mechanics (WP-5, Module 07
# Implementation Plan.md). This module's first real filesystem mutation. ---

_MAX_COLLISION_ATTEMPTS = 100
# The frozen design requires *a* bound ("degrades to a logged error after a
# bounded number of attempts, never an infinite loop", §14) but does not specify
# a number. 100 is an implementation-time judgment call — generous enough that
# no legitimate real-world collision run ever hits it, small enough that the
# degrade-to-error path is still reachable in bounded time — disclosed here
# rather than silently chosen, per this work package's own implementation audit.


def check_real_collision(path: Union[str, Path]) -> bool:
    """The real, execution-time collision check (§12): does a file already
    exist at `path`, in the destination library's actual, current contents,
    right now? Module 05's own collision detection is explicitly scoped to
    *within the current batch only* (`Module 05 Design.md` §9) — this is the
    *authoritative* check, deliberately performed here, synchronously, rather
    than pre-computed at preview time, since the destination library's true
    state can only be trusted at the moment of the actual write (the same
    reasoning Module 05's own design already used to justify deferring this
    exact check to Module 07).

    Deliberately the only function among WP-5's additions that reads real
    filesystem state rather than only reasoning about paths — kept as a single,
    narrow, named responsibility so every other WP-5 function can stay provably
    pure (§9's "no side effects" discipline applied as far as the physical
    mutation itself allows).
    """
    return Path(path).exists()


def apply_collision_suffix(path: Union[str, Path], attempt: int) -> Path:
    """Applies Module 05's own established collision-suffix convention
    (`_2`, `_3`, ...) to `path`, extended here to the real destination folder
    rather than only sibling batch records (§12). Mirrors
    `pipeline/naming.py`'s `resolve_within_batch_collision()` exactly —
    deliberately duplicated, not imported, per `ARCHITECTURE_DECISIONS.md`
    decision 5's "convention-following, not coupling" precedent (already
    applied twice elsewhere in this file, `resolve_precedence()`/
    `resolve_destination_path()`'s own module-level comment).

    `attempt` must be >= 1 and is 1-indexed to match Module 05's own counting
    convention exactly: `attempt=1` is the first retry after the *unsuffixed*
    path already collided, producing `_2` (Module 05's `count == 1` ->
    `stem_2{ext}`); `attempt=2` produces `_3`; in general `attempt=N` produces
    `_{N+1}`. Raises `ValueError` for `attempt < 1` — `attempt=0` would mean
    "no collision happened yet," which is a caller error (the unsuffixed path
    should simply be used as-is; this function is never the right call for
    that case).

    Pure — reasons only about the path string, performs no filesystem access
    of its own (that remains `check_real_collision()`'s sole responsibility).
    Only the last extension segment is treated as the suffix (`Path.suffix`'s
    own behavior, e.g. `"file.tar.gz"` -> stem `"file.tar"`, suffix `".gz"`) —
    identical to Module 05's own `_split_extension()`, not a new behavior
    introduced here.
    """
    if attempt < 1:
        raise ValueError(
            f"apply_collision_suffix() received attempt={attempt!r}, but "
            f"attempt must be >= 1 (attempt=1 is the first retry after the "
            f"unsuffixed path already collided) — attempt=0 is a caller error, "
            f"not a case this function produces a suffix for."
        )
    as_path = Path(path)
    return as_path.with_name(f"{as_path.stem}_{attempt + 1}{as_path.suffix}")


def resolve_available_destination(
    path: Union[str, Path],
    max_attempts: int = _MAX_COLLISION_ATTEMPTS,
) -> Optional[Path]:
    """Composes `check_real_collision()` and `apply_collision_suffix()` into
    the actual bounded collision-resolution loop §12/§14 describe: if `path`
    doesn't collide, it's returned unchanged; if it does, successive suffixed
    candidates are tried (via `apply_collision_suffix()`) until a free one is
    found or `max_attempts` is exhausted, at which point `None` is returned —
    "degrades to a logged error after a bounded number of attempts, never an
    infinite loop, never a silent overwrite" (§14). Logging that error is
    WP-6's job; this function only ever signals the exhausted case by
    returning `None`, never by logging or raising itself.

    **Scope note, disclosed rather than silently assumed:** the Implementation
    Plan's own "Owned components" list for WP-5 names four functions
    (`check_real_collision`, `apply_collision_suffix`, `perform_move`,
    `ensure_destination_folder`), not this one. This function is added because
    the Plan's own "Expected test additions"/"Acceptance criteria" for WP-5
    explicitly require the bounded-retry-degrades-to-failure *behavior* to be
    tested now, within this work package — which is impossible without some
    function that actually performs the loop; the two named primitives alone
    (a single collision check, a single suffix computation) cannot express a
    bounded loop by themselves. This is the minimal function that closes that
    gap using only WP-5's own already-scoped primitives, introduces no
    filesystem-mutating behavior beyond what §12 already assigns to WP-5, and
    performs no logging (WP-6) and no `ExecutionEngine` composition (WP-7) —
    both remain untouched, later work packages' responsibility.

    Pure with respect to anything other than reading filesystem existence
    (via `check_real_collision()`) — never creates, moves, or deletes
    anything.
    """
    if not check_real_collision(path):
        return Path(path)
    for attempt in range(1, max_attempts + 1):
        candidate = apply_collision_suffix(path, attempt)
        if not check_real_collision(candidate):
            return candidate
    return None  # budget exhausted — caller must log as `error`, never silently overwrite


def ensure_destination_folder(path: Union[str, Path]) -> None:
    """Creates `path` as a directory, including any missing parent
    directories, if it doesn't already exist — safe and idempotent, "never
    treated as a destructive or notable action requiring its own approval
    step" (§12, matching the pre-build spec note's "Edge cases" section
    verbatim). Calling this twice (or when the folder already exists) is a
    no-op, not an error.

    Deliberately does NOT silently succeed if `path` already exists as a
    regular *file* (not a directory) — `Path.mkdir(exist_ok=True)`'s own
    standard-library behavior already raises `FileExistsError` in exactly
    that case, which this function lets propagate rather than catching. That
    anomalous state (a plain file sitting where a destination folder needs to
    exist) is exactly the kind of case this project's "never guess" discipline
    (`ARCHITECTURE_DECISIONS.md` decision 19) says should fail loudly rather
    than being silently worked around.
    """
    Path(path).mkdir(parents=True, exist_ok=True)


def perform_move(source: Union[str, Path], destination: Union[str, Path]) -> MoveResult:
    """Performs the single, atomic move+rename operation that files a record
    at its resolved destination (§12) — "move + rename in one step... never a
    copy-then-delete" (§12's explicit requirement; G1's spirit: "a
    copy-then-delete window would violate G1 if the process crashed between
    the two").

    **Implemented using `Path.rename()` exclusively — deliberately never
    `shutil.move()`/`shutil.copy2()`.** This is a safety requirement, not a
    style choice: `shutil.move()` silently falls back to a copy-then-delete
    sequence whenever the source and destination are on different filesystems
    (`errno.EXDEV`), which is exactly the failure mode §12 forbids. `Path.
    rename()` (a thin wrapper over `os.rename()`) never does this — it either
    completes as a single atomic filesystem operation or raises `OSError`
    (including for the cross-device case), and this function treats that
    `OSError` as a normal, anticipated Layer-1 failure (`ARCHITECTURE_
    DECISIONS.md` decision 18) rather than a reason to fall back to copying.
    This file does not import `shutil` at all, structurally — not merely by
    convention — so this behavior can't regress by a future edit reaching for
    a `shutil` helper without noticing the constraint.

    Returns a `MoveResult` (never raises for an anticipated OS-level failure):
    `success=True, final_path=str(destination)` on a confirmed-complete move;
    `success=False, error_detail=<sanitized diagnostic>` if `Path.rename()`
    raises `OSError` for any reason (missing source, permissions, full
    volume, cross-device, etc.) — the source file is left exactly where it
    was (an atomic rename either fully completes or doesn't happen at all;
    there is no partial-move state to clean up), and `destination` never ends
    up holding a partial or duplicate file. `perform_move()` never touches any
    `FileRecord` field — it takes only paths, never a record — so
    `current_path` can only ever be updated by whatever later composes this
    result (`ExecutionEngine`, WP-7's own step 6, §9), and only after
    confirming `success=True` (§14: "the record's `current_path` is only ever
    updated after a move is confirmed complete").

    Destination-folder existence is `ensure_destination_folder()`'s
    responsibility, not this function's — call it first; this function does
    not create any directory itself.
    """
    source_path = Path(source)
    destination_path = Path(destination)
    try:
        source_path.rename(destination_path)
    except OSError as exc:
        return MoveResult(success=False, error_detail=str(exc))
    return MoveResult(success=True, final_path=str(destination_path))


# --- §17/§25 action logging integration (WP-6, Module 07 Implementation
# Plan.md). Wires the already-implemented append_action_log() (Module 01's own
# scope, src/storage/runtime_io.py) — no new logging mechanism, per §17. ---

_MOVE_ACTION_BY_OVERRIDE_TYPE = {
    "normal": "move_rename",
    "exact_duplicate": "archive_duplicate",
    "superseded_version": "archive_superseded_version",
}

_MAX_ERROR_DETAIL_LENGTH = 300


def _sanitize_error_detail(detail: str) -> str:
    """Truncates an already-stringified error diagnostic to a bounded length
    before it's ever written to the action log — mirrors `pipeline/
    classification.py`'s and `pipeline/metadata.py`'s own `_sanitize_error()`
    truncation bound (300 chars) and `"...(truncated)"` suffix exactly,
    independently implemented rather than imported (`ARCHITECTURE_DECISIONS.md`
    decision 5).

    Deliberately takes an already-stringified `detail: str`, not a raw
    `Exception` the way `_sanitize_error(exc: Exception)` does in those two
    modules — Module 07's own error source is `MoveResult.error_detail`
    (`perform_move()`, WP-5), which is already a string (`str(exc)`) by the
    time it reaches this function, not a live exception object. Same
    truncation behavior, adapted to the actual input shape available here
    rather than reshaping the caller to match an unrelated module's signature.
    """
    if len(detail) > _MAX_ERROR_DETAIL_LENGTH:
        return detail[:_MAX_ERROR_DETAIL_LENGTH] + "...(truncated)"
    return detail


def log_move(
    batch_id: str,
    record: FileRecord,
    override_type: str,
    executed_name: str,
    executed_destination: str,
    from_path: str,
    to_path: str,
    approved_by: str,
    collision_suffix_applied: bool = False,
) -> None:
    """Logs a confirmed-successful move (§17): `move_rename` for the ordinary
    category mapping, `archive_duplicate`/`archive_superseded_version` when
    the move's destination came from `Rules/Folder Rules.md`'s duplicate/
    superseded-version override rather than the normal mapping — selected from
    `override_type`, the same vocabulary `resolve_precedence()` (WP-2)
    already produces (`"normal"` / `"exact_duplicate"` / `"superseded_
    version"`). Raises `ValueError` for `"review_required"` or any
    unrecognized value — a `review_required` record is never executed, so
    logging a move for one is always a caller error, mirroring
    `resolve_destination_path()`'s own established "caller error, raise
    loudly" precedent in this file.

    Only ever call this for a *confirmed-successful* move — i.e. after
    `perform_move()` returned `MoveResult(success=True, ...)`. A failed move
    is `log_error()`'s responsibility instead, never this function's; this
    function has no failure branch of its own.

    `details` carries exactly what §17/§25 require to make the log line fully
    reconstructable in isolation, without needing to cross-reference
    `Database/Learning/`:
    - `override_applied` — `None` for `"normal"`, else `override_type` itself
      (`"exact_duplicate"` | `"superseded_version"` | `None`) — the exact
      vocabulary already established by Module 05's own `suggest_naming_and_
      destination` log entries' `override_applied` field.
    - `collision_suffix_applied` — passed through as given (WP-5's
      `resolve_available_destination()` is where this is actually determined;
      this function only records the caller's answer, it doesn't re-derive it).
    - `name_differed_from_suggestion` / `destination_differed_from_suggestion`
      — computed here, directly, by comparing `executed_name`/`executed_
      destination` (the actual, final values used — whether they came from a
      human edit, an override forcing an archive path, or neither) against
      `record.suggested_name`/`record.suggested_destination` (Module 05's
      original, permanent record, §8.1 — never mutated by this function or
      any other). This is a direct comparison of what happened vs. what was
      originally suggested, not an inference from whether an edit object was
      present — §25's own wording ("whether the executed name/destination
      differed from Module 05's original suggestion") is about the outcome,
      not the mechanism that produced it.

    Reads `record.suggested_name`/`record.suggested_destination` only — never
    writes any `FileRecord` field (ownership boundary, §8/G8; this function
    performs a log write only).
    """
    if override_type not in _MOVE_ACTION_BY_OVERRIDE_TYPE:
        raise ValueError(
            f"log_move() received override_type={override_type!r}, but a "
            f"move can only ever be logged for one of "
            f"{sorted(_MOVE_ACTION_BY_OVERRIDE_TYPE)!r} — a review_required "
            f"record is never executed (§11A step 1) and so never has a move "
            f"to log; passing it here is always a caller error."
        )
    action = _MOVE_ACTION_BY_OVERRIDE_TYPE[override_type]
    details = {
        "override_applied": None if override_type == "normal" else override_type,
        "collision_suffix_applied": collision_suffix_applied,
        "name_differed_from_suggestion": executed_name != record.suggested_name,
        "destination_differed_from_suggestion": executed_destination != record.suggested_destination,
    }
    append_action_log(
        batch_id=batch_id,
        file_id=record.file_id,
        action=action,
        from_path=from_path,
        to_path=to_path,
        approved_by=approved_by,
        details=details,
    )


def log_error(
    batch_id: str,
    file_id: str,
    error_detail: str,
    approved_by: str,
    from_path: Optional[str] = None,
) -> None:
    """Logs a caught, anticipated per-file failure (§14 Layer 1 — "logged as
    `error` with a sanitized `error_detail`"). `to` is always `None`, matching
    the action-log schema's own established convention for a non-move action
    (`Metadata & Log Schema.md`'s `to` field is only ever populated for
    `move_rename`) — the file never reached its destination, so there is no
    `to` location to record.

    `approved_by` is a required parameter, not defaulted — which value is
    correct depends on which `GateResult` branch the caller was in
    (`"auto"` for `EXECUTE_AS_AUTO`, `"user"` for `EXECUTE_AS_USER`) and this
    function has no way to know that on its own; guessing a default here would
    violate the same "never guess" discipline (`ARCHITECTURE_DECISIONS.md`
    decision 19) `error_detail`'s own sanitization already follows.

    `error_detail` is truncated via `_sanitize_error_detail()` before being
    written — never the raw, unbounded diagnostic string.
    """
    append_action_log(
        batch_id=batch_id,
        file_id=file_id,
        action="error",
        from_path=from_path,
        to_path=None,
        approved_by=approved_by,
        details={"error_detail": _sanitize_error_detail(error_detail)},
    )


def log_decline(batch_id: str, file_id: str, from_path: str) -> None:
    """Logs a human's explicit decline of a suggested filing (§17, Open
    Decision OD-2 — resolved as `ARCHITECTURE_DECISIONS.md` decision 21: the
    action value is `reject`, deliberately distinct from Module 01's `skip`,
    which means a categorically different thing — a file that was never
    queued in the first place, not a fully-processed suggestion a human
    reviewed and turned down). `to` is always `None` — nothing moved.

    `approved_by` is always `"user"`, hardcoded rather than accepted as a
    parameter — not a default, a structural fact: `GateResult.DECLINE_LOGGED`
    (WP-4, `evaluate_gate()`) can only ever arise from the `approval_required`
    branch with a recorded `ApprovalDecisionType.REJECT` decision, which is by
    definition always a human decision. There is no code path in this design
    where a decline is machine-originated, so there is no second value this
    parameter could ever legitimately need to carry.
    """
    append_action_log(
        batch_id=batch_id,
        file_id=file_id,
        action="reject",
        from_path=from_path,
        to_path=None,
        approved_by="user",
    )


# --- §9 ExecutionEngine (WP-7, Module 07 Implementation Plan.md). Composes
# WP-1/WP-2/WP-4/WP-5/WP-6 into the fixed six-step per-file sequence. Nothing
# above this point in the file is modified to add it. ---

def _iso_now() -> str:
    """UTC ISO-8601 timestamp, matching `append_action_log()`'s own convention
    (`src/storage/runtime_io.py`) and `pipeline/watch_ingest.py`'s established
    pattern — `processed_at`/`approved_at` use the same timestamp shape as
    every other timestamped field in this project. No shared timestamp helper
    exists anywhere in `core/` to import instead (checked before writing this);
    every module that needs one, including this one, inlines the same one-line
    call, consistent with how every existing timestamped field in this codebase
    is produced.
    """
    return datetime.now(timezone.utc).isoformat()


def _executed_destination_string(final_path: Path, library_root: Union[str, Path]) -> str:
    """Recovers the root-relative destination-folder string (e.g. `"Finance/"`,
    `"~ARCHIVE~/Duplicates/"`) `log_move()`'s `executed_destination` parameter
    needs, from `resolve_destination_path()`'s/`resolve_available_destination()`'s
    own combined absolute-path return value — `resolve_destination_path()`
    (WP-2) returns one joined `Path`, not the separate destination/name
    components `record.suggested_destination`/`suggested_name` are each stored
    as, so this function recovers the destination component post hoc rather
    than requiring any change to WP-2's own already-approved return shape
    (`Path.relative_to()` + `.parent`, pure path arithmetic, no filesystem
    access, no modification to `resolve_destination_path()` itself).

    A collision suffix (§12, WP-5) only ever changes the final path's *filename*
    component (`apply_collision_suffix()`'s own documented behavior — it calls
    `Path.with_name()`, which never touches `.parent`), so this function is
    safe to call with the post-collision-check `final_path` — the destination
    folder it reports is identical whether or not a suffix was applied.

    Trailing-slash convention matches `record.suggested_destination`'s own
    established format (`Module 05 Design.md` §9's `"Finance/"` example) so
    `log_move()`'s direct string comparison against `record.suggested_
    destination` is meaningful. A record resolved directly at the library
    root (no destination subfolder at all) returns `""` — not currently
    reachable by any real `Rules/Folder Rules.md` category mapping, which
    always names a subfolder, but handled rather than left to raise.
    """
    relative_parent = final_path.relative_to(Path(library_root)).parent
    if str(relative_parent) in (".", ""):
        return ""
    return relative_parent.as_posix() + "/"


class ExecutionEngine:
    """Per-file decision-making and execution (Module 07 Design.md §9) — fully
    deterministic, no Provider (`ARCHITECTURE_DECISIONS.md` decision 22),
    mirroring the shape of Module 04's `DuplicateDetectionEngine` (direct calls
    to already-implemented functions, no Provider layer) rather than Modules
    02/03's Engine->Provider shape.

    Trusts its caller to only ever hand it a record for which
    `needs_execution(record)` (WP-1) is already `True` — the same "trusting
    its caller's filtering" convention `DuplicateDetectionEngine.detect_file()`
    already established (`pipeline/duplicate_detector.py`: "Callers... are
    responsible for only calling this on records... that haven't already been
    processed... the Engine itself does not re-check this"). `execute_file()`
    does not call `needs_execution()` itself — that filtering is §5's CLI-level
    eligibility gate, applied by whatever later composes this engine into a
    batch (WP-9), not this class's own responsibility, per §9's own closing
    sentence: "A record is only ever handed to `ExecutionEngine` at all if
    `needs_execution(record)` ... is `True`."
    """

    def execute_file(
        self,
        record: FileRecord,
        decisions: Dict[str, ApprovalDecision],
        library_root: Union[str, Path],
        batch_id: str,
    ) -> ExecutionOutcome:
        """Runs the fixed six-step sequence §9 specifies for one record: gate ->
        resolve destination -> collision re-check -> move -> log -> update
        record. Steps 2 onward are only ever reached for a record the gate
        actually clears for execution (`EXECUTE_AS_AUTO`/`EXECUTE_AS_USER`) —
        every other `GateResult` returns immediately after step 1, the record
        left completely unchanged (§6/§10/§13), with the sole exception of
        `DECLINE_LOGGED`, which logs the decline (§17, WP-6) but still leaves
        every `FileRecord` field untouched.

        **Step 1 — gate (§13, WP-4).** `evaluate_gate()` is called unmodified,
        reading `record.tier` directly off the `FileRecord` passed in here
        (never a cached value) — this function does not re-implement or
        shortcut any part of that decision.

        **Step 2 — resolve destination (§11/§11A/§22, WP-2).**
        `resolve_precedence(record)` is re-derived here, independently of
        whatever `preview_batch()` may have computed earlier for the same
        record at preview time (`ARCHITECTURE_DECISIONS.md` decisions 8/9's
        "verify at the trust boundary" discipline, applied the same way
        `evaluate_gate()` already applies it to `tier`) — never trusts a
        `PreviewRow`'s own `override` field. `resolve_destination_path()` is
        then called with the edited name/destination from the recorded
        `ApprovalDecision`, if any (§8.1: an edit is executed but never
        written back onto `suggested_name`/`suggested_destination` — this
        function never assigns to either).

        The only `ValueError` `resolve_destination_path()` can actually raise
        at this specific call site is §22's path-escape rejection: the
        `"review_required"` branch is structurally unreachable here (a
        `review_required` record's `GateResult` is always
        `LEAVE_UNCHANGED_REVIEW_REQUIRED`, which already returned above,
        before `resolve_precedence()` is ever called), and the "unrecognized
        `override_type`" branch is unreachable because `resolve_precedence()`
        is a fully-tested pure function (WP-2) that never returns anything
        other than one of its four documented values. A path-escape rejection
        is therefore the one adversarial-input case this step is actually
        catching, treated as a Layer-1 anticipated failure (`ARCHITECTURE_
        DECISIONS.md` decision 18) consistent with every other anticipated
        failure in this method, even though §14's own enumerated failure list
        does not separately name it (a design cross-reference gap between §14
        and §22, not an implementation defect — flagged, not silently papered
        over).

        **Step 3 — collision re-check (§12/§14, WP-5).**
        `resolve_available_destination()` performs the real, execution-time
        check against the actual destination folder and applies a bounded
        collision-suffix retry. `None` (budget exhausted) is a Layer-1
        anticipated failure, logged and returned, never an infinite loop,
        never a silent overwrite (§14). `ensure_destination_folder()` is
        called immediately afterward, immediately before the move — safe,
        idempotent, never gated behind approval (§12) — its own `OSError`
        (e.g. a permissions failure) is likewise a Layer-1 anticipated
        failure.

        **Step 4 — move (§12, WP-5).** `perform_move()` is called unmodified.
        A failed move (`MoveResult(success=False, ...)`) is logged via
        `log_error()` and returned; `record.current_path` is never touched in
        this case (§14: "the record's `current_path` is only ever updated
        after a move is confirmed complete").

        **Step 5 — log (§17/§25, WP-6).** `log_move()` is only ever called
        after `perform_move()` returns `success=True` — never speculatively,
        never before the move is confirmed (G2's "guaranteed design
        behavior": every filesystem-mutating action is immediately followed
        by its log entry, never deferred).

        **Step 6 — update record (§8/§9 step 6).** The only point in the
        entire WP-1–7 codebase that ever assigns to `record.current_path`,
        `record.processed_at`, `record.approved_by`, `record.approved_at`, or
        `record.reversible` — and only reached after step 5's log write has
        already completed, matching §9's own fixed step order (log before
        record update, not the reverse). `record.suggested_name`/`suggested_
        destination` are never assigned to anywhere in this method (§8.1).

        `reversible` (§15) is set to `False` when either of §15's two trigger
        conditions holds: (a) a collision suffix was actually applied (the
        file did not land at the pristine, unsuffixed resolved path), or (b)
        the file's actual final destination folder is inside `~ARCHIVE~/`
        (checked against the *real*, executed destination string — not
        `override_type` alone — so that a duplicate/superseded-version record
        whose destination was redirected *out* of `~ARCHIVE~/` by an
        `APPROVE_WITH_EDIT` edit, `ARCHITECTURE_DECISIONS.md` decision 23,
        correctly is not flagged irreversible on that basis). §15's own text
        literally reads "the original location was itself inside
        `~ARCHIVE~/`," but its own parenthetical justification ("undoing an
        archive-of-a-duplicate could resurrect a name collision with the file
        that superseded it") unambiguously describes *this move's
        destination* landing in `~ARCHIVE~/`, not the file's pre-move source
        — `record.current_path` (the source) is never itself inside
        `~ARCHIVE~/` for any record this pipeline processes, so a literal
        reading of "original location" would make condition (b) permanently,
        vacuously false, which cannot be the intended rule. This is a
        disclosed interpretation of imprecise frozen-design wording (the same
        "flagged, not silently assumed" treatment already applied to WP-5's
        `perform_move()` docstring finding), not a silent judgment call.
        """
        gate_result = evaluate_gate(record, decisions)

        if gate_result in (
            GateResult.LEAVE_UNCHANGED_REVIEW_REQUIRED,
            GateResult.LEAVE_UNCHANGED_NO_DECISION,
        ):
            return ExecutionOutcome(gate_result=gate_result)

        source_path = record.current_path

        if gate_result == GateResult.DECLINE_LOGGED:
            log_decline(batch_id=batch_id, file_id=record.file_id, from_path=source_path)
            return ExecutionOutcome(gate_result=gate_result)

        # gate_result is EXECUTE_AS_AUTO or EXECUTE_AS_USER from here on (§13/G4).
        approved_by = "auto" if gate_result == GateResult.EXECUTE_AS_AUTO else "user"
        decision = decisions.get(record.file_id)
        edited_name = decision.edited_name if decision is not None else None
        edited_destination = decision.edited_destination if decision is not None else None

        # --- Step 2: resolve destination (§11/§11A/§22) ---
        override_type = resolve_precedence(record)
        try:
            resolved_path = resolve_destination_path(
                record, library_root, override_type,
                edited_name=edited_name, edited_destination=edited_destination,
            )
        except ValueError as exc:
            return self._fail(gate_result, batch_id, record, str(exc), approved_by, source_path)

        # --- Step 3: collision re-check (§12/§14) ---
        final_path = resolve_available_destination(resolved_path)
        if final_path is None:
            detail = (
                f"Collision-suffix attempts exhausted while resolving a free "
                f"destination for {resolved_path} — no move performed."
            )
            return self._fail(gate_result, batch_id, record, detail, approved_by, source_path)

        collision_suffix_applied = final_path != resolved_path

        try:
            ensure_destination_folder(final_path.parent)
        except OSError as exc:
            return self._fail(gate_result, batch_id, record, str(exc), approved_by, source_path)

        # --- Step 4: move (§12) ---
        move_result = perform_move(source_path, final_path)
        if not move_result.success:
            log_error(
                batch_id=batch_id, file_id=record.file_id,
                error_detail=move_result.error_detail, approved_by=approved_by,
                from_path=source_path,
            )
            return ExecutionOutcome(gate_result=gate_result, move_result=move_result)

        # --- Step 5: log (§17/§25) — only after a confirmed-successful move ---
        executed_name = final_path.name
        executed_destination = _executed_destination_string(final_path, library_root)
        log_move(
            batch_id=batch_id, record=record, override_type=override_type,
            executed_name=executed_name, executed_destination=executed_destination,
            from_path=source_path, to_path=move_result.final_path,
            approved_by=approved_by, collision_suffix_applied=collision_suffix_applied,
        )

        # --- Step 6: update record (§8/§9 step 6) — the sole write point ---
        now = _iso_now()
        record.current_path = move_result.final_path
        record.processed_at = now
        record.approved_by = approved_by
        record.approved_at = now
        record.reversible = not (
            collision_suffix_applied or executed_destination.startswith("~ARCHIVE~/")
        )
        # WP-7 correction (approved High-severity finding, recorded during WP-9
        # scoping): a FileRecord update is not complete until it is durably
        # persisted — matching reconcile_batch()'s own already-approved
        # mutate-then-persist pattern (WP-8) for this identical field set.
        # Persistence therefore belongs here, inside the same method that owns
        # the mutation, not in whatever later composes this Engine into a
        # batch (§16: "save_file_record() to upsert by file_id after
        # processing each record" is Module 07's own established pattern, not
        # a new one introduced by this correction). Only reached after a
        # confirmed-successful move and its log entry (step 5) — a failed
        # move never reaches this line, so no partial update is ever
        # persisted (§14: failures leave the record, and now the store,
        # exactly as they were).
        save_file_record(record)

        return ExecutionOutcome(gate_result=gate_result, move_result=move_result)

    @staticmethod
    def _fail(
        gate_result: GateResult,
        batch_id: str,
        record: FileRecord,
        detail: str,
        approved_by: str,
        source_path: str,
    ) -> ExecutionOutcome:
        """Shared Layer-1 anticipated-failure path (§14) for the two failure
        cases that occur before `perform_move()` is ever called — a §22
        path-escape rejection, or a bounded collision-suffix budget exhausted
        (§12). Logs the failure via `log_error()` (WP-6, unmodified) and
        returns a synthetically constructed `MoveResult(success=False, ...)`
        — see `ExecutionOutcome`'s own docstring for why this reuse is
        disclosed rather than silent. Never touches any `FileRecord` field —
        a failure here leaves the record exactly as it was, matching every
        other anticipated failure in this method.
        """
        log_error(
            batch_id=batch_id, file_id=record.file_id, error_detail=detail,
            approved_by=approved_by, from_path=source_path,
        )
        return ExecutionOutcome(
            gate_result=gate_result,
            move_result=MoveResult(success=False, error_detail=detail),
        )


# --- §13A crash-reconciliation (WP-8, Module 07 Implementation Plan.md). The
# single most novel piece of logic in this design (§28 Risks). Nothing above
# this point in the file is modified to add it. ---

_MOVE_LOG_ACTIONS = frozenset(_MOVE_ACTION_BY_OVERRIDE_TYPE.values())
# Reuses WP-6's own action mapping's value set ({"move_rename",
# "archive_duplicate", "archive_superseded_version"}) rather than re-listing
# the three action strings a second time — a single source of truth for "the
# three actions that mean a file was actually moved," shared by log_move()'s
# own dispatch (WP-6) and this module's own "was this file actually moved"
# check (WP-8).


def _find_matching_move_log_entry(
    log_entries: List[dict],
    batch_id: str,
    file_id: str,
    to_path: str,
) -> Optional[dict]:
    """§13A step 1: "check whether the action log has a completed
    move_rename/archive_duplicate/archive_superseded_version entry for that
    file_id matching the plan's intended to path." Matches on `batch_id` AND
    `file_id` AND `to` AND `action` being one of the three move-type actions
    — `batch_id` is not named explicitly in §13A's own step 1 text, but
    matching it is a disclosed, strictly-more-precise strengthening of the
    literal requirement (the same "verify at the trust boundary" carefulness
    `ARCHITECTURE_DECISIONS.md` decisions 8/9 already established elsewhere
    in this file), guarding against the theoretical case of the same
    `file_id`/`to` pair appearing in a completed log entry from a genuinely
    different batch. Returns the first match (log is append-only and
    chronological; `needs_execution()`/I7 already guarantee a given `file_id`
    is never legitimately re-executed after a real success, so more than one
    genuine match for the same `batch_id`/`file_id`/`to` should never occur
    in practice — this function does not assume that itself, it simply
    returns the first hit).
    """
    for entry in log_entries:
        if (
            entry.get("batch_id") == batch_id
            and entry.get("file_id") == file_id
            and entry.get("to") == to_path
            and entry.get("action") in _MOVE_LOG_ACTIONS
        ):
            return entry
    return None


def reconcile_batch(batch_id: str) -> ReconciliationReport:
    """Implements §13A's full five-step reconciliation procedure for one
    batch's leftover `Runtime/Temp/<batch_id>/plan.json`, resolving every
    entry to exactly one of `ReconciliationOutcome`'s four terminal states
    before returning. Intended to be called, per §13A, "on the next run
    before any new execution is attempted" — the actual call site (batch
    startup) is WP-9's orchestration responsibility, not wired in here.

    **No leftover plan (§13A's own implicit fifth case, a clean prior run):**
    if `read_batch_plan(batch_id)` returns `None` — either this batch was
    never staged, or it already completed cleanly and `clear_batch_temp()`
    already removed it — there is nothing to reconcile. Returns an empty
    report. `clear_batch_temp()` is still called in this case too (harmless
    and idempotent even if there's nothing there) purely for defensive
    tidiness, not because a `None` plan implies anything needs clearing.

    **Per-entry classification (§13A steps 1-4), for each `{"file_id",
    "from", "to"}` entry in the plan:**

    1. `_find_matching_move_log_entry()` performs step 1's match lookup.
    2. **Step 2 — `ALREADY_TERMINAL`:** a match exists and the loaded
       `FileRecord.processed_at` is already set. Nothing is written; the
       entry is simply classified and left out of the next plan (dropped by
       virtue of `clear_batch_temp()` removing the whole leftover plan file
       at the end — there is no partial-plan rewrite, matching §13A's own
       "once every entry... is reconciled... `clear_batch_temp()` runs").
    3. **Step 3 — `SAFE_TO_RETRY`:** no match exists and `processed_at` is
       still `None` (or the record can't be found at all, which implies the
       same "never confirmed executed" state). No write of any kind — the
       record is already correctly positioned for `needs_execution()` (WP-1)
       to pick it up again on the next `execute_batch()` call.
    4. **Step 4a — `REPAIRED`:** a match exists, `processed_at` is still
       `None`, and `check_real_collision(to_path)` (WP-5, reused unmodified
       — literally just "does a file exist at this path right now," exactly
       the check this step needs) confirms the file really is there. The
       `FileRecord` is repaired **from the log entry's own recorded
       values** (§13A: "the log is authoritative here, since it's the
       artifact closest in time to the actual filesystem write") —
       `current_path`/`to_path` and `approved_by`/`approved_at`/
       `processed_at` all sourced from the log entry, never guessed —
       and `save_file_record()` persists the repair immediately.
       `reversible` is computed the same way `ExecutionEngine.execute_file()`
       step 6 computes it (§15's two trigger conditions, checked against the
       real `to_path` string, not the log's `details.override_applied`
       alone — see the dedicated note below on why `override_applied` alone
       would be WRONG here after `ARCHITECTURE_DECISIONS.md` decision 23).
    5. **Step 4b — `INCONSISTENT_ERROR`:** a match exists, `processed_at` is
       still `None`, but the file is NOT at `to_path` — "the log line was
       written but the move itself failed or didn't complete" (§13A). Logged
       via `log_error()` (WP-6, reused unmodified) with an explicit
       inconsistency diagnostic; `processed_at` is deliberately left `None`
       so the record remains eligible for a clean retry — never silently
       assumed complete when the disk disagrees with the log.

    A defensive fifth branch — a match exists but the referenced `file_id`
    has no `FileRecord` in the metadata store at all — is treated as
    `INCONSISTENT_ERROR` too (logged, not silently skipped): this shouldn't
    be structurally reachable (every `file_id` that ever reaches the action
    log originates from a real, Module-01-created `FileRecord`), but per this
    project's "never guess, always disclose" discipline (`ARCHITECTURE_
    DECISIONS.md` decision 19), an anomaly this specific is surfaced, not
    silently absorbed into a different bucket.

    A second defensive branch — NO match exists but `processed_at` IS
    already set — is treated as `ALREADY_TERMINAL` (never re-executed, per
    I7): this also shouldn't be structurally reachable (`processed_at` is
    only ever set by `ExecutionEngine.execute_file()`'s own step 6, which
    only runs immediately after `log_move()`'s own step 5 already wrote a
    matching log entry, WP-7), but treating an already-processed record as
    anything other than terminal would risk a double-execution — the unsafe
    direction to guess wrong in, so this branch resolves toward safety, not
    toward "explain the anomaly by retrying."

    **Why `reversible` is repaired from the real `to_path` string, not
    `details.override_applied`:** `log_move()`'s own logged `details.
    override_applied` field (WP-6) records `resolve_precedence()`'s
    *classification* (`"exact_duplicate"`/`"superseded_version"`/`None`),
    which stays `"exact_duplicate"` even when `ARCHITECTURE_DECISIONS.md`
    decision 23 lets a human's `APPROVE_WITH_EDIT` redirect that record's
    real destination *outside* `~ARCHIVE~/`. A repair that read
    `override_applied is not None` as "this landed in `~ARCHIVE~/`" would
    incorrectly mark such a record `reversible=False` even though a live,
    uninterrupted `ExecutionEngine.execute_file()` run for the identical
    scenario would correctly have set `reversible=True` (`ExecutionEngine`'s
    own step 6 checks the real `executed_destination` string, precisely to
    stay correct under decision 23 — see its own docstring). Repairing from
    `override_applied` alone would therefore violate requirement #10 (a
    repaired state must be one a valid execution sequence could have
    produced) in exactly the decision-23 edit-override case. This function
    instead checks `"~ARCHIVE~" in Path(to_path).parts` — the same
    ground-truth signal `ExecutionEngine` itself uses — so `REPAIRED`
    results are provably identical to what `ExecutionEngine` would have
    produced for the same real outcome, not merely plausible.
    """
    report = ReconciliationReport(batch_id=batch_id)
    plan = read_batch_plan(batch_id)
    if not plan:
        clear_batch_temp(batch_id)  # defensive tidiness — safe no-op if nothing is there
        return report

    log_entries = read_action_log_entries()
    records_by_id = {record.file_id: record for record in load_metadata_store()}

    for planned_operation in plan:
        file_id = planned_operation["file_id"]
        to_path = planned_operation["to"]

        matching_entry = _find_matching_move_log_entry(log_entries, batch_id, file_id, to_path)
        record = records_by_id.get(file_id)
        already_processed = record is not None and record.processed_at is not None

        if matching_entry is not None and already_processed:
            report.outcomes[file_id] = ReconciliationOutcome.ALREADY_TERMINAL

        elif matching_entry is None and not already_processed:
            report.outcomes[file_id] = ReconciliationOutcome.SAFE_TO_RETRY

        elif matching_entry is None and already_processed:
            # Defensive branch — see docstring. Never re-executed (I7).
            report.outcomes[file_id] = ReconciliationOutcome.ALREADY_TERMINAL

        else:
            # matching_entry is not None and not already_processed — §13A step 4.
            if record is None:
                log_error(
                    batch_id=batch_id, file_id=file_id,
                    error_detail=(
                        f"Reconciliation: action log has a completed move entry for "
                        f"file_id={file_id!r} to {to_path!r}, but no FileRecord for "
                        f"this file_id exists in the metadata store — anomalous state."
                    ),
                    approved_by=matching_entry.get("approved_by", "auto"),
                    from_path=planned_operation.get("from"),
                )
                report.outcomes[file_id] = ReconciliationOutcome.INCONSISTENT_ERROR
            elif check_real_collision(to_path):
                details = matching_entry.get("details") or {}
                collision_suffix_applied = bool(details.get("collision_suffix_applied"))
                landed_in_archive = "~ARCHIVE~" in Path(to_path).parts
                record.current_path = to_path
                record.processed_at = matching_entry.get("timestamp")
                record.approved_by = matching_entry.get("approved_by")
                record.approved_at = matching_entry.get("timestamp")
                record.reversible = not (collision_suffix_applied or landed_in_archive)
                save_file_record(record)
                report.outcomes[file_id] = ReconciliationOutcome.REPAIRED
            else:
                log_error(
                    batch_id=batch_id, file_id=file_id,
                    error_detail=(
                        f"Reconciliation: action log claims file_id={file_id!r} was "
                        f"moved to {to_path!r}, but no file exists there — inconsistent "
                        f"state, log claims completion but disk disagrees."
                    ),
                    approved_by=matching_entry.get("approved_by", "auto"),
                    from_path=planned_operation.get("from"),
                )
                report.outcomes[file_id] = ReconciliationOutcome.INCONSISTENT_ERROR

    clear_batch_temp(batch_id)
    return report


# --- §7/§9/§14 batch orchestration & Layer 2 safety net (WP-9, Module 07
# Implementation Plan.md, `ARCHITECTURE_DECISIONS.md` decision 24). Composes
# WP-1/WP-2/WP-5/WP-7/WP-8 exactly as implemented — see the module docstring's
# WP-9 note above for the full disclosure. ---


def _validate_library_root(library_root: Union[str, Path]) -> Optional[str]:
    """Batch-level precondition (§14's closing paragraph): the destination
    library root must be set, must exist, must be a directory, and must be
    both readable and writable, or the *entire* batch is blocked before any
    file is attempted — "there is no meaningful per-file fallback for 'the
    whole library is unreachable,' and attempting one anyway risks silently
    filing files into the wrong place." Returns `None` if `library_root` is
    valid, else a human-readable detail string suitable for `log_error()`'s
    `error_detail` — never raises, mirroring every other Layer-1-style
    anticipated-failure check in this file (`resolve_available_destination()`
    returning `None`, `resolve_destination_path()` raising a caught
    `ValueError`) rather than letting a batch-level precondition escape as an
    uncaught exception.
    """
    if library_root is None or str(library_root).strip() == "":
        return "the destination library root is unset."
    root_path = Path(library_root)
    if not root_path.exists():
        return f"the destination library root {str(root_path)!r} does not exist."
    if not root_path.is_dir():
        return f"the destination library root {str(root_path)!r} is not a directory."
    if not (os.access(root_path, os.R_OK) and os.access(root_path, os.W_OK)):
        return f"the destination library root {str(root_path)!r} is not readable/writable."
    return None


def _stage_plan_entry_for_record(
    record: FileRecord,
    decisions: Dict[str, ApprovalDecision],
    library_root: Union[str, Path],
    batch_id: str,
) -> None:
    """`ARCHITECTURE_DECISIONS.md` decision 24: stages this one record's
    `plan.json` entry immediately before its own execution — never a separate
    whole-batch resolve-then-execute phase. Reuses (never reimplements)
    `resolve_precedence()` (WP-2), `resolve_destination_path()` (WP-2), and
    `resolve_available_destination()` (WP-5) for staging purposes only —
    decision 24 itself requires this composition. `ExecutionEngine.
    execute_file()` independently calls the same three functions again,
    moments later, for its own authoritative, real execution-time collision
    re-check (§12) — an accepted, disclosed double-computation cost of
    decision 24's own incremental-staging design (see this module's own
    docstring), not a new problem introduced here.

    Deliberately never calls `evaluate_gate()` (WP-4) — staging is attempted
    unconditionally for every `needs_execution()`-eligible, non-
    `review_required` record, regardless of what the gate will ultimately
    decide. A record whose gate later declines or leaves it unchanged simply
    leaves behind a harmless, never-executed `plan.json` entry: a future
    `reconcile_batch()` call correctly resolves it to `SAFE_TO_RETRY`, since
    no matching `move_rename`/`archive_*` log entry was ever written for it
    (§13A step 3). This keeps gate evaluation exclusively inside
    `ExecutionEngine`, never duplicated here (requirement: "execute_batch()
    must not duplicate ... gate evaluation").

    A `review_required` result from `resolve_precedence()` — reachable here,
    unlike inside `ExecutionEngine` (where the gate has already returned
    before `resolve_precedence()` is ever called) — means nothing is staged;
    the record is left for the gate to correctly leave completely unchanged
    (§11A step 1, I2).

    Any `ValueError` from `resolve_destination_path()` (a §22 path-escape
    rejection) or a `None` result from `resolve_available_destination()`
    (collision budget exhausted, §12/§14) is silently not staged here —
    `ExecutionEngine`'s own Layer-1 handling independently re-derives the
    identical destination/collision state moments later and will reach and
    log the identical failure itself. Staging a doomed entry for a failure
    `ExecutionEngine` is about to log anyway would be a harmless but pointless
    duplicate of work already correctly owned by WP-2/WP-5/WP-7, not a
    genuine gap.
    """
    override_type = resolve_precedence(record)
    if override_type == "review_required":
        return

    decision = decisions.get(record.file_id)
    edited_name = decision.edited_name if decision is not None else None
    edited_destination = decision.edited_destination if decision is not None else None

    try:
        resolved_path = resolve_destination_path(
            record, library_root, override_type,
            edited_name=edited_name, edited_destination=edited_destination,
        )
    except ValueError:
        return

    final_path = resolve_available_destination(resolved_path)
    if final_path is None:
        return

    planned_operations = read_batch_plan(batch_id) or []
    planned_operations.append({
        "file_id": record.file_id,
        "from": record.current_path,
        "to": str(final_path),
    })
    write_batch_plan(batch_id, planned_operations)


def execute_batch(
    records: List[FileRecord],
    decisions: Dict[str, ApprovalDecision],
    library_root: Union[str, Path],
) -> List[FileRecord]:
    """Batch orchestration (§9's `execute_batch()`) — mirrors every earlier
    module's `*_batch()` shape (no separate `batch_id` parameter; every
    batch-scoped call below derives it once from `records[0].batch_id`,
    matching the confirmed convention no other Module 04–06 `*_batch()`
    function takes a `batch_id` parameter of its own). Returns the *same*
    `records` list handed in, enriched in place (§6/§9) — this list, once
    returned, already *is* the batch result; no separate aggregation object
    is constructed (§10 step 4's counts-by-tier summary is the CLI/WP-12
    layer's job, computed from this same returned list).

    Fixed sequence, matching this work package's own required execution flow
    exactly:

    1. **Reconciliation runs first, unconditionally** (§13A: "before any new
       execution is attempted") — `reconcile_batch()` (WP-8) is called before
       anything else, including before the library-root precondition check,
       since reconciliation concerns *past* runs and is independent of
       whether *this* run's configuration is valid.
    2. **Post-reconciliation resync** — `reconcile_batch()` mutates its own,
       independently loaded `FileRecord` copies (`load_metadata_store()`),
       never the objects in `records` (see this module's own docstring for
       the full disclosure). This function re-reads the metadata store once,
       immediately after reconciliation, and copies the five already-decided
       WP-7-owned fields onto each matching in-memory record — purely a sync
       of already-persisted values, not a new mutation decision, so it does
       not duplicate WP-7/WP-8's ownership of *deciding* those values.
    3. **Batch-level library-root precondition** (§14's closing paragraph) —
       checked once, before any per-file work begins. If invalid, every
       still-eligible record gets one `log_error()` entry explaining the
       whole batch was blocked, `Runtime/Temp/<batch_id>/` is cleared, and
       the batch returns without a single file having been attempted.
    4. **Fixed processing order** (§7) — `sorted(records, key=lambda r:
       (r.discovered_at or "", r.file_id))`, the identical convention
       `confidence.py`/`duplicate_detector.py`/`naming.py` already establish.
    5. **Per record, in that order:** skip if `not needs_execution(record)`
       (already executed, or just resynced as such above — I7's idempotency
       guarantee); otherwise stage this one record's `plan.json` entry
       (decision 24, step 4 above) immediately before calling
       `ExecutionEngine.execute_file()` for it — never a separate whole-batch
       staging pass.
    6. **Layer 2** (§14) — the `ExecutionEngine.execute_file()` call is
       wrapped in a broad `try/except Exception`, catching anything genuinely
       unanticipated (nothing this function's own steps 3/5 above can raise
       is caught here — those already handle their own anticipated failures
       without raising); logs an `error` action and continues to the next
       record, never letting one file's unexpected exception abort the rest
       of the batch (G6/I4).
    7. **Cleanup** — `clear_batch_temp(batch_id)` once every eligible record
       has reached a terminal state (executed, failed-and-logged, or
       skipped).
    8. **Return** — the same `records` list, enriched in place.

    Never calls `evaluate_gate()`, `resolve_destination_path()` (for a final,
    authoritative answer — only for staging, see step 5 above),
    `resolve_available_destination()` (likewise), `perform_move()`,
    `log_move()`/`log_decline()`, or any `FileRecord`-field-mutating
    assignment itself — every one of those remains exclusively
    `ExecutionEngine`'s own responsibility (WP-7), called through exactly one
    call site in this function (step 5's `execute_file()` call).
    """
    if not records:
        return records

    batch_id = records[0].batch_id
    # Disclosed assumption: every record in one execute_batch() call shares
    # the same batch_id — the natural definition of "a batch," matching the
    # Implementation Plan's own signature (no separate batch_id parameter).
    # Not defensively re-validated per-record, mirroring the same
    # "trust the caller" precedent ExecutionEngine itself already documents
    # for needs_execution() filtering.

    # --- Step 1: reconciliation (§13A) — always first, unconditionally. ---
    reconcile_batch(batch_id)

    # --- Step 2: post-reconciliation resync — see docstring above. ---
    fresh_by_id = {fresh.file_id: fresh for fresh in load_metadata_store()}
    for record in records:
        fresh = fresh_by_id.get(record.file_id)
        if fresh is not None:
            record.current_path = fresh.current_path
            record.processed_at = fresh.processed_at
            record.approved_by = fresh.approved_by
            record.approved_at = fresh.approved_at
            record.reversible = fresh.reversible

    # --- Step 3: batch-level library-root precondition (§14). ---
    root_error = _validate_library_root(library_root)
    if root_error is not None:
        for record in records:
            if needs_execution(record):
                log_error(
                    batch_id=batch_id, file_id=record.file_id,
                    error_detail=(
                        f"Batch blocked before any file was attempted: {root_error}"
                    ),
                    approved_by="auto", from_path=record.current_path,
                )
        clear_batch_temp(batch_id)
        return records

    # --- Step 4: fixed processing order (§7). ---
    ordered_records = sorted(records, key=lambda r: (r.discovered_at or "", r.file_id))

    engine = ExecutionEngine()
    for record in ordered_records:
        if not needs_execution(record):
            continue

        # --- Step 5: incremental plan.json staging (decision 24) —
        # immediately before this record's own execution. ---
        _stage_plan_entry_for_record(record, decisions, library_root, batch_id)

        # --- Step 6: Layer 2 — the outer, batch-orchestration safety net. ---
        try:
            engine.execute_file(record, decisions, library_root, batch_id=batch_id)
        except Exception as exc:  # noqa: BLE001 — deliberately broad; this IS Layer 2 (§14)
            log_error(
                batch_id=batch_id, file_id=record.file_id,
                error_detail=f"Unanticipated error during execution: {exc}",
                approved_by="auto", from_path=record.current_path,
            )
            continue

    # --- Step 7: cleanup. ---
    clear_batch_temp(batch_id)

    # --- Step 8: return the same list, enriched in place. ---
    return records


# --- §19/G7 Database/Learning/ interaction (WP-10, Module 07 Implementation
# Plan.md). A leaf: no dependency on, and no call from, WP-2 through WP-9. See
# this module's own docstring's WP-10 note for the full disclosure, including
# the two judgment calls this function makes explicit. ---


def capture_user_correction(record: FileRecord, decision: ApprovalDecision) -> None:
    """Captures every inline edit/rejection an `ApprovalDecision` represents to
    `Database/Learning/User Corrections.json` (§19/G7), via `log_user_correction()`
    (`src/storage/database.py`) — never reimplementing that function's own
    append-only I/O, only deciding *whether* and *what* to log.

    - `APPROVE_AS_SUGGESTED` → nothing was corrected; this function returns
      without calling `log_user_correction()` at all.
    - `APPROVE_WITH_EDIT` → up to two entries, one per field that actually
      changed: `edited_name` only if set and different from `record.
      suggested_name`; `edited_destination` only if set and different from
      `record.suggested_destination`. An edit that resubmits the original,
      unchanged suggestion is not a correction (disclosed in this module's own
      docstring).
    - `REJECT` → exactly one entry, `field="category"`, `suggested_value=
      record.category.value`, `corrected_value=None` — the disclosed
      interpretation of what a whole-suggestion rejection means for a schema
      that only names a single field per entry (full reasoning in this
      module's own docstring).

    Passive capture only (NG6) — this function never reads `User Corrections.
    json` back and never influences `record`, `decision`, or any later
    execution step; it is called purely for its own side effect. Does not
    itself decide *when* it should be called — per this work package's own
    "no dependency on WP-2 through WP-9" scope, nothing in `ExecutionEngine`
    or `execute_batch()` calls this function; wiring an actual call site into
    the still-undecided approval mechanism (Open Decision OD-3) or its later
    CLI wiring (WP-12) is out of this work package's scope.
    """
    if decision.decision == ApprovalDecisionType.REJECT:
        log_user_correction(
            file_id=record.file_id,
            field_name="category",
            suggested_value=record.category.value if record.category is not None else None,
            corrected_value=None,
            category=record.category.value if record.category is not None else None,
        )
        return

    if decision.decision != ApprovalDecisionType.APPROVE_WITH_EDIT:
        return  # approve_as_suggested — nothing was corrected

    category_value = record.category.value if record.category is not None else None

    if decision.edited_name is not None and decision.edited_name != record.suggested_name:
        log_user_correction(
            file_id=record.file_id,
            field_name="filename",
            suggested_value=record.suggested_name,
            corrected_value=decision.edited_name,
            category=category_value,
        )

    if (
        decision.edited_destination is not None
        and decision.edited_destination != record.suggested_destination
    ):
        log_user_correction(
            file_id=record.file_id,
            field_name="destination",
            suggested_value=record.suggested_destination,
            corrected_value=decision.edited_destination,
            category=category_value,
        )


# --- §15 rollback / undo mechanism (WP-11, Module 07 Implementation Plan.md).
# The exact functional inverse of WP-7's ExecutionEngine. See this module's
# own docstring's WP-11 note for the full disclosure of every judgment call
# made below. Note: `src/storage/runtime_io.py`'s own pre-existing
# `undo_batch(batch_id)` stub is deliberately left untouched/superseded by
# the differently-homed functions below — the same "a stub in file A
# superseded by a function in file B, disclosed rather than silently
# reused" precedent WP-9 (`execute_approved()` -> `execute_batch()`) and
# WP-10 (`log_rejected_edit()` -> `log_user_correction()`/
# `capture_user_correction()`) already established. Undo is genuine
# decision-making (reverse-chronological ordering, the reversible-skip rule,
# per-entry FileRecord reset) — the same reasoning that already placed
# `reconcile_batch()` in this file rather than in `runtime_io.py`'s own
# raw-I/O-only territory, applied here identically. ---


def log_undo(batch_id: str, file_id: str, from_path: str, to_path: str,
             reversed_action: str) -> None:
    """Logs a completed undo (§15) — the fourth and final typed wrapper around
    `append_action_log()` (WP-1), alongside `log_move()`/`log_error()`/
    `log_decline()` (WP-6). Drafts `action: "undo"`'s own `details` shape for
    the first time (reserved but never defined in `Metadata & Log Schema.md`
    — see this module's own docstring's WP-11 note).

    `from_path`/`to_path` here are the *undo's own* from/to — i.e. already
    swapped relative to the original entry being reversed (`from_path` is
    where the file was just found — the original entry's own `to`; `to_path`
    is where it was just restored to — the original entry's own `from`),
    matching §15's literal "replay... with from/to swapped" wording exactly
    in the log's own record of what happened, not just in the mechanics.

    `approved_by` is always `"user"` — undo is inherently a deliberate human
    action in this design (NG7/§15: there is no automatic-undo code path in
    v1), the same structural reasoning `log_decline()` already established
    for `reject` (WP-6).
    """
    append_action_log(
        batch_id=batch_id,
        file_id=file_id,
        action="undo",
        from_path=from_path,
        to_path=to_path,
        approved_by="user",
        details={"reversed_action": reversed_action},
    )


def undo_single_action(log_entry: dict) -> UndoOutcome:
    """Reverses one `move_rename`/`archive_duplicate`/`archive_superseded_
    version` action-log entry (§15): moves the file back to its pre-move
    location and resets the affected `FileRecord`'s five WP-7-owned fields —
    `processed_at`/`approved_by`/`approved_at` to `None`, `current_path`
    restored, `reversible` reset to its dataclass default (`true`) — so
    `needs_execution()` (WP-1) correctly recognizes the record as eligible
    again (§13A's closing paragraph).

    Raises `ValueError` if `log_entry["action"]` is not one of the three
    undoable actions — a caller error, mirroring `log_move()`'s own
    established precedent (WP-6) rather than silently no-op'ing. See this
    module's own docstring's WP-11 note for why a `reversible=False` record
    is skipped with zero side effects, and for the exact mechanism by which
    an out-of-order restore could collide with a still-in-place later move
    (`SKIPPED_COLLISION`).

    Never touches `Database/FileIndex/*`, `Database/History/
    version_history.json`, or `Database/Learning/User Corrections.json` (§15's
    own explicit non-goals) — this function reads and writes only the action
    log and the one `FileRecord` its own `file_id` identifies.
    """
    action = log_entry.get("action")
    if action not in _MOVE_LOG_ACTIONS:
        raise ValueError(
            f"undo_single_action() received action={action!r}, but only "
            f"{sorted(_MOVE_LOG_ACTIONS)!r} entries can ever be undone (§15) — "
            f"passing any other action here is always a caller error."
        )

    batch_id = log_entry["batch_id"]
    file_id = log_entry["file_id"]
    original_from = log_entry["from"]
    original_to = log_entry["to"]

    records_by_id = {record.file_id: record for record in load_metadata_store()}
    record = records_by_id.get(file_id)
    if record is None:
        log_error(
            batch_id=batch_id, file_id=file_id,
            error_detail=(
                f"Undo: action log has a {action!r} entry for file_id={file_id!r}, "
                f"but no FileRecord for this file_id exists in the metadata store "
                f"— anomalous state."
            ),
            approved_by="user", from_path=original_to,
        )
        return UndoOutcome.SKIPPED_NO_RECORD

    if not record.reversible:
        return UndoOutcome.SKIPPED_IRREVERSIBLE  # nothing touched — surfaced via this return value only (§15)

    if not check_real_collision(original_to):
        log_error(
            batch_id=batch_id, file_id=file_id,
            error_detail=(
                f"Undo: action log claims file_id={file_id!r} is at {original_to!r}, "
                f"but no file exists there — cannot undo from a location the file "
                f"isn't actually at."
            ),
            approved_by="user", from_path=original_to,
        )
        return UndoOutcome.SKIPPED_MISSING

    if check_real_collision(original_from):
        log_error(
            batch_id=batch_id, file_id=file_id,
            error_detail=(
                f"Undo: cannot restore file_id={file_id!r} to its original location "
                f"{original_from!r} — something else now occupies that path. Not "
                f"overwritten (§12/§14's never-silently-overwrite discipline, "
                f"applied here to restoration)."
            ),
            approved_by="user", from_path=original_to,
        )
        return UndoOutcome.SKIPPED_COLLISION

    move_result = perform_move(original_to, original_from)
    if not move_result.success:
        log_error(
            batch_id=batch_id, file_id=file_id,
            error_detail=move_result.error_detail, approved_by="user",
            from_path=original_to,
        )
        return UndoOutcome.FAILED

    log_undo(
        batch_id=batch_id, file_id=file_id,
        from_path=original_to, to_path=original_from,
        reversed_action=action,
    )

    record.processed_at = None
    record.approved_by = None
    record.approved_at = None
    record.current_path = move_result.final_path
    record.reversible = True  # FileRecord's own dataclass default
    save_file_record(record)

    return UndoOutcome.UNDONE


def undo_batch(batch_id: str) -> UndoReport:
    """Reverses every undoable action-log entry for `batch_id`, in **reverse
    chronological order** (§15: "undoing the most recent action first") —
    see this module's own docstring's WP-11 note for the worked example of
    why forward order can produce a different, incorrect final state.

    Filters `read_action_log_entries()` (WP-8) to this `batch_id` and to
    `_MOVE_LOG_ACTIONS` (WP-8's own constant, reused — `reject`/`error`/
    `discover`/etc. entries are never undoable, §15) before sorting by
    `timestamp` descending and calling `undo_single_action()` once per
    remaining entry — never reimplementing any of that function's own
    per-entry logic here.
    """
    entries = [
        entry for entry in read_action_log_entries()
        if entry.get("batch_id") == batch_id and entry.get("action") in _MOVE_LOG_ACTIONS
    ]
    entries.sort(key=lambda entry: entry.get("timestamp") or "", reverse=True)

    report = UndoReport(batch_id=batch_id)
    for entry in entries:
        report.outcomes[entry["file_id"]] = undo_single_action(entry)

    return report


def build_preview(records: List[FileRecord]) -> str:
    """Render the batch as a preview table: old name -> new name, old location ->
    new destination, category, confidence, tier. `auto` tier rows pre-checked;
    `review_required` rows shown separately, flagged, never pre-filed."""
    raise NotImplementedError


def execute_approved(records: List[FileRecord], approved_file_ids: List[str]) -> None:
    """Move + rename each approved file in one step. Records the pre-move path via
    storage/runtime_io.append_action_log() before the move — that log entry IS the
    undo mechanism. Must update record.current_path (and persist via
    storage/database.save_file_record()) to the new location once the move succeeds —
    current_path is the single authoritative "where is this file now" field
    (see models/file_record.py); original_path stays fixed as the first-discovery
    record. Never deletes anything. Destination folders are created if they don't
    exist yet (safe/idempotent)."""
    raise NotImplementedError


def log_rejected_edit(file_id: str, field_name: str, suggested_value: str,
                       corrected_value: str, category: str) -> None:
    """When the user edits or rejects a suggestion, log it to
    Database/Learning/User Corrections.json via storage/database.log_user_correction()."""
    raise NotImplementedError


# After execute_approved() runs, hand off to pipeline/reporting.py's finalize_batch()
# to write the action log, Database updates, and Daily Summary.
