"""Column handles spanning the table viewport, including rows and empty space."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHeaderView, QTableWidget, QWidget

from .theme import current_palette


class _ColumnHandle(QWidget):
    HIT_WIDTH = 8

    def __init__(self, table, column):
        super().__init__(table.viewport())
        self.table, self.column = table, column
        self.dragging = False
        self.hovered = False
        self.setObjectName(f"columnResizeHandle{column}")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setCursor(Qt.CursorShape.SplitHCursor)
        self.setMouseTracking(True)
        self.setToolTip("拖动竖线调整列宽；双击竖线适应内容")

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.table.user_column_widths = True
            self._start_x = event.globalPosition().x()
            self._start_width = self.table.columnWidth(self.column)
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging:
            width = self._start_width + round(event.globalPosition().x() - self._start_x)
            self.table.setColumnWidth(self.column, max(self.table.horizontalHeader().minimumSectionSize(), width))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.dragging and event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.table.sync_column_handles()
            self.update()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.table.user_column_widths = True
            self.table.resizeColumnToContents(self.column)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        palette = current_palette()
        painter = QPainter(self)
        active = self.hovered or self.dragging
        # Handles remain full-height hit targets, but an idle handle is
        # invisible.  Drawing every boundary through a selected row made the
        # row look striped and confused the selection tint with a column cue.
        if active:
            painter.setPen(QPen(QColor(palette["accent"]), 2))
            painter.drawLine(self.HIT_WIDTH // 2, 0, self.HIT_WIDTH // 2, self.height())


class ResizableColumnsTable(QTableWidget):
    """Keep native headers/sorting; add full-height mouse targets for resizing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_column_widths = False
        self._header_pressed = False
        # Pixel scrolling keeps the right edge in sync while column widths
        # change; item scrolling can retain a stale offset at its maximum.
        self.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(56)
        header.setMinimumHeight(32)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.viewport().installEventFilter(self)
        self.column_handles = [_ColumnHandle(self, col) for col in range(self.columnCount())]
        header.sectionResized.connect(self._section_resized)
        header.geometriesChanged.connect(self.sync_column_handles)
        header.sectionMoved.connect(self.sync_column_handles)
        self.horizontalScrollBar().valueChanged.connect(self.sync_column_handles)

    def eventFilter(self, obj, event):
        if obj is self.horizontalHeader().viewport():
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._header_pressed = True
            elif event.type() in (QEvent.Type.MouseButtonRelease, QEvent.Type.UngrabMouse):
                self._header_pressed = False
            elif event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                self._header_pressed = True
        return super().eventFilter(obj, event)

    def _section_resized(self, *_):
        if self._header_pressed:
            self.user_column_widths = True
        self.sync_column_handles()

    def sync_column_handles(self, *_):
        header, viewport = self.horizontalHeader(), self.viewport()
        for handle in self.column_handles:
            col = handle.column
            # QHeaderView positions already include horizontal scrolling.
            boundary = header.sectionViewportPosition(col) + header.sectionSize(col) - 1
            visible = not self.isColumnHidden(col) and 0 <= boundary < viewport.width()
            handle.setGeometry(boundary - handle.HIT_WIDTH // 2, 0, handle.HIT_WIDTH, viewport.height())
            # Keep the mouse grab if a drag carries the boundary offscreen.
            handle.setVisible(visible or handle.dragging)
            handle.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "column_handles"):
            self.sync_column_handles()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if hasattr(self, "column_handles"):
            self.sync_column_handles()

    def setCellWidget(self, row, column, widget):
        super().setCellWidget(row, column, widget)
        # Checkbox cell widgets must not cover the resize target on their edge.
        self.sync_column_handles()
