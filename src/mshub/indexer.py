from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .database import Database


def rebuild_index(repo_root: Path, database: Database) -> dict:
    skills = []
    for item in database.list_skills():
        skills.append({
            "name": item["name"],
            "item_type": item.get("item_type", "skill"),
            "author": item["author"],
            "provider": item.get("provider", "github"),
            "library": item.get("library", ""),
            "dir": item["local_dir"],
            "description": item["description"],
            "description_zh": item.get("description_zh", ""),
            "tags": item["tags"],
            "version": item["version"],
            "has_scripts": item["has_scripts"],
            "security_status": item["security_status"],
            "install_mode": item["install_mode"],
            "source_url": item["source_url"],
            "subdir": item["subdir"],
        })
    projection = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "skills": skills,
    }
    target = repo_root / "index.json"
    if target.exists() and _skills_unchanged(target, skills):
        # 技能清单实质没变就不落盘：generated_at 时间戳不算变化。
        # 这是同步盘环境下防"每次启动都制造一个假变更"的关键——
        # 两机数据库经回填收敛后，此分支命中，index.json 进入静默稳态。
        return projection
    content = json.dumps(projection, ensure_ascii=False, indent=2) + "\n"
    temporary = repo_root / ".index.json.tmp"
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, target)
    return projection


def _skills_unchanged(target: Path, skills: list[dict]) -> bool:
    try:
        existing = json.loads(target.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(existing, dict) or existing.get("schema_version") != 1:
        return False
    return existing.get("skills") == skills
