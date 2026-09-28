"""Draft settings; probes run off-thread and credentials stay in ConfigStore."""
from pathlib import Path

from PySide6.QtCore import Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget,
    QVBoxLayout, QWidget, QFrame)

from .. import NATIVE_VERSION
from ..i18n import LanguageController, localize
from ..settings_service import detect_proxy, list_models, mask_secret, test_connection, validate_endpoint
from ..task_runner import RequestScope, TaskRunner
from ..widgets import button
from ..ui import AdaptivePage, copy_agent_prompt, label_controls, make_agent_prompt_button, scroll_form


class SettingsPage(AdaptivePage):
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
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(16)
        root.addWidget(QLabel("本地配置", objectName="eyebrow"))
        root.addWidget(QLabel("设置选项", objectName="title"))
        root.addWidget(QLabel("配置目录固定为 %APPDATA%\\mshub；修改草稿不会立即生效。", objectName="muted"))
        # v1.6.0："关于 123 MSHub"从导航栏移到设置页
        # v1.7.5：右上角统一「Agent连接提示词」皇家蓝按钮（最右），关于按钮在其左
        about_row = QHBoxLayout()
        about_row.addStretch()
        about_btn = QPushButton("关于 123 MSHub")
        about_btn.clicked.connect(lambda: self._show_about())
        about_row.addWidget(about_btn)
        self.agent_button = make_agent_prompt_button(self, self.copy_prompt)
        about_row.addWidget(self.agent_button)
        root.addLayout(about_row)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("设置分类")
        self.tabs.setUsesScrollButtons(True)
        root.addWidget(self.tabs, 1)
        general = QWidget()
        form = QFormLayout(general)
        form.setVerticalSpacing(14)
        self.repo_edit = QLineEdit()
        repo = QHBoxLayout()
        repo.addWidget(self.repo_edit)
        repo.addWidget(button("选择…", self.choose_repo))
        form.addRow("仓库根目录", repo)
        # v1.7.2：记忆库位置覆盖补悬停注解（用户反馈看不出这个字段做什么用）
        self.memory_edit = QLineEdit()
        memory_tip = (
            "默认记忆存放在「仓库根目录\\memory」下。\n"
            "如需把记忆库放到其他位置（例如另一块盘或别的同步目录），"
            "在此填写该目录的完整路径；留空表示使用默认位置。\n"
            "修改后需点「保存设置」生效。"
        )
        self.memory_edit.setToolTip(memory_tip)
        memory_label = QLabel("记忆库位置覆盖")
        memory_label.setToolTip(memory_tip)
        form.addRow(memory_label, self.memory_edit)
        # v1.7.2：抓取方式改为中文可读选项（数据值仍是 archive/git，存量配置无缝兼容），
        # 字段名改为"技能下载方式"并补悬停注解
        self.fetcher = QComboBox()
        for text, value in (("ZIP 压缩包（免装 Git）", "archive"), ("Git 克隆（保留完整历史）", "git")):
            self.fetcher.addItem(text, value)
        fetcher_tip = (
            "从 GitHub 获取技能/程序文件的方式：\n"
            "ZIP 压缩包——下载仓库打包快照，速度快、无需安装 Git，但没有提交历史；\n"
            "Git 克隆——完整克隆仓库，保留提交历史、可增量更新，需要本机已安装 Git。"
        )
        self.fetcher.setToolTip(fetcher_tip)
        fetcher_label = QLabel("技能下载方式")
        fetcher_label.setToolTip(fetcher_tip)
        form.addRow(fetcher_label, self.fetcher)
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
        self.tabs.addTab(scroll_form(general), "仓库与语言")

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
        # v1.8.0（审查 M-2）：钥匙串不可用（密钥仅存内存）时醒目提示
        self.secrets_backend_label = QLabel("", objectName="error")
        self.secrets_backend_label.setWordWrap(True)
        form.addRow("密钥保存方式", self.secrets_backend_label)
        self.github_key = QLineEdit()
        self.github_key.setEchoMode(QLineEdit.EchoMode.Password)
        github = QHBoxLayout()
        github.addWidget(self.github_key)
        github.addWidget(button("清除已存 Token", self.clear_github_key))
        form.addRow("GitHub Token", github)
        self.github_status = QLabel("", objectName="muted")
        form.addRow("已存状态", self.github_status)
        form.addRow(QLabel("匿名访问可用，但更容易触发 GitHub 速率限制。", objectName="muted"))
        self.tabs.addTab(scroll_form(ai), "AI 与凭据")
        maintenance = QWidget()
        layout = QVBoxLayout(maintenance)
        self.heal_button = button("重新识别已同步条目", self.heal)
        layout.addWidget(self.heal_button)
        layout.addWidget(button("导入记忆技能库…", self.choose_import))
        layout.addWidget(button("打开仓库目录", self.open_repo))
        # v1.7.4：快速重置入口——换仓库 / 重新导入新仓库时不必手工清理
        reset_line = QFrame()
        reset_line.setObjectName("line")
        reset_line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(reset_line)
        self.detach_repo_button = button("清除仓库数据保留配置", self.clear_repo_data)
        self.detach_repo_button.setObjectName("danger")
        self.detach_repo_button.setToolTip(
            "解除当前仓库的关联：清空「仓库根目录」和「记忆库位置覆盖」设置，\n"
            "API 密钥、语言、主题等配置保留。\n仓库里已有的数据与文件不会被删除。"
        )
        layout.addWidget(self.detach_repo_button)
        self.clear_all_button = button("清除所有配置", self.clear_all_settings)
        self.clear_all_button.setObjectName("danger")
        self.clear_all_button.setToolTip(
            "清空全部配置：仓库路径、API 密钥、语言、界面偏好都恢复初始状态。\n"
            "仓库里已有的数据与文件不会被删除。"
        )
        layout.addWidget(self.clear_all_button)
        reset_note = QLabel(
            "说明：「清除所有配置」和「清除仓库数据保留配置」都不会删除仓库里已有的数据和文件；\n"
            "清除后再使用时，需要重新导入或重新指定仓库路径；「清除所有配置」还需重新配置 AI 接口调用。\n"
            "适用于快速重新导入新仓库、或更换导入新的仓库数据。"
        )
        reset_note.setObjectName("muted")
        reset_note.setWordWrap(True)
        layout.addWidget(reset_note)
        layout.addStretch()
        self.tabs.addTab(scroll_form(maintenance), "维护与导入")
        actions = QHBoxLayout()
        self.status = QLabel("", objectName="status")
        self.status.setWordWrap(True)
        actions.addWidget(self.status, 1)
        self.save_button = button("保存设置", self.save_config, primary=True)
        actions.addWidget(self.save_button)
        root.addLayout(actions)
        root.addWidget(QLabel(f"123 MSHub Native {NATIVE_VERSION}", objectName="muted"))
        label_controls(self)

    def _show_about(self):
        """v1.6.0：显示"关于"对话框（从导航栏移到设置页）"""
        from ..branding import show_about
        show_about(self)

    def load_config(self):
        self.original = self.facade.config()
        config = self.original
        self.repo_edit.setText(config.repo_root)
        self.memory_edit.setText(config.memory_root_override)
        self.fetcher.setCurrentIndex(max(0, self.fetcher.findData(config.fetcher)))
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
        backend = str(getattr(config, "secrets_backend", "keyring") or "keyring")
        self.secrets_backend_label.setText(
            "⚠ 系统钥匙串不可用：密钥仅保存在内存，重启后需重新填写" if backend == "memory" else ""
        )
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
            self.jobs.submit("reconcile", "识别条目", self.facade.rebuild)
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
                "fetcher": self.fetcher.currentData() or "archive", "language": self.language.currentData(),
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

    def copy_prompt(self):
        """v1.7.5：设置页右上角「Agent连接提示词」。"""
        copy_agent_prompt(self.facade, self.agent_button, self.runner)

    def _jobs_running(self) -> bool:
        return bool(self.jobs and any(job["status"] == "running" for job in self.jobs.list()))

    def clear_repo_data(self):
        """v1.7.4：清除仓库数据（保留配置）——解除仓库关联，仓库文件原样保留。

        用户诉求：已导入仓库后无法清空重来。这里只清「仓库根目录 / 记忆库
        位置覆盖」两个关联设置，API 密钥、语言等全部保留；仓库里的数据与
        文件一个不动。再次使用时重新指定仓库路径或重新导入即可。
        """
        if self._jobs_running():
            self.status.setText("请等待后台任务完成后再清除仓库数据。")
            return
        asked = QMessageBox.question(self, "清除仓库数据", (
            "解除当前仓库的关联？\n\n"
            "· 仓库根目录与记忆库位置设置将被清空（列表立即无数据）；\n"
            "· API 密钥、语言、主题等配置保留；\n"
            "· 仓库里已有的数据与文件不会被删除。\n"
            "再次使用时需重新导入或重新指定仓库路径。"
        ))
        if asked != QMessageBox.StandardButton.Yes:
            return
        try:
            config = self.facade.save_config({"repo_root": "", "memory_root_override": ""})
            self.load_config()
            self.status.setText("已解除仓库关联：请重新指定仓库路径或重新导入新仓库。")
            self.statusMessage.emit("已清除仓库数据（配置保留）")
            self.saved.emit(config)
        except Exception as exc:
            self.status.setText(f"清除仓库数据失败：{exc}")

    def clear_all_settings(self):
        """v1.7.4：清除所有配置——恢复出厂状态，仓库文件与数据不删。

        覆盖 config.json 全部字段（含删除钥匙串里的 API 密钥与 GitHub
        Token）和 native-ui.ini 界面偏好（主题/侧栏宽/编辑器几何/引导抑制）。
        """
        if self._jobs_running():
            self.status.setText("请等待后台任务完成后再清除配置。")
            return
        asked = QMessageBox.question(self, "清除所有配置", (
            "确认清除全部配置？\n\n"
            "· 仓库路径、API 密钥、语言、界面偏好等全部恢复初始；\n"
            "· 仓库里已有的数据与文件不会被删除；\n"
            "· 再次使用时需重新导入或重新指定仓库路径，并重新配置 AI 接口。"
        ))
        if asked != QMessageBox.StandardButton.Yes:
            return
        try:
            config = self.facade.save_config({
                "repo_root": "", "memory_root_override": "", "mirrors": [], "proxy": "",
                "fetcher": "archive", "language": "system",
                "ai_base_url": "https://api.openai.com/v1", "ai_model": "gpt-4.1-mini",
                "ai_key": "", "github_token": "",
            })
            (self.facade.config_store.config_dir / "native-ui.ini").unlink(missing_ok=True)
            self.theme.apply("system")
            self.language_controller.apply("system")
            self.load_config()
            self.status.setText("已清除所有配置：请重新指定仓库路径并配置 AI 接口。")
            self.statusMessage.emit("已清除所有配置")
            self.saved.emit(config)
        except Exception as exc:
            self.status.setText(f"清除配置失败：{exc}")
