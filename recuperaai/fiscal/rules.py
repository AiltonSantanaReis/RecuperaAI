from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from recuperaai.fiscal.models import InvoiceData, InvoiceItem


@dataclass
class FindingDraft:
    severity: str
    code: str
    title: str
    message: str
    amount: float | None = None
    field: str | None = None
    source: str = 'local'

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class FiscalRule(Protocol):
    code: str
    title: str

    def evaluate(self, invoice: InvoiceData, context: dict) -> list[FindingDraft]:
        ...


class MissingTotalRule:
    code = 'TOTAL_AUSENTE'
    title = 'Valor total não identificado'

    def evaluate(self, invoice: InvoiceData, context: dict) -> list[FindingDraft]:
        if invoice.total_amount is None:
            return [FindingDraft('warning', self.code, self.title, 'Não foi possível identificar o valor total da nota.', field='total_amount')]
        return []


class ItemSumMismatchRule:
    code = 'SOMA_ITENS_DIVERGENTE'
    title = 'Soma dos itens diferente do total'

    def evaluate(self, invoice: InvoiceData, context: dict) -> list[FindingDraft]:
        if invoice.total_amount is None or not invoice.items:
            return []
        values = [item.total_value for item in invoice.items if item.total_value is not None]
        if not values:
            return []
        item_sum = round(sum(values), 2)
        total = round(invoice.total_amount, 2)
        tolerance = float(context.get('tolerance', 0.05))
        diff = round(abs(item_sum - total), 2)
        # Em NF-e pode haver frete/desconto/seguro. Por isso a regra é aviso, não inconsistência crítica.
        if diff > tolerance and invoice.products_total is None:
            return [FindingDraft('warning', self.code, self.title, f'A soma dos itens ({item_sum:.2f}) difere do total da nota ({total:.2f}).', amount=diff, field='items.total_value')]
        return []


class MissingTaxHighlightsRule:
    code = 'TRIBUTOS_NAO_IDENTIFICADOS'
    title = 'Tributos não destacados'

    def evaluate(self, invoice: InvoiceData, context: dict) -> list[FindingDraft]:
        if invoice.source_type == 'pdf':
            return []
        if not invoice.taxes and invoice.total_amount and invoice.total_amount > 0:
            return [FindingDraft('info', self.code, self.title, 'Não foram encontrados tributos destacados no documento importado.', field='taxes')]
        return []


class MissingInvoiceKeyRule:
    code = 'CHAVE_NAO_IDENTIFICADA'
    title = 'Chave da nota não identificada'

    def evaluate(self, invoice: InvoiceData, context: dict) -> list[FindingDraft]:
        if not invoice.invoice_key:
            severity = 'warning' if invoice.source_type == 'xml' else 'info'
            return [FindingDraft(severity, self.code, self.title, 'A chave de acesso da nota não foi identificada.', field='invoice_key')]
        return []


class PdfLimitedConfidenceRule:
    code = 'PDF_BAIXA_CONFIANCA'
    title = 'PDF exige conferência'

    def evaluate(self, invoice: InvoiceData, context: dict) -> list[FindingDraft]:
        if invoice.source_type != 'pdf':
            return []
        return [FindingDraft('warning', self.code, self.title, 'PDF analisado com confiança limitada. Para resultado fiscal preciso, importe o XML correspondente ou use API documental/OCR.', field='source_type')]


_VALID_CST_ICMS = {'00', '10', '20', '30', '40', '41', '50', '51', '60', '70', '90'}
_VALID_CSOSN = {'101', '102', '103', '201', '202', '203', '300', '400', '500', '900'}
_SIMPLES_CRT = {'1', '2', '4'}
_NORMAL_CRT = {'3'}
_CFOP_RE = re.compile(r'^[1-7][0-9]{3}$')
_NCM_RE = re.compile(r'^[0-9]{8}$')
_EXPECTED_CFOP_PREFIX = {
    ('entrada', 'interna'): '1',
    ('entrada', 'interestadual'): '2',
    ('entrada', 'exterior'): '3',
    ('saida', 'interna'): '5',
    ('saida', 'interestadual'): '6',
    ('saida', 'exterior'): '7',
}


def _digits(value: str | None) -> str | None:
    if not value:
        return None
    clean = re.sub(r'\D', '', str(value))
    return clean or None


def _is_product_document(invoice: InvoiceData) -> bool:
    return (invoice.model in {'55', '65'} or invoice.document_type in {'NF-e', 'NFC-e'}) and invoice.source_type != 'pdf'


def _is_product_item(item: InvoiceItem) -> bool:
    return not item.service_code and bool(item.description or item.ncm or item.cfop or item.total_value is not None)


def _item_label(index: int, item: InvoiceItem) -> str:
    base = f'item {index + 1}'
    if item.code:
        base += f' ({item.code})'
    return base


class FiscalClassificationRule:
    """Validações fiscais iniciais sobre CFOP, CST, CSOSN e NCM.

    Esta regra é propositalmente conservadora. Ela identifica combinações suspeitas
    e campos ausentes/formatos inválidos para revisão do analista, mas não declara
    crédito tributário definitivo nem substitui validação por legislação estadual,
    municipal ou regra de negócio especializada.
    """

    code = 'CLASSIFICACAO_FISCAL'
    title = 'Classificação fiscal exige revisão'

    def evaluate(self, invoice: InvoiceData, context: dict) -> list[FindingDraft]:
        if not _is_product_document(invoice):
            return []

        findings: list[FindingDraft] = []
        expected_cfop_prefix = _EXPECTED_CFOP_PREFIX.get((invoice.operation_type, invoice.operation_scope))
        crt = _digits(invoice.issuer_tax_regime)

        for index, item in enumerate(invoice.items):
            if not _is_product_item(item):
                continue
            label = _item_label(index, item)
            ncm = _digits(item.ncm)
            cfop = _digits(item.cfop)
            cst = _digits(item.cst)
            csosn = _digits(item.csosn)

            findings.extend(self._evaluate_ncm(label, ncm))
            findings.extend(self._evaluate_cfop(label, cfop, invoice, expected_cfop_prefix))
            findings.extend(self._evaluate_tax_code(label, cst, csosn, crt))

        return findings

    def _evaluate_ncm(self, label: str, ncm: str | None) -> list[FindingDraft]:
        if not ncm:
            return [FindingDraft(
                'warning',
                'NCM_AUSENTE',
                'NCM não informado no item',
                f'O {label} não possui NCM identificado. Revise a classificação fiscal antes de concluir a análise.',
                field='items.ncm',
            )]
        if not _NCM_RE.match(ncm) or ncm == '00000000':
            return [FindingDraft(
                'warning',
                'NCM_FORMATO_INVALIDO',
                'NCM com formato inválido',
                f'O {label} possui NCM "{ncm}". O NCM deve conter 8 dígitos e não pode ser genérico.',
                field='items.ncm',
            )]
        return []

    def _evaluate_cfop(
        self,
        label: str,
        cfop: str | None,
        invoice: InvoiceData,
        expected_prefix: str | None,
    ) -> list[FindingDraft]:
        if not cfop:
            return [FindingDraft(
                'warning',
                'CFOP_AUSENTE',
                'CFOP não informado no item',
                f'O {label} não possui CFOP identificado. Sem CFOP não é possível validar a natureza da operação.',
                field='items.cfop',
            )]
        if not _CFOP_RE.match(cfop):
            return [FindingDraft(
                'warning',
                'CFOP_FORMATO_INVALIDO',
                'CFOP com formato inválido',
                f'O {label} possui CFOP "{cfop}". O CFOP deve conter 4 dígitos e iniciar entre 1 e 7.',
                field='items.cfop',
            )]
        if expected_prefix and not cfop.startswith(expected_prefix):
            return [FindingDraft(
                'warning',
                'CFOP_INCOMPATIVEL_OPERACAO',
                'CFOP incompatível com a operação',
                f'O {label} possui CFOP {cfop}, mas a nota indica operação de {invoice.operation_type} {invoice.operation_scope}. '
                f'O prefixo esperado seria {expected_prefix}.xxx.',
                field='items.cfop',
            )]
        return []

    def _evaluate_tax_code(self, label: str, cst: str | None, csosn: str | None, crt: str | None) -> list[FindingDraft]:
        findings: list[FindingDraft] = []
        if not cst and not csosn:
            findings.append(FindingDraft(
                'warning',
                'CST_CSOSN_AUSENTE',
                'CST/CSOSN não identificado',
                f'O {label} não possui CST ou CSOSN de ICMS identificado.',
                field='items.cst_csosn',
            ))
            return findings

        if cst and csosn:
            findings.append(FindingDraft(
                'warning',
                'CST_CSOSN_DUPLO',
                'CST e CSOSN informados simultaneamente',
                f'O {label} possui CST {cst} e CSOSN {csosn}. Normalmente o item deve seguir um único enquadramento conforme o regime tributário.',
                field='items.cst_csosn',
            ))

        if cst and cst not in _VALID_CST_ICMS:
            findings.append(FindingDraft(
                'warning',
                'CST_ICMS_INVALIDO',
                'CST de ICMS não reconhecido',
                f'O {label} possui CST {cst}, que não está na tabela básica de CST ICMS esperada pelo motor local.',
                field='items.cst',
            ))
        if csosn and csosn not in _VALID_CSOSN:
            findings.append(FindingDraft(
                'warning',
                'CSOSN_INVALIDO',
                'CSOSN não reconhecido',
                f'O {label} possui CSOSN {csosn}, que não está na tabela básica de CSOSN esperada pelo motor local.',
                field='items.csosn',
            ))

        if crt in _SIMPLES_CRT and cst and not csosn:
            findings.append(FindingDraft(
                'warning',
                'REGIME_TRIBUTARIO_INCOMPATIVEL',
                'CST/CSOSN incompatível com o regime do emitente',
                f'O emitente está com CRT {crt}, mas o {label} possui CST sem CSOSN. Revise se o enquadramento do ICMS está correto.',
                field='issuer_tax_regime',
            ))
        if crt in _NORMAL_CRT and csosn and not cst:
            findings.append(FindingDraft(
                'warning',
                'REGIME_TRIBUTARIO_INCOMPATIVEL',
                'CST/CSOSN incompatível com o regime do emitente',
                f'O emitente está com CRT {crt}, mas o {label} possui CSOSN sem CST. Revise se o enquadramento do ICMS está correto.',
                field='issuer_tax_regime',
            ))
        return findings
