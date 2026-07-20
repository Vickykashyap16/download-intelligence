import sys
sys.path.insert(0, "/sessions/nice-fervent-wozniak/mnt/Download Intelligence")
import src.main as main_module
from src.storage.database import load_metadata_store
from src.models.execution import ApprovalDecision, ApprovalDecisionType

records = load_metadata_store()
by_name = {r.original_name: r for r in records}

decisions = {}
for name in ["Budget_Plan_v2.pdf", "Old_Meeting_Notes.txt", "Old_Meeting_Notes_backup.txt",
             "Receipt_Coffee_Shop.pdf", "Screenshot_ErrorDialog.png"]:
    r = by_name[name]
    assert r.tier == "approval_required", f"{name} unexpectedly {r.tier}"
    decisions[r.file_id] = ApprovalDecision(file_id=r.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED)

print("### main.execute(decisions=<5 real approvals>) ###")
main_module.execute(decisions=decisions)

print("\n### main.report() -- Module 08, real live data, real project Database/Runtime ###")
main_module.report()
