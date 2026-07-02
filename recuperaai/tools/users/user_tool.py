from __future__ import annotations

from recuperaai.database.models import Session
from recuperaai.tools.base import ToolBase


class UserTool(ToolBase):
    name = 'users'
    label = 'Usuários'

    def list_users(self, session: Session):
        self.engine.auth.require(session, 'users_read')
        return self.engine.users.list_all()

    def create_user(self, session: Session, username: str, full_name: str, role: str, password: str):
        return self.engine.auth.create_user(session, username, full_name, role, password)

    def set_active(self, session: Session, user_id: int, active: bool) -> None:
        self.engine.auth.require(session, 'users_write')
        self.engine.users.set_active(user_id, active)
        self.engine.audit.record(session.user_id, 'USUARIO_ATIVIDADE_ALTERADA', 'user', user_id, str(active))
