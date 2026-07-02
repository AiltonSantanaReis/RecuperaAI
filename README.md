# RecuperaAI Desktop

Local-first desktop application for Brazilian fiscal document review, client workspaces, audit history, backups, and professional report exports.

RecuperaAI is designed for operational fiscal analysis teams that need to centralize client records, import XML/PDF fiscal documents, review automated findings, preserve evidence, and export structured reports without sending sensitive data to a cloud service by default.

## Status

- Current application version: `1.0.0-etapa11.0`
- Primary platform: Windows desktop
- Runtime: Python 3.11 to 3.14
- UI framework: PySide6
- Storage model: local SQLite database plus local file storage

This repository contains source code, tests, build scripts, and documentation. Generated builds, local data, logs, screenshots, and release artifacts are intentionally excluded from version control.

## Core Capabilities

- Client workspace with registration data, contracts, supporting documents, invoices, imports, findings, reports, and audit history.
- XML/PDF fiscal document import with duplicate protection by file hash and fiscal key.
- Local fiscal rule engine with optional external API enrichment.
- Human review workflow for findings and estimated recovery opportunities.
- Professional PDF, XLSX, and CSV report exports.
- Local backup archive covering database, configuration, imported files, client documents, and reports.
- Soft client archive and restore flow that removes clients from operational screens while preserving documents, reports, findings, and history.
- Role-based access control for administrators, supervisors, analysts, operators, and read-only viewers.

## Security And Privacy Model

RecuperaAI is local-first. Operational data is stored on the user's machine unless an operator explicitly enables and configures an external analysis API.

Security-relevant behaviors:

- Passwords are hashed before storage.
- Sensitive local configuration is encrypted with a machine-local key.
- Tool-level permission checks are enforced outside the UI layer.
- Audit logs record significant client, document, import, analysis, review, report, backup, and user actions.
- Backups exclude existing backup archives to avoid recursive growth.

Important limitation: fiscal findings and estimated recovery values are decision-support outputs. They are not legal, accounting, or tax advice and require human validation.

## Architecture

The application is organized around a small engine and explicit use-case tools:

```text
recuperaai/
  audit/          Audit recording services
  core/           Engine, paths, config, events, logging
  database/       SQLite schema, migrations, repositories
  fiscal/         Parsing, normalization, fiscal rules, API contract
  maintenance/    Local backup service
  security/       Authentication, permissions, local crypto
  tools/          Use-case layer consumed by UI and tests
  ui/             PySide6 windows, widgets, and QSS theme
  validation/     Smoke and visual validation helpers
tests/            Unit, integration, permission, packaging, and workflow tests
scripts/          Windows build, packaging, and verification helpers
assets/           Static packaged assets
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the runtime model, data model, permissions, archive flow, and release hygiene.

## Requirements

- Python `>=3.11,<3.15`
- Windows for packaged desktop builds
- Runtime dependencies listed in `requirements.txt`
- Tested dependency snapshot in `requirements-lock.txt`

## First Login

Default local administrator:

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

Run the desktop application:

```powershell
.\.venv\Scripts\python.exe -m recuperaai.app
```

Run a source smoke test with isolated data:

```powershell
.\.venv\Scripts\python.exe -m recuperaai.app --smoke-test --base-dir "$env:TEMP\RecuperaAISmoke"
```

## Testing

Run the complete test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The current suite covers:

- engine initialization and smoke tests
- authentication and role permissions
- client workspace behavior
- client archive and restore behavior
- invoice import and duplicate protection
- document lifecycle and finding cleanup
- fiscal parsing and rule analysis
- report export data paths
- local backup behavior
- Windows packaging scripts

## Windows Build

```powershell
.\scripts\build_windows.ps1
```

The build script validates source code, runs tests unless skipped, creates PyInstaller outputs, verifies executable version consistency, runs smoke checks, and packages the Windows distribution.

Generated folders such as `build/`, `dist/`, `release/`, `logs/`, visual audit folders, and local data folders are not source files and should not be committed.

## Release Process

Recommended release sequence:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
git status --short
git tag -a v1.0.0-etapa11.0 -m "RecuperaAI Desktop v1.0.0-etapa11.0"
git push origin main --tags
```

For GitHub releases, include:

- release tag and commit hash
- test command and result
- key product capabilities
- known limitations
- build and packaging notes

## Repository Hygiene

Tracked:

- source code
- tests and fixtures
- scripts
- dependency manifests
- `README.md`
- `ARCHITECTURE.md`
- repository metadata such as `.gitignore` and `.gitattributes`

Ignored:

- virtual environments
- local SQLite runtime data
- local logs
- generated reports and imports
- build outputs
- release zips
- visual audit screenshots
- Python caches

## License

No open-source license has been declared yet. Until a license is added, all rights are reserved by the repository owner.
