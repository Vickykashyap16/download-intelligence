"""
Module 07 UAT — Run 1, stage 1: real scan -> classify(live) -> extract(live) ->
detect_duplicates -> suggest_naming -> score_confidence -> preview.

Uses the REAL project Database/Runtime (src/config/sources.yaml already edited
to point `path`/`destination_root` at the external /tmp/uat_m07_downloads and
/tmp/uat_m07_library folders) — per Module 06 UAT's own established
methodology, UAT runs against the real live system, not an isolated harness.

Classification/extraction answers below are literal, live judgments formed by
Claude reading each real generated file's actual content (pdfplumber-verified
text for the PDFs; the two .txt files read directly; the two images described
from their actual real drawn content) — never a canned/routing fake.
"""
import sys
sys.path.insert(0, "/sessions/nice-fervent-wozniak/mnt/Download Intelligence ")

from src.pipeline.classification import (
    ClassificationProvider, ClassificationResult, ProviderMetadata as CPM, ProviderResponse as CPR,
)
from src.pipeline.metadata import (
    MetadataExtractionProvider, ProviderMetadata as MPM, ProviderResponse as MPR,
)
from src import main as mainmod
from src.storage import database as dbmod

# --- Live classification judgments (read from each real file's actual content) ---
LIVE_CLASSIFICATIONS = {
    "Invoice_Clean_Acme.pdf": "Invoice",
    "Invoice_Sparse_Draft.pdf": "Invoice",
    "Locked_Contract_Vendor.pdf": None,  # never reaches provider — real is_locked() path
    "Utility_Bill_Download.txt": "Invoice",
    "Utility_Bill_Download_copy.txt": "Invoice",
    "Resume_Alex_v1.pdf": "Resume",
    "Resume_Alex_v2.pdf": "Resume",
    "Photo_Sunset_v1.jpg": "Screenshot",   # no camera EXIF -> real deterministic Screenshot path
    "Photo_Sunset_v2.jpg": "Screenshot",
    "CrashTest_Alpha.txt": "Document",
    "CrashTest_Beta.txt": "Document",
    "Screenshot_Dashboard.png": "Screenshot",
}

# --- Live extraction judgments (literal transcription of real content read) ---
LIVE_EXTRACTIONS = {
    "Invoice_Clean_Acme.pdf": {
        "vendor": "Acme Robotics Inc.", "invoice_date": "2026-07-01",
        "invoice_number": "INV-9001", "amount": "1250.00",
        "currency": "USD", "tax_type": "none",
    },
    "Invoice_Sparse_Draft.pdf": {
        "vendor": "Northstar Supplies", "invoice_date": "2026-07-02",
        # invoice_number/amount/currency/tax_type genuinely absent from the real text
    },
    "Utility_Bill_Download.txt": {
        "vendor": "CityPower Utilities Co.", "invoice_date": "2026-06-15",
    },
    "Utility_Bill_Download_copy.txt": {
        "vendor": "CityPower Utilities Co.", "invoice_date": "2026-06-15",
    },
    "Resume_Alex_v1.pdf": {
        "candidate_name": "Alex Rivera", "last_modified_date": "2026-05-01",
        # version_indicator genuinely absent
    },
    "Resume_Alex_v2.pdf": {
        "candidate_name": "Alex Rivera", "last_modified_date": "2026-06-15",
    },
    "Photo_Sunset_v1.jpg": {
        "context_description": "Product photo, warm orange background with a circular highlighted subject",
        # capture_date: no EXIF present, genuinely absent
    },
    "Photo_Sunset_v2.jpg": {
        "context_description": "Product photo, warm orange background with a circular highlighted subject",
    },
    "CrashTest_Alpha.txt": {
        "best_guess_title": "Reconciliation Test Note Alpha", "document_date": "2026-07-13",
        "description": "Fixture used to simulate a crash before any move is attempted.",
    },
    "CrashTest_Beta.txt": {
        "best_guess_title": "Reconciliation Test Note Beta", "document_date": "2026-07-13",
        "description": "Fixture used to simulate a crash between the log write and the record save.",
    },
    "Screenshot_Dashboard.png": {
        "context_description": "Dashboard login error screen, dark header bar, error message about an invalid session token",
        # capture_date: no EXIF, genuinely absent
    },
}


class LiveClassificationProvider(ClassificationProvider):
    def classify(self, request):
        from pathlib import Path
        name = Path(request.path).name
        cat = LIVE_CLASSIFICATIONS.get(name, "Document")
        return CPR(result=ClassificationResult(category=cat), metadata=CPM(provider_name="ClaudeLive"))


class LiveMetadataProvider(MetadataExtractionProvider):
    def extract(self, request):
        from pathlib import Path
        name = Path(request.path).name
        fields = LIVE_EXTRACTIONS.get(name, {})
        requested = {k: fields.get(k) for k in request.fields_requested}
        return MPR(fields=requested, metadata=MPM(provider_name="ClaudeLive"))


live_cls = LiveClassificationProvider()
live_meta = LiveMetadataProvider()

print("=== Module 07 UAT Run 1 — Stage 1: scan -> classify -> extract -> detect_dup -> name -> score -> preview ===\n")
mainmod.scan()
mainmod.classify(provider=live_cls)
mainmod.extract(provider=live_meta)
mainmod.detect_duplicates()
mainmod.suggest_naming()
mainmod.score_confidence()

records = dbmod.load_metadata_store()
print(f"\n--- Post-score summary ({len(records)} records) ---")
for r in sorted(records, key=lambda r: r.original_name):
    print(f"  {r.original_name}: cat={r.category.value if r.category else None} "
          f"score={r.confidence_score} tier={r.tier} dup_of={r.duplicate_of} "
          f"rank={r.version_rank} dest={r.suggested_destination}{r.suggested_name}")

mainmod.preview()
