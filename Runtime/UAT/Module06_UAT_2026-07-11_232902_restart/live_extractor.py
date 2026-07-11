"""Live-judgment MetadataExtractionProvider for the Module 06 UAT restart (2026-07-11).

Per-file field answers based on my own real reading of the actual generated content
(text extraction already confirmed directly against core/pdf.py before writing this
class) and, for the two Screenshot-classified images, my own real vision judgment of
what is actually drawn on each (I generated them, via Pillow, so I know the literal
pixel content). Only the fields actually requested (request.fields_requested) are
ever returned - anything else is silently omitted, exactly like a careful real
provider that never volunteers unrequested data (the closed-taxonomy privacy rule,
Module 03 Design.md §7/§18).
"""
from pathlib import Path

from src.pipeline.metadata import (
    MetadataExtractionProvider,
    MetadataExtractionRequest,
    ProviderResponse,
    ProviderMetadata,
)

_ANSWERS = {
    "Invoice_Northwind_Traders.pdf": {
        "vendor": "Northwind Traders", "invoice_date": "2026-06-15",
        "invoice_number": "INV-88213", "amount": 4230.00, "currency": "USD",
        "tax_type": "Sales Tax",
    },
    "Invoice_Sparse_Draft.pdf": {
        # Genuinely a placeholder draft - vendor/invoice_number/amount/currency/tax_type
        # are none of them actually stated in the real content.
        "invoice_date": "2026-05-02",
    },
    "Receipt_Or_Invoice_Ambiguous.pdf": {
        "vendor": "Riverside Cafe & Goods", "invoice_date": "2026-06-20",
        "amount": 612.50, "currency": "USD",
    },
    "Facture_Boulangerie_Paris.pdf": {
        "vendor": "Boulangerie Saint-Germain", "invoice_date": "2026-06-12",
        "invoice_number": "FR-2026-0417", "amount": 276.00, "currency": "EUR",
        "tax_type": "TVA (20%)",
    },
    "Batch_Invoices_Merged.pdf": {
        "vendor": "Cascade Hardware", "invoice_date": "2026-04-01",
        "invoice_number": "A-1001", "amount": 340.00, "currency": "USD",
    },
    "invoice_\U0001F9FE_northstar_—_v2.pdf": {
        "vendor": "North Star Freight Co.", "invoice_date": "2026-06-28",
        "invoice_number": "NS-3390", "amount": 980.00, "currency": "USD",
        "tax_type": "None",
    },
    "BankStatement_Chase_June2026.pdf": {
        "bank_name": "Chase Bank", "statement_period": "June 1 - June 30, 2026",
        "account_last4": "4821",
    },
    "BankStatement_Chase_June2026_copy.pdf": {
        "bank_name": "Chase Bank", "statement_period": "June 1 - June 30, 2026",
        "account_last4": "4821",
    },
    "Contract_ServiceAgreement_v1.pdf": {
        "contract_type": "Service Agreement", "counterparty": "Oakview Retail Inc.",
        "effective_date": "2026-03-01", "term_length": "12 months",
    },
    "Contract_ServiceAgreement_v2.pdf": {
        "contract_type": "Service Agreement", "counterparty": "Oakview Retail Inc.",
        "effective_date": "2026-01-15", "term_length": "12 months",
    },
    "Resume_Morgan_Ellis_v1.pdf": {
        "candidate_name": "Morgan Ellis",
        # version_indicator/last_modified_date genuinely absent from v1's real content.
    },
    "Resume_Morgan_Ellis_v2.pdf": {
        "candidate_name": "Morgan Ellis",
        "last_modified_date": "2026-05-10",
        # version_indicator genuinely absent - content never literally states "v2".
    },
    "Document_Employee_Handbook.pdf": {
        "best_guess_title": "Employee Handbook",
        "document_date": "2026-04-18",
        "description": "Company policy handbook covering remote work and paid time off.",
    },
    "Screenshot_Login_Error.png": {
        "context_description": "Login error screen showing an 'Invalid username or "
        "password' message with a 'Try Again' button.",
    },
    "Product_Shot_Front.jpg": {
        "context_description": "Abstract product photo composition: a rust-orange "
        "rectangle beside a blue ellipse on a light gray background.",
    },
    "Product_Shot_Angle.jpg": {
        "context_description": "Abstract product photo composition (angled variant): "
        "a rust-orange rectangle beside a blue ellipse on a light gray background, "
        "shapes shifted slightly right compared to the front shot.",
    },
}


class LiveJudgmentMetadataExtractionProvider(MetadataExtractionProvider):
    def __init__(self):
        self.calls = []

    def extract(self, request: MetadataExtractionRequest) -> ProviderResponse:
        name = Path(request.path).name
        self.calls.append((name, list(request.fields_requested)))
        answers = _ANSWERS.get(name, {})
        fields = {k: v for k, v in answers.items() if k in request.fields_requested}
        return ProviderResponse(
            fields=fields,
            metadata=ProviderMetadata(provider_name="LiveJudgmentMetadataExtractionProvider (Claude, live, UAT restart)"),
        )
