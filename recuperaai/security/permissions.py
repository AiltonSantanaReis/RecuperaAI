from __future__ import annotations

from dataclasses import dataclass


ROLE_LABELS = {
    "admin": "Administrador",
    "supervisor": "Supervisor",
    # Papel legado: mantido para bancos/pacotes anteriores; exibido como Supervisor.
    "manager": "Supervisor",
    "analyst": "Analista",
    "operator": "Operador",
    "viewer": "Consulta",
}

PERMISSION_LABELS = {
    "*": "acesso total",
    "dashboard_view": "visualizar oportunidades",
    "clients_read": "visualizar clientes",
    "clients_write": "cadastrar e editar clientes",
    "documents_read": "visualizar documentos",
    "documents_write": "adicionar documentos do cliente",
    "documents_delete": "excluir documentos do cliente",
    "invoices_import": "importar notas fiscais",
    "invoices_delete": "excluir notas fiscais",
    "analysis_read": "visualizar análises",
    "analysis_run": "executar análises",
    "findings_review": "revisar inconsistências",
    "reports_export": "gerar relatórios",
    "reports_approve": "aprovar relatórios",
    "users_read": "visualizar usuários",
    "users_write": "criar e alterar usuários",
    "settings_read": "visualizar configurações técnicas",
    "settings_write": "alterar configurações técnicas",
    "backup_create": "criar backup local",
    "invoices_read": "visualizar notas fiscais",
    "findings_read": "visualizar inconsistências",
    "audit_read": "visualizar histórico de ações",
}

# Permissões antigas mantidas como aliases para evitar quebra de integrações simples.
PERMISSION_ALIASES: dict[str, set[str]] = {
    "clients": {"clients_read", "clients_write"},
    "documents": {"documents_read", "documents_write", "documents_delete"},
    "import": {"invoices_import"},
    "analysis": {"analysis_read", "analysis_run"},
    "reports": {"reports_export"},
    "settings": {"settings_read", "settings_write"},
}

SUPERVISOR_PERMISSIONS = {
    "dashboard_view",
    "clients_read", "clients_write",
    "documents_read", "documents_write", "documents_delete", "invoices_read", "findings_read",
    "invoices_import", "invoices_delete",
    "analysis_read", "analysis_run", "findings_review",
    "reports_export", "reports_approve",
    "users_read",
    "backup_create",
    "audit_read",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "supervisor": set(SUPERVISOR_PERMISSIONS),
    # Compatibilidade com etapas anteriores.
    "manager": set(SUPERVISOR_PERMISSIONS),
    "analyst": {
        "dashboard_view",
        "clients_read", "clients_write",
        "documents_read", "documents_write", "documents_delete", "invoices_read", "findings_read",
        "invoices_import", "invoices_delete",
        "analysis_read", "analysis_run", "findings_review",
        "reports_export",
        "audit_read",
    },
    "operator": {
        "dashboard_view",
        "clients_read",
        "documents_read", "invoices_read", "findings_read",
        "invoices_import", "invoices_delete",
        "analysis_read", "analysis_run",
        "audit_read",
    },
    "viewer": {
        "dashboard_view",
        "clients_read",
        "documents_read", "invoices_read", "findings_read",
        "analysis_read",
        "audit_read",
    },
}


@dataclass(frozen=True)
class UiTab:
    key: str
    title: str
    permission: str
    builder: str


UI_TABS: tuple[UiTab, ...] = (
    UiTab("dashboard", "Oportunidades", "dashboard_view", "_build_dashboard"),
    UiTab("clients", "Clientes", "clients_read", "_build_clients"),
    UiTab("invoices", "Notas Fiscais", "invoices_read", "_build_invoices"),
    UiTab("analysis", "Análises", "analysis_read", "_build_analysis"),
    UiTab("reports", "Relatórios", "reports_export", "_build_reports"),
    UiTab("users", "Usuários", "users_read", "_build_users"),
    UiTab("backup", "Backup", "backup_create", "_build_backup"),
    UiTab("settings", "Configurações", "settings_read", "_build_settings"),
)


def normalize_role(role: str) -> str:
    role = (role or "").strip().lower()
    return role if role in ROLE_PERMISSIONS else ""


def _direct_can(role: str, permission: str) -> bool:
    normalized = normalize_role(role)
    if not normalized:
        return False
    permissions = ROLE_PERMISSIONS.get(normalized, set())
    return "*" in permissions or permission in permissions


def can(role: str, permission: str) -> bool:
    """Retorna True quando o perfil possui a permissão solicitada."""
    permission = (permission or "").strip()
    if not permission:
        return False
    if permission == "*":
        return _direct_can(role, "*")
    if permission in PERMISSION_ALIASES:
        return any(_direct_can(role, p) for p in PERMISSION_ALIASES[permission])
    return _direct_can(role, permission)


def can_all(role: str, permissions: list[str] | tuple[str, ...] | set[str]) -> bool:
    return all(can(role, permission) for permission in permissions)


def can_any(role: str, permissions: list[str] | tuple[str, ...] | set[str]) -> bool:
    return any(can(role, permission) for permission in permissions)


def visible_tabs_for_role(role: str) -> list[UiTab]:
    return [tab for tab in UI_TABS if can(role, tab.permission)]


def allowed_roles_for_user_creation(actor_role: str) -> list[str]:
    if can(actor_role, "users_write"):
        return ["operator", "analyst", "supervisor", "viewer", "manager", "admin"]
    return []


def permission_label(permission: str) -> str:
    return PERMISSION_LABELS.get(permission, permission)
