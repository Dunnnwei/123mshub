from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication

from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade
from mshub.native.views.skill_view import AddSkillDialog, MetadataDialog


def _skill(name="demo"):
    return {
        "name": name,
        "library": "skills",
        "provider": "local",
        "local_dir": f"skills/{name}",
        "source_url": "C:/source/demo.zip",
        "description": "English description",
        "description_zh": "中文说明",
        "tags": [],
        "security_status": "unchecked",
    }


def test_add_dialog_has_name_field_and_forwards_it(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    dialog = AddSkillDialog(window.skills_page)
    dialog.naming.setText("本地命名")
    assert dialog.options()["item_name"] == "本地命名"
    assert dialog.options()["local_dir_name"] == "本地命名"
    assert ".zip" in dialog.source.placeholderText().casefold()
    dialog.close()
    window.close()


def test_skill_editor_places_ai_description_before_translate(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    dialog = MetadataDialog(window.skills_page, _skill())
    assert dialog.ai_description_button.text() == "AI说明"
    assert dialog.ai_description_button.size() == dialog.translate_button.size()
    dialog.close()
    window.close()


def test_memory_range_status_uses_common_row_wording(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.memory_page
    page._shift_range_applied(1, 3)
    assert page.range_status.text() == "已连选第 2–4 行（共 3 项）"
    window.close()


def test_skills_batch_bar_has_no_redundant_prefix(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    labels = [label.text() for label in window.skills_page.findChildren(type(window.skills_page.status))]
    assert "已勾选条目：" not in labels
    window.close()
