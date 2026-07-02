from __future__ import annotations

import json
import platform
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from recuperaai.bootstrap import create_engine
from recuperaai.build_info import APP_CHANNEL, APP_NAME, APP_STAGE, APP_VERSION, version_label


def runtime_info(base_dir: str | None = None, portable: bool = False, log_path: str | None = None) -> dict[str, Any]:
    """Retorna informações de execução úteis para suporte e homologação."""
    engine = create_engine(base_dir=base_dir, portable=portable)
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "stage": APP_STAGE,
        "channel": APP_CHANNEL,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": str(Path(sys.executable).resolve()),
        "paths": {key: str(value) for key, value in asdict(engine.paths).items()},
        "log_path": log_path,
    }


def run_smoke_test(base_dir: str | None = None, keep_data: bool = False, portable: bool = False) -> dict[str, Any]:
    """Executa uma validação headless do núcleo do aplicativo.

    O smoke test não abre a interface. Ele valida inicialização, migrações,
    login padrão, ferramentas registradas e permissões essenciais. Isso permite
    testar o executável empacotado em Windows por linha de comando antes de
    entregar a pasta ao cliente.
    """
    temp_root: str | None = None
    if base_dir:
        smoke_base = Path(base_dir).expanduser().resolve()
    else:
        temp_root = tempfile.mkdtemp(prefix="recuperaai_smoke_")
        smoke_base = Path(temp_root)

    result: dict[str, Any] = {
        "ok": False,
        "version": version_label(),
        "base_dir": str(smoke_base),
        "checks": [],
    }

    try:
        engine = create_engine(base_dir=str(smoke_base), portable=portable)
        engine.initialize()
        result["checks"].append("engine_initialized")

        session = engine.auth.login("admin", "Admin@12345")
        result["checks"].append("default_admin_login_ok")

        expected_tools = {"clients", "documents", "invoices", "analysis", "users", "reports", "settings"}
        registered_tools = set(engine.tools.keys())
        missing_tools = sorted(expected_tools - registered_tools)
        if missing_tools:
            raise RuntimeError("Ferramentas ausentes: " + ", ".join(missing_tools))
        result["checks"].append("tools_registered")

        client = engine.tool("clients").create_client(
            session,
            name="Cliente Smoke Test",
            document="00.000.000/0001-00",
            contact_name="Homologação",
            email="teste@recuperaai.local",
        )
        workspace = engine.tool("clients").get_client_workspace(session, client.id)
        if workspace["client"]["name"] != "Cliente Smoke Test":
            raise RuntimeError("Workspace do cliente retornou dados inesperados.")
        result["checks"].append("client_workspace_ok")

        backup_path = engine.backups.create_backup()
        if not Path(backup_path).exists():
            raise RuntimeError("Backup de smoke test não foi criado.")
        result["checks"].append("backup_ok")

        result["database"] = str(engine.paths.database)
        result["backup"] = str(backup_path)
        result["ok"] = True
        return result
    finally:
        if temp_root and not keep_data:
            shutil.rmtree(temp_root, ignore_errors=True)


def to_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
