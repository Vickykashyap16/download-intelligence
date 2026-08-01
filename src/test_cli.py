"""
Unit tests for src/cli.py — C1, "Real CLI Entry Point"
(`Build-out/09 CLI & Product Interface/C1 CLI Entry Point — Design Package.md`
§4.6 T1-T9; Engineering Review findings F1/F6 verified explicitly below).

Isolation convention mirrors src/test_main.py exactly (same helper names,
same monkeypatch targets) — this file exercises a new layer on top of
main.py's already-tested functions, not a reason to invent a new isolation
style. Every test that could touch real Database/Runtime state is isolated
via tmp_path, matching this project's own hard-learned lesson (the Module 07
UAT test-isolation defect) about never trusting a test that runs against the
real installation's files.

Run with: pytest src/test_cli.py -v
"""

import json

import pytest
import yaml

import src.cli as cli_module
import src.main as main_module
import src.pipeline.watch_ingest as watch_ingest_module
import src.storage.database as database_module
import src.storage.runtime_io as runtime_io_module
from src.models.classification import Category
from src.models.execution import ApprovalDecisionType, PreviewRow
from src.models.file_record import FileRecord


def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "_METADATA_STORE_PATH", tmp_path / "metadata_store.json")
    monkeypatch.setattr(runtime_io_module, "_ACTION_LOG_PATH", tmp_path / "action_log.jsonl")


def _isolate_execution_storage(tmp_path, monkeypatch):
    """Mirrors src/test_main.py's own _isolate_execution_storage() exactly —
    the additional real-storage locations execute()/undo() touch beyond
    metadata/the action log."""
    _isolate_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime_io_module, "_RUNTIME_TEMP_PATH", tmp_path / "Temp")
    monkeypatch.setattr(database_module, "_USER_CORRECTIONS_PATH", tmp_path / "User Corrections.json")


def _write_sources_config(tmp_path, monkeypatch, destination_root=None, source_path=None):
    """Mirrors src/test_main.py's own _write_sources_config() — points both
    main_module._SOURCES_CONFIG_PATH (used by main.py's execute()) and
    cli_module._SOURCES_CONFIG_PATH (used by cli.py's status/config commands)
    at the same sandboxed file, since cli.py deliberately re-derives this path
    itself rather than importing main.py's private constant (design package
    §1.3 item 2's "trivial constant, no drift risk" reasoning)."""
    config_path = tmp_path / "sources.yaml"
    config = {
        "sources": [
            {"source_id": "downloads", "path": source_path, "type": "local_folder",
             "enabled": True, "recursive": False},
        ],
        "execution_mode": "manual",
        "destination_root": str(destination_root) if destination_root is not None else None,
    }
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(main_module, "_SOURCES_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli_module, "_SOURCES_CONFIG_PATH", config_path)


def _write_realistic_sources_config(tmp_path, monkeypatch, source_path=None, destination_root=None):
    """Writes a byte-for-byte realistic sources.yaml — matching the real
    project file's actual structure and comments exactly — unlike
    _write_sources_config() above (a full yaml.safe_dump() round-trip that
    has no comments at all). The H5 config-writer tests need real comments
    present to prove _write_config_value() actually preserves them
    (Engineering Review finding F4's precise-matching requirement)."""
    config_path = tmp_path / "sources.yaml"
    path_value = "null" if source_path is None else str(source_path)
    destination_value = "null" if destination_root is None else str(destination_root)
    text = (
        '# Source config — see Build-out/01 Watch & Ingest/01 Watch & Ingest.md for the "Source" concept.\n'
        '# v1 has exactly one entry. Adding a source later (Desktop, Google Drive, OneDrive, Dropbox — see\n'
        '# ROADMAP.md Version 3) means adding another entry here, not redesigning the pipeline.\n'
        '\n'
        'sources:\n'
        '  - source_id: downloads\n'
        f"    path: {path_value}   # filled in at runtime from the user's actual Downloads folder path\n"
        '    type: local_folder\n'
        '    enabled: true\n'
        '    recursive: false   # v1 only scans the top level — see Rules/Ignore Rules.md "Source scope"\n'
        '\n'
        'execution_mode: manual   # manual | scheduled | watch_folder — see README.md "Execution modes"\n'
        '\n'
        "# Module 07 (Preview, Approval & Execution)'s destination library root — Open\n"
        '# Decision OD-1, resolved as Governance/ARCHITECTURE_DECISIONS.md decision 20.\n'
        "# Sibling to `sources:`, null until the user configures it (the design's own\n"
        "# proposed shape, Module 07 Design.md §11/§26). Read by src/main.py's execute()\n"
        '# (WP-12) before any file is moved.\n'
        f'destination_root: {destination_value}\n'
    )
    config_path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(main_module, "_SOURCES_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli_module, "_SOURCES_CONFIG_PATH", config_path)
    # src/pipeline/watch_ingest.py's load_source_config() derives its own,
    # third, independent copy of this same constant (a pre-existing
    # duplication this work package found, not introduced by it — see the
    # H5 Implementation Report). Only the tests below that exercise a real,
    # unmocked scan()/load_source_config() call need this patched too; the
    # ones that only patch run_scan()/run_scan-that-succeeds never reach it.
    monkeypatch.setattr(watch_ingest_module, "_SOURCES_CONFIG_PATH", config_path)
    return config_path


def _make_execution_record(
    tmp_path, file_id, name="Amazon_2026-07-05.pdf", tier="approval_required",
    batch_id="batch-1", discovered_at="2026-01-01T00:00:00Z",
    suggested_destination="Finance/", category=Category.INVOICE,
    confidence_score=88, processed_at=None,
):
    """Mirrors src/test_main.py's own _make_execution_record() — a real file
    on disk, since execute() ultimately reaches a real Path.rename() move."""
    source = tmp_path / f"{file_id}_{name}"
    source.write_text(f"content-{file_id}")
    record = FileRecord(
        file_id=file_id, source_id="downloads", original_name=name,
        original_path=str(source), current_path=str(source),
        status="discovered", category=category,
        discovered_at=discovered_at, batch_id=batch_id,
        tier=tier, confidence_score=confidence_score,
        suggested_name=name, suggested_destination=suggested_destination,
        processed_at=processed_at,
    )
    database_module.save_file_record(record)
    return record


def _scripted_input(responses):
    """Returns a callable usable as builtins.input's replacement, yielding
    each of `responses` in order and raising a clear AssertionError (not a
    confusing StopIteration) if asked for more input than scripted."""
    iterator = iter(responses)

    def _input(prompt=""):
        try:
            return next(iterator)
        except StopIteration:
            raise AssertionError(f"input() called more times than scripted (last prompt: {prompt!r})")

    return _input


def _preview_row(file_id, tier="approval_required", name="invoice.pdf",
                  destination="Finance/", suggested_name=None, confidence=87, override=None):
    return PreviewRow(
        file_id=file_id,
        original_name=name,
        suggested_name=suggested_name or name,
        current_path=f"/tmp/{name}",
        suggested_destination=destination,
        category=Category.INVOICE,
        confidence_score=confidence,
        tier=tier,
        override=override,
    )


# --- T1: build_parser() accepts every documented combination, rejects
# genuinely invalid ones at the parser level. ---


def test_parser_accepts_every_documented_command():
    parser = cli_module.build_parser()
    for command in ("scan", "run", "preview", "report", "status", "version", "config", "init"):
        args = parser.parse_args([command])
        assert args.command == command


def test_parser_config_set_options():
    parser = cli_module.build_parser()
    args = parser.parse_args(["config", "--set-source", "/tmp/a", "--set-destination", "/tmp/b"])
    assert args.set_source == "/tmp/a"
    assert args.set_destination == "/tmp/b"

    args = parser.parse_args(["config"])
    assert args.set_source is None
    assert args.set_destination is None


def test_parser_execute_options():
    parser = cli_module.build_parser()
    args = parser.parse_args(["execute", "-y", "--debug"])
    assert args.yes is True
    assert args.debug is True

    args = parser.parse_args(["execute"])
    assert args.yes is False
    assert args.debug is False


def test_parser_undo_accepts_batch_id_and_last_separately():
    parser = cli_module.build_parser()
    args = parser.parse_args(["undo", "batch-42"])
    assert args.batch_id == "batch-42"
    assert args.last is False

    args = parser.parse_args(["undo", "--last"])
    assert args.batch_id is None
    assert args.last is True


def test_parser_no_command_prints_help_and_returns_zero(capsys):
    exit_code = cli_module.main([])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "usage: python -m src.cli" in captured.out


def test_parser_rejects_unknown_command():
    with pytest.raises(SystemExit) as exc_info:
        cli_module.main(["bogus-command"])
    assert exc_info.value.code == 2


# --- T2: thin-wrapper commands call exactly the expected main.py function(s). ---


def test_cmd_scan_calls_main_scan(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_module, "run_scan", lambda: calls.append("scan"))
    exit_code = cli_module.main(["scan"])
    assert exit_code == 0
    assert calls == ["scan"]


def test_cmd_run_calls_all_six_stages_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_module, "run_scan", lambda: calls.append("scan"))
    monkeypatch.setattr(cli_module, "classify", lambda: calls.append("classify"))
    monkeypatch.setattr(cli_module, "extract", lambda: calls.append("extract"))
    monkeypatch.setattr(cli_module, "detect_duplicates", lambda: calls.append("detect_duplicates"))
    monkeypatch.setattr(cli_module, "suggest_naming", lambda: calls.append("suggest_naming"))
    monkeypatch.setattr(cli_module, "score_confidence", lambda: calls.append("score_confidence"))
    monkeypatch.setattr(cli_module, "run_preview", lambda: calls.append("preview"))
    monkeypatch.setattr(cli_module, "run_execute", lambda decisions=None: calls.append("execute"))

    exit_code = cli_module.main(["run"])

    assert exit_code == 0
    assert calls == ["scan", "classify", "extract", "detect_duplicates", "suggest_naming", "score_confidence"]


def test_cmd_preview_calls_main_preview(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_module, "run_preview", lambda: calls.append("preview"))
    exit_code = cli_module.main(["preview"])
    assert exit_code == 0
    assert calls == ["preview"]


def test_cmd_report_calls_main_report(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_module, "run_report", lambda: calls.append("report"))
    exit_code = cli_module.main(["report"])
    assert exit_code == 0
    assert calls == ["report"]


# --- T3: the interactive approval loop, at the unit level
# (_prompt_decision / _collect_decisions_interactively). ---


def test_prompt_decision_approve_as_suggested(monkeypatch):
    row = _preview_row("f1")
    monkeypatch.setattr("builtins.input", _scripted_input(["a"]))
    decision, stop = cli_module._prompt_decision(row, 1, 1)
    assert stop is False
    assert decision.file_id == "f1"
    assert decision.decision == ApprovalDecisionType.APPROVE_AS_SUGGESTED
    assert decision.edited_name is None
    assert decision.edited_destination is None


def test_prompt_decision_edit_both_fields(monkeypatch):
    row = _preview_row("f1", name="old.pdf", destination="Finance/")
    monkeypatch.setattr("builtins.input", _scripted_input(["e", "New_Name.pdf", "Archive/"]))
    decision, stop = cli_module._prompt_decision(row, 1, 1)
    assert stop is False
    assert decision.decision == ApprovalDecisionType.APPROVE_WITH_EDIT
    assert decision.edited_name == "New_Name.pdf"
    assert decision.edited_destination == "Archive/"


def test_prompt_decision_edit_one_field_defaults_the_other(monkeypatch):
    row = _preview_row("f1", name="old.pdf", destination="Finance/")
    # Blank response to the destination sub-prompt defaults to the suggested
    # value — this is a data-entry default (Engineering Review's F1 finding
    # is about the a/e/r/s decision keystroke only, not these edit sub-fields).
    monkeypatch.setattr("builtins.input", _scripted_input(["e", "New_Name.pdf", ""]))
    decision, stop = cli_module._prompt_decision(row, 1, 1)
    assert decision.edited_name == "New_Name.pdf"
    assert decision.edited_destination == "Finance/"


def test_prompt_decision_reject(monkeypatch):
    row = _preview_row("f1")
    monkeypatch.setattr("builtins.input", _scripted_input(["r"]))
    decision, stop = cli_module._prompt_decision(row, 1, 1)
    assert stop is False
    assert decision.decision == ApprovalDecisionType.REJECT


def test_prompt_decision_skip_returns_none_and_stop_true(monkeypatch):
    row = _preview_row("f1")
    monkeypatch.setattr("builtins.input", _scripted_input(["s"]))
    decision, stop = cli_module._prompt_decision(row, 1, 1)
    assert decision is None
    assert stop is True


def test_prompt_decision_blank_input_reprompts_no_default(monkeypatch, capsys):
    """Engineering Review finding F1: pressing Enter (blank input) must NOT be
    treated as approval — it must re-prompt the same row, exactly like any
    other unrecognized input, until an explicit a/e/r/s is given."""
    row = _preview_row("f1")
    monkeypatch.setattr("builtins.input", _scripted_input(["", "   ", "zzz", "a"]))
    decision, stop = cli_module._prompt_decision(row, 1, 1)
    assert stop is False
    assert decision.decision == ApprovalDecisionType.APPROVE_AS_SUGGESTED
    captured = capsys.readouterr()
    assert captured.out.count("Please enter a, e, r, or s.") == 3


def test_collect_decisions_only_prompts_approval_required_rows(monkeypatch, capsys):
    auto_row = _preview_row("auto-1", tier="auto")
    review_row = _preview_row("review-1", tier="review_required")
    approval_row = _preview_row("approval-1", tier="approval_required")

    rows_by_tier = {"auto": [auto_row], "review_required": [review_row], "approval_required": [approval_row]}
    monkeypatch.setattr("builtins.input", _scripted_input(["a"]))

    decisions = cli_module._collect_decisions_interactively(rows_by_tier)

    assert set(decisions.keys()) == {"approval-1"}
    captured = capsys.readouterr()
    assert "1 file(s) will execute automatically" in captured.out
    assert "1 file(s) need attention" in captured.out


def test_collect_decisions_skip_remaining_leaves_later_rows_undecided(monkeypatch):
    rows = [_preview_row(f"f{i}") for i in range(1, 4)]
    rows_by_tier = {"auto": [], "review_required": [], "approval_required": rows}
    # approve f1, then skip on f2 — f3 must never be prompted at all.
    monkeypatch.setattr("builtins.input", _scripted_input(["a", "s"]))

    decisions = cli_module._collect_decisions_interactively(rows_by_tier)

    assert set(decisions.keys()) == {"f1"}


def test_collect_decisions_zero_approval_required_rows_prompts_nothing(monkeypatch):
    """Engineering Review finding F6: an all-auto (or auto+review_required
    -only) batch must visit zero rows and return {} without calling input()
    at all."""
    def _fail_if_called(prompt=""):
        raise AssertionError("input() should never be called when there are no approval_required rows")

    monkeypatch.setattr("builtins.input", _fail_if_called)
    rows_by_tier = {"auto": [_preview_row("a1", tier="auto")], "review_required": [], "approval_required": []}

    decisions = cli_module._collect_decisions_interactively(rows_by_tier)

    assert decisions == {}


# --- T3 (continued) / T4: _cmd_execute end to end, against real records and a
# real filesystem move — mirrors src/test_main.py's own "never mocked" Module
# 07 testing convention. ---


def test_cmd_execute_yes_flag_never_prompts_and_matches_default_behavior(tmp_path, monkeypatch, capsys):
    _isolate_execution_storage(tmp_path, monkeypatch)
    _write_sources_config(tmp_path, monkeypatch, destination_root=tmp_path / "library")
    record = _make_execution_record(tmp_path, "f1", tier="approval_required")

    def _fail_if_called(prompt=""):
        raise AssertionError("execute --yes must never call input()")

    monkeypatch.setattr("builtins.input", _fail_if_called)

    exit_code = cli_module.main(["execute", "--yes"])

    assert exit_code == 0
    reloaded = [r for r in database_module.load_metadata_store() if r.file_id == "f1"][0]
    # approval_required with no decision is left unchanged — identical to
    # today's execute() default (decisions={}).
    assert reloaded.processed_at is None
    assert reloaded.current_path == record.current_path


def test_cmd_execute_interactive_approve_moves_the_file(tmp_path, monkeypatch):
    _isolate_execution_storage(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _write_sources_config(tmp_path, monkeypatch, destination_root=library_root)
    _make_execution_record(tmp_path, "f1", tier="approval_required", suggested_destination="Finance/")

    monkeypatch.setattr("builtins.input", _scripted_input(["a"]))

    exit_code = cli_module.main(["execute"])

    assert exit_code == 0
    reloaded = [r for r in database_module.load_metadata_store() if r.file_id == "f1"][0]
    assert reloaded.processed_at is not None
    assert (library_root / "Finance" / "Amazon_2026-07-05.pdf").exists()


def test_cmd_execute_interactive_reject_leaves_file_in_place(tmp_path, monkeypatch):
    _isolate_execution_storage(tmp_path, monkeypatch)
    _write_sources_config(tmp_path, monkeypatch, destination_root=tmp_path / "library")
    record = _make_execution_record(tmp_path, "f1", tier="approval_required")

    monkeypatch.setattr("builtins.input", _scripted_input(["r"]))

    exit_code = cli_module.main(["execute"])

    assert exit_code == 0
    reloaded = [r for r in database_module.load_metadata_store() if r.file_id == "f1"][0]
    assert reloaded.processed_at is None
    assert reloaded.current_path == record.current_path


def test_cmd_execute_auto_tier_needs_no_prompt(tmp_path, monkeypatch):
    _isolate_execution_storage(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _write_sources_config(tmp_path, monkeypatch, destination_root=library_root)
    _make_execution_record(tmp_path, "f1", tier="auto", suggested_destination="Finance/")

    def _fail_if_called(prompt=""):
        raise AssertionError("auto-tier records must never trigger a prompt")

    monkeypatch.setattr("builtins.input", _fail_if_called)

    exit_code = cli_module.main(["execute"])

    assert exit_code == 0
    reloaded = [r for r in database_module.load_metadata_store() if r.file_id == "f1"][0]
    assert reloaded.processed_at is not None


def test_cmd_execute_keyboard_interrupt_never_calls_execute_batch(tmp_path, monkeypatch):
    """Ctrl-C during the prompt loop must abort before any file is moved —
    decision-collection happens entirely before execute() is invoked (design
    package §3.3 step 4)."""
    _isolate_execution_storage(tmp_path, monkeypatch)
    _write_sources_config(tmp_path, monkeypatch, destination_root=tmp_path / "library")
    record = _make_execution_record(tmp_path, "f1", tier="approval_required")

    def _raise_kbi(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _raise_kbi)

    exit_code = cli_module.main(["execute"])

    assert exit_code == 3
    reloaded = [r for r in database_module.load_metadata_store() if r.file_id == "f1"][0]
    assert reloaded.processed_at is None
    assert reloaded.current_path == record.current_path


def test_cmd_execute_keyboard_interrupt_during_run_execute_uses_generic_message(monkeypatch, capsys):
    """Implementation Audit finding (self-identified, corrected): a
    KeyboardInterrupt raised mid-run_execute() (after decision-collection has
    already completed cleanly — e.g. during the batch's actual file
    operations) must NOT print "no files have been moved", since that claim
    is only true for an interrupt during decision-collection itself. It must
    fall through to main()'s generic handler instead."""
    def _boom(decisions=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_module, "run_execute", _boom)
    monkeypatch.setattr(cli_module, "eligible_for_execution_records", lambda: [object()])
    monkeypatch.setattr(cli_module, "preview_batch", lambda records: [])

    exit_code = cli_module.main(["execute"])

    assert exit_code == 3
    captured = capsys.readouterr()
    assert "no files have been moved" not in captured.out
    assert "Aborted." in captured.out


def test_cmd_execute_nothing_to_execute_reuses_main_message(tmp_path, monkeypatch, capsys):
    _isolate_execution_storage(tmp_path, monkeypatch)
    _write_sources_config(tmp_path, monkeypatch)

    exit_code = cli_module.main(["execute"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Nothing to execute" in captured.out


# --- T5: undo --last resolution. ---


def test_most_recent_batch_id_picks_latest_timestamp_even_out_of_order():
    entries = [
        {"batch_id": "batch-2", "timestamp": "2026-07-20T10:00:00+00:00"},
        {"batch_id": "batch-1", "timestamp": "2026-07-19T10:00:00+00:00"},
        {"batch_id": "batch-3", "timestamp": "2026-07-21T10:00:00+00:00"},
    ]
    assert cli_module._most_recent_batch_id_from_entries(entries) == "batch-3"


def test_most_recent_batch_id_empty_log_returns_none():
    assert cli_module._most_recent_batch_id_from_entries([]) is None


def test_cmd_undo_last_resolves_and_calls_undo(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    runtime_io_module.append_action_log(
        batch_id="batch-old", file_id="f1", action="move_rename",
        from_path="/a", to_path="/b", approved_by="auto",
    )
    runtime_io_module.append_action_log(
        batch_id="batch-new", file_id="f2", action="move_rename",
        from_path="/c", to_path="/d", approved_by="auto",
    )

    calls = []
    monkeypatch.setattr(cli_module, "run_undo", lambda batch_id: calls.append(batch_id))

    exit_code = cli_module.main(["undo", "--last"])

    assert exit_code == 0
    assert calls == ["batch-new"]


def test_cmd_undo_last_with_empty_log_reports_nothing_to_undo(tmp_path, monkeypatch, capsys):
    _isolate_storage(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(cli_module, "run_undo", lambda batch_id: calls.append(batch_id))

    exit_code = cli_module.main(["undo", "--last"])

    assert exit_code == 0
    assert calls == []
    captured = capsys.readouterr()
    assert "nothing to undo" in captured.out


def test_cmd_undo_rejects_batch_id_and_last_together():
    with pytest.raises(SystemExit) as exc_info:
        cli_module.main(["undo", "batch-1", "--last"])
    assert exc_info.value.code == 2


def test_cmd_undo_rejects_neither_batch_id_nor_last():
    with pytest.raises(SystemExit) as exc_info:
        cli_module.main(["undo"])
    assert exc_info.value.code == 2


def test_cmd_undo_explicit_batch_id_calls_undo_directly(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_module, "run_undo", lambda batch_id: calls.append(batch_id))
    exit_code = cli_module.main(["undo", "batch-42"])
    assert exit_code == 0
    assert calls == ["batch-42"]


# --- T6: status. ---


def test_cmd_status_empty_store(tmp_path, monkeypatch, capsys):
    _isolate_storage(tmp_path, monkeypatch)
    _write_sources_config(tmp_path, monkeypatch)

    exit_code = cli_module.main(["status"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "no records — metadata store is empty" in captured.out
    assert "Awaiting your decision: 0" in captured.out
    assert "Most recent batch: (none)" in captured.out
    assert "destination_root: not set" in captured.out


def test_cmd_status_reports_counts_across_tiers(tmp_path, monkeypatch, capsys):
    _isolate_storage(tmp_path, monkeypatch)
    _write_sources_config(tmp_path, monkeypatch, destination_root=tmp_path / "library")

    _make_execution_record(tmp_path, "f1", tier="auto")
    _make_execution_record(tmp_path, "f2", tier="approval_required")
    _make_execution_record(tmp_path, "f3", tier="approval_required")
    _make_execution_record(tmp_path, "f4", tier="approval_required", processed_at="2026-07-20T00:00:00Z")

    exit_code = cli_module.main(["status"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "discovered: 4" in captured.out
    # f4 is already processed, so only f2/f3 count as awaiting a decision.
    assert "Awaiting your decision: 2" in captured.out
    assert "destination_root:" in captured.out


# --- T7: version / config. ---


def test_cmd_version_reads_real_versions_file(capsys):
    exit_code = cli_module.main(["version"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Pipeline Version" in captured.out


def test_cmd_version_missing_file_reports_gracefully(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "_VERSIONS_PATH", tmp_path / "does-not-exist.md")
    exit_code = cli_module.main(["version"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "version unknown" in captured.out


def test_cmd_config_reads_real_sources_yaml(capsys):
    exit_code = cli_module.main(["config"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "source_id" in captured.out
    # H5: config is no longer read-only-only — --set-source/--set-destination
    # now exist, so the old "Editing is not yet supported" line is gone.
    assert "--set-source" in captured.out


def test_cmd_config_missing_file_reports_gracefully(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "_SOURCES_CONFIG_PATH", tmp_path / "does-not-exist.yaml")
    exit_code = cli_module.main(["config"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Could not find" in captured.out


# --- T8: the renamed eligibility helper is a normal, public, importable
# function on src.main, doing exactly what it always did. ---


def test_eligible_for_execution_records_is_public_and_importable(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    _make_execution_record(tmp_path, "f1", tier="auto")
    _make_execution_record(tmp_path, "f2", tier="auto", processed_at="2026-07-20T00:00:00Z")

    records = main_module.eligible_for_execution_records()

    assert [r.file_id for r in records] == ["f1"]
    assert not hasattr(main_module, "_eligible_for_execution_records")


# --- T9 (exception/exit-code handling): the Layer 3 outermost safety net. ---


def test_main_unexpected_error_prints_short_message_and_returns_1(monkeypatch, capsys):
    # Injection point is run_report(), not run_scan(): H5 added a narrow,
    # deliberate ValueError/NotADirectoryError catch specifically around
    # run_scan() (_run_scan_with_friendly_config_errors(), design package
    # §9) to reclassify a *configuration* problem as an expected outcome
    # (exit 0), not a Layer 3 error. That narrow catch would otherwise
    # swallow this test's own generically-injected ValueError and report the
    # wrong thing (a false "not configured" message instead of genuine Layer
    # 3 propagation) — report() is untouched by H5, so it remains a clean,
    # unambiguous test of the *generic* Layer 3 net this test exists to
    # verify. (Disclosed, deliberate test-target change — H5 Implementation
    # Report.)
    def _boom():
        raise ValueError("simulated unexpected failure")

    monkeypatch.setattr(cli_module, "run_report", _boom)
    exit_code = cli_module.main(["report"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Unexpected error: simulated unexpected failure" in captured.err


def test_main_debug_flag_reraises_instead_of_swallowing(monkeypatch):
    def _boom(args):
        raise ValueError("simulated unexpected failure")

    # _COMMANDS binds direct function references at module load time, so the
    # dict entry itself (not the module attribute _cmd_execute) is what
    # main()'s dispatch actually calls — patched via setitem accordingly.
    monkeypatch.setitem(cli_module._COMMANDS, "execute", _boom)
    with pytest.raises(ValueError):
        cli_module.main(["execute", "--debug"])


# =====================================================================
# H5 — Configuration Experience
# (`Build-out/09 CLI & Product Interface/H5 Configuration Experience —
# Design Package.md`; Engineering Review in the same folder — findings F1-F6
# verified explicitly below.)
# =====================================================================


# --- _yaml_safe_scalar / _write_config_value: F1 (special characters must
# either be safely supported or fail precisely — never silently corrupt). ---


@pytest.mark.parametrize("value", [
    "/Users/vicky/Downloads",
    "/Users/vicky/Archive #2",
    "/Users/vicky/Client: Acme",
    "/Users/vicky/It's Mine",
    "",
    "null",
    "/Users/vicky/Trailing Spaces   ",
])
def test_yaml_safe_scalar_round_trips_every_case(value):
    scalar = cli_module._yaml_safe_scalar(value)
    parsed = yaml.safe_load(f"destination_root: {scalar}")
    assert parsed["destination_root"] == value


def test_write_config_value_handles_yaml_special_characters(tmp_path, monkeypatch):
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch)
    tricky_value = str(tmp_path / 'Archive #2: Client\'s "Files"')

    cli_module._write_config_value("destination_root", tricky_value)

    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["destination_root"] == tricky_value


def test_write_config_value_reverts_file_on_verification_mismatch(tmp_path, monkeypatch):
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch, destination_root="/tmp/original")
    original_text = config_path.read_text(encoding="utf-8")

    # Simulates a verification read that doesn't match what was written —
    # exercises the revert-on-failure path (F1: "silent corruption... is
    # unacceptable") without needing a genuinely corrupt write to trigger it.
    monkeypatch.setattr(cli_module.yaml, "safe_load", lambda f: {"destination_root": "/tmp/WRONG"})

    with pytest.raises(ValueError, match="restored to its previous state"):
        cli_module._write_config_value("destination_root", "/tmp/new-value")

    assert config_path.read_text(encoding="utf-8") == original_text


def test_write_config_value_raises_precise_error_when_source_missing(tmp_path, monkeypatch):
    config_path = tmp_path / "sources.yaml"
    config_path.write_text("destination_root: null\n", encoding="utf-8")
    monkeypatch.setattr(cli_module, "_SOURCES_CONFIG_PATH", config_path)

    with pytest.raises(ValueError, match="unexpected shape"):
        cli_module._write_config_value("source_path", "/tmp/x")


# --- F4: precise, indentation-aware line matching. ---


def test_find_destination_root_line_ignores_nested_key_of_the_same_name():
    lines = (
        "sources:\n"
        "  - source_id: downloads\n"
        "    path: /tmp/x\n"
        "    nested:\n"
        "      destination_root: should-not-match\n"
        "destination_root: /tmp/real\n"
    ).splitlines()
    index = cli_module._find_destination_root_line(lines)
    assert lines[index] == "destination_root: /tmp/real"


def test_find_source_path_line_stops_at_end_of_source_block():
    # `path:` only appears *before* the source block here — this must be
    # treated as "not found under downloads", not silently matched anyway.
    lines = (
        "sources:\n"
        "  - source_id: downloads\n"
        "    type: local_folder\n"
        "execution_mode: manual\n"
    ).splitlines()
    with pytest.raises(ValueError, match="unexpected shape"):
        cli_module._find_source_path_line(lines)


# --- Comment/structure preservation — the core claim of the Option C
# architecture (design package §9), verified with a full line-by-line diff. ---


def test_write_config_value_source_path_preserves_every_other_line(tmp_path, monkeypatch):
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch)
    original_lines = config_path.read_text(encoding="utf-8").splitlines()

    new_value = str(tmp_path / "MyDownloads")
    cli_module._write_config_value("source_path", new_value)

    new_lines = config_path.read_text(encoding="utf-8").splitlines()
    assert len(new_lines) == len(original_lines)
    for i, (old_line, new_line) in enumerate(zip(original_lines, new_lines)):
        if i == 6:  # the `path:` line — see _write_realistic_sources_config's own layout
            assert new_line == f"    path: {new_value}"
            # The stale "filled in at runtime" inline comment is deliberately
            # dropped once a real value is written (_write_config_value's own
            # documented, disclosed exception to "preserve every comment").
            assert "filled in at runtime" not in new_line
        else:
            assert old_line == new_line, f"line {i} changed unexpectedly: {old_line!r} -> {new_line!r}"


def test_write_config_value_destination_root_preserves_every_other_line(tmp_path, monkeypatch):
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch, source_path="/tmp/existing")
    original_lines = config_path.read_text(encoding="utf-8").splitlines()

    new_value = str(tmp_path / "MyLibrary")
    cli_module._write_config_value("destination_root", new_value)

    new_lines = config_path.read_text(encoding="utf-8").splitlines()
    assert len(new_lines) == len(original_lines)
    for i, (old_line, new_line) in enumerate(zip(original_lines, new_lines)):
        if i == 18:  # the `destination_root:` line
            assert new_line == f"destination_root: {new_value}"
        else:
            assert old_line == new_line, f"line {i} changed unexpectedly: {old_line!r} -> {new_line!r}"


# --- _cmd_init: FR-1/FR-2/FR-4, via simulated stdin (mirrors
# _prompt_decision()'s own established test convention). ---


def test_cmd_init_configures_both_settings_first_time(tmp_path, monkeypatch, capsys):
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch)
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    library_dir = tmp_path / "Library"
    library_dir.mkdir()

    monkeypatch.setattr("builtins.input", _scripted_input([str(downloads_dir), str(library_dir)]))

    exit_code = cli_module.main(["init"])

    assert exit_code == 0
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["sources"][0]["path"] == str(downloads_dir)
    assert reloaded["destination_root"] == str(library_dir)
    captured = capsys.readouterr()
    assert "Setup complete" in captured.out


def test_cmd_init_reprompts_on_invalid_or_blank_path(tmp_path, monkeypatch, capsys):
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch)
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    library_dir = tmp_path / "Library"
    library_dir.mkdir()
    nonexistent = str(tmp_path / "does-not-exist")

    monkeypatch.setattr(
        "builtins.input",
        _scripted_input(["", nonexistent, str(downloads_dir), str(library_dir)]),
    )

    exit_code = cli_module.main(["init"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Please enter a path." in captured.out
    assert "does not exist or is not a directory" in captured.out
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["sources"][0]["path"] == str(downloads_dir)


def test_cmd_init_overwrite_confirmed_replaces_value(tmp_path, monkeypatch):
    existing_source = tmp_path / "OldDownloads"
    existing_source.mkdir()
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch, source_path=str(existing_source))
    new_source = tmp_path / "NewDownloads"
    new_source.mkdir()
    library_dir = tmp_path / "Library"
    library_dir.mkdir()

    monkeypatch.setattr("builtins.input", _scripted_input(["y", str(new_source), str(library_dir)]))

    exit_code = cli_module.main(["init"])

    assert exit_code == 0
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["sources"][0]["path"] == str(new_source)


def test_cmd_init_overwrite_declined_keeps_existing_value(tmp_path, monkeypatch, capsys):
    existing_source = tmp_path / "OldDownloads"
    existing_source.mkdir()
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch, source_path=str(existing_source))
    library_dir = tmp_path / "Library"
    library_dir.mkdir()

    monkeypatch.setattr("builtins.input", _scripted_input(["n", str(library_dir)]))

    exit_code = cli_module.main(["init"])

    assert exit_code == 0
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["sources"][0]["path"] == str(existing_source)
    assert reloaded["destination_root"] == str(library_dir)
    captured = capsys.readouterr()
    assert "Keeping existing Downloads source path." in captured.out


def test_cmd_init_missing_config_file_reports_gracefully(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "_SOURCES_CONFIG_PATH", tmp_path / "does-not-exist.yaml")
    exit_code = cli_module.main(["init"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Could not find" in captured.out


# --- config --set-source / --set-destination: FR-5, F5 (flags on the
# existing `config` subcommand, not a nested sub-subparser). ---


def test_cmd_config_set_source_and_destination(tmp_path, monkeypatch, capsys):
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch)
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    library_dir = tmp_path / "Library"
    library_dir.mkdir()

    exit_code = cli_module.main(
        ["config", "--set-source", str(downloads_dir), "--set-destination", str(library_dir)]
    )

    assert exit_code == 0
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["sources"][0]["path"] == str(downloads_dir)
    assert reloaded["destination_root"] == str(library_dir)
    captured = capsys.readouterr()
    assert "Downloads source path set to" in captured.out
    assert "destination_root set to" in captured.out


def test_cmd_config_set_source_only_leaves_destination_untouched(tmp_path, monkeypatch):
    existing_destination = tmp_path / "ExistingLibrary"
    existing_destination.mkdir()
    config_path = _write_realistic_sources_config(
        tmp_path, monkeypatch, destination_root=str(existing_destination)
    )
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()

    exit_code = cli_module.main(["config", "--set-source", str(downloads_dir)])

    assert exit_code == 0
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["sources"][0]["path"] == str(downloads_dir)
    assert reloaded["destination_root"] == str(existing_destination)


def test_cmd_config_set_invalid_path_changes_nothing(tmp_path, monkeypatch, capsys):
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch)
    original_text = config_path.read_text(encoding="utf-8")

    exit_code = cli_module.main(["config", "--set-source", str(tmp_path / "does-not-exist")])

    assert exit_code == 0
    assert config_path.read_text(encoding="utf-8") == original_text
    captured = capsys.readouterr()
    assert "does not exist or is not a directory" in captured.out
    assert "Nothing was changed" in captured.out


# --- scan/run friendly config-error handling: FR-6, C1-PAT-1, R2 (narrow
# catch — a genuinely unrelated exception must still propagate to Layer 3,
# verified separately above via the retargeted
# test_main_unexpected_error_prints_short_message_and_returns_1). ---


def test_cmd_scan_unconfigured_prints_friendly_message_and_exits_0(tmp_path, monkeypatch, capsys):
    _isolate_storage(tmp_path, monkeypatch)
    _write_realistic_sources_config(tmp_path, monkeypatch)  # path left null

    exit_code = cli_module.main(["scan"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "no path set" in captured.out
    assert "python -m src.cli init" in captured.out
    assert "Unexpected error" not in captured.out


def test_cmd_scan_configured_path_missing_prints_distinct_friendly_message(tmp_path, monkeypatch, capsys):
    _isolate_storage(tmp_path, monkeypatch)
    missing_dir = tmp_path / "does-not-exist"
    _write_realistic_sources_config(tmp_path, monkeypatch, source_path=str(missing_dir))

    exit_code = cli_module.main(["scan"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "is not a directory" in captured.out
    assert "config --set-source" in captured.out
    assert "Unexpected error" not in captured.out


def test_cmd_run_stops_before_classify_when_unconfigured(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    _write_realistic_sources_config(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(cli_module, "classify", lambda: calls.append("classify"))

    exit_code = cli_module.main(["run"])

    assert exit_code == 0
    assert calls == []


# --- AC-8: init/config --set-* never write anywhere except sources.yaml. ---


def test_cmd_init_and_config_set_touch_only_sources_yaml(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch)
    metadata_path = tmp_path / "metadata_store.json"
    metadata_path.write_text("[]", encoding="utf-8")
    action_log_path_ = tmp_path / "action_log.jsonl"
    action_log_path_.write_text("", encoding="utf-8")
    other_mtimes_before = {
        p: p.stat().st_mtime_ns for p in (metadata_path, action_log_path_)
    }

    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    library_dir = tmp_path / "Library"
    library_dir.mkdir()

    monkeypatch.setattr("builtins.input", _scripted_input([str(downloads_dir), str(library_dir)]))
    exit_code = cli_module.main(["init"])
    assert exit_code == 0

    for path, mtime_before in other_mtimes_before.items():
        assert path.stat().st_mtime_ns == mtime_before, f"{path} was unexpectedly touched"
    assert config_path.exists()  # the one file that IS expected to change


def test_cmd_status_and_version_touch_nothing(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    config_path = _write_realistic_sources_config(tmp_path, monkeypatch)
    config_mtime_before = config_path.stat().st_mtime_ns

    cli_module.main(["status"])
    cli_module.main(["version"])
    cli_module.main(["config"])

    assert config_path.stat().st_mtime_ns == config_mtime_before


def test_cmd_scan_valid_configuration_is_unaffected(tmp_path, monkeypatch, capsys):
    _isolate_storage(tmp_path, monkeypatch)
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    (downloads_dir / "file.txt").write_text("hello")
    _write_realistic_sources_config(tmp_path, monkeypatch, source_path=str(downloads_dir))

    exit_code = cli_module.main(["scan"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Unexpected error" not in captured.out
    assert "python -m src.cli init" not in captured.out
    assert len(database_module.load_metadata_store()) == 1


# --- provider enable/disable/status: TD-01 v0.9
# ("Build-out/02 Classification/TD-01 Provider Architecture — Design
# Package.md" §5/§7). Byte-for-byte realistic config, matching the real
# src/config/sources.yaml's actual TD-01 block, is required here (unlike most
# of this file's other tests) because _write_config_value()'s line-finder
# needs the three new top-level keys already present to update them — see
# _write_realistic_sources_config_with_provider_keys() below. ---


def _write_realistic_sources_config_with_provider_keys(
    tmp_path, monkeypatch, source_path=None, destination_root=None,
    classification_provider="null", extraction_provider="null",
    ai_provider_consent="false",
):
    """Extends _write_realistic_sources_config()'s byte-for-byte-realistic
    approach with the TD-01 v0.9 provider block, matching the real
    src/config/sources.yaml's actual current content exactly."""
    config_path = tmp_path / "sources.yaml"
    path_value = "null" if source_path is None else str(source_path)
    destination_value = "null" if destination_root is None else str(destination_root)
    text = (
        '# Source config — see Build-out/01 Watch & Ingest/01 Watch & Ingest.md for the "Source" concept.\n'
        '\n'
        'sources:\n'
        '  - source_id: downloads\n'
        f"    path: {path_value}\n"
        '    type: local_folder\n'
        '    enabled: true\n'
        '    recursive: false\n'
        '\n'
        'execution_mode: manual\n'
        '\n'
        f'destination_root: {destination_value}\n'
        '\n'
        '# TD-01 v0.9 — autonomous provider selection.\n'
        f'classification_provider: {classification_provider}\n'
        f'extraction_provider: {extraction_provider}\n'
        f'ai_provider_consent: {ai_provider_consent}\n'
    )
    config_path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(main_module, "_SOURCES_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli_module, "_SOURCES_CONFIG_PATH", config_path)
    return config_path


def test_provider_status_reports_off_by_default(tmp_path, monkeypatch, capsys):
    _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: ["claude"])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: ["claude"])

    exit_code = cli_module.main(["provider", "status"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Opt-in enabled:           False" in captured.out
    assert "classification_provider:  not set" in captured.out


def test_provider_status_missing_config_reports_gracefully(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "_SOURCES_CONFIG_PATH", tmp_path / "does-not-exist.yaml")
    exit_code = cli_module.main(["provider", "status"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Could not find" in captured.out


def test_provider_enable_refuses_when_provider_not_registered(tmp_path, monkeypatch, capsys):
    _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: [])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: [])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

    exit_code = cli_module.main(["provider", "enable"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "not a registered provider" in captured.out
    reloaded = yaml.safe_load(
        (tmp_path / "sources.yaml").read_text(encoding="utf-8")
    )
    assert reloaded["ai_provider_consent"] is False


def test_provider_enable_refuses_when_api_key_unset(tmp_path, monkeypatch, capsys):
    config_path = _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: ["claude"])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: ["claude"])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    exit_code = cli_module.main(["provider", "enable"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "ANTHROPIC_API_KEY is not set" in captured.out
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["ai_provider_consent"] is False


def test_provider_enable_declined_confirmation_changes_nothing(tmp_path, monkeypatch, capsys):
    config_path = _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: ["claude"])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: ["claude"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setattr("builtins.input", _scripted_input(["n"]))

    exit_code = cli_module.main(["provider", "enable"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Not enabled" in captured.out
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["ai_provider_consent"] is False
    assert reloaded["classification_provider"] is None


def test_provider_enable_confirmed_writes_all_three_keys(tmp_path, monkeypatch, capsys):
    config_path = _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: ["claude"])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: ["claude"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setattr("builtins.input", _scripted_input(["y"]))

    exit_code = cli_module.main(["provider", "enable"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "enabled" in captured.out.lower()
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["ai_provider_consent"] is True
    assert reloaded["classification_provider"] == "claude"
    assert reloaded["extraction_provider"] == "claude"


def test_provider_enable_disclosure_text_shown_before_confirmation(tmp_path, monkeypatch, capsys):
    """The disclosure (cost, what gets sent, key never persisted) must
    actually appear on screen before the y/n prompt — not just be defined as
    a module constant nobody prints."""
    _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: ["claude"])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: ["claude"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setattr("builtins.input", _scripted_input(["n"]))

    cli_module.main(["provider", "enable"])

    captured = capsys.readouterr()
    assert "real, metered API cost" in captured.out
    assert "ANTHROPIC_API_KEY" in captured.out
    assert "never written to src/config/sources.yaml" in captured.out


def test_provider_enable_yes_flag_skips_confirmation_prompt(tmp_path, monkeypatch, capsys):
    """INFRA-01 / OD-GUI-5: -y/--yes must enable without ever calling
    input() — a scripted input list of zero responses raises if input() is
    called at all, so this fails loudly if the prompt is not actually
    skipped."""
    config_path = _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: ["claude"])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: ["claude"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setattr("builtins.input", _scripted_input([]))

    exit_code = cli_module.main(["provider", "enable", "-y"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "enabled" in captured.out.lower()
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["ai_provider_consent"] is True
    assert reloaded["classification_provider"] == "claude"
    assert reloaded["extraction_provider"] == "claude"


def test_provider_enable_yes_flag_still_shows_disclosure(tmp_path, monkeypatch, capsys):
    """The confirmation prompt is skipped by -y, but the disclosure text
    itself must still be printed — -y bypasses the interactive confirmation
    step only, not the disclosure guarantee."""
    _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: ["claude"])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: ["claude"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setattr("builtins.input", _scripted_input([]))

    cli_module.main(["provider", "enable", "--yes"])

    captured = capsys.readouterr()
    assert "real, metered API cost" in captured.out
    assert "never written to src/config/sources.yaml" in captured.out


def test_provider_enable_without_yes_flag_still_prompts(tmp_path, monkeypatch, capsys):
    """Backward-compatibility check: omitting -y must reproduce the exact
    pre-INFRA-01 behavior — input() is still called, and a declined answer
    still changes nothing."""
    config_path = _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: ["claude"])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: ["claude"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setattr("builtins.input", _scripted_input(["n"]))

    exit_code = cli_module.main(["provider", "enable"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Not enabled" in captured.out
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["ai_provider_consent"] is False


def test_provider_disable_writes_only_consent_key(tmp_path, monkeypatch, capsys):
    config_path = _write_realistic_sources_config_with_provider_keys(
        tmp_path, monkeypatch, classification_provider="claude",
        extraction_provider="claude", ai_provider_consent="true",
    )

    exit_code = cli_module.main(["provider", "disable"])

    assert exit_code == 0
    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert reloaded["ai_provider_consent"] is False
    # classification_provider/extraction_provider are deliberately left
    # as-is by disable() — only consent gates their effect (main.py's
    # _resolve_provider_for_classification()/_resolve_provider_for_extraction()).
    assert reloaded["classification_provider"] == "claude"
    assert reloaded["extraction_provider"] == "claude"


def test_provider_status_notes_consent_on_but_key_unset(tmp_path, monkeypatch, capsys):
    _write_realistic_sources_config_with_provider_keys(
        tmp_path, monkeypatch, classification_provider="claude",
        extraction_provider="claude", ai_provider_consent="true",
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    exit_code = cli_module.main(["provider", "status"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "ANTHROPIC_API_KEY is not set in this environment" in captured.out


def test_provider_status_notes_consent_on_but_provider_key_missing(tmp_path, monkeypatch, capsys):
    _write_realistic_sources_config_with_provider_keys(
        tmp_path, monkeypatch, ai_provider_consent="true",
    )

    exit_code = cli_module.main(["provider", "status"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "opt-in is enabled but one or both provider keys are" in captured.out


def test_provider_no_subcommand_defaults_to_status(tmp_path, monkeypatch, capsys):
    _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    exit_code = cli_module.main(["provider"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Provider configuration" in captured.out


def test_provider_enable_and_disable_touch_only_sources_yaml(tmp_path, monkeypatch):
    """Mirrors this file's own test_cmd_init_and_config_set_touch_only_sources_yaml
    convention — a provider opt-in/opt-out is still just a config write, must
    never touch Database/Runtime."""
    _isolate_storage(tmp_path, monkeypatch)
    config_path = _write_realistic_sources_config_with_provider_keys(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "registered_classification_providers", lambda: ["claude"])
    monkeypatch.setattr(cli_module, "registered_extraction_providers", lambda: ["claude"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setattr("builtins.input", _scripted_input(["y"]))

    cli_module.main(["provider", "enable"])
    cli_module.main(["provider", "disable"])

    assert config_path.exists()
    assert not database_module._METADATA_STORE_PATH.exists()
    assert not runtime_io_module._ACTION_LOG_PATH.exists()
