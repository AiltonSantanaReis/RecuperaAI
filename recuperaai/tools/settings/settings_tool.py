from __future__ import annotations

from recuperaai.database.models import Session
from recuperaai.tools.base import ToolBase


class SettingsTool(ToolBase):
    name = 'settings'
    label = 'Configurações'

    def get_config(self, session: Session):
        self.engine.auth.require(session, 'settings_read')
        return self.engine.config_store.config

    def update_api(self, session: Session, enabled: bool, base_url: str, token: str):
        self.engine.auth.require(session, 'settings_write')
        cfg = self.engine.config_store.update(api_enabled=enabled, api_base_url=base_url.strip(), api_token=token.strip())
        self.engine.audit.record(session.user_id, 'CONFIG_API_ATUALIZADA', 'settings', None, base_url)
        return cfg

    def create_backup(self, session: Session):
        self.engine.auth.require(session, 'backup_create')
        path = self.engine.backups.create_backup()
        self.engine.audit.record(session.user_id, 'BACKUP_CRIADO', 'backup', None, str(path))
        return path
