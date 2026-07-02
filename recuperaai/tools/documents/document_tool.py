from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from recuperaai.core.exceptions import ImportErrorRecoverable, ValidationError
from recuperaai.database.models import Session
from recuperaai.tools.base import ToolBase

CLIENT_DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg', '.txt'}
CLIENT_DOCUMENT_CATEGORIES = {'contract', 'corporate', 'report', 'other'}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


class DocumentTool(ToolBase):
    name = 'documents'
    label = 'Documentos'

    def list_for_client(self, session: Session, client_id: int, category: str | None = None):
        self.engine.auth.require(session, 'documents_read')
        return self.engine.documents.list_for_client(client_id, category=category)

    def list_contracts_for_client(self, session: Session, client_id: int):
        self.engine.auth.require(session, 'documents_read')
        return self.engine.documents.list_for_client(client_id, category='contract')

    def list_client_files(self, session: Session, client_id: int):
        self.engine.auth.require(session, 'documents_read')
        return self.engine.documents.list_client_files(client_id)

    def get_document(self, session: Session, document_id: int):
        self.engine.auth.require(session, 'documents_read')
        return self.engine.documents.get(document_id)

    def add_client_document(self, session: Session, client_id: int, file_path: str | Path, category: str = 'contract'):
        self.engine.auth.require(session, 'documents_write')
        category = (category or '').strip().lower()
        if category not in CLIENT_DOCUMENT_CATEGORIES:
            raise ValidationError('Categoria de documento inválida.')
        client = self.engine.clients.get(client_id)
        if not client:
            raise ValidationError('Cliente não encontrado.')
        if client.status == 'archived':
            raise ValidationError('Cliente arquivado. Restaure o cadastro antes de anexar documentos.')
        source = Path(file_path)
        if not source.exists() or not source.is_file():
            raise ImportErrorRecoverable('Arquivo não encontrado.')
        suffix = source.suffix.lower()
        if suffix not in CLIENT_DOCUMENT_EXTENSIONS:
            raise ImportErrorRecoverable('Formato de documento não suportado.')
        digest = sha256_file(source)
        duplicate = self.engine.documents.get_duplicate(client_id, digest)
        if duplicate:
            raise ImportErrorRecoverable('Documento já cadastrado para este cliente.')
        target_dir = self.engine.paths.storage / 'client_docs' / str(client_id) / category / digest[:2]
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = ''.join(ch if ch.isalnum() or ch in '._- ' else '_' for ch in source.name)
        target = target_dir / f'{digest[:12]}_{safe_name}'
        shutil.copy2(source, target)
        doc = self.engine.documents.create_import(client_id, source.name, suffix.lstrip('.'), target, digest, session.user_id, category=category)
        self.engine.documents.set_status(doc.id, 'stored')
        self.engine.audit.record(session.user_id, 'DOCUMENTO_CLIENTE_ADICIONADO', 'document', doc.id, f'{category}: {source.name}')
        self.engine.events.publish('client.document.added', client_id=client_id, document_id=doc.id)
        return self.engine.documents.get(doc.id)

    def open_path(self, session: Session, document_id: int) -> Path | None:
        self.engine.auth.require(session, 'documents_read')
        doc = self.engine.documents.get(document_id)
        return Path(doc.storage_path) if doc else None

    def delete_document(self, session: Session, document_id: int):
        doc = self.engine.documents.get(document_id)
        if not doc:
            raise ValidationError('Documento não encontrado.')
        if doc.category == 'invoice':
            self.engine.auth.require(session, 'invoices_delete')
            action = 'NOTA_FISCAL_EXCLUIDA'
        else:
            self.engine.auth.require(session, 'documents_delete')
            action = 'DOCUMENTO_CLIENTE_EXCLUIDO'

        storage_path = Path(doc.storage_path)
        deleted = self.engine.documents.delete(document_id)
        if not deleted:
            raise ValidationError('Documento não encontrado.')

        file_note = ''
        try:
            storage_root = self.engine.paths.storage.resolve()
            resolved = storage_path.resolve()
            resolved.relative_to(storage_root)
            resolved.unlink(missing_ok=True)
            file_note = ' | arquivo removido'
        except Exception as exc:
            file_note = f' | arquivo físico não removido: {exc.__class__.__name__}'

        self.engine.audit.record(session.user_id, action, 'document', document_id, f'{doc.original_name}{file_note}')
        self.engine.events.publish('document.deleted', document_id=document_id, client_id=doc.client_id, category=doc.category)
        return doc
