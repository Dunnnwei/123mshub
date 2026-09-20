from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .config import ConfigStore
from .database import Database
from .errors import ConflictError, NotFoundError, SkillRepoError, ValidationError
from .fetcher import cleanup_fetch, get_fetcher, remote_version
from .indexer import rebuild_index
from .libraries import (
    ACTIVE_LIBRARIES,
    LIBRARIES,
    LIBRARY_LABELS,
    library_root,
    repo_uses_libraries,
    resolve_library,
)
from .manifest import (
    detect_local_changes,
    patch_manifest,
    read_manifest,
    refresh_scan_snapshot,
    write_manifest,
)
from .memory_service import MemoryService
from .models import InstallMode, SourceSpec
from .parser import classify_repository, parse_skill
from .prompts import build_injection_prompt
from .recovery import (
    backfill_from_manifests,
    canonicalize_library_names,
    consolidate_libraries,
    migrate_manifest_names,
    recover_synced_records,
)
from .scanner import scan_ai, scan_offline
from .syncsafe import (
    GUIDE_NAME,
    refresh_git_bundle,
    robust_copy2,
    robust_rename,
    robust_rmtree,
    self_heal_library,
    stage_dotfiles,
    sync_dotfiles,
    to_local,
    to_transport,
)
from .tags import normalize_tags
from .translation import is_mostly_chinese, translate_description
from .urltool import parse_source, safe_dir_name


def _human_size(value: float) -> str:
    if value < 1024:
        return f"{int(value)} B"
    if value < 1024 ** 2:
        return f"{value / 1024:.1f} KB"
    return f"{value / 1024 ** 2:.1f} MB"


class SkillRepository:
    def __init__(self, config_store: ConfigStore | None = None) -> None:
        self.config_store = config_store or ConfigStore()
        # 记忆区与技能区共享同一份配置（仓库根 + memory_root_override）
        self.memory = MemoryService(self.config_store)

    def _memory_excludes(self) -> tuple[Path, ...]:
        """记忆库在仓库树内时，把该子树从技能侧冲突扫描中排除（记忆区自己隔离留档）。"""
        try:
            memory_root = self.memory.memory_root()
            repo = Path(self.config_store.load().repo_root)
            memory_root.relative_to(repo)
            return (memory_root,)
        except (ValueError, ValidationError):
            return ()

    def _memory_heal(self) -> dict[str, Any]:
        """记忆区自愈（容错：失败只计错误，不拖垮技能区状态）。"""
        try:
            return self.memory.heal()
        except Exception as exc:
            return {"errors": [f"memory: {exc}"]}

    def status(self) -> dict[str, Any]:
        config = self.config_store.load()
        if not config.repo_root:
            return {
                "configured": False,
                "repo_root": "",
                "skill_count": 0,
                "unchecked_count": 0,
                "warning_count": 0,
                "memory": {"memory_root": "", "inbox_pending": 0},
            }
        root = self.config_store.require_repo_root()
        database = Database(root)
        recovered_count = recover_synced_records(root, database)
        # 其他机器的编辑/更新落在随目录同步的 manifest 里：启动时回填进本机 SQLite，
        # 再把历史「库名/目录名」迁移为身份名，合并历史分区，顺手把旧点开头清单
        # 改名为 _manifest.json（同步盘不收点开头文件），最后按本机权威视图重建 index 自愈。
        backfilled_count = backfill_from_manifests(root, database)
        canonicalized_count = canonicalize_library_names(root, database)
        consolidated = consolidate_libraries(root, database)
        migrated_manifests = migrate_manifest_names(root)
        healed = self_heal_library(root, exclude_roots=self._memory_excludes())
        # 记忆对账并入自愈总编排：冲突隔离 + 懒对账 + MEMORY.md 重建（同容错语义）
        memory_healed = self._memory_heal()
        rebuild_index(root, database)
        skills = database.list_skills()
        return {
            "configured": True,
            "repo_root": str(root),
            "skill_count": len(skills),
            "unchecked_count": sum(item["security_status"] == "unchecked" for item in skills),
            "warning_count": sum(item["security_status"] == "warning" for item in skills),
            "recovered_count": recovered_count,
            "backfilled_count": backfilled_count,
            "canonicalized_count": canonicalized_count,
            "migrated_manifests": migrated_manifests["migrated"],
            "consolidated_moved": consolidated["moved"],
            "consolidated_removed": consolidated["removed_duplicates"],
            "self_heal": healed,
            "memory_heal": memory_healed,
            "memory_root": memory_healed.get("memory_root", ""),
            "multi_library": repo_uses_libraries(root),
            "libraries": [
                {"id": name, "label": LIBRARY_LABELS[name]}
                for name in ("skills", "github")
            ],
        }

    def list(self) -> list[dict[str, Any]]:
        root, database = self._storage()
        # 列表保持轻量：不做逐文件哈希与 manifest 装饰（那是详情接口的事），
        # 否则条目增多后开屏要全量扫描磁盘，列表迟迟出不来。
        del root
        return [dict(item) for item in database.list_skills()]

    def get(self, name: str, library: str = "") -> dict[str, Any]:
        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        return self._decorate(item, root)

    def list_tags(self) -> dict[str, Any]:
        _, database = self._storage()
        catalog: dict[str, dict[str, Any]] = {}
        untagged_count = 0
        for skill in database.list_skills():
            if not skill["tags"]:
                untagged_count += 1
            for tag in skill["tags"]:
                key = str(tag).casefold()
                if key not in catalog:
                    catalog[key] = {"name": tag, "count": 0}
                catalog[key]["count"] += 1
        items = sorted(
            catalog.values(),
            key=lambda item: (-item["count"], str(item["name"]).casefold()),
        )
        return {"items": items, "untagged_count": untagged_count}

    def set_tags(self, name: str, tags: list[str], library: str = "") -> dict[str, Any]:
        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        clean_tags = normalize_tags(tags)
        now = datetime.now(UTC).isoformat()
        database.update_fields(name, {"tags": clean_tags, "updated_at": now}, library=item.get("library"))
        # 标签也是跨机编辑的一部分：必须落 manifest，否则别的机器永远看不到。
        skill_dir = root / item["local_dir"]
        if skill_dir.exists():
            patch_manifest(skill_dir, {"tags": clean_tags})
        rebuild_index(root, database)
        return self._decorate(database.get_skill(item["name"], item.get("library")), root)

    def translate_one(self, name: str, library: str = "") -> dict[str, Any]:
        """把单个条目的备注翻译成中文；原生中文备注直接清掉旧译文展示原文。"""
        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        item_library = item.get("library")
        description = str(item.get("description") or "")
        if not description.strip():
            raise ValidationError("该条目没有备注，请先在“编辑信息”里补一条再翻译。")
        now = datetime.now(UTC).isoformat()
        if is_mostly_chinese(description):
            # 原生中文备注不翻译：直接把译文位标记为原文，列表展示统一走 description_zh。
            database.update_fields(
                item["name"], {"description_zh": description, "updated_at": now}, library=item_library
            )
            return self._decorate(database.get_skill(item["name"], item_library), root)
        config = self.config_store.load()
        translated = translate_description(
            description,
            base_url=config.ai_base_url,
            api_key=self.config_store.get_secret("ai_key"),
            model=config.ai_model,
        )
        database.update_fields(
            item["name"], {"description_zh": translated, "updated_at": now}, library=item_library
        )
        skill_dir = root / item["local_dir"]
        if skill_dir.exists():
            patch_manifest(skill_dir, {"description_zh": translated})
        rebuild_index(root, database)
        return self._decorate(database.get_skill(item["name"], item_library), root)

    def translate_descriptions(
        self,
        names: list[str] | None = None,
        *,
        progress: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        """批量翻译缺失中文备注：只处理有备注、非中文、还没有译文的条目。"""
        root, database = self._storage()
        config = self.config_store.load()
        api_key = self.config_store.get_secret("ai_key")
        if not config.ai_base_url or not api_key:
            raise ValidationError("翻译备注需要先在设置中填写 AI 网关地址与 Key。")
        skills = database.list_skills()
        if names is not None:
            wanted = set(names)
            skills = [item for item in skills if item["name"] in wanted]
        # 原生中文而译文位为空的条目：直接补标记为原文，让待翻计数归零。
        now = datetime.now(UTC).isoformat()
        marked = 0
        for item in skills:
            if is_mostly_chinese(item["description"]) and not str(item.get("description_zh") or "").strip():
                database.update_fields(
                    item["name"],
                    {"description_zh": item["description"], "updated_at": now},
                    library=item.get("library"),
                )
                item["description_zh"] = item["description"]
                marked += 1
        targets = [
            item for item in skills
            if str(item.get("description") or "").strip()
            and not is_mostly_chinese(item["description"])
            and not str(item.get("description_zh") or "").strip()
        ]
        translated = 0
        errors: list[str] = []
        now = datetime.now(UTC).isoformat()
        for index, item in enumerate(targets):
            if progress:
                progress(
                    int(5 + 88 * index / max(len(targets), 1)),
                    "正在翻译备注",
                    f"{item['name']}（{index + 1}/{len(targets)}）",
                )
            try:
                zh = translate_description(
                    item["description"],
                    base_url=config.ai_base_url,
                    api_key=api_key,
                    model=config.ai_model,
                )
            except SkillRepoError as exc:
                errors.append(f"{item['name']}：{exc}")
                continue
            except Exception as exc:  # 单条失败不断整批
                errors.append(f"{item['name']}：{exc}")
                continue
            database.update_fields(
                item["name"], {"description_zh": zh, "updated_at": now}, library=item.get("library")
            )
            skill_dir = root / item["local_dir"]
            if skill_dir.exists():
                patch_manifest(skill_dir, {"description_zh": zh})
            translated += 1
        if progress:
            progress(100, "正在刷新索引")
        rebuild_index(root, database)
        return {
            "translated": translated,
            "failed": len(errors),
            "failed_details": errors[:20],
            "skipped": len(skills) - len(targets),
            "marked_native": marked,
            "total": len(targets),
        }

    def update_metadata(self, name: str, updates: dict[str, Any], library: str = "") -> dict[str, Any]:
        """手动修正条目信息：名字（身份）、备注、来源、版本、仓库副本目录（归属）。

        身份与归属分离（v0.6.0）：名字是纯身份（GitHub 条目=作者/仓库[/子目录]，
        本地自研=local/目录名），可自由修改，唯一性按 (name, library) 校验；
        目录名只决定磁盘位置（改名即移动目录），与条目名互不牵连。
        来源切换 provider=github 时从地址解析作者/仓库/子目录，并同步写
        manifest（含 name），保证跨机回填与恢复一致。
        """
        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        item_library = str(item.get("library") or "")
        current_dir = Path(item["local_dir"])
        current_dir_name = current_dir.name

        # ---- 目录名（纯归属：磁盘位置）----
        new_dir_name = str(updates.get("dir_name") or "").strip() or current_dir_name
        if new_dir_name != current_dir_name and (
            "/" in new_dir_name or "\\" in new_dir_name or new_dir_name.startswith(".")
        ):
            raise ValidationError("仓库副本目录名只能是目录名，不能包含路径分隔符或以点开头。")

        # ---- 来源 ----
        provider = str(updates.get("provider") or item.get("provider") or "github")
        if provider not in {"local", "github"}:
            raise ValidationError("来源方式只支持 local（本地自研）或 github。")
        field_updates: dict[str, Any] = {}
        source_url = str(updates.get("source_url") if updates.get("source_url") is not None else item.get("source_url") or "").strip()
        source = None
        if provider == "github":
            if not source_url:
                raise ValidationError("GitHub 来源必须填写仓库地址（作者/仓库 或完整 URL）。")
            try:
                source = parse_source(source_url)
            except ValidationError as exc:
                raise ValidationError(f"来源地址无法解析：{exc}") from exc
            github_updates = {
                "author": source.owner,
                "repo": source.repo,
                "source_url": source.source_url,
                "subdir": source.subdir,
                "ref": source.ref,
                "provider": "github",
            }
            # 本地时代残留的无效 fetcher（local）切回可用默认
            if item.get("fetcher") not in {"archive", "git"}:
                github_updates["fetcher"] = "archive"
            field_updates.update(github_updates)
        else:
            field_updates.update({
                "provider": "local",
                "author": "local",
                "repo": new_dir_name,
                "source_url": "",
                "subdir": "",
            })

        # ---- 所属库（纯归属：共享技能库 / 程序库之间搬移）----
        target_library = str(updates.get("target_library") or "").strip()
        if target_library and target_library not in ACTIVE_LIBRARIES:
            raise ValidationError(f"不支持的目标库：{target_library}（可选 {'、'.join(ACTIVE_LIBRARIES)}）")
        final_library = target_library or item_library

        # ---- 名字（纯身份：与目录、归属无关）----
        new_name = str(updates.get("name") or "").strip() or item["name"]
        if new_name != item["name"] or final_library != item_library:
            clash = database.get_skill(new_name, final_library or None)
            if clash and clash["local_dir"] != item["local_dir"]:
                raise ConflictError(f"目标库已存在同名条目：{new_name}")

        # ---- 其余字段 ----
        if updates.get("description") is not None:
            field_updates["description"] = str(updates["description"]).strip()
        if updates.get("description_zh") is not None:
            field_updates["description_zh"] = str(updates["description_zh"]).strip()
        elif "description" in field_updates:
            # 手改了备注但没动中文备注：中文备注直接占位，英文备注清掉旧译文待重翻。
            field_updates["description_zh"] = (
                field_updates["description"]
                if is_mostly_chinese(field_updates["description"])
                else ""
            )
        if updates.get("version") is not None:
            field_updates["version"] = str(updates["version"]).strip()
        if updates.get("license_name") is not None:
            field_updates["license_name"] = str(updates["license_name"]).strip()
        field_updates["updated_at"] = datetime.now(UTC).isoformat()

        # ---- 磁盘搬移（目录改名与跨库移动合并为一次；校验全部通过后才动磁盘）----
        new_local_dir = item["local_dir"]
        if final_library != item_library or new_dir_name != current_dir_name:
            skill_dir = root / item["local_dir"]
            target = library_root(root, final_library) / new_dir_name
            if skill_dir.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target != skill_dir:
                    raise ConflictError(f"目标目录已存在：{target.relative_to(root).as_posix()}")
                shutil.move(str(skill_dir), str(target))
            elif target.exists():
                raise ConflictError(f"目标目录已存在：{target.relative_to(root).as_posix()}")
            new_local_dir = target.relative_to(root).as_posix()
            field_updates["local_dir"] = new_local_dir
            field_updates["library"] = final_library
            if provider == "local":
                field_updates["repo"] = new_dir_name
        field_updates["name"] = new_name
        database.update_fields(item["name"], field_updates, library=item_library or None)

        skill_dir = root / new_local_dir
        if skill_dir.exists():
            patch_manifest(skill_dir, {
                "name": new_name,
                "source_type": provider,
                "source_url": field_updates.get("source_url", item.get("source_url", "")),
                "subdir": field_updates.get("subdir", item.get("subdir", "")),
                "description": field_updates.get("description", item.get("description", "")),
                "description_zh": field_updates.get("description_zh", item.get("description_zh", "")),
                "version": field_updates.get("version", item.get("version", "")),
                "library": final_library,
            })
        rebuild_index(root, database)
        return self._decorate(database.get_skill(new_name, final_library or None), root)

    def preview(
        self,
        source_value: str,
        *,
        item_type: str = "skill",
        mode: str = InstallMode.STANDARD.value,
        fetcher_name: str | None = None,
        ref: str | None = None,
        subdir: str | None = None,
    ) -> dict[str, Any]:
        if item_type not in {"skill", "project"}:
            raise ValidationError("仓库类型必须是 skill 或 project。")
        if item_type == "project" and subdir:
            raise ValidationError("应用项目克隆必须选择仓库根目录，不能指定技能子目录。")
        if item_type == "project":
            mode = InstallMode.FULL.value
            fetcher_name = "git"
        install_mode = self._mode(mode)
        source, result, parsed = self._fetch_and_parse(
            source_value, fetcher_name=fetcher_name, ref=ref, subdir=subdir
        )
        try:
            all_files = self._all_files(result.root)
            selected = all_files if install_mode == InstallMode.FULL else parsed.referenced_files
            total_bytes = sum((result.root / Path(relative)).stat().st_size for relative in selected)
            return {
                "name": source.name,
                "item_type": item_type,
                "source_url": source.source_url,
                "subdir": source.subdir,
                "ref": result.ref,
                "mode": install_mode.value,
                "fetcher": result.fetcher,
                "description": parsed.description,
                "version": parsed.version,
                "commit_hash": result.commit_hash,
                "commit_date": result.commit_date,
                "has_scripts": parsed.has_scripts,
                "license_name": parsed.license_name,
                "files": selected,
                "all_file_count": len(all_files),
                "selected_file_count": len(selected),
                "total_bytes": total_bytes,
                "size_warning": total_bytes >= 100 * 1024 * 1024,
                "warnings": parsed.warnings,
                "exists": self._target_exists(source),
                **classify_repository(result.root),
            }
        finally:
            cleanup_fetch(result)

    def install(
        self,
        source_value: str,
        *,
        item_type: str = "skill",
        mode: str = InstallMode.STANDARD.value,
        fetcher_name: str | None = None,
        ref: str | None = None,
        subdir: str | None = None,
        overwrite: bool = False,
        selected_files: list[str] | None = None,
        preserve_manual: bool = False,
        tags: list[str] | None = None,
        library: str | None = None,
        local_dir_name: str | None = None,
        progress: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        def report(percent: int | None, phase: str, detail: str = "") -> None:
            if progress:
                progress(percent, phase, detail)

        if item_type not in {"skill", "project"}:
            raise ValidationError("仓库类型必须是 skill 或 project。")
        if item_type == "project" and subdir:
            raise ValidationError("应用项目克隆必须选择仓库根目录，不能指定技能子目录。")
        if item_type == "project":
            mode = InstallMode.FULL.value
            fetcher_name = "git"
        clean_tags = normalize_tags(tags) if tags is not None else None
        install_mode = self._mode(mode)
        report(4, "正在解析仓库地址")
        source, result, parsed = self._fetch_and_parse(
            source_value, fetcher_name=fetcher_name, ref=ref, subdir=subdir, progress=progress
        )
        try:
            report(60, "正在准备写入仓库")
            root, database = self._storage()
            try:
                target_library = resolve_library(root, library, item_type=item_type)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            base = library_root(root, target_library)
            if local_dir_name:
                if "/" in local_dir_name or "\\" in local_dir_name or local_dir_name.startswith("."):
                    raise ValidationError("local_dir_name 只能是目录名，不能包含路径分隔符。")
                dir_name = local_dir_name
            else:
                dir_name = safe_dir_name(source.owner, source.repo)
                if source.subdir:
                    dir_name = f"{dir_name}__{source.subdir.replace('/', '_')}"
            target = base / dir_name
            # 身份与归属分离：条目名 = 来源身份（作者/仓库[/子目录]），库归属单独存。
            # 同一技能装进多个库 = 同名不同库的多条记录（复合键不冲突）。
            record_name = source.name
            existing = database.get_skill(record_name, target_library or None)
            if not existing and target.exists():
                # 目录已存在但记录名不一致（上游改名后重装）：按目录认领旧记录
                existing = database.get_skill_by_dir(target.relative_to(root).as_posix())
                if existing and existing.get("library") == (target_library or ""):
                    database.update_fields(
                        existing["name"], {"name": record_name}, library=existing.get("library")
                    )
                    existing["name"] = record_name
                else:
                    existing = None
            if target.exists() and not overwrite:
                raise ConflictError(f"{record_name} 已存在，需要明确选择覆盖。")

            # 原生中文备注直接占位译文；上游备注没变则沿用旧译文；变了就清空待重翻。
            if is_mostly_chinese(parsed.description):
                next_description_zh = parsed.description
            elif existing and parsed.description == existing.get("description"):
                next_description_zh = existing.get("description_zh", "")
            else:
                next_description_zh = ""

            all_files = self._all_files(result.root)
            managed_files = (
                all_files
                if install_mode == InstallMode.FULL
                else list(selected_files or parsed.referenced_files)
            )
            if not managed_files:
                raise ValidationError("标准安装没有解析出可安装文件，请改用全仓安装。")
            invalid = [item for item in managed_files if item not in all_files]
            if invalid:
                raise ValidationError(f"确认清单包含不存在的文件：{invalid[0]}")

            preserved: list[str] = []
            backup_path = ""
            if target.exists():
                changes = detect_local_changes(target)
                if not existing or not existing.get("commit_hash") or any(changes.values()):
                    report(63, "正在备份本地修改")
                    backup_path = str(self._backup(target, source.name, root))

            staging_parent = root / ".meta" / "staging"
            staging_parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=f"{target.name}-", dir=staging_parent))
            try:
                report(70, "正在写入文件", f"共 {len(managed_files)} 个文件")
                if item_type == "project":
                    shutil.copytree(result.root, staging, dirs_exist_ok=True, copy_function=robust_copy2)
                else:
                    self._copy_selected(result.root, staging, managed_files)
                # 点文件收进 _dot_/ 容器：同步树里只留普通名字，清单随容器视图落册
                stage_dotfiles(staging)
                if preserve_manual and target.exists():
                    changes = detect_local_changes(target)
                    for relative in sorted(set(changes["modified"] + changes["untracked"])):
                        source_path = target / Path(to_local(relative))
                        if not source_path.is_file():
                            continue
                        destination = staging / Path(relative)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, destination)
                        preserved.append(relative)
                    preserved_transport = set(preserved)
                    managed_files = [
                        item for item in managed_files if to_transport(item) not in preserved_transport
                    ]

                report(85, "正在执行安全检查")
                report_scan = scan_offline(staging)
                report(95, "正在更新清单与索引")
                target.parent.mkdir(parents=True, exist_ok=True)
                write_manifest(
                    staging,
                    source_url=source.source_url,
                    commit_hash=result.commit_hash,
                    install_mode=install_mode.value,
                    item_type=item_type,
                    ref=result.ref,
                    subdir=source.subdir,
                    fetcher=result.fetcher,
                    commit_date=result.commit_date,
                    description=parsed.description,
                    description_zh=next_description_zh,
                    version=parsed.version,
                    name=record_name,
                    tags=clean_tags if clean_tags is not None else (existing["tags"] if existing else []),
                    managed_files=managed_files,
                    scan=report_scan.to_dict(),
                    library=target_library,
                )
                self._replace_directory(staging, target)
                # 落位后立刻物化本机点文件；有 .git 的条目顺手刷新随库同步的 bundle
                sync_dotfiles(target)
                refresh_git_bundle(target)
            finally:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)

            now = datetime.now(UTC).isoformat()
            record = {
                "name": record_name,
                "item_type": item_type,
                "author": source.owner,
                "repo": source.repo,
                "provider": source.provider,
                "library": target_library,
                "source_url": source.source_url,
                "ref": result.ref,
                "subdir": source.subdir,
                "local_dir": target.relative_to(root).as_posix(),
                "version": parsed.version,
                "commit_hash": result.commit_hash,
                "commit_date": result.commit_date,
                "description": parsed.description,
                "description_zh": next_description_zh,
                "tags": clean_tags if clean_tags is not None else (existing["tags"] if existing else []),
                "has_scripts": parsed.has_scripts,
                "security_status": report_scan.status.value,
                "security_route": report_scan.route,
                "security_findings": [finding.to_dict() for finding in report_scan.findings],
                "install_mode": install_mode.value,
                "fetcher": result.fetcher,
                "license_name": parsed.license_name,
                "installed_at": existing["installed_at"] if existing else now,
                "updated_at": now,
            }
            database.upsert_skill(record)
            rebuild_index(root, database)
            item = self._decorate(database.get_skill(record_name, target_library or None), root)
            item["backup_path"] = backup_path
            item["preserved_files"] = preserved
            item["warnings"] = parsed.warnings
            return item
        finally:
            cleanup_fetch(result)

    def check_version(self, name: str, library: str = "") -> dict[str, Any]:
        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        if item.get("provider") == "local":
            raise ValidationError("本地自研技能没有远端版本，不支持在线查版本。")
        config = self.config_store.load()
        source = SourceSpec(
            provider=item["provider"],
            owner=item["author"],
            repo=item["repo"],
            source_url=item["source_url"],
            ref=item["ref"],
            subdir=item["subdir"],
        )
        remote_hash, remote_date = remote_version(
            source,
            proxy=config.proxy,
            token=(
                self.config_store.get_secret("github_token")
                if config.github_token_configured
                else ""
            ),
        )
        return {
            "name": name,
            "current_hash": item["commit_hash"],
            "remote_hash": remote_hash,
            "remote_date": remote_date,
            "has_update": bool(remote_hash and remote_hash != item["commit_hash"]),
        }

    def update(self, name: str, library: str = "", *, force: bool = False, progress: Callable[..., None] | None = None) -> dict[str, Any]:
        item = self.get(name, library)
        if item.get("provider") == "local":
            raise ValidationError("本地自研技能由总机或你手动维护，不支持在线更新。")
        version = self.check_version(name)
        if not version["has_update"] and not force:
            return {"updated": False, "version": version, "skill": item}
        # 溯源改过来的条目可能残留无效 fetcher（如 local），回退到配置默认
        valid_fetcher = item["fetcher"] if item.get("fetcher") in {"archive", "git"} else None
        updated = self.install(
            item["source_url"],
            item_type=item.get("item_type", "skill"),
            mode=item["install_mode"],
            fetcher_name=valid_fetcher,
            ref=item["ref"],
            subdir=item["subdir"],
            overwrite=True,
            library=item.get("library") or None,
            local_dir_name=Path(item["local_dir"]).name,
            progress=progress,
        )
        return {"updated": True, "version": version, "skill": updated}

    def change_mode(self, name: str, mode: str, library: str = "") -> dict[str, Any]:
        item = self.get(name, library)
        if item.get("item_type") == "project":
            raise ValidationError("应用项目必须保留完整 Git 克隆，不能切换为技能安装模式。")
        if item.get("provider") == "local":
            raise ValidationError("本地自研技能不通过仓库重装切换安装模式。")
        target_mode = self._mode(mode)
        if item["install_mode"] == target_mode.value:
            return item
        valid_fetcher = item["fetcher"] if item.get("fetcher") in {"archive", "git"} else None
        return self.install(
            item["source_url"],
            mode=target_mode.value,
            fetcher_name=valid_fetcher,
            ref=item["ref"],
            subdir=item["subdir"],
            overwrite=True,
            preserve_manual=target_mode == InstallMode.STANDARD,
            library=item.get("library") or None,
        )

    def scan(
        self,
        name: str,
        library: str = "",
        *,
        route: str = "offline",
        ai_base_url: str = "",
        ai_key: str = "",
        ai_model: str = "",
        progress: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        def report(percent: int | None, phase: str, detail: str = "") -> None:
            if progress:
                progress(percent, phase, detail)

        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        skill_dir = root / item["local_dir"]
        if route == "offline":
            report(20, "正在离线扫描脚本与提示词")
            file_progress = None
            if progress:
                def file_progress(done: int, total: int) -> None:
                    if total:
                        percent = 20 + int(65 * min(done / total, 1.0))
                        progress(percent, "正在离线扫描脚本与提示词", f"{done} / {total} 个文件")
            report_offline = scan_offline(skill_dir, progress=file_progress)
        elif route == "ai":
            config = self.config_store.load()
            report(15, "正在准备审查内容")
            report_offline = scan_ai(
                skill_dir,
                base_url=ai_base_url or config.ai_base_url,
                api_key=ai_key or self.config_store.get_secret("ai_key"),
                model=ai_model or config.ai_model,
                progress=progress,
            )
        else:
            raise ValidationError("安全检查路线必须是 offline 或 ai。")
        report(95, "正在写入检查结果")
        database.update_fields(item["name"], {
            "security_status": report_offline.status.value,
            "security_route": report_offline.route,
            "security_findings": [finding.to_dict() for finding in report_offline.findings],
            "updated_at": datetime.now(UTC).isoformat(),
        }, library=item.get("library"))
        refresh_scan_snapshot(skill_dir, report_offline.to_dict())
        rebuild_index(root, database)
        return report_offline.to_dict()

    def trust(self, name: str, library: str = "") -> dict[str, Any]:
        """手动信任：来源可信时跳过整改，状态转为安全并保留操作痕迹。"""
        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        report = {
            "status": "safe",
            "route": "trust",
            "scanned_files": 0,
            "findings": [],
            "summary": "用户确认信任此来源，已人工放行。",
            "scanned_at": datetime.now(UTC).isoformat(),
        }
        database.update_fields(item["name"], {
            "security_status": "safe",
            "security_route": "trust",
            "security_findings": [],
            "updated_at": report["scanned_at"],
        }, library=item.get("library"))
        skill_dir = root / item["local_dir"]
        if skill_dir.exists():
            refresh_scan_snapshot(skill_dir, report)
        rebuild_index(root, database)
        return self._decorate(database.get_skill(item["name"], item.get("library")), root)

    def local_changes(self, name: str, library: str = "") -> dict[str, list[str]]:
        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        return detect_local_changes(root / item["local_dir"])

    def delete(self, name: str, library: str = "") -> dict[str, Any]:
        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        target = root / item["local_dir"]
        recovery_path = ""
        if target.exists():
            trash = root / ".meta" / "trash" / safe_dir_name(item["author"], item["repo"])
            trash = trash / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            trash.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(trash))
            recovery_path = str(trash)
        database.delete_skill(item["name"], item.get("library"))
        rebuild_index(root, database)
        return {"deleted": True, "name": name, "recovery_path": recovery_path}

    def install_prompt(self, name: str, library: str = "") -> str:
        root, database = self._storage()
        item = database.get_skill(name, library or None)
        if not item:
            raise NotFoundError(f"未找到技能：{name}")
        if item.get("item_type") == "project":
            project_dir = root / item["local_dir"]
            return (
                f"应用项目 `{name}` 的本地路径：`{project_dir}`。\n"
                "请先阅读项目中的 README、安装说明和依赖文件，再根据项目文档运行或构建。\n"
                "该目录保留 Git 溯源信息；需要升级时请通过 123 MSHub 的“查版本/更新”操作。"
            )
        library_note = ""
        if len([row for row in database.list_skills() if row["name"] == name]) > 1:
            library_note = f"（同名条目在多个库各有一份，请认准 dir 为 `{item['local_dir']}` 的那一条）"
        return (
            f"共享技能库的根目录：`{root}`。\n"
            f"请先读取该目录下的说明文件 `{GUIDE_NAME}`，了解共享技能库的功能规则与技能清单"
            "（`index.json`）的查询方式。\n"
            f"本次需要使用的技能：`{name}`（清单中 dir 为 `{item['local_dir']}`{library_note}）。\n"
            f"使用前请先阅读该技能目录内的 SKILL.md，掌握用法与用途后再使用。"
        )

    def library_prompt(self) -> str:
        """MSHub 全局注入提示词：记忆读取 + 技能使用 + 记忆投递的超集（含连通暗号）。"""
        root = self.config_store.require_repo_root()
        return build_injection_prompt(root, self.memory.memory_root())

    def rebuild(self) -> dict[str, Any]:
        root, database = self._storage()
        return rebuild_index(root, database)

    def reconcile(self) -> dict[str, Any]:
        root = self.config_store.require_repo_root()
        database = Database(root)
        recovered_count = recover_synced_records(root, database)
        backfilled_count = backfill_from_manifests(root, database)
        canonicalized_count = canonicalize_library_names(root, database)
        consolidated = consolidate_libraries(root, database)
        migrated = migrate_manifest_names(root)
        healed = self_heal_library(root, exclude_roots=self._memory_excludes())
        memory_healed = self._memory_heal()
        rebuild_index(root, database)
        return {
            "recovered_count": recovered_count,
            "backfilled_count": backfilled_count,
            "canonicalized_count": canonicalized_count,
            "migrated_manifests": migrated,
            "consolidated": consolidated,
            "self_heal": healed,
            "memory_heal": memory_healed,
            "total_count": len(database.list_skills()),
        }

    def migrate_manifests(self) -> dict[str, Any]:
        """一次性迁移：把库内旧名 .manifest.json 批量改名为 _manifest.json（内容不变）。"""
        root = self.config_store.require_repo_root()
        return migrate_manifest_names(root)

    def _storage(self) -> tuple[Path, Database]:
        root = self.config_store.require_repo_root()
        database = Database(root)
        if recover_synced_records(root, database):
            rebuild_index(root, database)
        return root, database

    def _existing(self, name: str, library: str = "") -> dict[str, Any] | None:
        try:
            _, database = self._storage()
            return database.get_skill(name, library or None)
        except ValidationError:
            return None

    def _target_exists(self, source: SourceSpec) -> bool:
        try:
            root, database = self._storage()
            dir_name = safe_dir_name(source.owner, source.repo)
            if source.subdir:
                dir_name = f"{dir_name}__{source.subdir.replace('/', '_')}"
            try:
                known = bool(database.get_skill(source.name))
            except ConflictError:
                known = True  # 同名条目已在多个库存在
            return bool(
                known
                or (root / dir_name).exists()
                or any((library_root(root, lib) / dir_name).exists() for lib in LIBRARIES)
            )
        except ValidationError:
            return False

    def _fetch_and_parse(
        self,
        source_value: str,
        *,
        fetcher_name: str | None,
        ref: str | None,
        subdir: str | None,
        progress: Callable[..., None] | None = None,
    ):
        config = self.config_store.load()
        source = parse_source(source_value, ref=ref, subdir=subdir)
        chosen = fetcher_name or config.fetcher
        fetcher = get_fetcher(chosen)
        fetch_kwargs: dict[str, Any] = {}
        if progress:
            def byte_progress(done: int, total: int) -> None:
                if total:
                    percent = 6 + int(49 * min(done / total, 1.0))
                    progress(percent, "正在下载仓库", f"{_human_size(done)} / {_human_size(total)}")
                else:
                    progress(None, "正在下载仓库", f"已下载 {_human_size(done)}")
            fetch_kwargs["progress"] = byte_progress
        result = fetcher.fetch(
            source,
            mirrors=config.mirrors,
            proxy=config.proxy,
            token=(
                self.config_store.get_secret("github_token")
                if config.github_token_configured
                else ""
            ),
            **fetch_kwargs,
        )
        parsed = parse_skill(result.root, result.commit_hash, result.commit_date)
        return source, result, parsed

    @staticmethod
    def _mode(value: str) -> InstallMode:
        try:
            return InstallMode(value)
        except ValueError as exc:
            raise ValidationError("安装模式必须是 standard 或 full。") from exc

    @staticmethod
    def _all_files(root: Path) -> list[str]:
        return sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(root).parts
        )

    @staticmethod
    def _copy_selected(source_root: Path, destination: Path, files: list[str]) -> None:
        for relative in files:
            source = source_root / Path(relative)
            target = destination / Path(to_transport(relative))
            target.parent.mkdir(parents=True, exist_ok=True)
            robust_copy2(source, target)

    @staticmethod
    def _replace_directory(staging: Path, target: Path) -> None:
        old = target.with_name(f".{target.name}.previous")
        robust_rmtree(old)
        try:
            if target.exists():
                robust_rename(target, old)
            robust_rename(staging, target)
            robust_rmtree(old)
        except Exception:
            if target.exists() and target != staging:
                robust_rmtree(target)
            if old.exists() and not target.exists():
                robust_rename(old, target)
            raise

    @staticmethod
    def _backup(target: Path, name: str, root: Path) -> Path:
        backup_root = root / ".meta" / "backups" / safe_dir_name(*name.split("/", 1))
        destination = backup_root / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, destination, copy_function=robust_copy2)
        return destination

    @staticmethod
    def _decorate(item: dict[str, Any] | None, root: Path) -> dict[str, Any]:
        if item is None:
            raise SkillRepoError("技能记录意外丢失。")
        skill_dir = root / item["local_dir"]
        item = dict(item)
        item["absolute_dir"] = str(skill_dir)
        item["local_changes"] = detect_local_changes(skill_dir) if skill_dir.exists() else {
            "modified": [], "missing": [], "untracked": []
        }
        item["manifest"] = read_manifest(skill_dir) if skill_dir.exists() else {}
        return item
