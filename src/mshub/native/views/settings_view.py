"""Native settings page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..memory_facade import MemoryFacade
from .. import NATIVE_VERSION
from ..theme import ThemeController


class SettingsPage(QWidget):
    saved = Signal(object)
    statusMessage = Signal(str)

    def __init__(self, facade: MemoryFacade, theme: ThemeController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.facade = facade
        self.theme = theme
        self._build_ui()
        self.load_config()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 24)
        root.setSpacing(18)
        eyebrow = QLabel("LOCAL CONFIGURATION")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("设置")
        title.setObjectName("title")
        subtitle = QLabel("配置仍由 %APPDATA%/123mshub 管理，原生壳不引入第二份数据格式。")
        subtitle.setObjectName("muted")
        root.addWidget(eyebrow)
        root.addWidget(title)
        root.addWidget(subtitle)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        repo_row = QHBoxLayout()
        self.repo_edit = QLineEdit()
        self.repo_edit.setPlaceholderText("选择已有技能/记忆仓库")
        browse = QPushButton("选择…")
        browse.clicked.connect(self.choose_repo)
        repo_row.addWidget(self.repo_edit, 1)
        repo_row.addWidget(browse)
        form.addRow("仓库根目录", repo_row)
        self.memory_edit = QLineEdit()
        self.memory_edit.setPlaceholderText("留空则使用 仓库根目录/memory")
        form.addRow("记忆库位置覆盖", self.memory_edit)
        self.language = QComboBox()
        self.language.addItem("跟随系统", "system")
        self.language.addItem("中文", "zh-CN")
        self.language.addItem("English", "en")
        form.addRow("语言", self.language)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("亮色", "light")
        self.theme_combo.addItem("暗色", "dark")
        form.addRow("主题", self.theme_combo)
        root.addLayout(form)

        self.ai_status = QLabel("")
        self.ai_status.setObjectName("muted")
        self.github_status = QLabel("")
        self.github_status.setObjectName("muted")
        root.addWidget(self.ai_status)
        root.addWidget(self.github_status)
        actions = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("status")
        actions.addWidget(self.status, 1)
        open_button = QPushButton("打开仓库目录")
        open_button.clicked.connect(self.open_repo)
        actions.addWidget(open_button)
        save_button = QPushButton("保存设置")
        save_button.setObjectName("primary")
        save_button.clicked.connect(self.save_config)
        actions.addWidget(save_button)
        root.addLayout(actions)
        root.addStretch(1)
        version = QLabel(f"原生壳 {NATIVE_VERSION} · 本地进程 · 不监听 TCP 端口")
        version.setObjectName("muted")
        root.addWidget(version)

    def load_config(self) -> None:
        try:
            config = self.facade.config()
        except Exception as exc:
            self.status.setText(f"配置读取失败：{exc}")
            return
        self.repo_edit.setText(config.repo_root)
        self.memory_edit.setText(config.memory_root_override)
        self.language.setCurrentIndex(max(0, self.language.findData(config.language)))
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.theme.mode)))
        self.ai_status.setText(f"AI 接口：{'已配置' if config.ai_key_configured else '未配置'}（地址 {config.ai_base_url}）")
        self.github_status.setText(f"GitHub Token：{'已配置' if config.github_token_configured else '未配置'}")

    def choose_repo(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择 123 MSHub 仓库", self.repo_edit.text() or str(Path.home()))
        if selected:
            self.repo_edit.setText(selected)

    def save_config(self) -> None:
        try:
            config = self.facade.save_config({
                "repo_root": self.repo_edit.text().strip(),
                "memory_root_override": self.memory_edit.text().strip(),
                "language": self.language.currentData() or "system",
            })
            mode = self.theme_combo.currentData() or "system"
            self.theme.apply(str(mode))
            self.load_config()
            self.status.setText("设置已保存")
            self.statusMessage.emit("设置已保存")
            self.saved.emit(config)
        except Exception as exc:
            self.status.setText(f"保存失败：{exc}")

    def open_repo(self) -> None:
        path = self.repo_edit.text().strip()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
