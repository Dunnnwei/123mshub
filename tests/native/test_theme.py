from __future__ import annotations

from PySide6.QtWidgets import QApplication

from mshub.native.theme import DARK_QSS, LIGHT_QSS, TYPOGRAPHY, ThemeController


def test_theme_controller_persists_and_applies(qapp: QApplication, tmp_path) -> None:
    from PySide6.QtCore import QSettings

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    controller = ThemeController(settings)
    assert controller.apply("dark") == "dark"
    assert "#0d1117" in qapp.styleSheet()
    assert controller.apply("light") == "light"
    assert "#ffffff" in qapp.styleSheet()
    assert LIGHT_QSS and DARK_QSS


def test_haui_typography_scale_is_shared_by_both_themes() -> None:
    assert TYPOGRAPHY == {
        "display": 24,
        "brand": 16,
        "body": 13,
        "row": 13,
        "meta": 12,
        "micro": 11,
        "nav": 13,
        "count": 11,
        "section": 15,
    }
    for stylesheet in (LIGHT_QSS, DARK_QSS):
        assert "font-size: 24px" in stylesheet
        assert "font-size: 12px" in stylesheet
        assert "font-size: 11px" in stylesheet
        assert "font-size: 13px" in stylesheet
        assert "Segoe UI" in stylesheet
        assert "Dream Han Sans" not in stylesheet
