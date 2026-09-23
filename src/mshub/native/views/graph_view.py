"""Local QWebEngine graph island."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from ..graph_bridge import GraphBridge
from ..memory_facade import MemoryFacade
from ..task_runner import TaskRunner

try:  # QtWebEngine is part of the native extra, but keep service imports usable without it.
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _WEB_ENGINE_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised on machines without native extra
    _WEB_ENGINE_AVAILABLE = False


if _WEB_ENGINE_AVAILABLE:
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
        self._build_ui()
        self._warm_graph_cache()

    def _warm_graph_cache(self) -> None:
        handle = self.runner.submit(self.facade.graph, "link")

        def ready(_identifier: int, payload: object) -> None:
            if isinstance(payload, dict):
                self.bridge.set_graph_cache("link", payload)

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
        self._profile = QWebEngineProfile("123mshub-native", self)
        self._profile.setPersistentStoragePath(str(config_dir))
        self._profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self._profile.setUrlRequestInterceptor(_LocalOnlyInterceptor(self._profile))
        page = QWebEnginePage(self._profile, self.web_view)
        channel = QWebChannel(page)
        channel.registerObject("mshub", self.bridge)
        page.setWebChannel(channel)
        self.web_view.setPage(page)
        self.web_view.urlChanged.connect(self._guard_url)
        self.web_view.loadFinished.connect(self._loaded)
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
        self.statusMessage.emit("图谱已加载" if ok else "图谱加载失败，请检查本地资源")

    def set_theme(self, theme: str) -> None:
        self.bridge.set_theme(theme)
        if self.web_view is not None:
            self.web_view.page().runJavaScript(f"window.mshubSetTheme && window.mshubSetTheme({theme!r})")
