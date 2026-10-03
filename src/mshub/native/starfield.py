"""v1.10.6 Hermes Mono：统一静态画布背景。

保留历史 ``set_colors`` 接口和可见性生命周期，画布自身采用 Hermes Agent
``Mono Clean`` 的中性色底。图谱页的闲置微动仍由 Web 图谱控制，原有窗口布局
与功能入口不变。
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

_SEED = 123_0455  # 固定星空：每次启动同一片点阵
_GRID = 44.0
_JITTER = 13.0
_NOISE_SCALE = 0.0042
_NOISE_THRESHOLD = 0.34
_BRIGHT_RATIO = 0.10  # 一成点为亮色"星光"


def _hash01(n: int) -> float:
    """确定性 [0,1) 哈希——点阵与相位唯一的随机源。"""
    h = (n * 374761393 + _SEED * 668265263) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 0x100000000


def _lattice(ix: int, iy: int) -> float:
    return _hash01(((ix & 0xFFFF) << 16) ^ (iy & 0xFFFF))


def _smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


def _value_noise(x: float, y: float) -> float:
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = _smooth(x - ix), _smooth(y - iy)
    a, b = _lattice(ix, iy), _lattice(ix + 1, iy)
    c, d = _lattice(ix, iy + 1), _lattice(ix + 1, iy + 1)
    return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy


class StarfieldBackground(QWidget):
    """程序化呼吸点阵底板；承载主布局（侧栏/内容浮于其上）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workspace")
        self._dots: list[tuple[float, float, float, float, float, float, float, bool]] = []
        self._base_pixmap: QPixmap | None = None
        self._t0 = time.monotonic()
        self._base = QColor("#0E0E0E")
        self._dot = QColor("#808080")
        self._bright = QColor("#B0B0B0")
        self._dark_mode = True
        self._timer = QTimer(self)
        self._timer.setInterval(50)  # 20fps：呼吸周期 3.5~7s，足够顺滑
        self._timer.timeout.connect(lambda: self.isVisible() and self.update())

    def set_colors(self, base: str, dot: str, bright: str, dark_mode: bool) -> None:
        self._base = QColor(base)
        self._dot = QColor(dot)
        self._bright = QColor(bright)
        self._dark_mode = dark_mode
        self._dots = []
        self._base_pixmap = None
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        super().showEvent(event)
        self._timer.stop()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        super().hideEvent(event)
        self._timer.stop()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        super().resizeEvent(event)
        self._regenerate()
        self._base_pixmap = None

    def _regenerate(self) -> None:
        self._dots = []

    def _paint_base(self) -> None:
        """静态底（基色 + 边缘暗角）按当前尺寸缓存。"""
        if self._base_pixmap is not None and self._base_pixmap.size() == self.size():
            return
        pixmap = QPixmap(self.size())
        pixmap.fill(self._base)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.end()
        self._base_pixmap = pixmap

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        painter = QPainter(self)
        self._paint_base()
        if self._base_pixmap is not None:
            painter.drawPixmap(0, 0, self._base_pixmap)
        painter.end()
