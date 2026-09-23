"""Native application entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def show_duplicate_message(timeout_ms: int = 4000) -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox

    dialog = QMessageBox(QMessageBox.Icon.Information, "123 MSHub 已在运行",
                         "原生程序已在运行，请使用现有窗口。此提示将在 4 秒后关闭。")
    timer = QTimer(dialog)
    timer.setSingleShot(True)
    timer.timeout.connect(dialog.accept)
    timer.start(timeout_ms)
    dialog.exec()


def main(argv: list[str] | None = None) -> int:
    smoke_log = Path(os.environ.get("TEMP", ".")) / "123mshub-native-smoke.log"

    def append_smoke(message: str) -> None:
        if "--smoke-graph" not in (argv if argv is not None else sys.argv[1:]):
            return
        with smoke_log.open("a", encoding="utf-8") as handle:
            handle.write(f"{message}\n")

    append_smoke("main-enter")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # keep the CLI/service installation usable without native extra
        append_smoke(f"import-error={exc}")
        print("原生界面需要安装可选依赖：python -m pip install 'mshub[native]'", file=sys.stderr)
        print(f"详细原因：{exc}", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(prog="123mshub-native", description="123 MSHub PySide6 原生壳")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--repo", help="仅本次会话使用的仓库根目录，不修改已存配置")
    group.add_argument("--repo-and-save", help="使用此仓库并明确保存为默认仓库")
    parser.add_argument("--config-dir", type=Path, help="独立配置目录（不读写系统钥匙串，供测试/便携会话）")
    parser.add_argument("--smoke-graph", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    append_smoke("args-parsed")

    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QMessageBox

    from .session_config import SessionConfigStore
    from .memory_facade import MemoryFacade

    app = QApplication.instance() or QApplication(sys.argv)
    append_smoke("qapplication-created")
    app.setApplicationName("123 MSHub")
    app.setOrganizationName("123mshub")
    store = SessionConfigStore(args.config_dir, repo=args.repo or "", isolated=args.config_dir is not None)
    append_smoke("config-created")
    store.config_dir.mkdir(parents=True, exist_ok=True)
    # File-based single-instance lock: no TCP endpoint and no desktop popup
    # retry loop.  A second invocation reports once and exits.
    lock = QLockFile(str(store.config_dir / "native-instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        append_smoke("lock-failed")
        show_duplicate_message()
        return 0
    if args.repo_and_save:
        store.save({"repo_root": args.repo_and_save})
    facade = MemoryFacade(store)
    if args.smoke_graph:
        # Packaging QA path: instantiate the real local WebEngine island and
        # let it load its qrc WebChannel bootstrap and graph assets. This is
        # intentionally hidden from the normal product CLI.
        from .views.graph_view import GraphView

        append_smoke("start")

        graph = GraphView(facade)
        append_smoke(f"graph-created web_view={graph.web_view is not None}")
        graph.resize(960, 640)
        graph.show()
        if graph.web_view is None:
            lock.unlock()
            append_smoke("no-webengine")
            print("图谱 WebEngine 未创建（请使用 Windows 图形平台运行 smoke-graph）", file=sys.stderr)
            return 3
        failure = {"message": ""}

        def record_status(message: str) -> None:
            append_smoke(f"status={message}")
            if "失败" in message or "缺失" in message:
                failure["message"] = message

        graph.statusMessage.connect(record_status)
        def stop_smoke() -> None:
            append_smoke("timer")
            app.quit()

        QTimer.singleShot(5000, stop_smoke)
        append_smoke("before-exec")
        result = int(app.exec())
        append_smoke(f"after-exec={result}")
        lock.unlock()
        if failure["message"]:
            print(failure["message"], file=sys.stderr)
            return 3
        return result

    from .main_window import MainWindow

    window = MainWindow(facade)
    window.show()
    QTimer.singleShot(0, window.startup)
    try:
        return int(app.exec())
    finally:
        lock.unlock()
