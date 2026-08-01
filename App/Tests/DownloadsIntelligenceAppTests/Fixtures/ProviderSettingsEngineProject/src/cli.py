"""Fixture stand-in for the real src/cli.py, used only by
AIProviderSettingsViewModelTests.

This file is NOT the engine and ships only inside this test target's own
Fixtures resource (never shared with EngineBridgeTests' own separate
fixtures, per this project's "never share fixtures across test targets"
convention). It exists so AIProviderSettingsViewModel's real
`provider enable -y` / `provider disable` round trip — including the
write-then-re-read confirmation both actions perform — can be exercised
against a real `python3` subprocess, without requiring the actual Python
engine and its dependencies, and without ever touching real, live
Database/Runtime data.

The `provider` branch below deliberately mirrors the real `src/cli.py`'s
own source-verified behavior (`_cmd_provider()`/`_provider_enable()`/
`_provider_disable()` in the real engine, confirmed at
`src/cli.py` lines 590-645):

* `enable` requires `ANTHROPIC_API_KEY` to be set in the environment —
  exactly the same check the real `_provider_enable()` performs — and
  fails with exit code 1 and a plain stderr message if it is not, the same
  outcome AIProviderSettingsViewModelTests uses to exercise the "engine
  reported failure" path.
* `enable -y`/`--yes` skips only the interactive confirmation
  (INFRA-01 / OD-GUI-5); the disclosure text still prints regardless,
  matching the real engine and `FakeEngineProject`'s own `-y` handling.
* On success, `enable` rewrites `ai_provider_consent: false` to
  `ai_provider_consent: true` in `src/config/sources.yaml` — the real,
  on-disk effect `AIProviderSettingsViewModel`'s post-invocation
  `readConfiguration()` re-read actually depends on to confirm the change
  took effect, not merely a printed message. `classification_provider`/
  `extraction_provider` are set too, mirroring the real engine's own
  `_provider_enable()`, even though this test target's ViewModel never
  reads those two fields itself.
* `disable` rewrites `ai_provider_consent: true` back to `false` — and,
  matching the real `_provider_disable()` exactly, does not touch
  `classification_provider`/`extraction_provider` (a real, intentional
  engine asymmetry, not a fixture simplification).
* `DI_TEST_FORCE_PROVIDER_FAILURE`, if set, makes both `enable` and
  `disable` fail with exit code 1 without writing anything — a test-only
  hook (not part of the real CLI's contract, the same pattern
  `FakeEngineProject`'s own `DI_TEST_ENV_MARKER` already establishes) that
  lets `AIProviderSettingsViewModelTests` exercise the "engine invocation
  failed" error-presentation path without needing a second fixture
  project.
"""
import os
import sys

_PROVIDER_DISCLOSURE_TEXT = (
    "fixture disclosure: AI-assisted classification sends limited file "
    "metadata to Anthropic's Claude API for harder judgment calls only."
)

_CONFIG_PATH = os.path.join("src", "config", "sources.yaml")


def _set_config_value(key: str, value: str) -> None:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    prefix = f"{key}:"
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}: {value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}: {value}")

    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _provider_enable(yes: bool) -> int:
    if os.environ.get("DI_TEST_FORCE_PROVIDER_FAILURE"):
        print("fixture: forced provider enable failure", file=sys.stderr)
        return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set in this environment.",
            file=sys.stderr,
        )
        return 1

    print(_PROVIDER_DISCLOSURE_TEXT)

    if not yes:
        try:
            response = input("Enable AI-assisted classification? [y/N] ")
        except EOFError:
            print("Unexpected error: EOF when reading a line", file=sys.stderr)
            return 1
        if response.strip().lower() != "y":
            print("Aborted.", file=sys.stderr)
            return 3

    _set_config_value("classification_provider", "claude")
    _set_config_value("extraction_provider", "claude")
    _set_config_value("ai_provider_consent", "true")
    print("AI-assisted classification is now on.")
    return 0


def _provider_disable() -> int:
    if os.environ.get("DI_TEST_FORCE_PROVIDER_FAILURE"):
        print("fixture: forced provider disable failure", file=sys.stderr)
        return 1

    _set_config_value("ai_provider_consent", "false")
    print("AI-assisted classification is now off.")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("fixture: no command given", file=sys.stderr)
        return 2

    command = args[0]

    if command == "version":
        print("Pipeline Version: 0.8.0-fixture")
        return 0

    if command == "provider":
        sub = args[1] if len(args) > 1 else None
        if sub == "enable":
            yes = "-y" in args or "--yes" in args
            return _provider_enable(yes=yes)
        if sub == "disable":
            return _provider_disable()
        if sub == "status":
            print("provider: status not used by this fixture")
            return 0
        print(f"fixture: unrecognized provider subcommand {sub!r}", file=sys.stderr)
        return 2

    print(f"fixture: unrecognized command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
