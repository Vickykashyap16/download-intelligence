"""Fixture stand-in for the real src/cli.py, used only by ProcessRunnerTests.

This file is NOT the engine and ships only inside the test target's
Fixtures resource. It exists so integration tests can exercise
ProcessRunner's real subprocess invocation, stdin-closing, and
stdout/stderr-capture behavior against a real child process, without
requiring the actual Python engine and its dependencies to be installed in
the test environment, and — just as importantly — without ever risking a
touch of the real, live Database/Runtime data that this project's
Engineering Freeze and non-negotiables (never delete, everything
reversible) require automated tests to stay completely clear of.

Each branch below deliberately mirrors one specific, real, documented
behavior of the real src/cli.py:

* The exit-code table from src/cli.py's own module docstring: 0 = success /
  expected outcome, 1 = an unanticipated internal error, 2 = a usage error,
  3 = aborted.
* The fact that a real interactive command (`init`) blocks on `input()`,
  and that when stdin has already reached end-of-file — exactly what
  ProcessRunner guarantees by closing its own copy of the stdin pipe's
  write end immediately after launch, unless a caller has explicitly opted
  into `allowInteractive: true` — the real CLI's outermost handler reports
  that as an "Unexpected error" (exit code 1), not a hang.
* `status`'s branch intentionally prints well over a typical OS pipe
  buffer's worth of bytes (64KB), making it double as the regression test
  for reading stdout/stderr concurrently with waiting for the process to
  exit, rather than only after — the classic Process+Pipe deadlock this
  package's design avoids.
* `config`'s branch sleeps briefly before succeeding, standing in for a
  real, non-instantaneous mutating engine operation so
  EngineMutationGuardTests can deterministically observe one mutating
  invocation still "in flight" when a second is attempted concurrently.
* `provider`'s sub-branches mirror the real CLI's `enable` (interactive,
  reads stdin), `disable` (non-interactive, immediate), and `status`
  (read-only, immediate) shape.
* The `DI_TEST_ENV_MARKER` check below exists only so
  ProcessRunnerTests can verify INFRA-01 / OD-GUI-6's
  `additionalEnvironment` parameter actually reaches this child process's
  environment (and takes precedence over an ambient value of the same
  name) — it is not part of the real CLI's contract and does not
  correspond to any real argv or command.
"""
import os
import sys
import time


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("fixture: no command given", file=sys.stderr)
        return 2

    marker = os.environ.get("DI_TEST_ENV_MARKER")
    if marker is not None:
        print(f"ENV_ECHO:{marker}")

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
