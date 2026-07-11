"""Live-judgment ClassificationProvider for the Module 06 UAT restart (2026-07-11).

Each answer below reflects my own real reading of the actual generated file content
(confirmed via a direct core/pdf.py extract_text() pass before writing this class).
Keyed by real file basename, matched against request.path. Mirrors the exact
per-file judgments used in the original Run 1 (same dataset design, same real
content), since the goal of this restart is to hold every variable constant except
the corrected Module 01.
"""
from pathlib import Path

from src.pipeline.classification import (
    ClassificationProvider,
    ClassificationRequest,
    ClassificationResult,
    ProviderResponse,
    ProviderMetadata,
)

_ANSWERS = {
    "Invoice_Northwind_Traders.pdf": ClassificationResult(category="Invoice"),
    "Invoice_Sparse_Draft.pdf": ClassificationResult(category="Invoice"),
    "Receipt_Or_Invoice_Ambiguous.pdf": ClassificationResult(category="Invoice", ambiguous=True),
    "Facture_Boulangerie_Paris.pdf": ClassificationResult(category="Invoice"),
    "Batch_Invoices_Merged.pdf": ClassificationResult(category="Invoice", multi_document_detected=True),
    "invoice_\U0001F9FE_northstar_—_v2.pdf": ClassificationResult(category="Invoice"),
    "BankStatement_Chase_June2026.pdf": ClassificationResult(category="Bank Statement"),
    "BankStatement_Chase_June2026_copy.pdf": ClassificationResult(category="Bank Statement"),
    "Contract_ServiceAgreement_v1.pdf": ClassificationResult(category="Contract"),
    "Contract_ServiceAgreement_v2.pdf": ClassificationResult(category="Contract"),
    "Resume_Morgan_Ellis_v1.pdf": ClassificationResult(category="Resume"),
    "Resume_Morgan_Ellis_v2.pdf": ClassificationResult(category="Resume"),
    "Document_Employee_Handbook.pdf": ClassificationResult(category="Document"),
    "Scan_Blank_Page.pdf": ClassificationResult(category="Unknown", notes="blank page, no content"),
}


class LiveJudgmentClassificationProvider(ClassificationProvider):
    def __init__(self):
        self.calls = []

    def classify(self, request: ClassificationRequest) -> ProviderResponse:
        name = Path(request.path).name
        self.calls.append(name)
        if name not in _ANSWERS:
            raise KeyError(f"No live judgment authored for {name!r} - harness gap, not a module defect.")
        return ProviderResponse(
            result=_ANSWERS[name],
            metadata=ProviderMetadata(provider_name="LiveJudgmentClassificationProvider (Claude, live, UAT restart)"),
        )
