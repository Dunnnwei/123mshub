"""Render the v1.11.0 native list states for the review record.

This is an isolated Qt render with synthetic rows. It is deliberately kept
separate from the real-repository Windows smoke check.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade
from mshub.native.views.skill_view import MetadataDialog


HERE = Path(__file__).resolve().parent


def row(name: str, status: str) -> dict:
    return {
        "name": name,
        "library": "skills",
        "provider": "github",
        "security_status": status,
        "updated_at": "2026-10-02T12:30:00",
        "description": f"English description for {name}",
        "description_zh": "用于检查名称和说明双行、标签摘要及平面表格卡。",
        "tags": ["agent", "review", "demo"],
        "local_dir": f"skills/{name}",
        "source_url": f"https://github.com/demo/{name}",
    }


def settle(app: QApplication) -> None:
    for _ in range(10):
        app.processEvents()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MemoryFacade())
    window.resize(1280, 820)
    rows = [row("alpha", "unchecked"), row("beta", "warning"), row("gamma", "safe")]
    window.skills_page.items = rows
    window.skills_page._apply_rows()
    window.security_page._apply({"items": rows})
    window.show()
    for mode in ("light", "dark"):
        window.theme.apply(mode)
        for index, name in ((2, "skills"), (3, "security")):
            window.nav.setCurrentRow(index)
            settle(app)
            window.grab().save(str(HERE / f"{mode}-{name}.png"))
        window.nav.setCurrentRow(2)
        settle(app)
        page = window.skills_page
        page._rich_tooltip.show(
            "标签：agent、review、demo\n说明：用于检查名称和说明双行、标签摘要及平面表格卡。",
            window.mapToGlobal(QPoint(760, 420)),
        )
        settle(app)
        if page._rich_tooltip._tip is not None:
            page._rich_tooltip._tip.grab().save(str(HERE / f"{mode}-tooltip.png"))
        page._rich_tooltip.hide()
    editor = MetadataDialog(window.skills_page, rows[0])
    editor.show()
    settle(app)
    editor.grab().save(str(HERE / "editor-layout.png"))
    editor.close()
    window.close()


if __name__ == "__main__":
    main()



