"""v1.10.0D（Stitch Silk/Mica）：统一静态画布背景。

用户提供了参考 SVG（pattern-organic-478055.svg：1920×1080、922 颗 #0156FC 点、
半径 2.2~3.6、透明度 0.2、有机聚簇分布），并明确"代码更轻量就换代码"——本模块
用**值噪声密度场 + 种子随机抖动网格**程序化复刻该形态：

- 分布：44px 基准网格、±13px 抖动，仅保留噪声值高于阈值的点 → 天然聚簇与留白，
  与参考图同量级的密度（1280×820 约 500 颗，1920×1080 约 900 颗）；
- 呼吸：与记忆图示（sigma.js）同一节奏体系——亮度周期 3.5~5.5s、半径周期
  4.1~7.0s，每颗点独立相位（哈希派生），半径脉动 ±30%；
- 性能：20fps 定时器仅在可见时运转；静态底色+暗角按尺寸缓存为 QPixmap，
  每帧只画点；窗口隐藏即停表。

v1.10.0C 的点阵背景属于另一套视觉语言，会把模板中的软质留白变成动态
装饰。本版本保留这个承载控件和 ``set_colors`` 接口，改为纯色画布，让
Silk/Mica 的层级、阴影和控件按模板成为视觉重点。图谱页自身的闲置微动
仍由 Web 图谱控制，不受此画布调整影响。
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
        self._base = QColor("#0B0E14")
        self._dot = QColor("#6366F1")
        self._bright = QColor("#A5B4FC")
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
