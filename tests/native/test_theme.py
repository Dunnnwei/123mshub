from __future__ import annotations

from PySide6.QtWidgets import QApplication

from mshub.native.theme import DARK_QSS, LIGHT_QSS, ThemeController


def test_theme_controller_persists_and_applies(qapp: QApplication, tmp_path) -> None:
    from PySide6.QtCore import QSettings

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    controller = ThemeController(settings)
    assert controller.apply("dark") == "dark"
    assert "#030711" in qapp.styleSheet()
    assert controller.apply("light") == "light"
    assert "#F7F5F2" in qapp.styleSheet()
    assert LIGHT_QSS and DARK_QSS
