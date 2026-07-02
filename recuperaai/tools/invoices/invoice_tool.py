from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path
from typing import Iterable

from recuperaai.core.exceptions import ImportErrorRecoverable, ValidationError
from recuperaai.database.models import Session
from recuperaai.fiscal.key_utils import normalize_invoice_key
from recuperaai.tools.base import ToolBase

SUPPORTED = {'.xml': 'xml', '.pdf': 'pdf'}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(name: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in '._- ' else '_' for ch in name)


class InvoiceTool(ToolBase):
    name = 'invoices'
    label = 'Notas Fiscais'

    def import_files(self, session: Session, client_id: int, file_paths: Iterable[str | Path], auto_analyze: bool = True) -> dict:
        self.engine.auth.require(session, 'invoices_import')
        client = self.engine.clients.get(client_id)
        if not client:
            raise ValidationError('Cliente não encontrado.')
        if client.status == 'archived':
            raise ValidationError('Cliente arquivado. Restaure o cadastro antes de importar notas fiscais.')

        imported = []
        skipped = []
        failed = []
        for raw in file_paths:
            try:
                doc = self._import_one(session, client_id, Path(raw))
                imported.append(doc)
                if auto_analyze:
                    self.engine.tool('analysis').analyze_document(session, doc.id)
            except ImportErrorRecoverable as exc:
                skipped.append({'file': str(raw), 'message': str(exc)})
            except Exception as exc:
                failed.append({'file': str(raw), 'message': str(exc)})

        self.engine.audit.record(session.user_id, 'IMPORTACAO_EM_MASSA', 'client', client_id, f'{len(imported)} importados, {len(skipped)} ignorados, {len(failed)} falhas')
        self.engine.events.publish('invoices.imported', client_id=client_id, imported=len(imported), failed=len(failed))
        return {'imported': imported, 'skipped': skipped, 'failed': failed}

    def _import_one(self, session: Session, client_id: int, source: Path):
        if not source.exists() or not source.is_file():
            raise ImportErrorRecoverable('Arquivo não encontrado.')
        suffix = source.suffix.lower()
        if suffix not in SUPPORTED:
            raise ImportErrorRecoverable('Formato não suportado. Use XML ou PDF.')

        digest = sha256_file(source)
        duplicate_hash = self.engine.documents.get_duplicate(client_id, digest)
        if duplicate_hash:
            raise ImportErrorRecoverable('Arquivo já importado para este cliente.')

        payload: dict
        parser_status: str
        processing_status: str
        try:
            invoice = self.engine.normalizer.parse_file(source)
            payload = invoice.to_dict()
            payload['invoice_key'] = normalize_invoice_key(payload.get('invoice_key'))
            parser_status = 'ok'
            processing_status = 'parsed'
        except Exception as exc:
            payload = {'source_type': SUPPORTED[suffix], 'warnings': [str(exc)]}
            parser_status = 'error'
            processing_status = 'parse_error'

        invoice_key = normalize_invoice_key(payload.get('invoice_key'))
        if invoice_key:
            duplicate_key = self.engine.documents.get_duplicate_by_invoice_key(invoice_key)
            if duplicate_key:
                raise ImportErrorRecoverable(
                    'Nota fiscal já importada com a mesma chave fiscal. '
                    f'Chave: {invoice_key}. Documento existente: {duplicate_key.original_name}.'
                )

        target_dir = self.engine.paths.imports / str(client_id) / digest[:2]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f'{digest[:12]}_{_safe_name(source.name)}'
        shutil.copy2(source, target)

        try:
            doc = self.engine.documents.create_import(
                client_id,
                source.name,
                SUPPORTED[suffix],
                target,
                digest,
                session.user_id,
                category='invoice',
                initial_payload=payload,
                parser_status=parser_status,
            )
        except sqlite3.IntegrityError as exc:
            target.unlink(missing_ok=True)
            if 'DUPLICATE_INVOICE_KEY' in str(exc) or 'ux_documents_invoice_key' in str(exc):
                raise ImportErrorRecoverable('Nota fiscal já importada com a mesma chave fiscal.') from exc
            raise

        self.engine.documents.set_status(doc.id, processing_status)
        self.engine.audit.record(session.user_id, 'DOCUMENTO_IMPORTADO', 'document', doc.id, source.name)
        return self.engine.documents.get(doc.id)

    def delete_invoice(self, session: Session, document_id: int):
        doc = self.engine.documents.get(document_id)
        if not doc:
            raise ValidationError('Nota fiscal não encontrada.')
        if doc.category != 'invoice':
            raise ValidationError('O documento selecionado não é uma nota fiscal.')
        return self.engine.tool('documents').delete_document(session, document_id)
