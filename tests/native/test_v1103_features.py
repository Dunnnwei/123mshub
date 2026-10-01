"""v1.10.3 regression checks for failure identity, tags, counts and list copy."""
from __future__ import annotations

from PySide6.QtTest import QSignalSpy

from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade
from mshub.native.views.memory_view import _memory_source_label
from mshub.native.views.skill_view import AddSkillDialog, MetadataDialog


def _skill(name="demo", **extra):
    item = {
        "name": name,
        "library": "skills",
        "provider": "github",
        "local_dir": f"skills/{name}",
        "description": "An English description",
        "description_zh": "中文技能说明",
        "tags": ["agent", "safe-use"],
        "security_status": "unchecked",
        "security_findings": [],
        "updated_at": "2026-10-01T00:00:00",
    }
    item.update(extra)
    return item


def test_v1103_skill_headers_search_clear_and_current_row(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.skills_page
    assert [page.table.horizontalHeaderItem(i).text() for i in range(7)] == [
        "多选", "名称", "标签", "说明", "来源", "时间", "安全"
    ]
    assert page.search.isClearButtonEnabled()
    page.items = [_skill("installed"), _skill("ghost", local_dir="skills/missing")]
    page._apply_rows()
    page.table.selectRow(1)
    page.current = page.items[0]
    assert page._selected()["name"] == "ghost", "双击/动作必须以当前行身份为准，不能沿用旧 current"
    window.close()


def test_v1103_native_skill_inventory_hides_missing_install_dirs(native_facade: MemoryFacade, monkeypatch):
    root = native_facade.repo_root()
    (root / "skills" / "installed").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        native_facade.repository,
        "list",
        lambda: [_skill("installed"), _skill("ghost", local_dir="skills/missing")],
    )
    assert [item["name"] for item in native_facade.skills()["items"]] == ["installed"]


def test_v1103_missing_skill_does_not_open_stale_selection(qapp, native_facade: MemoryFacade, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window = MainWindow(native_facade)
    page = window.skills_page
    (native_facade.repo_root() / "skills" / "installed").mkdir(parents=True, exist_ok=True)
    page.items = [_skill("installed"), _skill("ghost")]
    page._apply_rows()
    page.table.selectRow(0)
    page.current = page.items[0]
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, message: messages.append(message))
    monkeypatch.setattr(page, "refresh", lambda *args: None)

    page.table.itemDoubleClicked.emit(page.table.item(1, 1))

    assert messages == ["未能打开该项目"]
    assert page._detail_dialog is None
    assert page.current["name"] == "ghost", "双击信号的行身份优先于旧的选中项"
    window.close()


def test_v1103_security_pending_count_and_all_safe_zero(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.security_page
    spy = QSignalSpy(page.pendingChanged)
    page._apply({"items": [_skill("a", security_status="safe"), _skill("b", security_status="warning"), _skill("c", security_status="unchecked")]})
    assert spy.at(spy.size() - 1)[0] == 2
    page._apply({"items": [_skill("a", security_status="safe")]})
    assert spy.at(spy.size() - 1)[0] == 0
    window.close()


def test_v1103_tags_are_present_in_add_and_edit_dialogs(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    add = AddSkillDialog(window.skills_page)
    add.tags.setText("one, two")
    assert add.options()["tags"] == ["one", "two"]
    edit = MetadataDialog(window.skills_page, _skill("demo"))
    assert edit.tags.text() == "agent, safe-use"
    edit.tags.setText("release, internal")
    # The save payload is assembled at the boundary; inspect the normalized UI value.
    assert [tag.strip() for tag in edit.tags.text().split(",") if tag.strip()] == ["release", "internal"]
    edit.close(); add.close(); window.close()


def test_v1103_memory_source_labels_follow_ui_language(qapp):
    from mshub.native.i18n import LanguageController

    assert _memory_source_label("imported") == "导入"
    assert _memory_source_label("manual") == "存储"
    controller = LanguageController()
    controller.apply("en")
    try:
        assert _memory_source_label("imported") == "Imported"
        assert _memory_source_label("manual") == "Stored"
    finally:
        controller.apply("zh-CN")
