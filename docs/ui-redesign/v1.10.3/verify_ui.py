"""Reproducible source UI evidence with synthetic rows and isolated config."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mshub.config import ConfigStore
from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"scope": "source Qt render; synthetic skills; isolated temporary config", "themes": {}}
    with tempfile.TemporaryDirectory(prefix="mshub-v1103-ui-") as folder:
        root = Path(folder)
        store = ConfigStore(root / "config")
        store.save({"repo_root": str(root / "repo"), "auto_check_updates": False})
        window = MainWindow(MemoryFacade(store))
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        window.resize(1440, 880)
        window.show()
        window.nav.setCurrentRow(2)
        QTest.qWait(600)
        page, table = window.skills_page, window.skills_page.table
        page._timer.stop()
        page.scope.invalidate("list")
        page.items = [
            {"name": f"UI-test-skill-{i:02d}", "provider": "local", "item_type": "skill",
             "description": "独立测试样例：检查表头、列分隔线、选择和列宽交互。",
             "security_status": "safe" if i % 2 else "unchecked", "tags": ["测试样例"],
             "updated_at": "2026-10-02T09:00:00", "library": ""}
            for i in range(1, 7)
        ]
        page._apply_rows()
        app.processEvents()
        for mode in ("light", "dark"):
            window.theme.apply(mode)
            app.processEvents()
            pixels = []
            window.nav.blockSignals(True)
            for selected in (False, True):
                for index in range(5):
                    window.nav.setCurrentRow(index if selected else (index + 1) % 5)
                    app.processEvents()
                    item = window.nav.item(index)
                    rect = window.nav.visualItemRect(item)
                    rect.setLeft(rect.left() + 12)
                    rect.setWidth(20)
                    rect.setTop(rect.center().y() - 10)
                    rect.setHeight(20)
                    with_icon = window.nav.viewport().grab(rect).toImage()
                    icon = QIcon(item.icon())
                    item.setIcon(QIcon())
                    without_icon = window.nav.viewport().grab(rect).toImage()
                    item.setIcon(icon)
                    changed = sum(with_icon.pixel(x, y) != without_icon.pixel(x, y)
                                  for y in range(with_icon.height()) for x in range(with_icon.width()))
                    assert changed > 20, (mode, index, selected, changed)
                    pixels.append({"item": index, "selected": selected, "changed_pixels": changed})
            window.nav.setCurrentRow(2)
            window.nav.blockSignals(False)
            app.processEvents()
            assert window.grab().save(str(output / f"skills-{mode}.png"))
            evidence["themes"][mode] = {"navigation_paint": pixels, "header_height": table.horizontalHeader().height()}

        drag_results = []
        selected_before = table.currentRow()
        for col in range(table.columnCount()):
            table.horizontalScrollBar().setValue(0 if col < 3 else table.horizontalScrollBar().maximum())
            app.processEvents()
            handle = table.column_handles[col]
            assert handle.isVisible(), col
            header = table.horizontalHeader()
            scroll_geometry = {"viewport_width": table.viewport().width(),
                               "section_end": header.sectionViewportPosition(col) + header.sectionSize(col) - 1,
                               "handle_x": handle.x() + handle.HIT_WIDTH // 2,
                               "scroll": table.horizontalScrollBar().value(),
                               "scroll_max": table.horizontalScrollBar().maximum()}
            assert scroll_geometry["handle_x"] == scroll_geometry["section_end"]
            assert 0 <= scroll_geometry["section_end"] < scroll_geometry["viewport_width"]
            y = (24, min(100, handle.height() - 2), handle.height() - 12)[col % 3]
            point = QPoint(handle.HIT_WIDTH // 2, y)
            target = handle.mapToGlobal(point) + QPoint(32, 0)
            before = table.columnWidth(col)
            QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=point)
            QTest.mouseMove(handle, handle.mapFromGlobal(target), delay=30)
            QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=handle.mapFromGlobal(target))
            app.processEvents()
            after = table.columnWidth(col)
            assert after >= before + 28, (col, before, after)
            assert table.currentRow() == selected_before
            assert not table.cellWidget(0, 0).isChecked()
            drag_results.append({"column": col, "y": y, "before": before, "after": after, **scroll_geometry})
        widths = [table.columnWidth(i) for i in range(7)]
        page._apply_rows()
        window.resize(1520, 920)
        window.theme.apply("light")
        app.processEvents()
        assert [table.columnWidth(i) for i in range(7)] == widths
        page._header_clicked(1)
        assert [item["name"] for item in page.items] == sorted(item["name"] for item in page.items)
        assert [table.columnWidth(i) for i in range(7)] == widths
        evidence["column_drags"] = drag_results
        evidence["preserves_widths_after_refresh_resize_theme_sort"] = True
        evidence["selected_row_and_checkbox_unchanged_by_drag"] = True
        evidence["device_pixel_ratio"] = window.devicePixelRatioF()
        evidence["platform"] = app.platformName()
        window.close()
        app.processEvents()
    (output / "source-ui-check.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


