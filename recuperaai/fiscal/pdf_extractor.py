from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from recuperaai.fiscal.key_utils import normalize_invoice_key
from recuperaai.fiscal.models import InvoiceData


PDF_TEXT_BACKEND = 'pypdf'


_MONEY_RE = re.compile(r'(?<![\d./-])(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2})(?![\d./-])')

_TOTAL_LABELS = [
    r'valor\s+total\s+da\s+nota',
    r'valor\s+total\s+do\s+documento',
    r'valor\s+total',
    r'valor\s+da\s+nota',
    r'total\s+da\s+nota',
    r'total\s+a\s+pagar',
    r'valor\s+a\s+pagar',
    r'valor\s+liquido\s+da\s+nota',
    r'valor\s+líquido\s+da\s+nota',
    r'valor\s+liquido\s+nfse',
    r'valor\s+líquido\s+nfse',
    r'valor\s+total\s+dos\s+servicos',
    r'valor\s+total\s+dos\s+serviços',
    r'valor\s+dos\s+servicos',
    r'valor\s+dos\s+serviços',
]

_NOT_TOTAL_TERMS = [
    'capital social',
    'capital',
    'base de calculo',
    'base de cálculo',
    'valor aproximado dos tributos',
    'valor dos tributos',
    'desconto',
    'troco',
    'multa',
    'juros',
    'frete',
    'seguro',
]

_CNPJ_RE = re.compile(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b')


def _parse_money(value: str) -> float | None:
    try:
        if ',' in value:
            return float(value.replace('.', '').replace(',', '.'))
        return float(value)
    except Exception:
        return None


def _first_money(text: str) -> float | None:
    match = _MONEY_RE.search(text)
    return _parse_money(match.group(1)) if match else None


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _label_value(text: str, labels: list[str]) -> str | None:
    for line in _lines(text):
        for label in labels:
            match = re.match(rf'^\s*{label}\s*[:\-]\s*(.+?)\s*$', line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value:
                    return value
    return None


def _cnpj_from_label(text: str, labels: list[str]) -> str | None:
    value = _label_value(text, labels)
    if value:
        match = _CNPJ_RE.search(value)
        if match:
            return match.group(0)
    return None


def _date_from_label(text: str) -> str | None:
    value = _label_value(text, [r'data\s+de\s+emiss[aã]o', r'emiss[aã]o'])
    if not value:
        return None
    match = re.search(r'\b(\d{2})/(\d{2})/(\d{4})\b', value)
    if match:
        day, month, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat()
        except ValueError:
            return value
    match = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', value)
    return match.group(0) if match else value


def _is_rejected_context(text: str) -> bool:
    clean = text.lower()
    return any(term in clean for term in _NOT_TOTAL_TERMS)


def _money(text: str) -> float | None:
    """Extrai o total do PDF somente por rótulos fiscais confiáveis.

    PDFs são texto solto. Usar o maior valor encontrado gera falso positivo
    comum, por exemplo capital social, base de cálculo ou tributos aproximados.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized = [(line, re.sub(r'\s+', ' ', line.lower())) for line in lines]

    for label in _TOTAL_LABELS:
        pattern = re.compile(label, re.IGNORECASE)
        for index, (original, clean) in enumerate(normalized):
            if not pattern.search(clean):
                continue
            context = ' '.join(line for line, _ in normalized[index:index + 3])
            if _is_rejected_context(context):
                continue
            value = _first_money(context)
            if value is not None:
                return value

    fiscal_lines = [
        line for line, clean in normalized
        if _MONEY_RE.search(line) and not _is_rejected_context(clean)
    ]
    if len(fiscal_lines) == 1:
        return _first_money(fiscal_lines[0])
    return None


def _tax_value(text: str, label: str) -> float | None:
    pattern = re.compile(label, re.IGNORECASE)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if pattern.search(line):
            value = _first_money(' '.join(lines[index:index + 2]))
            if value is not None:
                return value
    return None


def _taxes(text: str) -> dict[str, float]:
    candidates = {
        'ICMS': r'\bvalor\s+do\s+icms\b|\bicms\b',
        'PIS': r'\bvalor\s+do\s+pis\b|\bpis\b',
        'COFINS': r'\bvalor\s+do\s+cofins\b|\bcofins\b',
        'ISS': r'\bvalor\s+do\s+iss\b|\biss\b',
        'TotalTributos': r'valor\s+aproximado\s+dos\s+tributos|valor\s+dos\s+tributos',
    }
    taxes: dict[str, float] = {}
    for key, label in candidates.items():
        value = _tax_value(text, label)
        if value is not None:
            taxes[key] = value
    return taxes


def _invoice_key(text: str) -> str | None:
    for match in re.finditer(r'(?:\d[\s.\-]*){44}', text):
        key = normalize_invoice_key(match.group(0))
        if key and key.isdigit() and len(key) == 44:
            return key
    return None


class PdfExtractor:
    def extract_text(self, path: Path) -> str:
        """Extrai texto de PDFs usando uma dependência permissiva e leve.

        PDFs escaneados continuam exigindo OCR externo. O extrator não tenta
        inventar dados fiscais quando não há camada textual confiável.
        """
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or '')
            return "\n".join(parts).strip()
        except Exception:
            return ""

    def parse(self, path: Path) -> InvoiceData:
        text = self.extract_text(path)
        data = InvoiceData(source_type='pdf', raw_text=text)
        if not text:
            data.warnings.append('PDF sem texto extraível. Pode ser digitalização ou imagem; requer OCR ou XML fiscal.')
            return data

        cnpj_match = _CNPJ_RE.search(text)
        data.invoice_key = _invoice_key(text)
        data.issue_date = _date_from_label(text)
        data.issuer_name = _label_value(text, [r'emitente', r'fornecedor'])
        data.recipient_name = _label_value(text, [r'destinat[aá]rio', r'tomador', r'cliente'])
        data.issuer_document = (
            _cnpj_from_label(text, [r'cnpj\s+emitente', r'cnpj\s+do\s+emitente', r'cnpj\s+fornecedor'])
            or (cnpj_match.group(0) if cnpj_match else None)
        )
        data.recipient_document = _cnpj_from_label(text, [r'cnpj\s+destinat[aá]rio', r'cnpj\s+do\s+destinat[aá]rio', r'cnpj\s+tomador', r'cnpj\s+cliente'])
        data.total_amount = _money(text)
        data.taxes = _taxes(text)
        if not data.invoice_key:
            data.warnings.append('Chave de 44 dígitos não encontrada no PDF.')
        if data.total_amount is None:
            data.warnings.append('Valor total da nota não identificado com rótulo confiável no PDF.')
        data.warnings.append('PDF não fornece itens, quantidades, CFOP, NCM e impostos de forma estruturada; valide pelo XML ou por serviço documental especializado.')
        data.warnings.append('Leitura de PDF é indicativa. Para precisão fiscal, priorize XML ou OCR homologado.')
        return data
