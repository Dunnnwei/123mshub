"""Draft settings; probes run off-thread and credentials stay in ConfigStore."""
from pathlib import Path

from PySide6.QtCore import Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from .. import NATIVE_VERSION
from ..i18n import LanguageController, localize
from ..settings_service import detect_proxy, list_models, mask_secret, test_connection, validate_endpoint
from ..task_runner import RequestScope, TaskRunner
from ..widgets import button


class SettingsPage(QWidget):
    saved = Signal(object)
    statusMessage = Signal(str)
    importRequested = Signal(str)

    def __init__(self, facade, theme, runner=None, jobs=None, language=None, parent=None):
        super().__init__(parent)
        self.facade, self.theme, self.jobs = facade, theme, jobs
        self.runner = runner or TaskRunner(self)
        self.scope = RequestScope(self.runner, self)
        self.language_controller = language or LanguageController(self)
        self._clear_ai = self._clear_github = False
        self._build_ui()
        self.load_config()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 24)
        root.addWidget(QLabel("LOCAL CONFIGURATION", objectName="eyebrow"))
        root.addWidget(QLabel("设置", objectName="title"))
        root.addWidget(QLabel("配置目录固定为 %APPDATA%\\mshub；修改草稿不会立即生效。", objectName="muted"))
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        general = QWidget()
        form = QFormLayout(general)
        form.setVerticalSpacing(14)
        self.repo_edit = QLineEdit()
        repo = QHBoxLayout()
        repo.addWidget(self.repo_edit)
        repo.addWidget(button("选择…", self.choose_repo))
        form.addRow("仓库根目录", repo)
        self.memory_edit = QLineEdit()
        form.addRow("记忆库位置覆盖", self.memory_edit)
        self.fetcher = QComboBox()
        self.fetcher.addItems(["archive", "git"])
        form.addRow("抓取方式", self.fetcher)
        self.language = QComboBox()
        for text, value in [("跟随系统 / System", "system"), ("中文", "zh-CN"), ("English", "en")]:
            self.language.addItem(text, value)
        form.addRow("语言", self.language)
        self.theme_combo = QComboBox()
        for text, value in [("跟随系统", "system"), ("亮色", "light"), ("暗色", "dark")]:
            self.theme_combo.addItem(text, value)
        form.addRow("主题", self.theme_combo)
        self.proxy = QLineEdit()
        proxy = QHBoxLayout()
        proxy.addWidget(self.proxy)
        proxy.addWidget(button("只读检测", self.detect_proxy))
        form.addRow("代理", proxy)
        self.proxy_status = QLabel("", objectName="muted")
        form.addRow("检测结果", self.proxy_status)
        self.mirrors = QPlainTextEdit()
        self.mirrors.setMaximumHeight(90)
        self.mirrors.setPlaceholderText("每行一个镜像地址")
        form.addRow("镜像列表", self.mirrors)
        mirrors = QHBoxLayout()
        for value in ("https://ghproxy.link/", "https://ghfast.top/"):
            mirrors.addWidget(button(value, lambda _=False, v=value: self._append_mirror(v)))
        form.addRow("常用镜像", mirrors)
        self.tabs.addTab(general, "仓库与语言")

        ai = QWidget()
        form = QFormLayout(ai)
        form.setVerticalSpacing(14)
        self.ai_preset = QComboBox()
        self.ai_preset.addItem("自定义", None)
        names = ["OpenAI", "DeepSeek", "OpenRouter", "SiliconFlow", "GLM", "Aliyun BaiLian"]
        for name, preset in zip(names, self.facade.ai_presets()):
            self.ai_preset.addItem(name, preset)
        self.ai_preset.activated.connect(self.select_preset)
        form.addRow("供应商预设", self.ai_preset)
        self.ai_base_url = QLineEdit()
        self.ai_base_url.textChanged.connect(self._endpoint_changed)
        form.addRow("AI 接口地址", self.ai_base_url)
        self.ai_model = QComboBox()
        self.ai_model.setEditable(True)
        models = QHBoxLayout()
        models.addWidget(self.ai_model)
        self.models_button = button("拉取 /models", self.fetch_models)
        models.addWidget(self.models_button)
        form.addRow("AI 模型", models)
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        key = QHBoxLayout()
        key.addWidget(self.ai_key)
        self.test_button = button("测试连通", self.test_ai)
        key.addWidget(self.test_button)
        key.addWidget(button("清除已存密钥", self.clear_ai_key))
        form.addRow("AI 密钥", key)
        self.ai_status = QLabel("", objectName="muted")
        self.ai_status.setWordWrap(True)
        form.addRow("已存状态", self.ai_status)
        self.github_key = QLineEdit()
        self.github_key.setEchoMode(QLineEdit.EchoMode.Password)
        github = QHBoxLayout()
        github.addWidget(self.github_key)
        github.addWidget(button("清除已存 Token", self.clear_github_key))
        form.addRow("GitHub Token", github)
        self.github_status = QLabel("", objectName="muted")
        form.addRow("已存状态", self.github_status)
        form.addRow(QLabel("匿名访问可用，但更容易触发 GitHub 速率限制。", objectName="muted"))
        self.tabs.addTab(ai, "AI 与凭据")
        maintenance = QWidget()
        layout = QVBoxLayout(maintenance)
        self.heal_button = button("重新识别已同步条目", self.heal)
        layout.addWidget(self.heal_button)
        layout.addWidget(button("导入记忆技能库…", self.choose_import))
        layout.addWidget(button("打开仓库目录", self.open_repo))
        layout.addStretch()
        self.tabs.addTab(maintenance, "维护与导入")
        actions = QHBoxLayout()
        self.status = QLabel("", objectName="status")
        self.status.setWordWrap(True)
        actions.addWidget(self.status, 1)
        self.save_button = button("保存设置", self.save_config, primary=True)
        actions.addWidget(self.save_button)
        root.addLayout(actions)
        root.addWidget(QLabel(f"123 MSHub Native {NATIVE_VERSION}", objectName="muted"))

    def load_config(self):
        self.original = self.facade.config()
        config = self.original
        self.repo_edit.setText(config.repo_root)
        self.memory_edit.setText(config.memory_root_override)
        self.fetcher.setCurrentText(config.fetcher)
        self.language.setCurrentIndex(max(0, self.language.findData(config.language)))
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.theme.mode)))
        self.proxy.setText(config.proxy)
        self.mirrors.setPlainText("\n".join(config.mirrors))
        self.ai_base_url.setText(config.ai_base_url)
        self.ai_model.setCurrentText(config.ai_model)
        self.ai_key.clear()
        self.github_key.clear()
        self._clear_ai = self._clear_github = False
        self.ai_status.setText(mask_secret(self.facade.config_store.get_secret("ai_key")))
        self.github_status.setText(mask_secret(self.facade.config_store.get_secret("github_token")))
        localize(self)

    def _append_mirror(self, value):
        values = self.mirrors.toPlainText().splitlines()
        if value not in values:
            self.mirrors.setPlainText("\n".join([*values, value]))

    def choose_repo(self):
        value = QFileDialog.getExistingDirectory(self, "选择 123 MSHub 仓库", self.repo_edit.text())
        if value:
            self.repo_edit.setText(value)

    def select_preset(self, *_):
        preset = self.ai_preset.currentData()
        if preset:
            self.ai_base_url.setText(preset["base_url"])
            self.ai_model.setCurrentText(preset["model"])

    def _endpoint_changed(self):
        self.scope.invalidate("probe")
        self.scope.invalidate("models")
        if hasattr(self, "original") and self.ai_base_url.text().rstrip("/") != self.original.ai_base_url.rstrip("/"):
            self.ai_status.setText("地址已变化：请填写新接口密钥。保存时不沿用旧密钥。")
        if hasattr(self, "test_button"):
            self.test_button.setEnabled(True)
            self.models_button.setEnabled(True)

    def _draft_key(self):
        if self.ai_key.text().strip():
            return self.ai_key.text().strip()
        same = self.ai_base_url.text().strip().rstrip("/") == self.original.ai_base_url.rstrip("/")
        return self.facade.config_store.get_secret("ai_key") if same and not self._clear_ai else ""

    def clear_ai_key(self):
        self._clear_ai = True
        self.ai_key.clear()
        self.ai_status.setText("保存后清除已存密钥")

    def clear_github_key(self):
        self._clear_github = True
        self.github_key.clear()
        self.github_status.setText("保存后清除已存 Token")

    def detect_proxy(self):
        result = detect_proxy(self.proxy.text().strip())
        self.proxy_status.setText(result["detected"] or "未检测到代理；支持手动填写")
        if result["detected"]:
            self.proxy.setText(result["detected"])

    def test_ai(self):
        self.test_button.setEnabled(False)
        self.status.setText("正在测试草稿中的接口与模型…")
        def done(message):
            self.test_button.setEnabled(True)
            self.status.setText(message)
        self.scope.call("probe", test_connection, done, done, self.ai_base_url.text().strip(),
                        self._draft_key(), self.ai_model.currentText().strip())

    def fetch_models(self):
        self.models_button.setEnabled(False)
        current = self.ai_model.currentText()
        def done(models):
            self.ai_model.clear()
            self.ai_model.addItems(models)
            self.ai_model.setCurrentText(current)
            self.models_button.setEnabled(True)
            self.status.setText(f"读取到 {len(models)} 个模型，可下拉选择或手动填写。")
        def failed(message):
            self.models_button.setEnabled(True)
            self.status.setText(message)
        self.scope.call("models", list_models, done, failed, self.ai_base_url.text().strip(), self._draft_key())

    def heal(self):
        if self.jobs:
            self.jobs.submit("reconcile", "重新识别已同步条目", self.facade.rebuild)
            self.status.setText("已提交后台任务，完成后自动刷新列表。")

    def choose_import(self):
        path = QFileDialog.getExistingDirectory(self, "选择要导入的 Agent 工作目录", str(Path.home()))
        if path:
            self.importRequested.emit(path)

    def save_config(self):
        if self.jobs and any(j["status"] == "running" for j in self.jobs.list()):
            self.status.setText("请等待后台任务完成后保存设置，防止任务写入另一个仓库。")
            return
        try:
            base = self.ai_base_url.text().strip()
            validate_endpoint(base)
            updates = {"memory_root_override": self.memory_edit.text().strip(),
                "fetcher": self.fetcher.currentText(), "language": self.language.currentData(),
                "proxy": self.proxy.text().strip(), "mirrors": self.mirrors.toPlainText().splitlines(),
                "ai_base_url": base, "ai_model": self.ai_model.currentText().strip()}
            # Saving an unrelated draft must not persist a --repo session override.
            if self.repo_edit.text().strip() != self.original.repo_root:
                updates["repo_root"] = self.repo_edit.text().strip()
            if self.ai_key.text().strip():
                updates["ai_key"] = self.ai_key.text().strip()
            elif self._clear_ai or base.rstrip("/") != self.original.ai_base_url.rstrip("/"):
                updates["ai_key"] = ""
            if self.github_key.text().strip():
                updates["github_token"] = self.github_key.text().strip()
            elif self._clear_github:
                updates["github_token"] = ""
            config = self.facade.save_config(updates)
            self.theme.apply(self.theme_combo.currentData())
            self.language_controller.apply(config.language)
            self.load_config()
            self.status.setText("设置已保存")
            self.saved.emit(config)
            self.statusMessage.emit("设置已保存")
        except Exception as exc:
            self.status.setText(f"保存失败：{exc}")

    def open_repo(self):
        if self.repo_edit.text().strip():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.repo_edit.text().strip()))
