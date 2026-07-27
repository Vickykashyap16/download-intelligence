"""Fixture stand-in for the real src/cli.py, used only by
FirstRunExperienceViewModelTests.

This file is NOT the engine and ships only inside this test target's own
Fixtures resource (never shared with EngineBridgeTests' own separate
fixtures, per this project's "never share fixtures across test targets"
convention). It exists so FirstRunExperienceViewModel's real config-write
round trip can be exercised against a real `python3` subprocess, without
requiring the actual Python engine and its dependencies, and without ever
touching real, live Database/Runtime data.

The `config` branch below deliberately mirrors the real `src/cli.py`'s own
documented, source-verified behavior (`_cmd_config()`/`_write_config_value()`
in the real engine): if `src/config/sources.yaml` doesn't exist, it prints a
message and returns 0 *without writing anything* — this is the real CLI's
own existence guard, not a fixture invention, and is exactly the behavior
`FirstRunExperienceViewModel`'s write-then-re-read-and-compare verification
step exists to catch (see that type's own documentation). When the file does
exist, `--set-source`/`--set-destination` rewrite the corresponding line
in place, using the same simple line-based text edit the real
`_write_config_value()` uses (not a full YAML round-trip, which would risk
losing comments/formatting) rather than requiring PyYAML to be installed in
the test environment.
"""
import os
import sys


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("fixture: no command given", file=sys.stderr)
        return 2

    command = args[0]

    if command == "version":
        print("Pipeline Version: 0.8.0-fixture")
        return 0

    if command == "config":
        config_path = os.path.join("src", "config", "sources.yaml")
        if not os.path.exists(config_path):
            print(f"Could not find {config_path}")
            return 0

        set_source = None
        if "--set-source" in args:
            set_source = args[args.index("--set-source") + 1]
        set_destination = None
        if "--set-destination" in args:
            set_destination = args[args.index("--set-destination") + 1]

        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        if set_source is not None:
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("path:"):
                    indent = line[: len(line) - len(line.lstrip())]
                    lines[i] = f"{indent}path: {set_source}"
                    break

        if set_destination is not None:
            replaced = False
            for i, line in enumerate(lines):
                if line.startswith("destination_root:"):
                    lines[i] = f"destination_root: {set_destination}"
                    replaced = True
                    break
            if not replaced:
                lines.append(f"destination_root: {set_destination}")

        with open(config_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print("config updated")
        return 0

    print(f"fixture: unrecognized command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
