"""Small native shell visuals; business state stays with the existing pages."""
from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from .theme import TYPOGRAPHY, current_palette, system_font_family


NAV_COUNT_ROLE = Qt.ItemDataRole.UserRole + 2


class NavigationDelegate(QStyledItemDelegate):
    """Keep native item selection/localization and draw a separate total column."""

    def sizeHint(self, option, index):
        return QSize(180, 44)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # PySide exposes opt.icon by reference: clearing it also clears aliases.
        # Keep an explicit value copy before asking the style to draw the row.
        label, icon = opt.text, QIcon(opt.icon)
        opt.text = ""
        opt.icon = QIcon()
        opt.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        palette = current_palette()
        content = option.rect.adjusted(12, 0, -12, 0)
        painter.save()
        icon_rect = QRect(content.left(), content.center().y() - 10, 20, 20)
        icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter, icon.Mode.Selected if selected else icon.Mode.Normal)
        count = index.data(NAV_COUNT_ROLE)
        count_width = 34 if count is not None else 0
        font = QFont(system_font_family())
        font.setPixelSize(TYPOGRAPHY["nav"])
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(palette["accent"] if selected else palette["ink"]))
        text_rect = content.adjusted(30, 0, -count_width, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, text_rect.width()))
        if count is not None:
            font.setPixelSize(TYPOGRAPHY["count"])
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(content, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, str(count))
        painter.restore()


class TaskActivityIcon(QWidget):
    """Template's three-part donut_small: 10s rotation while jobs are running."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("jobActivityIcon")
        self.setFixedSize(18, 18)
        self.setAccessibleName("后台任务状态")
        self.angle = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._advance)

    def set_running(self, running: bool):
        if running:
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()
            self.angle = 0.0
            self.update()
        self.setAccessibleDescription("后台任务运行中" if running else "后台任务已停止")

    def _advance(self):
        self.angle = (self.angle + 1.44) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(9, 9)
        painter.rotate(self.angle)
        painter.setPen(QPen(QColor(current_palette()["action"]), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        ring = QRectF(-5.5, -5.5, 11, 11)
        for start, length in ((96, 168), (6, 78), (276, 78)):
            painter.drawArc(ring, start * 16, length * 16)
        painter.end()
