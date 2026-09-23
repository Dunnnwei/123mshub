"""Minimal QtQml hook for the Widgets + WebEngine native shell.

The stock PyInstaller hook copies every QML module shipped in the PySide6
wheel.  The WebEngine widgets use the Qt runtime libraries but do not load
the unrelated Charts, 3D, PDF, Multimedia, and Quick Controls QML trees.
Collecting those trees also pulls their module DLLs into the onedir bundle.
QtWebEngine's own resources remain collected by its dedicated hook.
"""

from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
