"""
Module 07 UAT — Run 1, stage 2 / Call 1: crash simulation for the two
CrashTest_* records (real project Database/Runtime, real destination library),
then a real main.execute(decisions={}) call that reconciles them and executes
every auto-tier record (Invoice_Clean_Acme, Resume_Alex_v1, Resume_Alex_v2,
CrashTest_Alpha post-reconciliation). Invoice_Clean_Acme's naive destination
already has a real pre-placed collision file (§12 execution-time re-check).
"""
import sys
sys.path.insert(0, "/sessions/nice-fervent-wozniak/mnt/Download Intelligence ")
from pathlib import Path

from src import main as mainmod
from src.storage import database as dbmod
from src.storage import runtime_io as riomod
from src.pipeline import execution as execmod

records = dbmod.load_metadata_store()
by_name = {r.original_name: r for r in records}
alpha = by_name["CrashTest_Alpha.txt"]
beta = by_name["CrashTest_Beta.txt"]
BATCH_ID = alpha.batch_id
LIBRARY_ROOT = Path("/tmp/uat_m07_library")

print(f"Batch id: {BATCH_ID}")
print(f"CrashTest_Alpha tier={alpha.tier} CrashTest_Beta tier={beta.tier}")

# --- (a) SAFE_TO_RETRY: stage only, no move attempted. ---
execmod._stage_plan_entry_for_record(alpha, {}, LIBRARY_ROOT, BATCH_ID)
print("Staged plan entry for CrashTest_Alpha (no move attempted) — simulates a crash "
      "immediately after staging.")

# --- (b) REPAIRED: real move + real log entry, FileRecord deliberately never saved. ---
override_type = execmod.resolve_precedence(beta)
resolved_path = execmod.resolve_destination_path(beta, LIBRARY_ROOT, override_type)
final_path = execmod.resolve_available_destination(resolved_path)
execmod._stage_plan_entry_for_record(beta, {}, LIBRARY_ROOT, BATCH_ID)
execmod.ensure_destination_folder(final_path.parent)
move_result = execmod.perform_move(beta.current_path, final_path)
print(f"Real move for CrashTest_Beta: success={move_result.success}")
execmod.log_move(
    batch_id=BATCH_ID, record=beta, override_type=override_type,
    executed_name=final_path.name, executed_destination=beta.suggested_destination,
    from_path=beta.current_path, to_path=str(final_path), approved_by="auto",
)
print(f"CrashTest_Beta's FileRecord deliberately NOT updated yet "
      f"(processed_at={beta.processed_at}) — simulates a crash between the log write "
      f"and the record save.")

print("\n=== Call 1: main.execute(decisions={}) — reconciliation + auto-tier execution ===")
mainmod.execute(decisions={})

records = dbmod.load_metadata_store()
by_name = {r.original_name: r for r in records}
print("\n--- Post-Call-1 state ---")
for name in ["Invoice_Clean_Acme.pdf", "Resume_Alex_v1.pdf", "Resume_Alex_v2.pdf",
             "CrashTest_Alpha.txt", "CrashTest_Beta.txt"]:
    r = by_name[name]
    print(f"  {name}: processed_at={r.processed_at} approved_by={r.approved_by} "
          f"reversible={r.reversible} current_path={r.current_path}")

# Confirm approval_required/review_required records untouched.
for name in ["Invoice_Sparse_Draft.pdf", "Photo_Sunset_v1.jpg", "Photo_Sunset_v2.jpg",
             "Screenshot_Dashboard.png", "Utility_Bill_Download.txt",
             "Utility_Bill_Download_copy.txt", "Locked_Contract_Vendor.pdf"]:
    r = by_name[name]
    print(f"  [untouched check] {name}: processed_at={r.processed_at}")

print(f"\nRuntime/Temp plan for batch after reconciliation: "
      f"{riomod.read_batch_plan(BATCH_ID)}")
