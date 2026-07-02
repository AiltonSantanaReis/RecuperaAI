# RecuperaAI Desktop

RecuperaAI Desktop is a local-first fiscal review application for organizing clients, importing Brazilian fiscal documents, reviewing findings, and producing professional reports. It keeps sensitive operational data on the user's machine through SQLite, local encrypted configuration, and client-scoped file storage.

## Highlights

- PySide6 desktop interface with role-based navigation.
- Client workspace with registration data, contracts, supporting documents, invoices, imports, findings, reports, and audit history.
- XML/PDF invoice import with duplicate protection by file hash and fiscal key.
- Local rule-based analysis with optional external API enrichment.
- Review workflow for fiscal findings and estimated recovery opportunities.
- PDF, XLSX, and CSV report export.
- Local backup zip including database, configuration, imported files, client documents, and reports.
- Client archive/restore flow: archived clients leave operational screens while their documents, reports, findings, and history remain available for backup review or restoration.

## Requirements

- Python 3.11 to 3.14
- Windows is the primary packaging target
- See `requirements.txt` for runtime dependencies and `requirements-lock.txt` for the tested lock snapshot

## First Login

Default user:

```text
username: admin
password: Admin@12345
```

The application requires changing the temporary password on first login.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the application:

```powershell
.\.venv\Scripts\python.exe -m recuperaai.app
```

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Run the smoke test:

```powershell
.\.venv\Scripts\python.exe -m recuperaai.app --smoke-test --base-dir "$env:TEMP\RecuperaAISmoke"
```

## Windows Build

```powershell
.\scripts\build_windows.ps1
```

Generated folders such as `build/`, `dist/`, `release/`, `logs/`, visual audit folders, and local data folders are not source files and should not be committed.

## Project Layout

```text
recuperaai/
  audit/          Audit recording services
  core/           Engine, paths, config, events, logging
  database/       SQLite schema, migrations, repositories
  fiscal/         Parsing, normalization, rule engine, API contract
  maintenance/    Local backup service
  security/       Authentication, permissions, local crypto
  tools/          Application use-case tools used by UI and tests
  ui/             PySide6 windows, widgets, and QSS theme
tests/            Unit and workflow tests
scripts/          Build and release helper scripts
assets/           Static packaged assets
```

## Documentation

- `README.md`: setup, usage, and repository overview.
- `ARCHITECTURE.md`: technical architecture, data model, permissions, and operational workflows.
