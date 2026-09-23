"""Main native window and navigation shell."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .memory_facade import MemoryFacade
from .state import AppState
from .task_runner import TaskRunner
from .theme import ThemeController
if TYPE_CHECKING:
    from .views.graph_view import GraphView
from .views.memory_view import MemoryPage
from .views.settings_view import SettingsPage


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
        self.setWindowTitle("123 MSHub · 原生版")
        self.setMinimumSize(1040, 680)
        self.resize(1280, 820)
        self.facade = facade or MemoryFacade()
        self.runner = TaskRunner(self)
        self.state = AppState(self)
        self.theme = ThemeController(QSettings(str(self.facade.config_store.config_dir / "native-ui.ini"), QSettings.Format.IniFormat), parent=self)
        self._build_ui()
        self.theme.changed.connect(self._theme_changed)
        self.theme.apply()

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
        sidebar_layout.addWidget(brand)
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addSpacing(22)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for label, key in (("记忆库", "memory"), ("记忆图示", "graph"), ("技能库", "skills"), ("安全中心", "security"), ("设置", "settings")):
            row = QListWidgetItem(label)
            row.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(row)
        self.nav.currentRowChanged.connect(self._navigate)
        sidebar_layout.addWidget(self.nav, 1)
        hint = QLabel("数据只保存在本机仓库\n原生线不监听 TCP 端口")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        sidebar_layout.addWidget(hint)
        outer.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.memory_page = MemoryPage(self.facade, self.runner)
        # QWebEngine spins up a Chromium renderer and can cost 1–2 seconds at
        # cold start.  Keep only a lightweight placeholder until the user
        # first opens the graph page.
        self.graph_page = None
        self.graph_placeholder = _PlaceholderPage("记忆图示", "首次打开时加载本地 Sigma 图谱岛。")
        self.skills_page = _PlaceholderPage("技能库", "v1.4.0 先稳定原生记忆壳。技能库的 Git、本地入库、安全检查、跨机对账和批量操作将在 v1.5.0 按功能清单接回。")
        self.security_page = _PlaceholderPage("安全中心", "v1.5.0 接入技能安全检查路线 A/B、信任放行和任务面板；当前版本不伪造扫描结果。")
        self.settings_page = SettingsPage(self.facade, self.theme)
        for page in (self.memory_page, self.graph_placeholder, self.skills_page, self.security_page, self.settings_page):
            self.pages.addWidget(page)
        outer.addWidget(self.pages, 1)
        self.setCentralWidget(container)
        self.statusBar().showMessage("准备就绪")
        self.nav.setCurrentRow(0)
        self.memory_page.statusMessage.connect(self.statusBar().showMessage)
        self.settings_page.statusMessage.connect(self.statusBar().showMessage)
        self.settings_page.saved.connect(lambda _config: self.memory_page.refresh())

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
        if self.graph_page is not None:
            self.graph_page.set_theme(mode)

    def open_memory(self, name: str) -> None:
        self.nav.setCurrentRow(0)
        try:
            self.memory_page.load_detail_sync(name)
        except Exception as exc:
            self.statusBar().showMessage(f"条目打开失败：{exc}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        self.runner.pool.waitForDone(1500)
        event.accept()
