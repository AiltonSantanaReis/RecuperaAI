from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class OperationResult(Generic[T]):
    ok: bool
    message: str
    data: T | None = None
    errors: list[str] = field(default_factory=list)

    @classmethod
    def success(cls, message: str, data: T | None = None) -> "OperationResult[T]":
        return cls(ok=True, message=message, data=data)

    @classmethod
    def failure(cls, message: str, errors: list[str] | None = None) -> "OperationResult[T]":
        return cls(ok=False, message=message, errors=errors or [])
