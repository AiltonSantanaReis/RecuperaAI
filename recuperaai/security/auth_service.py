from __future__ import annotations

from recuperaai.core.exceptions import PermissionDenied, ValidationError
from recuperaai.database.models import Session
from recuperaai.database.repositories import UserRepository, AuditRepository
from recuperaai.security.passwords import hash_password, verify_password, validate_password_policy
from recuperaai.security.permissions import ROLE_LABELS, can, permission_label


class AuthService:
    def __init__(self, users: UserRepository, audit: AuditRepository) -> None:
        self.users = users
        self.audit = audit

    def ensure_default_admin(self) -> None:
        if self.users.count() == 0:
            admin = self.users.create(
                "admin",
                "Administrador",
                "admin",
                hash_password("Admin@12345"),
                must_change_password=True,
            )
            self.audit.add(admin.id, "USUARIO_ADMIN_INICIAL_CRIADO", "user", admin.id, "Senha temporária criada; troca obrigatória no primeiro acesso.")

    def login(self, username: str, password: str) -> Session:
        row = self.users.get_with_hash(username)
        if not row or not bool(row['is_active']) or not verify_password(password, row['password_hash']):
            self.audit.add(None, "LOGIN_NEGADO", "user", None, username)
            raise ValidationError("Usuário ou senha inválidos.")
        user = self.users.get(row['id'])
        if not user:
            raise ValidationError("Usuário não encontrado.")
        self.audit.add(user.id, "LOGIN_REALIZADO", "user", user.id, user.username)
        return Session(user=user)

    def change_password(self, session: Session, current_password: str, new_password: str) -> None:
        row = self.users.get_with_hash(session.user.username)
        if not row or not verify_password(current_password, row['password_hash']):
            self.audit.add(session.user_id, "ALTERACAO_SENHA_NEGADA", "user", session.user_id, session.user.username)
            raise ValidationError("Senha atual inválida.")
        errors = validate_password_policy(new_password)
        if errors:
            raise ValidationError("Senha inválida: " + ", ".join(errors) + ".")
        if verify_password(new_password, row['password_hash']):
            raise ValidationError("A nova senha deve ser diferente da senha atual.")
        self.users.change_password(session.user_id, hash_password(new_password))
        session.user.must_change_password = False
        self.audit.add(session.user_id, "SENHA_ALTERADA", "user", session.user_id, session.user.username)

    def require(self, session: Session, permission: str) -> None:
        if not can(session.role, permission):
            label = permission_label(permission)
            raise PermissionDenied(f"Seu perfil não permite {label}.")

    def require_any(self, session: Session, permissions: list[str] | tuple[str, ...] | set[str]) -> None:
        if not any(can(session.role, permission) for permission in permissions):
            labels = ", ".join(permission_label(permission) for permission in permissions)
            raise PermissionDenied(f"Seu perfil não permite nenhuma destas ações: {labels}.")

    def create_user(self, session: Session, username: str, full_name: str, role: str, password: str):
        self.require(session, 'users_write')
        username = (username or '').strip().lower()
        full_name = (full_name or '').strip()
        if not username:
            raise ValidationError('Informe o usuário.')
        if not full_name:
            raise ValidationError('Informe o nome do usuário.')
        if self.users.get_by_username(username):
            raise ValidationError('Usuário já cadastrado.')
        role = (role or '').strip().lower()
        if role not in ROLE_LABELS:
            raise ValidationError('Perfil de usuário inválido.')
        errors = validate_password_policy(password)
        if errors:
            raise ValidationError("Senha inválida: " + ", ".join(errors) + ".")
        user = self.users.create(username, full_name, role, hash_password(password), must_change_password=True)
        self.audit.add(session.user_id, "USUARIO_CRIADO", "user", user.id, user.username)
        return user
