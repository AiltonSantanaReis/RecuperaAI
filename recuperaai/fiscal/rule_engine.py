from __future__ import annotations

from recuperaai.fiscal.models import InvoiceData
from recuperaai.fiscal.rules import (
    FiscalRule,
    MissingTotalRule,
    ItemSumMismatchRule,
    MissingTaxHighlightsRule,
    MissingInvoiceKeyRule,
    PdfLimitedConfidenceRule,
    FiscalClassificationRule,
)


class FiscalRuleEngine:
    def __init__(self, rules: list[FiscalRule] | None = None) -> None:
        self.rules = rules or [
            MissingInvoiceKeyRule(),
            MissingTotalRule(),
            ItemSumMismatchRule(),
            MissingTaxHighlightsRule(),
            FiscalClassificationRule(),
            PdfLimitedConfidenceRule(),
        ]

    def analyze(self, invoice: InvoiceData, context: dict | None = None) -> list[dict]:
        context = context or {}
        findings = []
        for warning in invoice.warnings:
            findings.append({
                'severity': 'info',
                'code': 'LEITURA_DOCUMENTO',
                'title': 'Observação da leitura',
                'message': warning,
                'field': 'parser',
                'source': 'local',
            })
        for rule in self.rules:
            findings.extend([item.to_dict() for item in rule.evaluate(invoice, context)])
        return findings
