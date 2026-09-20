from __future__ import annotations

import sys
from types import SimpleNamespace

from mshub import gui


def test_browser_fallback_opens_url_and_explains_webview2(monkeypatch) -> None:
    opened: list[str] = []
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(gui.webbrowser, "open", opened.append)
    monkeypatch.setattr(
        gui,
        "show_message",
        lambda title, message, **_: messages.append((title, message)),
    )

    gui._browser_fallback("http://127.0.0.1:8766", "WebView2 unavailable")

    assert opened == ["http://127.0.0.1:8766"]
    assert "WebView2 Runtime" in messages[0][1]
    assert "http://127.0.0.1:8766" in messages[0][1]


def test_launch_falls_back_when_pywebview_cannot_start(monkeypatch) -> None:
    class FakeServer:
        should_exit = False

        def __init__(self, _config) -> None:
            pass

        def run(self) -> None:
            return

    fallback: list[tuple[str, str]] = []
    monkeypatch.setattr(gui, "_port_available", lambda *_: True)
    monkeypatch.setattr(gui, "_wait_for_port", lambda *_: None)
    monkeypatch.setattr(gui, "create_app", lambda: object())
    monkeypatch.setattr(gui.uvicorn, "Config", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(gui.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(gui, "_browser_fallback", lambda url, reason: fallback.append((url, reason)))
    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(create_window=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("WebView2 unavailable")
        )),
    )

    gui.launch()

    assert fallback == [("http://127.0.0.1:8766", "WebView2 unavailable")]


def test_launch_reports_occupied_port(monkeypatch) -> None:
    messages: list[tuple[str, str, bool]] = []
    monkeypatch.setattr(gui, "_port_available", lambda *_: False)
    monkeypatch.setattr(
        gui,
        "show_message",
        lambda title, message, *, error=False: messages.append((title, message, error)),
    )

    gui.launch()

    assert messages[0][2] is True
    assert "8766" in messages[0][1]
