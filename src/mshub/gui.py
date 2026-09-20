from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from .api import create_app


PRODUCT_NAME = "123 MSHub"


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            candidate.bind((host, port))
        except OSError:
            return False
    return True


def _wait_for_port(host: str, port: int, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("本地服务启动超时。")


def show_message(title: str, message: str, *, error: bool = False) -> None:
    """Show a dependency-free native message on Windows."""
    if sys.platform == "win32":
        import ctypes

        flags = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(None, message, title, flags)
        return
    print(f"{title}: {message}", file=sys.stderr)


def _browser_fallback(url: str, reason: str) -> None:
    webbrowser.open(url)
    show_message(
        f"{PRODUCT_NAME} 已在浏览器中打开",
        "桌面窗口无法启动，通常是因为系统缺少 Microsoft Edge WebView2 Runtime。\n\n"
        f"已改用默认浏览器打开：\n{url}\n\n"
        f"技术信息：{reason}\n\n"
        "使用期间请保持本提示框开启；完成后点击“确定”退出软件。",
    )


def launch(host: str = "127.0.0.1", port: int = 8766) -> None:
    if not _port_available(host, port):
        message = (
            f"端口 {port} 已被其他程序占用，{PRODUCT_NAME} 无法启动。\n\n"
            "请先退出已经运行的 123mshub，或关闭占用该端口的程序后重试。"
        )
        show_message(f"{PRODUCT_NAME} 启动失败", message, error=True)
        return

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(),
            host=host,
            port=port,
            log_level="warning",
            log_config=None,
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_port(host, port)
    url = f"http://{host}:{port}"
    try:
        import webview  # type: ignore

        webview.create_window(
            f"{PRODUCT_NAME}（Memory & Skill Hub） · 本地共享大脑管理器",
            url,
            width=1380,
            height=880,
            min_size=(960, 640),
        )
        webview.start()
    except Exception as exc:
        _browser_fallback(url, str(exc) or exc.__class__.__name__)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
