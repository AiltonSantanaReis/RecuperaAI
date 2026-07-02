from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from typing import Any


def _filter_dataclass_payload(cls: type, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {field.name for field in fields(cls)}
    return {key: value for key, value in payload.items() if key in allowed}


@dataclass
class InvoiceItem:
    code: str | None = None
    description: str | None = None
    ncm: str | None = None
    cfop: str | None = None
    cst: str | None = None
    csosn: str | None = None
    cest: str | None = None
    service_code: str | None = None
    unit: str | None = None
    quantity: float | None = None
    unit_value: float | None = None
    total_value: float | None = None
    discount: float | None = None
    taxes: dict[str, float] = field(default_factory=dict)


@dataclass
class InvoiceData:
    source_type: str
    invoice_key: str | None = None
    model: str | None = None
    document_type: str | None = None
    number: str | None = None
    series: str | None = None
    issue_date: str | None = None
    issuer_name: str | None = None
    issuer_document: str | None = None
    recipient_name: str | None = None
    recipient_document: str | None = None
    issuer_state: str | None = None
    recipient_state: str | None = None
    issuer_tax_regime: str | None = None
    operation_type: str | None = None
    operation_scope: str | None = None
    total_amount: float | None = None
    products_total: float | None = None
    services_total: float | None = None
    taxes: dict[str, float] = field(default_factory=dict)
    items: list[InvoiceItem] = field(default_factory=list)
    raw_text: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data['items'] = [asdict(item) for item in self.items]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InvoiceData":
        items = [InvoiceItem(**_filter_dataclass_payload(InvoiceItem, item)) for item in data.get('items', [])]
        clean = _filter_dataclass_payload(cls, {k: v for k, v in data.items() if k != 'items'})
        return cls(**clean, items=items)
