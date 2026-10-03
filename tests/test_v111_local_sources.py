from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from mshub.errors import ValidationError
from mshub.fetcher import _extract_zip_safely
from mshub.repository import SkillRepository


def _skill_source(path: Path, description: str = "local skill") -> None:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\ndescription: {description}\n---\n\nRun the skill.\n",
        encoding="utf-8",
    )


def test_local_directory_uses_explicit_name_without_source_validation(config_store):
    source = config_store.config_dir.parent / "本地来源"
    _skill_source(source)
    repository = SkillRepository(config_store)

    item = repository.install(str(source), item_name="我的技能", local_dir_name="我的技能")

    assert item["name"] == "我的技能"
    assert item["provider"] == "local"
    assert item["source_url"] == str(source.resolve())
    assert item["local_dir"].endswith("我的技能")
    assert item["manifest"]["source_type"] == "local"


def test_local_zip_uses_explicit_name_and_single_wrapper_directory(config_store, tmp_path: Path):
    archive = tmp_path / "来源包.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("wrapper/SKILL.md", "---\ndescription: zip source\n---\n\nRun.\n")
    repository = SkillRepository(config_store)

    item = repository.install(str(archive), item_name="zip技能", local_dir_name="zip技能")

    assert item["name"] == "zip技能"
    assert item["provider"] == "local"
    assert (config_store.config_dir.parent / "skills-repo" / item["local_dir"] / "SKILL.md").is_file()


def test_local_name_rejects_path_escape(config_store, tmp_path: Path):
    source = tmp_path / "source"
    _skill_source(source)
    with pytest.raises(ValidationError):
        SkillRepository(config_store).install(str(source), item_name="../escape")


def test_local_zip_rejects_traversal(tmp_path: Path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "x")
    with pytest.raises(ValidationError):
        _extract_zip_safely(archive, tmp_path / "out")


def test_ai_description_uses_local_material_and_returns_bilingual(monkeypatch, config_store, tmp_path: Path):
    source = tmp_path / "ai-source"
    _skill_source(source, "A skill that runs a local check")
    repository = SkillRepository(config_store)
    item = repository.install(str(source), item_name="ai-demo", local_dir_name="ai-demo")
    from mshub.native import memory_facade as facade_module
    from mshub.native.memory_facade import MemoryFacade

    seen = {}
    def fake_chat(_base, _key, _model, prompt, **_kwargs):
        seen["prompt"] = prompt
        return '{"zh":"本地检查技能。","en":"A local checking skill."}'

    monkeypatch.setattr(facade_module, "chat_completion", fake_chat)
    result = MemoryFacade(config_store).skill_ai_description(item["name"], item["library"])

    assert result == {"zh": "本地检查技能。", "en": "A local checking skill."}
    assert "A skill that runs a local check" in seen["prompt"]
