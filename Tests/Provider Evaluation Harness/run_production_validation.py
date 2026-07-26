"""
TD-01 Production Validation — Phase 2 execution script.

Design: "TD-01 Production Validation Plan.md" (project root), approved
2026-07-26. Implements §2 (dataset), §3 (metrics), §4 (before/after
comparison), §1.3/§1.4 (cost estimate + rate-limit handling) exactly as
specified there. Does not modify production code or pipeline logic — every
pipeline call below is the same `classify_batch()`/`extract_metadata_batch()`/
`detect_duplicates_batch()`/`suggest_naming_and_destination_batch()`/
`score_confidence_batch()` chain `src/main.py` already uses, called in the
same order, against the shipped `ClaudeAPIClassifier`/`ClaudeAPIExtractor`
(`src/providers/claude.py`) exactly as implemented in TD-01 v0.9.

Must be run locally (not in the sandboxed session that produced this
script) because it needs a real `ANTHROPIC_API_KEY` in the environment —
see "TD-01 Production Validation Execution Guide.md" for exact steps.

What this script does, precisely:
  1. Reads the REAL production `Database/Metadata/metadata_store.json`
     (866 real records, read-only) to sample a bounded validation set and
     to read each sampled record's existing "Before" values — these were
     already computed under deterministic-only conditions (this project's
     `ai_provider_consent` has been `false` for this store's entire
     existence), so no reprocessing is needed to get Before data for them.
  2. Builds fresh records for two named real difficult cases (the INC-34
     filing, the renamed/resized screenshot — both from the C2 Sandbox
     validation's sample folder, not the real Downloads folder) and runs
     them once with no provider (safe, deterministic-only fallback — this
     IS their "Before," since no prior computed record exists for them)
     and once with the real Claude provider ("After").
  3. Isolates all storage writes to a temp directory (same proven
     `_isolate_storage()`/`_restore_storage()` pattern as
     `run_harness.py`) — the real `Database/`/`Runtime/` are never
     written to by this script. Verified byte-identical before/after by
     the execution guide's own checklist, not just by this script.
  4. Runs the real pipeline chain against the sampled real files with the
     real, registered "claude" provider ("After"), computes every metric
     from "TD-01 Production Validation Plan.md" §3, and writes a
     privacy-safe (structure-only, no file content) results file under
     `Runtime/Validation/<timestamp>/` for Claude to turn into the final
     report — never printing or persisting raw file content, matching
     `DATASET_GUIDELINES.md` §2.2/§2.3 exactly.

Usage (from the project root, after `python3 -m src.cli provider enable`
has been run separately — see the execution guide):
    python3 "Tests/Provider Evaluation Harness/run_production_validation.py" [-y]
"""

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HARNESS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _HARNESS_DIR.parents[1]  # .../Tests/Provider Evaluation Harness -> Tests -> project root

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import src.storage.database as database_module  # noqa: E402
import src.storage.runtime_io as runtime_io_module  # noqa: E402
from src.models.classification import Category  # noqa: E402
from src.pipeline.classification import classify_batch  # noqa: E402
from src.pipeline.confidence import score_confidence_batch  # noqa: E402
from src.pipeline.duplicate_detector import detect_duplicates_batch  # noqa: E402
from src.pipeline.metadata import REQUIRED_FIELDS, extract_metadata_batch  # noqa: E402
from src.pipeline.naming import suggest_naming_and_destination_batch  # noqa: E402
from src.pipeline.watch_ingest import build_file_record  # noqa: E402
from src.providers.registry import (  # noqa: E402
    resolve_classification_provider,
    resolve_extraction_provider,
)

# Side-effect import — registers "claude" (see src/providers/claude.py's own
# docstring, and src/main.py's/run_harness.py's identical import).
import src.providers.claude  # noqa: E402,F401

# --- Config: named difficult cases (§2.2 of the plan). Override with
# --extra-file if these paths have moved or don't exist on this machine. ---
_DEFAULT_NAMED_CASES = [
    ("/Users/vicky/Desktop/sample/1-11920857482.pdf34DSC.pdf", "INC-34 legal document"),
    (
        "/Users/vicky/Desktop/sample/5579374e-6e1d-46a6-9ddc-2203c5d68e56.jpeg",
        "Renamed/resized screenshot",
    ),
]

# Same pricing table as run_harness.py (design §6: kept in the tool, not the
# frozen provider contracts, since pricing changes independently).
_PRICE_PER_MILLION_TOKENS_USD = {
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
}

# Categories that never reach a provider call for classification or
# extraction respectively — mirrors classification.py's Pass-1 deterministic
# set and metadata.py's _DETERMINISTIC_ONLY_CATEGORIES exactly (read from
# those modules where possible; the classification-side set isn't exported,
# so it's restated here for the cost estimate only — never used to change
# any actual routing decision, only to print an honest pre-run estimate).
_DETERMINISTIC_CLASSIFICATION_CATEGORIES = frozenset(
    {Category.ARCHIVE, Category.APPLICATION, Category.VIDEO, Category.AUDIO,
     Category.IMAGE, Category.SCREENSHOT}
)


# --- Isolation (identical pattern to run_harness.py's, restore-on-finally) ---

def _isolate_storage(tmp_path: Path) -> Dict[str, Path]:
    original = {
        "metadata_store_path": database_module._METADATA_STORE_PATH,
        "hash_index_path": database_module._HASH_INDEX_PATH,
        "phash_index_path": database_module._PHASH_INDEX_PATH,
        "name_index_path": database_module._NAME_INDEX_PATH,
        "version_history_path": database_module._VERSION_HISTORY_PATH,
        "user_corrections_path": database_module._USER_CORRECTIONS_PATH,
        "action_log_path": runtime_io_module._ACTION_LOG_PATH,
    }
    database_module._METADATA_STORE_PATH = tmp_path / "metadata_store.json"
    database_module._HASH_INDEX_PATH = tmp_path / "hash_index.json"
    database_module._PHASH_INDEX_PATH = tmp_path / "phash_index.json"
    database_module._NAME_INDEX_PATH = tmp_path / "name_index.json"
    database_module._VERSION_HISTORY_PATH = tmp_path / "version_history.json"
    database_module._USER_CORRECTIONS_PATH = tmp_path / "user_corrections.json"
    runtime_io_module._ACTION_LOG_PATH = tmp_path / "action_log.jsonl"
    return original


def _restore_storage(original: Dict[str, Path]) -> None:
    database_module._METADATA_STORE_PATH = original["metadata_store_path"]
    database_module._HASH_INDEX_PATH = original["hash_index_path"]
    database_module._PHASH_INDEX_PATH = original["phash_index_path"]
    database_module._NAME_INDEX_PATH = original["name_index_path"]
    database_module._VERSION_HISTORY_PATH = original["version_history_path"]
    database_module._USER_CORRECTIONS_PATH = original["user_corrections_path"]
    runtime_io_module._ACTION_LOG_PATH = original["action_log_path"]


# --- §2: dataset sampling from the REAL production store (read-only) ---

def _stratified_sample(records: List, target: int, seed: int = 42) -> List:
    """Groups by extension, round-robins a seeded, deterministic pick across
    groups so the sample is reproducible and not hand-picked. Records are
    sorted by file_id first so the same seed always yields the same sample
    regardless of the store's on-disk ordering."""
    groups: Dict[str, List] = defaultdict(list)
    for record in sorted(records, key=lambda r: r.file_id):
        ext = Path(record.current_path).suffix.lower()
        groups[ext].append(record)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)
    picked: List = []
    group_keys = sorted(groups)
    idx = 0
    while len(picked) < target and any(groups[k] for k in group_keys):
        key = group_keys[idx % len(group_keys)]
        if groups[key]:
            picked.append(groups[key].pop())
        idx += 1
    return picked


def _fixed_sample(records: List, n: int, seed: int = 42) -> List:
    ordered = sorted(records, key=lambda r: r.file_id)
    rng = random.Random(seed)
    rng.shuffle(ordered)
    return ordered[:n]


@dataclass
class SampledFile:
    file_id: str            # REAL store's file_id (Before) — After gets a fresh one
    current_path: str
    original_name: str
    group: str               # "unknown_sample" | "image_control" | "application_control"
    before: dict              # structural snapshot from the real store


def build_dataset(unknown_target: int = 25, image_n: int = 10, application_n: int = 10,
                   seed: int = 42) -> Tuple[List[SampledFile], List[str]]:
    """Reads the REAL store (unisolated paths — call this BEFORE
    _isolate_storage()) and returns the sampled file list plus a list of
    warnings (e.g. a real record's file has since moved/been deleted).

    Filters each candidate pool to files that still exist on disk BEFORE
    sampling, not after — real Downloads folders churn constantly between
    when a file was last scanned and when this validation runs, and
    sampling-then-discarding-missing-files would silently shrink the
    dataset below the requested target instead of backfilling from the
    rest of the (still large) real pool. Records whose file has moved are
    reported as a warning either way — never silently dropped without a
    trace — but they don't consume a sample slot."""
    warnings: List[str] = []
    real_records = database_module.load_metadata_store()

    def _existing_only(records: List, group_name: str) -> List:
        existing = []
        missing_count = 0
        for r in records:
            if Path(r.current_path).exists():
                existing.append(r)
            else:
                missing_count += 1
        if missing_count:
            warnings.append(
                f"{group_name}: {missing_count} real record(s) no longer exist on disk "
                f"(moved/deleted since the last scan) — excluded from the sampling pool, "
                f"not counted against the target."
            )
        return existing

    unknown = _existing_only([r for r in real_records if r.category == Category.UNKNOWN], "unknown_sample")
    images = _existing_only([r for r in real_records if r.category == Category.IMAGE], "image_control")
    apps = _existing_only([r for r in real_records if r.category == Category.APPLICATION], "application_control")

    unknown_sample = _stratified_sample(unknown, unknown_target, seed)
    image_sample = _fixed_sample(images, image_n, seed)
    app_sample = _fixed_sample(apps, application_n, seed)

    if len(unknown_sample) < unknown_target:
        warnings.append(f"unknown_sample: only {len(unknown_sample)}/{unknown_target} available "
                         f"(pool of existing real Unknown records is smaller than the target).")
    if len(image_sample) < image_n:
        warnings.append(f"image_control: only {len(image_sample)}/{image_n} available.")
    if len(app_sample) < application_n:
        warnings.append(f"application_control: only {len(app_sample)}/{application_n} available.")

    sampled: List[SampledFile] = []
    for group_name, group_records in (
        ("unknown_sample", unknown_sample),
        ("image_control", image_sample),
        ("application_control", app_sample),
    ):
        for r in group_records:
            required = REQUIRED_FIELDS.get(r.category, ())
            populated = sum(1 for f in required if r.extracted_metadata.get(f) not in (None, ""))
            sampled.append(SampledFile(
                file_id=r.file_id,
                current_path=r.current_path,
                original_name=r.original_name,
                group=group_name,
                before={
                    "category": r.category.value if r.category else None,
                    "tier": r.tier,
                    "confidence_score": r.confidence_score,
                    "confidence_breakdown": r.confidence_breakdown,
                    "required_fields_total": len(required),
                    "required_fields_populated": populated,
                    "naming_fell_back": bool(r.naming_signals.fields_fell_back) if r.naming_signals else None,
                },
            ))
    return sampled, warnings


# --- Cost estimate (§1.3) ---

def estimate_cost(sampled: List[SampledFile], named_case_count: int) -> Tuple[float, float, int]:
    """Returns (low_estimate_usd, high_estimate_usd, eligible_call_count).
    Deliberately a wide, honest range, not false precision — vision-mode
    image token costs vary with resolution in ways this estimate doesn't
    model exactly; §1.3 requires a range be shown, not a single number
    trusted as exact."""
    prices = _PRICE_PER_MILLION_TOKENS_USD["claude-sonnet-5"]
    calls = 0
    for s in sampled:
        before_category = s.before["category"]
        if s.group == "unknown_sample":
            calls += 2  # classify + (if resolved) extract
        elif s.group == "image_control":
            calls += 1  # extract only (classification is deterministic for Image)
        # application_control: 0 — fully deterministic both stages
    calls += named_case_count * 2  # classify + extract, worst case

    # Low: short text prompts, ~600 input + ~150 output tokens per call.
    # High: vision-mode worst case, ~2000 input (image) + 512 output (cap) tokens per call.
    low = calls * (600 / 1_000_000 * prices["input"] + 150 / 1_000_000 * prices["output"])
    high = calls * (2000 / 1_000_000 * prices["input"] + 512 / 1_000_000 * prices["output"])
    return low, high, calls


# --- Pipeline execution helpers ---

def _run_full_chain(records: List, provider_key: Optional[str]) -> None:
    """Runs the exact production chain, in the exact production order
    (mirrors src/main.py's own bottom-of-file chain and run_harness.py's
    run_provider()). `provider_key=None` means "use the shipped default"
    (ClaudeLiveClassifier/ClaudeLiveExtractor — safe, deterministic-only
    fallback when not in a live session, exactly today's behavior).
    `provider_key="claude"` resolves the real, registered TD-01 v0.9
    provider via the registry — the same shipped code path `provider
    enable` turns on for real use, called here directly (bypassing
    sources.yaml) so this isolated run never depends on that file's state."""
    classification_provider = resolve_classification_provider(provider_key) if provider_key else None
    extraction_provider = resolve_extraction_provider(provider_key) if provider_key else None
    classify_batch(records, provider=classification_provider)
    extract_metadata_batch(records, provider=extraction_provider)
    detect_duplicates_batch(records)
    suggest_naming_and_destination_batch(records)
    score_confidence_batch(records)


def _read_log_for_batch(batch_id: str) -> List[dict]:
    return [e for e in runtime_io_module.read_action_log_entries() if e.get("batch_id") == batch_id]


def _extract_token_usages_and_rate_limits(
    entries: List[dict],
) -> Tuple[List[dict], List[str], Optional[str], List[str]]:
    """Same extraction run_harness.py's run_provider() does, plus the
    per-file fallback diagnostic run_harness.py already has via
    per_file_failures — this script was missing that diagnostic (found
    during TD-01 results.json review 2026-07-26: with every sampled/named
    record falling back, this gap made it impossible to tell a code defect
    apart from "no key in this process's environment" apart from expected
    behavior without inference from aggregate zeros alone). Returns
    (token_usages, rate_limited_file_ids, model_used, fallback_details) —
    fallback_details entries are formatted identically to run_harness.py's
    per_file_failures: "{file_id}: {fallback_reason} — {error_detail}"."""
    token_usages: List[dict] = []
    rate_limited_file_ids: List[str] = []
    model_used: Optional[str] = None
    fallback_details: List[str] = []
    for entry in entries:
        details = entry.get("details") or {}
        provider_metadata = details.get("provider_metadata")
        if provider_metadata:
            if provider_metadata.get("token_usage"):
                token_usages.append(provider_metadata["token_usage"])
            model_used = provider_metadata.get("model") or model_used
        if entry.get("action") in ("classify", "extract_metadata") and details.get("fallback_used"):
            error_detail = str(details.get("error_detail") or "")
            if "ratelimit" in error_detail.lower().replace("_", "").replace(" ", ""):
                rate_limited_file_ids.append(entry.get("file_id"))
            fallback_details.append(
                f"{entry.get('file_id')}: {details.get('fallback_reason')} — {details.get('error_detail')}"
            )
    return token_usages, rate_limited_file_ids, model_used, fallback_details


def _estimate_actual_cost(model: Optional[str], token_usages: List[dict]) -> Optional[float]:
    if not token_usages:
        return None
    prices = _PRICE_PER_MILLION_TOKENS_USD.get(model)
    if prices is None:
        return None
    total = 0.0
    for usage in token_usages:
        total += usage.get("input_tokens", 0) / 1_000_000 * prices["input"]
        total += usage.get("output_tokens", 0) / 1_000_000 * prices["output"]
    return total


# --- Main orchestration ---

def run(unknown_target: int, image_n: int, application_n: int, seed: int,
        named_cases: List[Tuple[str, str]], skip_confirmation: bool) -> dict:
    run_started_at = datetime.now(timezone.utc).isoformat()

    # 0. Startup diagnostic (added 2026-07-26, TD-01 results.json review):
    # confirms, unambiguously and before any isolation or sampling work
    # happens, whether ANTHROPIC_API_KEY is visible to THIS process's
    # environment — never prints the key itself, only whether it's set and
    # non-empty. This exists because a prior real run produced results
    # consistent with zero real provider calls succeeding (see
    # provider_fallback_details in the output), and there was no direct way
    # to confirm from the output alone whether that was a missing key in
    # this specific process vs. a pipeline defect. `provider enable`/
    # `provider status` check the key in their own process; this script
    # runs as a separate process and must not assume that check still holds.
    key_present = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"ANTHROPIC_API_KEY present in this process's environment: {key_present}")
    if not key_present:
        print("WARNING: no key detected in this process. Every classify/extract call below "
              "will fall back to deterministic-only processing — Before and After will be "
              "identical, and this run will produce no evidence about real provider quality. "
              "If you already ran 'provider enable' successfully, confirm you're running this "
              "script in that SAME terminal session (the key does not persist across terminal "
              "windows/tabs).")

    # 1. Build the dataset from the REAL store — must happen before isolation.
    sampled, warnings = build_dataset(unknown_target, image_n, application_n, seed)
    if warnings:
        print("Dataset warnings:")
        for w in warnings:
            print(f"  - {w}")

    named_case_records = []
    for path_str, label in named_cases:
        p = Path(path_str)
        if not p.exists():
            warnings.append(f"named case {label!r}: file not found at {path_str!r} — skipped. "
                             f"Use --extra-file to point at its current location.")
            continue
        named_case_records.append((p, label))

    print(f"\nDataset: {len(sampled)} sampled real records "
          f"({sum(1 for s in sampled if s.group == 'unknown_sample')} unknown, "
          f"{sum(1 for s in sampled if s.group == 'image_control')} image-control, "
          f"{sum(1 for s in sampled if s.group == 'application_control')} application-control) "
          f"+ {len(named_case_records)} named difficult case(s).")

    # 2. Cost estimate + mandatory confirmation gate (§1.3).
    low, high, calls = estimate_cost(sampled, len(named_case_records))
    print(f"\nEstimated provider-eligible calls: {calls}")
    print(f"Estimated cost range: ${low:.2f} – ${high:.2f} (claude-sonnet-5 pricing)")
    print("This will make real, metered API calls to Anthropic if ANTHROPIC_API_KEY "
          "is set to a real, working key.")
    if not skip_confirmation:
        response = input("Proceed with real provider calls? [y/n]: ").strip().lower()
        if response != "y":
            print("Aborted. No API call was made.")
            return {"aborted": True}

    with tempfile.TemporaryDirectory(prefix="td01_production_validation_") as tmp:
        tmp_path = Path(tmp)
        original_storage = _isolate_storage(tmp_path)
        try:
            # 3a. Named cases — Before (no provider, safe fallback) then After (claude).
            named_case_results = []
            named_case_fallback_details: List[str] = []
            for p, label in named_case_records:
                before_batch = f"prodval_named_before_{int(time.time())}_{p.stem[:8]}"
                before_record, _ = build_file_record(p, source_id="production_validation", batch_id=before_batch)
                database_module.save_file_record(before_record)
                _run_full_chain([before_record], provider_key=None)
                before_snapshot = {
                    "category": before_record.category.value if before_record.category else None,
                    "tier": before_record.tier,
                }

                after_batch = f"prodval_named_after_{int(time.time())}_{p.stem[:8]}"
                after_record, _ = build_file_record(p, source_id="production_validation", batch_id=after_batch)
                database_module.save_file_record(after_record)
                _run_full_chain([after_record], provider_key="claude")
                after_snapshot = {
                    "category": after_record.category.value if after_record.category else None,
                    "tier": after_record.tier,
                    "confidence_score": after_record.confidence_score,
                }
                named_case_results.append({
                    "label": label,
                    "before": before_snapshot,
                    "after": after_snapshot,
                })
                # Only the After batch used the real provider — Before is the
                # intentional no-provider fallback, not a diagnostic signal.
                _, _, _, after_fallbacks = _extract_token_usages_and_rate_limits(
                    _read_log_for_batch(after_batch)
                )
                named_case_fallback_details.extend(after_fallbacks)

            # 3b. Sampled real records — After only (Before already read from real store).
            after_batch_id = f"prodval_sample_after_{int(time.time())}"
            isolated_records = []
            path_to_sample: Dict[str, SampledFile] = {}
            for s in sampled:
                record, _ = build_file_record(Path(s.current_path), source_id="production_validation",
                                               batch_id=after_batch_id)
                database_module.save_file_record(record)
                isolated_records.append(record)
                path_to_sample[s.current_path] = s

            run_start = time.time()
            _run_full_chain(isolated_records, provider_key="claude")
            run_elapsed = time.time() - run_start

            entries = _read_log_for_batch(after_batch_id)
            token_usages, rate_limited_ids, model_used, sample_fallback_details = (
                _extract_token_usages_and_rate_limits(entries)
            )
            actual_cost = _estimate_actual_cost(model_used, token_usages)
            provider_fallback_details = named_case_fallback_details + sample_fallback_details

            after_results = []
            for record in isolated_records:
                s = path_to_sample[record.current_path]
                required = REQUIRED_FIELDS.get(record.category, ()) if record.category else ()
                populated = sum(1 for f in required if record.extracted_metadata.get(f) not in (None, ""))
                after_results.append({
                    "before_file_id": s.file_id,
                    "group": s.group,
                    "before": s.before,
                    "after": {
                        "category": record.category.value if record.category else None,
                        "tier": record.tier,
                        "confidence_score": record.confidence_score,
                        "confidence_breakdown": record.confidence_breakdown,
                        "required_fields_total": len(required),
                        "required_fields_populated": populated,
                        "naming_fell_back": bool(record.naming_signals.fields_fell_back) if record.naming_signals else None,
                    },
                    "rate_limited": record.file_id in rate_limited_ids,
                })

        finally:
            _restore_storage(original_storage)

    result = {
        "run_started_at": run_started_at,
        "run_finished_at": datetime.now(timezone.utc).isoformat(),
        "anthropic_api_key_present_at_start": key_present,
        "dataset_warnings": warnings,
        "estimated_cost_range_usd": {"low": low, "high": high},
        "actual_cost_usd": actual_cost,
        "priced_model": model_used,
        "processing_time_seconds": run_elapsed,
        "files_per_second": (len(isolated_records) / run_elapsed) if run_elapsed > 0 else None,
        "token_usage_totals": {
            "input_tokens": sum(u.get("input_tokens", 0) for u in token_usages),
            "output_tokens": sum(u.get("output_tokens", 0) for u in token_usages),
        },
        "rate_limited_file_count": len(rate_limited_ids),
        # Diagnostic gap fix (2026-07-26): mirrors run_harness.py's existing
        # per_file_failures. Covers the sampled-batch After calls and every
        # named case's After call (the Before calls intentionally use no
        # provider, so their fallbacks are expected and excluded here).
        "provider_fallback_details": provider_fallback_details,
        "sample_results": after_results,
        "named_case_results": named_case_results,
    }
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unknown-target", type=int, default=25)
    parser.add_argument("--image-n", type=int, default=10)
    parser.add_argument("--application-n", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--extra-file", action="append", default=[],
                         help='Additional real file to process as a named difficult case, '
                              'formatted "path::label". Repeatable.')
    parser.add_argument("-y", "--yes", action="store_true", help="Skip the cost-confirmation prompt.")
    args = parser.parse_args(argv)

    named_cases = list(_DEFAULT_NAMED_CASES)
    for spec in args.extra_file:
        if "::" not in spec:
            print(f"Ignoring malformed --extra-file (expected path::label): {spec!r}")
            continue
        path_str, label = spec.split("::", 1)
        named_cases.append((path_str, label))

    result = run(args.unknown_target, args.image_n, args.application_n, args.seed,
                 named_cases, args.yes)

    if result.get("aborted"):
        return 0

    out_dir = _PROJECT_ROOT / "Runtime" / "Validation" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "results.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\nDone. Results written to: {out_path}")
    print(f"ANTHROPIC_API_KEY was present at start: {result['anthropic_api_key_present_at_start']}")
    print(f"Actual cost: ${result['actual_cost_usd']:.4f}" if result["actual_cost_usd"] is not None else "Actual cost: n/a")
    print(f"Rate-limited files: {result['rate_limited_file_count']}")
    print(f"Processing time: {result['processing_time_seconds']:.1f}s "
          f"({result['files_per_second']:.2f} files/sec)" if result["files_per_second"] else "")
    if result.get("provider_fallback_details"):
        print(f"\n{len(result['provider_fallback_details'])} provider fallback(s) occurred "
              f"(deterministic-only result used instead of a real provider judgment):")
        for line in result["provider_fallback_details"][:10]:
            print(f"  - {line}")
        if len(result["provider_fallback_details"]) > 10:
            print(f"  ... and {len(result['provider_fallback_details']) - 10} more (see results.json).")
    print("\nSend the contents of results.json back for the final report — it contains "
          "structural facts only (categories, tiers, scores, field-presence counts, token "
          "counts), never raw file content, per DATASET_GUIDELINES.md.")
    print("\nNext: run 'python3 -m src.cli provider disable' and "
          "'python3 -m src.cli provider status' to complete the rollback verification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
