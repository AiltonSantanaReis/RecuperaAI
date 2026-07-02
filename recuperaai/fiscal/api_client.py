from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Any


@dataclass
class ApiConfig:
    enabled: bool = False
    base_url: str = ""
    token: str = ""
    timeout: int = 30


class FiscalApiClient:
    """Cliente para serviço externo de análise fiscal.

    Contrato esperado:
    POST {base_url}/analyze
    Authorization: Bearer <token>
    Body: JSON produzido por ``build_analysis_payload``.
    Resposta: {"findings": [{severity, code, title, message, amount, field}]}

    Também aceita {"opportunities": [...]} para serviços que separam indícios
    de recuperação fiscal dos demais apontamentos.
    """

    def __init__(self, config: ApiConfig) -> None:
        self.config = config

    @staticmethod
    def build_analysis_payload(
        invoice_payload: dict[str, Any],
        *,
        client: dict[str, Any] | None = None,
        document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        items = invoice_payload.get('items') or []
        taxes = invoice_payload.get('taxes') or {}
        missing = []
        for key, label in [
            ('invoice_key', 'chave fiscal'),
            ('issuer_document', 'documento do emitente'),
            ('recipient_document', 'documento do destinatário'),
            ('issuer_state', 'UF do emitente'),
            ('recipient_state', 'UF do destinatário'),
            ('issue_date', 'data de emissão'),
            ('total_amount', 'valor total'),
        ]:
            if not invoice_payload.get(key):
                missing.append(label)
        if not items:
            missing.append('itens da nota')
        if not taxes:
            missing.append('impostos destacados')

        source_type = invoice_payload.get('source_type')
        warnings = invoice_payload.get('warnings') or []
        has_raw_text = bool(invoice_payload.get('raw_text'))
        confidence = 'structured' if source_type == 'xml' else 'limited'
        if source_type == 'pdf' and (not items or not taxes):
            confidence = 'requires_document_review'

        return {
            'schema_version': '1.0',
            'analysis_goal': 'identify_review_points_and_possible_tax_opportunities',
            'client': client or {},
            'document': document or {},
            'invoice': invoice_payload,
            'data_quality': {
                'source_type': source_type,
                'confidence': confidence,
                'has_raw_text': has_raw_text,
                'warnings': warnings,
            },
            'readiness': {
                'has_items': bool(items),
                'has_taxes': bool(taxes),
                'missing': missing,
            },
        }

    @staticmethod
    def _normalize_finding(item: dict[str, Any], *, opportunity: bool = False) -> dict[str, Any]:
        severity = str(item.get('severity') or ('warning' if opportunity else 'info')).lower()
        if severity not in {'critical', 'warning', 'info'}:
            severity = 'info'
        title = str(item.get('title') or ('Possível oportunidade fiscal' if opportunity else 'Apontamento da análise avançada')).strip()
        message = str(item.get('message') or item.get('description') or title).strip()
        confidence = item.get('confidence')
        if confidence:
            message = f'{message} Confiança informada: {confidence}.'
        amount = item.get('amount')
        try:
            amount = float(amount) if amount not in (None, '') else None
        except Exception:
            amount = None
        return {
            'severity': severity,
            'code': str(item.get('code') or ('POSSIVEL_OPORTUNIDADE' if opportunity else 'ANALISE_AVANCADA')).strip()[:80],
            'title': title,
            'message': message,
            'amount': amount,
            'field': item.get('field') or ('tax_opportunity' if opportunity else None),
            'source': 'api',
        }

    @classmethod
    def normalize_response(cls, data: dict[str, Any]) -> list[dict[str, Any]]:
        findings = [
            cls._normalize_finding(item)
            for item in data.get('findings', [])
            if isinstance(item, dict)
        ]
        findings.extend(
            cls._normalize_finding(item, opportunity=True)
            for item in data.get('opportunities', [])
            if isinstance(item, dict)
        )
        return findings

    def analyze(self, invoice_payload: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.config.enabled or not self.config.base_url:
            return []
        import requests

        headers = {"Content-Type": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        url = self.config.base_url.rstrip('/') + '/analyze'
        last_error = 'sem resposta'
        for attempt in range(3):
            try:
                response = requests.post(url, json=invoice_payload, headers=headers, timeout=self.config.timeout)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    last_error = 'resposta inválida'
                    break
                return self.normalize_response(data)
            except requests.RequestException as exc:
                last_error = exc.__class__.__name__
            except ValueError:
                last_error = 'resposta JSON inválida'
                break
            if attempt < 2:
                sleep(0.4 * (attempt + 1))
        return [{
            'severity': 'warning',
            'code': 'API_INDISPONIVEL',
            'title': 'Motor externo indisponível',
            'message': f'A API de inconsistências não respondeu corretamente ({last_error}).',
            'source': 'api',
        }]
