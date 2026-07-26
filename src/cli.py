"""
Command-line entry point for Downloads Intelligence — C1, "Real CLI Entry
Point" (`Build-out/09 CLI & Product Interface/C1 CLI Entry Point — Design
Package.md`; Engineering Review in the same folder).

Usage: `python -m src.cli <command> [options]` (run from the project root, the
same convention `python -m src.main` already uses).

Composition only, per C1's approved design: every subcommand below is a thin
wrapper around an already-existing, already-tested `src/main.py` function, or a
small, read-only aggregation over already-persisted state
(`load_metadata_store()`/`read_action_log_entries()`) for the two genuinely new
pieces of surface this file adds (`status`, and the `--last` convenience on
`undo`). No pipeline logic — classification, duplicate detection, naming,
confidence scoring, or execution/move decisions — is implemented here; all of
that remains exactly where Modules 01-08 already own it (design package §4.1).

`python -m src.main` is completely unaffected by this file's existence: its own
six-stage automatic chain (`scan` through `score_confidence`) and its
`if __name__ == "__main__":` block are untouched. This file is purely additive
except for one disclosed, zero-behavior-change touch to `src/main.py`:
`_eligible_for_execution_records()` was renamed to `eligible_for_execution_records()`
so `_cmd_execute()`'s interactive approval loop below can reuse it directly
rather than duplicating its four-condition filter a second time — see that
function's own docstring in `src/main.py` for the full rationale (design
package §1.3 item 2, Engineering Review finding F2).

Exit codes (design package §3.5):
    0 - command ran to completion. Matches every wrapped `main.py` function's
        own philosophy exactly: "nothing to do", "batch blocked", "N declined"
        are all normal, expected, printed outcomes today, never raised
        exceptions — this CLI does not invent a stricter definition of success
        than the functions it wraps already have.
    1 - unanticipated internal error (this file's own outermost `try/except` in
        `main()`, mirroring the pipeline's established Layer 1/2/3
        error-handling discipline, `ARCHITECTURE_DECISIONS.md` decisions
        18/19, applied here as the CLI's own additional outermost net). Pass
        `execute --debug` to see the full traceback instead of the short
        message.
    2 - usage error (argparse's own default behavior for bad/missing/
        conflicting arguments — not custom-built).
    3 - the user aborted with Ctrl-C. `_cmd_execute()` catches this locally
        around decision-collection specifically, and only there prints "no
        files have been moved" — that guarantee is provably true only before
        `execute()` (the real, file-moving call) has been invoked (design
        package §3.3 step 4). Every other Ctrl-C point (mid-scan, or mid-
        `execute()` itself after some files may have already moved) falls
        through to `main()`'s own generic handler, which deliberately does
        not repeat that specific claim (Implementation Audit finding,
        self-identified and corrected: an earlier draft used one shared
        message for both cases, which was inaccurate for the second one).

H5, "Configuration Experience" (`Build-out/09 CLI & Product Interface/H5
Configuration Experience — Design Package.md`; Engineering Review in the same
folder), adds `init` and `config --set-source`/`--set-destination` on top of
C1's own foundation — a guided way to set the two settings
`src/config/sources.yaml` has always exposed (source path, `destination_root`,
`Governance/ARCHITECTURE_DECISIONS.md` decision 20) without hand-editing YAML,
plus friendly, specific messages when `scan`/`run` hit an unconfigured or
misconfigured source instead of the generic Layer 3 "Unexpected error"
framing. Severity classified **High** on the existing scale, same tier as C1
and for the same underlying reason — new, user-facing capability, zero
pipeline-logic risk (`Governance/ARCHITECTURE_DECISIONS.md` decision 33,
resolving Engineering Review finding F2). Diagnostic/exit-code classification
applied consistently across every new code path this adds (decision 33, same
finding): an unmet configuration precondition (not configured; configured
path doesn't exist) is an *expected*, not an *error*, state — exit 0, plain
message, no "Error:" framing, matching every other wrapped function's own
"nothing to do" philosophy (exit-code table above); invalid interactive
input during `init` re-prompts, exactly like `_prompt_decision()` already
does, never a default (Engineering Review's own F1-precedent, extended here
to path input); a genuine config-write failure (verification mismatch after
`_write_config_value()` writes, or the file not matching the expected shape
at all) is a real, unanticipated problem, not a user precondition — it
raises and reaches this file's own Layer 3 net (exit 1), exactly like any
other unexpected internal error.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from src.main import (
    classify,
    detect_duplicates,
    eligible_for_execution_records,
    execute as run_execute,
    extract,
    preview as run_preview,
    report as run_report,
    scan as run_scan,
    score_confidence,
    suggest_naming,
    undo as run_undo,
)
from src.models.execution import ApprovalDecision, ApprovalDecisionType
from src.pipeline.execution import preview_batch
from src.providers.registry import (
    registered_classification_providers,
    registered_extraction_providers,
)
from src.storage.database import load_metadata_store, metadata_store_path
from src.storage.runtime_io import action_log_path, read_action_log_entries

# Mirrors src/main.py's own _SOURCES_CONFIG_PATH derivation exactly (both files
# live directly in src/) rather than importing main.py's private constant —
# this is a trivial path expression, not business logic; unlike
# eligible_for_execution_records()'s four-condition filter (design package
# §1.3 item 2), there is no drift risk in two files independently expressing
# "this file's own directory + config/sources.yaml" the same way.
_SOURCES_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "sources.yaml"

# Release/VERSIONS.md lives at the project root; src/cli.py's parent's parent
# is that root.
_VERSIONS_PATH = Path(__file__).resolve().parent.parent / "Release" / "VERSIONS.md"

_HELP_EPILOG = (
    "Note: scan/run classify and extract files without a live AI judgment "
    "provider when run this way (no autonomous provider exists yet — see "
    "TECHNICAL_DEBT_REGISTER.md TD-01). Ambiguous files may be classified as "
    "Unknown rather than correctly identified. This is a known, disclosed "
    "limit, not a bug.\n\n"
    "See 'python -m src.cli <command> --help' for details on any command."
)


def build_parser() -> argparse.ArgumentParser:
    """Constructs the top-level parser and one subparser per command — see the
    design package §3.2 for the full command/argument/option specification
    this mirrors exactly."""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description=(
            "Downloads Intelligence — classify, name, dedupe, and file your "
            "Downloads folder, with a human approval step before anything "
            "moves. Nothing is ever deleted."
        ),
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "scan", help="Identify new files in the configured source (Module 01)."
    )
    subparsers.add_parser(
        "run",
        help=(
            "Run scan through confidence scoring (Modules 01-06). Does not "
            "preview, execute, or move anything."
        ),
    )
    subparsers.add_parser(
        "preview", help="Show what would happen if you executed now. Read-only."
    )

    execute_parser = subparsers.add_parser(
        "execute",
        help=(
            "File approved records. Prompts for each file needing a decision "
            "unless --yes is given."
        ),
        description=(
            "File every eligible record. auto-tier records execute without a "
            "prompt. approval_required records are shown one at a time so you "
            "can approve, edit, or reject each — nothing in that tier "
            "executes without an explicit decision (there is no default; "
            "blank input re-prompts). review_required records are never "
            "touched."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    execute_parser.add_argument(
        "-y", "--yes", action="store_true",
        help=(
            "Don't prompt. Equivalent to running execute() with no decisions "
            "today: auto-tier still executes, approval_required is left "
            "unchanged. Does NOT auto-approve anything."
        ),
    )
    execute_parser.add_argument(
        "--debug", action="store_true",
        help="Show full error tracebacks instead of a short message.",
    )

    undo_parser = subparsers.add_parser(
        "undo", help="Reverse a previous execute batch."
    )
    undo_parser.add_argument(
        "batch_id", nargs="?", default=None, help="The batch to undo."
    )
    undo_parser.add_argument(
        "--last", action="store_true",
        help="Undo the most recent batch found in the action log, instead of naming one.",
    )
    # Stashed so _cmd_undo() can report a usage error (batch_id and --last
    # together, or neither) with this subcommand's own accurate usage string,
    # without build_parser() needing to return more than the top-level parser.
    undo_parser.set_defaults(_undo_parser=undo_parser)

    subparsers.add_parser(
        "report", help="Generate Daily/Weekly Summary and Duplicate/Storage reports."
    )
    subparsers.add_parser(
        "status",
        help=(
            "Show current pipeline state: what's scanned, what's waiting on "
            "you, what's configured."
        ),
    )
    subparsers.add_parser("version", help="Show the current pipeline version.")

    config_parser = subparsers.add_parser(
        "config",
        help=(
            "Show the current source/destination configuration, or change one "
            "value with --set-source/--set-destination."
        ),
        description=(
            "With no options, shows the current source path, destination_root, "
            "and execution_mode from src/config/sources.yaml. --set-source and "
            "--set-destination change exactly one value (validated: the path "
            "must exist and be a directory) and print the resulting "
            "configuration. Hand-editing src/config/sources.yaml directly "
            "remains equally valid — this is a convenience, not a replacement."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    config_parser.add_argument(
        "--set-source", metavar="PATH",
        help="Set the Downloads source path to PATH (must exist, must be a directory).",
    )
    config_parser.add_argument(
        "--set-destination", metavar="PATH",
        help="Set destination_root to PATH (must exist, must be a directory).",
    )

    subparsers.add_parser(
        "init",
        help="Guided first-time setup: configure your Downloads source and destination_root.",
        description=(
            "Interactively prompts for the Downloads source path and "
            "destination_root, validates each (must exist, must be a "
            "directory), and writes them to src/config/sources.yaml. If a "
            "value is already set, shows it and asks for confirmation before "
            "replacing it — never overwrites silently. Run this once before "
            "your first 'scan'/'run', or any time to reconfigure."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    provider_parser = subparsers.add_parser(
        "provider",
        help=(
            "Manage the opt-in autonomous AI classification/extraction "
            "provider (TD-01 v0.9). Off by default."
        ),
        description=(
            "Without an autonomous provider enabled, classify()/extract() "
            "behave exactly as they always have: judgment-dependent files "
            "fall back to Category.UNKNOWN / null fields unless a live, "
            "human-driven Claude session supplies the judgment call. "
            "'provider enable' turns on the Claude API as that provider for "
            "unattended runs — after an explicit disclosure and "
            "confirmation, and only if ANTHROPIC_API_KEY is already set. "
            "See 'Build-out/02 Classification/TD-01 Provider Architecture "
            "— Design Package.md' for the full design."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    provider_subparsers = provider_parser.add_subparsers(dest="provider_action")
    provider_subparsers.add_parser(
        "enable", help="Turn on the Claude API provider (requires confirmation)."
    )
    provider_subparsers.add_parser(
        "disable", help="Turn the opt-in provider back off."
    )
    provider_subparsers.add_parser(
        "status", help="Show current provider configuration. Read-only."
    )

    return parser


# --- Configuration writer (H5 design package §9; Engineering Review F1/F3/F4)
# — targeted, comment-preserving line replacement, not a full YAML round-trip
# (Option C, chosen over ruamel.yaml specifically to avoid a new dependency
# while PRODUCT_READINESS_REVIEW.md finding H1 — a broken/contradictory
# requirements.txt — remains open, NFR-5). ---


def _yaml_safe_scalar(value) -> str:
    """Formats `value` as a YAML scalar safe to substitute directly into a
    `key: <here>` line — quotes/escapes it exactly the way PyYAML's own
    dumper would, so values containing '#', ':', quotes, or leading/trailing
    spaces are all handled correctly (Engineering Review finding F1) without
    adding a new dependency (NFR-5): this reuses the already-imported `yaml`
    module's own representer rather than hand-rolling YAML quoting rules.

    `width=float("inf")` disables PyYAML's default 80-column line wrapping —
    without it, a long value (a realistic case: a deeply nested Downloads or
    cloud-sync path easily exceeds 80 characters) gets silently broken across
    two lines, and this function's own "first line only" extraction below
    would then return a truncated, unterminated quoted scalar — exactly the
    silent-corruption failure mode F1 exists to prevent. Caught by
    `test_write_config_value_handles_yaml_special_characters` using a
    realistic long path, not a short hand-picked example — a short value
    alone would not have exposed this."""
    dumped = yaml.safe_dump(value, default_flow_style=True, width=float("inf"))
    # First line only: safe_dump appends a `...` document-end marker after a
    # plain (unquoted) scalar (to guard against a bare value being misread as
    # a YAML directive by some parsers) — not needed once embedded in a real
    # `key: value` line inside a larger document. With width=inf above, the
    # scalar itself is now guaranteed to be entirely on this one line.
    return dumped.splitlines()[0]


def _find_source_path_line(lines: List[str]) -> int:
    """Locates the `path:` line nested under `- source_id: downloads` in
    `sources.yaml`'s text, precisely (Engineering Review finding F4): finds
    the `- source_id: downloads` line first, then the first subsequent line
    matching `path:` at strictly deeper indentation, stopping (and raising) if
    a line at the source's own indentation or shallower is reached first —
    never guesses past the boundary of that source's own block."""
    source_line_index = None
    source_indent = None
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)-\s*source_id:\s*downloads\s*$", line)
        if match:
            source_line_index = index
            source_indent = len(match.group(1))
            break
    if source_line_index is None:
        raise ValueError(
            "Could not find '- source_id: downloads' in "
            f"{_SOURCES_CONFIG_PATH} — the file may have been edited into an "
            "unexpected shape. Edit it directly instead."
        )

    for index in range(source_line_index + 1, len(lines)):
        line = lines[index]
        match = re.match(r"^(\s+)path:\s*.*$", line)
        if match and len(match.group(1)) > source_indent:
            return index
        if line.strip() and (len(line) - len(line.lstrip())) <= source_indent:
            break  # left the source's own block without finding `path:`

    raise ValueError(
        "Could not find a 'path:' line under the 'downloads' source in "
        f"{_SOURCES_CONFIG_PATH} — the file may have been edited into an "
        "unexpected shape. Edit it directly instead."
    )


def _find_top_level_key_line(lines: List[str], key: str) -> int:
    """Locates a top-level `<key>:` line precisely (F4, generalized for TD-01
    v0.9's three new flat keys — `classification_provider`/
    `extraction_provider`/`ai_provider_consent` — which all live at the same
    document level as `destination_root`): must start at column 0 (no
    leading whitespace) to avoid matching a same-named key nested inside some
    other block."""
    pattern = re.compile(rf"^{re.escape(key)}:\s*.*$")
    for index, line in enumerate(lines):
        if pattern.match(line):
            return index
    raise ValueError(
        f"Could not find a '{key}:' line in {_SOURCES_CONFIG_PATH} — the "
        "file may have been edited into an unexpected shape. Edit it "
        "directly instead."
    )


def _find_destination_root_line(lines: List[str]) -> int:
    """Locates the top-level `destination_root:` line — thin wrapper over
    `_find_top_level_key_line()` (F4), kept as its own named function since
    every existing call site already names it explicitly."""
    return _find_top_level_key_line(lines, "destination_root")


_TOP_LEVEL_CONFIG_TARGETS = (
    "destination_root", "classification_provider", "extraction_provider",
    "ai_provider_consent",
)


def _write_config_value(target: str, new_value) -> None:
    """Writes `new_value` into exactly one of this project's config settings
    (`target` is `"source_path"`, `"destination_root"`, or — added for TD-01
    v0.9, `Build-out/02 Classification/TD-01 Provider Architecture — Design
    Package.md` §5 — one of `_TOP_LEVEL_CONFIG_TARGETS`'s three provider
    keys) by replacing only that one line, byte-for-byte preserving every
    other line — comments, blank lines, every other key (H5 design package
    §9). `new_value` is a `str` for every path/provider-name target, or a
    real Python `bool` for `ai_provider_consent` specifically (never the
    string `"true"`/`"false"` — see `_yaml_safe_scalar()`'s own handling:
    passing a `bool` through `yaml.safe_dump()` produces the unquoted YAML
    boolean `true`/`false`; passing the string `"true"` would instead
    produce a quoted YAML string, which re-parses back as `str`, not `bool`
    — silently wrong for a value every caller treats as a boolean).

    Safety (Engineering Review finding F1 — "silent corruption... is
    unacceptable"): `new_value` is always written through
    `_yaml_safe_scalar()` (never raw string interpolation), and the write is
    verified immediately afterward by re-parsing the file and confirming the
    target key now equals exactly `new_value`. If anything goes wrong — the
    expected line isn't found, the write fails, or verification doesn't match
    — the file is restored to its exact original content before this raises,
    so a failed write is never left half-applied.
    """
    if target != "source_path" and target not in _TOP_LEVEL_CONFIG_TARGETS:
        raise ValueError(f"Unknown config target: {target!r}")

    original_text = _SOURCES_CONFIG_PATH.read_text(encoding="utf-8")
    had_trailing_newline = original_text.endswith("\n")
    lines = original_text.splitlines()

    if target == "source_path":
        line_index = _find_source_path_line(lines)
        indent = re.match(r"^(\s+)path:", lines[line_index]).group(1)
        # The existing inline comment ("filled in at runtime from the user's
        # actual Downloads folder path") describes the *unset* state — once a
        # real value is written it is no longer accurate, so it is
        # deliberately dropped here rather than preserved verbatim. This is
        # the one disclosed exception to "preserve every comment unchanged":
        # every top-level target below carries no inline comment to begin
        # with (its documentation lives entirely in the block comment above
        # it, which this function never touches), so no equivalent decision
        # is needed there.
        lines[line_index] = f"{indent}path: {_yaml_safe_scalar(new_value)}"
    else:
        line_index = _find_top_level_key_line(lines, target)
        lines[line_index] = f"{target}: {_yaml_safe_scalar(new_value)}"

    new_text = "\n".join(lines) + ("\n" if had_trailing_newline else "")

    try:
        _SOURCES_CONFIG_PATH.write_text(new_text, encoding="utf-8")
        with open(_SOURCES_CONFIG_PATH, "r", encoding="utf-8") as config_file:
            reloaded = yaml.safe_load(config_file) or {}
        if target == "source_path":
            actual = ((reloaded.get("sources") or [{}])[0] or {}).get("path")
        else:
            actual = reloaded.get(target)
        if actual != new_value:
            raise ValueError(
                f"write verification failed: expected {target}={new_value!r}, "
                f"found {actual!r} after writing"
            )
    except Exception as exc:
        try:
            _SOURCES_CONFIG_PATH.write_text(original_text, encoding="utf-8")
            restored_note = "The file has been restored to its previous state."
        except Exception:
            restored_note = (
                "Attempting to restore the file's previous state also "
                "failed — check src/config/sources.yaml directly before "
                "doing anything else."
            )
        raise ValueError(
            f"Could not safely write {target} to src/config/sources.yaml "
            f"({exc}). {restored_note} No change was intentionally left in "
            "place. Edit src/config/sources.yaml directly if this keeps "
            "happening."
        ) from exc


def _resolve_existing_directory(raw: str) -> Optional[Path]:
    """Resolves `raw` to an absolute path and returns it only if it exists
    and is a directory; returns `None` on any invalid input, never raises.
    Callers always write the *resolved, absolute* path, never the raw typed
    string (Engineering Review finding F3) — `src/main.py`'s own
    `_load_destination_root()` does not itself resolve relative paths, so an
    unresolved value's meaning would depend on the working directory the
    pipeline happens to be invoked from at run time, not fixed at
    configuration time."""
    resolved = Path(raw).expanduser().resolve()
    return resolved if resolved.is_dir() else None


def _prompt_path(label: str) -> Path:
    """Prompts for a directory path, validating it exists before accepting
    (FR-2) — invalid or empty input re-prompts, no default, exactly the same
    no-implicit-default discipline `_prompt_decision()` already established
    (Engineering Review's F1 precedent from C1, extended here to path
    input)."""
    while True:
        raw = input(f"{label}: ").strip()
        if not raw:
            print("Please enter a path.")
            continue
        resolved = _resolve_existing_directory(raw)
        if resolved is None:
            print(f"'{raw}' does not exist or is not a directory. Try again.")
            continue
        return resolved


def _confirm(prompt: str) -> bool:
    """y/n confirmation with no default (FR-4/NFR-3) — blank or unrecognized
    input re-prompts rather than assuming either answer."""
    while True:
        raw = input(f"{prompt} [y/n]: ").strip().lower()
        if raw == "y":
            return True
        if raw == "n":
            return False
        print("Please enter y or n.")


def _init_one_setting(label: str, target: str, current_value: Optional[str]) -> None:
    """Shared by _cmd_init for both settings it configures (source path,
    destination_root) — avoids two near-identical copies of the same
    prompt/confirm/write sequence (the same duplicated-logic risk this
    project's PT-002/PT-003 postmortems, and C1's own Alternative D, already
    warn against)."""
    if current_value:
        print(f"Current {label}: {current_value}")
        if not _confirm("Replace it?"):
            print(f"Keeping existing {label}.")
            return
    new_path = _prompt_path(f"{label}")
    _write_config_value(target, str(new_path))
    print(f"{label} set to {new_path}.")


def _cmd_init(args: argparse.Namespace) -> int:
    if not _SOURCES_CONFIG_PATH.exists():
        print(f"Could not find {_SOURCES_CONFIG_PATH}")
        return 0

    with open(_SOURCES_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}
    sources = config.get("sources") or [{}]
    current_source_path = sources[0].get("path")
    current_destination_root = config.get("destination_root")

    print("Downloads Intelligence setup\n")
    _init_one_setting("Downloads source path", "source_path", current_source_path)
    print()
    _init_one_setting("destination_root", "destination_root", current_destination_root)

    print(
        "\nSetup complete. Run 'python -m src.cli config' to review, or "
        "'python -m src.cli scan' to get started."
    )
    return 0


# --- provider (TD-01 v0.9) — opt-in autonomous AI provider management.
# "Build-out/02 Classification/TD-01 Provider Architecture — Design
# Package.md" §4/§5/§7. Only one registered provider exists in v0.9
# ("claude") — this is deliberately not a --provider flag exposing a choice
# that doesn't exist yet (§7's Acceptance Criteria #4: the registry supports
# more than one entry without this file needing to change when a second one
# is added later; the CLI surface for *choosing among several* is a v1.0-era
# concern, not a v0.9 one). ---

_PROVIDER_KEY = "claude"

_PROVIDER_DISCLOSURE_TEXT = (
    "\nEnabling the Claude API provider means: every file that today would "
    "fall back to Category.UNKNOWN (or a null metadata field) because no "
    "live Claude session is present will instead have its extracted text, "
    "or the file itself for image/vision cases, sent to Anthropic's API for "
    "an autonomous judgment call. This is a real, metered API cost — not "
    "free, though typically small for an occasional personal-Downloads-"
    "folder run. Nothing about scanning, execution, moving, or deletion "
    "changes: this only affects the classification/extraction judgment "
    "step. The API key itself is read from the ANTHROPIC_API_KEY "
    "environment variable and is never written to src/config/sources.yaml "
    "or anywhere else in this project.\n"
)


def _cmd_provider(args: argparse.Namespace) -> int:
    action = getattr(args, "provider_action", None)
    if action == "enable":
        return _provider_enable()
    if action == "disable":
        return _provider_disable()
    if action in (None, "status"):
        return _provider_status()
    print("Usage: python -m src.cli provider {enable,disable,status}")
    return 2


def _provider_enable() -> int:
    classification_providers = registered_classification_providers()
    extraction_providers = registered_extraction_providers()
    if _PROVIDER_KEY not in classification_providers or _PROVIDER_KEY not in extraction_providers:
        print(
            f"'{_PROVIDER_KEY}' is not a registered provider in this build "
            f"(registered classification providers: {classification_providers!r}, "
            f"extraction providers: {extraction_providers!r}). Nothing was changed."
        )
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set in this environment. The Claude "
            "API provider requires it before it can be enabled — set it "
            "(e.g. `export ANTHROPIC_API_KEY=...`) and run "
            "'python -m src.cli provider enable' again. Nothing was changed."
        )
        return 0

    print(_PROVIDER_DISCLOSURE_TEXT)
    if not _confirm("Enable the Claude API provider?"):
        print("Not enabled. Nothing was changed.")
        return 0

    _write_config_value("classification_provider", _PROVIDER_KEY)
    _write_config_value("extraction_provider", _PROVIDER_KEY)
    _write_config_value("ai_provider_consent", True)
    print(
        f"Claude API provider enabled for classification and extraction. "
        "Run 'python -m src.cli provider status' any time to review, or "
        "'provider disable' to turn it back off."
    )
    return 0


def _provider_disable() -> int:
    _write_config_value("ai_provider_consent", False)
    print(
        "Provider opt-in disabled. classify()/extract() will use today's "
        "existing behavior again (Category.UNKNOWN / null fields for "
        "judgment-dependent files outside a live Claude session) — the "
        "classification_provider/extraction_provider values are left as-is "
        "but have no effect while ai_provider_consent is false."
    )
    return 0


def _provider_status() -> int:
    if not _SOURCES_CONFIG_PATH.exists():
        print(f"Could not find {_SOURCES_CONFIG_PATH}")
        return 0

    with open(_SOURCES_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}

    consent = bool(config.get("ai_provider_consent", False))
    classification_provider = config.get("classification_provider")
    extraction_provider = config.get("extraction_provider")
    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))

    print("Provider configuration (src/config/sources.yaml):\n")
    print(f"  Opt-in enabled:           {consent}")
    print(f"  classification_provider:  {classification_provider or 'not set'}")
    print(f"  extraction_provider:      {extraction_provider or 'not set'}")
    print(f"  ANTHROPIC_API_KEY set:    {'yes' if api_key_set else 'no'}")
    if consent and (not classification_provider or not extraction_provider):
        print(
            "\n  Note: opt-in is enabled but one or both provider keys are "
            "unset — this behaves the same as opt-in being off for "
            "whichever one is unset (main.py resolves a provider only when "
            "both consent and a key are present)."
        )
    if consent and not api_key_set:
        print(
            "\n  Note: opt-in is enabled but ANTHROPIC_API_KEY is not set in "
            "this environment right now — the next classify()/extract() "
            "call using this provider will fail clearly rather than "
            "silently falling back."
        )

    print(f"\n  Registered classification providers: {registered_classification_providers()}")
    print(f"  Registered extraction providers:     {registered_extraction_providers()}")
    return 0


# --- Thin-wrapper commands (design package §4.1) — each a direct call to an
# already-existing, already-tested src/main.py function. ---


def _run_scan_with_friendly_config_errors() -> Optional[int]:
    """Wraps the call to `run_scan()` (`main.scan()`) that both `_cmd_scan`
    and `_cmd_run` begin with, catching only the two specific, fully
    enumerated exception types a configuration problem raises on this path
    (H5 design package §9, verified directly against `load_source_config()`/
    `scan_source()`): `ValueError` — not configured at all (no path set,
    source missing/disabled, or execution_mode isn't manual) — and
    `NotADirectoryError` — configured, but the path doesn't exist. Each gets
    a distinct, actionable message (FR-6) rather than the generic Layer 3
    "Unexpected error" framing (this was C1-PAT-1, found during C1's Product
    Acceptance Test). Deliberately narrow — wraps only this one call, not a
    broad `except Exception` — so a genuinely unrelated future exception is
    never misclassified as "not configured" (Engineering Review finding R2's
    own mitigation: `load_source_config()`'s four raise conditions are fully
    enumerated and confirmed to be the only source of `ValueError` on this
    path as of this writing; a future contributor adding a fifth
    `ValueError`-raising branch there should know this function depends on
    that assumption).

    Both cases are an *expected*, not an *error*, outcome — exit 0 (decision
    33, F2's diagnostic-classification requirement), matching every other
    wrapped function's own "nothing to do yet" philosophy. As with C1's own
    `execute -y` exit-0 choice (design package §3.5's disclosed open
    question, carried forward per Engineering Review finding F6): this may
    be unsatisfying for a future scripted/scheduled caller wanting a
    non-zero "nothing happened" signal — not resolved here, same open
    question, not newly settled by this addition.

    Returns `None` if `run_scan()` completed normally (caller should
    proceed); returns an exit code if a configuration problem was caught and
    a message already printed.
    """
    try:
        run_scan()
        return None
    except ValueError as exc:
        print(str(exc))
        print(
            "Run 'python -m src.cli init' to configure a Downloads source, "
            "or edit src/config/sources.yaml directly."
        )
        return 0
    except NotADirectoryError as exc:
        print(str(exc))
        print(
            "Run 'python -m src.cli init' or "
            "'python -m src.cli config --set-source <path>' to fix your "
            "configured source path, or edit src/config/sources.yaml directly."
        )
        return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    code = _run_scan_with_friendly_config_errors()
    return 0 if code is None else code


def _cmd_run(args: argparse.Namespace) -> int:
    """Reproduces python -m src.main's own six-stage automatic chain exactly
    — same stages, same order, same stopping point (FR-2). Does not call
    preview()/execute() — the human-approval gate stays a separate, explicit
    step, never folded into "run the pipeline"."""
    code = _run_scan_with_friendly_config_errors()
    if code is not None:
        return code
    classify()
    extract()
    detect_duplicates()
    suggest_naming()
    score_confidence()
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    run_preview()
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    run_report()
    return 0


# --- execute — the interactive approval flow (design package §3.3; Engineering
# Review finding F1 applied: no default on blank input, every approval_required
# record requires an explicit a/e/r/s keystroke). ---


def _prompt_decision(row, index: int, total: int) -> Tuple[Optional[ApprovalDecision], bool]:
    """Prompts for exactly one approval_required PreviewRow. Returns
    (decision, stop) — `stop=True` (only reachable via 's') means the caller
    should stop prompting for any remaining row in this batch; `decision` is
    `None` only when `stop=True`. There is no blank-input default (F1): an
    empty or unrecognized response re-prompts the same row, matching every
    other genuinely invalid-input path exactly (design package §3.3 step 4,
    as amended by the Engineering Review)."""
    note = f" [{row.override}]" if row.override else ""
    print(f"\n[{index} of {total}] {row.file_id}  {row.original_name}")
    print(
        f"          -> {row.suggested_destination}{row.suggested_name}"
        f"   (confidence {row.confidence_score}, {row.tier}){note}"
    )

    while True:
        raw = input("Approve as suggested / Edit / Reject / Skip remaining?  [a/e/r/s]: ").strip().lower()
        if raw == "a":
            return ApprovalDecision(
                file_id=row.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED
            ), False
        if raw == "e":
            new_name = input(f"New name [{row.suggested_name}]: ").strip() or row.suggested_name
            new_destination = (
                input(f"New destination [{row.suggested_destination}]: ").strip()
                or row.suggested_destination
            )
            return ApprovalDecision(
                file_id=row.file_id,
                decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
                edited_name=new_name,
                edited_destination=new_destination,
            ), False
        if raw == "r":
            return ApprovalDecision(
                file_id=row.file_id, decision=ApprovalDecisionType.REJECT
            ), False
        if raw == "s":
            return None, True
        print("Please enter a, e, r, or s.")


def _collect_decisions_interactively(rows_by_tier: Dict[str, list]) -> Dict[str, ApprovalDecision]:
    """Builds the ApprovalDecision dict execute() needs, by prompting only for
    approval_required rows (design package §3.3 step 2) — auto rows need no
    decision (EXECUTE_AS_AUTO requires none) and review_required rows are never
    eligible for one at all (I2, unconditional). Zero approval_required rows
    is a valid, expected case (Engineering Review finding F6): the loop below
    then does nothing and this returns {} immediately, after printing the
    up-front auto/review_required counts."""
    auto_rows = rows_by_tier.get("auto", [])
    review_rows = rows_by_tier.get("review_required", [])
    approval_rows = rows_by_tier.get("approval_required", [])

    if auto_rows:
        print(f"{len(auto_rows)} file(s) will execute automatically (auto tier) — no action needed.")
    if review_rows:
        print(
            f"{len(review_rows)} file(s) need attention and will NOT be filed "
            "(review_required) — run 'preview' for details."
        )

    decisions: Dict[str, ApprovalDecision] = {}
    if not approval_rows:
        return decisions

    total = len(approval_rows)
    print(f"\n{total} file(s) need your decision:")
    for index, row in enumerate(approval_rows, start=1):
        decision, stop = _prompt_decision(row, index, total)
        if stop:
            remaining = total - index + 1
            print(f"\nStopped — {remaining} file(s) left with no decision this run (left unchanged).")
            break
        decisions[row.file_id] = decision

    return decisions


def _cmd_execute(args: argparse.Namespace) -> int:
    if args.yes:
        # Equivalent to today's existing default (decisions={}): auto-tier
        # still executes, approval_required is left unchanged. Does NOT
        # auto-approve anything (design package §3.2, Engineering Review's
        # accepted-as-is F1 discussion of -y's asymmetric, safe-by-default
        # meaning).
        run_execute(decisions={})
        return 0

    records = eligible_for_execution_records()
    if not records:
        # Reuses execute()'s own "Nothing to execute..." message rather than
        # duplicating that text here — avoids the two-copies drift risk this
        # project's own PT-002/PT-003 postmortems flagged.
        run_execute(decisions={})
        return 0

    rows = preview_batch(records)
    rows_by_tier: Dict[str, list] = {"auto": [], "approval_required": [], "review_required": []}
    for row in rows:
        rows_by_tier.setdefault(row.tier, []).append(row)

    # Caught locally, specifically around decision-collection only — this is
    # the one interrupt point this design actually guarantees is a clean
    # no-op (design package §3.3 step 4: nothing has been read into
    # run_execute() yet, so "no files have been moved" is provably true
    # here). A KeyboardInterrupt raised anywhere inside run_execute() itself
    # below (e.g. mid-batch, after some auto-tier files already moved) is
    # deliberately NOT caught by this same message — it propagates to
    # main()'s own generic handler instead, which does not repeat this
    # specific claim (Implementation Audit finding, self-identified and
    # corrected before this file was considered complete: the original draft
    # printed the same "no files have been moved" text from one shared
    # top-level handler regardless of which of these two points the
    # interrupt actually happened at, which is only true for this one).
    try:
        decisions = _collect_decisions_interactively(rows_by_tier)
    except KeyboardInterrupt:
        print("\nAborted — no files have been moved.")
        return 3

    run_execute(decisions=decisions)
    return 0


# --- undo ---


def _most_recent_batch_id_from_entries(entries: List[dict]) -> Optional[str]:
    if not entries:
        return None
    latest = max(entries, key=lambda entry: entry.get("timestamp") or "")
    return latest.get("batch_id")


def _most_recent_batch_id() -> Optional[str]:
    return _most_recent_batch_id_from_entries(read_action_log_entries())


def _cmd_undo(args: argparse.Namespace) -> int:
    if args.last and args.batch_id:
        args._undo_parser.error("argument batch_id: not allowed with argument --last")
    if not args.last and not args.batch_id:
        args._undo_parser.error("one of the arguments batch_id --last is required")

    if args.last:
        batch_id = _most_recent_batch_id()
        if batch_id is None:
            print("No batches found in the action log — nothing to undo.")
            return 0
        print(f"Resolved --last to batch {batch_id}.")
    else:
        batch_id = args.batch_id

    run_undo(batch_id)
    return 0


# --- status (new, read-only, composition-only — design package §3.4) ---


def _cmd_status(args: argparse.Namespace) -> int:
    records = load_metadata_store()
    entries = read_action_log_entries()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"Pipeline status (as of {now})")

    status_counts: Dict[str, int] = {}
    for record in records:
        status_counts[record.status] = status_counts.get(record.status, 0) + 1

    print("\nRecords by status:")
    if not records:
        print("  (no records — metadata store is empty; nothing has been scanned yet)")
    else:
        for status_value, count in sorted(status_counts.items()):
            print(f"  {status_value}: {count}")

    eligible = eligible_for_execution_records()
    awaiting = sum(1 for record in eligible if record.tier == "approval_required")
    print(f"\nAwaiting your decision: {awaiting}")

    most_recent = _most_recent_batch_id_from_entries(entries)
    print(f"Most recent batch: {most_recent or '(none)'}")

    print("\nConfiguration:")
    if _SOURCES_CONFIG_PATH.exists():
        with open(_SOURCES_CONFIG_PATH, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file) or {}
        sources = config.get("sources") or [{}]
        source_path = sources[0].get("path")
        destination_root = config.get("destination_root")
        execution_mode = config.get("execution_mode", "manual")

        print(f"  Source path:      {source_path or 'not set (filled in at runtime)'}")
        if destination_root:
            print(f"  destination_root: {destination_root}")
        else:
            print(
                "  destination_root: not set — execute will block every "
                "eligible record until this is configured"
            )
        print(f"  Execution mode:   {execution_mode}")
    else:
        print(f"  (could not find {_SOURCES_CONFIG_PATH})")

    print(f"\nMetadata store: {metadata_store_path()}")
    print(f"Action log:      {action_log_path()}")
    return 0


# --- version, config (optional commands, justified in design package §3.1) ---


def _cmd_version(args: argparse.Namespace) -> int:
    if not _VERSIONS_PATH.exists():
        print("version unknown — could not find Release/VERSIONS.md")
        return 0

    version = None
    for line in _VERSIONS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("**Pipeline Version:"):
            version = stripped.split(":", 1)[1].strip().rstrip("*").strip()
            break

    if version is None:
        print("version unknown — could not read the Pipeline Version line from Release/VERSIONS.md")
        return 0

    print(f"Downloads Intelligence — Pipeline Version {version}")
    print(
        "(Read live from Release/VERSIONS.md — the module/pipeline version "
        "ledger, not a separately-versioned CLI.)"
    )
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    if not _SOURCES_CONFIG_PATH.exists():
        print(f"Could not find {_SOURCES_CONFIG_PATH}")
        return 0

    # --set-source/--set-destination (H5 FR-5): each validated and written
    # via the same _write_config_value()/_resolve_existing_directory() path
    # _cmd_init uses — one writer, two entry points, avoiding the duplicated-
    # validation-logic risk C1's own Alternative D already rejected for a
    # different pair of call sites. Non-interactive (a single attempt, not a
    # re-prompt loop) — this is a scripted-argument context, not a live
    # conversation.
    set_source = getattr(args, "set_source", None)
    set_destination = getattr(args, "set_destination", None)

    if set_source:
        resolved = _resolve_existing_directory(set_source)
        if resolved is None:
            print(f"'{set_source}' does not exist or is not a directory. Nothing was changed.")
            return 0
        _write_config_value("source_path", str(resolved))
        print(f"Downloads source path set to {resolved}.\n")

    if set_destination:
        resolved = _resolve_existing_directory(set_destination)
        if resolved is None:
            print(f"'{set_destination}' does not exist or is not a directory. Nothing was changed.")
            return 0
        _write_config_value("destination_root", str(resolved))
        print(f"destination_root set to {resolved}.\n")

    with open(_SOURCES_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}

    sources = config.get("sources") or []
    source = sources[0] if sources else {}

    print("Current configuration (src/config/sources.yaml):\n")
    print(f"  source_id:        {source.get('source_id', '(none)')}")
    print(f"  path:             {source.get('path') or 'not set (filled in at runtime)'}")
    print(f"  type:             {source.get('type', '(none)')}")
    print(f"  enabled:          {source.get('enabled', '(none)')}")
    print(f"  recursive:        {source.get('recursive', '(none)')}")
    print(f"\n  execution_mode:   {config.get('execution_mode', 'manual')}")

    destination_root = config.get("destination_root")
    if destination_root:
        print(f"  destination_root: {destination_root}")
    else:
        print(
            "  destination_root: not set — execute will block every "
            "eligible record until this is configured"
        )

    print(
        "\nUse --set-source <path> / --set-destination <path> to change a "
        "value, or 'python -m src.cli init' for guided setup. Hand-editing "
        "src/config/sources.yaml directly remains equally valid."
    )
    return 0


_COMMANDS = {
    "scan": _cmd_scan,
    "run": _cmd_run,
    "preview": _cmd_preview,
    "execute": _cmd_execute,
    "undo": _cmd_undo,
    "report": _cmd_report,
    "status": _cmd_status,
    "version": _cmd_version,
    "config": _cmd_config,
    "init": _cmd_init,
    "provider": _cmd_provider,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    handler = _COMMANDS[args.command]
    debug = getattr(args, "debug", False)

    try:
        return handler(args)
    except KeyboardInterrupt:
        # _cmd_execute() catches its own KeyboardInterrupt locally, with a
        # stronger, specific message, for the one interrupt point this
        # design actually guarantees is a clean no-op (decision-collection,
        # before run_execute() is ever called — design package §3.3 step 4).
        # This generic handler is what fires for every other interrupt point
        # (mid-scan, mid-execute after some files have already moved, etc.)
        # — deliberately does NOT claim "no files have been moved" here,
        # since that would not always be true (Implementation Audit finding,
        # self-identified and corrected).
        print("\nAborted. Run 'status' to check the current state.")
        return 3
    except Exception as exc:  # Layer 3 — this file's own outermost safety net
        if debug:
            raise
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
