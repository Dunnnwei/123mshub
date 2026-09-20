import json
import sqlite3
from pathlib import Path

import pytest

from mshub.config import ConfigStore
from mshub.database import SCHEMA, Database
from mshub.errors import ConflictError, ValidationError
from mshub.manifest import detect_local_changes, write_manifest
from mshub.repository import SkillRepository
from mshub.tags import normalize_tags


def test_install_manifest_index_and_prompt(config_store, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    repository = SkillRepository(config_store)

    preview = repository.preview("owner/demo")
    assert preview["selected_file_count"] == 4
    assert "scripts/run.py" in preview["files"]

    installed = repository.install("owner/demo")
    root = Path(config_store.load().repo_root)
    skill_dir = root / "owner__demo"
    assert installed["install_mode"] == "standard"
    assert (skill_dir / "SKILL.md").exists()
    assert not (skill_dir / "assets" / "large.txt").exists()
    manifest = json.loads((skill_dir / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["install_mode"] == "standard"
    assert manifest["scan"]["status"] == "safe"

    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert index["schema_version"] == 1
    assert index["skills"][0]["name"] == "owner/demo"
    prompt = repository.install_prompt("owner/demo")
    assert "`owner/demo`" in prompt
    assert "_共享技能库使用说明.md" in prompt
    assert "index.json" in prompt
    assert "SKILL.md" in prompt
    library_prompt = repository.library_prompt()
    # MSHub：升级为全局注入提示词（记忆读取 + 技能使用 + 记忆投递 + 暗号）
    assert "123 MSHub 共享大脑接入" in library_prompt
    assert "记忆读取协议" in library_prompt
    assert "技能库使用协议" in library_prompt
    assert "记忆投递协议" in library_prompt
    assert "AI猛如虎" in library_prompt
    assert str(root) in library_prompt

    with pytest.raises(ConflictError):
        repository.install("owner/demo")


def test_list_recovers_synced_skill_when_database_is_missing(tmp_path: Path) -> None:
    root = tmp_path / "synced-repo"
    skill_dir = root / "owner__demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: 从其他电脑同步的技能。\n---\n",
        encoding="utf-8",
    )
    (skill_dir / ".manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "source_url": "https://github.com/owner/demo",
            "commit_hash": "a" * 40,
            "install_mode": "standard",
            "generated_at": "2026-08-01T00:00:00+00:00",
            "files": [],
            "scan": {"status": "safe", "route": "offline", "findings": []},
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "index.json").write_text(
        json.dumps({
            "schema_version": 1,
            "skills": [{
                "name": "owner/demo",
                "dir": "owner__demo",
                "description": "从其他电脑同步的技能。",
                "tags": ["已同步"],
                "subdir": "",
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    store = ConfigStore(tmp_path / "fresh-config")
    store.save({"repo_root": str(root)})

    items = SkillRepository(store).list()

    assert len(items) == 1
    assert items[0]["name"] == "owner/demo"
    assert items[0]["tags"] == ["已同步"]


def test_stale_keyring_token_is_ignored_until_configured(
    config_store, fake_fetcher, monkeypatch
) -> None:
    tokens: list[str] = []
    original_fetch = fake_fetcher.fetch

    def tracked_fetch(source, *, mirrors, proxy, token):
        tokens.append(token)
        return original_fetch(
            source,
            mirrors=mirrors,
            proxy=proxy,
            token=token,
        )

    monkeypatch.setattr(fake_fetcher, "fetch", tracked_fetch)
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    monkeypatch.setattr(config_store, "get_secret", lambda _: "stale-or-configured-token")
    repository = SkillRepository(config_store)

    repository.preview("owner/demo")
    config_store.save({"github_token_configured": True})
    repository.preview("owner/demo")

    assert tokens == ["", "stale-or-configured-token"]


def test_project_clone_preserves_git_metadata_and_records_item_type(
    config_store, monkeypatch, tmp_path: Path
) -> None:
    class FakeProjectFetcher:
        name = "git"

        def fetch(self, source, *, mirrors, proxy, token):
            from mshub.models import FetchResult

            checkout = tmp_path / "project-fetch" / "checkout"
            (checkout / ".git").mkdir(parents=True)
            (checkout / ".git" / "config").write_text(
                "[remote \"origin\"]\nurl = https://github.com/owner/app\n",
                encoding="utf-8",
            )
            (checkout / "README.md").write_text("# Demo app\n", encoding="utf-8")
            (checkout / "package.json").write_text('{"name":"demo-app"}', encoding="utf-8")
            return FetchResult(
                root=checkout,
                commit_hash="c" * 40,
                commit_date="2026-08-09T00:00:00Z",
                ref="main",
                fetcher="git",
                temp_root=checkout.parent,
            )

    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: FakeProjectFetcher())

    installed = SkillRepository(config_store).install(
        "owner/app",
        item_type="project",
    )

    target = Path(config_store.load().repo_root) / "owner__app"
    assert installed["item_type"] == "project"
    assert installed["install_mode"] == "full"
    assert installed["fetcher"] == "git"
    assert (target / ".git" / "config").is_file()
    assert (target / "package.json").is_file()
    assert "应用项目" in SkillRepository(config_store).install_prompt("owner/app")
    with pytest.raises(ValidationError, match="应用项目"):
        SkillRepository(config_store).change_mode("owner/app", "standard")


def test_project_update_keeps_project_mode_and_git_metadata(
    config_store, monkeypatch, tmp_path: Path
) -> None:
    class VersionedProjectFetcher:
        name = "git"
        revision = 1

        def fetch(self, source, *, mirrors, proxy, token):
            from mshub.models import FetchResult

            checkout = tmp_path / f"project-fetch-{self.revision}" / "checkout"
            (checkout / ".git").mkdir(parents=True)
            (checkout / ".git" / "config").write_text("[core]\n", encoding="utf-8")
            (checkout / "README.md").write_text("# Demo app\n", encoding="utf-8")
            (checkout / "version.txt").write_text(str(self.revision), encoding="utf-8")
            return FetchResult(
                root=checkout,
                commit_hash=("c" if self.revision == 1 else "d") * 40,
                commit_date="2026-08-09T00:00:00Z",
                ref="main",
                fetcher="git",
                temp_root=checkout.parent,
            )

    fetcher = VersionedProjectFetcher()
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fetcher)
    repository = SkillRepository(config_store)
    repository.install("owner/app", item_type="project")
    fetcher.revision = 2
    monkeypatch.setattr(
        "mshub.repository.remote_version",
        lambda *args, **kwargs: ("d" * 40, "2026-08-09T01:00:00Z"),
    )

    result = repository.update("owner/app")

    target = Path(config_store.load().repo_root) / "owner__app"
    assert result["skill"]["item_type"] == "project"
    assert (target / ".git" / "config").is_file()
    assert (target / "version.txt").read_text(encoding="utf-8") == "2"


def test_project_type_is_recovered_from_synced_manifest(
    config_store, monkeypatch, tmp_path: Path
) -> None:
    class FakeProjectFetcher:
        name = "git"

        def fetch(self, source, *, mirrors, proxy, token):
            from mshub.models import FetchResult

            checkout = tmp_path / "recoverable-project" / "checkout"
            (checkout / ".git").mkdir(parents=True)
            (checkout / "README.md").write_text("# Recoverable app\n", encoding="utf-8")
            return FetchResult(
                root=checkout,
                commit_hash="e" * 40,
                commit_date="2026-08-09T00:00:00Z",
                ref="main",
                fetcher="git",
                temp_root=checkout.parent,
            )

    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: FakeProjectFetcher())
    SkillRepository(config_store).install("owner/app", item_type="project")
    root = Path(config_store.load().repo_root)
    database_path = root / ".meta" / "skills.db"
    database_path.unlink()
    fresh_store = ConfigStore(tmp_path / "new-system-config")
    fresh_store.save({"repo_root": str(root)})

    recovered = SkillRepository(fresh_store).list()

    assert recovered[0]["item_type"] == "project"
    assert recovered[0]["fetcher"] == "git"
    assert recovered[0]["ref"] == "main"


def test_list_recovers_legacy_directory_without_database_or_manifest(
    config_store,
) -> None:
    root = Path(config_store.load().repo_root)
    legacy_dir = root / "owner__legacy-tools"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "README.md").write_text(
        "# Legacy tools\n\n从旧版仓库同步来的工具集合。\n",
        encoding="utf-8",
    )

    recovered = SkillRepository(config_store).list()

    assert len(recovered) == 1
    assert recovered[0]["name"] == "owner/legacy-tools"
    assert recovered[0]["source_url"] == "https://github.com/owner/legacy-tools"
    assert recovered[0]["install_mode"] == "full"
    assert (legacy_dir / "_manifest.json").is_file()


def test_local_change_detection_ignores_internal_git_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (project / "README.md").write_text("# Project\n", encoding="utf-8")
    write_manifest(
        project,
        source_url="https://github.com/owner/app",
        commit_hash="f" * 40,
        install_mode="full",
        item_type="project",
        managed_files=["README.md"],
    )

    changes = detect_local_changes(project)

    assert changes == {"modified": [], "missing": [], "untracked": []}


def test_mode_change_preserves_manual_content(config_store, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    repository = SkillRepository(config_store)
    repository.install("owner/demo", mode="full")
    root = Path(config_store.load().repo_root)
    skill_dir = root / "owner__demo"

    (skill_dir / "assets" / "large.txt").write_text("user-edited", encoding="utf-8")
    (skill_dir / "notes.txt").write_text("manual note", encoding="utf-8")
    changed = repository.change_mode("owner/demo", "standard")

    assert changed["install_mode"] == "standard"
    assert (skill_dir / "assets" / "large.txt").read_text(encoding="utf-8") == "user-edited"
    assert (skill_dir / "notes.txt").read_text(encoding="utf-8") == "manual note"
    assert set(changed["preserved_files"]) == {"assets/large.txt", "notes.txt"}
    assert repository.local_changes("owner/demo")["untracked"] == [
        "assets/large.txt", "notes.txt"
    ]


def test_update_backs_up_local_changes(config_store, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    repository = SkillRepository(config_store)
    repository.install("owner/demo")
    root = Path(config_store.load().repo_root)
    skill_dir = root / "owner__demo"
    (skill_dir / "scripts" / "run.py").write_text("print('hand edit')", encoding="utf-8")

    fake_fetcher.revision = 2
    monkeypatch.setattr(
        "mshub.repository.remote_version",
        lambda *args, **kwargs: (f"{2:040x}", "2026-07-22T00:00:00Z"),
    )
    result = repository.update("owner/demo")
    assert result["updated"] is True
    assert "revision-2" in (skill_dir / "scripts" / "run.py").read_text(encoding="utf-8")
    backups = list((root / ".meta" / "backups" / "owner__demo").iterdir())
    assert len(backups) == 1
    assert "hand edit" in (backups[0] / "scripts" / "run.py").read_text(encoding="utf-8")


def test_delete_removes_projection_and_keeps_recovery_copy(config_store, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    repository = SkillRepository(config_store)
    repository.install("owner/demo")
    result = repository.delete("owner/demo")
    assert result["deleted"] is True
    assert Path(result["recovery_path"]).exists()
    assert repository.list() == []


def test_orphan_target_requires_confirmation_and_is_backed_up(config_store, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    repository = SkillRepository(config_store)
    root = Path(config_store.load().repo_root)
    orphan = root / "owner__demo"
    orphan.mkdir(parents=True)
    (orphan / "manual.txt").write_text("do not lose", encoding="utf-8")

    assert repository.preview("owner/demo")["exists"] is True
    with pytest.raises(ConflictError):
        repository.install("owner/demo")

    installed = repository.install("owner/demo", overwrite=True)
    assert installed["backup_path"]
    backup = Path(installed["backup_path"])
    assert (backup / "manual.txt").read_text(encoding="utf-8") == "do not lose"


def test_tags_are_normalized_indexed_and_preserved(config_store, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    repository = SkillRepository(config_store)

    installed = repository.install(
        "owner/demo",
        tags=["  自动化  ", "#Python", "python", "开发 工具"],
    )
    assert installed["tags"] == ["自动化", "Python", "开发 工具"]
    assert repository.list_tags() == {
        "items": [
            {"name": "Python", "count": 1},
            {"name": "开发 工具", "count": 1},
            {"name": "自动化", "count": 1},
        ],
        "untagged_count": 0,
    }

    changed = repository.set_tags("owner/demo", ["Agent", "效率"])
    assert changed["tags"] == ["Agent", "效率"]
    root = Path(config_store.load().repo_root)
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert index["skills"][0]["tags"] == ["Agent", "效率"]

    mode_changed = repository.change_mode("owner/demo", "full")
    assert mode_changed["tags"] == ["Agent", "效率"]

    fake_fetcher.revision = 2
    monkeypatch.setattr(
        "mshub.repository.remote_version",
        lambda *args, **kwargs: (f"{2:040x}", "2026-07-22T00:00:00Z"),
    )
    updated = repository.update("owner/demo")
    assert updated["skill"]["tags"] == ["Agent", "效率"]


def test_tag_validation_and_legacy_database_migration(config_store) -> None:
    root = Path(config_store.load().repo_root)
    meta = root / ".meta"
    meta.mkdir(parents=True)
    old_schema = SCHEMA.replace("    tags TEXT NOT NULL DEFAULT '[]',\n", "")
    with sqlite3.connect(meta / "skills.db") as connection:
        connection.executescript(old_schema)

    database = Database(root)
    with database.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(skills)").fetchall()
        }
    assert "tags" in columns

    with pytest.raises(ValidationError, match="最多"):
        normalize_tags([str(index) for index in range(13)])


def test_library_install_local_recovery_and_update_guard(
    config_store, fake_fetcher, monkeypatch, tmp_path
) -> None:
    import pytest

    from mshub.errors import ConflictError, ValidationError
    from mshub.manifest import write_manifest
    from mshub.repository import SkillRepository

    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    repo = SkillRepository(config_store)

    installed = repo.install("owner/demo", library="skills")
    # 身份与归属分离：名字 = 来源身份，与所在库无关
    assert installed["name"] == "owner/demo"
    assert installed["library"] == "skills"
    assert installed["local_dir"] == "skills/owner__demo"
    assert (tmp_path / "skills-repo" / "skills" / "owner__demo" / "SKILL.md").is_file()

    # 同一来源可再装进程序库：同名不同库的两条独立记录
    twin = repo.install("owner/demo", library="github")
    assert twin["name"] == "owner/demo"
    assert twin["library"] == "github"
    items = {(item["name"], item["library"]) for item in repo.list()}
    assert ("owner/demo", "skills") in items
    assert ("owner/demo", "github") in items
    # 不带库操作同名条目会被要求指定库
    with pytest.raises(ConflictError):
        repo.get("owner/demo")
    assert repo.get("owner/demo", "github")["local_dir"] == "github/owner__demo"

    # 历史分区不再接受新入库
    from mshub.errors import ValidationError as VE
    with pytest.raises(VE, match="历史分区"):
        repo.install("owner/demo", library="zcode-skills", overwrite=True)

    local_dir = tmp_path / "skills-repo" / "skills" / "my-skill"
    local_dir.mkdir(parents=True)
    (local_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: 自研技能。\n---\n\n本地维护。\n", encoding="utf-8"
    )
    write_manifest(
        local_dir, source_url="", commit_hash="", install_mode="full",
        source_type="local", library="skills",
    )

    result = repo.reconcile()
    assert result["recovered_count"] == 1
    item = repo.get("my-skill", "skills")
    assert item["provider"] == "local"
    assert item["library"] == "skills"
    assert item["local_dir"] == "skills/my-skill"

    with pytest.raises(ValidationError):
        repo.check_version("my-skill", "skills")
    with pytest.raises(ValidationError):
        repo.update("my-skill", "skills")

    index = (tmp_path / "skills-repo" / "index.json").read_text(encoding="utf-8")
    assert "my-skill" in index
    assert '"library": "skills"' in index


def test_library_name_migration_renames_identity_not_placement(
    config_store, fake_fetcher, monkeypatch, tmp_path
) -> None:
    """历史「库名/目录名」条目在启动自愈时迁移为身份名，目录不动、manifest 记录新名。"""
    import json

    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    repo = SkillRepository(config_store)
    repo.install("nolangz/pixel2motion", library="skills")

    # 模拟历史遗留：把目录和记录手工改成旧分区形态
    import shutil as _shutil
    root = Path(config_store.load().repo_root)
    from mshub.database import Database

    _shutil.move(str(root / "skills" / "nolangz__pixel2motion"), str(root / "zcode-skills" / "nolangz__pixel2motion"))
    with Database(root).connect() as connection:
        connection.execute(
            "UPDATE skills SET name = 'zcode-skills/nolangz__pixel2motion', "
            "library = 'zcode-skills', local_dir = 'zcode-skills/nolangz__pixel2motion' "
            "WHERE library = 'skills'"
        )

    status = repo.status()

    assert status["canonicalized_count"] == 1
    # 合并迁移把旧分区条目搬回共享技能库
    assert status["consolidated_moved"] == 1
    assert (root / "skills" / "nolangz__pixel2motion" / "SKILL.md").is_file()
    assert not (root / "zcode-skills").exists()
    item = repo.get("nolangz/pixel2motion", "skills")
    assert item["local_dir"] == "skills/nolangz__pixel2motion"
    manifest = json.loads(
        (root / "skills" / "nolangz__pixel2motion" / "_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "nolangz/pixel2motion"
    assert manifest["library"] == "skills"
    # 幂等：再跑不再计数
    again = repo.status()
    assert again["canonicalized_count"] == 0 and again["consolidated_moved"] == 0


def test_consolidate_dedupes_and_merges_legacy_partitions(
    config_store, fake_fetcher, monkeypatch, tmp_path
) -> None:
    """三个技能库合并为一个共享库：重名留一份（版本新内容全者胜），输家进回收站。"""
    import shutil

    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    repo = SkillRepository(config_store)
    root = Path(config_store.load().repo_root)
    from mshub.database import Database

    # 共享库里已有较新副本（commit=Y），旧分区里是落后副本
    repo.install("owner/demo", library="skills")
    fetcher_reborn = fake_fetcher
    fake_fetcher.revision = 1
    repo.install("owner/demo", library="zcode-skills", overwrite=True) if False else None

    # 手工制造旧分区副本：拷目录 + 造记录（无 commit、更早时间）
    shutil.copytree(root / "skills" / "owner__demo", root / "zcode-skills" / "owner__demo")
    shutil.copytree(root / "skills" / "owner__demo", root / "workbuddy-skills" / "solo-skill")
    with Database(root).connect() as connection:
        connection.executescript("""
            INSERT INTO skills (name, item_type, author, repo, provider, library, source_url,
                ref, subdir, local_dir, version, commit_hash, commit_date, description,
                description_zh, tags, has_scripts, security_status, security_route,
                security_findings, install_mode, fetcher, license_name, installed_at, updated_at)
            SELECT name, item_type, author, repo, provider, 'zcode-skills', source_url,
                ref, subdir, 'zcode-skills/owner__demo', version, '', commit_date, description,
                description_zh, tags, has_scripts, security_status, security_route,
                security_findings, install_mode, fetcher, license_name, installed_at,
                '2020-01-01T00:00:00+00:00'
            FROM skills WHERE library = 'skills';
            INSERT INTO skills (name, item_type, author, repo, provider, library, source_url,
                ref, subdir, local_dir, version, commit_hash, commit_date, description,
                description_zh, tags, has_scripts, security_status, security_route,
                security_findings, install_mode, fetcher, license_name, installed_at, updated_at)
            SELECT 'solo-skill', item_type, author, repo, provider, 'workbuddy-skills', source_url,
                ref, subdir, 'workbuddy-skills/solo-skill', version, commit_hash, commit_date, description,
                description_zh, tags, has_scripts, security_status, security_route,
                security_findings, install_mode, fetcher, license_name, installed_at, updated_at
            FROM skills WHERE library = 'skills';
        """)

    status = repo.status()

    assert status["consolidated_moved"] == 1  # solo-skill 搬入共享库
    assert status["consolidated_removed"] == 1  # owner/demo 落后副本删除
    assert not (root / "zcode-skills").exists()
    assert not (root / "workbuddy-skills").exists()
    items = {(item["name"], item["library"]) for item in repo.list()}
    assert ("owner/demo", "skills") in items
    assert ("solo-skill", "skills") in items
    assert ("owner/demo", "zcode-skills") not in items
    # 输家目录进了本机回收站，赢家目录在共享库
    trash = [p for p in (root / ".meta" / "trash").rglob("*") if p.name.endswith("owner__demo")]
    assert trash and (root / "skills" / "owner__demo" / "SKILL.md").is_file()
    # 幂等
    again = repo.status()
    assert again["consolidated_moved"] == 0 and again["consolidated_removed"] == 0
