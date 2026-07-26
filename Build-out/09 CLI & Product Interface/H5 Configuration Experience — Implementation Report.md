# H5 — Configuration Experience — Implementation Report

**Status:** Implementation complete. Design Package accepted as baseline (Approved with Changes); all six Engineering Review findings (F1–F6) incorporated; Implementation Audit (WP-7) complete with one self-identified-and-corrected finding.
**Scope:** `init` and `config --set-source`/`--set-destination`, plus specific, actionable messages when `scan`/`run` hit an unconfigured or misconfigured Downloads source instead of the generic "Unexpected error" framing.

---

## Files changed

- **`src/cli.py`** (551 → 935 lines). New: `_yaml_safe_scalar()`, `_find_source_path_line()`, `_find_destination_root_line()`, `_write_config_value()`, `_resolve_existing_directory()`, `_prompt_path()`, `_confirm()`, `_init_one_setting()`, `_cmd_init()`, `_run_scan_with_friendly_config_errors()`. Modified: `build_parser()` (new `init` subparser; `config` subparser gains `--set-source`/`--set-destination`), `_cmd_scan()`/`_cmd_run()` (now route through the new friendly-error wrapper), `_cmd_config()` (handles the two new flags before its existing read-only display), `_COMMANDS` (registers `init`), module docstring (H5 summary, severity, diagnostic classification). No change to any `_cmd_*` function C1 already shipped beyond `scan`/`run`/`config`.
- **`src/test_cli.py`** (551 → ~1,060 lines net of the earlier C1 baseline). 29 net new tests; 2 pre-existing tests retargeted with disclosed reasoning (see Implementation Audit).
- **`Governance/ARCHITECTURE_DECISIONS.md`**: new decision 33 (severity classification + diagnostic taxonomy, resolving F2).
- **`src/README.md`**: one paragraph added to `cli.py`'s layout-table entry.
- **Not touched:** `src/main.py`, `src/pipeline/*.py`, `src/models/*.py`, `src/storage/*.py`, `Rules/*.md` — confirmed via `git diff --stat` against each path, zero changes from this work package.

## Tests added

31 new tests across: `_yaml_safe_scalar()` round-trip correctness (7 parametrized special-character/edge cases); `_write_config_value()`'s special-character handling, revert-on-verification-failure, and precise unexpected-shape error; `_find_source_path_line()`/`_find_destination_root_line()`'s exact, adversarially-tested matching rules; full byte-for-byte comment/structure preservation for both settings; `_cmd_init()`'s first-run configuration, invalid/blank-input re-prompting, and both overwrite-confirm/decline branches; `config --set-source`/`--set-destination`'s success, partial-update, and invalid-input paths; `scan`/`run`'s two distinct friendly messages, exercised against real (unmocked) `load_source_config()`/`scan_source()` calls; a valid configuration confirmed unaffected; and AC-8's specified mtime-isolation check. 2 pre-existing tests retargeted (disclosed): one moved its fault-injection point from `scan`/`run_scan` to `report`/`run_report` (H5's own new, narrower exception handling would otherwise swallow it); one updated its assertion text to match `config`'s new footer.

## Final regression results

`src/test_cli.py`: **70/70 passing**. Full project suite: **799/799 passing** (770 pre-existing at C1's closure + 29 net new), run fresh as the final step of the Implementation Audit. Zero failures, zero new skips.

## Product Acceptance verdict

Not applicable at this stage — H5 has completed Design → Review → Implementation → Audit under the Engineering Change Playbook's spine (per the design package's own §1.5-equivalent process-fit reasoning, mirrored from C1). No separate Product Acceptance Test was instructed or performed for H5; the C1 Release Planning Matrix (the source of this work package) already carries the product-lens evidence (U5/H5) that motivated it.

## Known limitations

- **Targeted, not general, YAML editing (Option C, disclosed and accepted in the design).** `_write_config_value()` understands exactly two fixed keys in a known-shape file; it is not a general-purpose YAML editor. If `src/config/sources.yaml`'s structure changes materially (e.g. genuine multi-source support, TD-11, explicitly out of scope here), this writer would need revisiting.
- **`init` has no non-interactive/scriptable mode** (NG6, disclosed) — a future installer or CI fixture must either hand-edit `sources.yaml` (fully supported, unaffected) or drive `init`'s prompts via simulated stdin.
- **The one inline comment on `sources.yaml`'s `path:` line ("filled in at runtime...") is dropped, not preserved, the first time a real value is written** — disclosed and deliberate: that comment describes the unset state and becomes factually wrong the moment a real path exists. Every other comment in the file, including the block comment documenting `destination_root`, is preserved exactly.
- **No end-to-end test drives a genuine write failure all the way through `_cmd_init` to `main()`'s Layer 3 exit** — only its two constituent, independently-tested pieces are (`_write_config_value()`'s own revert path; `main()`'s pre-existing Layer 3 handling). Assessed low-risk: no logic sits between them beyond a direct call (Implementation Audit).
- **`src/pipeline/watch_ingest.py` independently re-derives its own copy of `_SOURCES_CONFIG_PATH`** — a third copy alongside `main.py`'s and `cli.py`'s own, discovered while building this work package's tests (the first in this project to exercise a real, unmocked `scan()` end to end). Not a functional defect (all three copies compute the same value); not fixed here (out of scope, per NG2/TD-29's own existing framing of injectable-paths work as separate, larger scope).
- **C1's own disclosed open question about exit 0 possibly under-signaling "nothing happened" to a future scripted caller (design package §3.5) is inherited, not resolved**, by `scan`/`run`'s new friendly-error exit-0 paths (Engineering Review finding F6).

## Engineering decisions

- **Config-writer architecture: targeted line replacement over a full YAML round-trip**, specifically to avoid a new dependency (`ruamel.yaml`) while `PRODUCT_READINESS_REVIEW.md` finding H1 (a broken, double-pinned `requirements.txt`) remains open — re-verified as still-true at Engineering Review time, not assumed.
- **Value serialization: `yaml.safe_dump(..., width=float("inf"))`**, chosen over hand-rolled quoting logic specifically because it reuses PyYAML's own correctness for edge cases (quotes, colons, `#`, leading/trailing whitespace) without a new dependency — and because a first pass without the explicit `width` argument was caught, by a realistic (not hand-picked) test, silently corrupting long values via PyYAML's default 80-column wrap (see Implementation Audit).
- **Safety net: write-then-verify-then-revert**, not atomic temp-file-plus-rename — matches this codebase's own existing convention (no write anywhere in `storage/database.py`/`storage/runtime_io.py` uses atomic rename either) while still directly satisfying "silent corruption... is unacceptable": a failed or mismatched write is always caught and the original file restored before the caller sees an error.
- **`config --set-source`/`--set-destination` as flags, not a nested `config set <key> <value>` sub-subparser** (Engineering Review finding F5's own recommendation) — avoids introducing this project's first nested-subparser pattern for a single, narrow use.
- **Severity: High, same tier as C1** (decision 33) — new, user-facing capability with real product leverage, zero pipeline-logic risk, no new severity tier invented (directly applying the lesson of C1's own Engineering Review finding F3).
