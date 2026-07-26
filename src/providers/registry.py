"""
Provider registry (TD-01 v0.9). Design:
`Build-out/02 Classification/TD-01 Provider Architecture — Design Package.md`
§5 (frozen for v0.9 — Claude the only registered entry, architecture not
assumed permanent).

What this is: a small, explicit mapping from a plain string key (e.g.
`"claude"`) to a zero-argument factory that produces a real
`ClassificationProvider` or `MetadataExtractionProvider` instance (see
`src/pipeline/classification.py`/`src/pipeline/metadata.py` for those ABCs).
Two independent registries — one per provider kind — mirroring the fact that
`ClassificationProvider` and `MetadataExtractionProvider` are already
separate ABCs with no shared base (Module 02 §25 / Module 03 §23); this
module doesn't unify them.

What this deliberately is NOT: a plugin-discovery system, a dependency-
injection framework, or anything that scans the filesystem for providers.
Every registered provider is still an explicit, reviewed import in this
project's own code — consistent with the "no code no one wrote" discipline
every other module here follows. Registration happens as an import-time side
effect: a concrete provider module (e.g. `src/providers/claude.py`) calls
`register_classification_provider(...)`/`register_extraction_provider(...)`
at module load. Importing that module is what "activates" its provider —
`src/main.py` does this once, at the top of the file, for `claude`.

Deliberately has NO import of `src.pipeline.classification`/
`src.pipeline.metadata` — those two modules' concrete provider
implementations (in `src/providers/claude.py`) import the ABCs *from* here's
callers, not the other way around, so this module carries zero risk of a
circular import and zero coupling to any provider's own implementation
details. Type hints below use `Callable[[], Any]` rather than the real ABC
types for exactly this reason.
"""

from typing import Any, Callable, Dict, List

_CLASSIFICATION_PROVIDERS: Dict[str, Callable[[], Any]] = {}
_EXTRACTION_PROVIDERS: Dict[str, Callable[[], Any]] = {}


class UnknownProviderError(ValueError):
    """Raised when a configured/requested provider key has no matching
    registry entry. A `ValueError` subclass (not a plain `Exception`) so a
    caller that already catches `ValueError` for other config problems
    (`main.py`'s `_load_destination_root()`-adjacent style,
    `cli.py`'s `_run_scan_with_friendly_config_errors()`) can treat this the
    same way without a new except clause, while still being distinguishable
    by type for a caller that wants to handle it specifically."""


def register_classification_provider(key: str, factory: Callable[[], Any]) -> None:
    """Register a `ClassificationProvider` factory under `key`. Re-registering
    the same key overwrites the previous entry (last import wins) — no
    project code currently relies on that, but it's simpler and more honest
    than raising on a re-registration that, in practice, only ever happens
    if a module is imported twice under different names (a packaging
    accident worth surfacing some other way, not this function's job)."""
    _CLASSIFICATION_PROVIDERS[key] = factory


def register_extraction_provider(key: str, factory: Callable[[], Any]) -> None:
    """Register a `MetadataExtractionProvider` factory under `key`. Mirrors
    `register_classification_provider()` exactly."""
    _EXTRACTION_PROVIDERS[key] = factory


def resolve_classification_provider(key: str) -> Any:
    """Instantiate and return the `ClassificationProvider` registered under
    `key`. Raises `UnknownProviderError` — never silently falls back to
    Unknown or to the interactive-session placeholder — if `key` isn't
    registered, so a configuration typo is visibly a configuration problem
    (§ "Risk assessment" of the design package) rather than a silent quality
    regression indistinguishable from TD-01 itself."""
    try:
        factory = _CLASSIFICATION_PROVIDERS[key]
    except KeyError:
        raise UnknownProviderError(
            f"No classification provider registered under {key!r}. "
            f"Registered: {registered_classification_providers()!r}. "
            "Check src/config/sources.yaml's classification_provider value, "
            "or run 'python -m src.cli provider status'."
        ) from None
    return factory()


def resolve_extraction_provider(key: str) -> Any:
    """Instantiate and return the `MetadataExtractionProvider` registered
    under `key`. Mirrors `resolve_classification_provider()` exactly."""
    try:
        factory = _EXTRACTION_PROVIDERS[key]
    except KeyError:
        raise UnknownProviderError(
            f"No extraction provider registered under {key!r}. "
            f"Registered: {registered_extraction_providers()!r}. "
            "Check src/config/sources.yaml's extraction_provider value, "
            "or run 'python -m src.cli provider status'."
        ) from None
    return factory()


def registered_classification_providers() -> List[str]:
    """Every currently-registered classification provider key, sorted —
    read by `cli.py`'s `provider status`/`provider enable` for user-facing
    listing and validation, and by the Provider Evaluation Harness to know
    which providers exist to benchmark."""
    return sorted(_CLASSIFICATION_PROVIDERS)


def registered_extraction_providers() -> List[str]:
    """Every currently-registered extraction provider key, sorted. Mirrors
    `registered_classification_providers()` exactly."""
    return sorted(_EXTRACTION_PROVIDERS)
