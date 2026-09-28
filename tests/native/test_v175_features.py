"""v1.7.5 页头统一回归：五页右上角「Agent连接提示词」+ 幽灵按钮 + 「已复制」浮框。"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade
from mshub.native.ui import copy_agent_prompt


def _primary_agent(button) -> bool:
    return button is not None and button.text() == "Agent连接提示词" and button.objectName() == "primary"


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
    window = MainWindow(native_facade)
    assert window.memory_page.new_window_button.objectName() == "ghost"
    assert window.memory_page.edit_window_button.objectName() == "ghost"
    add_buttons = [b for b in window.skills_page.findChildren(QPushButton) if b.text() == "添加技能 / 程序"]
    assert add_buttons and add_buttons[0].objectName() == "ghost"
    window.close()


def test_agent_prompt_copy_shows_toast(qapp, native_facade: MemoryFacade):
    """点击后：剪贴板拿到注入提示词，按钮下方弹出「已复制」小框。"""
    native_facade.create_entry({"name": "seed", "title": "种子", "type": "project", "body": "正文"})
    window = MainWindow(native_facade)
    window.show()
    window.memory_page.agent_button.click()
    text = QApplication.clipboard().text()
    assert "记忆" in text or "memory" in text.lower(), "剪贴板应是注入提示词"
    toast = window.findChild(QLabel, "mshubToast")
    assert toast is not None and toast.isVisible() and toast.text() == "已复制"
    window.close()


def test_agent_prompt_failure_is_readable(qapp, tmp_path):
    """未配置仓库时：不抛异常，小框给出可读原因。"""
    from mshub.config import ConfigStore

    store = ConfigStore(tmp_path / "config")  # 未设置 repo_root
    facade = MemoryFacade(store)
    window = MainWindow(facade)
    ok = copy_agent_prompt(facade, window.memory_page.agent_button)
    assert ok is False
    toast = window.findChild(QLabel, "mshubToast")
    assert toast is not None and toast.text().startswith("复制失败")
    window.close()
