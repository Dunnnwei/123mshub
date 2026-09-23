from __future__ import annotations

from PySide6.QtWidgets import QApplication

from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade


def test_native_window_memory_list_edit_delete_and_theme(qapp: QApplication, native_facade: MemoryFacade) -> None:
    native_facade.create_entry({"name": "window-note", "title": "窗口测试", "body": "旧正文"})
    window = MainWindow(native_facade)
    window.memory_page.refresh_sync()
    assert window.memory_page.entry_list.count() == 1
    window.memory_page.load_detail_sync("window-note")
    window.memory_page.title_edit.setText("窗口已编辑")
    window.memory_page.body_edit.setPlainText("新正文")
    saved = window.memory_page.save_current_sync()
    assert saved["title"] == "窗口已编辑"
    assert native_facade.get_entry("window-note")["body"] == "新正文"
    assert window.theme.apply("dark") == "dark"
    assert window.theme.apply("light") == "light"
    deleted = window.memory_page.delete_current_sync()
    assert deleted["deleted"] is True
    assert window.memory_page.entry_list.count() == 0
    window.close()


def test_graph_is_created_only_after_navigation(qapp: QApplication, native_facade: MemoryFacade) -> None:
    window = MainWindow(native_facade)
    assert window.graph_page is None
    window.nav.setCurrentRow(1)
    qapp.processEvents()
    assert window.graph_page is not None
    # The offscreen fixture cannot create Chromium, but the lazy boundary is
    # still observable: the placeholder is replaced only after navigation.
    assert window.graph_page.web_view is None
    window.close()
