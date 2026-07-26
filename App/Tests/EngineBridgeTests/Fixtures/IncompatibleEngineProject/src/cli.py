"""Fixture stand-in for the real src/cli.py. This copy exists purely so
IncompatibleEngineProject has *something* real to (fail to) invoke —
EngineBridgeTests's version-failure tests assert that this executable is
never actually reached, because the version gate must refuse the call
before ProcessRunner is ever given the chance to run it. If a bug ever let
one of these branches actually execute during a version-failure test, that
would itself be the test failing.
"""
import sys


def main() -> int:
    args = sys.argv[1:]
    command = args[0] if args else ""
    if command == "status":
        print("this should never print during a version-failure test")
        return 0
    print(f"fixture: unrecognized command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
