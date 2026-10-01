"""Runtime branding shared by the shell, dialogs and frozen distribution."""
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import __version__


def icon_path(mode="light", *, series=False) -> Path:
    # The supplied identity is shared by both themes.  ICO contains 16–256px
    # frames so Qt and Windows can select the right size for each DPI surface.
    filename = "new123uilogo.ico" if series else "NEWmshublogo.ico"
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


def create_about_dialog(parent):
    from .i18n import localize
    dialog = QDialog(parent)
    dialog.setWindowTitle("关于 123 MSHub")
    dialog.resize(440, 330)
    root = QVBoxLayout(dialog)
    root.setContentsMargins(32, 32, 32, 24)
    logos = QHBoxLayout()
    logos.setSpacing(20)
    logos.addStretch()
    logo = QLabel(objectName="brandLogo")
    logo.setFixedSize(80, 80)
    logo.setPixmap(QIcon(str(icon_path())).pixmap(80, 80))
    logo.setAccessibleName("123 MSHub 标志")
    series_logo = QLabel(objectName="seriesLogo")
    series_logo.setFixedSize(80, 80)
    series_logo.setPixmap(QIcon(str(icon_path(series=True))).pixmap(80, 80))
    series_logo.setAccessibleName("123 系列工具标志")
    logos.addWidget(logo)
    logos.addWidget(series_logo)
    logos.addStretch()
    root.addLayout(logos)
    root.addWidget(QLabel("123系列工具", objectName="muted", alignment=Qt.AlignmentFlag.AlignCenter))
    title = QLabel(f"123 MSHub v{__version__}", objectName="title")
    root.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
    root.addWidget(QLabel("本地共享记忆与技能", alignment=Qt.AlignmentFlag.AlignCenter))
    close = QPushButton("关闭")
    close.clicked.connect(dialog.accept)
    root.addWidget(close)
    localize(dialog)
    return dialog


def show_about(parent):
    create_about_dialog(parent).exec()
