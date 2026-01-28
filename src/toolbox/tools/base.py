from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from textual.screen import Screen


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    category: str
    screen_factory: Optional[Callable[[], Screen]] = None
