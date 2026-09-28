"""QWebChannel bridge for the local graph island."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QObject, QSettings, Signal, Slot

from .memory_facade import MemoryFacade
from .theme import graph_palette


class GraphBridge(QObject):
    openMemoryRequested = Signal(str)
    themeChanged = Signal(str)

    def __init__(self, facade: MemoryFacade, theme: str = "light", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.facade = facade
        self._theme = theme
        self._graph_settings: dict[str, Any] = {}
        self._graph_cache: dict[str, str] = {}
        self._settings_store = QSettings(str(facade.config_store.config_dir / "native-graph.ini"), QSettings.Format.IniFormat)
        self._graph_settings = {
            "includeTags": False, "showOrphans": True, "labelThreshold": 8,
            "nodeScale": 1, "selectedTypes": {"user": True, "project": True, "reference": True, "feedback": True},
            "forces": {"center": 1, "repel": 100, "link": 1, "distance": 80},
        }
        try:
            saved = json.loads(str(self._settings_store.value("graph", "{}")))
            if isinstance(saved, dict):
                self._graph_settings = {**self._graph_settings, **saved}
        except (TypeError, ValueError):
            pass

    @Slot(str, result=str)
    def getGraph(self, kinds: str = "link") -> str:
        normalized = kinds or "link"
        cached = self._graph_cache.get(normalized)
        if cached is not None:
            return cached
        try:
            payload = self.facade.graph(normalized)
        except Exception as exc:  # noqa: BLE001 - reported to the page as data
            # A missing repository must not surface in the island as a JSON
            # parse error ("Unexpected end of JSON input"): the slot raising
            # makes WebChannel deliver an empty string instead. Return a
            # structured payload so the page can show a proper hint.
            import logging

            logging.getLogger(__name__).exception("graph payload generation failed for kinds=%s", normalized)
            # ocr 审查修复：facade.graph 常因配置损坏而失败，此处再读 config()
            # 可能二次抛同一异常跳出 except——单独保护，失败按未配置处理。
            try:
                repo_root = str(getattr(self.facade.config(), "repo_root", "") or "").strip()
            except Exception:  # noqa: BLE001 - config itself may be broken
                repo_root = ""
            if not repo_root:
                reason = "repo-not-set"
                message = "尚未配置仓库根目录，请先在「设置选项 → 仓库与语言」选择并保存。"
            else:
                reason = "error"
                message = str(exc)
            return json.dumps(
                {"nodes": [], "edges": [], "unavailable": reason, "message": message},
                ensure_ascii=False,
            )
        self._graph_cache[normalized] = json.dumps(payload, ensure_ascii=False)
        return self._graph_cache[normalized]

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
        self._settings_store.setValue("graph", json.dumps(parsed, ensure_ascii=False))
        return True

    @Slot(result=str)
    def readGraphSettings(self) -> str:
        return json.dumps(self._graph_settings, ensure_ascii=False)

    def set_theme(self, theme: str) -> None:
        self._theme = str(theme)
        self.themeChanged.emit(self._theme)

    @Slot(result=str)
    def getPalette(self) -> str:
        return json.dumps(graph_palette(self._theme), ensure_ascii=False)
