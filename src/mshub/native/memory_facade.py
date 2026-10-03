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
from ..translation import translate_description
from ..ai_gateway import chat_completion, strip_fence
import json


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

    def delete_entry(self, name: str, hard: bool = False) -> dict[str, Any]:
        return self.service.delete_entry(name, hard=hard)

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

    def bulk_delete(self, names: list[str], hard: bool = False):
        return self.service.bulk_delete(names, hard=hard)

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
        # A failed install may leave a recoverable index row without its
        # committed directory.  Keep the core repository's historical list
        # contract intact, but never expose that ghost through the native UI.
        root = self.config_store.require_repo_root().resolve()
        visible = []
        for item in self.repository.list():
            raw_dir = str(item.get("local_dir") or "").strip()
            if not raw_dir:
                continue
            target = (root / Path(raw_dir)).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                continue
            if target != root and target.is_dir():
                visible.append(item)
        return {"items": visible}

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

    def skill_delete(self, name: str, library: str = "", hard: bool = False):
        return self.repository.delete(name, library, hard=hard)

    def skill_set_tags(self, name: str, tags: list[str], library: str = ""):
        return self.repository.set_tags(name, tags, library)

    def skill_translate(self, name: str, library: str = ""):
        return self.repository.translate_one(name, library)

    def skill_translate_text(self, text: str, target: str = "zh") -> str:
        """v1.7.2：编辑器内即时翻译一段说明文本（不落库），target 为 zh/en。"""
        config = self.config_store.load()
        return translate_description(
            text,
            base_url=config.ai_base_url,
            api_key=self.config_store.get_secret("ai_key"),
            model=config.ai_model,
            target="en" if target == "en" else "zh",
        )

    def skill_translate_batch(self, names: list[str] | None = None, progress=None):
        return self.repository.translate_descriptions(names, progress=progress)

    def skill_ai_description(self, name: str, library: str = "") -> dict[str, str]:
        """Generate bilingual skill descriptions from the installed local files."""
        item = self.repository.get(name, library)
        root = Path(str(item.get("absolute_dir") or ""))
        if not root.is_dir():
            raise ValueError("技能目录不存在，无法生成 AI 说明。")
        materials: list[str] = []
        seen_materials: set[Path] = set()
        for candidate in (root / "SKILL.md", root / "skill.md", root / "README.md", root / "README.MD"):
            if candidate.is_file() and candidate not in seen_materials:
                text = candidate.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    materials.append(f"--- {candidate.name} ---\n{text[:12000]}")
                    seen_materials.add(candidate)
        if not materials:
            for candidate in sorted(root.glob("*.md"))[:3]:
                text = candidate.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    materials.append(f"--- {candidate.name} ---\n{text[:8000]}")
        if not materials:
            raise ValueError("技能目录没有可读取的 Markdown 说明材料。")
        config = self.config_store.load()
        prompt = (
            "你是 agent skill 文档编辑。仅根据下面的本地技能材料，生成清楚、准确、可执行的中英文说明。"
            "不要补充材料中没有的功能、集成、数据或性能承诺。输出严格 JSON，键为 zh 和 en，值为一段 1-3 句说明；"
            "不要 Markdown 围栏，不要额外键。技能名称：" + name + "\n\n" + "\n\n".join(materials)
        )
        raw = chat_completion(
            config.ai_base_url,
            self.config_store.get_secret("ai_key"),
            config.ai_model,
            prompt,
            timeout=90,
            json_mode=True,
            label="AI说明",
        )
        try:
            parsed = json.loads(strip_fence(raw))
        except json.JSONDecodeError as exc:
            raise ValueError("AI说明返回的不是有效 JSON。") from exc
        zh, en = str(parsed.get("zh") or "").strip(), str(parsed.get("en") or "").strip()
        if not zh or not en:
            raise ValueError("AI说明未同时返回中文和英文说明。")
        return {"zh": zh, "en": en}

    def skill_update_metadata(self, name: str, updates: dict[str, Any], library: str = ""):
        # Tags already have a stable public core entry point.  Keep metadata
        # edits in that contract and apply tags through set_tags so the native
        # adapter does not widen the repository method's write semantics.
        payload = dict(updates)
        tags = payload.pop("tags", None)
        result = self.repository.update_metadata(name, payload, library)
        if tags is not None:
            updated_name = str(result.get("name") or name)
            updated_library = str(result.get("library") or library)
            result = self.repository.set_tags(updated_name, list(tags), updated_library)
        return result

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
