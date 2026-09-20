from __future__ import annotations

from multiprocessing import freeze_support

from mshub.gui import PRODUCT_NAME, launch, show_message


def main() -> None:
    freeze_support()
    try:
        launch(host="127.0.0.1", port=8766)
    except Exception as exc:
        show_message(
            f"{PRODUCT_NAME} 启动失败",
            f"{exc}\n\n如果问题持续，请查看 README 的“常见问题”。",
            error=True,
        )


if __name__ == "__main__":
    main()
