"""v1.10.0 双修复回归：图谱页首访自动刷新 + 后台任务面板高度三修复。"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from mshub.native.main_window import MainWindow


def _show(window, app: QApplication) -> None:
    window.show()
    for _ in range(20):
        app.processEvents()
    app.processEvents()


def test_graph_first_visit_auto_refreshes_once(qapp, native_facade) -> None:
    window = MainWindow(native_facade)
    graph = window._ensure_graph_page()
    calls: list[int] = []
    graph.refresh_graph = lambda: calls.append(1)  # type: ignore[method-assign]
    window._graph_auto_refreshed = False
    window.nav.setCurrentRow(1)
    window.nav.setCurrentRow(0)
    window.nav.setCurrentRow(1)
    assert len(calls) == 1, "首次进入图谱页应自动刷新一次，再次进入不重复刷"
    window.close()


def test_job_panel_default_keeps_five_nav_items(qapp, native_facade) -> None:
    window = MainWindow(native_facade)
    _show(window, qapp)
    # 默认面板紧凑（≤200px），导航区足够放下五个完整条目（每项约 40px）
    assert window.job_panel.height() <= 200
    assert window.nav.height() >= 5 * 38
    window.close()


def test_job_panel_collapse_shrinks_and_expand_restores(qapp, native_facade) -> None:
    window = MainWindow(native_facade)
    _show(window, qapp)
    expanded = window.job_panel.height()
    window.job_toggle.setChecked(True)  # 收起
    for _ in range(10):
        qapp.processEvents()
    assert window.job_panel.height() <= 60, "收起后面板应降到只留标题行的高度"
    window.job_toggle.setChecked(False)  # 展开
    for _ in range(10):
        qapp.processEvents()
    assert window.job_panel.height() >= 100, "展开后应恢复到可用高度"
    assert abs(window.job_panel.height() - expanded) <= 4
    window.close()


def test_job_panel_height_persists_across_restart(qapp, native_facade, tmp_path) -> None:
    from PySide6.QtCore import QSettings

    settings_path = tmp_path / "native-ui.ini"
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    settings.setValue("jobPanel/height", 200)
    settings.sync()

    window = MainWindow(native_facade)
    # 注入同一份设置（构造后、显示前替换 _ui_settings 的读取源）
    window._ui_settings = lambda: settings  # type: ignore[method-assign]
    _show(window, qapp)
    assert abs(window.job_panel.height() - 200) <= 8, "重启后应恢复用户调过的面板高度"
    window.close()
