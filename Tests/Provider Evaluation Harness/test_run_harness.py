"""
Tests for run_harness.py (TD-01 v0.9's Provider Evaluation Harness) — see
that file's own module docstring for what this tool is and its isolation
guarantees.

Colocated with run_harness.py in this same Tests/ subfolder rather than
under src/ (src/README.md's "colocated test_*.py, not a generic tests/
folder" convention applies to src/'s own unit tests; run_harness.py itself
is an operator-invoked QA tool that lives under Tests/ by design, not
production src/ code, so its test lives next to it). NOT part of the
standard `pytest src/` regression suite for that same reason — run this file
directly:

    pytest "Tests/Provider Evaluation Harness/test_run_harness.py" -v

Every test here uses a fake, in-process, zero-cost, zero-network "test-stub"
provider registered temporarily under its own registry key — never the real
"claude" provider — so this file never makes a network call and never
depends on ANTHROPIC_API_KEY being set. This is exactly the "fake/stub
provider" run_harness.py's own module docstring already promises this file
would use.

Run with: pytest "Tests/Provider Evaluation Harness/test_run_harness.py" -v
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HARNESS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _HARNESS_DIR.parents[1]

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import src.providers.registry as registry_module  # noqa: E402
from src.pipeline.classification import ClassificationProvider  # noqa: E402
from src.pipeline.classification import ClassificationResult  # noqa: E402
from src.pipeline.classification import ProviderMetadata as ClassificationProviderMetadata  # noqa: E402
from src.pipeline.classification import ProviderResponse as ClassificationProviderResponse  # noqa: E402
from src.pipeline.metadata import MetadataExtractionProvider  # noqa: E402
from src.pipeline.metadata import ProviderMetadata as ExtractionProviderMetadata  # noqa: E402
from src.pipeline.metadata import ProviderResponse as ExtractionProviderResponse  # noqa: E402


def _load_run_harness_module():
    """run_harness.py can't be imported with a normal `import` statement —
    its directory name has spaces and is not a package (deliberately: it
    lives under Tests/, not src/, per this project's own colocation
    convention — see this file's module docstring). Loaded once per test
    session via importlib against its real file path instead."""
    spec = importlib.util.spec_from_file_location(
        "provider_evaluation_run_harness", _HARNESS_DIR / "run_harness.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def harness_module():
    return _load_run_harness_module()


@pytest.fixture(autouse=True)
def _clean_registry():
    """Snapshots/restores the registry around every test — mirrors
    src/providers/test_registry.py's own fixture exactly, since this file
    also registers (and must un-register) a temporary provider key."""
    saved_classification = dict(registry_module._CLASSIFICATION_PROVIDERS)
    saved_extraction = dict(registry_module._EXTRACTION_PROVIDERS)
    yield
    registry_module._CLASSIFICATION_PROVIDERS.clear()
    registry_module._CLASSIFICATION_PROVIDERS.update(saved_classification)
    registry_module._EXTRACTION_PROVIDERS.clear()
    registry_module._EXTRACTION_PROVIDERS.update(saved_extraction)


# --- A perfect-oracle fake provider: answers every fixture with exactly the
# ground truth from expected_answers.json, looked up by filename (the only
# thing ClassificationRequest.path/MetadataExtractionRequest.path reliably
# gives us — see run_harness.py's own accuracy-definition docstring for why
# this is legitimate). Used to prove the harness's own arithmetic (accuracy,
# unknown rate, tier counts, cost estimation) is correct, not to test
# classification quality itself (that's Module 02/03's own test suites'
# job). ---


def _load_expected():
    return json.loads((_HARNESS_DIR / "expected_answers.json").read_text(encoding="utf-8"))


class _OracleClassifier(ClassificationProvider):
    def classify(self, request):
        expected = _load_expected()
        filename = Path(request.path).name
        category = expected[filename]["category"]
        return ClassificationProviderResponse(
            result=ClassificationResult(category=category),
            metadata=ClassificationProviderMetadata(provider_name="test-stub", model="test-model"),
        )


class _OracleExtractor(MetadataExtractionProvider):
    def extract(self, request):
        # Confidently answers every requested field with a non-null
        # placeholder — this harness's naming_quality metric only cares
        # whether a field fell back to null, not whether the value is
        # realistic, so a fixed placeholder is sufficient and keeps this
        # fake deterministic.
        fields = {name: "test-value" for name in request.fields_requested}
        return ExtractionProviderResponse(
            fields=fields,
            metadata=ExtractionProviderMetadata(provider_name="test-stub", model="test-model"),
        )


def _register_oracle_provider():
    registry_module.register_classification_provider("test-stub", _OracleClassifier)
    registry_module.register_extraction_provider("test-stub", _OracleExtractor)


# --- _estimate_cost() -----------------------------------------------------


def test_estimate_cost_returns_none_for_empty_usage_list(harness_module):
    assert harness_module._estimate_cost("claude-sonnet-5", []) is None


def test_estimate_cost_returns_none_for_unpriced_model(harness_module):
    """None must mean "no price on file for this model", not "free" — a
    real cost of $0 (a provider that genuinely used zero tokens) is a
    different, valid answer this function must not conflate with this
    case."""
    usages = [{"input_tokens": 100, "output_tokens": 50}]
    assert harness_module._estimate_cost("some-unlisted-model", usages) is None
    assert harness_module._estimate_cost(None, usages) is None


def test_estimate_cost_computes_correct_total(harness_module):
    usages = [
        {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
        {"input_tokens": 500_000, "output_tokens": 0},
    ]
    # claude-sonnet-5: $3.00/M input, $15.00/M output (harness's own table)
    expected = (1_000_000 / 1_000_000 * 3.00) + (1_000_000 / 1_000_000 * 15.00) + (500_000 / 1_000_000 * 3.00)
    result = harness_module._estimate_cost("claude-sonnet-5", usages)
    assert result == pytest.approx(expected)


def test_estimate_cost_handles_missing_token_keys_as_zero(harness_module):
    usages = [{}]  # a provider that reported usage but omitted a key
    assert harness_module._estimate_cost("claude-sonnet-5", usages) == 0.0


# --- run_provider() with the oracle fake ----------------------------------


def test_run_provider_oracle_achieves_five_of_six_not_perfect_accuracy(harness_module):
    """A perfect-oracle classifier still does NOT reach 100% — proven here,
    not assumed. Image/Screenshot classification is fully deterministic
    (the filename/resolution split in core/images.py, run before any
    provider is ever consulted for that family — see run_harness.py's own
    module docstring), so the oracle is never even asked about
    b3f0a1c2-....jpg's category; it's decided purely by that deterministic
    split, which the fixture was deliberately built to defeat (mirrors the
    real C2 Finding 2 screenshot-misclassification trade-off). The other 5
    fixtures (the 2 deterministic-by-extension ones, the correctly-Unknown
    one, the correctly-classified legal PDF, and photo.jpg, which the
    deterministic split does get right) all resolve correctly, so exactly
    5/6 — this is the harness correctly reporting a real, already-known
    product limitation, not a harness bug."""
    _register_oracle_provider()
    metrics = harness_module.run_provider("test-stub")

    expected = _load_expected()
    assert metrics.total_fixtures == len(expected)
    assert metrics.accuracy == pytest.approx(5 / 6)


def test_run_provider_oracle_unknown_rate_matches_expected_unknown_count(harness_module):
    _register_oracle_provider()
    metrics = harness_module.run_provider("test-stub")

    expected = _load_expected()
    expected_unknown_count = sum(
        1 for entry in expected.values() if entry["category"] == "Unknown"
    )
    assert metrics.unknown_rate == pytest.approx(expected_unknown_count / len(expected))


def test_run_provider_oracle_tier_counts_sum_to_total_fixtures(harness_module):
    _register_oracle_provider()
    metrics = harness_module.run_provider("test-stub")

    assert sum(metrics.tier_counts.values()) == metrics.total_fixtures


def test_run_provider_oracle_estimated_cost_is_none_for_unpriced_fake_model(harness_module):
    """The oracle reports model="test-model", which has no entry in the
    harness's pricing table — estimated_cost_usd must come back None, not
    a silently-wrong $0.00."""
    _register_oracle_provider()
    metrics = harness_module.run_provider("test-stub")
    assert metrics.estimated_cost_usd is None
    assert metrics.priced_model == "test-model"


def test_run_provider_oracle_has_no_per_file_failures(harness_module):
    """The oracle never raises and is never unavailable — a clean run
    should log zero fallback_used=True entries for it."""
    _register_oracle_provider()
    metrics = harness_module.run_provider("test-stub")
    assert metrics.per_file_failures == []


def test_run_provider_reports_mean_latency_even_for_a_fake_provider(harness_module):
    """latency_ms is measured by the Engine wrapping the call (design's own
    "provider-agnostic" note), not self-reported — so even a fake,
    effectively-instant provider must produce a real (small, non-None)
    mean_latency_ms."""
    _register_oracle_provider()
    metrics = harness_module.run_provider("test-stub")
    assert metrics.mean_latency_ms is not None
    assert metrics.mean_latency_ms >= 0


def test_run_provider_raises_clear_error_if_fixture_missing_from_disk(harness_module, monkeypatch, tmp_path):
    """expected_answers.json driving fixture selection (not a directory
    listing) is deliberate — see run_harness.py's own module docstring for
    why the two stray undeletable files in fixtures/ are harmless. This
    test proves the inverse failure mode (an answers-file entry with no
    matching file) fails loudly instead of silently skipping a fixture."""
    _register_oracle_provider()
    monkeypatch.setattr(
        harness_module, "_load_expected",
        lambda: {"does-not-exist.pdf": {"category": "Document", "notes": ""}},
    )
    with pytest.raises(FileNotFoundError):
        harness_module.run_provider("test-stub")


# --- run_provider() isolation ---------------------------------------------


def test_run_provider_does_not_touch_real_database_or_runtime(harness_module):
    """The harness's own isolation guarantee (module docstring: "never
    touches the real project's Database/Runtime") — checked two ways: (1)
    the module-level path constants are restored to their exact pre-call
    values afterward (run_provider()'s try/finally around _isolate_storage()
    / _restore_storage()), and (2) the real project's actual metadata file on
    disk is untouched."""
    import src.storage.database as database_module
    import src.storage.runtime_io as runtime_io_module

    original_metadata_path = database_module._METADATA_STORE_PATH
    original_action_log_path = runtime_io_module._ACTION_LOG_PATH
    real_metadata_bytes_before = (
        original_metadata_path.read_bytes() if original_metadata_path.exists() else None
    )

    _register_oracle_provider()
    harness_module.run_provider("test-stub")

    assert database_module._METADATA_STORE_PATH == original_metadata_path
    assert runtime_io_module._ACTION_LOG_PATH == original_action_log_path
    real_metadata_bytes_after = (
        original_metadata_path.read_bytes() if original_metadata_path.exists() else None
    )
    assert real_metadata_bytes_after == real_metadata_bytes_before


def test_run_provider_restores_storage_paths_even_when_a_fixture_is_missing(harness_module, monkeypatch):
    """The try/finally around _isolate_storage()/_restore_storage() must
    restore real state even on the error path (a mid-run FileNotFoundError),
    not just the success path — otherwise a single bad harness run would
    permanently corrupt process state for whatever runs next in the same
    process (exactly the defect this fix addresses)."""
    import src.storage.database as database_module

    original_metadata_path = database_module._METADATA_STORE_PATH
    _register_oracle_provider()
    monkeypatch.setattr(
        harness_module, "_load_expected",
        lambda: {"does-not-exist.pdf": {"category": "Document", "notes": ""}},
    )

    with pytest.raises(FileNotFoundError):
        harness_module.run_provider("test-stub")

    assert database_module._METADATA_STORE_PATH == original_metadata_path


# --- main() ------------------------------------------------------------


def test_main_dash_y_skips_confirmation_prompt(harness_module, monkeypatch, capsys):
    _register_oracle_provider()
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(
        AssertionError("input() must not be called when -y is passed")
    ))
    exit_code = harness_module.main(["--providers", "test-stub", "-y"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "test-stub" in captured.out


def test_main_declined_confirmation_runs_nothing(harness_module, monkeypatch, capsys):
    _register_oracle_provider()
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    called = []
    monkeypatch.setattr(harness_module, "run_provider", lambda key: called.append(key))

    exit_code = harness_module.main(["--providers", "test-stub"])

    assert exit_code == 0
    assert called == []
    captured = capsys.readouterr()
    assert "Aborted" in captured.out


def test_main_confirmed_runs_and_prints_report_table(harness_module, monkeypatch, capsys):
    _register_oracle_provider()
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    exit_code = harness_module.main(["--providers", "test-stub"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "provider" in captured.out and "accuracy" in captured.out


def test_main_no_registered_providers_exits_cleanly(harness_module, monkeypatch, capsys):
    monkeypatch.setattr(harness_module, "registered_classification_providers", lambda: [])
    monkeypatch.setattr(harness_module, "registered_extraction_providers", lambda: [])

    exit_code = harness_module.main([])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "nothing to benchmark" in captured.out.lower()


def test_main_defaults_to_every_registered_provider_when_flag_omitted(harness_module, monkeypatch):
    _register_oracle_provider()
    received = []
    monkeypatch.setattr(harness_module, "run_provider", lambda key: received.append(key) or _DummyMetrics(key))
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    harness_module.main([])

    assert "test-stub" in received


class _DummyMetrics:
    """Minimal stand-in for ProviderMetrics — just enough attribute access
    for _print_report() to not crash when main()'s own run_provider() call
    is mocked out in the test above."""

    def __init__(self, provider_key):
        self.provider_key = provider_key
        self.accuracy = 1.0
        self.unknown_rate = 0.0
        self.naming_quality = 1.0
        self.tier_counts = {}
        self.mean_latency_ms = None
        self.estimated_cost_usd = None
        self.per_file_failures = []
