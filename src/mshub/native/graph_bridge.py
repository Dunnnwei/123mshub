"""QWebChannel bridge for the local graph island."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from .memory_facade import MemoryFacade


class GraphBridge(QObject):
    openMemoryRequested = Signal(str)
    themeChanged = Signal(str)

    def __init__(self, facade: MemoryFacade, theme: str = "light", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.facade = facade
        self._theme = theme
        self._graph_settings: dict[str, Any] = {}
        self._graph_cache: dict[str, str] = {}

    @Slot(str, result=str)
    def getGraph(self, kinds: str = "link") -> str:
        normalized = kinds or "link"
        cached = self._graph_cache.get(normalized)
        if cached is not None:
            return cached
        payload = json.dumps(self.facade.graph(normalized), ensure_ascii=False)
        self._graph_cache[normalized] = payload
        return payload

    def set_graph_cache(self, kinds: str, payload: dict[str, Any]) -> None:
        """Accept a worker-produced graph payload before the page asks for it."""

        self._graph_cache[kinds or "link"] = json.dumps(payload, ensure_ascii=False)

    def invalidate(self) -> None:
        self._graph_cache.clear()

    @Slot(str)
    def openMemory(self, name: str) -> None:
        self.openMemoryRequested.emit(str(name))

    @Slot(result=str)
    def getTheme(self) -> str:
        return json.dumps({"theme": self._theme}, ensure_ascii=False)

    @Slot(str, result=bool)
    def writeGraphSettings(self, payload: str) -> bool:
        try:
            parsed = json.loads(payload or "{}")
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        self._graph_settings = parsed
        return True

    @Slot(result=str)
    def readGraphSettings(self) -> str:
        return json.dumps(self._graph_settings, ensure_ascii=False)

    def set_theme(self, theme: str) -> None:
        self._theme = str(theme)
        self.themeChanged.emit(self._theme)
