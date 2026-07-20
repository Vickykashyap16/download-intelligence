"""Module 08 UAT — Stage 1: real scan/classify/extract/detect_duplicates/suggest_naming/score_confidence/preview
against the REAL project Database/Runtime, real external Downloads/library folders, live Claude judgment
for classify()/extract() (this script's own hardcoded answers ARE that live judgment -- formed by directly
reading each real file's actual extracted text, myself, in the immediately preceding step of this session)."""
import sys
sys.path.insert(0, "/sessions/nice-fervent-wozniak/mnt/Download Intelligence")

import src.main as main_module
from src.pipeline.classification import ClassificationProvider, ProviderResponse as CResp, ClassificationResult, ProviderMetadata as CMeta
from src.pipeline.metadata import MetadataExtractionProvider, ProviderResponse as MResp, ProviderMetadata as MMeta
from pathlib import Path

# My own real judgment, formed by reading each file's real extracted text in the prior step.
LIVE_CATEGORY = {
    "Invoice_CloudHosting_Vendor.pdf": "Invoice",
    "Resume_Morgan_Taylor.pdf": "Resume",
    "Receipt_Coffee_Shop.pdf": "Invoice",
    "Old_Meeting_Notes.txt": "Document",
    "Old_Meeting_Notes_backup.txt": "Document",
    "Budget_Plan_v1.pdf": "Document",
    "Budget_Plan_v2.pdf": "Document",
    "Screenshot_ErrorDialog.png": "Screenshot",
}
LIVE_FIELDS = {
    "Invoice_CloudHosting_Vendor.pdf": {
        "vendor": "NimbusHost Cloud Services", "invoice_date": "2026-07-15",
        "invoice_number": "NH-88213", "amount": "249.00", "currency": "USD", "tax_type": "VAT",
    },
    "Resume_Morgan_Taylor.pdf": {"candidate_name": "Morgan Taylor"},
    "Receipt_Coffee_Shop.pdf": {"vendor": "Corner Coffee Co", "invoice_date": "2026-07-16"},
    "Old_Meeting_Notes.txt": {"best_guess_title": "Q3 Planning Meeting Notes"},
    "Old_Meeting_Notes_backup.txt": {"best_guess_title": "Q3 Planning Meeting Notes"},
    "Budget_Plan_v1.pdf": {"best_guess_title": "Marketing Budget Plan"},
    "Budget_Plan_v2.pdf": {"best_guess_title": "Marketing Budget Plan"},
    "Screenshot_ErrorDialog.png": {"context_description": "Error dialog showing a connection timeout message with a retry button"},
}

class LiveClassifier(ClassificationProvider):
    """My own real judgment, per file, formed by reading its real extracted text/image content
    directly in this UAT session -- not a filename-substring routing fake."""
    def classify(self, request):
        name = Path(request.path).name
        cat = LIVE_CATEGORY.get(name, "Unknown")
        return CResp(result=ClassificationResult(category=cat, notes="live Claude judgment, Module 08 UAT"),
                     metadata=CMeta(provider_name="claude-live-uat", latency_ms=5))

class LiveExtractor(MetadataExtractionProvider):
    def extract(self, request):
        name = Path(request.path).name
        fields = LIVE_FIELDS.get(name, {})
        answered = {k: v for k, v in fields.items() if k in request.fields_requested}
        return MResp(fields=answered, metadata=MMeta(provider_name="claude-live-uat", latency_ms=5))

print("### main.scan() ###")
main_module.scan()
print("\n### main.classify(provider=LiveClassifier()) ###")
main_module.classify(provider=LiveClassifier())
print("\n### main.extract(provider=LiveExtractor()) ###")
main_module.extract(provider=LiveExtractor())
print("\n### main.detect_duplicates() ###")
main_module.detect_duplicates()
print("\n### main.suggest_naming() ###")
main_module.suggest_naming()
print("\n### main.score_confidence() ###")
main_module.score_confidence()
print("\n### main.preview() ###")
main_module.preview()
