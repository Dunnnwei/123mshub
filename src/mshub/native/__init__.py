"""PySide6 原生桌面壳适配层。

The existing ``mshub`` modules remain the source of truth.  This package is
deliberately a leaf package: core services never import it back.
"""

from __future__ import annotations

from .. import __version__

NATIVE_VERSION = __version__

__all__ = ["NATIVE_VERSION"]
