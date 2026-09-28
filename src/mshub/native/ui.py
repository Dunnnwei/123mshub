"""Shared presentation controls for the MASTER design system; no service policy."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QBoxLayout, QComboBox, QDialog, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit, QPlainTextEdit,
    QCheckBox, QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTextEdit,
    QVBoxLayout, QWidget,
)


def show_toast(anchor: QWidget, text: str, duration_ms: int = 1500) -> None:
    """v1.7.5：小型「已复制」浮框——出现在触发按钮正下方，自动消失。

    QLabel 直接挂在窗口上、鼠标穿透、不抢焦点；固定深色圆角胶囊样式，
    亮暗主题下都可读。同页连续点击会先关上一个，不叠加。
    """
    window = anchor.window()
    old = window.findChild(QLabel, "mshubToast")
    if old is not None:
        old.close()
        old.deleteLater()
    toast = QLabel(text, window)
    toast.setObjectName("mshubToast")
    toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
    toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    toast.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    toast.setStyleSheet(
        "QLabel#mshubToast { background: rgba(23,27,35,.92); color:#FFFFFF;"
        " border-radius:14px; padding:7px 18px; font-size:13px; font-weight:600; }"
    )
    toast.adjustSize()
    top_left = anchor.mapTo(window, QPoint(anchor.width() // 2 - toast.width() // 2, anchor.height() + 8))
    toast.move(max(8, min(top_left.x(), window.width() - toast.width() - 8)), max(8, top_left.y()))
    toast.show()
    toast.raise_()
    QTimer.singleShot(duration_ms, toast.close)


def copy_agent_prompt(facade, button: QWidget, runner) -> None:
    """v1.7.5 起五页右上角「Agent连接提示词」共用的复制动作（注入提示词）；
    v1.8.0（审查 P0-2）：injection_prompt 要读全库统计，改走后台线程生成，
    回 GUI 线程再写剪贴板——大库不再冻结界面。成功弹「已复制」小框。"""
    from PySide6.QtWidgets import QApplication

    def ok(_identifier, payload) -> None:
        try:
            QApplication.clipboard().setText(str(payload))
        except Exception as exc:  # noqa: BLE001 - 剪贴板偶发占用
            show_toast(button, f"复制失败：{exc}")
            return
        show_toast(button, "已复制")

    def failed(_identifier, payload) -> None:
        message = payload.get("error") if isinstance(payload, dict) else payload
        show_toast(button, f"复制失败：{str(message)[:60]}")

    handle = runner.submit(facade.injection_prompt)
    handle.signals.finished.connect(ok)
    handle.signals.failed.connect(failed)


AGENT_PROMPT_BUTTON_TEXT = "Agent连接提示词"
AGENT_PROMPT_BUTTON_TIP = (
    "复制注入提示词：粘贴给你的 agent（对话首条消息或常驻配置），\n"
    "即赋予它读共享记忆、用共享技能库、投递新记忆的完整协议。"
)



def open_singleton_dialog(owner, attr: str, factory) -> "QDialog | None":
    """v1.8.0（审查 P2-4）：非模态弹窗统一"关旧开新"单实例策略。

    - 0.35s 防重入：itemActivated 与 itemDoubleClicked 双绑定时同一双击只开一窗
    - WA_DeleteOnClose + destroyed 身份判断：旧窗延迟销毁不会抹掉新窗引用
    - factory() 返回未 show 的 QDialog；引用挂在 owner.<attr> 上
    """
    import time

    now = time.monotonic()
    if now - getattr(owner, f"{attr}_last_open", 0.0) < 0.35:
        return None
    setattr(owner, f"{attr}_last_open", now)
    existing = getattr(owner, attr, None)
    if existing is not None:
        try:
            existing.close()
        except RuntimeError:
            pass  # C++ 对象已销毁
        setattr(owner, attr, None)
    dialog = factory()
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.destroyed.connect(lambda *_, d=dialog: getattr(owner, attr, None) is d and setattr(owner, attr, None))
    setattr(owner, attr, dialog)
    dialog.show()
    return dialog


class CheckableTableMixin:
    """v1.8.0（审查 P2-4）：「多选 + 表头排序」表格的公共状态机。

    技能仓库与安全中心原来各复制一份：表头第 0 列点击 = 全选/全取消，
    其余列点击 = 正/反序排序（表头箭头指示）。宿主需实现：
      _apply_sort(col, order)      —— 按列排序并重建行
      _after_select_all(target, count) —— 全选后写状态栏文案
    """

    def _header_clicked(self, col: int) -> None:
        if col == 0:
            checks = [self.table.cellWidget(row, 0) for row in range(self.table.rowCount())]
            checks = [check for check in checks if isinstance(check, QCheckBox)]
            if not checks:
                return
            target = not all(check.isChecked() for check in checks)
            for check in checks:
                check.setChecked(target)
            self._after_select_all(target, len(checks))
            return
        if getattr(self, "_sort_col", None) == col:
            self._sort_order = (Qt.SortOrder.DescendingOrder
                                if self._sort_order == Qt.SortOrder.AscendingOrder
                                else Qt.SortOrder.AscendingOrder)
        else:
            self._sort_col = col
            self._sort_order = Qt.SortOrder.AscendingOrder
        self.table.horizontalHeader().setSortIndicator(col, self._sort_order)
        self._apply_sort(col, self._sort_order)

def make_agent_prompt_button(parent: QWidget, clicked_slot) -> QPushButton:
    """v1.7.5：构造右上角皇家蓝「Agent连接提示词」按钮，保证五页样式文案一致。"""
    button = QPushButton(AGENT_PROMPT_BUTTON_TEXT, parent)
    button.setObjectName("primary")
    button.setToolTip(AGENT_PROMPT_BUTTON_TIP)
    button.clicked.connect(clicked_slot)
    return button


class FlowLayout(QLayout):
    """Wrap complete controls before truncating labels, including compact windows."""
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item): self._items.append(item)
    def count(self): return len(self._items)
    def itemAt(self, i): return self._items[i] if 0 <= i < len(self._items) else None
    def takeAt(self, i): return self._items.pop(i) if 0 <= i < len(self._items) else None
    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self._arrange(QRect(0, 0, width, 0), True)
    def sizeHint(self): return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            if not item.isEmpty(): size = size.expandedTo(item.minimumSize())
        return size

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, False)

    def _arrange(self, rect, test):
        x, y, height = rect.x(), rect.y(), 0
        for item in self._items:
            if item.isEmpty(): continue
            size = item.sizeHint()
            width = min(size.width(), rect.width())
            if x > rect.x() and x + width > rect.right() + 1:
                x, y, height = rect.x(), y + height + self.spacing(), 0
            if not test: item.setGeometry(QRect(QPoint(x, y), QSize(width, size.height())))
            x += width + self.spacing()
            height = max(height, size.height())
        return y + height - rect.y()


def flow_bar(parent=None):
    widget = QWidget(parent)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout = FlowLayout(widget)
    return widget, layout


class ElideLabel(QLabel):
    """Visible ellipsis with full text available to tooltip and accessibility."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)
        self.setAccessibleName(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.contentsRect().width())
        painter.drawText(self.contentsRect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)


class PageHeader(QWidget):
    def __init__(self, title, subtitle, parent=None, eyebrow=""):
        super().__init__(parent)
        self.row = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(16)
        self.words = QWidget()
        labels = QVBoxLayout(self.words)
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(6)
        if eyebrow:
            labels.addWidget(QLabel(eyebrow, objectName="eyebrow"))
        self.heading = QLabel(title, objectName="title")
        labels.addWidget(self.heading)
        self.description = QLabel(subtitle, objectName="muted")
        self.description.setWordWrap(True)
        labels.addWidget(self.description)
        self.row.addWidget(self.words, 1)
        self.actions_widget = QWidget()
        self.actions = QHBoxLayout(self.actions_widget)
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(8)
        self.row.addWidget(self.actions_widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.row.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 920 else QBoxLayout.Direction.LeftToRight)
        self.row.setAlignment(self.actions_widget, Qt.AlignmentFlag.AlignLeft if self.width() < 920 else Qt.AlignmentFlag.AlignVCenter)


class GuardedDialog(QDialog):
    """Keep a draft open when its owner rejects closing or Escape."""
    def __init__(self, parent, can_close):
        super().__init__(parent)
        self.can_close = can_close

    def reject(self):
        if self.can_close():
            super().reject()

    def closeEvent(self, event):
        if self.can_close():
            event.accept()
        else:
            event.ignore()


class AdaptivePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.layout():
            margin = 16 if self.width() < 900 else 28
            self.layout().setContentsMargins(margin, 24 if margin == 28 else 16, margin, 16)

    def showEvent(self, event):
        super().showEvent(event)


class DataTable(QTableWidget):
    """Native, keyboard-operable data rows with predictable compact columns."""
    def __init__(self, headers, kind, parent=None):
        super().__init__(0, len(headers), parent)
        self.kind = kind
        self.setHorizontalHeaderLabels(headers)
        self.setAccessibleName("技能仓库" if kind == "skills" else "安全中心")
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setMinimumWidth(0)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(52)
        self.verticalHeader().setMinimumSectionSize(52)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setMinimumSectionSize(32)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 900
        if self.kind == "skills":
            self.setColumnHidden(5, compact)
            self.setColumnHidden(6, compact)
            for col, width in ((0, 56), (1, max(190, min(270, int(self.width() * .25)))) , (2, 94), (4, 98), (5, 100), (6, 168)):
                self.setColumnWidth(col, width)
            self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        else:
            # v1.7.4：安全中心补"多选"列后整体右移——多选/名称/来源/状态/最近检查/摘要
            self.setColumnHidden(4, compact)
            for col, width in ((0, 56), (1, max(190, min(300, int(self.width() * .29)))), (2, 96), (3, 104), (4, 170)):
                self.setColumnWidth(col, width)
            self.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)


def scroll_form(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(widget)
    area.setMinimumWidth(0)
    return area


def label_controls(root):
    """Bind native form labels including compound rows; keep Qt semantics intact."""
    for form in root.findChildren(QFormLayout):
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(20)
        for row in range(form.rowCount()):
            label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field_item = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if not label_item or not field_item: continue
            label = label_item.widget()
            if not isinstance(label, QLabel): continue
            candidates = []
            def collect(item):
                if item.widget():
                    w = item.widget()
                    if isinstance(w, (QLineEdit, QComboBox, QPlainTextEdit, QTextEdit)): candidates.append(w)
                elif item.layout():
                    for i in range(item.layout().count()): collect(item.layout().itemAt(i))
            collect(field_item)
            for control in candidates:
                control.setAccessibleName(label.text())
                if hasattr(control, "placeholderText"):
                    control.setAccessibleDescription(control.placeholderText())
                control.setMinimumWidth(0)
            if candidates: label.setBuddy(candidates[0])
    for control in root.findChildren(QAbstractButton):
        if control.text() and not control.accessibleName(): control.setAccessibleName(control.text())
        control.setCursor(Qt.CursorShape.PointingHandCursor)
    for control in root.findChildren(QLineEdit):
        if not control.accessibleName() and control.placeholderText():
            control.setAccessibleName(control.placeholderText())


def prepare_dialog(dialog):
    dialog.setSizeGripEnabled(True)
    if dialog.layout():
        dialog.layout().setContentsMargins(24, 20, 24, 20)
        dialog.layout().setSpacing(12)
    label_controls(dialog)
    screen = dialog.screen()
    if screen:
        available = screen.availableGeometry()
        dialog.resize(min(dialog.width(), available.width() - 48), min(dialog.height(), available.height() - 64))
    return dialog
