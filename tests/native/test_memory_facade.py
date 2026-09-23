from __future__ import annotations

from pathlib import Path

from mshub.native.memory_facade import MemoryFacade


def test_facade_roundtrip_preserves_core_file_contract(native_facade: MemoryFacade) -> None:
    created = native_facade.create_entry({
        "name": "native-note",
        "title": "原生壳测试",
        "description": "验证 facade 不改变文件契约",
        "type": "project",
        "tags": ["native", "qa"],
        "body": "正文 [[other-note]]",
    })
    assert created["name"] == "native-note"
    assert created["links"] == [{"name": "other-note", "exists": False}]
    listed = native_facade.list_entries(query="native")
    assert [item["name"] for item in listed["items"]] == ["native-note"]
    updated = native_facade.update_entry("native-note", {"title": "已编辑", "body": "新正文"})
    assert updated["title"] == "已编辑"
    path = native_facade.service.memory_root() / "notes" / "native-note.md"
    assert path.read_text(encoding="utf-8").startswith("---\nname: native-note\n")
    deleted = native_facade.delete_entry("native-note")
    assert Path(deleted["recovery_path"]).is_file()
    assert not path.exists()


def test_inbox_admit_and_discard_use_existing_service(native_facade: MemoryFacade) -> None:
    inbox = native_facade.service.memory_root() / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "drop.md").write_text("---\ntitle: 投递\n---\n正文", encoding="utf-8")
    assert native_facade.list_inbox()["items"][0]["file"] == "drop.md"
    admitted = native_facade.admit_inbox("drop.md", {"title": "收编投递"})
    assert admitted["source"] == "agent"
    assert native_facade.list_inbox()["items"] == []
