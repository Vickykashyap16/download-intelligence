"""
Module 07 UAT — Run 1, stage 3 / Call 2: real approval decisions for the
approval_required records (decision 23 edited-destination overrides x2,
G6/I4 forced move failure), an adversarial forged decision for a
review_required record, and no decision at all for the other review_required
record. Real project Database/Runtime, real destination library.
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

EDITED_PHOTO_DEST = "Images/Reviewed/"
EDITED_DUP_DEST = "Finance/Reviewed/"

decisions = {
    sparse.file_id: ApprovalDecision(file_id=sparse.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
    photo1.file_id: ApprovalDecision(file_id=photo1.file_id, decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
                                      edited_destination=EDITED_PHOTO_DEST),
    screenshot.file_id: ApprovalDecision(file_id=screenshot.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
    canonical.file_id: ApprovalDecision(file_id=canonical.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
    duplicate.file_id: ApprovalDecision(file_id=duplicate.file_id, decision=ApprovalDecisionType.APPROVE_WITH_EDIT,
                                         edited_destination=EDITED_DUP_DEST),
    # Adversarial: forged APPROVE_AS_SUGGESTED for a review_required record.
    locked.file_id: ApprovalDecision(file_id=locked.file_id, decision=ApprovalDecisionType.APPROVE_AS_SUGGESTED),
    # photo2 (review_required, fuzzy_duplicate): deliberately NO decision supplied at all.
}

# --- Force Invoice_Sparse_Draft.pdf's move to fail (G6/I4). ---
_real_rename = Path.rename
failure_source = str(Path(sparse.current_path))
def _flaky_rename(self, target):
    if str(self) == failure_source:
        raise OSError("Simulated OS-level failure (UAT Run 1 forced-failure scenario)")
    return _real_rename(self, target)
Path.rename = _flaky_rename

print("=== Call 2: main.execute(decisions=...) — approval_required decisions, "
      "decision 23 x2, forced failure, adversarial forged decision, no-decision baseline ===")
mainmod.execute(decisions=decisions)

Path.rename = _real_rename  # restore immediately

records = dbmod.load_metadata_store()
by_name = {r.original_name: r for r in records}

print("\n--- Post-Call-2 state ---")
for name in ["Invoice_Sparse_Draft.pdf", "Photo_Sunset_v1.jpg", "Screenshot_Dashboard.png",
             "Utility_Bill_Download.txt", "Utility_Bill_Download_copy.txt",
             "Locked_Contract_Vendor.pdf", "Photo_Sunset_v2.jpg"]:
    r = by_name[name]
    print(f"  {name}: processed_at={r.processed_at} approved_by={r.approved_by} "
          f"reversible={r.reversible} current_path={r.current_path}")

log_entries = riomod.read_action_log_entries()
error_entries = [e for e in log_entries if e.get("action") == "error" and e.get("file_id") == sparse.file_id]
print(f"\nForced-failure 'error' log entries for Invoice_Sparse_Draft: {len(error_entries)}")
print(f"Invoice_Sparse_Draft original file still exists: {Path(sparse.current_path).exists() if by_name['Invoice_Sparse_Draft.pdf'].processed_at is None else 'N/A (executed)'}")
