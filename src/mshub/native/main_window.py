"""Main native window and navigation shell."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QByteArray, QEvent, QObject, QSize, Qt, QSettings, QTimer
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
    QMessageBox,
)

from .memory_facade import MemoryFacade
from .state import AppState, ui_settings
from .task_runner import RequestScope, TaskRunner
from .job_controller import JobController
from .starfield import StarfieldBackground
from .theme import PALETTES, ThemeController, current_palette, ensure_brand_fonts, starfield_colors
from .i18n import LanguageController, localize
from .branding import apply_brand_icon, show_about
from .ui import label_controls, show_toast
from .ui_icons import decorate_controls, tinted_icon
from .shell_widgets import NAV_COUNT_ROLE, NavigationDelegate, TaskActivityIcon
from .navigation_symbols import STITCH_NAV_SVGS
from .. import __version__
if TYPE_CHECKING:
    from .views.graph_view import GraphView
from .views.memory_view import MemoryPage
from .views.settings_view import SettingsPage
from .views.skill_view import SkillsPage, SecurityPage
from .views.import_view import ImportDialog


_NAV_SVGS = STITCH_NAV_SVGS


def _nav_icon(key: str, mode: str) -> QIcon:
    # v1.10.0C：导航选中态改浅底胶囊（theme.py #nav::item:selected），
    # 选中图标从白色改主题强调色，浅底上才看得清
    icon = QIcon()
    source = _NAV_SVGS[key]
    for icon_mode, color in ((QIcon.Mode.Normal, PALETTES[mode]["ink"]), (QIcon.Mode.Selected, PALETTES[mode]["accent"])):
        renderer = QSvgRenderer(QByteArray(source.replace("COLOR", color).encode("utf-8")))
        # Exact template symbols, rasterized at common Windows DPI sizes.
        for size in (20, 25, 30, 40, 60):
            pixmap = QPixmap(size, size)
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
        layout.setContentsMargins(20, 14, 20, 12)
        layout.setSpacing(12)
        from .ui import HeaderBand
        layout.addWidget(HeaderBand("NATIVE ROADMAP", title, detail))
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
        self.theme = ThemeController(ui_settings(self.facade.config_store.config_dir), parent=self)
        self._build_ui()
        self.theme.changed.connect(self._theme_changed)
        self.theme.apply()
        self.language.apply(self.facade.config().language)

    def _build_ui(self) -> None:
        # v1.10.0D（Stitch）：Silk/Mica 画布承载侧栏与内容浮层；页面本身不改变业务路由。
        container = StarfieldBackground()
        container.set_colors(*starfield_colors(self.theme.effective_mode))
        outer = QHBoxLayout(container)
        # v1.7.4：侧边栏浮动面板——四边 16px 外边距；侧栏与内容区的 16px
        # 间隙由 splitter 把手宽度提供（把手已透明化）。圆角 16 在 theme.py。
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        # The 14px brand plus the v1.10.0D micro version pill must remain
        # readable at the normal desktop breakpoint; 236px is the minimum
        # width that keeps the three brand elements on one line.
        self.sidebar.setMinimumWidth(236)
        # v1.7.2：上限从 236 放宽，配合 QSplitter 支持鼠标拖宽侧栏
        self.sidebar.setMaximumWidth(560)
        # v1.7.4：柔和低透明度投影（QSS 不支持 box-shadow，用图形效果实现）
        self.sidebar_shadow = QGraphicsDropShadowEffect(self.sidebar)
        self.sidebar_shadow.setBlurRadius(32)
        self.sidebar_shadow.setOffset(0, 6)
        self.sidebar.setGraphicsEffect(self.sidebar_shadow)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 18, 12, 12)
        self.brand_label = QLabel("123 MSHub", objectName="brandName")
        self.brand_label.setAccessibleName("123 MSHub")
        self.brand_label.setFont(QFont(ensure_brand_fonts(), 14, 700))
        self.brand_subtitle = QLabel("本地共享记忆与技能")
        self.brand_subtitle.setObjectName("muted")
        self.brand_logo = QLabel(objectName="brandLogo")
        self.brand_logo.setFixedSize(36, 36)
        brand_row = QHBoxLayout()
        # Keep the 14px template brand and the v1.10.0D pill on one line in
        # the fixed-width Silk sidebar; the compact gap preserves hierarchy.
        brand_row.setSpacing(2)
        brand_row.addWidget(self.brand_logo)
        brand_row.addWidget(self.brand_label, 1)
        self.brand_version = QLabel(f"v{__version__}")
        self.brand_version.setObjectName("versionPill")
        brand_row.addWidget(self.brand_version)
        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addWidget(self.brand_subtitle)
        sidebar_layout.addSpacing(16)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.nav.setLineWidth(0)
        self.nav.setStyleSheet("QListWidget#nav { border: 0; outline: 0; }")
        self.nav.setAccessibleName("主导航")
        # 导航是鼠标/触控入口；去掉 QAbstractItemView 默认的整块焦点框，
        # 避免模板里的浮起胶囊被一圈高亮矩形包住。点击导航仍会切换页面。
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setFont(QFont(ensure_brand_fonts(), 13, QFont.Weight.Bold))
        self.nav.setItemDelegate(NavigationDelegate(self.nav))
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
            if key in {"memory", "skills", "security"}:
                row.setData(NAV_COUNT_ROLE, 0)
            row.setIcon(_nav_icon(key, self.theme.effective_mode))
            self.nav.addItem(row)
        self.nav.currentRowChanged.connect(self._navigate)
        # v1.9.1（需求 C）：nav 不再直接进侧栏布局，与任务面板组成垂直 QSplitter（见下）
        # v1.6.0：后台任务移到导航栏下半部分（原来在底部 dock 太矮看不清）
        # v1.10.0（Stitch 需求 4）：悬浮圆角卡——QSS 填充+描边+圆角（theme.py
        # #jobPanel），配独立小投影；旧版 border-top 衬底已删，直接浮在侧栏上
        self.job_panel = QFrame()
        self.job_panel.setObjectName("jobPanel")
        self.job_shadow = QGraphicsDropShadowEffect(self.job_panel)
        self.job_shadow.setBlurRadius(24)
        self.job_shadow.setOffset(0, 4)
        self.job_panel.setGraphicsEffect(self.job_shadow)
        job_layout = QVBoxLayout(self.job_panel)
        job_layout.setContentsMargins(10, 10, 10, 10)
        job_layout.setSpacing(6)
        self._jobs_collapsed = False
        job_header = QHBoxLayout()
        job_header.setSpacing(7)
        self.job_activity_icon = TaskActivityIcon(self)
        job_header.addWidget(self.job_activity_icon, alignment=Qt.AlignmentFlag.AlignVCenter)
        # v1.7.2：标题字号 14px ≥「收起/展开」按钮（13px），原来用 eyebrow 只有 11px 反而更小
        job_title = QLabel("后台任务")
        job_title.setObjectName("jobTitle")
        job_header.addWidget(job_title)
        job_header.addStretch()
        self.job_toggle = QToolButton()
        self.job_toggle.setObjectName("jobToggle")
        self.job_toggle.setProperty("mshubNoIcon", True)
        self.job_toggle.setFixedSize(30, 28)
        self.job_toggle.setIconSize(QSize(16, 16))
        self.job_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.job_toggle.setCheckable(True)
        self.job_toggle.setAccessibleName("展开或收起后台任务")
        self.job_toggle.toggled.connect(self._toggle_jobs)
        job_header.addWidget(self.job_toggle, alignment=Qt.AlignmentFlag.AlignVCenter)
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
        self.job_table.itemSelectionChanged.connect(self._job_selection_changed)
        self._selected_job_id: str | None = None
        job_layout.addWidget(self.job_table)
        # v1.10.3：失败/未完成任务需要可追溯、可重试；动作行贴右侧与
        # 「清除已完成」并排，避免把错误原因藏在单行 tooltip 里。
        job_actions = QHBoxLayout()
        job_actions.addStretch(1)
        self.job_clear_button = QPushButton("清除已完成")
        self.job_clear_button.setObjectName("jobClear")
        self.job_clear_button.setToolTip("从列表中移除已完成和失败的任务记录（运行中的任务不受影响）。")
        self.job_clear_button.clicked.connect(self._clear_finished_jobs)
        job_actions.addWidget(self.job_clear_button)
        self.job_detail_button = QPushButton("详情")
        self.job_detail_button.setObjectName("jobAction")
        self.job_detail_button.setEnabled(False)
        self.job_detail_button.clicked.connect(self._show_selected_job_detail)
        job_actions.addWidget(self.job_detail_button)
        self.job_retry_button = QPushButton("重试")
        self.job_retry_button.setObjectName("jobAction")
        self.job_retry_button.setEnabled(False)
        self.job_retry_button.clicked.connect(self._retry_selected_job)
        job_actions.addWidget(self.job_retry_button)
        job_layout.addLayout(job_actions)
        # v1.9.1（需求 C）：任务面板高度可拖——与导航组成垂直 QSplitter。
        # 垂直方向 Ignored 策略让面板跟随用户拖动而不是回弹到 sizeHint；
        # 把手细线上色见 theme.py 的 #jobSplitter。收起按钮仍可用（只藏内容）。
        self.job_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.nav.setMinimumHeight(160)
        self.job_panel.setMinimumHeight(120)
        self.job_splitter = QSplitter(Qt.Orientation.Vertical)
        self.job_splitter.setObjectName("jobSplitter")
        self.job_splitter.setChildrenCollapsible(False)
        self.job_splitter.setHandleWidth(8)
        self.job_splitter.addWidget(self.nav)
        self.job_splitter.addWidget(self.job_panel)
        self.job_splitter.setStretchFactor(0, 1)
        self.job_splitter.setStretchFactor(1, 0)
        sidebar_layout.addWidget(self.job_splitter, 1)
        # v1.6.0：删除"数据只保存在本机仓库..."提示，"关于"移到设置页
        # v1.7.2：侧栏与内容区改为 QSplitter——支持鼠标拖动分隔条调整侧栏宽度
        # （查看后台任务长任务名时可以拖宽），不再锁死 236/560。
        # v1.7.4：把手加宽为 16 充当浮动侧栏与内容区的间隙（把手透明，见 theme.py）
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(16)
        self.splitter.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        self.memory_page = MemoryPage(self.facade, self.runner, self.jobs)
        # QWebEngine spins up a Chromium renderer and can cost 1–2 seconds at
        # cold start.  Keep only a lightweight placeholder until the user
        # first opens the graph page.
        self.graph_page = None
        self.graph_placeholder = _PlaceholderPage("记忆图示", "首次打开时加载本地 Sigma 图谱岛。")
        self.skills_page = SkillsPage(self.facade, self.runner, self.jobs)
        self.security_page = SecurityPage(self.facade, self.runner, self.jobs)
        self.settings_page = SettingsPage(self.facade, self.theme, self.runner, self.jobs, self.language)
        self.memory_page.totalChanged.connect(lambda total: self._set_nav_count("memory", total))
        self.skills_page.totalChanged.connect(self._set_asset_counts)
        self.security_page.pendingChanged.connect(lambda pending: self._set_nav_count("security", pending))
        for page in (self.memory_page, self.graph_placeholder, self.skills_page, self.security_page, self.settings_page):
            self.pages.addWidget(page)
        # v1.10.0（Stitch）：内容区整体坐在半透明页板上浮于点阵背景
        # （theme.py #pageSheet）；页板内布局零边距，各页自身留白不变。
        self.page_sheet = QFrame()
        self.page_sheet.setObjectName("pageSheet")
        sheet_layout = QVBoxLayout(self.page_sheet)
        sheet_layout.setContentsMargins(0, 0, 0, 0)
        sheet_layout.addWidget(self.pages)
        self.splitter.addWidget(self.page_sheet)
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
        # v1.10.0：语言切换会重译按钮文本——文本→图标映射随之重挂（英文文案不在
        # 映射表内的按钮自然回退无图标，不报错）
        self.language.changed.connect(
            lambda _mode: (
                localize(self), self.memory_page.retranslate(), self.skills_page.retranslate(),
                self.security_page.retranslate(), decorate_controls(self, current_palette()),
            )
        )
        self.jobs.repositoryChanged.connect(self._repository_changed)
        # v1.6.0：后台任务已移到导航栏下半部分，不再用底部 dock
        self.jobs.changed.connect(self._refresh_jobs)
        self.jobs.completed.connect(self._job_completed)
        self._refresh_jobs()
        self._verify_fonts()
        self._install_shortcuts()
        label_controls(self)
        # v1.10.0（Stitch）：按钮/搜索框按文本映射挂图标；主题切换后随 _theme_changed 重染
        self.workspace = container
        decorate_controls(self, current_palette())
        # v1.9.1（需求 A）：启动 8 秒后后台查一次新版本（可在设置页关）。
        # 延迟挂网是刻意的——不能回退 v1.8.1 的首帧优化；singleShot 排在
        # QApplication 就绪之后（v1.8.1 教训：排在创建之前会静默不触发）。
        self.update_scope = RequestScope(self.runner, self)
        QTimer.singleShot(8000, self._startup_update_check)

    def _startup_update_check(self) -> None:
        """v1.9.1（需求 A）：启动自动检查更新——失败静默放弃，发现新版仅轻提示。"""
        from . import upgrader
        if not getattr(sys, "frozen", False):
            return  # 源码运行不提示（开发环境不打扰）
        config = self.facade.config()
        if not getattr(config, "auto_check_updates", True):
            return

        def done(release):
            tag = str(release.get("tag") or "")
            if tag and upgrader.is_newer(tag, __version__):
                show_toast(self.nav, f"发现新版本 {tag}：到「设置选项 → 检查更新」升级", 6000)

        def failed(_message):
            pass  # 静默放弃：自动检查失败不弹窗不写状态栏（用户要求）

        token = self.facade.config_store.get_secret("github_token")
        self.update_scope.call("startup-update-check", upgrader.fetch_latest_release, done, failed, config.proxy, token)

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
        for key in ("memory", "skills", "security"):
            self._set_nav_count(key, 0)
        self.memory_page.refresh()
        self.skills_page.refresh()
        self.security_page.refresh()
        if self.graph_page is not None:
            self.graph_page.refresh_graph()

    def _apply_sidebar_shadow(self, mode: str) -> None:
        """v1.7.4：浮动侧栏投影颜色随主题；v1.10.0 任务悬浮卡投影同走这里。"""
        if not hasattr(self, "sidebar_shadow"):
            return
        dark = mode == "dark"
        color = QColor(0, 0, 0, 150) if dark else QColor(23, 27, 35, 60)
        self.sidebar_shadow.setColor(color)
        if hasattr(self, "job_shadow"):
            self.job_shadow.setColor(QColor(0, 0, 0, 130) if dark else QColor(23, 27, 35, 45))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < 1100
        # v1.7.2：侧栏宽度交给 QSplitter（用户可拖动），这里只管紧凑模式下的品牌区收缩
        if hasattr(self, "brand_label"):
            brand_size = 36
            self.brand_logo.setFixedSize(brand_size, brand_size)
            self.brand_label.setFont(QFont(ensure_brand_fonts(), 13 if compact else 14, 700))
            self.brand_label.setText("123" if compact else "123 MSHub")
            self.brand_subtitle.setVisible(not compact)
            self.brand_version.setVisible(not compact)
            self.brand_logo.setPixmap(apply_brand_icon(self.theme.effective_mode).pixmap(self.brand_logo.size()))

    def _ui_settings(self) -> QSettings:
        return ui_settings(self.facade.config_store.config_dir)

    def _restore_sidebar_width(self) -> None:
        """v1.7.2：恢复用户上次拖出的侧栏宽度；首次启动用默认 236。"""
        width = self._ui_settings().value("mainSidebar/width")
        try:
            width = int(width)
        except (TypeError, ValueError):
            # 236px keeps the template's 14px brand, version pill and icon on
            # one line at the normal desktop width without text elision.
            width = 236
        self.splitter.setSizes([max(236, min(560, width)), 10000])

    def _save_sidebar_width(self) -> None:
        width = self.sidebar.width()
        if 236 <= width <= 560:
            self._ui_settings().setValue("mainSidebar/width", width)

    # ---- v1.10.0：后台任务面板高度三修复（默认可见五项 / 记忆用户调整 / 收起降到最低） ----

    def _job_panel_height(self) -> int:
        """用户记忆的任务面板高度；无记忆或越界时用紧凑默认 132px。"""
        value = self._ui_settings().value("jobPanel/height")
        try:
            panel = int(value)
        except (TypeError, ValueError):
            panel = 0
        return panel if 44 <= panel <= 720 else 132

    def _apply_job_layout(self, panel_height: int | None = None) -> None:
        """按像素精确分配导航/任务面板高度——显示后调用（此时分隔条总高已知）。

        v1.9.1 用比例式 setSizes([4000, 800])，实际分配受窗口高度/DPI/布局时序
        影响不可控，用户侧出现过面板占大半侧栏、导航只剩两项的情况。这里保证：
        面板 = 指定高度（默认取记忆值），导航 = 其余全部（保底 5 项完整可见）。
        """
        total = self.job_splitter.height() or self.sidebar.height() - 120 or 640
        panel = panel_height if panel_height is not None else self._job_panel_height()
        panel = max(44, min(panel, total - 260))
        self.job_splitter.setSizes([max(total - panel, 260), panel])

    def showEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        super().showEvent(event)
        # 首次显示布局稳定后应用任务面板布局（singleShot(0) 等布局结算完成）
        if not getattr(self, "_job_layout_applied", False):
            self._job_layout_applied = True
            QTimer.singleShot(0, self._apply_job_layout)

    def _save_job_layout(self) -> None:
        if not self._jobs_collapsed:
            self._ui_settings().setValue("jobPanel/height", self.job_panel.height())

    def _refresh_jobs(self) -> None:
        if not hasattr(self, "job_table"):
            return
        rows = self.jobs.list()
        self.job_activity_icon.set_running(any(j["status"] == "running" for j in rows))
        self._update_job_toggle()
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
            result = job.get("result")
            if isinstance(result, dict) and result.get("summary"):
                label_item.setToolTip(f"{job['label']}\n{result['summary']}")
            self.job_table.setItem(row, 0, label_item)
            state = {"running": "未完成", "done": "完成", "error": "失败"}.get(job["status"], str(job["status"]))
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
            if job["status"] != "done":
                error_color = QColor(current_palette()["error"])
                for cell in (label_item, state_item, progress_item):
                    cell.setForeground(error_color)
        restore_row = next((index for index, job in enumerate(rows) if job["id"] == self._selected_job_id), -1)
        if restore_row >= 0:
            self.job_table.selectRow(restore_row)
        else:
            self._selected_job_id = None
        self._job_selection_changed()

    def _job_selection_changed(self) -> None:
        selected = self.job_table.selectionModel().selectedRows() if hasattr(self, "job_table") else []
        row = selected[0].row() if selected else -1
        rows = self.jobs.list() if hasattr(self, "jobs") else []
        job = rows[row] if 0 <= row < len(rows) else None
        self._selected_job_id = job["id"] if job else None
        if hasattr(self, "job_detail_button"):
            self.job_detail_button.setEnabled(job is not None)
            self.job_retry_button.setEnabled(bool(job and job["status"] != "done" and job.get("kind") == "install"))

    def _selected_job(self):
        if not self._selected_job_id:
            return None
        return next((job for job in self.jobs.list() if job["id"] == self._selected_job_id), None)

    def _show_selected_job_detail(self) -> None:
        job = self._selected_job()
        if not job:
            return
        result = job.get("result")
        summary = result.get("summary") if isinstance(result, dict) else ""
        detail = str(job.get("error") or job.get("detail") or summary or "暂无更多错误信息")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning if job["status"] != "done" else QMessageBox.Icon.Information)
        box.setWindowTitle(f"任务详情 · {job.get('label', '')}")
        box.setText(detail)
        box.setInformativeText(f"状态：{job.get('status')}\n阶段：{job.get('phase') or '—'}")
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def _retry_selected_job(self) -> None:
        job = self._selected_job()
        if not job or job.get("kind") != "install":
            return
        retried = self.jobs.retry(job["id"])
        if retried is None:
            self.statusBar().showMessage("该任务当前不可重试")
        else:
            self._selected_job_id = retried.id
            self.statusBar().showMessage("已重新提交安装任务")
            self._refresh_jobs()

    def _clear_finished_jobs(self) -> None:
        """v1.7.3：一键清除已完成/失败的任务记录，运行中的保留。"""
        self.jobs.clear_finished()
        self._selected_job_id = None

    def _job_completed(self, job) -> None:
        result = job.get("result")
        if isinstance(result, dict) and result.get("summary"):
            self.statusBar().showMessage(str(result["summary"]))
            show_toast(self.nav, str(result["summary"]), 7000)

    def _toggle_jobs(self, collapsed: bool) -> None:
        self._jobs_collapsed = bool(collapsed)
        self._update_job_toggle()
        if collapsed:
            # v1.10.0：收起 = 面板真降到最低（只留标题行），导航区即时放大；
            # 原来只藏内容不改高度，收起后仍看不到五个导航项
            self._jobs_expanded_height = max(self.job_panel.height(), 44)
            self.job_panel.setMinimumHeight(50)
            self._apply_job_layout(50)
        else:
            self.job_panel.setMinimumHeight(120)
            self._apply_job_layout(getattr(self, "_jobs_expanded_height", 0) or None)
        self._refresh_jobs()

    def _update_job_toggle(self) -> None:
        collapsed = self._jobs_collapsed
        name = "chevron_up" if collapsed else "chevron_down"
        self.job_toggle.setIcon(tinted_icon(name, current_palette()["muted"], 24))
        self.job_toggle.setProperty("direction", "up" if collapsed else "down")
        self.job_toggle.setToolTip("展开后台任务" if collapsed else "收起后台任务")

    def _set_nav_count(self, key: str, total: int) -> None:
        for index in range(self.nav.count()):
            item = self.nav.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                item.setData(NAV_COUNT_ROLE, max(0, int(total)))
                item.setToolTip(f"{item.text()} · {max(0, int(total))}")
                break

    def _set_asset_counts(self, total: int) -> None:
        # The skills badge is the full installed inventory.  Safety has its
        # own pendingChanged signal and deliberately does not mirror this.
        self._set_nav_count("skills", total)

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
        # v1.8.1：预热整体提前到 show 之前（见 show_after_graph_prewarm），这里保留
        # 幂等兜底——万一预热被跳过（异常路径），启动 500ms 后仍会补一次。
        QTimer.singleShot(500, self._prewarm_graph_page)
        # v1.7.2：未配置仓库路径 / AI 密钥时弹窗说明哪些功能不可用 + 三步上手流程。
        QTimer.singleShot(600, self._maybe_show_setup_hint)

    def show_after_graph_prewarm(self, timeout_ms: int = 2800) -> None:
        """v1.8.1：显示前预创建图谱页，把 Chromium 冷启动引起的顶层窗口原生重建
        挪到用户视野之外。

        根因：QWebEngineView 首次初始化渲染表面时，Qt 会销毁并重建已显示顶层窗口的
        原生窗口（Hide→WinIdChange→Show 三连）——用户看到"窗口打开后 1 秒内闪烁
        一次重新弹开"。在 show() 之前创建图谱页，重建发生在窗口显示前，无感。
        显示时机 = 首次 WinIdChange 后 150ms（布局稳定）或超时兜底（默认 2.8s，
        offscreen 测试注入短超时）。
        """
        class _RevealOnRecreate(QObject):
            def __init__(self, on_recreate: object) -> None:
                super().__init__()
                self._on_recreate = on_recreate

            def eventFilter(self, obj, ev) -> bool:  # noqa: N803 - Qt virtual method name
                if ev.type() == QEvent.Type.WinIdChange:
                    QTimer.singleShot(150, self._on_recreate)
                return False

        revealed = {"done": False}

        def reveal() -> None:
            if revealed["done"]:
                return
            revealed["done"] = True
            self.removeEventFilter(self._reveal_spy)
            self.show()
            QTimer.singleShot(0, self.startup)

        # Spy 实例必须挂在 self 上保活：局部实例被 GC 时过滤器会被静默卸载。
        self._reveal_spy = _RevealOnRecreate(reveal)
        self._reveal_spy.setParent(self)
        self.installEventFilter(self._reveal_spy)
        QTimer.singleShot(timeout_ms, reveal)
        try:
            self._ensure_graph_page()
        except Exception:
            reveal()

    def _maybe_show_setup_hint(self) -> None:
        """初始配置提醒：仓库根目录或 AI 密钥缺失时引导用户按顺序完成配置。"""
        box = self._build_setup_hint_box()
        if box is None:
            return
        # v1.8.1：exec 前先取 checkbox 引用。无 parent 的 QCheckBox 经 setCheckBox
        # 挂进弹窗后，Python 局部变量消失时 PySide6 会连 C++ 对象一起回收，
        # exec() 之后再访问 box.checkBox() 就是悬空指针（未配置新用户 100% 段错误，
        # 程序随弹窗一起退出）。构造处已补 parent，这里持引用是第二道保险。
        checkbox = box.checkBox()
        box.exec()
        if checkbox.isChecked():
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
        checkbox = QCheckBox("以后启动不再显示此提醒（完成配置后会自动停止提醒）", box)
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
            # v1.10.0：启动后首次进入图谱页自动加载一次数据——原来预热只建视图
            # 不装数据，用户每次都要手点「刷新」才见画面
            if not getattr(self, "_graph_auto_refreshed", False):
                self._graph_auto_refreshed = True
                graph.refresh_graph()
        else:
            self.pages.setCurrentIndex(row)
        if row == 0:
            self.memory_page.refresh()

    def _theme_changed(self, mode: str) -> None:
        self.state.update(theme=mode)
        self._apply_sidebar_shadow(mode)
        # v1.10.0（Stitch）：点阵底板换色 + 图标重染
        if hasattr(self, "workspace"):
            self.workspace.set_colors(*starfield_colors(mode))
        decorate_controls(self, PALETTES.get(mode, {}))
        self._update_job_toggle()
        self.job_activity_icon.update()
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
            if actual != expected:
                logging.getLogger(__name__).warning("%s font fallback: expected %s, got %s", name, expected, actual)

    def open_memory(self, name: str) -> None:
        self.nav.setCurrentRow(0)
        self.memory_page.open_entry(name)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        if not self.memory_page.can_close_editor():
            event.ignore()
            return
        self._save_sidebar_width()
        self._save_job_layout()
        self.jobs.shutdown()
        self.runner.pool.waitForDone(1500)
        event.accept()
