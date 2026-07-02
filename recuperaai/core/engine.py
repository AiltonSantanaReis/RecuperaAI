from __future__ import annotations

from dataclasses import dataclass, field

from recuperaai.audit.audit_service import AuditService
from recuperaai.core.config import ConfigStore
from recuperaai.core.events import EventBus
from recuperaai.core.paths import AppPaths
from recuperaai.database.connection import Database
from recuperaai.database.migrations import MigrationRunner
from recuperaai.database.repositories import (
    UserRepository, ClientRepository, DocumentRepository, FindingRepository,
    AuditRepository, SettingsRepository,
)
from recuperaai.fiscal.api_client import ApiConfig, FiscalApiClient
from recuperaai.fiscal.normalizer import FiscalDocumentNormalizer
from recuperaai.fiscal.rule_engine import FiscalRuleEngine
from recuperaai.security.auth_service import AuthService
from recuperaai.security.local_crypto import LocalCrypto
from recuperaai.maintenance.backup_service import BackupService


@dataclass
class ApplicationEngine:
    paths: AppPaths
    events: EventBus = field(default_factory=EventBus)

    def __post_init__(self) -> None:
        self.db = Database(self.paths.database)
        self.crypto = LocalCrypto(self.paths.data / 'local.key')
        self.config_store = ConfigStore(self.paths.config, self.crypto)
        self.users = UserRepository(self.db)
        self.clients = ClientRepository(self.db)
        self.documents = DocumentRepository(self.db)
        self.findings = FindingRepository(self.db)
        self.audit_repo = AuditRepository(self.db)
        self.settings = SettingsRepository(self.db)
        self.audit = AuditService(self.audit_repo)
        self.auth = AuthService(self.users, self.audit_repo)
        self.normalizer = FiscalDocumentNormalizer()
        self.rule_engine = FiscalRuleEngine()
        self.backups = BackupService(self.paths)
        self.tools = {}

    def initialize(self) -> None:
        MigrationRunner(self.db).migrate()
        self.auth.ensure_default_admin()
        self._register_tools()
        self.events.publish('engine.ready')

    def api_client(self) -> FiscalApiClient:
        cfg = self.config_store.config
        return FiscalApiClient(ApiConfig(enabled=cfg.api_enabled, base_url=cfg.api_base_url, token=cfg.api_token))

    def _register_tools(self) -> None:
        from recuperaai.tools.clients.client_tool import ClientTool
        from recuperaai.tools.documents.document_tool import DocumentTool
        from recuperaai.tools.invoices.invoice_tool import InvoiceTool
        from recuperaai.tools.analysis.analysis_tool import AnalysisTool
        from recuperaai.tools.users.user_tool import UserTool
        from recuperaai.tools.reports.report_tool import ReportTool
        from recuperaai.tools.settings.settings_tool import SettingsTool

        for cls in [ClientTool, DocumentTool, InvoiceTool, AnalysisTool, UserTool, ReportTool, SettingsTool]:
            tool = cls(self)
            self.tools[tool.name] = tool

    def tool(self, name: str):
        return self.tools[name]
