from __future__ import annotations

APP_NAME = "RecuperaAI"
APP_VERSION = "1.0.0-etapa11.0"
APP_STAGE = "Etapa 11"
APP_CHANNEL = "cliente-teste"


def version_label() -> str:
    return f"{APP_NAME} {APP_VERSION} ({APP_STAGE} / {APP_CHANNEL})"
