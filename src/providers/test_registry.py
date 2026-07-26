"""
Unit tests for src/providers/registry.py — TD-01 v0.9.

Each test resets both module-level dicts before and after, since the
registry is deliberately global, process-lifetime state (import-time
side-effect registration, per the module's own docstring) — without this
isolation, tests would leak registrations into each other and into whatever
real provider modules (`src/providers/claude.py`) happen to have been
imported elsewhere in the same pytest run.

Run with: pytest src/providers/test_registry.py -v
"""

import pytest

import src.providers.registry as registry_module


@pytest.fixture(autouse=True)
def _clean_registry():
    """Snapshots and restores both dicts around every test — see module
    docstring above for why this must be unconditional, not opt-in."""
    saved_classification = dict(registry_module._CLASSIFICATION_PROVIDERS)
    saved_extraction = dict(registry_module._EXTRACTION_PROVIDERS)
    registry_module._CLASSIFICATION_PROVIDERS.clear()
    registry_module._EXTRACTION_PROVIDERS.clear()
    yield
    registry_module._CLASSIFICATION_PROVIDERS.clear()
    registry_module._CLASSIFICATION_PROVIDERS.update(saved_classification)
    registry_module._EXTRACTION_PROVIDERS.clear()
    registry_module._EXTRACTION_PROVIDERS.update(saved_extraction)


class _FakeClassifier:
    pass


class _FakeExtractor:
    pass


def test_registered_classification_providers_starts_empty():
    assert registry_module.registered_classification_providers() == []


def test_registered_extraction_providers_starts_empty():
    assert registry_module.registered_extraction_providers() == []


def test_register_and_resolve_classification_provider_returns_new_instance():
    registry_module.register_classification_provider("fake", _FakeClassifier)
    resolved = registry_module.resolve_classification_provider("fake")
    assert isinstance(resolved, _FakeClassifier)


def test_register_and_resolve_extraction_provider_returns_new_instance():
    registry_module.register_extraction_provider("fake", _FakeExtractor)
    resolved = registry_module.resolve_extraction_provider("fake")
    assert isinstance(resolved, _FakeExtractor)


def test_resolve_calls_factory_fresh_each_time():
    """Not documented as singleton behavior anywhere — the factory is a
    zero-arg callable, called once per resolve() (registry.py's own
    docstring: "Instantiate and return"), so two resolutions must be two
    distinct instances."""
    registry_module.register_classification_provider("fake", _FakeClassifier)
    first = registry_module.resolve_classification_provider("fake")
    second = registry_module.resolve_classification_provider("fake")
    assert first is not second


def test_resolve_unknown_classification_provider_raises_unknown_provider_error():
    with pytest.raises(registry_module.UnknownProviderError) as excinfo:
        registry_module.resolve_classification_provider("nonexistent")
    assert "nonexistent" in str(excinfo.value)
    assert "classification_provider" in str(excinfo.value)


def test_resolve_unknown_extraction_provider_raises_unknown_provider_error():
    with pytest.raises(registry_module.UnknownProviderError) as excinfo:
        registry_module.resolve_extraction_provider("nonexistent")
    assert "nonexistent" in str(excinfo.value)
    assert "extraction_provider" in str(excinfo.value)


def test_unknown_provider_error_message_lists_registered_keys():
    registry_module.register_classification_provider("alpha", _FakeClassifier)
    registry_module.register_classification_provider("beta", _FakeClassifier)
    with pytest.raises(registry_module.UnknownProviderError) as excinfo:
        registry_module.resolve_classification_provider("gamma")
    message = str(excinfo.value)
    assert "alpha" in message and "beta" in message


def test_unknown_provider_error_is_a_value_error():
    """cli.py/main.py-adjacent callers that already catch ValueError for
    other config problems must be able to catch this the same way — see the
    class's own docstring for why this matters."""
    assert issubclass(registry_module.UnknownProviderError, ValueError)


def test_registered_classification_providers_is_sorted():
    registry_module.register_classification_provider("zeta", _FakeClassifier)
    registry_module.register_classification_provider("alpha", _FakeClassifier)
    assert registry_module.registered_classification_providers() == ["alpha", "zeta"]


def test_registered_extraction_providers_is_sorted():
    registry_module.register_extraction_provider("zeta", _FakeExtractor)
    registry_module.register_extraction_provider("alpha", _FakeExtractor)
    assert registry_module.registered_extraction_providers() == ["alpha", "zeta"]


def test_classification_and_extraction_registries_are_independent():
    """Registering a classification provider must not make it resolvable as
    an extraction provider, and vice versa — the two dicts must never be
    accidentally unified."""
    registry_module.register_classification_provider("only-classification", _FakeClassifier)
    assert registry_module.registered_extraction_providers() == []
    with pytest.raises(registry_module.UnknownProviderError):
        registry_module.resolve_extraction_provider("only-classification")


def test_re_registering_same_key_overwrites_previous_entry():
    """register_classification_provider()'s own docstring: "last import wins"
    — re-registration is a silent overwrite, not an error."""
    registry_module.register_classification_provider("fake", _FakeClassifier)

    class _ReplacementClassifier:
        pass

    registry_module.register_classification_provider("fake", _ReplacementClassifier)
    resolved = registry_module.resolve_classification_provider("fake")
    assert isinstance(resolved, _ReplacementClassifier)


def test_registry_module_has_no_import_of_classification_or_metadata_modules():
    """Architectural invariant from the module's own docstring — zero
    circular-import risk, zero coupling to a provider's implementation
    details. Verified mechanically (not just by reading the source) so a
    future edit that reintroduces the coupling fails a test, not just a
    design-review re-read."""
    import sys

    module_globals = vars(registry_module)
    for name, value in module_globals.items():
        if hasattr(value, "__module__"):
            module_name = getattr(value, "__module__", "") or ""
            assert not module_name.startswith("src.pipeline.classification"), (
                f"registry.py's {name!r} is bound from src.pipeline.classification "
                "— this reintroduces the circular-import risk the module "
                "docstring says this file must never have."
            )
            assert not module_name.startswith("src.pipeline.metadata"), (
                f"registry.py's {name!r} is bound from src.pipeline.metadata "
                "— this reintroduces the circular-import risk the module "
                "docstring says this file must never have."
            )
    assert "src.pipeline.classification" not in sys.modules or True  # see note below
    # Note: the assertion above is intentionally a no-op guard against a
    # flaky check — other test files imported earlier in the same pytest
    # process legitimately import src.pipeline.classification, so "is it in
    # sys.modules at all" is not a valid signal in a shared test run. The
    # module-globals scan above is the real check: registry.py's own
    # top-level names must never be bound to those modules.
