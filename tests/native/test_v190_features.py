"""v1.9.0 八项需求的回归：皇家蓝保存反馈、批量/彻底删除、信任选中、Shift 连选、单一完整包、在线升级核心逻辑。"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QCheckBox, QPushButton, QWidget

from mshub.config import ConfigStore
from mshub.errors import FetchError
from mshub.native import upgrader
from mshub.native.memory_facade import MemoryFacade
from mshub.native.task_runner import TaskRunner
from mshub.native.theme import DARK_QSS, LIGHT_QSS
from mshub.native.ui import SHIFT_RANGE_HINT, ShiftRangeCheckMixin
from mshub.native.views.memory_view import MemoryPage
from mshub.native.views.settings_view import SettingsPage


# ---- 需求 8：升级核心逻辑（纯函数，无网络） --------------------------------

def test_parse_version_and_is_newer():
    assert upgrader.parse_version("v1.9.0") == (1, 9, 0)
    assert upgrader.parse_version("1.10.1-rc1") == (1, 10, 1)
    assert upgrader.parse_version("") == (0,)
    assert upgrader.is_newer("v1.9.1", "1.9.0")
    assert upgrader.is_newer("v1.10.0", "1.9.9")  # 逐段数值比较，不是字符串比较
    assert not upgrader.is_newer("v1.9.0", "1.9.0")
    assert not upgrader.is_newer("v1.9", "1.9.0")  # 右补零后相等，不算更新
    assert not upgrader.is_newer("v1.8.9", "1.9.0")


GOOD_ZIP_URL = "https://github.com/Dunnnwei/123mshub/releases/download/v1.9.1/123mshub-native-v1.9.1-win64.zip"


def test_pick_asset_prefers_native_zip():
    release = {"assets": [
        {"name": "SHA256SUMS.txt", "url": "https://github.com/Dunnnwei/123mshub/releases/download/v1.9.1/SHA256SUMS.txt", "size": 100},
        {"name": "123mshub-native-v1.9.1-win64.zip", "url": GOOD_ZIP_URL, "size": 170},
    ]}
    assert upgrader.pick_asset(release)["url"] == GOOD_ZIP_URL
    # v1.9.1（审查 P0-1）：删除"最大 zip 兜底"——资产名不匹配发布惯例即拒绝，
    # 且下载地址必须是 GitHub 官方域 HTTPS。
    with pytest.raises(FetchError):
        upgrader.pick_asset({"assets": [
            {"name": "SHA256SUMS.txt", "url": "https://github.com/Dunnnwei/123mshub/releases/download/v1.9.1/SHA256SUMS.txt", "size": 100},
            {"name": "other.zip", "url": GOOD_ZIP_URL, "size": 500},
        ]})
    with pytest.raises(FetchError):
        upgrader.pick_asset({"assets": [{"name": "SHA256SUMS.txt", "url": "https://github.com/Dunnnwei/123mshub/releases/download/v1.9.1/SHA256SUMS.txt", "size": 1}]})


def _build_upgrade_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("123mshub/123mshub.exe", "new-exe")
        bundle.writestr("123mshub/_internal/app.py", "new-app")
        bundle.writestr("123mshub/_internal/data/flag.txt", "new-flag")


def test_apply_upgrade_overlays_and_counts(tmp_path: Path):
    install = tmp_path / "install"
    (install / "_internal").mkdir(parents=True)
    (install / "123mshub.exe").write_text("old-exe")
    (install / "_internal" / "app.py").write_text("old-app")
    archive = tmp_path / "pkg.zip"
    _build_upgrade_zip(archive)
    stats = upgrader.apply_upgrade(archive, install)
    assert stats["files"] == 3
    assert stats["renamed"] == 0  # 测试环境无文件锁，全部直接覆盖
    assert (install / "123mshub.exe").read_text() == "new-exe"
    assert (install / "_internal" / "app.py").read_text() == "new-app"
    assert (install / "_internal" / "data" / "flag.txt").read_text() == "new-flag"


def test_apply_upgrade_rejects_zip_slip(tmp_path: Path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as bundle:
        bundle.writestr("123mshub/../../escape.txt", "boom")
    with pytest.raises(FetchError):
        upgrader.apply_upgrade(evil, tmp_path / "install")


def test_cleanup_old_removes_stale_files(tmp_path: Path):
    stale = tmp_path / "123mshub.exe.mshub-old"
    stale.write_text("old")
    keep = tmp_path / "123mshub.exe"
    keep.write_text("new")
    assert upgrader.cleanup_old(tmp_path) == 1
    assert not stale.exists()
    assert keep.exists()


# ---- 需求 3：记忆条目硬删除（服务层） --------------------------------------

def _make_entry(facade: MemoryFacade, name: str) -> None:
    facade.create_entry({"name": name, "title": f"条目 {name}", "description": "描述",
                         "type": "reference", "tags": [], "body": "正文"})


def test_memory_soft_delete_keeps_trash(native_facade: MemoryFacade, tmp_path: Path):
    _make_entry(native_facade, "soft-note")
    result = native_facade.delete_entry("soft-note")
    assert result["deleted"] and not result["hard"]
    notes = native_facade.service._notes_dir()
    assert not (notes / "soft-note.md").exists()
    assert result["recovery_path"], "软删除必须给回收路径"


def test_memory_hard_delete_no_trash(native_facade: MemoryFacade):
    _make_entry(native_facade, "hard-note")
    _make_entry(native_facade, "stay-note")
    result = native_facade.delete_entry("hard-note", hard=True)
    assert result["deleted"] and result["hard"]
    assert result["recovery_path"] == ""
    notes = native_facade.service._notes_dir()
    assert not (notes / "hard-note.md").exists()
    assert (notes / "stay-note.md").exists()  # 只删目标
    trash = native_facade.service._trash_dir()
    assert not any(trash.rglob("hard-note.md")), "硬删除不得进入回收目录"
    assert "hard-note" not in [item["name"] for item in native_facade.list_entries()["items"]]


def test_memory_bulk_delete_hard(native_facade: MemoryFacade):
    for index in range(3):
        _make_entry(native_facade, f"bulk-{index}")
    result = native_facade.bulk_delete(["bulk-0", "bulk-1", "bulk-2"], hard=True)
    assert result["deleted"] == ["bulk-0", "bulk-1", "bulk-2"]
    assert not result["failed"]
    assert native_facade.list_entries()["items"] == []


# ---- 需求 6：Shift 连选状态机 ----------------------------------------------

class _RangeHost(ShiftRangeCheckMixin, QWidget):
    def __init__(self, rows: int = 6, parent=None):
        super().__init__(parent)
        self.boxes = [QCheckBox(self) for _ in range(rows)]
        self.ranges: list[tuple[int, int]] = []

    def _checkbox_at_row(self, row: int):
        return self.boxes[row] if 0 <= row < len(self.boxes) else None

    def _shift_range_applied(self, low: int, high: int) -> None:
        self.ranges.append((low, high))


def _press(host: _RangeHost, row: int, shift: bool) -> bool:
    modifiers = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, modifiers)
    return host.eventFilter(host.boxes[row], event)


def test_shift_range_selection(qapp):
    host = _RangeHost()
    for row in range(6):
        host._hook_shift_checkbox(host.boxes[row], row)
    assert _press(host, 1, shift=False) is False  # 普通点击只更新锚点
    assert host._shift_anchor == 1
    assert _press(host, 4, shift=True) is True    # Shift 连选拦截本次点击
    assert host.ranges == [(1, 4)]
    assert [box.isChecked() for box in host.boxes] == [False, True, True, True, True, False]
    # 锚点不因连选漂移：再 Shift 点第 5 行，区间仍是 1..5
    _press(host, 5, shift=True)
    assert host.ranges[-1] == (1, 5)
    assert all(box.isChecked() for box in host.boxes[1:6])


def test_shift_range_without_anchor_is_plain_click(qapp):
    host = _RangeHost()
    host._hook_shift_checkbox(host.boxes[0], 0)
    host._hook_shift_checkbox(host.boxes[3], 3)
    assert _press(host, 3, shift=True) is False   # 没有锚点：退化为普通点击
    assert host._shift_anchor == 3


# ---- 页面级 UI 回归 --------------------------------------------------------

def _window(qapp, tmp_path: Path):
    from mshub.native.main_window import MainWindow
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    window = MainWindow(MemoryFacade(store))
    return window


def test_settings_saved_status_royal_blue(qapp, tmp_path: Path):
    window = _window(qapp, tmp_path)
    try:
        page = window.settings_page
        page._set_status("设置已保存", emphasis=True)
        assert page.status.objectName() == "statusSaved"
        assert "QLabel#statusSaved" in DARK_QSS and "QLabel#statusSaved" in LIGHT_QSS
        page._set_status("保存失败：x")
        assert page.status.objectName() == "status"  # 非强调状态必须退出蓝样式
    finally:
        window.close()


def test_settings_page_has_upgrade_button(qapp, tmp_path: Path):
    window = _window(qapp, tmp_path)
    try:
        assert window.settings_page.upgrade_button.text() == "检查更新"
    finally:
        window.close()


def test_skills_page_batch_delete_and_hard_delete(qapp, tmp_path: Path):
    window = _window(qapp, tmp_path)
    try:
        page = window.skills_page
        assert page.batch_delete.text() == "批量删除"
        assert page.batch_delete.objectName() == "danger"
        assert hasattr(page, "hard_delete")
        assert page.shift_hint.text() == SHIFT_RANGE_HINT
        # Delete 键只在表格聚焦时触发（不抢输入框的 Delete）
        assert page._delete_shortcut.context() == Qt.ShortcutContext.WidgetShortcut
    finally:
        window.close()


def _owning_layout(root_layout, widget):
    """递归找出直接容纳 widget 的布局对象（布局项可能是子布局）。"""
    for index in range(root_layout.count() or 0):
        item = root_layout.itemAt(index)
        if item is None:
            continue
        if item.widget() is widget:
            return root_layout
        sub = item.layout()
        if sub is not None:
            found = _owning_layout(sub, widget)
            if found is not None:
                return found
    return None


def test_security_page_trust_and_layout(qapp, tmp_path: Path):
    window = _window(qapp, tmp_path)
    try:
        page = window.security_page
        assert page.trust_checked.text() == "信任选中"
        assert page.batch_delete.text() == "批量删除"
        assert page.shift_hint.text() == SHIFT_RANGE_HINT
        # v1.9.1（需求 B）：按钮行从 FlowLayout 改回 QHBoxLayout 横排靠左——
        # FlowLayout 挂进 QHBoxLayout 后布局协商异常实际渲染成竖排。
        # 按钮与「检查通过后不显示」勾选框同属一行，勾选框经 stretch 推到行尾靠右。
        layout = _owning_layout(page.layout(), page.hide_passed)
        assert layout is not None and layout.__class__.__name__ == "QHBoxLayout"
        bar = _owning_layout(page.layout(), page.batch)
        assert bar is layout, "按钮与勾选框应同在横向按钮行里"
        assert layout.itemAt(layout.count() - 1).widget() is page.hide_passed, "勾选框必须在行尾（靠右）"
        assert hasattr(page, "batch_trust_checked")
        assert page._delete_shortcut.context() == Qt.ShortcutContext.WidgetShortcut
    finally:
        window.close()


def test_memory_page_unified_buttons_and_hard_delete(qapp, tmp_path: Path):
    window = _window(qapp, tmp_path)
    try:
        page = window.memory_page
        # 需求 5：统计行不再是 #stat 胶囊样式，与技能仓库功能按钮视觉统一
        assert all(button.objectName() != "stat" for button in page.stat_buttons.values())
        assert not page.stat_buttons["total"].isFlat()
        # 需求 3：编辑器里有「删除」（彻底删除）按钮，且与软删除并排
        assert page.hard_delete_button.text() == "删除"
        assert page.hard_delete_button.objectName() == "danger"
        assert page.delete_button.text() == "软删除"
        # 需求 2：批量按钮改为「批量删除」
        labels = [b.text() for b in page.batch_bar.findChildren(QPushButton)]
        assert "批量删除" in labels and "批量软删除" not in labels
        assert page.shift_hint.text() == SHIFT_RANGE_HINT
        assert page._delete_shortcut.context() == Qt.ShortcutContext.WidgetShortcut
    finally:
        window.close()


def test_memory_page_shift_hooks_rows(qapp, tmp_path: Path):
    window = _window(qapp, tmp_path)
    try:
        page = window.memory_page
        for index in range(4):
            _make_entry(page.facade, f"shift-{index}")
        page.refresh_sync()
        assert len(page._row_checks) == 4
        host = page
        assert host._checkbox_at_row(2) is page._row_checks[2]
        _press_like = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1),
                                  Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                  Qt.KeyboardModifier.NoModifier)
        page.eventFilter(page._row_checks[0], _press_like)
        assert page._shift_anchor == 0
        shift_event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1),
                                  Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                  Qt.KeyboardModifier.ShiftModifier)
        assert page.eventFilter(page._row_checks[3], shift_event) is True
        assert all(box.isChecked() for box in page._row_checks)
    finally:
        window.close()


def test_env_check_message_mentions_full_package():
    # 非打包环境恒为 None；文案校验走源码文本（打包态在本机不可构造）
    import inspect
    from mshub.native import app as app_module
    assert upgrader or True
    source = inspect.getsource(app_module.missing_environment_text)
    assert app_module.missing_environment_text() is None  # 源码运行不弹缺环境
    assert "单一完整包" in source or "完整程序包" in inspect.getsource(app_module)
