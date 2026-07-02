from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, DefaultDict
from collections import defaultdict


@dataclass(frozen=True)
class AppEvent:
    name: str
    payload: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, list[Callable[[AppEvent], None]]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: Callable[[AppEvent], None]) -> None:
        self._subscribers[event_name].append(callback)

    def publish(self, name: str, **payload) -> None:
        event = AppEvent(name=name, payload=payload)
        for callback in list(self._subscribers.get(name, [])):
            callback(event)
        for callback in list(self._subscribers.get("*", [])):
            callback(event)
