from __future__ import annotations

from PySide6.QtWidgets import QApplication

from mshub.native.theme import DARK_QSS, LIGHT_QSS, TYPOGRAPHY, ThemeController


def test_theme_controller_persists_and_applies(qapp: QApplication, tmp_path) -> None:
    from PySide6.QtCore import QSettings

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    controller = ThemeController(settings)
    assert controller.apply("dark") == "dark"
    assert "#0E0E0E" in qapp.styleSheet()
    assert controller.apply("light") == "light"
    assert "#FFFFFF" in qapp.styleSheet()
    assert LIGHT_QSS and DARK_QSS


def test_stitch_typography_scale_is_shared_by_both_themes() -> None:
    assert TYPOGRAPHY == {
        "display": 20,
        "brand": 14,
        "body": 12,
        "row": 12,
        "meta": 11,
        "micro": 10,
        "nav": 13,
        "count": 10,
        "section": 14,
    }
    for stylesheet in (LIGHT_QSS, DARK_QSS):
        assert "font-size: 20px" in stylesheet
        assert "font-size: 12px" in stylesheet
        assert "font-size: 11px" in stylesheet
        assert "font-size: 10px" in stylesheet
        assert "Segoe UI" in stylesheet
        assert "Dream Han Sans" not in stylesheet
