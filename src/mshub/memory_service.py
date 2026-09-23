"""记忆库服务层：条目 CRUD / 索引维护 / inbox 收编 / AI 草稿 / 启动自愈。

数据所有权（技术架构 §三）：notes\\ 条目文件是事实源，MEMORY.md 是派生索引，
SQLite（.meta\\memory.db）只是本机缓存——每次列表前按 mtime+size 做懒对账，
手改文件无需重启即可被看到。所有落盘走 syncsafe 重试层 + 临时文件原子替换，
双写时先文件后库。
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

import httpx

from .config import ConfigStore
from .errors import ConflictError, NotFoundError, ValidationError
from .fsretry import robust_rename, robust_replace, robust_unlink
from .memory import (
    INBOX_DIR,
    INDEX_NAME,
    NOTES_DIR,
    TRASH_DIRNAME,
    MemoryEntry,
    build_index_content,
    extract_links,
    is_conflict_name,
    normalize_date,
    normalize_type,
    parse_entry_file,
    sanitize_name,
    scan_inbox_file,
    slug_from_title,
    today,
    validate_name,
)
from .scanner import MARKDOWN_RULES
from .tags import normalize_tags

# 索引规模红线（借鉴 Engramory：Claude Code 等宿主只加载 MEMORY.md 的前
# 200 行 / 25KB，超出部分会被静默丢弃）。150 行 / 20KB 起提示整理。
INDEX_WARN_LINES = 150
INDEX_WARN_BYTES = 20 * 1024


def _write_text_atomic(path: Path, content: str) -> None:
    """UTF-8 + 固定 LF + 临时文件原子替换 + 瞬时锁重试。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    robust_replace(temp, path)


class _MemoryCache:
    """SQLite 本机缓存：列表秒出，条目文件才是事实源。"""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = db_path
        with self.connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    name TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    type TEXT NOT NULL DEFAULT 'reference',
                    source TEXT NOT NULL DEFAULT 'manual',
                    created TEXT NOT NULL DEFAULT '',
                    updated TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    file_mtime_ns INTEGER NOT NULL DEFAULT 0,
                    file_size INTEGER NOT NULL DEFAULT 0
                )
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def list_rows(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT name, title, description, type, source, created, updated, tags,"
                " file_mtime_ns, file_size FROM memories ORDER BY lower(name)"
            ).fetchall()
        return [self._decode(row) for row in rows]

    def upsert(self, entry: MemoryEntry, mtime_ns: int, size: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO memories (name, title, description, type, source, created, updated, tags, file_mtime_ns, file_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    title=excluded.title, description=excluded.description,
                    type=excluded.type, source=excluded.source,
                    created=excluded.created, updated=excluded.updated,
                    tags=excluded.tags, file_mtime_ns=excluded.file_mtime_ns,
                    file_size=excluded.file_size
                """,
                (
                    entry.name, entry.title, entry.description, entry.type, entry.source,
                    entry.created, entry.updated,
                    json.dumps(entry.tags, ensure_ascii=False), mtime_ns, size,
                ),
            )

    def delete(self, name: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM memories WHERE name = ?", (name,))

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        try:
            tags = json.loads(data.get("tags") or "[]")
            data["tags"] = tags if isinstance(tags, list) else []
        except json.JSONDecodeError:
            data["tags"] = []
        return data


class MemoryService:
    def __init__(self, config_store: ConfigStore | None = None) -> None:
        self.config_store = config_store or ConfigStore()

    # ------------------------------------------------------------ 路径布局

    def memory_root(self) -> Path:
        """记忆库根：默认 <仓库根>\\memory，可被 memory_root_override 指到任意路径。"""
        config = self.config_store.load()
        if getattr(config, "memory_root_override", ""):
            root = Path(config.memory_root_override).expanduser().resolve()
        else:
            root = self.config_store.require_repo_root() / "memory"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _inside_repo(self, memory_root: Path) -> bool:
        try:
            repo = self.config_store.load()
            if not repo.repo_root:
                return False
            memory_root.relative_to(Path(repo.repo_root))
            return True
        except ValueError:
            return False

    def _private_root(self, memory_root: Path) -> Path:
        """本机私有区（缓存/回收站）：记忆库在仓库内 → 仓库 .meta；分设 → 记忆库自带 .meta。"""
        if self._inside_repo(memory_root):
            return Path(self.config_store.load().repo_root) / ".meta"
        return memory_root / ".meta"

    def _notes_dir(self, memory_root: Path | None = None) -> Path:
        return (memory_root or self.memory_root()) / NOTES_DIR

    def _inbox_dir(self, memory_root: Path | None = None) -> Path:
        return (memory_root or self.memory_root()) / INBOX_DIR

    def _index_path(self, memory_root: Path | None = None) -> Path:
        return (memory_root or self.memory_root()) / INDEX_NAME

    def _trash_dir(self, memory_root: Path | None = None) -> Path:
        root = memory_root or self.memory_root()
        return self._private_root(root) / TRASH_DIRNAME

    def _ensure_layout(self) -> Path:
        root = self.memory_root()
        self._notes_dir(root).mkdir(parents=True, exist_ok=True)
        self._inbox_dir(root).mkdir(parents=True, exist_ok=True)
        return root

    def _cache(self, memory_root: Path) -> _MemoryCache:
        return _MemoryCache(self._private_root(memory_root) / "memory.db")

    # -------------------------------------------------------------- 对账

    def _reconcile_cache(self, memory_root: Path | None = None) -> int:
        """按 (mtime_ns, size) 做懒对账；返回发生变动的条目数。"""
        root = memory_root or self._ensure_layout()
        notes = self._notes_dir(root)
        cache = self._cache(root)
        disk: dict[str, tuple[int, int]] = {}
        for child in notes.iterdir():
            if not child.is_file() or child.suffix.lower() != ".md":
                continue
            if is_conflict_name(child.name):
                continue  # 冲突副本由 heal() 隔离，不进缓存
            stat = child.stat()
            disk[child.stem] = (stat.st_mtime_ns, stat.st_size)
        rows = {row["name"]: row for row in cache.list_rows()}
        changed = 0
        for name, (mtime_ns, size) in disk.items():
            row = rows.get(name)
            if row and row["file_mtime_ns"] == mtime_ns and row["file_size"] == size:
                continue
            try:
                entry = parse_entry_file(notes / f"{name}.md")
                entry.name = validate_name(name)
            except ValidationError:
                # 脏文件名/坏条目不拖垮整个列表：跳过，留待 heal() 或人工处理
                continue
            cache.upsert(entry, mtime_ns, size)
            changed += 1
        for name in rows:
            if name not in disk:
                cache.delete(name)
                changed += 1
        return changed

    # --------------------------------------------------------------- CRUD

    def list_entries(
        self,
        *,
        type_filter: str = "",
        query: str = "",
        sort: str = "updated",
    ) -> dict[str, Any]:
        root = self._ensure_layout()
        self._reconcile_cache(root)
        rows = self._cache(root).list_rows()
        items = [self._row_to_item(row) for row in rows]
        if type_filter:
            type_filter = normalize_type(type_filter)
            items = [item for item in items if item["type"] == type_filter]
        term = query.strip().lower()
        if term:
            # 搜索覆盖标题+描述+tags+正文全文：md 小文件直接读文件匹配
            notes = self._notes_dir(root)
            matched: list[dict[str, Any]] = []
            for item in items:
                haystacks = [item["title"], item["description"], " ".join(item["tags"])]
                path = notes / f"{item['name']}.md"
                if path.is_file():
                    haystacks.append(path.read_text(encoding="utf-8-sig", errors="replace"))
                if any(term in str(value).lower() for value in haystacks):
                    matched.append(item)
            items = matched
        sort = sort if sort in {"updated", "created", "name"} else "updated"
        items.sort(key=lambda item: item["name"])
        if sort != "name":
            # 稳定排序：先按名字升序垫底，再按日期倒序，同日条目仍按名字可查
            items.sort(key=lambda item: item[sort] or "", reverse=True)
        return {
            "items": items,
            "inbox_pending": self._inbox_count(root),
            "memory_root": str(root),
        }

    def get_entry(self, name: str) -> dict[str, Any]:
        root = self._ensure_layout()
        name = validate_name(name)
        path = self._notes_dir(root) / f"{name}.md"
        if not path.is_file():
            raise NotFoundError(f"未找到记忆条目：{name}")
        entry = parse_entry_file(path)
        entry.name = name
        known = {child.stem for child in self._notes_dir(root).glob("*.md")}
        links = [
            {"name": target, "exists": target in known}
            for target in extract_links(entry.body)
        ]
        return {**entry.to_meta(), "body": entry.body, "links": links}

    def graph(self, kinds: str = "link") -> dict[str, Any]:
        """Return an explainable graph; common-tag edges are opt-in.

        Double-link edges are sparse and safe for the default view.  Common-tag
        edges are intentionally behind ``kinds=link,tag`` because their natural
        construction is O(n²) for a large memory vault.
        """
        requested = {part.strip().lower() for part in str(kinds).split(",") if part.strip()}
        include_links = not requested or "link" in requested
        include_tags = "tag" in requested
        result = self.list_entries(sort="name")
        items = result["items"]
        nodes = [{
            "id": item["name"], "title": item["title"], "type": item["type"],
            "source": item["source"], "tags": item.get("tags", []),
        } for item in items]
        known = {node["id"] for node in nodes}
        edges: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        if include_links:
            for node in nodes:
                try:
                    entry = self.get_entry(node["id"])
                except Exception:
                    continue
                for link in entry.get("links", []):
                    if link.get("exists") and link["name"] in known:
                        key = (node["id"], link["name"], "双链")
                        if key not in seen:
                            seen.add(key); edges.append({"source": key[0], "target": key[1], "kind": key[2]})
        if include_tags:
            for index, left in enumerate(nodes):
                if len(edges) >= 5000:
                    break
                for right in nodes[index + 1:]:
                    common_tags = set(left["tags"]) & set(right["tags"])
                    if common_tags:
                        key = (left["id"], right["id"], "共同标签")
                        if key not in seen:
                            seen.add(key); edges.append({"source": key[0], "target": key[1], "kind": key[2]})
                            if len(edges) >= 5000:
                                break
        return {"nodes": nodes, "edges": edges, "memory_root": result.get("memory_root", "")}

    def create_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        root = self._ensure_layout()
        title = str(payload.get("title") or "").strip()
        if not title:
            body_hint = str(payload.get("body") or "").strip()
            if body_hint:
                try:
                    title = self.ai_draft(body_hint)["title"] or body_hint.splitlines()[0][:32]
                except Exception:
                    title = body_hint.splitlines()[0][:32]
            if not title:
                raise ValidationError("中文标题不能为空。")
        raw_name = str(payload.get("name") or "").strip()
        # 纯中文标题没有可提取的 ASCII 词：走 slug_from_title 兜底（note-日期-哈希）
        name = sanitize_name(raw_name) if raw_name else slug_from_title(title)
        target = self._notes_dir(root) / f"{name}.md"
        if target.exists():
            existing = parse_entry_file(target)
            raise ConflictError(
                f"已有同名条目：{name}（{existing.display_title()}）。请换个条目名，或去编辑已有条目。"
            )
        entry = MemoryEntry(
            name=name,
            title=title,
            description=str(payload.get("description") or "").strip(),
            type=normalize_type(payload.get("type")),
            source="manual",
            created=today(),
            updated=today(),
            tags=normalize_tags(payload.get("tags") or []),
            body=str(payload.get("body") or "").rstrip() + "\n" if str(payload.get("body") or "").strip() else "",
        )
        self._write_entry(root, entry)
        return self.get_entry(name)

    def update_entry(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        root = self._ensure_layout()
        name = validate_name(name)
        path = self._notes_dir(root) / f"{name}.md"
        if not path.is_file():
            raise NotFoundError(f"未找到记忆条目：{name}")
        current = parse_entry_file(path)
        current.name = name
        title = str(payload.get("title") or "").strip() or current.title
        if not title:
            raise ValidationError("中文标题不能为空。")
        new_name = name
        if payload.get("name") is not None and str(payload["name"]).strip():
            new_name = sanitize_name(str(payload["name"]))
        if new_name != name:
            conflict = self._notes_dir(root) / f"{new_name}.md"
            if conflict.exists():
                existing = parse_entry_file(conflict)
                raise ConflictError(
                    f"已有同名条目：{new_name}（{existing.display_title()}）。请换个条目名，或去编辑已有条目。"
                )
        body = current.body
        if payload.get("body") is not None:
            body = str(payload["body"])
            if body.strip():
                body = body.rstrip() + "\n"
        updated = MemoryEntry(
            name=new_name,
            title=title,
            description=(
                str(payload["description"]).strip()
                if payload.get("description") is not None else current.description
            ),
            type=normalize_type(payload.get("type") or current.type),
            source=current.source,
            created=current.created or today(),
            updated=today(),
            tags=normalize_tags(payload["tags"]) if payload.get("tags") is not None else current.tags,
            body=body,
        )
        _write_text_atomic(self._notes_dir(root) / f"{new_name}.md", updated.full_text())
        if new_name != name:
            robust_unlink(path)
        self._reconcile_cache(root)
        self.rebuild_index(root)
        return self.get_entry(new_name)

    def delete_entry(self, name: str) -> dict[str, Any]:
        root = self._ensure_layout()
        name = validate_name(name)
        path = self._notes_dir(root) / f"{name}.md"
        if not path.is_file():
            raise NotFoundError(f"未找到记忆条目：{name}")
        trash = self._trash_dir(root) / datetime_stamp()
        trash.mkdir(parents=True, exist_ok=True)
        robust_rename(path, trash / path.name)
        cache = self._cache(root)
        cache.delete(name)
        self.rebuild_index(root)
        return {"deleted": True, "name": name, "recovery_path": str(trash / path.name)}

    def bulk_update(self, names: list[str], *, type_name: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        done: list[str] = []; failed: list[str] = []
        for raw_name in dict.fromkeys(names):
            try:
                current = self.get_entry(validate_name(raw_name))
                payload: dict[str, Any] = {"title": current["title"], "body": current["body"]}
                if type_name: payload["type"] = normalize_type(type_name)
                if tags is not None: payload["tags"] = tags
                self.update_entry(current["name"], payload)
                done.append(current["name"])
            except Exception as exc:
                failed.append(f"{raw_name}: {exc}")
        return {"updated": done, "failed": failed}

    def bulk_delete(self, names: list[str]) -> dict[str, Any]:
        deleted: list[str] = []; failed: list[str] = []
        for raw_name in dict.fromkeys(names):
            try:
                deleted.append(self.delete_entry(validate_name(raw_name))["name"])
            except Exception as exc:
                failed.append(f"{raw_name}: {exc}")
        return {"deleted": deleted, "failed": failed}

    def _write_entry(self, root: Path, entry: MemoryEntry) -> None:
        _write_text_atomic(self._notes_dir(root) / f"{entry.name}.md", entry.full_text())
        self._reconcile_cache(root)
        self.rebuild_index(root)

    @staticmethod
    def _row_to_item(row: dict[str, Any]) -> dict[str, Any]:
        from .memory import SOURCE_LABELS, TYPE_LABELS

        return {
            "name": row["name"],
            "title": row["title"] or row["name"],
            "description": row["description"],
            "type": row["type"],
            "type_label": TYPE_LABELS.get(row["type"], row["type"]),
            "source": row["source"],
            "source_label": SOURCE_LABELS.get(row["source"], row["source"]),
            "created": row["created"],
            "updated": row["updated"],
            "tags": list(row["tags"]),
        }

    # --------------------------------------------------------------- 索引

    def rebuild_index(self, memory_root: Path | None = None) -> bool:
        """重建 MEMORY.md；内容不变一个字节不写（同步盘纪律）。返回是否写盘。"""
        root = memory_root or self._ensure_layout()
        rows = self._cache(root).list_rows()
        content = build_index_content(rows)
        target = self._index_path(root)
        try:
            existing = target.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            existing = None
        if existing == content:
            return False
        _write_text_atomic(target, content)
        return True

    def index_file_content(self) -> dict[str, Any]:
        root = self._ensure_layout()
        target = self._index_path(root)
        try:
            content = target.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            content = ""
        return {
            "content": content,
            "exists": target.is_file(),
            "note": "索引由程序维护，手动修改会在下次重建时被覆盖；改内容请编辑条目。",
        }

    # --------------------------------------------------------------- inbox

    def _inbox_files(self, root: Path) -> list[Path]:
        inbox = self._inbox_dir(root)
        if not inbox.is_dir():
            return []
        return sorted(
            child for child in inbox.iterdir()
            if child.is_file() and child.suffix.lower() == ".md" and not is_conflict_name(child.name)
        )

    def _inbox_count(self, root: Path) -> int:
        return len(self._inbox_files(root))

    def list_inbox(self) -> dict[str, Any]:
        root = self._ensure_layout()
        items = [scan_inbox_file(path, MARKDOWN_RULES) for path in self._inbox_files(root)]
        return {"items": [item.to_dict() for item in items]}

    def admit_inbox(self, file_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        root = self._ensure_layout()
        safe_file = _safe_file_name(file_name)
        source_path = self._inbox_dir(root) / safe_file
        if not source_path.is_file():
            raise NotFoundError(f"投递文件不存在：{safe_file}")
        item = scan_inbox_file(source_path, MARKDOWN_RULES)
        title = str(payload.get("title") or item.title or "").strip()
        if not title:
            raise ValidationError("收编前请补一个标题（可点「AI 补全标题与描述」生成）。")
        raw_name = str(payload.get("name") or "").strip() or item.suggested_name
        name = sanitize_name(raw_name)
        target = self._notes_dir(root) / f"{name}.md"
        if target.exists():
            existing = parse_entry_file(target)
            raise ConflictError(
                f"已有同名条目：{name}（{existing.display_title()}）。请换个条目名再收编。"
            )
        body = item.body.rstrip() + "\n" if item.body.strip() else ""
        if payload.get("body") is not None and str(payload["body"]).strip():
            body = str(payload["body"]).rstrip() + "\n"
        entry = MemoryEntry(
            name=name,
            title=title,
            description=(
                str(payload["description"]).strip()
                if payload.get("description") is not None else item.description
            ),
            type=normalize_type(payload.get("type") or item.type),
            source="agent",
            created=item.created or today(),
            updated=today(),
            tags=normalize_tags(payload["tags"]) if payload.get("tags") is not None else item.tags,
            body=body,
        )
        _write_text_atomic(target, entry.full_text())
        robust_unlink(source_path)
        self._reconcile_cache(root)
        self.rebuild_index(root)
        return self.get_entry(name)

    def discard_inbox(self, file_name: str) -> dict[str, Any]:
        root = self._ensure_layout()
        safe_file = _safe_file_name(file_name)
        source_path = self._inbox_dir(root) / safe_file
        if not source_path.is_file():
            raise NotFoundError(f"投递文件不存在：{safe_file}")
        trash = self._trash_dir(root) / "inbox" / datetime_stamp()
        trash.mkdir(parents=True, exist_ok=True)
        robust_rename(source_path, trash / safe_file)
        return {"discarded": True, "file": safe_file}

    def discard_all_inbox(self) -> dict[str, Any]:
        root = self._ensure_layout()
        discarded = 0
        for path in self._inbox_files(root):
            trash = self._trash_dir(root) / "inbox" / datetime_stamp()
            trash.mkdir(parents=True, exist_ok=True)
            try:
                robust_rename(path, trash / path.name)
                discarded += 1
            except OSError:
                continue
        return {"discarded": discarded}

    # ------------------------------------------------------------- AI 草稿

    def ai_draft(self, body: str) -> dict[str, str]:
        """对正文调统一 AI 接口，一次返回候选 title + description。"""
        text = str(body or "").strip()
        if not text:
            raise ValidationError("正文为空，没有可生成的内容。")
        config = self.config_store.load()
        api_key = self.config_store.get_secret("ai_key")
        if not config.ai_base_url or not api_key:
            raise ValidationError("AI 补全需要先在设置中填写「AI 接口」的地址与 Key。")
        prompt = (
            "阅读下面这段记忆正文，为它拟一个标题和一句话描述（都是简体中文）。"
            "标题不超过 16 个字；描述一句话说清这条知识讲什么，不超过 40 个字。"
            '只输出 JSON：{"title": "…", "description": "…"}，不要输出其他内容。\n\n'
            + text[:20_000]
        )
        endpoint = f"{config.ai_base_url.rstrip('/')}/chat/completions"
        request_body: dict[str, Any] = {"temperature": 0, "messages": [{"role": "user", "content": prompt}]}
        if config.ai_model:
            request_body["model"] = config.ai_model
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            response = httpx.post(endpoint, headers=headers, json=request_body, timeout=60)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise ValidationError(f"AI 请求失败：{exc}") from exc
        except ValueError as exc:
            raise ValidationError("AI 网关返回的内容不是有效 JSON。") from exc
        try:
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(_strip_fence(str(content)))
            title = str(parsed.get("title") or "").strip()
            description = str(parsed.get("description") or "").strip()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValidationError("AI 返回内容无法解析为标题与描述。") from exc
        if not title and not description:
            raise ValidationError("AI 没有返回可用的标题或描述。")
        return {"title": title, "description": description}

    # ---------------------------------------------------------------- 统计

    def stats(self) -> dict[str, Any]:
        root = self._ensure_layout()
        self._reconcile_cache(root)
        rows = self._cache(root).list_rows()
        types = {type_name: 0 for type_name in ("user", "project", "reference", "feedback")}
        for row in rows:
            if row["type"] in types:
                types[row["type"]] += 1
        monday = (date.today() - timedelta(days=date.today().weekday())).isoformat()
        this_week = sum(1 for row in rows if (row["created"] or "") >= monday)
        index_content = build_index_content(rows)
        index_lines = len(index_content.splitlines())
        index_bytes = len(index_content.encode("utf-8"))
        return {
            "total": len(rows),
            "types": types,
            "this_week": this_week,
            "inbox_pending": self._inbox_count(root),
            "memory_root": str(root),
            "index_lines": index_lines,
            "index_bytes": index_bytes,
            "index_warn": index_lines > INDEX_WARN_LINES or index_bytes > INDEX_WARN_BYTES,
        }

    # ---------------------------------------------------------------- 自愈

    def heal(self) -> dict[str, Any]:
        """启动 / 「重新识别」时的记忆区自愈：冲突隔离 + 懒对账 + 索引重建。

        每步独立容错——单步失败只计错误，不拖垮其余修复（与 self_heal_library 同语义）。
        """
        result: dict[str, Any] = {
            "memory_root": "",
            "index_conflicts": [],
            "note_conflicts": [],
            "inbox_conflicts": [],
            "cache_reconciled": 0,
            "index_rewritten": False,
            "errors": [],
        }

        def step(key: str, action):
            try:
                return action()
            except Exception as exc:  # 自愈永不拖垮主流程
                result["errors"].append(f"{key}: {exc}")
                return None

        root = step("layout", self._ensure_layout)
        if root is None:
            return result
        result["memory_root"] = str(root)

        def _quarantine() -> None:
            trash = self._trash_dir(root) / "conflicts" / datetime_stamp()
            notes = self._notes_dir(root)
            inbox = self._inbox_dir(root)
            # 索引冲突副本：派生物，直接清理留档
            for child in sorted(root.iterdir()):
                if child.is_file() and is_conflict_name(child.name) and child.name.startswith(INDEX_NAME):
                    trash.mkdir(parents=True, exist_ok=True)
                    robust_rename(child, trash / child.name)
                    result["index_conflicts"].append(child.name)
            for directory, bucket in ((notes, "note_conflicts"), (inbox, "inbox_conflicts")):
                if not directory.is_dir():
                    continue
                for child in sorted(directory.iterdir()):
                    if child.is_file() and is_conflict_name(child.name):
                        trash.mkdir(parents=True, exist_ok=True)
                        robust_rename(child, trash / child.name)
                        result[bucket].append(child.name)

        step("conflicts", _quarantine)
        result["cache_reconciled"] = step("reconcile", lambda: self._reconcile_cache(root)) or 0
        result["index_rewritten"] = bool(step("index", lambda: self.rebuild_index(root)))
        return result

    def rebuild_all(self) -> dict[str, Any]:
        """手动「重建索引 / 对账」入口。"""
        healed = self.heal()
        rows = self._cache(self._ensure_layout()).list_rows()
        return {**healed, "total_count": len(rows)}


def datetime_stamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"


def _safe_file_name(file_name: str) -> str:
    """inbox 文件名只允许普通文件名：拦路径分隔符、点开头与非法字符。"""
    text = str(file_name or "").strip()
    if not text or text != Path(text).name or text.startswith("."):
        raise ValidationError(f"非法的投递文件名：{file_name}")
    if any(char in text for char in '<>:"/\\|?*'):
        raise ValidationError(f"非法的投递文件名：{file_name}")
    return text


def _strip_fence(value: str) -> str:
    import re

    value = value.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    return value
