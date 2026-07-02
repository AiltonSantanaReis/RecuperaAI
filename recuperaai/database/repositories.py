from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recuperaai.database.connection import Database
from recuperaai.database.models import User, Client, Document, Finding
from recuperaai.fiscal.key_utils import normalize_invoice_key


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user(row) -> User | None:
    if not row:
        return None
    keys = set(row.keys())
    must_change = bool(row['must_change_password']) if 'must_change_password' in keys else False
    return User(
        id=row['id'],
        username=row['username'],
        full_name=row['full_name'],
        role=row['role'],
        is_active=bool(row['is_active']),
        must_change_password=must_change,
    )


def _client(row) -> Client | None:
    if not row:
        return None
    return Client(
        id=row['id'], name=row['name'], document=row['document'], contact_name=row['contact_name'], email=row['email'],
        phone=row['phone'], notes=row['notes'], status=row['status']
    )


def _document(row) -> Document | None:
    if not row:
        return None
    return Document(
        id=row['id'], client_id=row['client_id'], original_name=row['original_name'], file_type=row['file_type'], category=row['category'],
        storage_path=row['storage_path'], sha256=row['sha256'], invoice_key=row['invoice_key'], issue_date=row['issue_date'],
        issuer_name=row['issuer_name'], issuer_document=row['issuer_document'], recipient_name=row['recipient_name'],
        recipient_document=row['recipient_document'], total_amount=row['total_amount'], parser_status=row['parser_status'],
        processing_status=row['processing_status'], payload_json=row['payload_json']
    )


def _finding(row) -> Finding | None:
    if not row:
        return None
    return Finding(
        id=row['id'], document_id=row['document_id'], severity=row['severity'], code=row['code'], title=row['title'],
        message=row['message'], amount=row['amount'], field=row['field'], source=row['source'], status=row['status']
    )


class UserRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, username: str, full_name: str, role: str, password_hash: str, must_change_password: bool = False) -> User:
        t = now()
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO users(username, full_name, role, password_hash, must_change_password, is_active, created_at, updated_at) VALUES(?,?,?,?,?,1,?,?)",
                (username.strip().lower(), full_name.strip(), role, password_hash, 1 if must_change_password else 0, t, t),
            )
            conn.commit()
            return self.get(cur.lastrowid)  # type: ignore[arg-type]

    def get(self, user_id: int) -> User | None:
        return _user(self.db.query_one("SELECT * FROM users WHERE id=?", (user_id,)))

    def get_with_hash(self, username: str):
        return self.db.query_one("SELECT * FROM users WHERE username=?", (username.strip().lower(),))

    def get_by_username(self, username: str) -> User | None:
        return _user(self.get_with_hash(username))

    def list_all(self) -> list[User]:
        return [_user(row) for row in self.db.query_all("SELECT * FROM users ORDER BY full_name")]  # type: ignore[misc]

    def set_active(self, user_id: int, active: bool) -> None:
        self.db.execute("UPDATE users SET is_active=?, updated_at=? WHERE id=?", (1 if active else 0, now(), user_id))

    def change_password(self, user_id: int, password_hash: str) -> None:
        self.db.execute("UPDATE users SET password_hash=?, must_change_password=0, updated_at=? WHERE id=?", (password_hash, now(), user_id))

    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS total FROM users")
        return int(row['total'])


class ClientRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, name: str, document: str | None = None, contact_name: str | None = None, email: str | None = None,
               phone: str | None = None, notes: str | None = None) -> Client:
        t = now()
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO clients(name, document, contact_name, email, phone, notes, status, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?, 'active', ?, ?)",
                (name.strip(), document, contact_name, email, phone, notes, t, t),
            )
            conn.commit()
            return self.get(cur.lastrowid)  # type: ignore[arg-type]

    def update(self, client_id: int, **fields) -> Client | None:
        allowed = {"name", "document", "contact_name", "email", "phone", "notes", "status"}
        clean = {k: v for k, v in fields.items() if k in allowed}
        if not clean:
            return self.get(client_id)
        clean["updated_at"] = now()
        sql = "UPDATE clients SET " + ", ".join([f"{k}=?" for k in clean.keys()]) + " WHERE id=?"
        self.db.execute(sql, (*clean.values(), client_id))
        return self.get(client_id)

    def get(self, client_id: int) -> Client | None:
        return _client(self.db.query_one("SELECT * FROM clients WHERE id=?", (client_id,)))

    def list_all(self, term: str | None = None, include_archived: bool = False, archived_only: bool = False) -> list[Client]:
        filters = []
        params: list[Any] = []
        if archived_only:
            filters.append("status='archived'")
        elif not include_archived:
            filters.append("status<>'archived'")
        if term:
            like = f"%{term.strip()}%"
            filters.append("(name LIKE ? OR document LIKE ?)")
            params.extend([like, like])
        where = " WHERE " + " AND ".join(filters) if filters else ""
        rows = self.db.query_all(f"SELECT * FROM clients{where} ORDER BY name", params)
        return [_client(row) for row in rows]  # type: ignore[misc]

    def dashboard_counts(self) -> dict[str, int]:
        rows = self.db.query_all("SELECT status, COUNT(*) AS total FROM clients WHERE status<>'archived' GROUP BY status")
        return {row['status']: row['total'] for row in rows}


class DocumentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_import(
        self,
        client_id: int,
        original_name: str,
        file_type: str,
        storage_path: Path,
        sha256: str,
        user_id: int | None,
        category: str = 'invoice',
        initial_payload: dict[str, Any] | None = None,
        parser_status: str = 'pending',
    ) -> Document:
        t = now()
        payload = initial_payload or {}
        invoice_key = normalize_invoice_key(payload.get('invoice_key'))
        payload_json = json.dumps(payload, ensure_ascii=False) if initial_payload is not None else None
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO documents("
                "client_id, original_name, file_type, category, storage_path, sha256, "
                "invoice_key, issue_date, issuer_name, issuer_document, recipient_name, recipient_document, "
                "total_amount, parser_status, payload_json, created_by, created_at, updated_at"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    client_id, original_name, file_type, category, str(storage_path), sha256,
                    invoice_key, payload.get('issue_date'), payload.get('issuer_name'), payload.get('issuer_document'),
                    payload.get('recipient_name'), payload.get('recipient_document'), payload.get('total_amount'),
                    parser_status, payload_json, user_id, t, t,
                ),
            )
            conn.commit()
            return self.get(cur.lastrowid)  # type: ignore[arg-type]

    def get_duplicate(self, client_id: int, sha256: str) -> Document | None:
        return _document(self.db.query_one("SELECT * FROM documents WHERE client_id=? AND sha256=?", (client_id, sha256)))

    def get_duplicate_by_invoice_key(self, invoice_key: str, exclude_document_id: int | None = None) -> Document | None:
        normalized = normalize_invoice_key(invoice_key)
        if not normalized:
            return None
        if exclude_document_id is None:
            row = self.db.query_one(
                "SELECT * FROM documents WHERE category='invoice' AND invoice_key=? ORDER BY created_at ASC LIMIT 1",
                (normalized,),
            )
        else:
            row = self.db.query_one(
                "SELECT * FROM documents WHERE category='invoice' AND invoice_key=? AND id<>? ORDER BY created_at ASC LIMIT 1",
                (normalized, exclude_document_id),
            )
        return _document(row)

    def get(self, document_id: int) -> Document | None:
        return _document(self.db.query_one("SELECT * FROM documents WHERE id=?", (document_id,)))

    def list_for_client(self, client_id: int, category: str | None = None) -> list[Document]:
        if category is None:
            rows = self.db.query_all(
                "SELECT * FROM documents WHERE client_id=? ORDER BY created_at DESC",
                (client_id,),
            )
        else:
            rows = self.db.query_all(
                "SELECT * FROM documents WHERE client_id=? AND category=? ORDER BY created_at DESC",
                (client_id, category),
            )
        return [_document(row) for row in rows]  # type: ignore[misc]

    def list_client_files(self, client_id: int) -> list[Document]:
        rows = self.db.query_all(
            "SELECT * FROM documents WHERE client_id=? AND category <> 'invoice' ORDER BY created_at DESC",
            (client_id,),
        )
        return [_document(row) for row in rows]  # type: ignore[misc]

    def summary_for_client(self, client_id: int) -> dict[str, Any]:
        rows = self.db.query_all(
            """
            SELECT
                category,
                processing_status,
                COUNT(*) AS total,
                COALESCE(SUM(total_amount), 0) AS total_amount
            FROM documents
            WHERE client_id=?
            GROUP BY category, processing_status
            """,
            (client_id,),
        )
        by_category: dict[str, int] = {}
        by_status: dict[str, int] = {}
        amount_by_category: dict[str, float] = {}
        total_documents = 0
        total_amount = 0.0
        for row in rows:
            category = row['category'] or 'sem_categoria'
            status = row['processing_status'] or 'sem_status'
            count = int(row['total'] or 0)
            amount = float(row['total_amount'] or 0)
            by_category[category] = by_category.get(category, 0) + count
            by_status[status] = by_status.get(status, 0) + count
            amount_by_category[category] = amount_by_category.get(category, 0.0) + amount
            total_documents += count
            total_amount += amount
        last = self.db.query_one(
            "SELECT created_at FROM documents WHERE client_id=? ORDER BY created_at DESC LIMIT 1",
            (client_id,),
        )
        return {
            'total_documents': total_documents,
            'by_category': by_category,
            'by_status': by_status,
            'amount_by_category': amount_by_category,
            'total_invoice_amount': amount_by_category.get('invoice', 0.0),
            'total_amount': total_amount,
            'last_document_at': last['created_at'] if last else None,
        }

    def list_recent(self, limit: int = 100) -> list[Document]:
        rows = self.db.query_all(
            """
            SELECT d.*
            FROM documents d
            JOIN clients c ON c.id=d.client_id
            WHERE c.status<>'archived'
            ORDER BY d.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [_document(row) for row in rows]  # type: ignore[misc]

    def dashboard_summary(self) -> dict[str, Any]:
        rows = self.db.query_all(
            """
            SELECT d.category, d.processing_status, d.parser_status, COUNT(*) AS total, COALESCE(SUM(d.total_amount), 0) AS amount
            FROM documents d
            JOIN clients c ON c.id=d.client_id
            WHERE c.status<>'archived'
            GROUP BY d.category, d.processing_status, d.parser_status
            """
        )
        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        total_amount = 0.0
        total_documents = 0
        for row in rows:
            category = row['category'] or 'sem_categoria'
            status = row['processing_status'] or 'sem_status'
            count = int(row['total'] or 0)
            amount = float(row['amount'] or 0)
            by_category[category] = by_category.get(category, 0) + count
            by_status[status] = by_status.get(status, 0) + count
            total_documents += count
            if category == 'invoice':
                total_amount += amount
        return {
            'total_documents': total_documents,
            'total_invoices': by_category.get('invoice', 0),
            'by_category': by_category,
            'by_status': by_status,
            'total_invoice_amount': total_amount,
        }

    def update_payload(self, document_id: int, payload: dict[str, Any], parser_status: str) -> None:
        normalized_key = normalize_invoice_key(payload.get('invoice_key'))
        payload = dict(payload)
        payload['invoice_key'] = normalized_key
        self.db.execute(
            "UPDATE documents SET invoice_key=?, issue_date=?, issuer_name=?, issuer_document=?, recipient_name=?, recipient_document=?, "
            "total_amount=?, parser_status=?, payload_json=?, updated_at=? WHERE id=?",
            (
                normalized_key, payload.get('issue_date'), payload.get('issuer_name'), payload.get('issuer_document'),
                payload.get('recipient_name'), payload.get('recipient_document'), payload.get('total_amount'), parser_status,
                json.dumps(payload, ensure_ascii=False), now(), document_id,
            ),
        )

    def set_status(self, document_id: int, processing_status: str) -> None:
        self.db.execute("UPDATE documents SET processing_status=?, updated_at=? WHERE id=?", (processing_status, now(), document_id))

    def delete(self, document_id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute("DELETE FROM documents WHERE id=?", (document_id,))
            conn.commit()
            return cur.rowcount > 0


class FindingRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def clear_for_document(self, document_id: int) -> None:
        self.db.execute("DELETE FROM analysis_findings WHERE document_id=?", (document_id,))

    def add_many(self, document_id: int, findings: list[dict[str, Any]]) -> None:
        t = now()
        with self.db.connect() as conn:
            conn.executemany(
                "INSERT INTO analysis_findings(document_id, severity, code, title, message, amount, field, source, status, created_at) "
                "VALUES(?,?,?,?,?,?,?,?, 'open', ?)",
                [
                    (
                        document_id, f.get('severity', 'info'), f.get('code', 'INFO'), f.get('title', ''), f.get('message', ''),
                        f.get('amount'), f.get('field'), f.get('source', 'local'), t,
                    )
                    for f in findings
                ],
            )
            conn.commit()

    def list_for_document(self, document_id: int) -> list[Finding]:
        return [_finding(row) for row in self.db.query_all("SELECT * FROM analysis_findings WHERE document_id=? ORDER BY severity DESC, id", (document_id,))]  # type: ignore[misc]

    def get(self, finding_id: int) -> dict[str, Any] | None:
        row = self.db.query_one(
            "SELECT f.*, d.client_id, d.original_name, d.invoice_key, d.total_amount, d.issue_date FROM analysis_findings f "
            "JOIN documents d ON d.id=f.document_id WHERE f.id=?",
            (finding_id,),
        )
        return dict(row) if row else None

    def list_for_client(self, client_id: int, only_open: bool = False) -> list[dict[str, Any]]:
        status_filter = "AND f.status='open'" if only_open else ""
        rows = self.db.query_all(
            "SELECT f.*, d.original_name, d.invoice_key, d.total_amount, d.issue_date, d.processing_status "
            "FROM analysis_findings f "
            "JOIN documents d ON d.id=f.document_id WHERE d.client_id=? "
            f"{status_filter} "
            "ORDER BY CASE f.severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, f.created_at DESC",
            (client_id,),
        )
        return [dict(row) for row in rows]

    def list_open_for_client(self, client_id: int) -> list[dict[str, Any]]:
        return self.list_for_client(client_id, only_open=True)

    def update_review(self, finding_id: int, status: str, note: str | None, user_id: int | None) -> None:
        self.db.execute(
            "UPDATE analysis_findings SET status=?, review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?",
            (status, note, user_id, now(), finding_id),
        )

    def dashboard_counts(self) -> dict[str, int]:
        rows = self.db.query_all(
            """
            SELECT f.severity, COUNT(*) AS total
            FROM analysis_findings f
            JOIN documents d ON d.id=f.document_id
            JOIN clients c ON c.id=d.client_id
            WHERE f.status='open' AND c.status<>'archived'
            GROUP BY f.severity
            """
        )
        return {row['severity']: row['total'] for row in rows}

    def counts_for_client(self, client_id: int) -> dict[str, int]:
        rows = self.db.query_all(
            "SELECT f.severity, COUNT(*) AS total FROM analysis_findings f "
            "JOIN documents d ON d.id=f.document_id "
            "WHERE d.client_id=? AND f.status='open' GROUP BY f.severity",
            (client_id,),
        )
        return {row['severity']: row['total'] for row in rows}

    def status_counts_for_client(self, client_id: int) -> dict[str, int]:
        rows = self.db.query_all(
            "SELECT f.status, COUNT(*) AS total FROM analysis_findings f "
            "JOIN documents d ON d.id=f.document_id WHERE d.client_id=? GROUP BY f.status",
            (client_id,),
        )
        return {row['status']: row['total'] for row in rows}

    def opportunity_summary(self, client_id: int | None = None) -> dict[str, Any]:
        client_join = "" if client_id is not None else "JOIN clients c ON c.id=d.client_id"
        filters = ["d.category='invoice'", "f.amount IS NOT NULL", "f.amount > 0"]
        params: list[Any] = []
        if client_id is not None:
            filters.append("d.client_id=?")
            params.append(client_id)
        else:
            filters.append("c.status<>'archived'")
        where = " AND ".join(filters)

        rows = self.db.query_all(
            f"""
            SELECT
                f.status,
                f.source,
                COUNT(*) AS findings,
                COALESCE(SUM(f.amount), 0) AS amount
            FROM analysis_findings f
            JOIN documents d ON d.id=f.document_id
            {client_join}
            WHERE {where}
            GROUP BY f.status, f.source
            """,
            params,
        )
        invoices = self.db.query_one(
            f"""
            SELECT COUNT(*) AS total, COALESCE(SUM(total_amount), 0) AS amount
            FROM (
                SELECT DISTINCT d.id, d.total_amount
                FROM analysis_findings f
                JOIN documents d ON d.id=f.document_id
                {client_join}
                WHERE {where} AND f.status <> 'rejected'
            )
            """,
            params,
        )

        estimated = 0.0
        confirmed = 0.0
        in_review = 0.0
        rejected = 0.0
        api_estimated = 0.0
        local_estimated = 0.0
        findings_total = 0
        for row in rows:
            amount = float(row['amount'] or 0)
            status = row['status'] or ''
            source = (row['source'] or 'local').lower()
            findings_total += int(row['findings'] or 0)
            if status == 'rejected':
                rejected += amount
                continue
            estimated += amount
            if status == 'confirmed':
                confirmed += amount
            else:
                in_review += amount
            if source == 'api':
                api_estimated += amount
            else:
                local_estimated += amount

        return {
            'estimated_total': estimated,
            'confirmed_total': confirmed,
            'in_review_total': in_review,
            'rejected_total': rejected,
            'api_estimated_total': api_estimated,
            'local_estimated_total': local_estimated,
            'findings_total': findings_total,
            'impacted_invoices': int(invoices['total'] if invoices else 0),
            'impacted_invoice_amount': float(invoices['amount'] if invoices else 0),
        }

    def opportunities_by_client(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.query_all(
            """
            SELECT
                c.id AS client_id,
                c.name,
                c.document,
                COUNT(DISTINCT d.id) AS invoices,
                COUNT(f.id) AS findings,
                COALESCE(SUM(CASE WHEN f.status <> 'rejected' THEN f.amount ELSE 0 END), 0) AS estimated,
                COALESCE(SUM(CASE WHEN f.status='confirmed' THEN f.amount ELSE 0 END), 0) AS confirmed,
                COALESCE(SUM(CASE WHEN f.source='api' AND f.status <> 'rejected' THEN f.amount ELSE 0 END), 0) AS api_estimated,
                MAX(d.issue_date) AS last_issue_date
            FROM clients c
            JOIN documents d ON d.client_id=c.id AND d.category='invoice'
            JOIN analysis_findings f ON f.document_id=d.id
            WHERE c.status<>'archived' AND f.amount IS NOT NULL AND f.amount > 0
            GROUP BY c.id, c.name, c.document
            HAVING estimated > 0
            ORDER BY estimated DESC, findings DESC, c.name ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in rows]


class AuditRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, user_id: int | None, action: str, entity: str | None = None, entity_id: int | None = None, details: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO audit_log(user_id, action, entity, entity_id, details, created_at) VALUES(?,?,?,?,?,?)",
            (user_id, action, entity, entity_id, details, now()),
        )

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.query_all("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,))]

    def for_entity(self, entity: str, entity_id: int, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.query_all(
            "SELECT a.*, u.username, u.full_name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id "
            "WHERE a.entity=? AND a.entity_id=? ORDER BY a.created_at DESC LIMIT ?",
            (entity, entity_id, limit),
        )
        return [dict(row) for row in rows]

    def for_client(self, client_id: int, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.query_all(
            """
            SELECT a.*, u.username, u.full_name
            FROM audit_log a
            LEFT JOIN users u ON u.id=a.user_id
            WHERE
                (a.entity='client' AND a.entity_id=?)
                OR (a.entity='document' AND a.entity_id IN (SELECT id FROM documents WHERE client_id=?))
            ORDER BY a.created_at DESC
            LIMIT ?
            """,
            (client_id, client_id, limit),
        )
        return [dict(row) for row in rows]

    def import_history_for_client(self, client_id: int, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.query_all(
            "SELECT a.*, u.username, u.full_name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id "
            "WHERE a.entity='client' AND a.entity_id=? AND a.action='IMPORTACAO_EM_MASSA' "
            "ORDER BY a.created_at DESC LIMIT ?",
            (client_id, limit),
        )
        return [dict(row) for row in rows]


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now()),
        )

    def get(self, key: str, default: str = "") -> str:
        row = self.db.query_one("SELECT value FROM settings WHERE key=?", (key,))
        return row['value'] if row else default
