"""Fixture stand-in for the real src/cli.py — see the FakeEngineProject
copy of this file for the full explanation of each branch. This copy
exists so ConfiguredButFreshEngineProject (a project that is configured
and version-compatible but has never had `scan`/`run` executed against it)
can still exercise EngineBridge.run(_:) — the "configured but fresh"
condition applies to the Database/Runtime artifacts, not to whether the
engine executable itself is reachable.
"""
import sys
import time


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("fixture: no command given", file=sys.stderr)
        return 2

    command = args[0]

    if command == "version":
        print("Pipeline Version: 9.9.9-fixture")
        return 0

    if command == "status":
        print("x" * 100_000)
        return 0

    if command == "report":
        print("simulated internal failure", file=sys.stderr)
        return 1

    if command == "scan":
        print("usage: fixture scan [-h]", file=sys.stderr)
        return 2

    if command == "run":
        return 3

    if command == "undo" and "--last" in args:
        return 42

    if command == "init":
        try:
            input()
        except EOFError:
            print("Unexpected error: EOF when reading a line", file=sys.stderr)
            return 1
        return 0

    if command == "preview":
        print("fixture preview ok: " + " ".join(args))
        return 0

    if command == "config":
        time.sleep(0.3)
        print("config updated")
        return 0

    if command == "provider":
        sub = args[1] if len(args) > 1 else None
        if sub == "enable":
            try:
                input()
            except EOFError:
                print("Unexpected error: EOF when reading a line", file=sys.stderr)
                return 1
            return 0
        if sub == "disable":
            print("provider disabled")
            return 0
        if sub == "status":
            print("provider: disabled")
            return 0
        print(f"fixture: unrecognized provider subcommand {sub!r}", file=sys.stderr)
        return 2

    print(f"fixture: unrecognized command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
