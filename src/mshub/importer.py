"""外部记忆技能导入器：从任意目录打捞可识别的记忆与技能，导入本仓库。

支持的来源（按识别优先级）：
1. mshub 自身仓库（另一台机）：memory\\notes\\*.md + inbox + MEMORY.md；
2. DSH 总机格式：memory.md 索引 + brain\\*.md（标题从索引行提取）；
3. Engramory 式布局：MEMORY.md + 同级散装带 frontmatter 的 md；
4. 散装启发式：递归扫描 *.md，frontmatter 具备记忆条目特征的收，不像的放弃。

技能来源：
- skillrepo/skillhub 库（index.json + _manifest.json）：按清单复制目录，
  导入后走 reconcile() 自愈入册（与跨机同步同一条已验证路径）；
- 含 SKILL.md 的任意目录：复制进 skills\\，由 recover 按「本地自研」收录。

导入是长任务：经 JobManager 后台执行，分阶段上报进度；完成后自动跑一遍
整理（疑似重复检测 + 索引重建 + 整理日报），全程不阻断界面。
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import ConfigStore
from .errors import ValidationError
from .fsretry import robust_copy2
from .libraries import LIBRARY_DSH, LIBRARY_GITHUB
from .manifest import MANIFEST_NAMES, patch_manifest, read_manifest, write_manifest
from .memory import (
    INBOX_DIR,
    INDEX_NAME,
    NOTES_DIR,
    MemoryEntry,
    normalize_date,
    normalize_source,
    normalize_type,
    parse_entry_file,
    sanitize_name,
    split_frontmatter,
)
from .memory_service import MemoryService, _write_text_atomic
from .repository import SkillRepository
from .scanner import scan_offline
from .syncsafe import CONFLICT_MARK

# 扫描边界：防误选整个磁盘把程序拖死
MAX_SCAN_FILES = 20_000
MAX_ENTRY_BYTES = 512 * 1024
MAX_SKILL_DIR_BYTES = 500 * 1024 * 1024
SKIP_DIR_NAMES = {
    "node_modules", ".git", ".meta", "__pycache__", ".venv", "venv",
    "dist", "build", ".pytest_cache", ".playwright-mcp", ".idea", ".vscode",
    "test-output", "target", ".mypy_cache", ".ruff_cache",
}
MEMORY_TYPE_WORDS = {"user", "project", "reference", "feedback", "global", "local", "task"}
# 明显不是记忆的文件名（技能文档/项目说明；技能侧会收走或本来就非记忆）
MEMORY_SKIP_FILENAMES = {"SKILL.md", "README.md", "CHANGELOG.md", "LICENSE", "AGENTS.md", "CLAUDE.md", "tasks.md"}
# DSH 等总机风格：索引文件小写、条目区叫 brain
DSH_INDEX_NAME = "memory.md"
DSH_BRAIN_DIR = "brain"


def _source_label(source: Path) -> str:
    """Derive a human-readable import platform only when the path names it."""
    text = source.as_posix().casefold()
    for token, label in (
        ("workbuddy", "WorkBuddy"),
        ("zcode", "ZCode"),
        ("claude", "Claude Desktop"),
        ("cursor", "Cursor"),
    ):
        if token in text:
            return label
    return "外部仓库"

_INDEX_LINE_RE = re.compile(r"^[-*]\s+\[([^\]]+)\]\(([^)]+\.md)\)", re.I)
_TITLE_NORM_RE = re.compile(r"[\s，。：:；;！!？?\-_/\\]+")


@dataclass(slots=True)
class MemoryCandidate:
    path: Path
    kind: str  # mshub / dsh / engramory / loose
    fields: dict[str, Any]
    body: str
    title_hint: str = ""

    def preview(self) -> dict[str, Any]:
        name = str(self.fields.get("name") or "").strip() or self.path.stem
        return {
            "file": self.path.name,
            "kind": self.kind,
            "name": name,
            "title": str(self.fields.get("title") or "").strip() or self.title_hint or "",
            "description": str(self.fields.get("description") or "").strip()[:100],
            "type": normalize_type(self.fields.get("type")),
        }


@dataclass(slots=True)
class SkillCandidate:
    path: Path
    kind: str  # skillrepo / skill-local
    library: str  # skills / github
    dir_name: str
    name_hint: str = ""
    imported_from: str = ""

    def preview(self) -> dict[str, Any]:
        return {
            "dir": self.dir_name,
            "kind": self.kind,
            "library": self.library,
            "name": self.name_hint or self.dir_name,
            "imported_from": self.imported_from,
        }


@dataclass(slots=True)
class ScanReport:
    source: Path
    memory_items: list[MemoryCandidate] = field(default_factory=list)
    skill_items: list[SkillCandidate] = field(default_factory=list)
    scanned_files: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        for item in self.memory_items:
            by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        return {
            "source": str(self.source),
            "memory_count": len(self.memory_items),
            "memory_by_kind": by_kind,
            "memory_preview": [item.preview() for item in self.memory_items[:60]],
            "skill_count": len(self.skill_items),
            "skill_preview": [item.preview() for item in self.skill_items[:60]],
            "scanned_files": self.scanned_files,
            "notes": self.notes[:10],
        }


def _safe_child_name(value: str) -> str:
    text = str(value or "").strip()
    if not text or text != Path(text).name or text.startswith("."):
        raise ValidationError(f"非法的目录名：{value}")
    if any(char in text for char in '<>:"|?*'):
        raise ValidationError(f"非法的目录名：{value}")
    return text


def _skipped(relative_parts: tuple[str, ...]) -> bool:
    return any(part in SKIP_DIR_NAMES or part.startswith(".") for part in relative_parts)


def _iter_md_files(root: Path, *, max_files: int = MAX_SCAN_FILES) -> list[Path]:
    """受限递归收集 *.md（跳过技术目录、符号链接与冲突副本）。

    符号链接不跟随（Engramory 0.3.3 同款纪律）：防目录循环与越出来源根。
    """
    collected: list[Path] = []
    for path in root.rglob("*"):
        if len(collected) >= max_files:
            break
        relative = path.relative_to(root)
        if _skipped(relative.parts):
            continue
        if path.is_symlink():
            continue
        if path.is_file() and path.suffix.lower() == ".md" and CONFLICT_MARK not in path.name:
            collected.append(path)
    return collected


def _looks_like_memory(fields: dict[str, Any]) -> bool:
    """记忆条目特征：有身份字段（name/title/description 之一）且另有元信息佐证。"""
    has_identity = any(str(fields.get(key) or "").strip() for key in ("name", "title", "description"))
    if not has_identity:
        return False
    tags = fields.get("tags")
    meta_evidence = (
        str(fields.get("type") or "").strip().lower() in MEMORY_TYPE_WORDS
        or bool(str(fields.get("created") or "").strip())
        or bool(str(fields.get("updated") or "").strip())
        or (isinstance(tags, list) and bool(tags))
    )
    return bool(meta_evidence)


def _parse_index_titles(index_path: Path, entry_dir: str) -> dict[str, str]:
    """从索引文件的 `- [标题](dir/文件.md)` 行提取 文件名→标题 映射。"""
    titles: dict[str, str] = {}
    try:
        content = index_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return titles
    prefix = "" if entry_dir == "." else f"{entry_dir}/"
    for line in content.splitlines():
        match = _INDEX_LINE_RE.match(line.strip())
        if not match:
            continue
        title, target = match.group(1).strip(), match.group(2).strip().replace("\\", "/")
        normalized = target.split("#", 1)[0]
        if normalized.startswith(prefix):
            titles.setdefault(Path(normalized).name, title)
    return titles


class ImportService:
    def __init__(self, config_store: ConfigStore | None = None) -> None:
        self.config_store = config_store or ConfigStore()
        self.memory = MemoryService(self.config_store)
        self.repository = SkillRepository(self.config_store)

    # -------------------------------------------------------------- 扫描

    def scan(
        self, source_value: str, *, progress: Callable[..., None] | None = None
    ) -> dict[str, Any]:
        """只读预览：识别可导入的记忆与技能，不写入任何内容。"""
        return self._scan_internal(source_value, progress=progress).to_dict()

    def _scan_internal(
        self, source_value: str, *, progress: Callable[..., None] | None = None
    ) -> ScanReport:
        def report_progress(percent: int, phase: str, detail: str = "") -> None:
            if progress:
                progress(percent, phase, detail)

        source = Path(str(source_value or "").strip()).expanduser()
        if not source.is_dir():
            raise ValidationError(f"目录不存在或不可读：{source}")
        report = ScanReport(source=source.resolve())
        imported_from = _source_label(source)

        report_progress(5, "正在识别目录结构")
        md_files = _iter_md_files(source)
        report.scanned_files = len(md_files)
        report_progress(15, "正在识别记忆条目", f"{len(md_files)} 个 md 文件")

        collected: dict[Path, MemoryCandidate] = {}

        def claim(paths: list[Path], kind: str, titles: dict[str, str] | None = None) -> int:
            added = 0
            for path in paths:
                if path in collected:
                    continue
                try:
                    if path.stat().st_size > MAX_ENTRY_BYTES:
                        report.notes.append(f"跳过过大文件：{path.name}")
                        continue
                    text = path.read_text(encoding="utf-8-sig", errors="replace")
                except OSError:
                    continue
                fields, body = split_frontmatter(text)
                if not fields or not _looks_like_memory(fields):
                    continue
                collected[path] = MemoryCandidate(
                    path=path, kind=kind, fields=fields, body=body,
                    title_hint=(titles or {}).get(path.name, ""),
                )
                added += 1
            return added

        # 1) mshub 自身仓库：memory\notes + memory\inbox
        mshub_notes = source / "memory" / NOTES_DIR
        mshub_inbox = source / "memory" / INBOX_DIR
        mshub_files = [
            *(sorted(mshub_notes.glob("*.md")) if mshub_notes.is_dir() else []),
            *(sorted(mshub_inbox.glob("*.md")) if mshub_inbox.is_dir() else []),
        ]
        if mshub_files:
            titles: dict[str, str] = {}
            mshub_index = source / "memory" / INDEX_NAME
            if mshub_index.is_file():
                titles = _parse_index_titles(mshub_index, NOTES_DIR)
            count = claim(mshub_files, "mshub", titles)
            report_progress(30, "正在识别记忆条目", f"mshub 记忆库：{count} 条")

        # 2) DSH 总机格式：memory.md + brain\*.md
        dsh_index = source / DSH_INDEX_NAME
        dsh_brain = source / DSH_BRAIN_DIR
        if dsh_index.is_file() and dsh_brain.is_dir():
            titles = _parse_index_titles(dsh_index, DSH_BRAIN_DIR)
            files = sorted(dsh_brain.glob("*.md"))
            dsh_inbox = dsh_brain / INBOX_DIR
            if dsh_inbox.is_dir():
                files += sorted(dsh_inbox.glob("*.md"))
            count = claim(files, "dsh", titles)
            report.notes.append(f"识别到 DSH 总机格式（{DSH_INDEX_NAME} + brain\\），索引行标题已提取。")
            report_progress(40, "正在识别记忆条目", f"DSH brain：{count} 条")

        # 3) Engramory 式 / 通用：MEMORY.md（或 .engramory-memory\MEMORY.md）同级 md
        #    （.engramory-memory 以点开头会被 _iter_md_files 排除，这里单独 glob）
        for index_candidate in (source / INDEX_NAME, source / ".engramory-memory" / INDEX_NAME):
            if not index_candidate.is_file():
                continue
            base = index_candidate.parent
            titles = _parse_index_titles(index_candidate, ".")
            count = claim(sorted(base.glob("*.md")), "engramory", titles)
            if count:
                report.notes.append(f"识别到 Engramory 式索引（{index_candidate.name}）。")
            break

        # 4) 散装启发式：剩余 md 逐个试（ZCode/WorkBuddy 等任意 agent 的记忆 md）
        rest = [p for p in md_files if p not in collected and p.name not in MEMORY_SKIP_FILENAMES]
        report_progress(55, "正在打捞散装记忆", f"剩余 {len(rest)} 个候选文件")
        claim(rest, "loose")

        report.memory_items = list(collected.values())
        report_progress(65, "记忆识别完成", f"共 {len(report.memory_items)} 条")

        # ---- 技能源识别
        skill_dirs: dict[Path, SkillCandidate] = {}
        claimed_targets: set[tuple[str, str]] = set()

        def add_skill(path: Path, kind: str, library: str, name_hint: str = "") -> None:
            if path in skill_dirs or not path.is_dir():
                return
            if path.is_symlink():
                return  # 符号链接目录不注册：防循环与越出来源根
            try:
                relative = path.relative_to(source)
            except ValueError:
                return
            if _skipped(relative.parts):
                return  # 索引/清单可能引用被排除的目录（node_modules 等），统一在此拦截
            try:
                dir_name = _safe_child_name(path.name)
            except ValidationError:
                report.notes.append(f"跳过非法目录名：{path.name}")
                return
            resolved_library = library if library in (LIBRARY_DSH, LIBRARY_GITHUB) else LIBRARY_DSH
            target = (resolved_library, dir_name)
            if target in claimed_targets:
                # 不同来源路径指向同一目标（库+目录名）：只留先认领的一个，
                # 预览数与导入结果对齐，避免「260 个候选装出 255 个」的口径差
                return
            claimed_targets.add(target)
            skill_dirs[path] = SkillCandidate(
                path=path, kind=kind,
                library=resolved_library,
                dir_name=dir_name, name_hint=name_hint, imported_from=imported_from,
            )

        # skillrepo 库：index.json（skills[].dir）
        for path in source.rglob("index.json"):
            if _skipped(path.relative_to(source).parts):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            items = data.get("skills") if isinstance(data, dict) else None
            if not isinstance(items, list):
                continue
            root = path.parent
            for item in items:
                if not isinstance(item, dict):
                    continue
                dir_value = str(item.get("dir") or "").strip()
                if dir_value:
                    add_skill(
                        root / Path(dir_value.replace("\\", "/")),
                        "skillrepo",
                        str(item.get("library") or "") or LIBRARY_DSH,
                        str(item.get("name") or ""),
                    )
        # 含 manifest 的技能目录
        for name in MANIFEST_NAMES:
            for path in source.rglob(name):
                directory = path.parent
                if _skipped(directory.relative_to(source).parts):
                    continue
                manifest = read_manifest(directory)
                add_skill(
                    directory, "skillrepo",
                    str(manifest.get("library") or "") or LIBRARY_DSH,
                    str(manifest.get("name") or ""),
                )
        # 含 SKILL.md 的目录 → 本地自研候选
        for path in source.rglob("SKILL.md"):
            directory = path.parent
            if _skipped(directory.relative_to(source).parts):
                continue
            if directory not in skill_dirs:
                add_skill(directory, "skill-local", LIBRARY_DSH)

        report.skill_items = list(skill_dirs.values())

        # 已认领为技能的目录，其内部 md（模板/示例/说明文档）不再走散装记忆通道：
        # 典型如 engramory 技能包的 templates\example-*.md，长得就是记忆条目的样子
        skill_roots = set(skill_dirs)
        before_count = len(report.memory_items)
        report.memory_items = [
            item for item in report.memory_items
            if item.kind != "loose" or not any(root in item.path.parents for root in skill_roots)
        ]
        excluded = before_count - len(report.memory_items)
        if excluded:
            report.notes.append(f"已排除技能目录内的文档 {excluded} 个（防模板示例误入记忆）。")

        report_progress(100, "扫描完成", f"记忆 {len(report.memory_items)} 条 / 技能 {len(report.skill_items)} 个")
        return report

    # -------------------------------------------------------------- 导入

    def run(
        self,
        source_value: str,
        *,
        include_memory: bool = True,
        include_skills: bool = True,
        progress: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        def report_progress(percent: int | None, phase: str, detail: str = "") -> None:
            if progress:
                progress(percent, phase, detail)

        repo_root = self.config_store.require_repo_root()
        result: dict[str, Any] = {
            "memory_imported": 0,
            "memory_renamed": [],
            "memory_skipped_same": [],
            "memory_failed": [],
            "skills_imported": [],
            "skills_skipped": [],
            "skills_failed": [],
            "reconcile": {},
            "duplicate_groups": [],
            "tidy_report": None,
            "errors": [],
        }

        report_progress(3, "正在扫描来源目录")
        report = self._scan_internal(source_value, progress=report_progress)

        # ---------------- 记忆导入
        if include_memory and report.memory_items:
            memory_root = self.memory._ensure_layout()
            notes_dir = self.memory._notes_dir(memory_root)
            total = len(report.memory_items)
            for index, candidate in enumerate(report.memory_items):
                report_progress(
                    6 + int(38 * (index + 1) / total),
                    "正在写入记忆条目",
                    f"{candidate.path.name}（{index + 1}/{total}）",
                )
                try:
                    self._import_memory_entry(notes_dir, candidate, result)
                except Exception as exc:  # 单条失败（含非法名）不断整批
                    result["memory_failed"].append(f"{candidate.path.name}: {exc}")
            self.memory._reconcile_cache(memory_root)
            self.memory.rebuild_index(memory_root)
            report_progress(45, "记忆写入完成", f"成功 {result['memory_imported']} 条")

        # ---------------- 技能导入
        if include_skills and report.skill_items:
            total = len(report.skill_items)
            for index, candidate in enumerate(report.skill_items):
                report_progress(
                    46 + int(29 * (index + 1) / total),
                    "正在复制技能目录",
                    f"{candidate.dir_name}（{index + 1}/{total}）",
                )
                target_base = repo_root / candidate.library
                target = target_base / candidate.dir_name
                if target.exists():
                    result["skills_skipped"].append(f"{candidate.dir_name}：目标目录已存在")
                    continue
                try:
                    if self._dir_size(candidate.path) > MAX_SKILL_DIR_BYTES:
                        result["skills_skipped"].append(f"{candidate.dir_name}：超过 500MB 上限")
                        continue
                    target_base.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(
                        candidate.path, target, copy_function=robust_copy2,
                        ignore=lambda _src, names: [n for n in names if Path(_src, n).is_symlink()],
                    )
                    if not any((target / name).is_file() for name in MANIFEST_NAMES):
                        # 没有清单的旧仓也要留下来源/标签/导入时间，供迁移后筛选。
                        report_scan = scan_offline(target) if candidate.kind == "skill-local" else None
                        write_manifest(
                            target,
                            source_url="",
                            commit_hash="",
                            install_mode="full",
                            item_type="skill",
                            ref="HEAD",
                            subdir="",
                            fetcher="local",
                            commit_date="",
                            description="",
                            version="",
                            name=candidate.dir_name,
                            tags=[],
                            managed_files=sorted(
                                path.relative_to(target).as_posix()
                                for path in target.rglob("*")
                                if path.is_file() and path.name not in MANIFEST_NAMES
                            ),
                            scan=report_scan.to_dict() if report_scan else None,
                            source_type="local" if candidate.kind == "skill-local" else "github",
                            library=candidate.library,
                            imported_from=candidate.imported_from,
                            imported_at=datetime.now(UTC).isoformat(),
                        )
                    elif any((target / name).is_file() for name in MANIFEST_NAMES):
                        # 保留旧清单全部字段，只补导入追踪，避免导入平台信息丢失。
                        patch_manifest(target, {
                            "imported_from": candidate.imported_from,
                            "imported_at": datetime.now(UTC).isoformat(),
                        })
                    result["skills_imported"].append(f"{candidate.dir_name}（{candidate.library}）")
                except OSError as exc:
                    # 复制中途失败必须清掉半成品目录：否则残留目录会让后续导入永远走「已存在跳过」
                    shutil.rmtree(target, ignore_errors=True)
                    result["skills_failed"].append(f"{candidate.dir_name}: {exc}")

        # ---------------- 整理：入册 + 去重审查 + 日报
        report_progress(76, "正在入册与重建索引")
        try:
            result["reconcile"] = {
                key: value for key, value in self.repository.reconcile().items()
                if key in ("recovered_count", "total_count")
            }
        except Exception as exc:
            result["errors"].append(f"reconcile: {exc}")

        report_progress(88, "正在整理去重审查")
        try:
            result["duplicate_groups"] = self._duplicate_groups()
        except Exception as exc:
            result["errors"].append(f"duplicate-check: {exc}")

        report_progress(95, "正在生成整理日报")
        try:
            from .tidy import TidyService

            tidy_result = TidyService(self.config_store).run_tidy(use_ai=False)
            result["tidy_report"] = {
                "file": tidy_result["file"],
                "content": tidy_result["content"][:4000],
            }
        except Exception as exc:
            result["errors"].append(f"tidy: {exc}")

        result["memory_count"] = self.memory.stats()["total"]
        result["skill_count"] = len(self.repository.list())
        report_progress(100, "导入完成")
        return result

    # ------------------------------------------------------------- 内部

    def _import_memory_entry(self, notes_dir: Path, candidate: MemoryCandidate, result: dict[str, Any]) -> None:
        raw_name = str(candidate.fields.get("name") or "").strip() or candidate.path.stem
        name = sanitize_name(raw_name)
        tags_field = candidate.fields.get("tags")
        title = (
            str(candidate.fields.get("title") or "").strip()
            or candidate.title_hint
            or raw_name
        )
        if not str(candidate.fields.get("title") or "").strip() and candidate.body.strip():
            try:
                title = self.memory.ai_draft(candidate.body)["title"] or title
            except Exception:
                pass
        entry = MemoryEntry(
            name=name,
            title=title,
            description=str(candidate.fields.get("description") or "").strip(),
            type=normalize_type(candidate.fields.get("type")),
            # 外部迁移保留显式 source；缺失时标记为导入仓库，避免用户误以为是手动创建。
            source=normalize_source(candidate.fields.get("source") or "imported"),
            created=normalize_date(candidate.fields.get("created")),
            updated=normalize_date(candidate.fields.get("updated") or candidate.fields.get("created")),
            tags=[str(tag).strip() for tag in tags_field if str(tag).strip()][:12]
            if isinstance(tags_field, list) else [],
            body=candidate.body,
        )
        target = notes_dir / f"{entry.name}.md"
        if target.exists():
            if self._same_entry(target, entry):
                result["memory_skipped_same"].append(entry.name)
                return
            # 内容不同：自动避让改名导入（尽量做到，不丢数据）；
            # 避让候选也做内容比对——重复导入同一来源时幂等识别，不无限累积 -3/-4
            for suffix in range(2, 100):
                alternative = f"{entry.name}-{suffix}"
                alternative_path = notes_dir / f"{alternative}.md"
                if not alternative_path.exists():
                    result["memory_renamed"].append(f"{entry.name} → {alternative}")
                    entry.name = alternative
                    target = alternative_path
                    break
                if self._same_entry(alternative_path, entry):
                    result["memory_skipped_same"].append(alternative)
                    return
            else:
                result["memory_failed"].append(f"{entry.name}: 重名避让失败")
                return
        _write_text_atomic(target, entry.full_text())
        result["memory_imported"] += 1

    @staticmethod
    def _same_entry(path: Path, entry: MemoryEntry) -> bool:
        """实质内容比对：忽略 name（避让改名会改变它）与 updated，其余字段+正文一致即视为同一条。

        只捕获 IO/解析类异常；编程错误（NameError 等）要大声失败，不许静默吞掉。
        """
        try:
            existing = parse_entry_file(path)
        except (OSError, ValueError):
            return False
        return (
            existing.title == entry.title
            and existing.description == entry.description
            and existing.type == entry.type
            and existing.tags == entry.tags
            and existing.created == entry.created
            and existing.body.rstrip() == entry.body.rstrip()
        )

    def _duplicate_groups(self) -> list[list[str]]:
        """标题归一化相同 → 疑似重复组（只报告，不自动合并，留给人在程序里裁决）。"""
        entries = self.memory.list_entries(sort="name")["items"]
        seen: dict[str, str] = {}
        groups: dict[str, list[str]] = {}
        for entry in entries:
            key = _TITLE_NORM_RE.sub("", str(entry["title"])).casefold()
            if not key:
                continue
            if key in seen:
                groups.setdefault(key, [seen[key]]).append(entry["name"])
            else:
                seen[key] = entry["name"]
        return list(groups.values())[:20]

    @staticmethod
    def _dir_size(directory: Path) -> int:
        total = 0
        for path in directory.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return total
