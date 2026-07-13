"""
Module 07 UAT — Run 1, stage 5: undo, batch and single-action granularity.
Real project Database/Runtime, real destination library.
"""
import sys
sys.path.insert(0, "/sessions/nice-fervent-wozniak/mnt/Download Intelligence ")
from pathlib import Path

from src.models.execution import ApprovalDecision, ApprovalDecisionType
from src.pipeline import execution as execmod
from src.storage import database as dbmod
from src.storage import runtime_io as riomod

records = dbmod.load_metadata_store()
by_name = {r.original_name: r for r in records}
BATCH_ID = by_name["Invoice_Clean_Acme.pdf"].batch_id
LIBRARY_ROOT = Path("/tmp/uat_m07_library")

executed_names = ["Invoice_Clean_Acme.pdf", "Resume_Alex_v1.pdf", "Resume_Alex_v2.pdf",
                  "CrashTest_Alpha.txt", "CrashTest_Beta.txt", "Photo_Sunset_v1.jpg",
                  "Screenshot_Dashboard.png", "Utility_Bill_Download.txt",
                  "Utility_Bill_Download_copy.txt", "Invoice_Sparse_Draft.pdf"]
expected_irreversible = {"Invoice_Clean_Acme.pdf", "Resume_Alex_v1.pdf"}

reversible_flags = {n: by_name[n].reversible for n in executed_names}
print("Reversible flags before undo:", reversible_flags)

print("\n=== undo_batch() ===")
undo_report = execmod.undo_batch(BATCH_ID)
by_id = {by_name[n].file_id: n for n in executed_names}
for file_id, outcome in undo_report.outcomes.items():
    print(f"  {by_id.get(file_id, file_id)}: {outcome}")

records = dbmod.load_metadata_store()
by_name = {r.original_name: r for r in records}
print("\n--- Post-undo state ---")
for n in executed_names:
    r = by_name[n]
    print(f"  {n}: current_path={r.current_path} processed_at={r.processed_at} "
          f"approved_by={r.approved_by}")

# --- Single-action undo: re-execute the (now-undone, reversible) canonical
# Utility_Bill_Download record, then undo just that one log entry directly. ---
print("\n=== Single-action undo (re-execute canonical, then undo_single_action) ===")
can = by_name["Utility_Bill_Download.txt"]
print(f"needs_execution(canonical) before redo: {execmod.needs_execution(can)}")
redo_decision = {can.file_id: ApprovalDecision(file_id=can.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED)}
execmod.execute_batch([can], redo_decision, LIBRARY_ROOT)

records = dbmod.load_metadata_store()
by_name = {r.original_name: r for r in records}
can2 = by_name["Utility_Bill_Download.txt"]
print(f"Canonical re-executed: processed_at={can2.processed_at} current_path={can2.current_path}")

log_entries = riomod.read_action_log_entries()
matching = [e for e in log_entries if e.get("file_id") == can2.file_id
            and e.get("action") in ("move_rename", "archive_duplicate", "archive_superseded_version")
            and e.get("to") == can2.current_path]
print(f"Fresh move-type log entries found for canonical: {len(matching)}")
single_outcome = execmod.undo_single_action(matching[-1])
print(f"undo_single_action() outcome: {single_outcome}")

records = dbmod.load_metadata_store()
by_name = {r.original_name: r for r in records}
can3 = by_name["Utility_Bill_Download.txt"]
print(f"After single-action undo: current_path={can3.current_path} "
      f"original_path={can3.original_path} processed_at={can3.processed_at}")
