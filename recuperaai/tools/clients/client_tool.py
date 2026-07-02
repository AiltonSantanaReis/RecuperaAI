from __future__ import annotations

from dataclasses import asdict
from typing import Any

from recuperaai.core.exceptions import ValidationError
from recuperaai.database.models import Client, Document, Session
from recuperaai.tools.base import ToolBase


def _client_to_dict(client: Client) -> dict[str, Any]:
    return asdict(client)


def _document_to_dict(document: Document) -> dict[str, Any]:
    return asdict(document)


def _clean_text(value: str | None) -> str:
    return (value or '').strip()


CLIENT_STATUSES = {'active', 'inactive', 'paused', 'archived'}


class ClientTool(ToolBase):
    name = 'clients'
    label = 'Clientes'

    def create_client(self, session: Session, name: str, document: str | None = None, contact_name: str | None = None,
                      email: str | None = None, phone: str | None = None, notes: str | None = None):
        self.engine.auth.require(session, 'clients_write')
        name = _clean_text(name)
        if not name:
            raise ValidationError('Informe o nome do cliente.')
        client = self.engine.clients.create(
            name,
            _clean_text(document),
            _clean_text(contact_name),
            _clean_text(email),
            _clean_text(phone),
            _clean_text(notes),
        )
        self.engine.audit.record(session.user_id, 'CLIENTE_CRIADO', 'client', client.id, client.name)
        self.engine.events.publish('client.created', client_id=client.id)
        return client

    def update_client(self, session: Session, client_id: int, **fields):
        self.engine.auth.require(session, 'clients_write')
        if 'name' in fields:
            fields['name'] = _clean_text(fields.get('name'))
            if not fields['name']:
                raise ValidationError('Informe o nome do cliente.')
        for key in ('document', 'contact_name', 'email', 'phone', 'notes', 'status'):
            if key in fields and isinstance(fields[key], str):
                fields[key] = fields[key].strip()
        if 'status' in fields:
            fields['status'] = _clean_text(fields.get('status')).lower()
            if fields['status'] not in CLIENT_STATUSES:
                raise ValidationError('Situação do cliente inválida.')
            if fields['status'] == 'archived':
                raise ValidationError('Use a ação de arquivar cliente para preservar a auditoria corretamente.')
        client = self.engine.clients.update(client_id, **fields)
        if not client:
            raise ValidationError('Cliente não encontrado.')
        self.engine.audit.record(session.user_id, 'CLIENTE_ATUALIZADO', 'client', client_id, str(fields))
        self.engine.events.publish('client.updated', client_id=client_id)
        return client

    def archive_client(self, session: Session, client_id: int):
        self.engine.auth.require(session, 'clients_write')
        client = self.engine.clients.get(client_id)
        if not client:
            raise ValidationError('Cliente não encontrado.')
        if client.status == 'archived':
            return client
        archived = self.engine.clients.update(client_id, status='archived')
        self.engine.audit.record(
            session.user_id,
            'CLIENTE_ARQUIVADO',
            'client',
            client_id,
            'Cliente removido das telas operacionais; dados, documentos e histórico preservados.',
        )
        self.engine.events.publish('client.archived', client_id=client_id)
        return archived

    def restore_client(self, session: Session, client_id: int):
        self.engine.auth.require(session, 'clients_write')
        client = self.engine.clients.get(client_id)
        if not client:
            raise ValidationError('Cliente não encontrado.')
        if client.status != 'archived':
            return client
        restored = self.engine.clients.update(client_id, status='active')
        self.engine.audit.record(
            session.user_id,
            'CLIENTE_RESTAURADO',
            'client',
            client_id,
            'Cliente restaurado para as telas operacionais.',
        )
        self.engine.events.publish('client.restored', client_id=client_id)
        return restored

    def list_clients(
        self,
        session: Session,
        term: str | None = None,
        include_archived: bool = False,
        archived_only: bool = False,
    ):
        self.engine.auth.require(session, 'clients_read')
        return self.engine.clients.list_all(term, include_archived=include_archived, archived_only=archived_only)

    def get_client(self, session: Session, client_id: int):
        self.engine.auth.require(session, 'clients_read')
        return self.engine.clients.get(client_id)

    def get_client_workspace(self, session: Session, client_id: int) -> dict[str, Any]:
        """Retorna a visão 360º do cliente para a tela de cadastro.

        A tela completa do cliente não deve montar informações por consultas soltas
        espalhadas na UI. Este método consolida dados cadastrais, notas fiscais,
        contratos, documentos avulsos, resumo operacional e apontamentos abertos.
        """
        self.engine.auth.require(session, 'clients_read')
        self.engine.auth.require(session, 'documents_read')
        self.engine.auth.require(session, 'analysis_read')

        client = self.engine.clients.get(client_id)
        if not client:
            raise ValidationError('Cliente não encontrado.')

        all_documents = self.engine.documents.list_for_client(client_id)
        invoices = [doc for doc in all_documents if doc.category == 'invoice']
        contracts = [doc for doc in all_documents if doc.category == 'contract']
        client_documents = [doc for doc in all_documents if doc.category not in {'invoice', 'contract'}]
        open_findings = self.engine.findings.list_open_for_client(client_id)
        all_findings = self.engine.findings.list_for_client(client_id, only_open=False)
        document_summary = self.engine.documents.summary_for_client(client_id)
        finding_summary = self.engine.findings.counts_for_client(client_id)
        finding_status_summary = self.engine.findings.status_counts_for_client(client_id)
        opportunity_summary = self.engine.findings.opportunity_summary(client_id)
        history = self.engine.audit_repo.for_client(client_id)
        import_history = self.engine.audit_repo.import_history_for_client(client_id)
        reports = self.engine.tool('reports').list_client_reports(session, client_id)

        return {
            'client': _client_to_dict(client),
            'summary': {
                'documents_total': document_summary['total_documents'],
                'invoices_total': document_summary['by_category'].get('invoice', 0),
                'contracts_total': document_summary['by_category'].get('contract', 0),
                'client_documents_total': sum(
                    count for category, count in document_summary['by_category'].items()
                    if category not in {'invoice', 'contract'}
                ),
                'attention_documents': document_summary['by_status'].get('attention', 0),
                'clear_documents': document_summary['by_status'].get('clear', 0),
                'parse_errors': document_summary['by_status'].get('parse_error', 0),
                'waiting_analysis': document_summary['by_status'].get('parsed', 0) + document_summary['by_status'].get('imported', 0),
                'total_invoice_amount': document_summary['total_invoice_amount'],
                'last_document_at': document_summary['last_document_at'],
                'findings': finding_summary,
                'finding_status': finding_status_summary,
                'open_findings_total': sum(finding_summary.values()),
                'opportunities': opportunity_summary,
                'reports_total': len(reports),
                'history_total': len(history),
            },
            'invoices': [_document_to_dict(doc) for doc in invoices],
            'contracts': [_document_to_dict(doc) for doc in contracts],
            'client_documents': [_document_to_dict(doc) for doc in client_documents],
            'all_documents': [_document_to_dict(doc) for doc in all_documents],
            'open_findings': open_findings,
            'all_findings': all_findings,
            'import_history': import_history,
            'reports': reports,
            'history': history,
        }
