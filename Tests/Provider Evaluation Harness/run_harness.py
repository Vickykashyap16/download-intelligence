"""
Provider Evaluation Harness (TD-01 v0.9). Design:
"Build-out/02 Classification/TD-01 Provider Architecture — Design Package.md"
§6.

Standalone, operator-invoked benchmarking tool — never called by `scan`/`run`/
`preview`/`execute`, never runs automatically. Runs every requested
registered provider (`src.providers.registry`) against the same fixed,
hand-labeled fixture set (`fixtures/` + `expected_answers.json`, both in this
same directory) inside a fully isolated, temporary Database/Runtime — the
same isolation discipline the C2 Sandbox Product Validation used (see
"Tests/C2 Sandbox Product Validation Report.md") — and reports six
comparable metrics per provider: accuracy, Unknown %, naming quality, the
resulting confidence-tier distribution, latency, and estimated cost.

Never touches the real project's Database/Runtime. Never runs automatically
as part of any test suite (`pytest`) — see `test_run_harness.py` (same
folder) for the version of this that runs in CI, against a fake/stub
provider instead of a real network call.

Usage:
    python3 "Tests/Provider Evaluation Harness/run_harness.py" [--providers claude,...] [-y]

Accuracy definition (deliberately not "did the provider get it right" for
every fixture): two of these six fixtures (archive.zip, MyApp_1.2.3_Mac.dmg)
are resolved deterministically before any provider is ever called (Module 02
Pass 1), and Image/Screenshot classification is also fully deterministic
(the filename/resolution split in core/images.py) — a provider is never
consulted for the category of an image-family file at all, only for its
extraction fields. Accuracy here measures the file's *final* category after
the full pipeline runs under each provider, which is what actually reaches a
user — the same framing the C2 Retrospective's Unknown % metric used — not a
literal "provider was asked and answered correctly" count. This means two
providers can legitimately post identical accuracy on the deterministic and
image-family fixtures while differing only on the two genuinely
judgment-dependent ones (legal_form.pdf, ambiguous_note.txt).
"""

import argparse
import json
import statistics
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_HARNESS_DIR = Path(__file__).resolve().parent
_FIXTURES_DIR = _HARNESS_DIR / "fixtures"
_EXPECTED_ANSWERS_PATH = _HARNESS_DIR / "expected_answers.json"
_PROJECT_ROOT = _HARNESS_DIR.parents[1]  # .../Tests/Provider Evaluation Harness -> Tests -> project root

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import src.storage.database as database_module  # noqa: E402
import src.storage.runtime_io as runtime_io_module  # noqa: E402
from src.pipeline.classification import classify_batch  # noqa: E402
from src.pipeline.confidence import score_confidence_batch  # noqa: E402
from src.pipeline.duplicate_detector import detect_duplicates_batch  # noqa: E402
from src.pipeline.metadata import extract_metadata_batch  # noqa: E402
from src.pipeline.naming import suggest_naming_and_destination_batch  # noqa: E402
from src.pipeline.watch_ingest import build_file_record  # noqa: E402
from src.providers.registry import (  # noqa: E402
    registered_classification_providers,
    registered_extraction_providers,
    resolve_classification_provider,
    resolve_extraction_provider,
)

# Side-effect import — registers "claude" (see src/providers/claude.py's own
# docstring, and src/main.py's identical import for why this needs to happen
# explicitly wherever the registry is consulted).
import src.providers.claude  # noqa: E402,F401

# A small, harness-owned, approximate pricing table (design §6: "kept in the
# harness, not in the frozen provider contracts, since pricing changes
# independently of the architecture"). Update here, never in
# src/providers/claude.py, if pricing changes. USD per million tokens.
_PRICE_PER_MILLION_TOKENS_USD = {
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
}


def _isolate_storage(tmp_path: Path) -> None:
    """Redirects every Database/Runtime path constant this harness's pipeline
    calls touch to `tmp_path` — mirrors `src/test_main.py`'s own
    `_isolate_storage()`/`_isolate_execution_storage()` helpers exactly, so
    a harness run can never write to the real project's `Database/`/
    `Runtime/`.

    Returns the original values as a dict, so `run_provider()` can restore
    them afterward (`_restore_storage()` below) — unlike the test suite's
    own version of this helper, this one has no pytest `monkeypatch` fixture
    to auto-undo the reassignment for it. Without an explicit restore, this
    is a standalone-script permanent mutation of shared module state that's
    harmless for a one-shot `python3 run_harness.py` process (the process
    exits right after), but corrupts state for any longer-lived process that
    imports this module directly — e.g. this file's own
    `test_run_harness.py`, which loads it once per test session and calls
    `run_provider()` many times in the same process."""
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
    """Undoes `_isolate_storage()` — see that function's docstring for why
    this explicit restore exists."""
    database_module._METADATA_STORE_PATH = original["metadata_store_path"]
    database_module._HASH_INDEX_PATH = original["hash_index_path"]
    database_module._PHASH_INDEX_PATH = original["phash_index_path"]
    database_module._NAME_INDEX_PATH = original["name_index_path"]
    database_module._VERSION_HISTORY_PATH = original["version_history_path"]
    database_module._USER_CORRECTIONS_PATH = original["user_corrections_path"]
    runtime_io_module._ACTION_LOG_PATH = original["action_log_path"]


def _load_expected() -> Dict[str, dict]:
    return json.loads(_EXPECTED_ANSWERS_PATH.read_text(encoding="utf-8"))


def _estimate_cost(model: Optional[str], token_usages: List[dict]) -> Optional[float]:
    """None means "unknown/unpriced", not "free" — `0.0` is a real,
    meaningful answer (a provider that reported zero token usage); `None`
    means this table doesn't have a price for the model that was actually
    used, which the report must not silently show as $0."""
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


@dataclass
class ProviderMetrics:
    provider_key: str
    total_fixtures: int
    accuracy: float
    unknown_rate: float
    naming_quality: float
    tier_counts: Dict[str, int] = field(default_factory=dict)
    mean_latency_ms: Optional[float] = None
    estimated_cost_usd: Optional[float] = None
    priced_model: Optional[str] = None
    per_file_failures: List[str] = field(default_factory=list)


def run_provider(provider_key: str) -> ProviderMetrics:
    """Runs the full Module 01(-equivalent)->06 chain for `provider_key`
    against every harness fixture, in a fresh isolated Database/Runtime, and
    computes this provider's six metrics.

    Deliberately does not wrap the provider resolution/calls in a
    try/except at this level: `classify_batch()`/`extract_metadata_batch()`
    already catch every provider failure internally (a missing API key, a
    network error, an unparseable response) and fall back to
    Category.UNKNOWN/null fields per file, exactly the same contract every
    other caller of these functions relies on (see
    `src/pipeline/classification.py`'s `ClassificationEngine`) — so a
    provider with no working API key still produces a complete, honest
    report here (100% Unknown, 0% accuracy on the two judgment-dependent
    fixtures), not a crash.
    """
    expected = _load_expected()
    batch_id = f"harness_{provider_key}_{int(time.time())}"

    with tempfile.TemporaryDirectory(prefix="provider_harness_") as tmp:
        tmp_path = Path(tmp)
        original_storage = _isolate_storage(tmp_path)
        try:
            records = []
            for fixture_name in sorted(expected):
                fixture_path = _FIXTURES_DIR / fixture_name
                if not fixture_path.exists():
                    raise FileNotFoundError(
                        f"expected_answers.json names {fixture_name!r} but no such "
                        f"file exists in {_FIXTURES_DIR} — fixtures and answers "
                        "have drifted out of sync."
                    )
                record, _content_changed = build_file_record(
                    fixture_path, source_id="provider_harness", batch_id=batch_id
                )
                records.append(record)

            classification_provider = resolve_classification_provider(provider_key)
            extraction_provider = resolve_extraction_provider(provider_key)

            classify_batch(records, provider=classification_provider)
            extract_metadata_batch(records, provider=extraction_provider)
            detect_duplicates_batch(records)
            suggest_naming_and_destination_batch(records)
            score_confidence_batch(records)

            correct = 0
            unknown_count = 0
            naming_clean = 0
            for record in records:
                expected_category = expected[record.original_name]["category"]
                actual_category = record.category.value if record.category else None
                if actual_category == expected_category:
                    correct += 1
                if actual_category == "Unknown":
                    unknown_count += 1
                if record.naming_signals is not None and not record.naming_signals.fields_fell_back:
                    naming_clean += 1

            tier_counts = Counter(record.tier for record in records if record.tier)

            entries = [
                entry for entry in runtime_io_module.read_action_log_entries()
                if entry.get("batch_id") == batch_id
            ]
            latencies: List[int] = []
            token_usages: List[dict] = []
            model_used: Optional[str] = None
            failures: List[str] = []
            for entry in entries:
                details = entry.get("details") or {}
                provider_metadata = details.get("provider_metadata")
                if provider_metadata:
                    if provider_metadata.get("latency_ms") is not None:
                        latencies.append(provider_metadata["latency_ms"])
                    if provider_metadata.get("token_usage"):
                        token_usages.append(provider_metadata["token_usage"])
                    model_used = provider_metadata.get("model") or model_used
                if entry.get("action") in ("classify", "extract_metadata") and details.get("fallback_used"):
                    failures.append(
                        f"{entry.get('file_id')}: {details.get('fallback_reason')} "
                        f"— {details.get('error_detail')}"
                    )

            total = len(records)
            return ProviderMetrics(
                provider_key=provider_key,
                total_fixtures=total,
                accuracy=correct / total if total else 0.0,
                unknown_rate=unknown_count / total if total else 0.0,
                naming_quality=naming_clean / total if total else 0.0,
                tier_counts=dict(tier_counts),
                mean_latency_ms=statistics.mean(latencies) if latencies else None,
                estimated_cost_usd=_estimate_cost(model_used, token_usages),
                priced_model=model_used,
                per_file_failures=failures,
            )
        finally:
            _restore_storage(original_storage)


def _print_report(results: List[ProviderMetrics]) -> None:
    print("\nProvider Evaluation Harness — results\n")
    header = f"{'provider':<12}{'accuracy':>10}{'unknown%':>10}{'naming%':>10}{'auto':>6}{'appr':>6}{'rev':>6}{'lat(ms)':>10}{'est.$':>10}"
    print(header)
    print("-" * len(header))
    for result in results:
        latency = f"{result.mean_latency_ms:.0f}" if result.mean_latency_ms is not None else "n/a"
        cost = f"{result.estimated_cost_usd:.4f}" if result.estimated_cost_usd is not None else "n/a"
        print(
            f"{result.provider_key:<12}"
            f"{result.accuracy * 100:>9.1f}%"
            f"{result.unknown_rate * 100:>9.1f}%"
            f"{result.naming_quality * 100:>9.1f}%"
            f"{result.tier_counts.get('auto', 0):>6}"
            f"{result.tier_counts.get('approval_required', 0):>6}"
            f"{result.tier_counts.get('review_required', 0):>6}"
            f"{latency:>10}"
            f"{cost:>10}"
        )
    print()
    for result in results:
        if result.per_file_failures:
            print(f"{result.provider_key} — per-file fallbacks:")
            for line in result.per_file_failures:
                print(f"  - {line}")
            print()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark every registered classification/extraction provider "
            "against the same fixed, hand-labeled fixture set. Never touches "
            "the real project's Database/Runtime."
        )
    )
    parser.add_argument(
        "--providers", default=None,
        help="Comma-separated provider keys to benchmark (default: every registered provider).",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true",
        help="Skip the cost-confirmation prompt.",
    )
    args = parser.parse_args(argv)

    available = sorted(set(registered_classification_providers()) | set(registered_extraction_providers()))
    keys = args.providers.split(",") if args.providers else available
    keys = [key.strip() for key in keys if key.strip()]

    if not keys:
        print("No providers registered — nothing to benchmark.")
        return 0

    fixture_count = len(_load_expected())
    print(f"About to benchmark: {keys}")
    print(f"Fixtures: {fixture_count} (in {_FIXTURES_DIR})")
    print(
        "This may make real, metered API calls for any cloud-backed provider "
        "in this list (in v0.9, that's 'claude' only) and will incur real "
        "cost if ANTHROPIC_API_KEY is set to a real, working key. A provider "
        "with no working key still completes cleanly (every fixture falls "
        "back to Category.UNKNOWN/null fields, exactly like an unconfigured "
        "production run) — this is not an error, just an uninformative "
        "benchmark row."
    )
    if not args.yes:
        response = input("Proceed? [y/n]: ").strip().lower()
        if response != "y":
            print("Aborted. Nothing was run.")
            return 0

    results = [run_provider(key) for key in keys]
    _print_report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
