from __future__ import annotations

import base64
import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Any


@dataclass
class AppConfig:
    api_enabled: bool = False
    api_base_url: str = ""
    api_token: str = ""
    company_name: str = "RecuperaAI"
    auto_backup: bool = True
    pdf_ocr_enabled: bool = False


class ConfigStore:
    """Persistência da configuração local.

    O token da API fica disponível em memória para uso pelo app, mas é salvo
    no arquivo de configuração somente em formato criptografado. Arquivos
    antigos com api_token em texto puro são aceitos na leitura e migrados no
    próximo save().
    """

    def __init__(self, path: Path, crypto: Any | None = None) -> None:
        self.path = path
        self.crypto = crypto
        self._config = AppConfig()
        self.load()

    @property
    def config(self) -> AppConfig:
        return self._config

    def load(self) -> AppConfig:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                base = asdict(AppConfig())
                allowed = {field.name for field in fields(AppConfig)}
                clean = {key: value for key, value in data.items() if key in allowed}
                token = self._read_token(data)
                clean["api_token"] = token
                self._config = AppConfig(**{**base, **clean})
            except Exception:
                self._config = AppConfig()
        return self._config

    def _read_token(self, data: dict[str, Any]) -> str:
        encrypted = data.get("api_token_encrypted")
        if encrypted and self.crypto and getattr(self.crypto, "enabled", False):
            try:
                raw = base64.b64decode(str(encrypted).encode("ascii"))
                return self.crypto.decrypt_bytes(raw).decode("utf-8")
            except Exception:
                return ""
        legacy_plain = data.get("api_token")
        return str(legacy_plain or "")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self._config)
        token = str(payload.pop("api_token", "") or "")
        if token:
            if not self.crypto or not getattr(self.crypto, "enabled", False):
                raise RuntimeError("Criptografia local indisponível para salvar token da API.")
            encrypted = self.crypto.encrypt_bytes(token.encode("utf-8"))
            payload["api_token_encrypted"] = base64.b64encode(encrypted).decode("ascii")
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def update(self, **kwargs) -> AppConfig:
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        self.save()
        return self._config
