"""v1.7.5 页头统一回归：五页右上角「Agent连接提示词」+ 幽灵按钮 + 「已复制」浮框。"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade
from mshub.native.ui import copy_agent_prompt


def _primary_agent(button) -> bool:
    return button is not None and button.text() == "Agent连接提示词" and button.objectName() == "agentButton"


def test_every_page_has_agent_prompt_button(qapp, native_facade: MemoryFacade):
    native_facade.create_entry({"name": "seed", "title": "种子", "type": "project", "body": "正文"})
    window = MainWindow(native_facade)
    assert _primary_agent(window.memory_page.agent_button)
    assert _primary_agent(window.skills_page.agent_button)
    assert _primary_agent(window.security_page.agent_button)
    assert _primary_agent(window.settings_page.agent_button)
    graph = window._ensure_graph_page()
    assert _primary_agent(graph.agent_button), "记忆图示页也要有右上角按钮"
    window.close()


def test_secondary_actions_are_ghost_buttons(qapp, native_facade: MemoryFacade):
    # v1.10.0B（Stitch 结构）：页头动作组分层——主操作（新建记忆）升为 primary，
    # 次级动作回普通按钮；技能页「添加技能 / 程序」保持幽灵样式。
    window = MainWindow(native_facade)
    assert window.memory_page.new_window_button.objectName() == "primary"
    assert window.memory_page.edit_window_button.objectName() == ""
    add_buttons = [b for b in window.skills_page.findChildren(QPushButton) if b.text() == "添加技能 / 程序"]
    assert add_buttons and add_buttons[0].objectName() == "ghost"
    window.close()


def _wait_for(qapp, predicate, timeout=2000):
    """v1.8.0：copy_agent_prompt 改后台线程，回 GUI 线程是排队信号——轮询等待。"""
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    deadline = QTimer(); deadline.setSingleShot(True); deadline.timeout.connect(loop.quit)
    poll = QTimer(); poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    poll.start(); deadline.start(timeout)
    if not predicate():
        loop.exec()
    poll.stop(); deadline.stop()
    return bool(predicate())


def test_agent_prompt_copy_shows_toast(qapp, native_facade: MemoryFacade):
    """点击后：剪贴板拿到注入提示词，按钮下方弹出「已复制」小框。"""
    native_facade.create_entry({"name": "seed", "title": "种子", "type": "project", "body": "正文"})
    window = MainWindow(native_facade)
    window.show()
    window.memory_page.agent_button.click()

    def delivered():
        toast = window.findChild(QLabel, "mshubToast")
        return toast is not None and toast.text() == "已复制"

    assert _wait_for(qapp, delivered), "复制应异步完成并弹「已复制」小框"
    assert "记忆" in QApplication.clipboard().text() or "memory" in QApplication.clipboard().text().lower()
    window.close()


def test_agent_prompt_failure_is_readable(qapp, tmp_path):
    """未配置仓库时：不抛异常，小框给出可读原因。"""
    from mshub.config import ConfigStore

    store = ConfigStore(tmp_path / "config")  # 未设置 repo_root
    facade = MemoryFacade(store)
    window = MainWindow(facade)
    window.show()
    window.memory_page.agent_button.click()

    def delivered():
        toast = window.findChild(QLabel, "mshubToast")
        return toast is not None and toast.text().startswith("复制失败")

    assert _wait_for(qapp, delivered), "失败也应异步回 UI 并给出可读原因"
    window.close()


def test_graph_settings_panel_has_save_and_close_exit():
    """v1.7.5 修复：图谱设置面板是浮层，会挡住工具栏"设置"按钮——必须自带关闭出口。

    防回归三断言：源码/页面有「保存并关闭」按钮、JS 绑定收口 closePanel、
    构建产物（PyInstaller 实际打包的 bundle）里也带着该逻辑。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    html = (root / "web" / "native-graph" / "index.html").read_text(encoding="utf-8")
    assert 'id="save-settings"' in html and "保存并关闭" in html
    js = (root / "web" / "native-graph" / "graph.js").read_text(encoding="utf-8")
    assert "closePanel" in js and "Escape" in js
    bundle_dir = root / "src" / "mshub" / "native" / "graph" / "assets"
    bundled = "\n".join(p.read_text(encoding="utf-8") for p in bundle_dir.glob("*.js"))
    bundled_html = (root / "src" / "mshub" / "native" / "graph" / "index.html").read_text(encoding="utf-8")
    assert "save-settings" in bundled and "保存并关闭" in bundled_html


def _skill_row(name: str, **kwargs):
    base = {"name": name, "library": "skills", "provider": "github", "security_status": "unchecked", "updated_at": "2026-01-01T00:00:00", "description": "", "description_zh": "", "tags": []}
    base.update(kwargs)
    return base


def _raw_double_click(table, item) -> None:
    """向表格 viewport 直发原生鼠标双击序列。

    QTest.mouseDClick 在 offscreen 平台的嵌套窗口里走 QWindow 分发会丢事件
    （hits 全 0，产品代码无关），sendEvent 原生序列才能真实走通信号链路。
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    center = QPointF(table.visualItemRect(item).center())
    viewport = table.viewport()

    def send(kind, buttons):
        QApplication.sendEvent(viewport, QMouseEvent(kind, center, center, center, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier))

    for kind, buttons in (
        (QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseButtonRelease, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseButtonDblClick, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseButtonRelease, Qt.MouseButton.LeftButton),
    ):
        send(kind, buttons)


def test_real_double_click_opens_skill_detail(qapp, native_facade: MemoryFacade):
    """v1.7.5 修复：真双击必须能打开技能详情。v1.7.4 只留 itemActivated 且
    _SkillTable 漏设 NoEditTriggers（默认触发器含 DoubleClicked，双击被编辑
    路径吞掉、所有信号不发射）——双击彻底无反应。根因修复 + 双绑定 + 防重入。"""
    window = MainWindow(native_facade)
    window.show()
    window.nav.setCurrentRow(2)  # 技能页（QStackedWidget 隐藏页收不到鼠标事件，必须切页）
    page = window.skills_page
    (native_facade.repo_root() / "skills" / "demo-skill").mkdir(parents=True, exist_ok=True)
    page.items = [_skill_row("demo-skill", local_dir="skills/demo-skill")]
    page._apply_rows()
    page.table.selectRow(0)
    qapp.processEvents()
    _raw_double_click(page.table, page.table.item(0, 1))
    qapp.processEvents()
    assert page._detail_dialog is not None and page._detail_dialog.isVisible(), "双击行应打开详情窗口"
    # 双信号（doubleClicked+activated）同时到达时只开一个窗（0.35s 防重入）
    page._detail_dialog_last_open = 0.0  # 模拟用户稍后再次双击另一行
    _raw_double_click(page.table, page.table.item(0, 1))
    qapp.processEvents()
    from PySide6.QtWidgets import QDialog as _Dlg

    visible = [d for d in page.findChildren(_Dlg) if d.isVisible()]
    assert len(visible) == 1
    window.close()


def test_skill_page_has_explicit_edit_button(qapp, native_facade: MemoryFacade):
    """v1.7.5：双击之外必须有显式「编辑选中」入口（详情面板隐藏后不再无路可走）。"""
    window = MainWindow(native_facade)
    from PySide6.QtWidgets import QPushButton as _Btn

    buttons = [b for b in window.skills_page.findChildren(_Btn) if b.text() == "编辑选中"]
    assert buttons, "技能页应有「编辑选中」按钮"
    window.close()


def test_real_double_click_opens_security_report(qapp, native_facade: MemoryFacade):
    """v1.7.5：安全中心双击（双信号 + 防重入）恰好开一个报告窗。"""
    window = MainWindow(native_facade)
    window.show()
    window.nav.setCurrentRow(3)  # 安全中心页
    page = window.security_page
    page.items = [_skill_row("demo-skill")]
    page._apply({"items": page.items})
    page.table.selectRow(0)
    qapp.processEvents()
    _raw_double_click(page.table, page.table.item(0, 1))
    qapp.processEvents()
    assert page._report_dialog is not None and page._report_dialog.isVisible()
    from PySide6.QtWidgets import QDialog as _Dlg

    visible = [d for d in page.findChildren(_Dlg) if d.isVisible()]
    assert len(visible) == 1, "doubleClicked+activated 双信号同时到也只开一个窗"
    window.close()
