PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','manager','supervisor','analyst','operator','viewer')),
    password_hash TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    document TEXT,
    contact_name TEXT,
    email TEXT,
    phone TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name);

CREATE TABLE IF NOT EXISTS documents (
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
);

CREATE INDEX IF NOT EXISTS idx_documents_client ON documents(client_id);
CREATE INDEX IF NOT EXISTS idx_documents_key ON documents(invoice_key);

CREATE TABLE IF NOT EXISTS analysis_findings (
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
);

CREATE INDEX IF NOT EXISTS idx_findings_doc ON analysis_findings(document_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON analysis_findings(severity);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    entity TEXT,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
