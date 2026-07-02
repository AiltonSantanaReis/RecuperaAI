from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class User:
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool = False


@dataclass
class Session:
    user: User

    @property
    def user_id(self) -> int:
        return self.user.id

    @property
    def role(self) -> str:
        return self.user.role


@dataclass
class Client:
    id: int
    name: str
    document: str | None
    contact_name: str | None
    email: str | None
    phone: str | None
    notes: str | None
    status: str


@dataclass
class Document:
    id: int
    client_id: int
    original_name: str
    file_type: str
    category: str
    storage_path: str
    sha256: str
    invoice_key: str | None
    issue_date: str | None
    issuer_name: str | None
    issuer_document: str | None
    recipient_name: str | None
    recipient_document: str | None
    total_amount: float | None
    parser_status: str
    processing_status: str
    payload_json: str | None


@dataclass
class Finding:
    id: int
    document_id: int
    severity: str
    code: str
    title: str
    message: str
    amount: float | None
    field: str | None
    source: str
    status: str


def row_to_dict(row: Any) -> dict:
    return dict(row) if row is not None else {}
