"""v1.10.4 regression coverage for the unified native lists and task panel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer, QPoint, Qt
from PySide6.QtWidgets import QApplication, QLabel

from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade
from mshub.native.theme import PALETTES
from mshub.native.ui import RichHoverToolTip, SHIFT_RANGE_HINT
from mshub.native.views.skill_view import MetadataDialog


def _show(window: MainWindow, app: QApplication) -> None:
    window.show()
    for _ in range(12):
        app.processEvents()


def _skill(name: str, status: str = "unchecked") -> dict:
    return {
        "name": name,
        "library": "skills",
        "provider": "github",
        "security_status": status,
        "updated_at": "2026-10-02T12:30:00",
        "description": f"English description for {name}",
        "description_zh": f"用于验证 {name} 的双行说明。",
        "tags": ["agent", "demo"],
        "local_dir": f"skills/{name}",
    }


def _wait_for(window: MainWindow, predicate, timeout_ms: int = 2500) -> None:
    loop = QEventLoop()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    deadline.start(timeout_ms)
    while not predicate():
        window.jobs.poll()
        QApplication.processEvents()
        if not deadline.isActive():
            break
        QTimer.singleShot(20, loop.quit)
        loop.exec()
    deadline.stop()


def test_light_and_dark_rich_tooltip_use_application_tokens(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    owner = window.skills_page.table.viewport()
    tooltip = RichHoverToolTip(owner, lambda _pos: "标签：demo\n说明：完整说明")
    window.theme.apply("light")
    tooltip.show("标签：demo\n说明：完整说明", window.mapToGlobal(QPoint(50, 50)))
    assert PALETTES["light"]["raised"] in tooltip._tip.styleSheet()
    assert PALETTES["light"]["ink"] in tooltip._tip.findChild(QLabel).styleSheet()
    tooltip.hide()
    window.theme.apply("dark")
    tooltip.show("标签：demo\n说明：完整说明", window.mapToGlobal(QPoint(50, 50)))
    assert PALETTES["dark"]["raised"] in tooltip._tip.styleSheet()
    tooltip.hide()
    window.close()


def test_unified_list_card_merges_description_and_preserves_drag_width(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.skills_page
    page.items = [_skill(str(index)) for index in range(30)]
    page._apply_rows()
    _show(window, qapp)
    assert page.table.isColumnHidden(3)
    assert page.table.item(0, 1).data(Qt.ItemDataRole.UserRole + 10)
    card = page.table_card
    assert card.header.geometry().bottom() <= page.table.geometry().top()
    card.header.resizeSection(1, 333)
    qapp.processEvents()
    page.table.resize(940, page.table.height())
    qapp.processEvents()
    assert page.table.user_column_widths
    assert page.table.columnWidth(1) >= 333
    assert card.header.width() <= page.table.viewport().width()
    window.close()


def test_task_panel_retry_is_available_for_translation_and_keeps_id_selection(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    attempts = {"count": 0}

    def task():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("bad address")
        return {"summary": "重试成功"}

    window.jobs.submit("translate", "翻译 demo", task)
    _wait_for(window, lambda: bool(window.jobs.list()) and window.jobs.list()[0]["status"] == "error")
    _show(window, qapp)
    window._refresh_jobs()
    window.job_table.selectRow(0)
    qapp.processEvents()
    failed_id = window._selected_job_id
    assert failed_id
    assert window.job_detail_button.isEnabled()
    assert window.job_retry_button.isEnabled()
    window._retry_selected_job()
    _wait_for(window, lambda: any(job["status"] == "done" for job in window.jobs.list()))
    assert any(job["status"] == "done" for job in window.jobs.list())
    assert any(job["id"] == failed_id and job["status"] == "error" for job in window.jobs.list())
    window.close()


def test_memory_header_and_skill_editor_buttons_share_size(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    memory = window.memory_page
    qapp.processEvents()
    sizes = [button.size() for button in (memory.new_window_button, memory.edit_window_button, memory.agent_button)]
    assert sizes[0] == sizes[1] == sizes[2]
    dialog = MetadataDialog(window.skills_page, _skill("demo"))
    assert dialog.translate_button.size() == dialog.save_button.size() == dialog.close_button.size()
    labels = {label.text() for label in dialog.findChildren(QLabel)}
    assert "来源类型" in labels and "解析预览" in labels
    assert SHIFT_RANGE_HINT == "双击可打开编辑  ·  可使用 Shift 连选"
    dialog.close()
    window.close()
