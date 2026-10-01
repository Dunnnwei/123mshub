"""v1.10.2 regression checks for template navigation icons and column handles."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QIcon, QImage
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QCheckBox, QListWidget, QListWidgetItem

from mshub.native.main_window import _nav_icon
from mshub.native.shell_widgets import NavigationDelegate
from mshub.native.views.skill_view import _SkillTable


def _opaque_pixels(image) -> int:
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return sum(
        1
        for y in range(rgba.height())
        for x in range(rgba.width())
        if rgba.pixelColor(x, y).alpha() > 0
    )


def test_stitch_navigation_icons_have_visible_pixels(qapp) -> None:
    nav = QListWidget()
    nav.resize(236, 300)
    nav.setItemDelegate(NavigationDelegate(nav))
    keys = ("memory", "graph", "skills", "security", "settings")
    for key in keys:
        nav.addItem(QListWidgetItem(key))
    nav.show()
    try:
        for mode in ("light", "dark"):
            for row, key in enumerate(keys):
                item = nav.item(row)
                icon = _nav_icon(key, mode)
                assert not icon.isNull(), (mode, key)
                assert _opaque_pixels(icon.pixmap(20).toImage()) > 20, (mode, key)
                for selected in (False, True):
                    nav.setCurrentRow(row if selected else (row + 1) % 5)
                    item.setIcon(icon)
                    qapp.processEvents()
                    rect = nav.visualItemRect(item)
                    rect.setLeft(rect.left() + 12)
                    rect.setWidth(20)
                    rect.setTop(rect.center().y() - 10)
                    rect.setHeight(20)
                    rendered = nav.viewport().grab(rect).toImage()
                    item.setIcon(QIcon())
                    blank = nav.viewport().grab(rect).toImage()
                    # Test the delegate's actual paint path, not just the icon
                    # object: the previous alias-clearing bug only failed here.
                    changed = sum(rendered.pixel(x, y) != blank.pixel(x, y)
                                  for y in range(rendered.height()) for x in range(rendered.width()))
                    assert changed > 20, (mode, key, selected)
                    item.setIcon(icon)
    finally:
        nav.close()


def test_skill_table_has_full_height_interactive_handles_and_preserves_drag(qapp) -> None:
    table = _SkillTable(6, 7)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(44)
    check = QCheckBox()
    table.setCellWidget(0, 0, check)
    table.resize(1200, 420)
    table.show()
    qapp.processEvents()

    header = table.horizontalHeader()
    assert all(header.sectionResizeMode(col).name == "Interactive" for col in range(7))
    assert all(handle.isVisible() for handle in table.column_handles)

    clicked = QSignalSpy(table.cellClicked)
    for col in range(7):
        scrollbar = table.horizontalScrollBar()
        scrollbar.setValue(0 if col < 3 else scrollbar.maximum())
        qapp.processEvents()
        handle = table.column_handles[col]
        assert handle.isVisible(), col
        assert handle.height() == table.viewport().height()
        boundary = header.sectionViewportPosition(col) + header.sectionSize(col) - 1
        assert handle.x() + handle.HIT_WIDTH // 2 == boundary
        assert 0 <= boundary < table.viewport().width()
        before = table.columnWidth(col)
        # Exercise data rows and the empty area below them, including the last
        # column after horizontal scrolling and multiple preceding resizes.
        y = (20, 100, handle.height() - 12)[col % 3]
        point = QPoint(handle.HIT_WIDTH // 2, y)
        target = handle.mapToGlobal(point) + QPoint(48, 0)
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(handle, handle.mapFromGlobal(target), delay=30)
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=handle.mapFromGlobal(target))
        qapp.processEvents()
        assert table.columnWidth(col) >= before + 35, col

    assert table.user_column_widths is True
    assert clicked.count() == 0
    assert not check.isChecked()
    adjusted = [table.columnWidth(col) for col in range(7)]
    table.resize(1320, 420)
    qapp.processEvents()
    assert [table.columnWidth(col) for col in range(7)] == adjusted
    table.close()
