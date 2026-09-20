from __future__ import annotations

import json
from pathlib import Path

import pytest

from mshub.config import ConfigStore
from mshub.errors import ConflictError, NotFoundError, ValidationError
from mshub.memory_service import MemoryService


@pytest.fixture()
def service(tmp_path: Path) -> MemoryService:
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    return MemoryService(store)


def _write_note(memory_root: Path, name: str, text: str) -> None:
    target = memory_root / "notes" / f"{name}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


class TestCrud:
    def test_create_list_get(self, service: MemoryService) -> None:
        created = service.create_entry({
            "title": "用户偏好", "name": "user-preferences",
            "description": "中文交流、在意 token 消耗", "type": "user",
            "tags": ["偏好"], "body": "事实。[[other-note]]",
        })
        assert created["name"] == "user-preferences"
        assert created["source"] == "manual"
        assert created["links"] == [{"name": "other-note", "exists": False}]

        listing = service.list_entries()
        assert [item["name"] for item in listing["items"]] == ["user-preferences"]
        assert listing["items"][0]["type_label"] == "用户"

        detail = service.get_entry("user-preferences")
        assert detail["body"].startswith("事实。")

    def test_create_slug_from_title(self, service: MemoryService) -> None:
        created = service.create_entry({"title": "Release Flow", "body": "x"})
        assert created["name"] == "release-flow"

    def test_duplicate_name_conflict(self, service: MemoryService) -> None:
        service.create_entry({"title": "第一条", "name": "same-name"})
        with pytest.raises(ConflictError) as exc:
            service.create_entry({"title": "第二条", "name": "same-name"})
        assert "已有同名条目" in str(exc.value)

    def test_update_renames_file_and_refreshes_updated(self, service: MemoryService) -> None:
        service.create_entry({"title": "旧标题", "name": "old-name", "body": "内容"})
        updated = service.update_entry("old-name", {
            "title": "新标题", "name": "new-name", "body": "新内容",
        })
        assert updated["name"] == "new-name"
        root = service.memory_root()
        assert not (root / "notes" / "old-name.md").exists()
        assert (root / "notes" / "new-name.md").exists()
        assert updated["updated"] >= updated["created"]

    def test_update_rejects_conflicting_rename(self, service: MemoryService) -> None:
        service.create_entry({"title": "A", "name": "note-a"})
        service.create_entry({"title": "B", "name": "note-b"})
        with pytest.raises(ConflictError):
            service.update_entry("note-a", {"name": "note-b"})

    def test_delete_is_soft(self, service: MemoryService) -> None:
        service.create_entry({"title": "待删", "name": "doomed"})
        result = service.delete_entry("doomed")
        assert result["deleted"]
        assert "memory-trash" in result["recovery_path"]
        assert Path(result["recovery_path"]).exists()
        with pytest.raises(NotFoundError):
            service.get_entry("doomed")

    def test_missing_entry_raises(self, service: MemoryService) -> None:
        with pytest.raises(NotFoundError):
            service.get_entry("ghost")

    def test_title_required(self, service: MemoryService) -> None:
        with pytest.raises(ValidationError):
            service.create_entry({"name": "no-title"})


class TestIndex:
    def test_index_rebuilt_and_stable(self, service: MemoryService) -> None:
        service.create_entry({"title": "条目", "name": "entry-one", "description": "描述"})
        root = service.memory_root()
        index = root / "MEMORY.md"
        assert index.is_file()
        first = index.read_text(encoding="utf-8")
        assert "(notes/entry-one.md) — 描述" in first
        # 内容不变不写盘
        mtime = index.stat().st_mtime_ns
        assert service.rebuild_index(root) is False
        assert index.stat().st_mtime_ns == mtime

    def test_search_matches_body(self, service: MemoryService) -> None:
        service.create_entry({"title": "甲", "name": "note-a", "body": "独特的正文关键词 xyzzy"})
        service.create_entry({"title": "乙", "name": "note-b", "body": "别的内容"})
        hits = service.list_entries(query="xyzzy")
        assert [item["name"] for item in hits["items"]] == ["note-a"]


class TestReconcile:
    def test_manual_file_edit_picked_up_lazily(self, service: MemoryService) -> None:
        service.create_entry({"title": "原始", "name": "manual-edit"})
        root = service.memory_root()
        _write_note(root, "hand-made", "---\ntitle: 手写\ntype: project\n---\n手写正文")
        items = service.list_entries()["items"]
        names = [item["name"] for item in items]
        assert "manual-edit" in names and "hand-made" in names
        hand = next(item for item in items if item["name"] == "hand-made")
        assert hand["type"] == "project"

    def test_delete_file_removes_row(self, service: MemoryService) -> None:
        service.create_entry({"title": "临时", "name": "temp-note"})
        (service.memory_root() / "notes" / "temp-note.md").unlink()
        assert all(item["name"] != "temp-note" for item in service.list_entries()["items"])


class TestInbox:
    def test_admit_flow(self, service: MemoryService) -> None:
        inbox = service.memory_root() / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "agent-drop.md").write_text(
            "---\nname: agent-drop\ndescription: 投递描述\n---\nagent 写的正文",
            encoding="utf-8",
        )
        items = service.list_inbox()["items"]
        assert len(items) == 1
        assert items[0]["suggested_name"] == "agent-drop"
        assert items[0]["raw_text"].startswith("---")

        admitted = service.admit_inbox("agent-drop.md", {"title": "收编标题"})
        assert admitted["source"] == "agent"
        assert admitted["source_label"] == "agent 投递"
        assert not (inbox / "agent-drop.md").exists()
        assert (service.memory_root() / "notes" / "agent-drop.md").exists()
        assert service.list_inbox()["items"] == []

    def test_admit_conflict(self, service: MemoryService) -> None:
        service.create_entry({"title": "占用", "name": "taken"})
        inbox = service.memory_root() / "inbox"
        (inbox / "clash.md").write_text("---\nname: taken\n---\nx", encoding="utf-8")
        with pytest.raises(ConflictError):
            service.admit_inbox("clash.md", {"title": "撞名", "name": "taken"})

    def test_discard_and_discard_all(self, service: MemoryService) -> None:
        inbox = service.memory_root() / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        for name in ("d1.md", "d2.md"):
            (inbox / name).write_text(f"---\nname: {name[:-3]}\n---\n正文", encoding="utf-8")
        service.discard_inbox("d1.md")
        assert service.stats()["inbox_pending"] == 1
        result = service.discard_all_inbox()
        assert result["discarded"] == 1
        assert service.stats()["inbox_pending"] == 0

    def test_traversal_file_name_rejected(self, service: MemoryService) -> None:
        with pytest.raises(ValidationError):
            service.admit_inbox("..\\evil.md", {"title": "x"})


class TestHeal:
    def test_conflict_copies_quarantined(self, service: MemoryService) -> None:
        service.create_entry({"title": "条目", "name": "real-note"})
        root = service.memory_root()
        # 制造冲突副本（模拟同步盘命名）
        (root / "notes" / f"real-note（NAS 的冲突副本 1 - 2026-09-20）.md").write_text(
            "---\ntitle: 双版本\n---\n冲突内容", encoding="utf-8"
        )
        (root / f"MEMORY.md（NAS 的冲突副本 1 - 2026-09-20）.md").write_text(
            "# 假索引", encoding="utf-8"
        )
        result = service.heal()
        assert len(result["note_conflicts"]) == 1
        assert len(result["index_conflicts"]) == 1
        assert not (root / f"MEMORY.md（NAS 的冲突副本 1 - 2026-09-20）.md").exists()
        # 原条目不受影响
        assert service.get_entry("real-note")["title"] == "条目"

    def test_heal_rebuilds_index(self, service: MemoryService) -> None:
        service.create_entry({"title": "条目", "name": "idx-note"})
        (service.memory_root() / "MEMORY.md").unlink()
        result = service.heal()
        assert result["index_rewritten"] is True
        assert (service.memory_root() / "MEMORY.md").is_file()


class TestOverrideRoot:
    def test_memory_root_override(self, tmp_path: Path) -> None:
        store = ConfigStore(tmp_path / "config")
        store.save({
            "repo_root": str(tmp_path / "repo"),
            "memory_root_override": str(tmp_path / "elsewhere-memory"),
        })
        service = MemoryService(store)
        service.create_entry({"title": "外部", "name": "outside-note"})
        assert (tmp_path / "elsewhere-memory" / "notes" / "outside-note.md").exists()
        # 私有区跟随记忆库（分设时自带 .meta）
        assert (tmp_path / "elsewhere-memory" / ".meta").is_dir()


class TestStatsAndAi:
    def test_stats_counts(self, service: MemoryService) -> None:
        service.create_entry({"title": "一", "name": "n1", "type": "user"})
        service.create_entry({"title": "二", "name": "n2", "type": "project"})
        (service.memory_root() / "inbox" / "p.md").write_text("---\n---\nx", encoding="utf-8")
        stats = service.stats()
        assert stats["total"] == 2
        assert stats["types"]["user"] == 1
        assert stats["types"]["project"] == 1
        assert stats["this_week"] == 2
        assert stats["inbox_pending"] == 1

    def test_ai_draft_requires_config(self, service: MemoryService) -> None:
        with pytest.raises(ValidationError) as exc:
            service.ai_draft("正文")
        assert "AI 接口" in str(exc.value)

    def test_index_file_view(self, service: MemoryService) -> None:
        service.create_entry({"title": "条目", "name": "view-me"})
        view = service.index_file_content()
        assert view["exists"]
        assert "(notes/view-me.md)" in view["content"]
        assert "程序维护" in view["note"]
