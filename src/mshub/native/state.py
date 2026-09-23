"""Application state shared by native views."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, Signal


@dataclass(slots=True)
class AppSnapshot:
    repo_root: str = ""
    memory_root: str = ""
    theme: str = "system"
    entries: list[dict[str, Any]] = field(default_factory=list)
    inbox_pending: int = 0
    selected_name: str = ""
    busy: bool = False
    last_error: str = ""


class AppState(QObject):
    changed = Signal()
    theme_changed = Signal(str)
    entries_changed = Signal()
    error_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.snapshot = AppSnapshot()

    def update(self, **updates: Any) -> None:
        theme = updates.get("theme")
        error = updates.get("last_error")
        entries = "entries" in updates or "inbox_pending" in updates
        for key, value in updates.items():
            if hasattr(self.snapshot, key):
                setattr(self.snapshot, key, value)
        if theme is not None:
            self.theme_changed.emit(str(theme))
        if error is not None:
            self.error_changed.emit(str(error))
        if entries:
            self.entries_changed.emit()
        self.changed.emit()

    def clear_error(self) -> None:
        self.update(last_error="")

