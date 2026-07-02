from __future__ import annotations

from recuperaai.database.repositories import AuditRepository


class AuditService:
    def __init__(self, audit: AuditRepository) -> None:
        self.audit = audit

    def record(self, user_id: int | None, action: str, entity: str | None = None, entity_id: int | None = None, details: str | None = None) -> None:
        self.audit.add(user_id, action, entity, entity_id, details)

    def recent(self, limit: int = 100):
        return self.audit.recent(limit)
