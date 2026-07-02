from __future__ import annotations

import json

from recuperaai.core.exceptions import ValidationError
from recuperaai.database.models import Session
from recuperaai.fiscal.models import InvoiceData
from recuperaai.tools.base import ToolBase


REVIEW_STATUSES = {
    'open': 'Aberta',
    'confirmed': 'Confirmada',
    'rejected': 'Rejeitada',
    'in_review': 'Em revisão',
    'pending_document': 'Pendente de documento',
    'waiting_client': 'Aguardando cliente',
    'exported': 'Exportada em relatório',
}


class AnalysisTool(ToolBase):
    name = 'analysis'
    label = 'Análises'

    def analyze_document(self, session: Session, document_id: int) -> list[dict]:
        self.engine.auth.require(session, 'analysis_run')
        doc = self.engine.documents.get(document_id)
        if not doc:
            raise ValidationError('Documento não encontrado.')
        client = self.engine.clients.get(doc.client_id)
        if client and client.status == 'archived':
            raise ValidationError('Cliente arquivado. Restaure o cadastro antes de executar novas análises.')
        if not doc.payload_json:
            findings = [{
                'severity': 'warning', 'code': 'DOCUMENTO_NAO_LIDO', 'title': 'Documento não lido',
                'message': 'O documento não possui dados suficientes para análise.', 'source': 'local'
            }]
        else:
            payload = json.loads(doc.payload_json)
            invoice = InvoiceData.from_dict(payload)
            findings = self.engine.rule_engine.analyze(invoice)
            api_payload = self.engine.api_client().build_analysis_payload(
                payload,
                client={
                    'id': client.id,
                    'name': client.name,
                    'document': client.document,
                    'status': client.status,
                } if client else {},
                document={
                    'id': doc.id,
                    'file_name': doc.original_name,
                    'file_type': doc.file_type,
                    'invoice_key': doc.invoice_key,
                    'issue_date': doc.issue_date,
                    'total_amount': doc.total_amount,
                },
            )
            findings.extend(self.engine.api_client().analyze(api_payload))
        self.engine.findings.clear_for_document(document_id)
        if findings:
            self.engine.findings.add_many(document_id, findings)
            self.engine.documents.set_status(document_id, 'attention')
        else:
            self.engine.documents.set_status(document_id, 'clear')
        self.engine.audit.record(session.user_id, 'DOCUMENTO_ANALISADO', 'document', document_id, f'{len(findings)} apontamentos')
        self.engine.events.publish('document.analyzed', document_id=document_id, findings=len(findings))
        return findings

    def analyze_client(self, session: Session, client_id: int) -> dict:
        self.engine.auth.require(session, 'analysis_run')
        client = self.engine.clients.get(client_id)
        if not client:
            raise ValidationError('Cliente não encontrado.')
        if client.status == 'archived':
            raise ValidationError('Cliente arquivado. Restaure o cadastro antes de executar novas análises.')
        docs = self.engine.documents.list_for_client(client_id, category='invoice')
        total_findings = 0
        analyzed = 0
        failed = []
        for doc in docs:
            try:
                total_findings += len(self.analyze_document(session, doc.id))
                analyzed += 1
            except Exception as exc:
                failed.append({'document_id': doc.id, 'message': str(exc)})
        self.engine.audit.record(session.user_id, 'CLIENTE_REANALISADO', 'client', client_id, f'{analyzed} documentos, {total_findings} apontamentos')
        return {'analyzed': analyzed, 'findings': total_findings, 'failed': failed}

    def list_open_for_client(self, session: Session, client_id: int):
        self.engine.auth.require(session, 'analysis_read')
        return self.engine.findings.list_open_for_client(client_id)

    def list_for_client(self, session: Session, client_id: int, only_open: bool = False):
        self.engine.auth.require(session, 'analysis_read')
        return self.engine.findings.list_for_client(client_id, only_open=only_open)

    def review_finding(self, session: Session, finding_id: int, status: str, note: str | None = None) -> dict:
        self.engine.auth.require(session, 'findings_review')
        status = (status or '').strip().lower()
        if status not in REVIEW_STATUSES:
            raise ValidationError('Status de revisão inválido.')
        finding = self.engine.findings.get(finding_id)
        if not finding:
            raise ValidationError('Inconsistência não encontrada.')
        client = self.engine.clients.get(int(finding['client_id']))
        if client and client.status == 'archived':
            raise ValidationError('Cliente arquivado. Restaure o cadastro antes de alterar revisões.')
        self.engine.findings.update_review(finding_id, status, note, session.user_id)
        self.engine.audit.record(
            session.user_id,
            'INCONSISTENCIA_REVISADA',
            'document',
            int(finding['document_id']),
            f"{finding.get('code')}: {REVIEW_STATUSES[status]}" + (f" | {note}" if note else ''),
        )
        self.engine.events.publish('finding.reviewed', finding_id=finding_id, status=status)
        updated = self.engine.findings.get(finding_id)
        return updated or {}

    def dashboard(self, session: Session) -> dict:
        self.engine.auth.require(session, 'dashboard_view')
        return {
            'clients': self.engine.clients.dashboard_counts(),
            'documents': self.engine.documents.dashboard_summary(),
            'findings': self.engine.findings.dashboard_counts(),
            'opportunities': self.engine.findings.opportunity_summary(),
            'opportunities_by_client': self.engine.findings.opportunities_by_client(20),
            'recent_documents': self.engine.documents.list_recent(20),
        }
