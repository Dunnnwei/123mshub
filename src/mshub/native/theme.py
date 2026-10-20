"""HAUI native adapter. Theme values are exported from the actual HAUI resolver."""
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from .haui import ROOT as HAUI_ROOT, catalog, resolve

DURATIONS = {"hover": 100, "fade": 180, "panel": 220, "row": 100}
TYPOGRAPHY = {"display": 24, "brand": 16, "body": 13, "row": 13,
              "meta": 12, "micro": 11, "nav": 13, "count": 11, "section": 15}
PALETTES = {mode: dict(resolve(mode=mode)["qt"]) for mode in ("light", "dark")}
_font_app = None


def system_font_family() -> str:
    family = (QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
              if QApplication.instance() else "Segoe UI")
    return "Segoe UI" if family in {"Sans Serif", "sans-serif", ""} else family


def ensure_brand_fonts() -> str:
    global _font_app
    app = QApplication.instance()
    if app is not None and _font_app is not app:
        for path in (HAUI_ROOT / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(path))
        _font_app = app
    return system_font_family()


def current_palette() -> dict:
    """Constant-time lookup; never guess the theme by scanning stylesheet colors."""
    app = QApplication.instance()
    return PALETTES["dark" if app and app.property("mshubTheme") == "dark" else "light"]


def graph_palette(mode: str) -> dict:
    p = PALETTES["dark" if mode == "dark" else "light"]
    return {"theme": mode, "system": "HAUI", "background": p["surface"],
            "canvas": p["bg"], "label": p["ink"], "muted": p["muted"],
            "line": p["graph_line"], "accent": p["accent"], "selection": p["selection"],
            "inset": p["inset"], "controls": p,
            "action_gradient_start": p["action"], "action_gradient_end": p["action"],
            "types": {key: p[key] for key in ("user", "project", "reference", "feedback")}}


def starfield_colors(mode: str) -> tuple[str, str, str, bool]:
    p = PALETTES["dark" if mode == "dark" else "light"]
    return p["bg"], p["star_dot"], p["star_bright"], mode == "dark"


_QSS = (HAUI_ROOT / "native.qss").read_text(encoding="utf-8")


def stylesheet(mode: str) -> str:
    p = PALETTES["dark" if mode == "dark" else "light"]
    tick = (HAUI_ROOT / ("check-light.svg" if p["on_action"] == "#ffffff" else "check-dark.svg")).as_posix()
    chevron = (HAUI_ROOT / ("chevron-light.svg" if QColor(p["ink"]).lightnessF() > .5 else "chevron-dark.svg")).as_posix()
    text = _QSS.replace("@font", system_font_family()).replace("@tick", tick).replace("@chevron", chevron)
    for key, value in sorted(p.items(), key=lambda item: -len(item[0])):
        text = text.replace("@" + key, str(value))
    return text


class ThemeController(QObject):
    changed = Signal(str)

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        ensure_brand_fonts()
        self.settings = settings or QSettings("123mshub", "123mshub")
        mode = str(self.settings.value("theme", "system"))
        self.mode = mode if mode in {"system", "light", "dark"} else "system"
        palette = str(self.settings.value("haui/palette", "nous"))
        self.palette = palette if palette in catalog()["themes"] else "nous"
        accent = str(self.settings.value("haui/accent", "default"))
        self.accent = accent if accent in {a["id"] for a in catalog()["accents"]} else "default"
        self._select_palette()
        app = QApplication.instance()
        if app and hasattr(app.styleHints(), "colorSchemeChanged"):
            app.styleHints().colorSchemeChanged.connect(self._system_changed)

    def _select_palette(self):
        for mode in ("light", "dark"):
            PALETTES[mode].clear()
            PALETTES[mode].update(resolve(self.palette, mode, self.accent)["qt"])

    def _system_changed(self, *_):
        if self.mode == "system":
            self.apply()

    @staticmethod
    def system_mode():
        app = QApplication.instance()
        scheme = getattr(app.styleHints(), "colorScheme", None) if app else None
        if callable(scheme):
            name = str(scheme()).lower()
            if name.endswith("dark"):
                return "dark"
            if name.endswith("light"):
                return "light"
        return "light"

    @property
    def effective_mode(self):
        return self.system_mode() if self.mode == "system" else self.mode

    def apply(self, mode=None, *, palette=None, accent=None):
        if mode in {"light", "dark", "system"}:
            self.mode = mode
            self.settings.setValue("theme", mode)
        if palette in catalog()["themes"]:
            self.palette = palette
            self.settings.setValue("haui/palette", palette)
        if accent in {a["id"] for a in catalog()["accents"]}:
            self.accent = accent
            self.settings.setValue("haui/accent", accent)
        self._select_palette()
        effective = self.effective_mode
        app = QApplication.instance()
        if app:
            app.setProperty("mshubTheme", effective)
            p = PALETTES[effective]
            native = QPalette(app.palette())
            for role, token in ((QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.Base, "surface"),
                                (QPalette.ColorRole.Text, "ink"), (QPalette.ColorRole.WindowText, "ink"),
                                (QPalette.ColorRole.Button, "control"), (QPalette.ColorRole.ButtonText, "ink"),
                                (QPalette.ColorRole.Highlight, "selection"), (QPalette.ColorRole.HighlightedText, "ink")):
                native.setColor(role, QColor(p[token]))
            app.setPalette(native)
            app.setStyleSheet(stylesheet(effective))
        self.changed.emit(effective)
        return effective


LIGHT_QSS = stylesheet("light")
DARK_QSS = stylesheet("dark")
