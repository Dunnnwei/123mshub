"""Qt-friendly adapter around the existing MemoryService and prompt contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import ConfigStore
from ..database import Database
from ..memory_service import MemoryService
from ..prompts import build_duty_prompt, build_injection_prompt
from ..repository import SkillRepository
from ..tidy import TidyService
from ..importer import ImportService
from ..ai_presets import AI_PROVIDER_PRESETS


class MemoryFacade:
    def __init__(self, config_store: ConfigStore | None = None, service: MemoryService | None = None) -> None:
        self.config_store = config_store or ConfigStore()
        self.service = service or MemoryService(self.config_store)
        self.repository = SkillRepository(self.config_store)
        self.tidy = TidyService(self.config_store)
        self.importer = ImportService(self.config_store)

    def list_entries(self, *, query: str = "", type_filter: str = "", sort: str = "updated") -> dict[str, Any]:
        result = self.service.list_entries(query=query, type_filter=type_filter, sort=sort)
        result["stats"] = self.service.stats()
        return result

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

    def bulk_update(self, names: list[str], *, type_name: str | None = None, tags: list[str] | None = None):
        return self.service.bulk_update(names, type_name=type_name, tags=tags)

    def bulk_delete(self, names: list[str]):
        return self.service.bulk_delete(names)

    def ai_draft(self, body: str):
        return self.service.ai_draft(body)

    def index_file(self):
        return self.service.index_file_content()

    def rebuild(self):
        return self.repository.reconcile()

    def tidy_run(self, *, use_ai: bool = True):
        return self.tidy.run_tidy(use_ai=use_ai)

    def tidy_reports(self):
        return self.tidy.list_reports()

    def tidy_report(self, file_name: str):
        return self.tidy.read_report(file_name)

    def skills(self):
        return {"items": self.repository.list()}

    def skill(self, name: str, library: str = ""):
        return self.repository.get(name, library)

    def skill_tags(self):
        return self.repository.list_tags()

    def skill_preview(self, source: str, **kwargs):
        return self.repository.preview(source, **kwargs)

    def skill_install(self, source: str, **kwargs):
        return self.repository.install(source, **kwargs)

    def skill_update(self, name: str, library: str = "", **kwargs):
        return self.repository.update(name, library, **kwargs)

    def skill_check_version(self, name: str, library: str = ""):
        return self.repository.check_version(name, library)

    def skill_scan(self, name: str, library: str = "", **kwargs):
        return self.repository.scan(name, library, **kwargs)

    def skill_trust(self, name: str, library: str = ""):
        return self.repository.trust(name, library)

    def skill_delete(self, name: str, library: str = ""):
        return self.repository.delete(name, library)

    def skill_set_tags(self, name: str, tags: list[str], library: str = ""):
        return self.repository.set_tags(name, tags, library)

    def skill_translate(self, name: str, library: str = ""):
        return self.repository.translate_one(name, library)

    def skill_translate_batch(self, names: list[str] | None = None, progress=None):
        return self.repository.translate_descriptions(names, progress=progress)

    def skill_update_metadata(self, name: str, updates: dict[str, Any], library: str = ""):
        return self.repository.update_metadata(name, updates, library)

    def skill_install_prompt(self, name: str, library: str = ""):
        return self.repository.install_prompt(name, library)

    def library_prompt(self):
        return self.repository.library_prompt()

    def scan_import(self, source: Path):
        return self.importer.scan(source)

    def run_import(self, source: Path, **kwargs):
        return self.importer.run(source, **kwargs)

    @staticmethod
    def ai_presets():
        return list(AI_PROVIDER_PRESETS)

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
