"""清单命名改造（v0.8.1）：.manifest.json → _manifest.json。

飞牛同步按「排除前缀带 . 的隐藏文件」过滤，点开头清单 NAS 一份都收不到；
改名后新写入一律用 _manifest.json，读取回退兼容旧名，迁移动作批量改名
且内容字节不变。
"""
import json
from pathlib import Path

from mshub.config import ConfigStore
from mshub.manifest import (
    LEGACY_MANIFEST_NAME,
    MANIFEST_NAME,
    detect_local_changes,
    patch_manifest,
    read_manifest,
    sha256_file,
    write_manifest,
)
from mshub.repository import SkillRepository


def _make_skill(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text("---\nname: demo\n---\n正文。", encoding="utf-8")
    return path


def test_write_uses_underscore_name_and_removes_legacy(tmp_path: Path) -> None:
    skill = _make_skill(tmp_path / "demo")
    legacy = skill / LEGACY_MANIFEST_NAME
    legacy.write_text('{"schema_version": 1, "files": []}', encoding="utf-8")

    write_manifest(
        skill,
        source_url="https://github.com/owner/demo",
        commit_hash="a" * 40,
        install_mode="standard",
    )

    assert (skill / MANIFEST_NAME).is_file()
    assert not legacy.exists()
    # 旧名清单文件自身不得混进 files 哈希清单
    manifest = read_manifest(skill)
    assert all(item["path"] != LEGACY_MANIFEST_NAME for item in manifest["files"])


def test_read_falls_back_to_legacy_name(tmp_path: Path) -> None:
    skill = _make_skill(tmp_path / "demo")
    legacy = skill / LEGACY_MANIFEST_NAME
    payload = {"schema_version": 2, "name": "owner/demo", "files": []}
    legacy.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert read_manifest(skill)["name"] == "owner/demo"

    # 新名一旦出现即压过旧名
    (skill / MANIFEST_NAME).write_text(
        json.dumps({**payload, "name": "winner"}, ensure_ascii=False), encoding="utf-8"
    )
    assert read_manifest(skill)["name"] == "winner"


def test_patch_on_legacy_only_dir_converts_name(tmp_path: Path) -> None:
    skill = _make_skill(tmp_path / "demo")
    (skill / LEGACY_MANIFEST_NAME).write_text(
        json.dumps({"schema_version": 2, "name": "old-name", "files": []}), encoding="utf-8"
    )

    patch_manifest(skill, {"name": "new-name"})

    assert not (skill / LEGACY_MANIFEST_NAME).exists()
    manifest = json.loads((skill / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["name"] == "new-name"


def test_local_change_detection_ignores_both_manifest_names(tmp_path: Path) -> None:
    skill = _make_skill(tmp_path / "demo")
    (skill / LEGACY_MANIFEST_NAME).write_text("{}", encoding="utf-8")

    write_manifest(
        skill,
        source_url="",
        commit_hash="",
        install_mode="full",
        managed_files=["SKILL.md"],
    )

    # 新旧名并存时都算程序内部文件，不得报成 untracked
    (skill / LEGACY_MANIFEST_NAME).write_text("{}", encoding="utf-8")
    changes = detect_local_changes(skill)
    assert changes == {"modified": [], "missing": [], "untracked": []}


def test_migrate_renames_in_place_content_unchanged(config_store: ConfigStore) -> None:
    root = Path(config_store.load().repo_root)
    library = root / "skills"
    originals: dict[str, str] = {}
    for name in ("alpha", "beta"):
        skill = _make_skill(library / name)
        write_manifest(
            skill,
            source_url=f"https://github.com/owner/{name}",
            commit_hash="b" * 40,
            install_mode="standard",
        )
        # 手工降级成旧命名，模拟存量库
        (skill / MANIFEST_NAME).rename(skill / LEGACY_MANIFEST_NAME)
        originals[name] = sha256_file(skill / LEGACY_MANIFEST_NAME)

    result = SkillRepository(config_store).migrate_manifests()

    assert result["migrated"] == 2
    assert result["errors"] == []
    for name, digest in originals.items():
        skill = library / name
        assert not (skill / LEGACY_MANIFEST_NAME).exists()
        assert (skill / MANIFEST_NAME).is_file()
        # 内容（sha256、安全扫描结论随整份文件）字节不变
        assert sha256_file(skill / MANIFEST_NAME) == digest


def test_migrate_is_idempotent_and_counts_current(config_store: ConfigStore) -> None:
    root = Path(config_store.load().repo_root)
    _make_skill(root / "skills" / "alpha")

    repository = SkillRepository(config_store)
    first = repository.migrate_manifests()
    second = repository.migrate_manifests()

    # 没有任何 manifest 的目录两轮都不计数；第二轮仍是空操作不报错
    assert first == second
    assert first["migrated"] == 0 and first["already_current"] == 0


def test_status_self_heal_migrates_legacy_manifests(config_store: ConfigStore) -> None:
    root = Path(config_store.load().repo_root)
    skill = _make_skill(root / "skills" / "alpha")
    write_manifest(
        skill,
        source_url="https://github.com/owner/alpha",
        commit_hash="c" * 40,
        install_mode="standard",
        library="skills",
    )
    (skill / MANIFEST_NAME).rename(skill / LEGACY_MANIFEST_NAME)

    status = SkillRepository(config_store).status()

    assert status["migrated_manifests"] == 1
    assert (skill / MANIFEST_NAME).is_file()
    assert not (skill / LEGACY_MANIFEST_NAME).exists()


def test_migrate_keeps_newer_when_both_names_exist(config_store: ConfigStore) -> None:
    root = Path(config_store.load().repo_root)
    skill = _make_skill(root / "skills" / "alpha")
    (skill / MANIFEST_NAME).write_text(
        json.dumps({"generated_at": "2026-01-01T00:00:00+00:00", "name": "old"}),
        encoding="utf-8",
    )
    (skill / LEGACY_MANIFEST_NAME).write_text(
        json.dumps({"generated_at": "2026-02-01T00:00:00+00:00", "name": "new"}),
        encoding="utf-8",
    )

    SkillRepository(config_store).migrate_manifests()

    assert not (skill / LEGACY_MANIFEST_NAME).exists()
    assert read_manifest(skill)["name"] == "new"
