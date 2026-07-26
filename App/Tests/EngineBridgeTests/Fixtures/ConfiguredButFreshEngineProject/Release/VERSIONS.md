# Version History

**Pipeline Version: 0.8.0**

Fixture for a project that has been configured (`sources.yaml` exists) and
is running a compatible engine version, but has never had `scan`/`run`
executed — so `Database/` and `Runtime/` do not exist yet. Used to test
`EngineBridge`'s "missing artifact" handling distinctly from "engine
version incompatible" or "never configured at all."
