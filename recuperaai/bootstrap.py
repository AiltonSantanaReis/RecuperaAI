from __future__ import annotations

from recuperaai.core.engine import ApplicationEngine
from recuperaai.core.paths import AppPaths


def create_engine(base_dir: str | None = None, portable: bool = False) -> ApplicationEngine:
    paths = AppPaths.create(base_dir=base_dir, portable=portable)
    return ApplicationEngine(paths=paths)
