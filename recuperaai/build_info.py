from __future__ import annotations

APP_NAME = "RecuperaAI"
APP_VERSION = "1.0.0"
APP_STAGE = "Production"
APP_CHANNEL = "desktop"


def version_label() -> str:
    return f"{APP_NAME} {APP_VERSION} ({APP_STAGE} / {APP_CHANNEL})"
