"""Regression coverage for neutral themes and focus/selection polish."""

from __future__ import annotations

from PySide6.QtCore import QEventLoop, QTimer

from mshub.native.main_window import MainWindow
from mshub.native.theme import PALETTES, current_palette


def _wait_for(window, predicate, timeout_ms: int = 2500) -> None:
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    while not predicate():
        window.jobs.poll()
        window.windowHandle()  # keep the native window alive during polling
        window.app if hasattr(window, "app") else None
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        if not timer.isActive():
            break
        QTimer.singleShot(20, loop.quit)
        loop.exec()
    timer.stop()


def test_neutral_canvas_tokens_and_theme_detection(qapp):
    assert PALETTES["light"]["bg"] == "#FFFFFF"
    assert PALETTES["dark"]["bg"] == "#0E0E0E"
    from PySide6.QtCore import QSettings
    from mshub.native.theme import ThemeController

    controller = ThemeController(QSettings())
    controller.apply("light")
    assert current_palette()["bg"] == "#FFFFFF"
    controller.apply("dark")
    assert current_palette()["bg"] == "#0E0E0E"


def test_task_panel_starts_collapsed_and_expands_for_first_task(qapp, native_facade):
    window = MainWindow(native_facade)
    window.show()
    qapp.processEvents()
    assert window._jobs_collapsed is True
    assert window.job_toggle.isChecked() is True
    window.jobs.submit("v1105", "v1.10.5 demo task", lambda: {"summary": "done"})
    _wait_for(window, lambda: bool(window.jobs.list()))
    qapp.processEvents()
    assert window._jobs_collapsed is False
    assert window.job_toggle.isChecked() is False
    assert window.job_table.isVisible() is True
    assert window.job_panel.maximumHeight() > 54
    window.close()


def test_search_leading_icons_are_centered_and_transparent(qapp, native_facade):
    window = MainWindow(native_facade)
    window.show()
    qapp.processEvents()
    for edit in (window.memory_page.search, window.skills_page.search):
        icon = edit.findChild(type(window.job_toggle), "searchLeading")
        assert icon is not None
        assert edit.textMargins().left() >= 28
        assert abs(icon.geometry().center().y() - edit.rect().center().y()) <= 1
    window.close()


def test_memory_list_and_job_toggle_have_no_focus_border(qapp, native_facade):
    window = MainWindow(native_facade)
    stylesheet = qapp.styleSheet()
    assert "QListWidget#memoryList:focus { border: none; outline: none; }" in stylesheet
    assert "QToolButton#jobToggle:focus" in stylesheet
    window.close()
