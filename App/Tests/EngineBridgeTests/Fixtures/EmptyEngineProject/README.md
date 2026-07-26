Deliberately near-empty fixture project: no `src/config/sources.yaml`, no
`Database/`, no `Runtime/`. Stands in for a fresh installation that has
never been configured or run, so artifact-reader tests can verify "nothing
exists yet" is handled as the correct empty/not-found state for each
reader, distinctly from a genuinely corrupted or unreadable artifact.

This file exists only so this directory itself is a real, non-empty
resource SwiftPM will copy into the test bundle.
