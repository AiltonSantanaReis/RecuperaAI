# RecuperaAI Architecture

## Runtime Model

The application is built around `ApplicationEngine`, which wires paths, SQLite repositories, authentication, audit logging, fiscal parsing, rule analysis, backup services, and UI-facing tools. UI code calls tools instead of reaching directly into repositories, keeping permission checks and validation in one place.

Main layers:

- `recuperaai.core`: engine lifecycle, local paths, config, logging, events.
- `recuperaai.database`: schema, migrations, repositories, dataclasses.
- `recuperaai.tools`: use-case API for clients, documents, invoices, analysis, reports, settings, and users.
- `recuperaai.ui`: PySide6 interface and QSS styling.
- `recuperaai.security`: authentication, password hashing, role permissions, local encryption.
- `recuperaai.fiscal`: fiscal file parsing, normalization, duplicate key handling, local rules, optional API client.

## Data Storage

The local SQLite database stores users, clients, documents, analysis findings, audit log entries, and settings. Imported files and client documents are stored under the configured local storage path, grouped by client and content hash. Backups are zip archives generated from the local data and storage folders while excluding existing backup archives.

The `clients.status` field controls operational visibility:

- `active`, `inactive`, and `paused` clients are operational.
- `archived` clients are hidden from normal selectors, dashboards, recent documents, and opportunity summaries.
- Archived client workspaces can still be opened from the archive area so documents, reports, findings, and audit history remain available.
- Restoring an archived client returns it to `active`.

## Client Archive Flow

Archiving a client is a soft removal:

1. The UI asks for confirmation.
2. `ClientTool.archive_client` requires `clients_write`.
3. The client status changes to `archived`.
4. The audit log records `CLIENTE_ARQUIVADO`.
5. Operational dashboards and selectors exclude the client.
6. The Backup tab lists archived clients for review or restoration.

New imports, client document attachments, and new analyses are blocked while a client is archived. Existing workspace data remains readable.

## Permissions

Role permissions are centralized in `recuperaai.security.permissions`. Tools enforce permissions server-side, so UI visibility is not the only protection. The main roles are:

- `admin`: full access.
- `supervisor` / legacy `manager`: operational management, users read, backups.
- `analyst`: client work, imports, analysis, reports.
- `operator`: imports and analysis without client editing.
- `viewer`: read-only access.

## Fiscal Workflow

1. A client is created or selected.
2. XML/PDF fiscal files are imported.
3. Files are stored locally and registered as `documents`.
4. Fiscal keys and hashes prevent duplicate imports.
5. The normalizer extracts invoice data when possible.
6. The rule engine and optional API generate findings.
7. Findings are reviewed and exported through reports.
8. All significant actions are recorded in `audit_log`.

## Testing

The test suite focuses on workflow behavior and permission boundaries:

- client workspace consolidation
- client archive/restore behavior
- invoice import and duplicate protection
- document deletion and linked finding cleanup
- role permissions
- reports and backups
- fiscal parsing and rule analysis

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Release Hygiene

Commit source, tests, scripts, assets, requirements, and the two documentation files. Do not commit:

- virtual environments
- SQLite runtime data
- local logs
- generated reports and imports
- build outputs
- release zips
- visual audit screenshots
- Python caches
