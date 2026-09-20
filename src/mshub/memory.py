"""记忆库核心层（纯函数，无配置与 GUI 依赖）。

数据模型（需求文档 §2.3 / 技术架构 §2.2）：
- 条目文件 = 事实源：notes/<name>.md，开头 frontmatter（name/title/description/
  type/source/created/updated/tags），其后正文；
- MEMORY.md = 派生索引：按 type 分组、组内按 name 排序，内容确定（不含时间戳），
  重建时「实质没变不写盘」；
- inbox = agent 投递区：程序只读，收编由人在界面里完成。

解析纪律：坏行容忍——frontmatter 缺字段用兜底值，绝不让单条脏数据拖垮整个列表。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .errors import ValidationError

# 记忆库目录结构
INDEX_NAME = "MEMORY.md"
NOTES_DIR = "notes"
INBOX_DIR = "inbox"
TRASH_DIRNAME = "memory-trash"

MEMORY_TYPES = ("user", "project", "reference", "feedback")
MEMORY_SOURCES = ("manual", "agent")

TYPE_LABELS = {
    "user": "用户",
    "project": "项目",
    "reference": "参考",
    "feedback": "反馈",
}
SOURCE_LABELS = {
    "manual": "手动创建",
    "agent": "agent 投递",
}
DEFAULT_TYPE = "reference"
DEFAULT_SOURCE = "manual"

_FRONTMATTER_DELIM = "---"
_FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")
_LIST_ITEM_RE = re.compile(r"^\s*-\s+(.*)$")
_LINK_RE = re.compile(r"\[\[([^\[\]|]+)(?:\|[^\[\]]*)?\]\]")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLUG_OK_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_ASCII_RUN_RE = re.compile(r"[A-Za-z0-9]+")

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def today() -> str:
    """本机本地日期（frontmatter 里的 created/updated 都是 YYYY-MM-DD）。"""
    return datetime.now().strftime("%Y-%m-%d")


def normalize_date(value: Any) -> str:
    """容忍各种日期写法，落成 YYYY-MM-DD；无法解析时退回今天。"""
    text = str(value or "").strip()
    if _DATE_RE.match(text):
        return text
    for fmt in ("%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return today()


def normalize_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in MEMORY_TYPES:
        return text
    return DEFAULT_TYPE


def normalize_source(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in MEMORY_SOURCES:
        return text
    return DEFAULT_SOURCE


# --------------------------------------------------------------- 条目名字

def sanitize_name(value: str) -> str:
    """把任意输入清理成合法的条目名（kebab-case，同时是 Windows 安全文件名）。

    清理规则：NFKC 归一化（全角"ＭＳＨＵＢ"→"mshub"，借鉴 Engramory 生态实践）、
    小写、空白/下划线转连字符、丢弃非法字符、压缩连续连字符。
    清理后仍为空或撞 Windows 保留名时抛 ValidationError。
    """
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    validate_name(text)
    return text


def validate_name(value: str) -> str:
    """校验（可选先经 sanitize）：非空、kebab-case、Windows 保留名拦截。"""
    text = str(value or "").strip()
    if not text:
        raise ValidationError("条目名不能为空（英文短横线格式，如 my-first-note）。")
    if text.startswith("."):
        raise ValidationError("条目名不能以点开头。")
    if not _SLUG_OK_RE.match(text):
        raise ValidationError(
            "条目名只能是英文小写字母、数字和短横线（kebab-case），"
            "例如 my-first-note。中文标题请留在「标题」字段。"
        )
    if text.upper() in _WINDOWS_RESERVED:
        raise ValidationError(f"{text} 是 Windows 保留名，请换一个条目名。")
    if len(text) > 64:
        raise ValidationError("条目名过长（最多 64 个字符）。")
    return text


def slug_from_title(title: str) -> str:
    """从标题自动生成条目名：提取英文/数字词；纯中文标题用日期+短哈希兜底。

    哈希用 sha256（内置 hash() 受 PYTHONHASHSEED 影响跨进程不稳定，
    会破坏 name 作为长期标识的一致性）。
    """
    words = _ASCII_RUN_RE.findall(str(title or ""))
    if words:
        candidate = "-".join(word.lower() for word in words)[:64]
        return sanitize_name(candidate)
    stamp = date.today().strftime("%m%d")
    digest = hashlib.sha256(str(title).encode("utf-8")).hexdigest()[:4]
    return sanitize_name(f"note-{stamp}-{digest}")


# ------------------------------------------------------------- frontmatter

def _quote_yaml(value: str) -> str:
    """标量安全落 YAML：含特殊字符（含逗号，防行内列表切分歧义）或首尾空白的值加双引号。"""
    if value == "" or re.search(r"[:#,'\"\n]", value) or value.strip() != value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _unquote_yaml(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        inner = text[1:-1]
        if text[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    if "#" in text:
        # 裸标量里的行内注释：'# 前有空白才算注释起点
        for index, char in enumerate(text):
            if char == "#" and index > 0 and text[index - 1].isspace():
                return text[:index].strip()
    return text


def _parse_scalar_list(value: str) -> list[str]:
    inner = value.strip().strip("[]")
    if not inner:
        return []
    return [str(_unquote_yaml(item)) for item in inner.split(",") if str(item).strip()]


@dataclass(slots=True)
class MemoryEntry:
    name: str
    title: str = ""
    description: str = ""
    type: str = DEFAULT_TYPE
    source: str = DEFAULT_SOURCE
    created: str = ""
    updated: str = ""
    tags: list[str] = field(default_factory=list)
    body: str = ""

    def display_title(self) -> str:
        return self.title or self.name

    def frontmatter_text(self) -> str:
        lines = ["---"]
        lines.append(f"name: {_quote_yaml(self.name)}")
        lines.append(f"title: {_quote_yaml(self.title or self.name)}")
        lines.append(f"description: {_quote_yaml(self.description)}")
        lines.append(f"type: {self.type}")
        lines.append(f"source: {self.source}")
        lines.append(f"created: {self.created or today()}")
        lines.append(f"updated: {self.updated or self.created or today()}")
        if self.tags:
            lines.append("tags: [" + ", ".join(_quote_yaml(tag) for tag in self.tags) + "]")
        lines.append("---")
        return "\n".join(lines)

    def full_text(self) -> str:
        body = self.body.rstrip()
        return f"{self.frontmatter_text()}\n\n{body}\n" if body else f"{self.frontmatter_text()}\n"

    def to_meta(self) -> dict[str, Any]:
        """列表/详情接口的元信息视图（不含正文）。"""
        return {
            "name": self.name,
            "title": self.title or self.name,
            "description": self.description,
            "type": self.type,
            "type_label": TYPE_LABELS.get(self.type, self.type),
            "source": self.source,
            "source_label": SOURCE_LABELS.get(self.source, self.source),
            "created": self.created,
            "updated": self.updated,
            "tags": list(self.tags),
        }


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """把文件文本拆成（元信息字典, 正文）。没有 frontmatter 时返回空字典。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        return {}, text.lstrip("\n")
    fields: dict[str, Any] = {}
    pending_list_key: str | None = None
    body_start = len(lines)
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == _FRONTMATTER_DELIM:
            body_start = index + 1
            break
        match = _FIELD_RE.match(line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            pending_list_key = None
            if value == "":
                pending_list_key = key
                fields[key] = []
            elif value.startswith("["):
                fields[key] = _parse_scalar_list(value)
            else:
                fields[key] = _unquote_yaml(value)
            continue
        item = _LIST_ITEM_RE.match(line)
        if item and pending_list_key:
            current = fields.get(pending_list_key)
            if isinstance(current, list):
                current.append(str(_unquote_yaml(item.group(1))))
            continue
        # 坏行容忍：无法识别的行直接跳过，不让单条脏数据拖垮解析
    else:
        # 没有闭合的 '---'：整个文件都不算有合法 frontmatter
        return {}, text.lstrip("\n")
    body = "\n".join(lines[body_start:]).lstrip("\n")
    return fields, body


def entry_from_fields(name: str, fields: dict[str, Any], body: str) -> MemoryEntry:
    """按兜底规则把解析出的字段装配成条目（坏行容忍的另一半）。"""
    raw_tags = fields.get("tags")
    tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()] if isinstance(raw_tags, list) else []
    return MemoryEntry(
        name=str(name),
        title=str(fields.get("title") or "").strip() or str(name),
        description=str(fields.get("description") or "").strip(),
        type=normalize_type(fields.get("type")),
        source=normalize_source(fields.get("source")),
        created=normalize_date(fields.get("created")),
        updated=normalize_date(fields.get("updated") or fields.get("created")),
        tags=tags[:12],
        body=body,
    )


def parse_entry_text(name: str, text: str) -> MemoryEntry:
    fields, body = split_frontmatter(text)
    return entry_from_fields(name, fields, body)


def parse_entry_file(path: Path) -> MemoryEntry:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    fallback_name = sanitize_name(path.stem) if path.stem else "unnamed"
    return parse_entry_text(fallback_name, text)


# ------------------------------------------------------------------ 双链

def extract_links(body: str) -> list[str]:
    """提取正文里的 [[条目名]] 双链（保留顺序、去重；|别名 语法取竖线前段）。"""
    seen: dict[str, None] = {}
    for match in _LINK_RE.finditer(body or ""):
        target = match.group(1).strip()
        if target:
            seen.setdefault(target, None)
    return list(seen.keys())


# ------------------------------------------------------------------ 索引

def build_index_content(entries: list[MemoryEntry] | list[dict[str, Any]]) -> str:
    """生成 MEMORY.md 全文。内容确定（不含时间戳），比对即知是否需要写盘。

    条目统一按 name 排序、按 type 分组，保证任意机器重建结果逐字节一致。
    """
    def field_of(entry: Any, key: str, default: str = "") -> str:
        if isinstance(entry, MemoryEntry):
            return str(getattr(entry, key, "") or default)
        return str(entry.get(key, "") or default)

    rows = []
    for entry in entries:
        rows.append({
            "name": field_of(entry, "name"),
            "title": field_of(entry, "title") or field_of(entry, "name"),
            "description": field_of(entry, "description"),
            "type": normalize_type(field_of(entry, "type")),
        })
    rows.sort(key=lambda row: row["name"])

    lines = [
        "# MEMORY.md · 记忆索引",
        "",
        "> 这份索引由 123 MSHub 维护，条目在 notes\\ 下。一行一条：标题 — 一句话描述。",
        "> 手动修改本文件会在下次重建时被覆盖；改内容请编辑对应条目。",
        "",
    ]
    if not rows:
        lines.append("（暂无记忆条目）")
        lines.append("")
        return "\n".join(lines)
    for type_name in MEMORY_TYPES:
        group = [row for row in rows if row["type"] == type_name]
        if not group:
            continue
        lines.append(f"## {type_name}")
        for row in group:
            suffix = f" — {row['description']}" if row["description"] else ""
            lines.append(f"- [{row['title']}](notes/{row['name']}.md){suffix}")
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------ inbox

@dataclass(slots=True)
class InboxItem:
    file: str
    suggested_name: str
    title: str
    description: str
    type: str
    created: str
    tags: list[str]
    body: str
    raw_text: str
    has_frontmatter: bool
    injection_hits: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "suggested_name": self.suggested_name,
            "title": self.title,
            "description": self.description,
            "type": normalize_type(self.type),
            "created": self.created,
            "tags": list(self.tags),
            "body": self.body,
            "raw_text": self.raw_text,
            "has_frontmatter": self.has_frontmatter,
            "injection_hits": self.injection_hits,
        }


def scan_inbox_file(path: Path, markdown_rules: list[tuple]) -> InboxItem:
    """读取一个投递文件并跑 md 注入规则（规则组来自 scanner.MARKDOWN_RULES）。"""
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    fields, body = split_frontmatter(raw)
    stem = path.stem
    suggested = sanitize_name(str(fields.get("name") or stem) if (fields.get("name") or stem) else "inbox-note")
    hits: list[dict[str, Any]] = []
    for severity, category, label, pattern in markdown_rules:
        for match in pattern.finditer(raw):
            line = raw.count("\n", 0, match.start()) + 1
            hits.append({
                "severity": severity,
                "category": category,
                "rule": label,
                "line": line,
                "excerpt": (raw.splitlines()[line - 1].strip()[:240] if raw.splitlines() else ""),
            })
            if len(hits) >= 20:
                return _inbox_item(path, suggested, fields, body, raw, hits)
    return _inbox_item(path, suggested, fields, body, raw, hits)


def _inbox_item(
    path: Path, suggested: str, fields: dict[str, Any], body: str, raw: str,
    hits: list[dict[str, Any]],
) -> InboxItem:
    return InboxItem(
        file=path.name,
        suggested_name=suggested,
        title=str(fields.get("title") or "").strip(),
        description=str(fields.get("description") or "").strip(),
        type=normalize_type(fields.get("type")),
        created=normalize_date(fields.get("created")),
        tags=[str(tag).strip() for tag in fields.get("tags", []) if str(tag).strip()]
        if isinstance(fields.get("tags"), list) else [],
        body=body,
        raw_text=raw,
        has_frontmatter=bool(fields),
        injection_hits=hits,
    )


def is_conflict_name(file_name: str) -> bool:
    """同步客户端的冲突副本命名标记（与 syncsafe.CONFLICT_MARK 同规则）。"""
    return "冲突副本" in file_name or "conflict" in file_name.lower()
