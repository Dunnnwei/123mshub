"""Shared rounded list table used by the skills and safety pages.

The memory page already has an inset header and a body that scrolls below it.
QTableWidget's built-in header paints inside the scroll area, which is why the
two older pages had square corners, a scrollbar running through the header and
the platform's selected-cell decoration.  This module keeps the existing
QTableWidget API while giving it the same visual contract as the memory list.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .theme import current_palette, system_font_family


SECONDARY_ROLE = Qt.ItemDataRole.UserRole + 10


class ListTableDelegate(QStyledItemDelegate):
    """Paint rows consistently and avoid the native selected-cell stripe."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font_family = system_font_family()

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        painter.save()
        tokens = current_palette()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect
        if selected:
            painter.fillRect(rect, QColor(tokens["selection"]))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            hover = QColor(tokens["action"])
            hover.setAlpha(18)
            painter.fillRect(rect, hover)
        # The memory rows use one quiet bottom rule rather than a grid or a
        # leading accent bar.  Drawing it per cell makes the rule continuous
        # even when a row contains a checkbox widget.
        painter.setPen(QPen(QColor(tokens["line"]), 1))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        value = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if not value:
            painter.restore()
            return
        margin = 10
        text_rect = rect.adjusted(margin, 3, -margin, -3)
        primary = QFont(self._font_family, 11)
        primary.setWeight(QFont.Weight.Normal)
        color = QColor(tokens["muted"])
        secondary = str(index.data(SECONDARY_ROLE) or "")
        if index.column() == 1 and secondary:
            primary.setPointSize(12)
            primary.setWeight(QFont.Weight.Bold)
            painter.setFont(primary)
            painter.setPen(QColor(tokens["ink"]))
            first = QRect(text_rect.left(), text_rect.top(), text_rect.width(), 18)
            painter.drawText(first, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, value)
            sub = QFont(self._font_family, 10)
            sub.setWeight(QFont.Weight.Normal)
            painter.setFont(sub)
            painter.setPen(color)
            second = QRect(text_rect.left(), text_rect.top() + 18, text_rect.width(), max(12, text_rect.height() - 18))
            painter.drawText(second, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, secondary)
        else:
            painter.setFont(primary)
            painter.setPen(color if index.column() != 1 else QColor(tokens["ink"]))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, value)
        painter.restore()


class ListTableCard(QFrame):
    """Rounded card with a fixed header above a scrolling QTableWidget."""

    def __init__(self, table: QTableWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.table = table
        self._syncing = True
        self._ready = False
        self.setObjectName("listCard")
        self.header = QHeaderView(Qt.Orientation.Horizontal, self)
        self.header.setObjectName("listHeaderView")
        self.header.setModel(table.model())
        self.header.setSectionsClickable(True)
        self.header.setSectionsMovable(False)
        self.header.setHighlightSections(False)
        self.header.setSortIndicatorShown(True)
        self.header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.header.setMinimumHeight(36)
        self.header.setFixedHeight(36)
        self.header.setStretchLastSection(False)
        self.header.sectionClicked.connect(self._forward_header_click)
        self.header.sectionResized.connect(self._external_section_resized)
        for column in range(table.columnCount()):
            if table.isColumnHidden(column):
                self.header.hideSection(column)

        internal = table.horizontalHeader()
        internal.hide()
        internal.sectionResized.connect(self._internal_section_resized)
        internal.sectionMoved.connect(lambda *_: self.sync_header())
        internal.sortIndicatorChanged.connect(self.header.setSortIndicator)
        table.horizontalScrollBar().valueChanged.connect(self.header.setOffset)
        table.installEventFilter(self)
        table.viewport().installEventFilter(self)
        table.setItemDelegate(ListTableDelegate(table))
        table.setStyleSheet(
            "QTableWidget { border: 0; border-radius: 0; background: transparent; "
            "alternate-background-color: transparent; selection-background-color: transparent; "
            "selection-color: palette(text); } "
            "QTableWidget::item:selected { background: transparent; border: 0; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(table, 1)
        QTimer.singleShot(0, self._finish_initialization)

    def _finish_initialization(self) -> None:
        self.sync_header()
        self._ready = True

    def _forward_header_click(self, section: int) -> None:
        self.table.horizontalHeader().sectionClicked.emit(section)

    def _external_section_resized(self, logical: int, old: int, new: int) -> None:
        if self._syncing or not self._ready:
            return
        # Resizing through the visible header is the same user action as
        # dragging a column handle on the table itself.  Preserve that choice
        # through subsequent page resizes and theme changes.
        if hasattr(self.table, "user_column_widths"):
            self.table.user_column_widths = True
        self.table.setColumnWidth(logical, new)

    def _internal_section_resized(self, logical: int, _old: int, _new: int) -> None:
        if not self._syncing:
            self.sync_header()

    def sync_header(self) -> None:
        if not self.header or not self.table:
            return
        self._syncing = True
        try:
            self.header.setOffset(self.table.horizontalHeader().offset())
            for col in range(self.table.columnCount()):
                self.header.setSectionHidden(col, self.table.isColumnHidden(col))
                width = self.table.columnWidth(col)
                if self.header.sectionSize(col) != width:
                    self.header.resizeSection(col, width)
            self.header.setFixedWidth(max(0, self.table.viewport().width()))
        finally:
            self._syncing = False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, self.sync_header)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self.sync_header)
