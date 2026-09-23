"""Safe local child-process defaults used by Git helpers.

The application is a windowed desktop program.  Git is an implementation
detail, so Windows must not create a console window for it.  Keeping this in
one small, explicit helper also makes the behaviour testable and avoids
scattered platform-specific flags.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any


def hidden_windows_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": _startupinfo(),
    }


def _startupinfo() -> subprocess.STARTUPINFO:
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0
    return info

