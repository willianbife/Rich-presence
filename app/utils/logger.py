from __future__ import annotations

from datetime import datetime
from typing import Callable


class AppLogger:
    def __init__(self) -> None:
        self._listeners: list[Callable[[str, str], None]] = []

    def subscribe(self, listener: Callable[[str, str], None]) -> None:
        self._listeners.append(listener)

    def log(self, message: str, level: str = "info") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        for listener in self._listeners:
            listener(entry, level)


logger = AppLogger()
