"""v1.8.1 三个修复的回归：首启弹窗勾选框生命周期、显示前图谱预热、图谱拖移松手即恢复呼吸。"""
from __future__ import annotations

import gc
import re
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from mshub.config import ConfigStore
from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---- 1. 首启提示弹窗：勾选框 C++ 对象必须活过构造函数返回（致命崩溃修复） ----

def test_setup_hint_checkbox_survives_gc(qapp, tmp_path: Path, monkeypatch):
    """未配置环境下构造首启提示弹窗后强制 GC：勾选框仍可读。

    崩溃机理（v1.8.0 实锤 100% 段错误）：QCheckBox 构造时无 parent，
    setCheckBox 挂入弹窗后 Python 局部变量消亡触发 PySide6 连 C++ 对象一起
    回收；_maybe_show_setup_hint 在 exec() 后读 box.checkBox().isChecked()
    就是访问悬空指针。修复=构造时以弹窗为 parent（此处对checkBox().parentWidget
    断言）+ exec 前持引用。若回归，本测试进程会直接 access violation。
    """
    monkeypatch.setenv("MSHUB_SHOW_SETUP_HINT", "1")  # offscreen 平台保护开关
    store = ConfigStore(tmp_path / "config")  # 不 save：仓库/密钥均未配置
    facade = MemoryFacade(store)
    window = MainWindow(facade)
    try:
        box = window._build_setup_hint_box()
        assert isinstance(box, QMessageBox)
        checkbox = box.checkBox()
        assert checkbox is not None
        assert checkbox.parentWidget() is not None, "勾选框必须挂 parent，否则 GC 连 C++ 对象回收（v1.8.1 致命崩溃根因）"
        del checkbox
        gc.collect()  # _build_setup_hint_box 的局部引用已消亡，强制回收走一遍
        checked = box.checkBox().isChecked()  # 回归点：修复前此处段错误
        assert isinstance(checked, bool)
    finally:
        window.close()


def test_setup_hint_suppressed_after_checkbox(qapp, tmp_path: Path, monkeypatch):
    """勾选后完整路径（exec 返回后读勾选状态→写抑制开关）可用。

    offscreen 平台 exec() 无用户交互会挂死（v1.7.2 教训），stub 成立即返回；
    _maybe_show_setup_hint 里 exec 后读 checkBox 的代码正是 v1.8.1 崩溃点，
    本测试逼它整段跑完。
    """
    monkeypatch.setenv("MSHUB_SHOW_SETUP_HINT", "1")
    store = ConfigStore(tmp_path / "config")
    facade = MemoryFacade(store)
    window = MainWindow(facade)
    real_build = window._build_setup_hint_box
    checked_boxes: list[QMessageBox] = []

    def build_and_stub_exec():
        box = real_build()
        if box is not None:
            box.checkBox().setChecked(True)
            checked_boxes.append(box)
            box.exec = lambda: None  # type: ignore[method-assign]  # offscreen：跳过模态循环
        return box

    window._build_setup_hint_box = build_and_stub_exec  # type: ignore[method-assign]
    try:
        window._maybe_show_setup_hint()
        assert checked_boxes, "未配置环境必须构造提示弹窗"
        assert window._ui_settings().value("setupHint/suppressed") in (True, "true", 1, "1")
    finally:
        window.close()


# ---- 2. 显示前预热图谱：reveal 路径必须可达（启动闪烁修复） -----------------

def test_show_after_graph_prewarm_reveals_window(qapp, native_facade: MemoryFacade):
    """show_after_graph_prewarm：预热图谱页后窗口最终显示、startup 已排队。

    offscreen 平台 GraphView 无 WebEngine（QLabel 占位），reveal 走超时兜底；
    真实 Windows 平台的"WinIdChange 先行"路径由打包冒烟（smoke-graph）覆盖。
    """
    window = MainWindow(native_facade)
    window.show_after_graph_prewarm(timeout_ms=80)
    QTest.qWait(600)
    try:
        assert window.graph_page is not None, "预热应在 reveal 前创建图谱页"
        assert window.isVisible(), "超时兜底后窗口必须显示"
    finally:
        window.close()


# ---- 3. 图谱拖移：松手后呼吸立即恢复（graph.js 静态断言） --------------------

def _function_body(source: str, name: str) -> str:
    match = re.search(rf"function {name}\([^)]*\) {{", source)
    assert match, f"graph.js 缺少 {name}"
    start = match.end()
    depth = 1
    index = start
    while depth and index < len(source):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
        index += 1
    return source[start:index]


def test_graph_drag_does_not_refresh_interaction_gate():
    """拖移路径（moveNode/resumeFloat）不得再刷新交互时间戳。

    v1.8.0 行为：moveNode 每帧 + resumeFloat 都调 markInteraction 刷新
    lastInteraction，叠加 floatTick 的 900ms 空闲门 → 松手后呼吸冻结
    900~1100ms（用户报"拖移后卡 1 秒"）。浏览器级行为由 drag_verify
    （Playwright）人工验收，这里做防回归的静态断言。
    """
    source = (PROJECT_ROOT / "web" / "native-graph" / "graph.js").read_text(encoding="utf-8")
    for name in ("moveNode", "resumeFloat"):
        body = _function_body(source, name)
        assert "markInteraction" not in body, f"{name} 不得刷新交互时间戳（拖移后呼吸冻结根因）"
    resume = _function_body(source, "resumeFloat")
    assert "lastInteraction = performance.now() - 1000" in resume, "松手 depth 归零时必须回拨时间戳立即放行呼吸"
    pause = _function_body(source, "pauseFloat")
    assert "markInteraction" in pause, "按下时仍需 markInteraction 供漏 mouseup 安全网使用"
