# Version History

**Pipeline Version: 0.8.0**

Fixture engine version inside the supported range. This project
deliberately has no `src/config/sources.yaml` at all, exercising the real
CLI's own existence guard (`_cmd_config()`'s "Could not find..." branch) —
used by `FirstRunExperienceViewModelTests` to prove the write-then-re-read
verification step catches a silent no-op write rather than proceeding as if
it had succeeded.
