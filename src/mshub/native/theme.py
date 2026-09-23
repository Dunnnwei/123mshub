"""123UI v4.2 token translation for Qt Widgets."""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication


LIGHT_QSS = """
QWidget { background: #F7F5F2; color: #000A1E; font-family: 'Segoe UI', 'Microsoft YaHei'; font-size: 14px; }
QMainWindow { background: #F7F5F2; }
QFrame#sidebar { background: #EBE7E0; border-right: 1px solid #E8E4DC; }
QFrame#surface, QGroupBox { background: #FFFFFF; border: 1px solid #E8E4DC; border-radius: 16px; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox { background: #FFFFFF; color: #000A1E; border: 1px solid #D9D3C6; border-radius: 10px; padding: 8px 10px; selection-background-color: #CCDDFE; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 2px solid #0156FC; padding: 7px 9px; }
QPushButton { min-height: 38px; padding: 0 14px; border-radius: 10px; border: 1px solid #D9D3C6; background: #FFFFFF; color: #000A1E; }
QPushButton:hover { background: #F3F8FD; border-color: #0156FC; }
QPushButton:pressed { padding-top: 2px; }
QPushButton#primary { background: #0156FC; color: #FFFFFF; border-color: #0156FC; font-weight: 600; }
QPushButton#danger { color: #8C1D16; border-color: #E7A9A3; background: #FFF7F6; }
QListWidget { background: transparent; border: none; outline: none; padding: 8px; }
QListWidget::item { padding: 12px; border-radius: 10px; margin: 2px 0; }
QListWidget::item:hover { background: #FFFFFF; }
QListWidget::item:selected { background: #CCDDFE; color: #000A1E; }
QLabel#eyebrow { color: #0148D2; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#muted, QLabel#status { color: rgba(0, 10, 30, 0.62); }
QLabel#title { font-size: 28px; font-weight: 650; }
QToolTip { background: #000A1E; color: #FFFFFF; border: none; padding: 6px 8px; }
QScrollBar:vertical { width: 10px; background: transparent; }
QScrollBar::handle:vertical { background: #D9D3C6; border-radius: 5px; min-height: 24px; }
"""

DARK_QSS = """
QWidget { background: #030711; color: #FFFFFF; font-family: 'Segoe UI', 'Microsoft YaHei'; font-size: 14px; }
QMainWindow { background: #030711; }
QFrame#sidebar { background: #0C1730; border-right: 1px solid #1B2E55; }
QFrame#surface, QGroupBox { background: #0C1730; border: 1px solid #1B2E55; border-radius: 16px; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox { background: #0C1730; color: #FFFFFF; border: 1px solid #243862; border-radius: 10px; padding: 8px 10px; selection-background-color: #243862; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 2px solid #568EFD; padding: 7px 9px; }
QPushButton { min-height: 38px; padding: 0 14px; border-radius: 10px; border: 1px solid #243862; background: #0C1730; color: #FFFFFF; }
QPushButton:hover { background: #152344; border-color: #568EFD; }
QPushButton:pressed { padding-top: 2px; }
QPushButton#primary { background: #0156FC; color: #FFFFFF; border-color: #0156FC; font-weight: 600; }
QPushButton#danger { color: #FFA69E; border-color: rgba(255, 138, 128, 0.35); background: rgba(255, 138, 128, 0.1); }
QListWidget { background: transparent; border: none; outline: none; padding: 8px; }
QListWidget::item { padding: 12px; border-radius: 10px; margin: 2px 0; }
QListWidget::item:hover { background: rgba(255, 255, 255, 0.06); }
QListWidget::item:selected { background: rgba(86, 142, 253, 0.26); color: #FFFFFF; }
QLabel#eyebrow { color: #568EFD; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#muted, QLabel#status { color: rgba(255, 255, 255, 0.66); }
QLabel#title { font-size: 28px; font-weight: 650; }
QToolTip { background: #FFFFFF; color: #000A1E; border: none; padding: 6px 8px; }
QScrollBar:vertical { width: 10px; background: transparent; }
QScrollBar::handle:vertical { background: #243862; border-radius: 5px; min-height: 24px; }
"""


class ThemeController(QObject):
    changed = Signal(str)

    def __init__(self, settings: QSettings | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings or QSettings("123mshub", "123mshub")
        self.mode = str(self.settings.value("theme", "system"))

    @staticmethod
    def system_mode() -> str:
        app = QApplication.instance()
        hints = app.styleHints() if app is not None else None
        scheme = getattr(hints, "colorScheme", None)
        if callable(scheme):
            value = scheme()
            if str(value).lower().endswith("dark"):
                return "dark"
            if str(value).lower().endswith("light"):
                return "light"
        palette = QApplication.palette()
        return "dark" if palette.color(QPalette.ColorRole.Window).lightness() < 128 else "light"

    @property
    def effective_mode(self) -> str:
        return self.system_mode() if self.mode == "system" else self.mode

    def apply(self, mode: str | None = None) -> str:
        if mode is not None and mode in {"light", "dark", "system"}:
            self.mode = mode
            self.settings.setValue("theme", mode)
        effective = self.effective_mode
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(DARK_QSS if effective == "dark" else LIGHT_QSS)
        self.changed.emit(effective)
        return effective
