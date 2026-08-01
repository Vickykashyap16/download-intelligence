"""Fixture stand-in for the real src/cli.py, used only by
ReportsViewModelTests to exercise the real `python3 -m src.cli report`
subprocess path end-to-end — proving `ReportsViewModel.refreshNow()`'s
invocation is wired correctly and that the subsequent artifact re-read
picks up exactly what this process actually wrote — without requiring the
real Python engine or its real aggregation logic.

Deliberately independent from `UndoingEngineProject`/`ExecutingEngineProject`
(other work packages' own already-frozen fixtures, "do not disturb another
work package's fixture"): this fixture only implements `report`, matching
`src/cli.py`'s own real `_cmd_report()` (`run_report(); return 0` — no
arguments, always (re)writes all four report files in one call, per that
function's own docstring confirmed during WP-GUI-10 dependency verification).
The Markdown this fixture writes is deliberately structured (heading, a
leading bullet, one `## Section` table) so a real end-to-end run also
exercises `ReportsProjection`'s structural parser against genuinely
subprocess-written files, not just inline Swift string literals.
"""
import os
import sys

REPORTS_ROOT = os.path.join("Runtime", "Reports")


def write(relative_path, content):
    full_path = os.path.join(REPORTS_ROOT, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as handle:
        handle.write(content)


def cmd_report():
    write(
        os.path.join("Daily Summary", "summary_2026-08-01.md"),
        "# Daily Summary — 2026-08-01\n\n"
        "- Files scanned: 1\n\n"
        "## Files\n"
        "| Original | New Name | Destination | Category | Confidence | Tier |\n"
        "|---|---|---|---|---|---|\n"
        "| invoice.pdf | Invoice_2026-08-01.pdf | Finance/Invoices/ | invoice | 97 | auto |\n",
    )
    write(
        os.path.join("Weekly Summary", "summary_2026-W31.md"),
        "# Weekly Summary — 2026-W31\n\n"
        "- Week range: 2026-07-28 to 2026-08-03\n\n"
        "## Days\n"
        "| Date | Status |\n"
        "|---|---|\n"
        "| 2026-08-01 | Reported |\n",
    )
    write(
        os.path.join("Duplicate Report", "duplicate_report.md"),
        "# Duplicate Report\n\n"
        "- As of: no activity recorded yet\n\n"
        "## Records\n"
        "| Original | Type | Related To | Disposition |\n"
        "|---|---|---|---|\n",
    )
    write(
        os.path.join("Storage Report", "storage_report.md"),
        "# Storage Report\n\n"
        "- Filed records: 1\n\n"
        "## By Destination\n"
        "| Destination | Size |\n"
        "|---|---|\n"
        "| Finance/Invoices/ | 12.0 KB |\n",
    )
    print("fixture report complete")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("fixture: no command given", file=sys.stderr)
        return 2

    if args[0] == "report":
        return cmd_report()

    print(f"fixture: unrecognized command {args[0]!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
