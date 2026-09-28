"""Main native window and navigation shell."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QByteArray, QSize, Qt, QSettings, QTimer
from PySide6.QtGui import QColor, QFont, QFontInfo, QIcon, QPainter, QPixmap, QKeySequence, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QHeaderView,
    QVBoxLayout,
    QWidget,
    QToolButton,
    QDockWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QSizePolicy,
)

from .memory_facade import MemoryFacade
from .state import AppState
from .task_runner import TaskRunner
from .job_controller import JobController
from .theme import PALETTES, ThemeController, ensure_brand_fonts
from .i18n import LanguageController, localize
from .branding import apply_brand_icon, show_about
from .ui import label_controls
from .. import __version__
if TYPE_CHECKING:
    from .views.graph_view import GraphView
from .views.memory_view import MemoryPage
from .views.settings_view import SettingsPage
from .views.skill_view import SkillsPage, SecurityPage
from .views.import_view import ImportDialog


_NAV_SVGS = {
    "memory": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 5.5h16v13H4z" fill="none" stroke="COLOR" stroke-width="1.8" stroke-linejoin="round"/><path d="M8 5.5v13M8 9h8M8 13h8M8 17h5" fill="none" stroke="COLOR" stroke-width="1.8" stroke-linecap="round"/></svg>',
    "graph": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="6" cy="7" r="2.3" fill="none" stroke="COLOR" stroke-width="1.8"/><circle cx="18" cy="5" r="2.3" fill="none" stroke="COLOR" stroke-width="1.8"/><circle cx="17" cy="18" r="2.3" fill="none" stroke="COLOR" stroke-width="1.8"/><path d="m8 7 7.7-1.5M7.3 8.8l8.4 7.3M17.8 7.2l-.6 8.5" fill="none" stroke="COLOR" stroke-width="1.8" stroke-linecap="round"/></svg>',
    "skills": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4.5 8.5h5l1.5 2h8.5v8.5h-15z" fill="none" stroke="COLOR" stroke-width="1.8" stroke-linejoin="round"/><path d="M4.5 8.5V6.8c0-1 .8-1.8 1.8-1.8h4.2l1.5 2h5.7c1 0 1.8.8 1.8 1.8v1.7" fill="none" stroke="COLOR" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "security": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3.8 19 6.5v5.2c0 4.1-2.8 7.3-7 8.5-4.2-1.2-7-4.4-7-8.5V6.5z" fill="none" stroke="COLOR" stroke-width="1.8" stroke-linejoin="round"/><path d="m8.5 12 2.2 2.2 4.8-4.8" fill="none" stroke="COLOR" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "settings": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="COLOR" stroke-width="1.8" stroke-linecap="round"/><circle cx="9" cy="7" r="2" fill="none" stroke="COLOR" stroke-width="1.8"/><circle cx="15" cy="12" r="2" fill="none" stroke="COLOR" stroke-width="1.8"/><circle cx="11" cy="17" r="2" fill="none" stroke="COLOR" stroke-width="1.8"/></svg>',
}


def _nav_icon(key: str, mode: str) -> QIcon:
    icon = QIcon()
    source = _NAV_SVGS[key]
    for icon_mode, color in ((QIcon.Mode.Normal, PALETTES[mode]["ink"]), (QIcon.Mode.Selected, "#FFFFFF")):
        renderer = QSvgRenderer(QByteArray(source.replace("COLOR", color).encode("utf-8")))
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap, icon_mode)
    return icon


class _PlaceholderPage(QWidget):
    def __init__(self, title: str, detail: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        eyebrow = QLabel("NATIVE ROADMAP")
        eyebrow.setObjectName("eyebrow")
        heading = QLabel(title)
        heading.setObjectName("title")
        message = QLabel(detail)
        message.setObjectName("muted")
        message.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(heading)
        layout.addWidget(message)
        layout.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(self, facade: MemoryFacade | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"123 MSHub v{__version__}")
        self.setMinimumSize(960, 640)
        self.resize(1280, 820)
        self.facade = facade or MemoryFacade()
        self.runner = TaskRunner(self)
        self.jobs = JobController(self)
        self.language = LanguageController(self)
        self.state = AppState(self)
        self.theme = ThemeController(QSettings(str(self.facade.config_store.config_dir / "native-ui.ini"), QSettings.Format.IniFormat), parent=self)
        self._build_ui()
        self.theme.changed.connect(self._theme_changed)
        self.theme.apply()
        self.language.apply(self.facade.config().language)

    def _build_ui(self) -> None:
        container = QWidget()
        outer = QHBoxLayout(container)
        # v1.7.4：侧边栏改浮动面板——四边 16px 外边距；侧栏与内容区的 16px
        # 间隙由 splitter 把手宽度提供（把手已透明化）。圆角 20 在 theme.py。
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(176)
        # v1.7.2：上限从 236 放宽，配合 QSplitter 支持鼠标拖宽侧栏
        self.sidebar.setMaximumWidth(560)
        # v1.7.4：柔和低透明度投影（QSS 不支持 box-shadow，用图形效果实现）
        self.sidebar_shadow = QGraphicsDropShadowEffect(self.sidebar)
        self.sidebar_shadow.setBlurRadius(32)
        self.sidebar_shadow.setOffset(0, 6)
        self.sidebar.setGraphicsEffect(self.sidebar_shadow)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 26, 16, 20)
        self.brand_label = QLabel("123 MSHub", objectName="brandName")
        self.brand_label.setAccessibleName("123 MSHub")
        self.brand_label.setFont(QFont(ensure_brand_fonts(), 20, 900))
        self.brand_subtitle = QLabel("本地共享记忆与技能")
        self.brand_subtitle.setObjectName("muted")
        self.brand_logo = QLabel(objectName="brandLogo")
        self.brand_logo.setFixedSize(36, 36)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(6)
        brand_row.addWidget(self.brand_logo)
        brand_row.addWidget(self.brand_label, 1)
        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addWidget(self.brand_subtitle)
        sidebar_layout.addSpacing(22)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setAccessibleName("主导航")
        self.nav.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.nav.setFont(QFont(ensure_brand_fonts(), 15, 693))
        self.nav.setIconSize(QSize(20, 20))
        # 123UI outline icons with normal/selected theme tints.
        for label, key in (
            ("记忆仓库", "memory"),
            ("记忆图示", "graph"),
            ("技能仓库", "skills"),
            ("安全中心", "security"),
            ("设置选项", "settings"),
        ):
            row = QListWidgetItem(label)
            row.setData(Qt.ItemDataRole.UserRole, key)
            row.setData(Qt.ItemDataRole.UserRole + 1, key)
            row.setIcon(_nav_icon(key, self.theme.effective_mode))
            self.nav.addItem(row)
        self.nav.currentRowChanged.connect(self._navigate)
        sidebar_layout.addWidget(self.nav, 1)
        # v1.6.0：后台任务移到导航栏下半部分（原来在底部 dock 太矮看不清）
        self.job_panel = QFrame()
        self.job_panel.setObjectName("jobPanel")
        job_layout = QVBoxLayout(self.job_panel)
        job_layout.setContentsMargins(0, 12, 0, 0)
        job_layout.setSpacing(6)
        self._jobs_collapsed = False
        job_header = QHBoxLayout()
        # v1.7.2：标题字号 14px ≥「收起/展开」按钮（13px），原来用 eyebrow 只有 11px 反而更小
        job_title = QLabel("后台任务")
        job_title.setObjectName("jobTitle")
        job_header.addWidget(job_title)
        job_header.addStretch()
        self.job_toggle = QToolButton()
        self.job_toggle.setText("收起")
        self.job_toggle.setCheckable(True)
        self.job_toggle.setAccessibleName("展开或收起后台任务")
        self.job_toggle.toggled.connect(self._toggle_jobs)
        job_header.addWidget(self.job_toggle)
        job_layout.addLayout(job_header)
        self.job_empty = QLabel("没有正在运行的后台任务")
        self.job_empty.setObjectName("helper")
        self.job_empty.setWordWrap(True)
        job_layout.addWidget(self.job_empty)
        self.job_table = QTableWidget(0, 3)  # 精简为 3 列（任务/状态/进度），去掉时间和操作列
        self.job_table.setObjectName("jobTable")
        self.job_table.setAccessibleName("后台任务")
        self.job_table.setHorizontalHeaderLabels(["任务", "状态", "进度"])
        self.job_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.job_table.horizontalHeader().setStretchLastSection(False)
        self.job_table.verticalHeader().setVisible(False)
        self.job_table.setWordWrap(False)
        self.job_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.job_table.verticalHeader().setDefaultSectionSize(32)
        self.job_table.verticalHeader().setMinimumSectionSize(32)
        # v1.7.2：任务列吃满剩余宽度；状态/进度按内容压紧（配合侧栏拖宽查看长任务名）
        self.job_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.job_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.job_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        job_layout.addWidget(self.job_table)
        # v1.7.3：补"清除已完成"入口（v1.6 精简列时被去掉，完成任务会一直堆到重启）
        self.job_clear_button = QPushButton("清除已完成")
        self.job_clear_button.setObjectName("jobClear")
        self.job_clear_button.setToolTip("从列表中移除已完成和失败的任务记录（运行中的任务不受影响）。\n失败原因：悬停对应任务的“状态”单元格查看。")
        self.job_clear_button.clicked.connect(self._clear_finished_jobs)
        job_layout.addWidget(self.job_clear_button)
        self.job_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sidebar_layout.addWidget(self.job_panel, 0)
        # v1.6.0：删除"数据只保存在本机仓库..."提示，"关于"移到设置页
        # v1.7.2：侧栏与内容区改为 QSplitter——支持鼠标拖动分隔条调整侧栏宽度
        # （查看后台任务长任务名时可以拖宽），不再锁死 176/236。
        # v1.7.4：把手加宽为 16 充当浮动侧栏与内容区的间隙（把手透明，见 theme.py）
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(16)
        self.splitter.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.memory_page = MemoryPage(self.facade, self.runner, self.jobs)
        # QWebEngine spins up a Chromium renderer and can cost 1–2 seconds at
        # cold start.  Keep only a lightweight placeholder until the user
        # first opens the graph page.
        self.graph_page = None
        self.graph_placeholder = _PlaceholderPage("共享记忆关系图", "首次打开时加载本地 Sigma 图谱岛。")
        self.skills_page = SkillsPage(self.facade, self.runner, self.jobs)
        self.security_page = SecurityPage(self.facade, self.runner, self.jobs)
        self.settings_page = SettingsPage(self.facade, self.theme, self.runner, self.jobs, self.language)
        for page in (self.memory_page, self.graph_placeholder, self.skills_page, self.security_page, self.settings_page):
            self.pages.addWidget(page)
        self.splitter.addWidget(self.pages)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        outer.addWidget(self.splitter, 1)
        self._restore_sidebar_width()
        self.setCentralWidget(container)
        self.statusBar().showMessage("准备就绪")
        self.nav.setCurrentRow(0)
        self.memory_page.statusMessage.connect(self.statusBar().showMessage)
        self.settings_page.statusMessage.connect(self.statusBar().showMessage)
        # v1.7.4：设置保存/清除配置后刷新所有数据页（原来只刷记忆页，
        # 清除仓库关联后技能/安全/图谱页会留着旧数据）
        self.settings_page.saved.connect(self._settings_saved)
        self.settings_page.importRequested.connect(self.open_import)
        self.language.changed.connect(lambda _mode: (localize(self), self.memory_page.retranslate(), self.skills_page.retranslate(), self.security_page.retranslate()))
        self.jobs.repositoryChanged.connect(self._repository_changed)
        # v1.6.0：后台任务已移到导航栏下半部分，不再用底部 dock
        self.jobs.changed.connect(self._refresh_jobs)
        self._refresh_jobs()
        self._verify_fonts()
        self._install_shortcuts()
        label_controls(self)

    def _install_shortcuts(self) -> None:
        for index in range(5):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(lambda index=index: self.nav.setCurrentRow(index))
        focus_search = QShortcut(QKeySequence("Ctrl+F"), self)
        focus_search.activated.connect(self._focus_current_search)

    def _focus_current_search(self) -> None:
        page = self.pages.currentWidget()
        search = getattr(page, "search", None)
        if search is not None:
            search.setFocus(Qt.FocusReason.ShortcutFocusReason)
            search.selectAll()

    def _settings_saved(self, _config) -> None:
        """v1.7.4：设置保存（含两个清除入口）后，把所有数据页拉一次新。"""
        self.memory_page.refresh()
        self.skills_page.refresh()
        self.security_page.refresh()
        if self.graph_page is not None:
            self.graph_page.refresh_graph()

    def _apply_sidebar_shadow(self, mode: str) -> None:
        """v1.7.4：浮动侧栏投影颜色随主题——暗色下加深一档保证可见。"""
        if not hasattr(self, "sidebar_shadow"):
            return
        color = QColor(0, 0, 0, 150) if mode == "dark" else QColor(23, 27, 35, 60)
        self.sidebar_shadow.setColor(color)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < 1100
        # v1.7.2：侧栏宽度交给 QSplitter（用户可拖动），这里只管紧凑模式下的品牌区收缩
        if hasattr(self, "brand_label"):
            brand_size = 36
            self.brand_logo.setFixedSize(brand_size, brand_size)
            self.brand_label.setFont(QFont(ensure_brand_fonts(), 17 if compact else 20, 900))
            self.brand_label.setText("123" if compact else "123 MSHub")
            self.brand_subtitle.setVisible(not compact)
            self.brand_logo.setPixmap(apply_brand_icon(self.theme.effective_mode).pixmap(self.brand_logo.size()))

    def _ui_settings(self) -> QSettings:
        return QSettings(str(self.facade.config_store.config_dir / "native-ui.ini"), QSettings.Format.IniFormat)

    def _restore_sidebar_width(self) -> None:
        """v1.7.2：恢复用户上次拖出的侧栏宽度；首次启动用默认 236。"""
        width = self._ui_settings().value("mainSidebar/width")
        try:
            width = int(width)
        except (TypeError, ValueError):
            width = 236
        self.splitter.setSizes([max(176, min(560, width)), 10000])

    def _save_sidebar_width(self) -> None:
        width = self.sidebar.width()
        if 176 <= width <= 560:
            self._ui_settings().setValue("mainSidebar/width", width)

    def _refresh_jobs(self) -> None:
        if not hasattr(self, "job_table"):
            return
        rows = self.jobs.list()
        has_finished = any(j["status"] != "running" for j in rows)
        self.job_empty.setVisible(not rows and not self._jobs_collapsed)
        self.job_table.setVisible(bool(rows) and not self._jobs_collapsed)
        # 只在有已结束任务时显示清除入口，收起状态下隐藏
        self.job_clear_button.setVisible(has_finished and not self._jobs_collapsed)
        self.job_table.setRowCount(len(rows))
        for row, job in enumerate(rows):
            label_item = QTableWidgetItem(str(job["label"]))
            # v1.7.4：侧栏较窄时任务名可能省略，悬停看全名
            label_item.setToolTip(str(job["label"]))
            self.job_table.setItem(row, 0, label_item)
            state = {"running": "运行中", "done": "完成", "error": "失败"}.get(job["status"], str(job["status"]))
            state_item = QTableWidgetItem(state)
            # v1.7.3：失败原因原来完全不可见，现在悬停"状态"单元格可看错误详情
            if job["status"] == "error":
                detail = str(job.get("error") or "未知错误")
                state_item.setToolTip(f"失败：{detail}")
            self.job_table.setItem(row, 1, state_item)
            progress = "未知" if job["progress"] is None else f'{job["progress"]}%'
            phase = str(job.get("phase") or "")
            progress_item = QTableWidgetItem(str(progress if progress != "未知" else phase[:10]))
            progress_item.setToolTip(f"{progress} · {phase}" if phase else str(progress))
            self.job_table.setItem(row, 2, progress_item)

    def _clear_finished_jobs(self) -> None:
        """v1.7.3：一键清除已完成/失败的任务记录，运行中的保留。"""
        self.jobs.clear_finished()

    def _toggle_jobs(self, collapsed: bool) -> None:
        self._jobs_collapsed = bool(collapsed)
        self.job_toggle.setText("展开" if collapsed else "收起")
        self._refresh_jobs()

    def _repository_changed(self) -> None:
        self.memory_page.refresh()
        self.skills_page.refresh()
        self.security_page.refresh()
        if self.graph_page is not None:
            self.graph_page.refresh_graph()

    def open_import(self, source: str) -> None:
        ImportDialog(self.facade, self.runner, self.jobs, source, self).exec()

    def _ensure_graph_page(self) -> GraphView:
        if self.graph_page is not None:
            return self.graph_page
        # Delay importing Chromium's DLLs as well as constructing its view.
        from .views.graph_view import GraphView

        graph = GraphView(self.facade, self.theme.effective_mode, runner=self.runner)
        graph.statusMessage.connect(self.statusBar().showMessage)
        graph.openMemoryRequested.connect(self.open_memory)
        placeholder_index = self.pages.indexOf(self.graph_placeholder)
        self.pages.insertWidget(placeholder_index, graph)
        self.pages.removeWidget(self.graph_placeholder)
        self.graph_placeholder.deleteLater()
        self.graph_page = graph
        return graph

    def startup(self) -> None:
        """Start read-only self-heal and then populate the first page."""
        def healed(_identifier: int, _payload: object) -> None:
            self.memory_page.refresh()
            self.statusBar().showMessage("仓库已准备，记忆列表正在加载")

        def failed(_identifier: int, payload: object) -> None:
            self.memory_page.refresh()
            message = payload.get("error") if isinstance(payload, dict) else payload
            self.statusBar().showMessage(f"自愈提示：{message}")

        handle = self.runner.submit(self.facade.heal)
        handle.signals.finished.connect(healed)
        handle.signals.failed.connect(failed)
        # v1.6.0：预热 GraphView，消除首次点击"记忆图示"时的 QWebEngine 冷启动闪屏。
        # 500ms 后后台静默创建（此时主窗口已显示，用户无感知），点击时立即切换。
        QTimer.singleShot(500, self._prewarm_graph_page)
        # v1.7.2：未配置仓库路径 / AI 密钥时弹窗说明哪些功能不可用 + 三步上手流程。
        QTimer.singleShot(600, self._maybe_show_setup_hint)

    def _maybe_show_setup_hint(self) -> None:
        """初始配置提醒：仓库根目录或 AI 密钥缺失时引导用户按顺序完成配置。"""
        box = self._build_setup_hint_box()
        if box is None:
            return
        box.exec()
        if box.checkBox().isChecked():
            self._ui_settings().setValue("setupHint/suppressed", True)

    def _build_setup_hint_box(self):
        """v1.7.2：构造初始配置提醒弹窗；配置齐全或已抑制时返回 None。"""
        from PySide6.QtWidgets import QCheckBox, QMessageBox

        # offscreen 平台（单元测试）没有用户可点的窗口，模态框会挂死事件循环；
        # MSHUB_SHOW_SETUP_HINT=1 供打包 QA 在 offscreen 下截图验证弹窗内容
        if QApplication.platformName() == "offscreen" and not os.environ.get("MSHUB_SHOW_SETUP_HINT"):
            return None
        try:
            config = self.facade.config()
        except Exception:
            return None
        missing_repo = not str(config.repo_root or "").strip()
        missing_key = not bool(config.ai_key_configured)
        settings = self._ui_settings()
        suppressed = settings.value("setupHint/suppressed", False)
        if suppressed in (True, "true", 1, "1"):
            return None
        if not (missing_repo or missing_key):
            # 配置补齐后自动复位开关，未来再次缺配置仍会提醒
            settings.setValue("setupHint/suppressed", False)
            return None
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("欢迎使用 123 MSHub · 初始配置提醒")
        lines = ["检测到初始配置尚未完成，以下功能暂时不可用：", ""]
        if missing_repo:
            lines.append("· 未设置「仓库根目录」：记忆仓库、记忆图示、技能仓库、安全中心、")
            lines.append("   导入记忆技能库都无数据可读写（底部状态栏会提示读取失败）。")
        if missing_key:
            lines.append("· 未填写「AI 密钥」：AI 生成描述、AI 检查、翻译说明等 AI 功能不可用，")
            lines.append("   浏览和手工编辑不受影响。")
        lines += [
            "",
            "快速上手（按顺序三步）：",
            "1. 打开「设置选项 → 仓库与语言」，选择仓库根目录",
            "   （没有现成仓库可先新建一个空文件夹），点「保存设置」；",
            "2. 打开「设置选项 → 维护与导入 → 导入记忆技能库」，",
            "   把现有 Agent 工作目录导入仓库（此步需在第 1 步之后）；",
            "3. 打开「设置选项 → AI 与凭据」，填写 AI 接口地址与密钥并保存，解锁 AI 功能。",
            "",
            "完成第 1、2 步即可正常使用；第 3 步可以之后再补。",
        ]
        box.setText("\n".join(lines))
        checkbox = QCheckBox("以后启动不再显示此提醒（完成配置后会自动停止提醒）")
        box.setCheckBox(checkbox)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setDefaultButton(QMessageBox.StandardButton.Ok)
        return box

    def _prewarm_graph_page(self) -> None:
        if self.graph_page is None:
            self._ensure_graph_page()

    def _navigate(self, row: int) -> None:
        if row < 0:
            return
        if row == 1:
            graph = self._ensure_graph_page()
            self.pages.setCurrentWidget(graph)
            graph.set_theme(self.theme.effective_mode)
        else:
            self.pages.setCurrentIndex(row)
        if row == 0:
            self.memory_page.refresh()

    def _theme_changed(self, mode: str) -> None:
        self.state.update(theme=mode)
        self._apply_sidebar_shadow(mode)
        icon = apply_brand_icon(mode)
        if hasattr(self, "brand_logo"):
            self.brand_logo.setPixmap(icon.pixmap(self.brand_logo.size()))
        if hasattr(self, "nav"):
            for index in range(self.nav.count()):
                key = str(self.nav.item(index).data(Qt.ItemDataRole.UserRole + 1) or "memory")
                self.nav.item(index).setIcon(_nav_icon(key, mode))
        if self.graph_page is not None:
            self.graph_page.set_theme(mode)

    def _verify_fonts(self) -> None:
        """Check the family Qt actually resolved after stylesheet application."""

        import logging

        expected = ensure_brand_fonts()
        for name, widget in (("brand", self.brand_label), ("nav", self.nav)):
            actual = QFontInfo(widget.font()).family()
            if expected == "Dream Han Sans CN" and actual != expected:
                logging.getLogger(__name__).warning("%s font fallback: expected %s, got %s", name, expected, actual)

    def open_memory(self, name: str) -> None:
        self.nav.setCurrentRow(0)
        self.memory_page.open_entry(name)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        if not self.memory_page.can_close_editor():
            event.ignore()
            return
        self._save_sidebar_width()
        self.jobs.shutdown()
        self.runner.pool.waitForDone(1500)
        event.accept()
