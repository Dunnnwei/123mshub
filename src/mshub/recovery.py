from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .database import Database
from .errors import ValidationError
from .libraries import (
    AGENT_LIBRARIES,
    LEGACY_LIBRARIES,
    LIBRARY_DSH,
    LIBRARY_MERGE_PRIORITY,
    candidate_skill_dirs,
    is_library_name,
)
from .manifest import (
    LEGACY_MANIFEST_NAME,
    MANIFEST_NAME,
    MANIFEST_NAMES,
    patch_manifest,
    read_manifest,
    write_manifest,
)
from .parser import parse_skill
from .urltool import parse_source


def recover_synced_records(repo_root: Path, database: Database) -> int:
    """Restore missing database rows from synced manifests and index.json.

    支持两种布局：flat（根下平铺）与多库（库目录下一级子目录）。
    条目名 = 纯身份（作者/仓库[/子目录]，本地自研 = 目录名），与所在库无关；
    库归属由目录位置决定，同一技能多库分身 = 同名不同库的多条记录。
    """
    existing_dirs = {item["local_dir"] for item in database.list_skills()}
    index_items = _read_index(repo_root)
    recovered = 0

    for local_dir in candidate_skill_dirs(repo_root):
        if local_dir in existing_dirs:
            continue
        directory = repo_root / local_dir
        library = ""
        if "/" in local_dir:
            prefix = local_dir.split("/", 1)[0]
            if is_library_name(prefix):
                library = prefix

        has_manifest = any((directory / name).is_file() for name in MANIFEST_NAMES)
        manifest = read_manifest(directory) if has_manifest else {}
        projected = index_items.get(local_dir, {})

        # 空目录防护（2026-09-10 分机事故教训）：大文件尚未同步完成的空目录
        # 一律不识别、不写清单——那时写出的 files=[] 空清单会随同步回传污染
        # 全库，让每台机器都误报「本地变化」。等文件到了再自愈收录。
        if not has_manifest and not _directory_has_content(directory):
            continue

        source_type = str(
            manifest.get("source_type")
            or projected.get("provider")
            or "github"
        )
        # 身份名优先级：manifest（编辑/迁移时写入）> index 投影 > 从来源解析 > 目录名
        name = str(manifest.get("name") or projected.get("name") or "").strip()

        if source_type == "local":
            source = None
            if not name:
                name = directory.name
        else:
            source_url = str(
                manifest.get("source_url")
                or projected.get("source_url")
                or _source_from_legacy_directory(directory.name)
                or ""
            ).strip()
            source = None
            if source_url:
                try:
                    source = parse_source(source_url)
                except ValidationError:
                    source = None
            # 三个 agent 技能库内含 SKILL.md 的目录按本地技能收录
            # （总机经 inbox 收编、尚未生成 manifest 的新技能）；
            # github 库必须有 manifest/index 溯源，避免误收随手放入的目录。
            if source is None and library in AGENT_LIBRARIES \
                    and (directory / "SKILL.md").is_file():
                source_type = "local"
                if not name:
                    name = directory.name
            elif source is None:
                continue
            if source is not None and not name:
                name = source.name
            record_subdir = str(manifest.get("subdir") or projected.get("subdir") or "")
            if source is not None and record_subdir and f"/{record_subdir}" not in name:
                name = f"{name}/{record_subdir}"

        parsed = parse_skill(
            directory,
            str(manifest.get("commit_hash") or ""),
            str(manifest.get("generated_at") or ""),
        )
        scan = manifest.get("scan") if isinstance(manifest.get("scan"), dict) else {}
        timestamp = str(manifest.get("generated_at") or datetime.now(UTC).isoformat())
        item_type = str(
            manifest.get("item_type")
            or projected.get("item_type")
            or ("project" if (directory / ".git").exists() else "skill")
        )
        if source_type == "local":
            install_mode = str(manifest.get("install_mode") or "full")
            fetcher = "local"
        else:
            install_mode = str(
                manifest.get("install_mode")
                or projected.get("install_mode")
                or ("full" if not has_manifest else "standard")
            )
            fetcher = str(
                manifest.get("fetcher")
                or projected.get("fetcher")
                or ("git" if (directory / ".git").exists() else "archive")
            )
        record = {
            "name": name,
            "item_type": item_type,
            "author": source.owner if source else "local",
            "repo": source.repo if source else directory.name,
            "provider": source.provider if source else "local",
            "library": library,
            "source_url": source.source_url if source else "",
            "ref": str(manifest.get("ref") or (source.ref if source else "") or "HEAD"),
            "subdir": str(manifest.get("subdir") or projected.get("subdir") or ""),
            "local_dir": local_dir,
            "version": str(manifest.get("version") or projected.get("version") or parsed.version),
            "commit_hash": str(manifest.get("commit_hash") or ""),
            "commit_date": str(manifest.get("commit_date") or ""),
            "description": str(manifest.get("description") or projected.get("description") or parsed.description),
            "description_zh": str(
                manifest.get("description_zh")
                or projected.get("description_zh")
                or ""
            ),
            "tags": (
                manifest.get("tags")
                if isinstance(manifest.get("tags"), list)
                else projected.get("tags") if isinstance(projected.get("tags"), list) else []
            ),
            "has_scripts": bool(projected.get("has_scripts", parsed.has_scripts)),
            "security_status": str(scan.get("status") or projected.get("security_status") or "unchecked"),
            "security_route": str(scan.get("route") or ""),
            "security_findings": scan.get("findings") if isinstance(scan.get("findings"), list) else [],
            "install_mode": install_mode,
            "fetcher": fetcher,
            "license_name": parsed.license_name,
            "imported_from": str(manifest.get("imported_from") or projected.get("imported_from") or ""),
            "imported_at": str(manifest.get("imported_at") or projected.get("imported_at") or ""),
            "installed_at": timestamp,
            "updated_at": timestamp,
        }
        database.upsert_skill(record)
        if not has_manifest:
            managed_files = [
                path.relative_to(directory).as_posix()
                for path in directory.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(directory).parts
            ]
            write_manifest(
                directory,
                source_url=record["source_url"],
                commit_hash=record["commit_hash"],
                install_mode=record["install_mode"],
                item_type=record["item_type"],
                ref=record["ref"],
                subdir=record["subdir"],
                fetcher=record["fetcher"],
                commit_date=record["commit_date"],
                description=record["description"],
                version=record["version"],
                name=record["name"],
                tags=record["tags"],
                managed_files=managed_files,
                source_type=source_type,
                library=library,
                imported_from=record["imported_from"],
                imported_at=record["imported_at"],
            )
        existing_dirs.add(local_dir)
        recovered += 1
    return recovered


def _directory_has_content(directory: Path) -> bool:
    """除清单文件外目录里是否还有任何真实文件（判断同步是否已送达内容）。"""
    from .syncsafe import is_derived_local, is_transport_artifact

    for path in directory.rglob("*"):
        if not path.is_file() or path.name in MANIFEST_NAMES:
            continue
        relative = path.relative_to(directory).as_posix()
        if is_derived_local(relative) or is_transport_artifact(relative):
            continue
        return True
    return False


def _source_from_legacy_directory(name: str) -> str:
    if "__" not in name:
        return ""
    owner, repo = name.split("__", 1)
    try:
        return parse_source(f"{owner}/{repo}").source_url
    except ValidationError:
        return ""


# manifest → SQLite 回填白名单：这些字段的跨机真相在 manifest 里。
# name 也在其中——改名经 manifest 跨机传播。
BACKFILL_FIELDS = (
    "name", "description", "description_zh", "version", "commit_hash", "commit_date",
    "install_mode", "fetcher", "item_type", "source_url", "source_type", "subdir", "ref",
    "tags",
)


def backfill_from_manifests(repo_root: Path, database: Database) -> int:
    """把别的机器写入 manifest 的较新元数据回填进本机 SQLite。

    判定：manifest.generated_at 晚于 SQLite.updated_at 才动手（本机刚写完的记录
    两者相等，天然免疫自我回填）。内容一致只对齐时间戳，保证幂等。
    方向：最后写 manifest 的机器赢（单用户多机，不做字段级合并）。
    """
    updated = 0
    for item in database.list_skills():
        manifest = read_manifest(repo_root / item["local_dir"])
        generated_at = str(manifest.get("generated_at") or "")
        if not generated_at or generated_at <= str(item.get("updated_at") or ""):
            continue
        updates: dict[str, Any] = {}
        for key in BACKFILL_FIELDS:
            value = manifest.get(key, None)
            if value is None or value == item.get(key):
                continue
            if key == "name":
                # 重名回填仅在同库不冲突时生效，避免撞复合键
                clash = database.get_skill(str(value), item.get("library") or None)
                if clash and clash["local_dir"] != item["local_dir"]:
                    continue
            updates[key] = value
        scan = manifest.get("scan") if isinstance(manifest.get("scan"), dict) else None
        if scan:
            updates["security_status"] = str(scan.get("status") or item.get("security_status") or "unchecked")
            updates["security_route"] = str(scan.get("route") or "")
            findings = scan.get("findings")
            updates["security_findings"] = findings if isinstance(findings, list) else []
        if "source_type" in updates or "source_url" in updates:
            _apply_source_backfill(manifest, item, updates)
        if not updates:
            database.update_fields(item["name"], {"updated_at": generated_at}, library=item.get("library"))
            continue
        updates["updated_at"] = generated_at
        database.update_fields(item["name"], updates, library=item.get("library"))
        if "name" in updates:
            item["name"] = updates["name"]
        updated += 1
    return updated


# 旧命名迁移：旧版把库名（或 local/）揉进条目名，v0.6 起条目名 = 纯身份：
# GitHub = 作者/仓库[/子目录]，本地自研 = 技能名（目录名，无前缀）。
LEGACY_NAME_PREFIX = re.compile(r"^(skills|zcode-skills|workbuddy-skills|local)/")


def canonicalize_library_names(repo_root: Path, database: Database) -> int:
    """把历史遗留的旧命名条目迁移为身份名。

    身份从 manifest（跨机事实源）优先推导：manifest 有来源地址 → 作者/仓库[/子目录]；
    否则才退回本机 DB 字段——避免另一台机器数据未收敛时把 github 技能误判成本地名、
    再经同步把错名传回来。本地自研 = 目录名，不加任何前缀（用户裁决：客户端里
    能看到的本来就是本地仓库，local/ 前缀是噪音）。同库重名冲突时保留旧名。
    """
    items = database.list_skills()
    taken = {(item["name"], item.get("library") or "") for item in items}
    renamed = 0
    for item in items:
        old_name = item["name"]
        if not LEGACY_NAME_PREFIX.match(old_name):
            continue
        manifest = read_manifest(repo_root / item["local_dir"])
        dir_name = PurePosixPath(item["local_dir"]).name

        new_name = ""
        manifest_name = str(manifest.get("name") or "").strip()
        source_url = str(manifest.get("source_url") or item.get("source_url") or "").strip()
        source = None
        if source_url:
            try:
                source = parse_source(source_url)
            except ValidationError:
                source = None
        if source is not None:
            record_subdir = str(manifest.get("subdir") or item.get("subdir") or "")
            new_name = source.name
            if record_subdir and f"/{record_subdir}" not in new_name:
                new_name = f"{new_name}/{record_subdir}"
        elif manifest_name and not LEGACY_NAME_PREFIX.match(manifest_name):
            new_name = manifest_name
        elif item.get("provider") == "github" and item.get("author") and item.get("repo"):
            new_name = f"{item['author']}/{item['repo']}"
            if item.get("subdir"):
                new_name = f"{new_name}/{item['subdir']}"
        else:
            new_name = dir_name

        if not new_name or new_name == old_name:
            continue
        if (new_name, item.get("library") or "") in taken:
            continue
        database.update_fields(old_name, {"name": new_name}, library=item.get("library"))
        taken.discard((old_name, item.get("library") or ""))
        taken.add((new_name, item.get("library") or ""))
        skill_dir = repo_root / item["local_dir"]
        if skill_dir.exists():
            patch_manifest(skill_dir, {"name": new_name})
        renamed += 1
    return renamed


def migrate_manifest_names(repo_root: Path) -> dict[str, Any]:
    """一次性迁移：库内所有旧名 .manifest.json 原子改名为 _manifest.json。

    背景：部分文件同步程序按「排除前缀带 . 的隐藏文件」过滤，点开头清单在同步端
    一份都收不到；该排除规则本身不能关（.meta 的 SQLite 严禁进同步盘）。
    改名走 os.replace 原子替换，内容（含 sha256 与安全扫描结论）字节不变，
    SQLite 与 index.json 均不受影响。幂等：重复执行时旧名不存在即空操作。
    """
    migrated = 0
    kept = 0
    resolved = 0
    errors: list[str] = []
    for local_dir in candidate_skill_dirs(repo_root):
        directory = repo_root / local_dir
        legacy = directory / LEGACY_MANIFEST_NAME
        target = directory / MANIFEST_NAME
        try:
            if not legacy.is_file():
                if target.is_file():
                    kept += 1
                continue
            if target.is_file():
                # 双名并存（正常流程不会出现，防御处理）：按 generated_at 留新者。
                newer = str(read_manifest(directory).get("generated_at") or "")
                legacy_newer = str(
                    json.loads(legacy.read_text(encoding="utf-8", errors="replace"))
                    .get("generated_at") or ""
                )
                if legacy_newer > newer:
                    os.replace(legacy, target)
                    resolved += 1
                else:
                    legacy.unlink()
                    resolved += 1
            else:
                os.replace(legacy, target)
                migrated += 1
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{local_dir}: {exc}")
    return {
        "migrated": migrated,
        "resolved_conflicts": resolved,
        "already_current": kept,
        "errors": errors,
    }


def _apply_source_backfill(
    manifest: dict[str, Any], item: dict[str, Any], updates: dict[str, Any]
) -> None:
    source_type = str(manifest.get("source_type") or item.get("provider") or "github")
    if source_type == "local":
        updates["provider"] = "local"
        updates["author"] = "local"
        updates["source_url"] = ""
        return
    source_url = str(manifest.get("source_url") or "")
    if not source_url:
        return
    try:
        source = parse_source(source_url)
    except ValidationError:
        return
    updates.update({
        "provider": "github",
        "author": source.owner,
        "repo": source.repo,
        "source_url": source.source_url,
        "subdir": source.subdir,
    })


def _read_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    path = repo_root / "index.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    items = data.get("skills") if isinstance(data, dict) else []
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("dir")): item
        for item in items
        if isinstance(item, dict) and item.get("dir")
    }


def _merge_score(item: dict[str, Any], file_count: int) -> tuple:
    """重名副本取舍（越大越好）：GitHub 来源 > 本地；有 commit > 无；更新时间新；文件多；已在共享库优先。"""
    return (
        0 if item.get("provider") == "local" else 1,
        1 if item.get("commit_hash") else 0,
        str(item.get("updated_at") or ""),
        file_count,
        -LIBRARY_MERGE_PRIORITY.get(item.get("library") or "", 9),
    )


def _file_count(directory: Path) -> int:
    if not directory.is_dir():
        return -1
    return sum(1 for p in directory.rglob("*") if p.is_file() and p.name not in MANIFEST_NAMES)


def consolidate_libraries(repo_root: Path, database: Database) -> dict[str, Any]:
    """把 zcode-skills / workbuddy-skills 历史分区合并进共享技能库 skills。

    用户裁决（2026-09-11）：平台不分仓库——一个共享技能库，所有平台的技能目录
    junction 指向它。重名副本按"版本新、内容全"留一份，其余目录移入 .meta/trash
    （同步侧即删除，本机保留恢复能力）。幂等：旧分区不存在时为空操作。
    """
    skill_libs = (LIBRARY_DSH, *LEGACY_LIBRARIES)
    legacy_present = [
        lib for lib in LEGACY_LIBRARIES
        if (repo_root / lib).is_dir() and any((repo_root / lib).iterdir())
    ]
    items = [item for item in database.list_skills() if item.get("library") in skill_libs]
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(item["name"], []).append(item)

    trash_root = repo_root / ".meta" / "trash" / (
        "consolidated-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )
    used_dirs = {
        PurePosixPath(item["local_dir"]).name
        for item in database.list_skills()
        if (item.get("library") or "") not in skill_libs
    }
    for item in items:
        if item.get("library") != LIBRARY_DSH:
            continue
        used_dirs.add(PurePosixPath(item["local_dir"]).name)

    moved = 0
    removed = 0
    report: list[str] = []

    def discard(item: dict[str, Any], reason: str) -> None:
        nonlocal removed
        source_dir = repo_root / item["local_dir"]
        if source_dir.is_dir():
            destination = trash_root / f"{item['library']}__{PurePosixPath(item['local_dir']).name}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_dir), str(destination))
        database.delete_skill(item["name"], item.get("library"))
        removed += 1
        report.append(f"删除副本 {item['name']}（{item['library']}）：{reason}")

    def relocate(item: dict[str, Any]) -> None:
        nonlocal moved
        source_dir = repo_root / item["local_dir"]
        dir_name = PurePosixPath(item["local_dir"]).name
        if dir_name in used_dirs:
            dir_name = f"{dir_name}__{item['library']}"
            report.append(f"目录重名避让：{item['name']} 目录改为 {dir_name}")
        target = repo_root / LIBRARY_DSH / dir_name
        if source_dir.is_dir():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                report.append(f"跳过 {item['name']}：目标目录已存在 {target.name}")
                return
            shutil.move(str(source_dir), str(target))
        new_local_dir = f"{LIBRARY_DSH}/{dir_name}"
        database.update_fields(
            item["name"], {"library": LIBRARY_DSH, "local_dir": new_local_dir},
            library=item.get("library"),
        )
        if target.is_dir():
            patch_manifest(target, {"library": LIBRARY_DSH, "name": item["name"]})
        used_dirs.add(dir_name)
        moved += 1

    for name, group in sorted(groups.items()):
        if len(group) == 1:
            item = group[0]
            if item.get("library") != LIBRARY_DSH:
                relocate(item)
            continue
        ranked = sorted(
            group,
            key=lambda item: _merge_score(item, _file_count(repo_root / item["local_dir"])),
            reverse=True,
        )
        winner, losers = ranked[0], ranked[1:]
        for loser in losers:
            discard(loser, "重名副本（按版本新/内容全落选）")
        if winner.get("library") != LIBRARY_DSH:
            relocate(winner)

    removed_libraries = []
    for lib in LEGACY_LIBRARIES:
        directory = repo_root / lib
        if directory.is_dir():
            try:
                directory.rmdir()
                removed_libraries.append(lib)
            except OSError:
                report.append(f"旧分区 {lib} 非空，保留待查")

    return {
        "moved": moved,
        "removed_duplicates": removed,
        "removed_libraries": removed_libraries,
        "report": report,
    }
