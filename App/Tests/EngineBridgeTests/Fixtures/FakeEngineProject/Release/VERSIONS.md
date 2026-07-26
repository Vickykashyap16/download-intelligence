# Version History

**Pipeline Version: 0.8.0**

This fixture file mirrors the real `Release/VERSIONS.md` format exactly:
a bolded `**Pipeline Version: X.Y.Z**` line, found by `src/cli.py`'s
`_cmd_version()` via a `startswith("**Pipeline Version:")` check — and by
`EngineVersionReader` the same way.

## History

- 0.8.0 — fixture baseline used by EngineBridgeTests.
