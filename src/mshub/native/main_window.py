"""Main native window and navigation shell."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
    QToolButton,
    QDockWidget,
    QTableWidget,
    QTableWidgetItem,
)

from .memory_facade import MemoryFacade
from .state import AppState
from .task_runner import TaskRunner
from .job_controller import JobController
from .theme import ThemeController
from .i18n import LanguageController, localize
from .branding import apply_brand_icon, show_about
from .. import __version__
if TYPE_CHECKING:
    from .views.graph_view import GraphView
from .views.memory_view import MemoryPage
from .views.settings_view import SettingsPage
from .views.skill_view import SkillsPage, SecurityPage
from .views.import_view import ImportDialog


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
        self.setMinimumSize(1040, 680)
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
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(236)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(20, 26, 20, 20)
        brand = QLabel("123 MSHub")
        brand.setStyleSheet("font-size: 21px; font-weight: 700;")
        subtitle = QLabel("本地共享记忆与技能")
        subtitle.setObjectName("muted")
        self.brand_logo = QLabel(objectName="brandLogo")
        self.brand_logo.setFixedSize(44, 44)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        brand_row.addWidget(self.brand_logo)
        brand_row.addWidget(brand, 1)
        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addSpacing(22)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        # v1.6.0：导航项改为四字 + 图标（统一用 Qt 标准图标，与文字同色）
        for label, key, icon_name in (
            ("记忆仓库", "memory", "SP_DirHomeIcon"),
            ("记忆图示", "graph", "SP_DriveNetIcon"),
            ("技能仓库", "skills", "SP_DirLinkIcon"),
            ("安全中心", "security", "SP_DialogApplyButton"),
            ("设置选项", "settings", "SP_FileDialogDetailedView"),
        ):
            row = QListWidgetItem(label)
            row.setData(Qt.ItemDataRole.UserRole, key)
            icon = self.style().standardIcon(getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon))
            row.setIcon(icon)
            self.nav.addItem(row)
        self.nav.currentRowChanged.connect(self._navigate)
        sidebar_layout.addWidget(self.nav, 1)
        # v1.6.0：后台任务移到导航栏下半部分（原来在底部 dock 太矮看不清）
        self.job_panel = QFrame()
        self.job_panel.setObjectName("jobPanel")
        job_layout = QVBoxLayout(self.job_panel)
        job_layout.setContentsMargins(0, 12, 0, 0)
        job_layout.setSpacing(6)
        job_title = QLabel("后台任务")
        job_title.setObjectName("eyebrow")
        job_layout.addWidget(job_title)
        self.job_table = QTableWidget(0, 3)  # v1.6.0：精简为 3 列（任务/状态/进度），去掉时间和操作列
        self.job_table.setHorizontalHeaderLabels(["任务", "状态", "进度"])
        self.job_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.job_table.horizontalHeader().setStretchLastSection(True)
        self.job_table.verticalHeader().setVisible(False)
        self.job_table.setMaximumHeight(180)
        job_layout.addWidget(self.job_table)
        sidebar_layout.addWidget(self.job_panel)
        # v1.6.0：删除"数据只保存在本机仓库..."提示，"关于"移到设置页
        outer.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.memory_page = MemoryPage(self.facade, self.runner, self.jobs)
        # QWebEngine spins up a Chromium renderer and can cost 1–2 seconds at
        # cold start.  Keep only a lightweight placeholder until the user
        # first opens the graph page.
        self.graph_page = None
        self.graph_placeholder = _PlaceholderPage("记忆图示", "首次打开时加载本地 Sigma 图谱岛。")
        self.skills_page = SkillsPage(self.facade, self.runner, self.jobs)
        self.security_page = SecurityPage(self.facade, self.runner, self.jobs)
        self.settings_page = SettingsPage(self.facade, self.theme, self.runner, self.jobs, self.language)
        for page in (self.memory_page, self.graph_placeholder, self.skills_page, self.security_page, self.settings_page):
            self.pages.addWidget(page)
        outer.addWidget(self.pages, 1)
        self.setCentralWidget(container)
        self.statusBar().showMessage("准备就绪")
        self.nav.setCurrentRow(0)
        self.memory_page.statusMessage.connect(self.statusBar().showMessage)
        self.settings_page.statusMessage.connect(self.statusBar().showMessage)
        self.settings_page.saved.connect(lambda _config: self.memory_page.refresh())
        self.settings_page.importRequested.connect(self.open_import)
        self.language.changed.connect(lambda _mode: (localize(self), self.memory_page.retranslate(), self.skills_page.retranslate(), self.security_page.retranslate()))
        self.jobs.repositoryChanged.connect(self._repository_changed)
        # v1.6.0：后台任务已移到导航栏下半部分，不再用底部 dock
        self.jobs.changed.connect(self._refresh_jobs)
        self._refresh_jobs()

    def _refresh_jobs(self) -> None:
        if not hasattr(self, "job_table"):
            return
        rows = self.jobs.list()
        self.job_table.setRowCount(len(rows))
        for row, job in enumerate(rows):
            self.job_table.setItem(row, 0, QTableWidgetItem(str(job["label"])))
            state = {"running": "运行中", "done": "完成", "error": "失败"}.get(job["status"], str(job["status"]))
            self.job_table.setItem(row, 1, QTableWidgetItem(str(state)))
            progress = "未知" if job["progress"] is None else f'{job["progress"]}%'
            self.job_table.setItem(row, 2, QTableWidgetItem(str(f'{progress} · {job["phase"]}')))

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
        icon = apply_brand_icon(mode)
        if hasattr(self, "brand_logo"):
            self.brand_logo.setPixmap(icon.pixmap(self.brand_logo.size()))
        if self.graph_page is not None:
            self.graph_page.set_theme(mode)

    def open_memory(self, name: str) -> None:
        self.nav.setCurrentRow(0)
        try:
            self.memory_page.load_detail_sync(name)
        except Exception as exc:
            self.statusBar().showMessage(f"条目打开失败：{exc}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        self.jobs.shutdown()
        self.runner.pool.waitForDone(1500)
        event.accept()
