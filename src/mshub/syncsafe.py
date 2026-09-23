"""同步盘运输安全层（v0.9.0）。

共享技能库经同步盘跨机器复制，同步侧有两条硬规则：
1. 内建不可关的「点开头隐藏文件」规则：任何点开头的文件/目录都不进同步盘；
2. 用户可配的扩展名排除名单（har/lnk/meta/pst/swp）。

本模块让程序在**不依赖任何用户配置**的前提下保证：同步树里只出现普通名字的
功能文件，机器私有状态（.meta）与点开头文件各安其位：

- 瞬时锁重试：杀毒实时扫描新建文件时会短暂独占句柄，一次相撞就足以打断
  整个安装（2026-09-20 实测 [Errno 13]），所有落盘动作经 robust_* 退避重试；
- 点文件容器：技能内点开头文件收进 `_dot_/` 普通名字目录随库同步，每台机
  自愈时物化还原成真实点文件（本机私有，同步盘看不见）；
- git bundle：项目 `.git` 打成随库同步的 `git.bundle` 单文件，分机自愈时
  还原 `.git`，令跨机的项目溯源与 git 通道更新无损；
- 库根维护 `_共享技能库使用说明.md`：给未接入的 agent 指路（相对表述，
  任意机器任意挂载路径都成立，内容确定故无同步冲突）；
- 冲突副本隔离、过期暂存清理、空清单修复：把同步环境的碎片问题在软件内部
  消化掉，用户零配置。
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

from .fsretry import (  # noqa: F401  （重导出：repository 从 syncsafe 统一取用）
    RETRY_DELAYS,
    robust_copy2,
    robust_rename,
    robust_replace,
    robust_unlink,
    robust_rmtree,
)
from .libraries import candidate_skill_dirs
from .manifest import MANIFEST_NAMES, read_manifest, write_manifest
from .process import hidden_windows_kwargs

# 技能目录内的点文件容器目录名（普通名字，随同步走）。
DOT_CONTAINER = "_dot_"
# 点开头路径段的运输标记前缀：`.github` → `_dot_/dot.github`（不与普通文件冲突：
# 真实的 dot.xxx 文件不含点开头段，不进容器，两者永不见面）。
DOT_MARKER = "dot."
# 项目目录内随库同步的 git 捆绑文件名（普通名字单文件）。
BUNDLE_NAME = "git.bundle"
# 库根给 agent 的说明文件名。
GUIDE_NAME = "_共享技能库使用说明.md"
GUIDE_VERSION = "v2"
# 同步客户端的冲突副本命名标记（例如「xxx (机器名 的冲突副本 …)」）。
CONFLICT_MARK = "冲突副本"


# ------------------------------------------------- 运输路径 <-> 本机真实路径


def is_derived_local(relative: str) -> bool:
    """本机派生文件：任一路径段点开头（.git、物化出来的 .gitignore 等）。

    这些文件不进清单、不参与本地变化检测——它们由容器物化产生，
    同步盘也运不走它们，管理真相在 `_dot_/` 容器里。
    """
    return any(part.startswith(".") for part in PurePosixPath(relative).parts)


def is_container_path(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return bool(parts) and parts[0] == DOT_CONTAINER


def to_transport(relative: str) -> str:
    """本机真实路径 → 同步树运输路径：点开头路径段改写为 `dot.` 前缀并收进容器。

    `.gitignore` → `_dot_/dot.gitignore`；`.claude/settings.json` →
    `_dot_/dot.claude/settings.json`；`.config/.hidden` → `_dot_/dot.config/dot.hidden`。
    逐段标记保证往返无损；普通文件原样返回。
    """
    parts = PurePosixPath(relative).parts
    if not any(part.startswith(".") for part in parts):
        return relative
    mapped = tuple(
        (DOT_MARKER + part.lstrip(".")) if part.startswith(".") else part
        for part in parts
    )
    return PurePosixPath(DOT_CONTAINER, *mapped).as_posix()


def to_local(relative: str) -> str:
    """运输路径 → 本机真实路径：容器内 `dot.` 前缀还原成点开头，其余原样。"""
    if not is_container_path(relative):
        return relative
    rest = PurePosixPath(relative).parts[1:]
    dotted = tuple(
        ("." + part[len(DOT_MARKER):]) if part.startswith(DOT_MARKER) else part
        for part in rest
    )
    return PurePosixPath(*dotted).as_posix()


def is_transport_artifact(relative: str) -> bool:
    """随目录同步的运输件（git.bundle）：是内容的一部分，但不入清单。"""
    return relative == BUNDLE_NAME


# ------------------------------------------------------------ 点文件容器


def _iter_files(directory: Path):
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            yield path


def stage_dotfiles(directory: Path) -> int:
    """安装落盘时把点文件收进容器（真实文件挪走，仅保留容器副本）。

    `.git` 不收——项目模式靠它 + git.bundle 机制处理。
    返回收进容器的文件数。
    """
    moved = 0
    for path in _iter_files(directory):
        relative = path.relative_to(directory).as_posix()
        if ".git" in PurePosixPath(relative).parts or not is_derived_local(relative):
            continue
        destination = directory / Path(to_transport(relative))
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            # 同名非点文件孪生（理论边缘）：加后缀避免互相覆盖
            if destination.read_bytes() != path.read_bytes():
                destination = destination.with_name(destination.name + ".dotfile")
                destination.parent.mkdir(parents=True, exist_ok=True)
            else:
                robust_unlink(path)
                moved += 1
                continue
        robust_replace(path, destination)
        moved += 1
    _prune_empty_dot_dirs(directory)
    return moved


def _prune_empty_dot_dirs(directory: Path) -> None:
    for path in sorted(
        (p for p in directory.rglob("*") if p.is_dir() and p.name.startswith(".")),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        try:
            path.rmdir()
        except OSError:
            pass


def sync_dotfiles(directory: Path) -> int:
    """自愈：容器 ↔ 真实点文件双向收敛，返回发生变动的文件数。

    规则（确定性收敛，容器是跨机事实源）：
    - 真实点文件存在而容器没有 → 收编进容器（老版本装的技能由此开始可运输）；
    - 容器有而真实缺失或内容不同 → 物化/覆盖真实文件（远端更新到达即生效）。
    """
    changed = 0
    container_root = directory / DOT_CONTAINER
    # 1) 收编：真实 → 容器（仅当容器侧没有对应文件）
    for path in _iter_files(directory):
        relative = path.relative_to(directory).as_posix()
        if ".git" in PurePosixPath(relative).parts or not is_derived_local(relative):
            continue
        destination = directory / Path(to_transport(relative))
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        robust_copy2(path, destination)
        changed += 1
    # 2) 物化：容器 → 真实
    if container_root.is_dir():
        for path in _iter_files(container_root):
            relative = path.relative_to(directory).as_posix()
            destination = directory / Path(to_local(relative))
            if destination.exists() and destination.read_bytes() == path.read_bytes():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            robust_copy2(path, destination)
            changed += 1
    return changed


# --------------------------------------------------------------- git bundle


def _git_available() -> bool:
    return shutil.which("git") is not None


def refresh_git_bundle(directory: Path) -> bool:
    """目录里有 `.git` 就刷新随库同步的 `git.bundle`（原子落盘）。"""
    if not (directory / ".git").is_dir() or not _git_available():
        return False
    bundle = directory / BUNDLE_NAME
    temp = directory / ".git.bundle.tmp"
    robust_unlink(temp)
    result = subprocess.run(
        ["git", "-C", str(directory), "bundle", "create", str(temp), "--all"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        **hidden_windows_kwargs(),
    )
    if result.returncode != 0 or not temp.is_file():
        robust_unlink(temp)
        return False
    robust_replace(temp, bundle)
    return True


def restore_git_from_bundle(directory: Path) -> bool:
    """分机自愈：有 bundle、没 `.git` 时从 bundle 还原 `.git`。"""
    bundle = directory / BUNDLE_NAME
    if not bundle.is_file() or (directory / ".git").exists() or not _git_available():
        return False
    temp_root = Path(tempfile.mkdtemp(prefix="mshub-bundle-"))
    try:
        clone = temp_root / "clone"
        result = subprocess.run(
            ["git", "clone", "--quiet", str(bundle), str(clone)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
            **hidden_windows_kwargs(),
        )
        if result.returncode != 0 or not (clone / ".git").is_dir():
            return False
        shutil.move(str(clone / ".git"), str(directory / ".git"))
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    # bundle 克隆出来的 origin 指向 bundle 文件本身，改回真实来源（尽力而为）
    source_url = str(read_manifest(directory).get("source_url") or "")
    if source_url:
        subprocess.run(
            ["git", "-C", str(directory), "remote", "set-url", "origin", source_url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
            **hidden_windows_kwargs(),
        )
    return True


# ----------------------------------------------------------------- 说明文件

_GUIDE_BODY = f"""<!-- 123mshub shared-library guide {GUIDE_VERSION} -->
# 共享技能库使用说明

本文件所在目录就是「共享技能库」的根目录，由 123 MSHub 程序管理，经同步盘在多台机器间共享。

## 查询技能清单

- 技能清单文件：本目录下的 `index.json`——库内全部条目的全量投影（名称 `name`、目录 `dir`、来源、描述、标签）。
- 技能文件位于 `skills/<目录名>/`；应用程序项目位于 `github/<目录名>/`。

## 使用规则

1. 先读 `index.json`，按名称、描述或标签找到合适的条目，记下它的 `dir` 字段。
2. 进入该目录阅读 `SKILL.md`（技能文档），掌握用法与用途后再使用；应用程序项目请先读其 README。
3. 技能与项目文件由 123 MSHub 统一管理（安装、更新、备份），请勿手工增删改；需要更新或移除时请用该程序操作。
4. 目录内的 `{DOT_CONTAINER}/` 文件夹与 `{BUNDLE_NAME}` 文件是跨机器运输容器，请勿删除或改名。
5. 清单里查不到条目或对内容有疑问时，请让库管理员用 123 MSHub 检查。
"""


def ensure_library_guide(repo_root: Path) -> bool:
    """库根维护说明文件；缺失或版本变化时重写。返回是否发生写入。"""
    path = repo_root / GUIDE_NAME
    if path.is_file():
        try:
            if f"guide {GUIDE_VERSION}" in path.read_text(encoding="utf-8"):
                return False
        except OSError:
            pass
    temp = repo_root / ".guide.tmp"
    temp.write_text(_GUIDE_BODY, encoding="utf-8")
    robust_replace(temp, path)
    return True


# ------------------------------------------------------- 冲突副本与暂存残留


def find_conflict_files(repo_root: Path, *, exclude_roots: tuple[Path, ...] = ()) -> list[str]:
    """全库扫描同步客户端产生的冲突副本（按命名标记识别）。

    exclude_roots：交给其他模块处理的子树（记忆库有自己的冲突隔离与留档规则）。
    """
    conflicts: list[str] = []
    resolved_excludes = tuple(root.resolve() for root in exclude_roots)
    for path in repo_root.rglob("*"):
        relative = path.relative_to(repo_root).as_posix()
        if any(part.startswith(".") for part in PurePosixPath(relative).parts):
            continue  # .meta 等本机私有区不参与
        try:
            if any(path.resolve().is_relative_to(exclude) for exclude in resolved_excludes):
                continue
        except OSError:
            continue
        if path.is_file() and CONFLICT_MARK in path.name:
            conflicts.append(relative)
    return conflicts


def quarantine_conflicts(repo_root: Path, *, exclude_roots: tuple[Path, ...] = ()) -> list[str]:
    """冲突副本移入 .meta/trash/conflicts/<时间戳>/，避免误用双版本数据。"""
    conflicts = find_conflict_files(repo_root, exclude_roots=exclude_roots)
    if not conflicts:
        return []
    from datetime import datetime

    base = repo_root / ".meta" / "trash" / "conflicts" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    base.mkdir(parents=True, exist_ok=True)
    for relative in conflicts:
        source = repo_root / Path(relative)
        destination = base / Path(relative).name
        if destination.exists():
            destination = destination.with_name(f"{destination.stem}-{int(time.time())}{destination.suffix}")
        try:
            shutil.move(str(source), str(destination))
        except OSError:
            continue
    return conflicts


def clean_stale_staging(repo_root: Path, *, max_age_seconds: int = 3600) -> int:
    """清理超过 1 小时的失败更新暂存残留（在跑的安装不受影响）。"""
    staging = repo_root / ".meta" / "staging"
    if not staging.is_dir():
        return 0
    now = time.time()
    cleaned = 0
    for child in staging.iterdir():
        try:
            if now - child.stat().st_mtime <= max_age_seconds:
                continue
        except OSError:
            continue
        if robust_rmtree(child):
            cleaned += 1
    return cleaned


# ------------------------------------------------------------- 清单修复


def _has_transport_content(directory: Path) -> bool:
    """目录里除清单/运输件/派生文件外是否还有真实内容（判断同步是否完成）。"""
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        if path.name in MANIFEST_NAMES or is_transport_artifact(relative):
            continue
        if is_derived_local(relative):
            continue
        return True
    return False


def repair_empty_manifests(repo_root: Path) -> int:
    """files 清单为空但目录有内容 → 从磁盘现状重建（2026-09-10 分机事故的善后）。

    那次事故：分机在技能大文件尚未同步完成时跑识别，为空目录写出了
    files 为空的清单，随同步回传污染总机，全库误报「本地变化」。
    """
    repaired = 0
    for local_dir in candidate_skill_dirs(repo_root):
        directory = repo_root / local_dir
        if not directory.is_dir():
            continue
        if not any((directory / name).is_file() for name in MANIFEST_NAMES):
            continue
        manifest = read_manifest(directory)
        if manifest.get("files"):
            continue
        if not _has_transport_content(directory):
            continue
        write_manifest(
            directory,
            source_url=str(manifest.get("source_url") or ""),
            commit_hash=str(manifest.get("commit_hash") or ""),
            install_mode=str(manifest.get("install_mode") or "standard"),
            item_type=str(manifest.get("item_type") or "skill"),
            ref=str(manifest.get("ref") or "HEAD"),
            subdir=str(manifest.get("subdir") or ""),
            fetcher=str(manifest.get("fetcher") or "archive"),
            commit_date=str(manifest.get("commit_date") or ""),
            description=str(manifest.get("description") or ""),
            description_zh=str(manifest.get("description_zh") or ""),
            version=str(manifest.get("version") or ""),
            name=str(manifest.get("name") or ""),
            tags=manifest.get("tags") if isinstance(manifest.get("tags"), list) else [],
            scan=manifest.get("scan") if isinstance(manifest.get("scan"), dict) else None,
            source_type=str(manifest.get("source_type") or "github"),
            library=str(manifest.get("library") or ""),
        )
        repaired += 1
    return repaired


def refresh_manifest_transport_view(directory: Path) -> bool:
    """旧版清单的 files 记的是真实点文件路径（无容器时代）→ 刷新为运输视图。

    只在清单里确有点开头路径时动手；合并规则：旧路径全部映射为容器路径，
    另外只吸收磁盘上已存在的容器文件（收编产物），不吸收普通未跟踪文件
    （用户手工新增的可见文件仍应如实报告为本地变化）。
    """
    from .manifest import MANIFEST_NAMES

    if not any((directory / name).is_file() for name in MANIFEST_NAMES):
        return False
    manifest = read_manifest(directory)
    old_paths = [str(item["path"]) for item in manifest.get("files", [])]
    if not any(is_derived_local(path) for path in old_paths):
        return False

    merged = {to_transport(path) for path in old_paths}
    for path in directory.rglob("*"):
        if not path.is_file() or path.name in MANIFEST_NAMES:
            continue
        relative = path.relative_to(directory).as_posix()
        if is_container_path(relative):
            merged.add(relative)

    write_manifest(
        directory,
        source_url=str(manifest.get("source_url") or ""),
        commit_hash=str(manifest.get("commit_hash") or ""),
        install_mode=str(manifest.get("install_mode") or "standard"),
        item_type=str(manifest.get("item_type") or "skill"),
        ref=str(manifest.get("ref") or "HEAD"),
        subdir=str(manifest.get("subdir") or ""),
        fetcher=str(manifest.get("fetcher") or "archive"),
        commit_date=str(manifest.get("commit_date") or ""),
        description=str(manifest.get("description") or ""),
        description_zh=str(manifest.get("description_zh") or ""),
        version=str(manifest.get("version") or ""),
        name=str(manifest.get("name") or ""),
        tags=manifest.get("tags") if isinstance(manifest.get("tags"), list) else [],
        managed_files=sorted(merged),
        scan=manifest.get("scan") if isinstance(manifest.get("scan"), dict) else None,
        source_type=str(manifest.get("source_type") or "github"),
        library=str(manifest.get("library") or ""),
    )
    return True


# --------------------------------------------------------------- 自愈编排


def self_heal_library(repo_root: Path, *, exclude_roots: tuple[Path, ...] = ()) -> dict[str, Any]:
    """零配置自愈总入口：启动与「重新识别已同步条目」都会走到这里。

    每一步独立容错——单步失败只计错误数，不拖垮其余修复。
    exclude_roots 里的子树（记忆库）由 MemoryService.heal 单独处理冲突隔离。
    """
    result: dict[str, Any] = {
        "guide_written": False,
        "staging_cleaned": 0,
        "manifests_repaired": 0,
        "dotfiles_synced": 0,
        "bundles_restored": 0,
        "bundles_refreshed": 0,
        "conflicts_quarantined": [],
        "errors": [],
    }

    def step(key: str, action) -> Any:
        try:
            return action()
        except Exception as exc:  # 自愈永不拖垮主流程
            result["errors"].append(f"{key}: {exc}")
            return None

    result["guide_written"] = bool(step("guide", lambda: ensure_library_guide(repo_root)))
    result["staging_cleaned"] = step("staging", lambda: clean_stale_staging(repo_root)) or 0
    result["manifests_repaired"] = step("repair", lambda: repair_empty_manifests(repo_root)) or 0

    def _heal_items() -> None:
        for local_dir in candidate_skill_dirs(repo_root):
            directory = repo_root / local_dir
            if not directory.is_dir():
                continue
            changed = step(f"dotfiles:{local_dir}", lambda d=directory: sync_dotfiles(d))
            if changed:
                result["dotfiles_synced"] += changed
            # 无条件尝试：旧版清单的运输视图刷新自带「无旧路径即空操作」判断
            step(f"transport:{local_dir}", lambda d=directory: refresh_manifest_transport_view(d))
            if (directory / ".git").is_dir():
                if step(f"bundle:{local_dir}", lambda d=directory: refresh_git_bundle(d)):
                    result["bundles_refreshed"] += 1
            elif step(f"restore:{local_dir}", lambda d=directory: restore_git_from_bundle(d)):
                result["bundles_restored"] += 1

    step("items", _heal_items)
    result["conflicts_quarantined"] = step(
        "conflicts", lambda: quarantine_conflicts(repo_root, exclude_roots=exclude_roots)
    ) or []
    return result
