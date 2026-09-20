"""syncsafe 运输安全层测试：重试、容器、bundle、自愈、清单修复。"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mshub import syncsafe
from mshub import fsretry
from mshub.manifest import detect_local_changes, read_manifest, write_manifest
from mshub.recovery import recover_synced_records
from mshub.syncsafe import (
    BUNDLE_NAME,
    DOT_CONTAINER,
    GUIDE_NAME,
    clean_stale_staging,
    ensure_library_guide,
    find_conflict_files,
    quarantine_conflicts,
    refresh_git_bundle,
    repair_empty_manifests,
    restore_git_from_bundle,
    robust_copy2,
    self_heal_library,
    stage_dotfiles,
    sync_dotfiles,
    to_local,
    to_transport,
)


# ------------------------------------------------------------------- 映射


@pytest.mark.parametrize("relative", [
    ".gitignore",
    ".env.example",
    ".claude/settings.json",
    ".github/workflows/ci.yml",
    ".config/.hidden",
    "SKILL.md",
    "scripts/run.py",
])
def test_transport_mapping_roundtrip(relative):
    assert to_local(to_transport(relative)) == relative


def test_transport_mapping_shape():
    assert to_transport(".gitignore") == f"{DOT_CONTAINER}/dot.gitignore"
    assert to_transport("a/b.md") == "a/b.md"
    assert to_transport(".claude/settings.json") == f"{DOT_CONTAINER}/dot.claude/settings.json"


# ------------------------------------------------------------------- 重试


def test_robust_copy2_retries_transient_permission_error(tmp_path, monkeypatch):
    source = tmp_path / "src.txt"
    source.write_text("data", encoding="utf-8")
    target = tmp_path / "dst.txt"
    real_copy = shutil.copy2
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(13, "Permission denied")
        real_copy(src, dst)

    monkeypatch.setattr(shutil, "copy2", flaky)
    monkeypatch.setattr("mshub.fsretry.time.sleep", lambda _s: None)
    robust_copy2(source, target)
    assert calls["n"] == 3
    assert target.read_text(encoding="utf-8") == "data"


def test_robust_copy2_raises_after_exhausting_retries(tmp_path, monkeypatch):
    source = tmp_path / "src.txt"
    source.write_text("data", encoding="utf-8")

    def always_fail(_src, _dst):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(shutil, "copy2", always_fail)
    monkeypatch.setattr("mshub.fsretry.time.sleep", lambda _s: None)
    with pytest.raises(PermissionError):
        robust_copy2(source, tmp_path / "dst.txt")


# ------------------------------------------------------------------- 容器


def test_stage_dotfiles_moves_into_container(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "SKILL.md").write_text("skill", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignore", encoding="utf-8")
    (tmp_path / ".claude" / "settings.json").write_text("{}", encoding="utf-8")

    moved = stage_dotfiles(tmp_path)

    assert moved == 2
    assert not (tmp_path / ".gitignore").exists()
    assert not (tmp_path / ".claude").exists()
    assert (tmp_path / DOT_CONTAINER / "dot.gitignore").read_text(encoding="utf-8") == "ignore"
    assert (tmp_path / DOT_CONTAINER / "dot.claude" / "settings.json").read_text(encoding="utf-8") == "{}"
    assert (tmp_path / "SKILL.md").exists()


def test_stage_dotfiles_keeps_git_directory(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    assert stage_dotfiles(tmp_path) == 0
    assert (tmp_path / ".git" / "HEAD").exists()


def test_sync_dotfiles_materializes_on_fresh_machine(tmp_path):
    container = tmp_path / DOT_CONTAINER
    (container / "dot.claude").mkdir(parents=True)
    (container / "dot.gitignore").write_text("ignore", encoding="utf-8")
    (container / "dot.claude" / "settings.json").write_text("{}", encoding="utf-8")

    changed = sync_dotfiles(tmp_path)

    assert changed == 2
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "ignore"
    assert (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8") == "{}"


def test_sync_dotfiles_adopts_legacy_real_dotfiles(tmp_path):
    (tmp_path / ".gitignore").write_text("legacy", encoding="utf-8")

    changed = sync_dotfiles(tmp_path)

    assert changed == 1
    assert (tmp_path / DOT_CONTAINER / "dot.gitignore").read_text(encoding="utf-8") == "legacy"
    # 再跑一次：双向已收敛，无变动
    assert sync_dotfiles(tmp_path) == 0


def test_sync_dotfiles_container_wins_on_divergence(tmp_path):
    (tmp_path / ".gitignore").write_text("stale-local", encoding="utf-8")
    container = tmp_path / DOT_CONTAINER
    container.mkdir()
    (container / "dot.gitignore").write_text("fresh-remote", encoding="utf-8")

    sync_dotfiles(tmp_path)

    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "fresh-remote"


# ------------------------------------------------------------------- 清单


def test_write_manifest_records_transport_view(tmp_path):
    (tmp_path / "SKILL.md").write_text("skill", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignore", encoding="utf-8")
    container = tmp_path / DOT_CONTAINER
    container.mkdir()
    (container / "dot.gitignore").write_text("ignore", encoding="utf-8")

    manifest = write_manifest(
        tmp_path, source_url="https://github.com/a/b", commit_hash="h",
        install_mode="full", name="a/b", managed_files=["SKILL.md", ".gitignore"],
    )
    paths = [item["path"] for item in manifest["files"]]
    assert sorted(paths) == sorted(["SKILL.md", f"{DOT_CONTAINER}/dot.gitignore"])

    # 本地变化检测：全部一致 → 零噪音；点文件（物化产物）不算 untracked
    changes = detect_local_changes(tmp_path)
    assert changes == {"modified": [], "missing": [], "untracked": []}


def test_detect_local_changes_reports_container_edit(tmp_path):
    (tmp_path / "SKILL.md").write_text("skill", encoding="utf-8")
    write_manifest(
        tmp_path, source_url="https://github.com/a/b", commit_hash="h",
        install_mode="full", name="a/b",
    )
    container = tmp_path / DOT_CONTAINER / "dot.gitignore"
    container.parent.mkdir(parents=True)
    container.write_text("edited", encoding="utf-8")

    changes = detect_local_changes(tmp_path)
    assert changes["untracked"] == [f"{DOT_CONTAINER}/dot.gitignore"]


# ------------------------------------------------------------------- bundle


@pytest.mark.skipif(shutil.which("git") is None, reason="需要 git")
def test_git_bundle_roundtrip(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_AUTHOR_DATE": "2026-01-01T00:00:00",
           "GIT_COMMITTER_DATE": "2026-01-01T00:00:00"}
    for args in (
        ["git", "init", "-q", "-b", "main", str(repo)],
        ["git", "-C", str(repo), "add", "-A"],
        ["git", "-C", str(repo), "commit", "-q", "-m", "init", "--allow-empty"],
    ):
        subprocess.run(args, check=True, capture_output=True, env=env)

    assert refresh_git_bundle(repo) is True
    bundle = repo / BUNDLE_NAME
    assert bundle.is_file()

    # 模拟分机：删掉 .git，只剩 bundle → 还原（git 对象只读，先解锁再删）
    for path in (repo / ".git").rglob("*"):
        if path.is_file():
            path.chmod(0o666)
    shutil.rmtree(repo / ".git")
    write_manifest(
        repo, source_url="https://github.com/a/proj", commit_hash="h",
        install_mode="full", item_type="project", name="a/proj",
    )
    assert restore_git_from_bundle(repo) is True
    assert (repo / ".git").is_dir()
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    assert head.stdout.strip()
    origin = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True,
    )
    assert origin.stdout.strip() == "https://github.com/a/proj"
    # git 对象文件只读：清理成可写，避免 pytest 回收临时目录时被拒绝
    for path in repo.rglob("*"):
        if path.is_file():
            path.chmod(0o666)


# ------------------------------------------------------------------ 自愈件


def test_ensure_library_guide_idempotent(tmp_path):
    assert ensure_library_guide(tmp_path) is True
    guide = tmp_path / GUIDE_NAME
    assert guide.is_file()
    body = guide.read_text(encoding="utf-8")
    assert "index.json" in body
    assert ensure_library_guide(tmp_path) is False


def test_clean_stale_staging_removes_old_only(tmp_path):
    staging = tmp_path / ".meta" / "staging" / "demo-abc"
    staging.mkdir(parents=True)
    fresh = tmp_path / ".meta" / "staging" / "demo-xyz"
    fresh.mkdir(parents=True)
    import os
    old = syncsafe.time.time() - 7200
    os.utime(staging, (old, old))

    cleaned = clean_stale_staging(tmp_path)

    assert cleaned == 1
    assert not staging.exists()
    assert fresh.exists()


def test_quarantine_conflicts_moves_to_trash(tmp_path):
    skill_dir = tmp_path / "skills" / "demo__repo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("real", encoding="utf-8")
    conflict = skill_dir / "SKILL (DWPC 的冲突副本 2026).md"
    conflict.write_text("dupe", encoding="utf-8")

    assert find_conflict_files(tmp_path) == [f"skills/demo__repo/SKILL (DWPC 的冲突副本 2026).md"]
    moved = quarantine_conflicts(tmp_path)

    assert moved == [f"skills/demo__repo/SKILL (DWPC 的冲突副本 2026).md"]
    assert not conflict.exists()
    assert (skill_dir / "SKILL.md").exists()
    trash = list((tmp_path / ".meta" / "trash" / "conflicts").rglob("*.md"))
    assert len(trash) == 1 and trash[0].read_text(encoding="utf-8") == "dupe"


def test_repair_empty_manifests_rebuilds_from_disk(tmp_path):
    skill_dir = tmp_path / "skills" / "demo__repo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("skill", encoding="utf-8")
    write_manifest(
        skill_dir, source_url="https://github.com/demo/repo", commit_hash="h",
        install_mode="full", name="demo/repo",
    )
    manifest_path = skill_dir / "_manifest.json"
    poisoned = json.loads(manifest_path.read_text(encoding="utf-8"))
    poisoned["files"] = []
    manifest_path.write_text(json.dumps(poisoned, ensure_ascii=False), encoding="utf-8")

    repaired = repair_empty_manifests(tmp_path)

    assert repaired == 1
    manifest = read_manifest(skill_dir)
    assert [item["path"] for item in manifest["files"]] == ["SKILL.md"]
    # 修复幂等
    assert repair_empty_manifests(tmp_path) == 0


def test_refresh_transport_view_rewrites_legacy_dot_paths(tmp_path):
    """旧版清单记录真实点文件路径 → 刷新为容器路径，消除过渡期噪音。"""
    from mshub.syncsafe import refresh_manifest_transport_view

    skill_dir = tmp_path / "skills" / "demo__repo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("skill", encoding="utf-8")
    (skill_dir / ".gitignore").write_text("ignore", encoding="utf-8")
    # 旧版清单：files 里记的是真实点文件路径
    write_manifest(
        skill_dir, source_url="https://github.com/demo/repo", commit_hash="h",
        install_mode="full", name="demo/repo", managed_files=["SKILL.md", ".gitignore"],
    )
    manifest_path = skill_dir / "_manifest.json"
    legacy = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy["files"] = [
        {"path": "SKILL.md", "sha256": legacy["files"][0]["sha256"], "size": 5},
        {"path": ".gitignore", "sha256": "x", "size": 6},
    ]
    manifest_path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    # 真实流程中自愈先收编点文件进容器，再刷新清单视图
    assert sync_dotfiles(skill_dir) == 1

    refreshed = refresh_manifest_transport_view(skill_dir)

    assert refreshed is True
    manifest = read_manifest(skill_dir)
    assert sorted(item["path"] for item in manifest["files"]) == sorted([
        "SKILL.md", f"{DOT_CONTAINER}/dot.gitignore",
    ])
    # 已是运输视图后再跑：无操作
    assert refresh_manifest_transport_view(skill_dir) is False
    # 点文件不再显示为本地变化
    assert detect_local_changes(skill_dir)["untracked"] == []


def test_refresh_transport_view_keeps_untracked_visible_files(tmp_path):
    """普通未跟踪文件（用户手工新增）不被吸收进清单，仍如实报告。"""
    from mshub.syncsafe import refresh_manifest_transport_view

    (tmp_path / "SKILL.md").write_text("skill", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignore", encoding="utf-8")
    (tmp_path / "my-note.txt").write_text("user file", encoding="utf-8")
    write_manifest(
        tmp_path, source_url="https://github.com/a/b", commit_hash="h",
        install_mode="full", name="a/b", managed_files=["SKILL.md"],
    )
    sync_dotfiles(tmp_path)  # 收编 .gitignore 进容器
    # 手工构造旧版清单：files 记真实点文件路径
    manifest_path = tmp_path / "_manifest.json"
    legacy = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy["files"].append({"path": ".gitignore", "sha256": "x", "size": 6})
    manifest_path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    assert refresh_manifest_transport_view(tmp_path) is True
    manifest = read_manifest(tmp_path)
    paths = [item["path"] for item in manifest["files"]]
    assert f"{DOT_CONTAINER}/dot.gitignore" in paths
    assert "my-note.txt" not in paths
    assert detect_local_changes(tmp_path)["untracked"] == ["my-note.txt"]


def test_recovery_skips_empty_directory(tmp_path):
    """空目录（同步未完成）不再被识别——2026-09-10 分机事故的防护。"""
    from mshub.database import Database

    empty_dir = tmp_path / "skills" / "still-syncing__repo"
    empty_dir.mkdir(parents=True)

    database = Database(tmp_path)
    recovered = recover_synced_records(tmp_path, database)

    assert recovered == 0
    assert database.list_skills() == []
    assert not (empty_dir / "_manifest.json").exists()


def test_self_heal_library_runs_all_steps(tmp_path):
    skill_dir = tmp_path / "skills" / "demo__repo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("skill", encoding="utf-8")
    (skill_dir / ".gitignore").write_text("ignore", encoding="utf-8")
    (skill_dir / "_manifest.json").write_text(
        json.dumps({"files": [], "source_url": "https://github.com/demo/repo"}, ensure_ascii=False),
        encoding="utf-8",
    )
    staging = tmp_path / ".meta" / "staging" / "leftover"
    staging.mkdir(parents=True)
    import os
    old = syncsafe.time.time() - 7200
    os.utime(staging, (old, old))

    result = self_heal_library(tmp_path)

    assert result["guide_written"] is True
    assert (tmp_path / GUIDE_NAME).is_file()
    assert result["staging_cleaned"] == 1
    assert not staging.exists()
    assert result["manifests_repaired"] == 1
    assert result["dotfiles_synced"] == 1
    assert (skill_dir / DOT_CONTAINER / "dot.gitignore").exists()
    assert result["errors"] == []
