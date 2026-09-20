from __future__ import annotations

import json
from pathlib import Path

import pytest

from mshub.config import ConfigStore
from mshub.errors import ValidationError
from mshub.importer import ImportService
from mshub.memory_service import MemoryService


@pytest.fixture()
def service(tmp_path: Path) -> ImportService:
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    return ImportService(store)


def _make_dsh(source: Path) -> None:
    """构造 DSH 总机格式：memory.md 索引 + brain\\ 条目 + brain\\inbox\\ 投递。"""
    brain = source / "brain"
    (brain / "inbox").mkdir(parents=True)
    (brain / "user-profile.md").write_text(
        "---\nname: user-profile\ndescription: 用户画像\ntype: user\n"
        "created: 2026-08-18\nupdated: 2026-09-08\nscope: global\n---\n\n用户画像正文。\n",
        encoding="utf-8", newline="\n",
    )
    (brain / "reference-arch.md").write_text(
        "---\nname: reference-arch\ndescription: 架构速查\ntype: reference\n---\n\n架构正文。\n",
        encoding="utf-8", newline="\n",
    )
    (brain / "inbox" / "pending-note.md").write_text(
        "---\nname: pending-note\ndescription: 待收编\ntype: feedback\n---\n\n投递正文。\n",
        encoding="utf-8", newline="\n",
    )
    (source / "memory.md").write_text(
        "# memory.md\n\n- [用户画像](brain/user-profile.md) — 用户偏好速查\n"
        "- [架构速查](brain/reference-arch.md) — 星型架构\n",
        encoding="utf-8", newline="\n",
    )
    # 干扰项：不是记忆的文件
    (source / "README.md").write_text("# 项目说明\n没有 frontmatter。\n", encoding="utf-8")
    (source / "随便.md").write_text("没有 frontmatter 的散文本。\n", encoding="utf-8")


def _make_mshub_repo(source: Path) -> None:
    notes = source / "memory" / "notes"
    notes.mkdir(parents=True)
    (notes / "remote-note.md").write_text(
        "---\nname: remote-note\ntitle: 远端条目\ndescription: 另一台机的记忆\ntype: project\n"
        "source: agent\ncreated: 2026-09-01\nupdated: 2026-09-02\n---\n\n远端正文。\n",
        encoding="utf-8", newline="\n",
    )
    (source / "memory" / "MEMORY.md").write_text(
        "# MEMORY.md\n\n## project\n- [远端条目](notes/remote-note.md) — 另一台机的记忆\n",
        encoding="utf-8", newline="\n",
    )


def _make_skill_source(source: Path) -> None:
    # skillrepo 格式技能（带 manifest）
    skill_dir = source / "skillhub" / "skills" / "owner__demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\ndescription: 演示技能。\n---\n用法。\n", encoding="utf-8")
    (skill_dir / "_manifest.json").write_text(json.dumps({
        "name": "owner/demo", "source_type": "github", "library": "skills",
        "source_url": "https://github.com/owner/demo", "description": "演示技能。",
        "install_mode": "standard", "item_type": "skill", "ref": "HEAD",
        "subdir": "", "fetcher": "archive", "version": "1.0",
        "generated_at": "2026-09-19T00:00:00+00:00",
        "files": [{"path": "SKILL.md", "sha256": "x" * 64, "size": 10}],
    }, ensure_ascii=False), encoding="utf-8")
    (source / "skillhub" / "index.json").write_text(json.dumps({
        "schema_version": 1, "skills": [
            {"name": "owner/demo", "dir": "skills/owner__demo", "provider": "github",
             "description": "演示技能。", "tags": []},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    # 纯 SKILL.md 目录（本地自研候选）
    local_dir = source / "agent-skills" / "my-local-skill"
    local_dir.mkdir(parents=True)
    (local_dir / "SKILL.md").write_text("---\ndescription: 本地技能。\n---\n本地用法。\n", encoding="utf-8")
    # 干扰目录：node_modules 里的 SKILL.md 不收
    junk = source / "node_modules" / "junk-skill"
    junk.mkdir(parents=True)
    (junk / "SKILL.md").write_text("---\ndescription: 干扰。\n---\n", encoding="utf-8")


class TestScan:
    def test_scan_dsh_recognizes_all(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "dsh"
        _make_dsh(source)
        report = service.scan(str(source))
        assert report["memory_count"] == 3  # 2 条 brain + 1 条 inbox
        kinds = report["memory_by_kind"]
        assert kinds.get("dsh") == 3
        by_name = {item["name"]: item for item in report["memory_preview"]}
        assert by_name["user-profile"]["title"] == "用户画像"  # 标题取自索引行
        assert report["skill_count"] == 0

    def test_scan_mshub_repo(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "other-mshub"
        _make_mshub_repo(source)
        report = service.scan(str(source))
        assert report["memory_by_kind"].get("mshub") == 1

    def test_scan_loose_memory(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "workbuddy"
        source.mkdir()
        (source / "note-a.md").write_text(
            "---\nname: note-a\ndescription: workbuddy 记忆\ntype: feedback\ncreated: 2026-09-01\n---\n\n正文。\n",
            encoding="utf-8",
        )
        (source / "plain.md").write_text("没有元信息的 md。\n", encoding="utf-8")
        report = service.scan(str(source))
        assert report["memory_count"] == 1
        assert report["memory_by_kind"].get("loose") == 1

    def test_scan_skills(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "skills-src"
        _make_skill_source(source)
        report = service.scan(str(source))
        dirs = {item["dir"] for item in report["skill_preview"]}
        assert "owner__demo" in dirs
        assert "my-local-skill" in dirs
        assert "junk-skill" not in dirs  # node_modules 排除
        by_dir = {item["dir"]: item for item in report["skill_preview"]}
        assert by_dir["owner__demo"]["kind"] == "skillrepo"
        assert by_dir["my-local-skill"]["kind"] == "skill-local"

    def test_skill_dir_templates_not_imported_as_memory(self, service: ImportService, tmp_path: Path) -> None:
        """技能目录内长得像记忆的模板 md 不再走散装记忆通道（v1.2.4：engramory 模板误入修复）。"""
        source = tmp_path / "tpl"
        skill = source / "skillhub" / "skills" / "engramory"
        (skill / "templates").mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\ndescription: engramory 协议技能。\n---\n用法。\n", encoding="utf-8")
        (skill / "templates" / "example-feedback.md").write_text(
            "---\nname: example-fb\ndescription: 模板示例\ntype: feedback\ncreated: 2026-01-01\n---\n\n模板正文。\n",
            encoding="utf-8",
        )
        report = service.scan(str(source))
        assert report["skill_count"] == 1
        assert report["memory_count"] == 0
        assert any("防模板示例误入" in note for note in report["notes"])

    def test_duplicate_skill_targets_deduped(self, service: ImportService, tmp_path: Path) -> None:
        """不同来源路径、同一目标（库+目录名）的技能候选只留一个（v1.2.4：预览口径与导入结果对齐）。"""
        source = tmp_path / "dup-skill"
        for sub in ("place-a", "place-b"):
            skill_dir = source / sub / "demo-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\ndescription: 同名技能。\n---\n用法。\n", encoding="utf-8")
        report = service.scan(str(source))
        assert report["skill_count"] == 1

    def test_scan_missing_dir_raises(self, service: ImportService) -> None:
        with pytest.raises(ValidationError):
            service.scan("Z:/definitely/not/exist")

    def test_scan_is_read_only(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "dsh"
        _make_dsh(source)
        service.scan(str(source))
        # 扫描不写仓库：notes 目录里没有任何 md
        repo = tmp_path / "repo"
        notes = repo / "memory" / "notes"
        assert not notes.exists() or not list(notes.glob("*.md"))


class TestRun:
    def test_import_dsh_memories(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "dsh"
        _make_dsh(source)
        result = service.run(str(source))
        assert result["memory_imported"] == 3
        assert result["memory_failed"] == []
        memory = MemoryService(service.config_store)
        detail = memory.get_entry("user-profile")
        assert detail["title"] == "用户画像"
        assert detail["type"] == "user"
        assert "用户画像正文" in detail["body"]
        pending = memory.get_entry("pending-note")  # brain\inbox 的投递也进来了
        assert pending["description"] == "待收编"
        # 索引已重建
        index = memory.index_file_content()["content"]
        assert "(notes/user-profile.md)" in index

    def test_import_mshub_and_skills(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "combined"
        source.mkdir()
        _make_mshub_repo(source)
        _make_skill_source(source)
        result = service.run(str(source))
        assert result["memory_imported"] == 1
        assert len(result["skills_imported"]) == 2
        # 技能入册（reconcile 后）
        skills = {item["name"]: item for item in service.repository.list()}
        assert "owner/demo" in skills
        assert skills["owner/demo"]["library"] == "skills"
        local_names = [name for name in skills if name == "my-local-skill"]
        assert local_names  # SKILL.md 目录按本地自研收录
        # v1.2.0 吸收：SKILL.md 目录导入即自动跑离线安全检查（不再停在「尚未检查」）
        assert skills["my-local-skill"]["security_status"] != "unchecked"
        # 远端记忆带 source=agent 保留
        assert MemoryService(service.config_store).get_entry("remote-note")["source"] == "agent"

    def test_reimport_same_source_skips_identical(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "dsh"
        _make_dsh(source)
        first = service.run(str(source))
        assert first["memory_imported"] == 3
        second = service.run(str(source))
        assert second["memory_imported"] == 0
        assert len(second["memory_skipped_same"]) == 3
        assert second["skills_skipped"] == []

    def test_conflicting_content_renames(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "dsh"
        _make_dsh(source)
        memory = MemoryService(service.config_store)
        memory.create_entry({
            "title": "同名但内容不同", "name": "user-profile",
            "description": "程序里已有的条目", "body": "本地正文不一样。",
        })
        result = service.run(str(source))
        assert "user-profile → user-profile-2" in result["memory_renamed"]
        assert memory.get_entry("user-profile")["description"] == "程序里已有的条目"
        assert "用户画像正文" in memory.get_entry("user-profile-2")["body"]
        # 再次导入同一来源：-2 已存在且实质内容相同 → 幂等跳过，不再生成 -3
        again = service.run(str(source))
        assert again["memory_imported"] == 0
        assert "user-profile-2" in again["memory_skipped_same"]
        assert not any("user-profile-3" in item for item in again["memory_renamed"])

    def test_chinese_filename_in_source_does_not_abort(self, service: ImportService, tmp_path: Path) -> None:
        """来源里 name 为纯中文的条目：单条失败不中止整批（ocr 审查 #high 修复）。"""
        source = tmp_path / "cn"
        source.mkdir()
        (source / "good.md").write_text(
            "---\nname: good-one\ndescription: ok\ntype: reference\n---\n\n正文。\n",
            encoding="utf-8",
        )
        (source / "bad.md").write_text(
            "---\nname: 中文名\ndescription: 无法转 kebab\ntype: reference\n---\n\n正文。\n",
            encoding="utf-8",
        )
        result = service.run(str(source))
        assert result["memory_imported"] == 1
        assert len(result["memory_failed"]) == 1
        assert "bad.md" in result["memory_failed"][0]

    def test_duplicate_groups_reported(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "dup"
        source.mkdir()
        for name in ("a", "b"):
            (source / f"{name}.md").write_text(
                f"---\nname: {name}\ndescription: x\ntype: reference\n---\n\n正文 {name}\n",
                encoding="utf-8",
            )
        (source / "MEMORY.md").write_text(
            "# MEMORY.md\n\n- [重复标题](a.md) — x\n- [重复 标题](b.md) — x\n",
            encoding="utf-8",
        )
        result = service.run(str(source))
        # 标题归一化后相同（重复标题 / 重复 标题）→ 报疑似重复组
        assert any("a" in group and "b" in group for group in result["duplicate_groups"])

    def test_tidy_report_generated(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "dsh"
        _make_dsh(source)
        result = service.run(str(source))
        assert result["tidy_report"]["file"].endswith(".md")
        assert "整理日报" in result["tidy_report"]["content"]

    def test_include_flags(self, service: ImportService, tmp_path: Path) -> None:
        source = tmp_path / "combined"
        source.mkdir()
        _make_dsh(source)
        _make_skill_source(source)
        result = service.run(str(source), include_memory=False, include_skills=True)
        assert result["memory_imported"] == 0
        assert len(result["skills_imported"]) == 2
        result2 = service.run(str(source), include_memory=True, include_skills=False)
        assert result2["memory_imported"] == 3
        assert result2["skills_imported"] == []


class TestImportApi:
    @staticmethod
    def _wait_job(client, job_id, timeout_seconds: float = 20.0):
        import time

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            jobs = client.get("/api/jobs").json()["items"]
            job = next(item for item in jobs if item["id"] == job_id)
            if job["status"] != "running":
                return job
            time.sleep(0.1)
        raise AssertionError(f"任务超时未完成：{job_id}")

    def test_scan_and_run_via_jobs(self, tmp_path: Path) -> None:
        from fastapi.testclient import TestClient

        from mshub.api import create_app

        store = ConfigStore(tmp_path / "config")
        store.save({"repo_root": str(tmp_path / "repo")})
        client = TestClient(create_app(store))
        source = tmp_path / "dsh"
        _make_dsh(source)

        scan = client.post("/api/migration/scan", json={"path": str(source)})
        assert scan.status_code == 200
        job = self._wait_job(client, scan.json()["job_id"])
        assert job["status"] == "done", job
        assert job["result"]["memory_count"] == 3

        run = client.post("/api/migration/run", json={"path": str(source)})
        assert run.status_code == 200
        job = self._wait_job(client, run.json()["job_id"])
        assert job["status"] == "done", job
        assert job["result"]["memory_imported"] == 3

    def test_scan_requires_repo_root(self, tmp_path: Path) -> None:
        from fastapi.testclient import TestClient

        from mshub.api import create_app

        client = TestClient(create_app(ConfigStore(tmp_path / "empty-config")))
        response = client.post("/api/migration/scan", json={"path": str(tmp_path)})
        assert response.status_code == 400
        assert "仓库根" in response.json()["detail"]
