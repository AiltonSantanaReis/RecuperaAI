from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    base: Path
    data: Path
    storage: Path
    imports: Path
    reports: Path
    backups: Path
    logs: Path
    database: Path
    config: Path

    @staticmethod
    def _default_base() -> Path:
        if sys.platform.startswith("win"):
            root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            return Path(root) / "RecuperaAI"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "RecuperaAI"
        return Path.home() / ".local" / "share" / "RecuperaAI"

    @staticmethod
    def _portable_base() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent / "dados"
        return Path.cwd() / "dados"

    @classmethod
    def create(cls, base_dir: str | None = None, portable: bool = False) -> "AppPaths":
        if base_dir:
            base = Path(base_dir).expanduser().resolve()
        elif portable:
            base = cls._portable_base()
        else:
            base = cls._default_base()
        data = base / "data"
        storage = base / "storage"
        paths = cls(
            base=base,
            data=data,
            storage=storage,
            imports=storage / "imports",
            reports=storage / "reports",
            backups=storage / "backups",
            logs=base / "logs",
            database=data / "recuperaai.sqlite3",
            config=data / "config.json",
        )
        paths.ensure()
        return paths

    def ensure(self) -> None:
        for folder in [self.base, self.data, self.storage, self.imports, self.reports, self.backups, self.logs]:
            folder.mkdir(parents=True, exist_ok=True)
