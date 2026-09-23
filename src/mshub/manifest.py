from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

# 清单文件名用下划线开头（与库内 _skillhub_meta.json 命名风格一致）：
# 点开头可能被文件同步程序按隐藏文件排除，导致同步端收不到 manifest
# （v0.8.1 改名；旧点开头名仅作读取回退，不再新写）。
MANIFEST_NAME = "_manifest.json"
LEGACY_MANIFEST_NAME = ".manifest.json"
MANIFEST_NAMES = frozenset({MANIFEST_NAME, LEGACY_MANIFEST_NAME})


def sha256_file(path: Path) -> str:
    from .fsretry import retry_on_denied

    def _hash() -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    return retry_on_denied(_hash, f"读取 {path}")


def write_manifest(
    skill_dir: Path,
    *,
    source_url: str,
    commit_hash: str,
    install_mode: str,
    item_type: str = "skill",
    ref: str = "HEAD",
    subdir: str = "",
    fetcher: str = "archive",
    commit_date: str = "",
    description: str = "",
    description_zh: str = "",
    version: str = "",
    name: str = "",
    tags: Iterable[str] | None = None,
    managed_files: Iterable[str] | None = None,
    scan: dict[str, Any] | None = None,
    source_type: str = "github",
    library: str = "",
    imported_from: str = "",
    imported_at: str = "",
) -> dict[str, Any]:
    from .syncsafe import is_derived_local, is_transport_artifact, to_transport

    # 清单记录「运输视图」：点文件以 _dot_/ 容器路径入册（同步盘里的真相），
    # 本机物化出来的真实点文件与 git.bundle 运输件不入册。
    selected = {to_transport(item) for item in (managed_files or [])}
    files = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name in MANIFEST_NAMES:
            continue
        relative = path.relative_to(skill_dir).as_posix()
        if is_derived_local(relative) or is_transport_artifact(relative):
            continue
        transport = to_transport(relative)
        if selected and transport not in selected:
            continue
        files.append({"path": transport, "sha256": sha256_file(path), "size": path.stat().st_size})

    manifest = {
        "schema_version": 2,
        "name": name,
        "source_type": source_type,
        "library": library,
        "imported_from": imported_from,
        "imported_at": imported_at,
        "source_url": source_url,
        "commit_hash": commit_hash,
        "commit_date": commit_date,
        "install_mode": install_mode,
        "item_type": item_type,
        "ref": ref,
        "subdir": subdir,
        "fetcher": fetcher,
        "description": description,
        "description_zh": description_zh,
        "version": version,
        "tags": list(tags or []),
        "generated_at": datetime.now(UTC).isoformat(),
        "files": files,
        "scan": scan or None,
    }
    target = skill_dir / MANIFEST_NAME
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from .fsretry import robust_replace
    robust_replace(temp, target)
    _remove_legacy(skill_dir)
    return manifest


def read_manifest(skill_dir: Path) -> dict[str, Any]:
    # 优先新名；旧点开头名仍可读（存量技能升级过渡期不失效）。
    for name in (MANIFEST_NAME, LEGACY_MANIFEST_NAME):
        path = skill_dir / name
        if not path.exists():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {"schema_version": 1, "files": []}
    return {"schema_version": 1, "files": []}


PATCHABLE_FIELDS = (
    "name", "source_type", "source_url", "author", "repo", "subdir", "ref", "fetcher",
    "description", "description_zh", "version", "commit_hash", "commit_date",
    "item_type", "install_mode", "library", "tags",
    "imported_from", "imported_at",
)


def patch_manifest(skill_dir: Path, updates: dict[str, Any]) -> dict[str, Any]:
    """只改元数据字段，保留 files 哈希清单原样——编辑信息/补翻译用，不触碰文件。

    generated_at 必须随补丁刷新：它是跨机回填判定新旧的唯一依据，
    漏刷会导致"本机编辑过、对端永远不回填"。
    """
    manifest = read_manifest(skill_dir)
    clean = {key: value for key, value in updates.items() if key in PATCHABLE_FIELDS}
    if not clean:
        return manifest
    manifest.update(clean)
    manifest["generated_at"] = datetime.now(UTC).isoformat()
    target = skill_dir / MANIFEST_NAME
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from .fsretry import robust_replace
    robust_replace(temp, target)
    _remove_legacy(skill_dir)
    return manifest


def _remove_legacy(skill_dir: Path) -> None:
    """落盘新名后清掉旧点开头清单，避免双名并存造成两个事实源。"""
    legacy = skill_dir / LEGACY_MANIFEST_NAME
    try:
        legacy.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # 只读属性等极端情况：不阻塞主流程，迁移动作会再兜底处理。
        pass


def detect_local_changes(skill_dir: Path) -> dict[str, list[str]]:
    from .syncsafe import is_derived_local, is_transport_artifact, to_local

    manifest = read_manifest(skill_dir)
    expected = {item["path"]: item["sha256"] for item in manifest.get("files", [])}
    modified: list[str] = []
    missing: list[str] = []
    for relative, digest in expected.items():
        path = skill_dir / Path(relative)
        if not path.exists():
            # 旧版清单可能记的是真实点文件路径（无容器时代的遗产）
            path = skill_dir / Path(to_local(relative))
        if not path.exists():
            missing.append(relative)
        elif sha256_file(path) != digest:
            modified.append(relative)

    current = {
        path.relative_to(skill_dir).as_posix()
        for path in skill_dir.rglob("*")
        if path.is_file()
        and path.name not in MANIFEST_NAMES
        and not is_derived_local(path.relative_to(skill_dir).as_posix())
        and not is_transport_artifact(path.relative_to(skill_dir).as_posix())
    }
    untracked = sorted(current - set(expected))
    return {"modified": sorted(modified), "missing": sorted(missing), "untracked": untracked}


def refresh_scan_snapshot(skill_dir: Path, report: dict[str, Any]) -> None:
    manifest = read_manifest(skill_dir)
    write_manifest(
        skill_dir,
        source_url=manifest.get("source_url", ""),
        commit_hash=manifest.get("commit_hash", ""),
        install_mode=manifest.get("install_mode", "standard"),
        item_type=manifest.get("item_type", "skill"),
        ref=manifest.get("ref", "HEAD"),
        subdir=manifest.get("subdir", ""),
        fetcher=manifest.get("fetcher", "archive"),
        commit_date=manifest.get("commit_date", ""),
        description=manifest.get("description", ""),
        description_zh=manifest.get("description_zh", ""),
        version=manifest.get("version", ""),
        name=manifest.get("name", ""),
        tags=manifest.get("tags", []),
        managed_files=[item["path"] for item in manifest.get("files", [])],
        scan=report,
        source_type=manifest.get("source_type", "github"),
        library=manifest.get("library", ""),
    )
