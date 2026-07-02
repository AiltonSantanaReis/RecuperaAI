from __future__ import annotations

import re

_PREFIX_RE = re.compile(r'^(?:NFe|NFCe|CTe|NFSe|Nfse|Id|ID)[:\-\s_]*', re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r'[^0-9A-Za-z]')


def normalize_invoice_key(value: object) -> str | None:
    """Normaliza chaves fiscais para comparação e bloqueio de duplicidade.

    NF-e/NFC-e/CT-e usam chave de acesso de 44 dígitos. Para outros modelos
    com chaves/códigos alfanuméricos, preserva uma forma compacta em maiúsculas.
    Retorna None quando não há valor útil.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    text = _PREFIX_RE.sub('', text).strip()

    # Quando o texto contém exatamente uma chave de acesso de 44 dígitos com
    # pontuação/espaços no meio, usa somente os dígitos como chave canônica.
    digits = re.sub(r'\D', '', text)
    if len(digits) == 44:
        return digits

    compact = _NON_ALNUM_RE.sub('', text).upper()
    compact = _PREFIX_RE.sub('', compact).strip()
    return compact or None


def same_invoice_key(left: object, right: object) -> bool:
    normalized_left = normalize_invoice_key(left)
    normalized_right = normalize_invoice_key(right)
    return bool(normalized_left and normalized_left == normalized_right)
