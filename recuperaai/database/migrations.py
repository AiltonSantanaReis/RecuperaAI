from __future__ import annotations

from datetime import datetime, timezone
from importlib.resources import files
import sqlite3

from recuperaai.database.connection import Database
from recuperaai.fiscal.key_utils import normalize_invoice_key

SCHEMA_VERSION = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MigrationRunner:
    def __init__(self, db: Database) -> None:
        self.db = db

    def migrate(self) -> None:
        schema_text = files('recuperaai.database').joinpath('schema.sql').read_text(encoding='utf-8')
        with self.db.connect() as conn:
            conn.executescript(schema_text)
            self._ensure_stage09_columns(conn)
            self._ensure_stage09_user_roles(conn)
            self._repair_stage09_user_fk_references(conn)
            self._normalize_existing_invoice_keys(conn)
            self._install_invoice_key_duplicate_guards(conn)
            conn.execute(
                "INSERT INTO schema_version(id, version, updated_at) VALUES(1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET version=excluded.version, updated_at=excluded.updated_at",
                (SCHEMA_VERSION, utc_now()),
            )
            conn.commit()

    def _table_columns(self, conn, table: str) -> set[str]:
        return {row['name'] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _ensure_stage09_columns(self, conn) -> None:
        columns = self._table_columns(conn, 'analysis_findings')
        additions = {
            'review_note': "ALTER TABLE analysis_findings ADD COLUMN review_note TEXT",
            'reviewed_by': "ALTER TABLE analysis_findings ADD COLUMN reviewed_by INTEGER REFERENCES users(id)",
            'reviewed_at': "ALTER TABLE analysis_findings ADD COLUMN reviewed_at TEXT",
        }
        for column, sql in additions.items():
            if column not in columns:
                conn.execute(sql)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_status ON analysis_findings(status)")

        user_columns = self._table_columns(conn, 'users')
        if 'must_change_password' not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")

    def _ensure_stage09_user_roles(self, conn) -> None:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        table_sql = row['sql'] if row else ''
        if 'supervisor' in table_sql and 'viewer' in table_sql:
            return

        # SQLite não permite alterar CHECK diretamente. Recriamos a tabela users
        # preservando os dados existentes e mantendo roles antigas como manager.
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA legacy_alter_table=ON")
        try:
            conn.execute("ALTER TABLE users RENAME TO users_old_stage09")
            conn.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','manager','supervisor','analyst','operator','viewer')),
                    password_hash TEXT NOT NULL,
                    must_change_password INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO users(id, username, full_name, role, password_hash, must_change_password, is_active, created_at, updated_at)
                SELECT id, username, full_name, role, password_hash,
                       COALESCE(must_change_password, 0),
                       is_active, created_at, updated_at
                FROM users_old_stage09
                """
            )
            conn.execute("DROP TABLE users_old_stage09")
        finally:
            conn.execute("PRAGMA legacy_alter_table=OFF")
            conn.execute("PRAGMA foreign_keys=ON")

    def _table_sql(self, conn, table: str) -> str:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row['sql'] if row and row['sql'] else ''

    def _repair_stage09_user_fk_references(self, conn) -> None:
        if 'users_old_stage09' not in (
            self._table_sql(conn, 'documents') + self._table_sql(conn, 'analysis_findings')
        ):
            return

        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            if 'users_old_stage09' in self._table_sql(conn, 'documents'):
                conn.execute("DROP TRIGGER IF EXISTS trg_documents_no_duplicate_invoice_key_insert")
                conn.execute("DROP TRIGGER IF EXISTS trg_documents_no_duplicate_invoice_key_update")
                conn.execute("DROP INDEX IF EXISTS ux_documents_invoice_key")
                conn.execute("DROP INDEX IF EXISTS idx_documents_invoice_key_duplicate_guard")
                conn.execute("DROP INDEX IF EXISTS idx_documents_client")
                conn.execute("DROP INDEX IF EXISTS idx_documents_key")
                conn.execute(
                    """
                    CREATE TABLE documents_stage09_fix (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                        original_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT 'invoice',
                        storage_path TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        invoice_key TEXT,
                        issue_date TEXT,
                        issuer_name TEXT,
                        issuer_document TEXT,
                        recipient_name TEXT,
                        recipient_document TEXT,
                        total_amount REAL,
                        parser_status TEXT NOT NULL DEFAULT 'pending',
                        processing_status TEXT NOT NULL DEFAULT 'imported',
                        payload_json TEXT,
                        created_by INTEGER REFERENCES users(id),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(client_id, sha256)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO documents_stage09_fix(
                        id, client_id, original_name, file_type, category, storage_path, sha256,
                        invoice_key, issue_date, issuer_name, issuer_document, recipient_name,
                        recipient_document, total_amount, parser_status, processing_status,
                        payload_json, created_by, created_at, updated_at
                    )
                    SELECT
                        id, client_id, original_name, file_type, category, storage_path, sha256,
                        invoice_key, issue_date, issuer_name, issuer_document, recipient_name,
                        recipient_document, total_amount, parser_status, processing_status,
                        payload_json, created_by, created_at, updated_at
                    FROM documents
                    """
                )
                conn.execute("DROP TABLE documents")
                conn.execute("ALTER TABLE documents_stage09_fix RENAME TO documents")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_client ON documents(client_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_key ON documents(invoice_key)")

            if 'users_old_stage09' in self._table_sql(conn, 'analysis_findings'):
                conn.execute("DROP INDEX IF EXISTS idx_findings_doc")
                conn.execute("DROP INDEX IF EXISTS idx_findings_severity")
                conn.execute("DROP INDEX IF EXISTS idx_findings_status")
                conn.execute(
                    """
                    CREATE TABLE analysis_findings_stage09_fix (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        severity TEXT NOT NULL CHECK(severity IN ('info','warning','critical')),
                        code TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        amount REAL,
                        field TEXT,
                        source TEXT NOT NULL DEFAULT 'local',
                        status TEXT NOT NULL DEFAULT 'open',
                        review_note TEXT,
                        reviewed_by INTEGER REFERENCES users(id),
                        reviewed_at TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO analysis_findings_stage09_fix(
                        id, document_id, severity, code, title, message, amount, field, source,
                        status, review_note, reviewed_by, reviewed_at, created_at
                    )
                    SELECT
                        id, document_id, severity, code, title, message, amount, field, source,
                        status, review_note, reviewed_by, reviewed_at, created_at
                    FROM analysis_findings
                    """
                )
                conn.execute("DROP TABLE analysis_findings")
                conn.execute("ALTER TABLE analysis_findings_stage09_fix RENAME TO analysis_findings")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_doc ON analysis_findings(document_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_severity ON analysis_findings(severity)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_status ON analysis_findings(status)")
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

    def _normalize_existing_invoice_keys(self, conn) -> None:
        rows = conn.execute(
            "SELECT id, invoice_key FROM documents WHERE invoice_key IS NOT NULL AND invoice_key <> ''"
        ).fetchall()
        for row in rows:
            normalized = normalize_invoice_key(row['invoice_key'])
            if normalized != row['invoice_key']:
                conn.execute(
                    "UPDATE documents SET invoice_key=?, updated_at=? WHERE id=?",
                    (normalized, utc_now(), row['id']),
                )

    def _install_invoice_key_duplicate_guards(self, conn) -> None:
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_documents_no_duplicate_invoice_key_insert
            BEFORE INSERT ON documents
            WHEN NEW.category='invoice'
                 AND NEW.invoice_key IS NOT NULL
                 AND NEW.invoice_key <> ''
                 AND EXISTS (
                    SELECT 1 FROM documents
                    WHERE category='invoice'
                      AND invoice_key=NEW.invoice_key
                 )
            BEGIN
                SELECT RAISE(ABORT, 'DUPLICATE_INVOICE_KEY');
            END;
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_documents_no_duplicate_invoice_key_update
            BEFORE UPDATE OF invoice_key, category ON documents
            WHEN NEW.category='invoice'
                 AND NEW.invoice_key IS NOT NULL
                 AND NEW.invoice_key <> ''
                 AND EXISTS (
                    SELECT 1 FROM documents
                    WHERE category='invoice'
                      AND invoice_key=NEW.invoice_key
                      AND id <> NEW.id
                 )
            BEGIN
                SELECT RAISE(ABORT, 'DUPLICATE_INVOICE_KEY');
            END;
            """
        )
        try:
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_invoice_key
                ON documents(invoice_key)
                WHERE category='invoice' AND invoice_key IS NOT NULL AND invoice_key <> ''
                """
            )
        except sqlite3.IntegrityError:
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_invoice_key_duplicate_guard
                ON documents(invoice_key)
                WHERE category='invoice' AND invoice_key IS NOT NULL AND invoice_key <> ''
                """
            )
