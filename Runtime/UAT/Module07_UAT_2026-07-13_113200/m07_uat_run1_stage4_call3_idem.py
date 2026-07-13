"""
Module 07 UAT — Run 1, stage 4 / Call 3: CLI-level idempotency. Re-invoke
main.execute() with the SAME decisions dict as Call 2. Every already-terminal
or review_required record must be byte-identical; Invoice_Sparse_Draft (whose
move genuinely failed and was never persisted as processed) must legitimately
retry and succeed this time (the forced-failure monkeypatch was one-shot,
already restored after Call 2).
"""
import sys
sys.path.insert(0, "/sessions/nice-fervent-wozniak/mnt/Download Intelligence ")
from pathlib import Path

from src.models.execution import ApprovalDecision, ApprovalDecisionType
from src import main as mainmod
from src.storage import database as dbmod
from src.storage import runtime_io as riomod

records = dbmod.load_metadata_store()
by_name = {r.original_name: r for r in records}

sparse = by_name["Invoice_Sparse_Draft.pdf"]
photo1 = by_name["Photo_Sunset_v1.jpg"]
screenshot = by_name["Screenshot_Dashboard.png"]
canonical = by_name["Utility_Bill_Download.txt"]
duplicate = by_name["Utility_Bill_Download_copy.txt"]
locked = by_name["Locked_Contract_Vendor.pdf"]
photo2 = by_name["Photo_Sunset_v2.jpg"]

decisions = {
    sparse.file_id: ApprovalDecision(file_id=sparse.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
    photo1.file_id: ApprovalDecision(file_id=photo1.file_id, decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
                                      edited_destination="Images/Reviewed/"),
    screenshot.file_id: ApprovalDecision(file_id=screenshot.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
    canonical.file_id: ApprovalDecision(file_id=canonical.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
    duplicate.file_id: ApprovalDecision(file_id=duplicate.file_id, decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
                                         edited_destination="Finance/Reviewed/"),
    locked.file_id: ApprovalDecision(file_id=locked.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
}

def _snap(r):
    return (r.current_path, r.processed_at, r.approved_by, r.approved_at, r.reversible, r.tier, r.confidence_score)

terminal_names = ["Invoice_Clean_Acme.pdf", "Resume_Alex_v1.pdf", "Resume_Alex_v2.pdf",
                  "CrashTest_Alpha.txt", "CrashTest_Beta.txt", "Photo_Sunset_v1.jpg",
                  "Screenshot_Dashboard.png", "Utility_Bill_Download.txt",
                  "Utility_Bill_Download_copy.txt", "Locked_Contract_Vendor.pdf", "Photo_Sunset_v2.jpg"]
pre_snapshot = {n: _snap(by_name[n]) for n in terminal_names}
pre_log_lines = len(riomod.action_log_path().read_text().strip().splitlines())

print("=== Call 3: main.execute(decisions=<same as Call 2>) — idempotency check ===")
mainmod.execute(decisions=decisions)

records = dbmod.load_metadata_store()
by_name = {r.original_name: r for r in records}
post_snapshot = {n: _snap(by_name[n]) for n in terminal_names}

changed = [n for n in terminal_names if pre_snapshot[n] != post_snapshot[n]]
print(f"\nRecords changed across Call 3 (should be empty): {changed}")

post_log_lines = len(riomod.action_log_path().read_text().strip().splitlines())
print(f"Action log lines: {pre_log_lines} -> {post_log_lines}")

sparse2 = by_name["Invoice_Sparse_Draft.pdf"]
print(f"Invoice_Sparse_Draft after Call 3: processed_at={sparse2.processed_at} "
      f"current_path={sparse2.current_path}")
