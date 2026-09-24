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
        args_list = argv if argv is not None else sys.argv[1:]
        if "--smoke-graph" not in args_list and "--smoke-float" not in args_list and "--smoke-float-stable" not in args_list:
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
    parser.add_argument("--smoke-float", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-float-stable", action="store_true", help=argparse.SUPPRESS)  # v1.6.0：模拟"页面稳定后"场景，等 8s 再查呼吸
    args = parser.parse_args(argv)
    append_smoke("args-parsed")

    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QMessageBox

    from .session_config import SessionConfigStore
    from .memory_facade import MemoryFacade

    from .branding import apply_brand_icon, set_windows_app_id
    set_windows_app_id()
    app = QApplication.instance() or QApplication(sys.argv)
    apply_brand_icon("light")
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
    if args.smoke_graph or args.smoke_float or args.smoke_float_stable:
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
            if "失败" in message or "缺失" in message or "脚本错误" in message:
                failure["message"] = message

        graph.statusMessage.connect(record_status)
        def stop_smoke() -> None:
            append_smoke("timer")
            app.quit()

        def check_graph_ready() -> None:
            if graph.web_view is None:
                return
            graph.web_view.page().runJavaScript(
                "JSON.stringify({ready:Boolean(window.mshubGraphReady),nodes:window.mshubGraphNodeCount||0,edges:window.mshubGraphEdgeCount||0})",
                lambda value: _finish_graph_check(value),
            )

        float_hashes: list[str] = []

        def grab_float_frame(tag: str) -> None:
            """抓 QWebEngineView 当前帧像素，验证 v1.5.0 漂移动效在上屏。"""
            if graph.web_view is None:
                return
            image = graph.web_view.grab().toImage()
            import hashlib
            ptr = image.bits()
            data = ptr.tobytes() if hasattr(ptr, "tobytes") else bytes(ptr)
            digest = hashlib.md5(data).hexdigest()
            float_hashes.append(digest)
            append_smoke(f"float-frame-{tag}={digest}")

        def finish_float_check() -> None:
            alive = len(float_hashes) == 2 and float_hashes[0] != float_hashes[1]
            append_smoke(f"float-alive={alive}")
            print("DRIFT_ALIVE" if alive else "DRIFT_DEAD")
            app.exit(0 if alive else 4)

        def _finish_graph_check(value: object) -> None:
            try:
                import json
                result = json.loads(str(value))
            except (TypeError, ValueError):
                result = {"ready": False}
            append_smoke(f"graph-ready={result.get('ready')} nodes={result.get('nodes', 0)} edges={result.get('edges', 0)}")
            if not result.get("ready"):
                failure["message"] = "图谱脚本未完成 WebChannel/Sigma 渲染"
                app.quit()
                return
            if args.smoke_float or args.smoke_float_stable:
                # 先做一次桥接数据诊断：直接调 getGraph 看页面侧拿到的真实节点数，
                # 分辨"数据没到页面"与"到了但渲染为 0"。
                graph.web_view.page().runJavaScript(
                    "window.mshubDiagCount ? window.mshubDiagCount() : 'no-diag'",
                    lambda value: append_smoke(f"diag-count={value}"),
                )
                graph.web_view.page().runJavaScript(
                    "window.mshubDiagBridge ? window.mshubDiagBridge((r) => { window.__diagBridgeResult = r }) : 'no-diag'",
                    lambda _v: None,
                )
                def read_diag_bridge() -> None:
                    graph.web_view.page().runJavaScript(
                        "window.__diagBridgeResult || 'pending'",
                        lambda value: append_smoke(f"diag-bridge={value}"),
                    )
                QTimer.singleShot(1500, read_diag_bridge)
                if args.smoke_float_stable:
                    # v1.6.0：模拟用户场景——页面完全稳定后（8s）再检查呼吸是否还活着。
                    # 先抓初始诊断，等 8s 后再抓一次诊断 + 两帧像素比对。
                    def dump_diag_float(tag: str) -> None:
                        page = graph.web_view.page()
                        if page is None:
                            append_smoke(f"diag-float-{tag}=no-page")
                            return
                        append_smoke(f"diag-float-{tag}-calling")
                        def _cb(value: object) -> None:
                            append_smoke(f"diag-float-{tag}={value}")
                        page.runJavaScript(
                            "window.mshubDiagFloat ? window.mshubDiagFloat() : 'no-diag-float'",
                            _cb,
                        )
                    QTimer.singleShot(800, lambda: dump_diag_float("initial"))
                    QTimer.singleShot(8000, lambda: dump_diag_float("stable"))
                    QTimer.singleShot(8000, lambda: grab_float_frame("stable-t1"))
                    QTimer.singleShot(10000, lambda: grab_float_frame("stable-t2"))
                    QTimer.singleShot(10400, finish_float_check)
                else:
                    # 图谱已 ready。file:// 协议走同步 FA2，此刻已收敛，漂浮应已接管。
                    # 连抓两帧（间隔 2s），漂移上屏则像素必变。
                    QTimer.singleShot(800, lambda: grab_float_frame("t1"))
                    QTimer.singleShot(2800, lambda: grab_float_frame("t2"))
                    QTimer.singleShot(3200, finish_float_check)
            else:
                app.quit()

        QTimer.singleShot(5000 if args.smoke_graph else 15000, stop_smoke if args.smoke_graph else (lambda: None))
        # smoke-float 需要等异步暖缓存 + WebChannel 握手 + 页面 render 完成，
        # 2.5s 对真实库偏紧（曾实测 nodes=0 的假就绪），放宽到 4.5s。
        QTimer.singleShot(2500 if args.smoke_graph else 4500, check_graph_ready)
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
