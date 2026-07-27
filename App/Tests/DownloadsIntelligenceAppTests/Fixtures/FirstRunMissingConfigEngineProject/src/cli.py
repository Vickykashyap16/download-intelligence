"""Fixture stand-in for the real src/cli.py — see
`FirstRunEngineProject/src/cli.py`'s module docstring for the full
rationale; this is the identical fixture CLI, paired here with a project
that has no `src/config/sources.yaml` at all so its `config` command's
existence guard is exercised (real behavior, not a fixture invention):
`FirstRunExperienceViewModelTests` uses this project specifically to prove
a silent, no-op-but-exit-0 write is caught by the re-read verification step
rather than treated as success.
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
