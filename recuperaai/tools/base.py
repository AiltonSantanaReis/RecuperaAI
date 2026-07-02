from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from recuperaai.core.engine import ApplicationEngine


class ToolBase:
    name = 'base'
    label = 'Ferramenta'

    def __init__(self, engine: 'ApplicationEngine') -> None:
        self.engine = engine
