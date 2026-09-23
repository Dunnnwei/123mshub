"""Runtime branding shared by the shell, dialogs and frozen distribution."""
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QVBoxLayout

from .. import __version__


def icon_path(mode="light") -> Path:
    filename = "123mshublogohei.ico" if mode == "dark" else "123mshublogo.ico"
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "mshub/native/icons" / filename
    return Path(__file__).resolve().parents[3] / "packaging/native/icons" / filename


def apply_brand_icon(mode="light") -> QIcon:
    icon = QIcon(str(icon_path(mode)))
    app = QApplication.instance()
    app.setWindowIcon(icon)
    for window in app.topLevelWidgets():
        window.setWindowIcon(icon)
        for label in window.findChildren(QLabel, "brandLogo"):
            label.setPixmap(icon.pixmap(label.size()))
    return icon


def set_windows_app_id() -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Dunnnwei.123mshub")


def show_about(parent):
    from .i18n import localize
    dialog = QDialog(parent)
    dialog.setWindowTitle("关于 123 MSHub")
    dialog.resize(420, 300)
    root = QVBoxLayout(dialog)
    root.setContentsMargins(32, 32, 32, 24)
    logo = QLabel(objectName="brandLogo")
    logo.setFixedSize(80, 80)
    logo.setPixmap(QApplication.windowIcon().pixmap(80, 80))
    root.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)
    title = QLabel(f"123 MSHub v{__version__}", objectName="title")
    root.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
    root.addWidget(QLabel("本地共享记忆与技能", alignment=Qt.AlignmentFlag.AlignCenter))
    close = QPushButton("关闭")
    close.clicked.connect(dialog.accept)
    root.addWidget(close)
    localize(dialog)
    dialog.exec()
