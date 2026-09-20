"""文件系统瞬时锁重试原语（叶子模块，供 manifest/syncsafe/repository 共用）。

杀毒实时扫描、索引器对新建文件的短暂独占会以 PermissionError 形式打断
突发写入（2026-09-20 实测 [Errno 13] 打断整个技能更新）。所有重试只在
出错时才付时间成本，正常路径零开销。
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

RETRY_DELAYS = (0.2, 0.4, 0.8, 1.6, 3.2)


def retry_on_denied(action, description: str = ""):
    """PermissionError 退避重试：瞬时独占最长约几秒，五档共约 6 秒兜底。"""
    last: Exception | None = None
    for delay in RETRY_DELAYS:
        try:
            return action()
        except PermissionError as exc:
            last = exc
            time.sleep(delay)
    if last is not None:
        raise last
    return None


def robust_copy2(source: Path, destination: Path) -> None:
    retry_on_denied(lambda: shutil.copy2(source, destination), f"复制 {source}")


def robust_rename(source: Path, destination: Path) -> None:
    retry_on_denied(lambda: source.rename(destination), f"改名 {source}")


def robust_replace(source: Path, destination: Path) -> None:
    retry_on_denied(lambda: source.replace(destination), f"替换 {destination}")


def robust_unlink(path: Path) -> None:
    def _unlink() -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    retry_on_denied(_unlink, f"删除 {path}")


def robust_rmtree(path: Path) -> bool:
    def _rmtree() -> None:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass

    retry_on_denied(_rmtree, f"删除目录 {path}")
    return not path.exists()


def robust_read_bytes(path: Path) -> bytes:
    return retry_on_denied(path.read_bytes, f"读取 {path}")
