"""Qt-friendly adapter around the existing MemoryService and prompt contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import ConfigStore
from ..database import Database
from ..memory_service import MemoryService
from ..prompts import build_duty_prompt, build_injection_prompt


class MemoryFacade:
    def __init__(self, config_store: ConfigStore | None = None, service: MemoryService | None = None) -> None:
        self.config_store = config_store or ConfigStore()
        self.service = service or MemoryService(self.config_store)

    def list_entries(self, *, query: str = "", type_filter: str = "", sort: str = "updated") -> dict[str, Any]:
        return self.service.list_entries(query=query, type_filter=type_filter, sort=sort)

    def get_entry(self, name: str) -> dict[str, Any]:
        return self.service.get_entry(name)

    def create_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.service.create_entry(payload)

    def update_entry(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.service.update_entry(name, payload)

    def delete_entry(self, name: str) -> dict[str, Any]:
        return self.service.delete_entry(name)

    def list_inbox(self) -> dict[str, Any]:
        return self.service.list_inbox()

    def admit_inbox(self, file_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.service.admit_inbox(file_name, payload)

    def discard_inbox(self, file_name: str) -> dict[str, Any]:
        return self.service.discard_inbox(file_name)

    def discard_all_inbox(self) -> dict[str, Any]:
        return self.service.discard_all_inbox()

    def graph(self, kinds: str = "link") -> dict[str, Any]:
        return self.service.graph(kinds)

    def stats(self) -> dict[str, Any]:
        return self.service.stats()

    def heal(self) -> dict[str, Any]:
        return self.service.heal()

    def config(self):
        return self.config_store.load()

    def save_config(self, updates: dict[str, Any]):
        return self.config_store.save(updates)

    def repo_root(self) -> Path:
        return self.config_store.require_repo_root()

    def injection_prompt(self) -> str:
        root = self.config_store.require_repo_root()
        memory_root = self.service.memory_root()
        skill_count = len(Database(root).list_skills())
        count = int(self.service.stats().get("total", 0))
        return build_injection_prompt(root, memory_root, count, skill_count)

    def duty_prompt(self) -> str:
        root = self.config_store.require_repo_root()
        memory_root = self.service.memory_root()
        skill_count = len(Database(root).list_skills())
        count = int(self.service.stats().get("total", 0))
        return build_duty_prompt(root, memory_root, count, skill_count)
