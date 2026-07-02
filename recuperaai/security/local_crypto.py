from __future__ import annotations

import base64
import os
from pathlib import Path


class LocalCrypto:
    """Criptografia opcional de arquivos sensíveis usando cryptography/Fernet.

    O projeto mantém o app funcional mesmo em desenvolvimento sem a dependência, mas o build Windows
    deve instalar requirements.txt para habilitar esta camada.
    """

    def __init__(self, key_file: Path) -> None:
        self.key_file = key_file
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = None
        self._load()

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def _load(self) -> None:
        try:
            from cryptography.fernet import Fernet
            if self.key_file.exists():
                key = self.key_file.read_bytes()
            else:
                key = Fernet.generate_key()
                self.key_file.write_bytes(key)
            self._fernet = Fernet(key)
        except Exception:
            self._fernet = None

    def encrypt_bytes(self, data: bytes) -> bytes:
        if not self._fernet:
            return data
        return self._fernet.encrypt(data)

    def decrypt_bytes(self, data: bytes) -> bytes:
        if not self._fernet:
            return data
        return self._fernet.decrypt(data)
