"""Local QWebEngine graph island."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..graph_bridge import GraphBridge
from ..memory_facade import MemoryFacade
from ..task_runner import TaskRunner
from ..ui import copy_agent_prompt, make_agent_prompt_button

try:  # QtWebEngine is part of the native extra, but keep service imports usable without it.
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _WEB_ENGINE_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised on machines without native extra
    _WEB_ENGINE_AVAILABLE = False


if _WEB_ENGINE_AVAILABLE:
    class _GraphPage(QWebEnginePage):
        consoleError = Signal(str)

        def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):  # noqa: N802
            # A worker fallback may log a warning; only script errors make the
            # smoke path fail.  Never surface source text or repository data.
            if int(level) >= 2:
                self.consoleError.emit(f"{message}（{sourceID}:{lineNumber}）")

    class _LocalOnlyInterceptor(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info) -> None:  # noqa: N802 - Qt virtual method name
            url = info.requestUrl()
            # graphology 0.10.1 already inlines its worker into a Blob URL.
            # Blob is local; it must stay allowed for file:// graph pages.
            if url.scheme() not in {"file", "qrc", "blob", "data", "about"}:
                info.block(True)


class GraphView(QWidget):
    openMemoryRequested = Signal(str)
    statusMessage = Signal(str)

    def __init__(self, facade: MemoryFacade, theme: str = "light", parent: QWidget | None = None, runner: TaskRunner | None = None) -> None:
        super().__init__(parent)
        self.facade = facade
        self.runner = runner or TaskRunner(self)
        self.bridge = GraphBridge(facade, theme, self)
        self._profile = None
        self.web_view = None
        self._page_loaded = False
        self._build_ui()
        self._warm_graph_cache()

    def _warm_graph_cache(self) -> None:
        handle = self.runner.submit(self.facade.graph, "link")

        def ready(_identifier: int, payload: object) -> None:
            if isinstance(payload, dict):
                self.bridge.set_graph_cache("link", payload)

        handle.signals.finished.connect(ready)

    def refresh_graph(self) -> None:
        """Invalidate the read cache and ask the local page to reload data."""
        self.bridge.invalidate()
        handle = self.runner.submit(self.facade.graph, "link")

        def ready(_identifier, payload):
            if isinstance(payload, dict):
                self.bridge.set_graph_cache("link", payload)
                if self.web_view is not None:
                    self.web_view.page().runJavaScript("window.mshubReloadGraph && window.mshubReloadGraph()")

        handle.signals.finished.connect(ready)

    @staticmethod
    def graph_asset_path() -> Path:
        return Path(__file__).resolve().parent.parent / "graph" / "index.html"

    @property
    def graph_path(self) -> Path:
        return self.graph_asset_path()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # v1.7.5：图谱页顶部细条——右上角统一「Agent连接提示词」皇家蓝按钮
        bar = QHBoxLayout()
        bar.setContentsMargins(16, 10, 16, 0)
        bar.addStretch()
        self.agent_button = make_agent_prompt_button(self, self._copy_prompt)
        bar.addWidget(self.agent_button)
        layout.addLayout(bar)
        # QtWebEngine cannot create a Chromium surface on the offscreen
        # platform plugin used by unit tests.  The real Windows build uses the
        # full web island; tests still validate its static assets and bridge.
        if not _WEB_ENGINE_AVAILABLE or QApplication.platformName() == "offscreen":
            label = QLabel("图谱 web 岛需要安装 native extra（PySide6 + QtWebEngine）。")
            label.setObjectName("muted")
            layout.addWidget(label)
            return
        self.web_view = QWebEngineView(self)
        config_dir = self.facade.config_store.config_dir / "web-profile"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "cache").mkdir(parents=True, exist_ok=True)
        self._profile = QWebEngineProfile("123mshub-native", self)
        self._profile.setPersistentStoragePath(str(config_dir))
        self._profile.setCachePath(str(config_dir / "cache"))
        # Local file assets are versioned with the application. Never let a
        # persistent Chromium HTTP cache serve the previous bundled graph JS.
        self._profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        self._profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self._profile.setUrlRequestInterceptor(_LocalOnlyInterceptor(self._profile))
        page = _GraphPage(self._profile, self.web_view)
        page.consoleError.connect(lambda message: self.statusMessage.emit(f"图谱脚本错误：{message}"))
        channel = QWebChannel(page)
        channel.registerObject("mshub", self.bridge)
        page.setWebChannel(channel)
        self.web_view.setPage(page)
        self.web_view.urlChanged.connect(self._guard_url)
        self.web_view.loadFinished.connect(self._loaded)
        self.bridge.themeChanged.connect(self._push_palette)
        self.bridge.openMemoryRequested.connect(self.openMemoryRequested)
        layout.addWidget(self.web_view)
        if self.graph_path.is_file():
            self.web_view.setUrl(QUrl.fromLocalFile(str(self.graph_path)))
        else:
            layout.addWidget(QLabel(f"图谱资源缺失：{self.graph_path}"))

    def _guard_url(self, url: QUrl) -> None:
        if url.scheme() not in {"file", "qrc", "about"} and self.web_view is not None:
            self.web_view.stop()
            self.statusMessage.emit("已阻止图谱页面访问远程地址")

    def _loaded(self, ok: bool) -> None:
        self._page_loaded = bool(ok)
        self.statusMessage.emit("图谱已加载" if ok else "图谱加载失败，请检查本地资源")
        if ok:
            self._push_palette(self.bridge.getTheme())

    def _push_palette(self, _theme: str = "") -> None:
        if self.web_view is None:
            return
        self.web_view.page().runJavaScript(
            "window.mshubSetPalette && window.mshubSetPalette(%s)" % self.bridge.getPalette()
        )

    def set_theme(self, theme: str) -> None:
        self.bridge.set_theme(theme)
        # The bridge retains the new palette; if the page is still loading the
        # loadFinished callback below will push it again after WebChannel exists.
        if self._page_loaded:
            self._push_palette(theme)

    def _copy_prompt(self) -> None:
        """v1.7.5：图谱页右上角「Agent连接提示词」。"""
        copy_agent_prompt(self.facade, self.agent_button, self.runner)
