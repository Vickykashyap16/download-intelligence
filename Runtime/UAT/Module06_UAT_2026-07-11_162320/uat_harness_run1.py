"""
Module 06 UAT harness — Run 1.

This is NOT a permanent pytest file (per project convention, only the UAT plan
markdown persists). Runs the real Module 01->06 pipeline via src/main.py's real
CLI functions, against the real project Database/Runtime, with a live-judgment
ClassificationProvider/MetadataExtractionProvider whose classify()/extract()
methods return literal, per-file judgments I (Claude) formed by generating and
then reading each real file's actual content in /tmp/uat_m06_downloads --
never a filename-substring routing fake (that pattern is Integration-Testing-only).
"""
import sys
from pathlib import Path

sys.path.insert(0, "/sessions/nice-fervent-wozniak/mnt/Download Intelligence ")

from src import main
from src.pipeline.classification import (
    ClassificationRequest, ClassificationResult, ClassificationProvider,
)
from src.pipeline.metadata import (
    MetadataExtractionRequest, MetadataExtractionProvider,
)
from src.pipeline.classification import ProviderMetadata as ClsProviderMetadata
from src.pipeline.metadata import ProviderMetadata as MetaProviderMetadata
from src.pipeline.classification import ProviderResponse as ClsProviderResponse
from src.pipeline.metadata import ProviderResponse as MetaProviderResponse

PROVIDER_NAME = "claude-live-uat-m06"


# ---------------------------------------------------------------------------
# Live classification judgments -- one entry per PDF that actually reaches the
# provider (locked/blank/corrupted files never get this far -- confirmed by
# direct inspection of classification.py before this run).
# ---------------------------------------------------------------------------
_CLASSIFY_JUDGMENTS = {
    "Invoice_Northwind_Traders.pdf": dict(category="Invoice", ambiguous=False, multi_document_detected=False,
        notes="Clean, complete invoice: vendor, invoice number, date, line items, total all present."),
    "Invoice_Sparse_Draft.pdf": dict(category="Invoice", ambiguous=False, multi_document_detected=False,
        notes="Draft billing note, no vendor/invoice number stated, but structurally an invoice-in-progress, not ambiguous about document type."),
    "Receipt_Or_Invoice_Ambiguous.pdf": dict(category="Invoice", ambiguous=True, multi_document_detected=False,
        notes="Text explicitly says it serves as both invoice and receipt -- genuinely ambiguous framing."),
    "Facture_Boulangerie_Paris.pdf": dict(category="Invoice", ambiguous=False, multi_document_detected=False,
        notes="French-language invoice ('Facture'), clearly a single invoice despite language."),
    "Batch_Invoices_Merged.pdf": dict(category="Invoice", ambiguous=False, multi_document_detected=True,
        notes="Three distinct invoice blocks (#A-1001/1002/1003, different vendors/dates) on three separate pages -- a batched export, not one invoice."),
    "Resume_Morgan_Ellis_v1.pdf": dict(category="Resume", ambiguous=False, multi_document_detected=False,
        notes="Standard resume: name, experience, education."),
    "Resume_Morgan_Ellis_v2.pdf": dict(category="Resume", ambiguous=False, multi_document_detected=False,
        notes="Updated resume, same candidate, added senior role + last-updated date."),
    "BankStatement_Chase_June2026.pdf": dict(category="Bank Statement", ambiguous=False, multi_document_detected=False,
        notes="Monthly bank statement with period, balances, account number."),
    "BankStatement_Chase_June2026_copy.pdf": dict(category="Bank Statement", ambiguous=False, multi_document_detected=False,
        notes="Byte-identical copy of the Chase June statement."),
    "Contract_ServiceAgreement_v1.pdf": dict(category="Contract", ambiguous=False, multi_document_detected=False,
        notes="Service agreement between Meridian Consulting Group and Oakview Retail Inc., effective March 1 2026."),
    "Contract_ServiceAgreement_v2.pdf": dict(category="Contract", ambiguous=False, multi_document_detected=False,
        notes="Revised/corrected copy of the same service agreement, restates an earlier effective date (Jan 15 2026)."),
    "Document_Employee_Handbook.pdf": dict(category="Document", ambiguous=False, multi_document_detected=False,
        notes="Generic company policy document, no more specific category fits."),
    "invoice_\U0001F9FE_northstar_—_v2.pdf": dict(category="Invoice", ambiguous=False, multi_document_detected=False,
        notes="Simple, complete invoice from North Star Freight Co.; adversarial filename (emoji + em-dash) does not affect content."),
}


class LiveClassificationProvider(ClassificationProvider):
    def classify(self, request: ClassificationRequest) -> ClsProviderResponse:
        name = Path(request.path).name
        if name not in _CLASSIFY_JUDGMENTS:
            raise AssertionError(
                f"UAT harness: classify() called for unexpected file {name!r} "
                f"(mode={request.mode}) -- no live judgment was prepared for it."
            )
        j = _CLASSIFY_JUDGMENTS[name]
        return ClsProviderResponse(
            result=ClassificationResult(
                category=j["category"],
                ambiguous=j["ambiguous"],
                multi_document_detected=j["multi_document_detected"],
                notes=j["notes"],
            ),
            metadata=ClsProviderMetadata(provider_name=PROVIDER_NAME, model="claude-sonnet-5"),
        )


# ---------------------------------------------------------------------------
# Live metadata extraction judgments -- one entry per file that reaches the
# provider for judgment fields (Invoice/Resume/Bank Statement/Contract/Document
# text fields, plus Image/Screenshot vision description fields).
# ---------------------------------------------------------------------------
_EXTRACT_JUDGMENTS = {
    "Invoice_Northwind_Traders.pdf": {
        "vendor": "Northwind Traders", "invoice_date": "2026-06-15",
        "invoice_number": "INV-88213", "amount": "$4,230.00",
        "currency": "USD", "tax_type": "Sales Tax",
    },
    "Invoice_Sparse_Draft.pdf": {
        "vendor": None, "invoice_date": "2026-05-02",
        "invoice_number": None, "amount": None,
        "currency": None, "tax_type": None,
    },
    "Receipt_Or_Invoice_Ambiguous.pdf": {
        "vendor": "Riverside Cafe & Goods", "invoice_date": "2026-06-20",
        "invoice_number": None, "amount": "$612.50",
        "currency": "USD", "tax_type": None,
    },
    "Facture_Boulangerie_Paris.pdf": {
        "vendor": "Boulangerie Saint-Germain", "invoice_date": "2026-06-12",
        "invoice_number": "FR-2026-0417", "amount": "276,00 EUR",
        "currency": "EUR", "tax_type": "TVA (20%)",
    },
    "Batch_Invoices_Merged.pdf": {
        # Design note (Module 03 Design.md S19): extraction attempted as a single
        # unit, likely from the first/primary document within a multi-document file.
        "vendor": "Cascade Hardware", "invoice_date": "2026-04-01",
        "invoice_number": "A-1001", "amount": "$340.00",
        "currency": None, "tax_type": None,
    },
    "Resume_Morgan_Ellis_v1.pdf": {
        "candidate_name": "Morgan Ellis", "version_indicator": None, "last_modified_date": None,
    },
    "Resume_Morgan_Ellis_v2.pdf": {
        "candidate_name": "Morgan Ellis", "version_indicator": None, "last_modified_date": "2026-05-10",
    },
    "BankStatement_Chase_June2026.pdf": {
        "bank_name": "Chase", "statement_period": "June 1 - June 30, 2026", "account_last4": "4821",
        # Deliberately NOT extracting balance/transaction figures even though the
        # source text contains them -- closed taxonomy privacy rule (Module 03
        # Design.md S7/S18): those fields are not in Bank Statement's defined list.
    },
    "BankStatement_Chase_June2026_copy.pdf": {
        "bank_name": "Chase", "statement_period": "June 1 - June 30, 2026", "account_last4": "4821",
    },
    "Contract_ServiceAgreement_v1.pdf": {
        "contract_type": "Service Agreement", "counterparty": "Oakview Retail Inc.",
        "effective_date": "2026-03-01", "term_length": "12 months",
    },
    "Contract_ServiceAgreement_v2.pdf": {
        "contract_type": "Service Agreement", "counterparty": "Oakview Retail Inc.",
        "effective_date": "2026-01-15", "term_length": "12 months",
    },
    "Document_Employee_Handbook.pdf": {
        "best_guess_title": "Employee Handbook", "document_date": "2026-04-18",
        "description": "Company policy handbook covering remote work and PTO policies",
    },
    "invoice_\U0001F9FE_northstar_—_v2.pdf": {
        "vendor": "North Star Freight Co.", "invoice_date": "2026-06-28",
        "invoice_number": "NS-3390", "amount": "$980.00",
        "currency": "USD", "tax_type": None,  # source literally says "Tax Type: None"
    },
    "Screenshot_Login_Error.png": {
        "context_description": "Login screen showing an authentication error dialog "
                                "('Invalid username or password') with a Try Again button",
    },
    # CORRECTION (harness-authoring error found on first execution, not a module
    # defect): classification.py's classify_screenshot_or_image() correctly puts any
    # image with no camera EXIF into Screenshot, not Image (Rules/Classification
    # Rules.md's real third condition -- "no camera EXIF data" -- confirmed by
    # direct code read). These Pillow-generated JPGs carry no EXIF at all, so both
    # were correctly classified Screenshot on the real run. Screenshot's real
    # required/optional fields are context_description/capture_date, not Image's
    # description/variant -- my first-draft judgment used the wrong category's
    # field names. Corrected here before Run 1 execution.
    "Product_Shot_Front.jpg": {
        "context_description": "Product photo of an orange/tan rectangular box next "
                                "to a blue circular item on a neutral background",
    },
    "Product_Shot_Angle.jpg": {
        "context_description": "Product photo of an orange/tan rectangular box next "
                                "to a blue circular item on a neutral background, "
                                "shown from a slightly different angle",
    },
}


class LiveMetadataExtractionProvider(MetadataExtractionProvider):
    def extract(self, request: MetadataExtractionRequest) -> MetaProviderResponse:
        name = Path(request.path).name
        if name not in _EXTRACT_JUDGMENTS:
            raise AssertionError(
                f"UAT harness: extract() called for unexpected file {name!r} "
                f"(mode={request.mode}, fields_requested={request.fields_requested}) "
                f"-- no live judgment was prepared for it."
            )
        all_fields = _EXTRACT_JUDGMENTS[name]
        # Engine only asks for the specific outstanding judgment fields -- return
        # only those, mirroring the real request contract.
        answer = {f: all_fields.get(f) for f in request.fields_requested if f in all_fields}
        return MetaProviderResponse(
            fields=answer,
            metadata=MetaProviderMetadata(provider_name=PROVIDER_NAME, model="claude-sonnet-5"),
        )


if __name__ == "__main__":
    print("=" * 70)
    print("MODULE 01: scan()")
    print("=" * 70)
    main.scan()

    print("\n" + "=" * 70)
    print("MODULE 02: classify(provider=LiveClassificationProvider())")
    print("=" * 70)
    main.classify(provider=LiveClassificationProvider())

    print("\n" + "=" * 70)
    print("MODULE 03: extract(provider=LiveMetadataExtractionProvider())")
    print("=" * 70)
    main.extract(provider=LiveMetadataExtractionProvider())

    print("\n" + "=" * 70)
    print("MODULE 04: detect_duplicates()")
    print("=" * 70)
    main.detect_duplicates()

    print("\n" + "=" * 70)
    print("MODULE 05: suggest_naming()")
    print("=" * 70)
    main.suggest_naming()

    print("\n" + "=" * 70)
    print("MODULE 06: score_confidence()")
    print("=" * 70)
    main.score_confidence()

    print("\nUAT Run 1 pipeline execution complete.")
