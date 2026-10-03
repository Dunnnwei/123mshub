"""123ui5.0 Hermes Mono Clean structure with Indigo/Violet brand tokens."""

from __future__ import annotations

import json
from pathlib import Path

from mshub.native.main_window import MainWindow
from mshub.native.theme import DARK_QSS, LIGHT_QSS, PALETTES


ROOT = Path(__file__).resolve().parents[2]


def test_hermes_mono_tokens_match_design_token_source() -> None:
    tokens = json.loads((ROOT / "src/mshub/native/design_tokens.json").read_text(encoding="utf-8"))
    expected = {
        "light": {
            "bg": "#FFFFFF", "sidebar": "#F5F5F5", "surface": "#FFFFFF", "inset": "#F9F9F9",
            "ink": "#161616", "muted": "#737377", "line": "#E1E1E3", "action": "#6366F1",
            "accent": "#7C3AED", "selection": "#E9E7FF", "error": "#B94A3A",
        },
        "dark": {
            "bg": "#0E0E0E", "sidebar": "#0A0A0A", "surface": "#141414", "inset": "#1E1E1E",
            "ink": "#EAEAEA", "muted": "#C8C8C8", "line": "#2A2A2A", "action": "#6366F1",
            "accent": "#A78BFA", "selection": "#312E81", "error": "#A84040",
        },
    }
    for mode, values in expected.items():
        assert tokens[mode].items() >= values.items()
        assert PALETTES[mode].items() >= values.items()


def test_hermes_qss_removes_chromatic_and_elevation_layers() -> None:
    for stylesheet in (LIGHT_QSS, DARK_QSS):
        assert "#6366F1" in stylesheet
        assert "#7C3AED" in stylesheet
        assert "qlineargradient" in stylesheet
        assert "QFrame#jobPanel { background: transparent; border: none;" in stylesheet
        assert "QToolButton#jobToggle:focus { background: transparent; border: none; outline: none; }" in stylesheet
        assert "QListWidget#memoryList:focus { border: none; outline: none; }" in stylesheet
        assert "border-radius: 0" in stylesheet


def test_theme_switch_keeps_flat_task_and_memory_focus_contract(qapp, native_facade) -> None:
    window = MainWindow(native_facade)
    try:
        for mode, background in (("light", "#FFFFFF"), ("dark", "#0E0E0E")):
            assert window.theme.apply(mode) == mode
            assert background in qapp.styleSheet()
            assert window.job_panel.graphicsEffect().blurRadius() == 0
            assert window.sidebar.graphicsEffect().blurRadius() == 0
    finally:
        window.close()


def test_built_graph_is_mono_and_uses_local_hashed_assets() -> None:
    index = ROOT / "src/mshub/native/graph/index.html"
    html = index.read_text(encoding="utf-8")
    assert 'content="#FFFFFF"' in html
    assert "assets/" in html
    assets = list((index.parent / "assets").glob("*.css"))
    assert assets
    css = assets[0].read_text(encoding="utf-8")
    assert "#0E0E0E" in css and "#FFFFFF" in css
    assert "#6366F1" in css and "#7C3AED" in css and "backdrop-filter" not in css
