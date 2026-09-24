"""123UI v4.2 semantic tokens shared with the local graph island."""
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

DURATIONS = {"hover": 120, "fade": 200, "panel": 320}
PALETTES = {
    "light": dict(bg="#F7F5F2", sidebar="#EBE7E0", surface="#FFFFFF", raised="#FFFFFF",
                  inset="#F3F8FD", ink="#000A1E", muted="rgba(0,10,30,0.68)",
                  faint="rgba(0,10,30,0.52)", line="#E8E4DC", strong="#D9D3C6",
                  accent="#0156FC", selection="#CCDDFE", error="#B3261E",
                  error_soft="#FDE8E8", ok="#0E6B33", ok_soft="#DAFFE3",
                  glass="rgba(255,255,255,0.86)"),
    "dark": dict(bg="#030711", sidebar="#0C1730", surface="#0C1730", raised="#152344",
                 inset="#152344", ink="#FFFFFF", muted="rgba(255,255,255,0.72)",
                 faint="rgba(255,255,255,0.56)", line="#1B2E55", strong="#243862",
                 accent="#568EFD", selection="#243862", error="#FF8A80",
                 error_soft="rgba(255,138,128,0.14)", ok="#45D48A",
                 ok_soft="rgba(69,212,138,0.14)", glass="rgba(12,23,48,0.78)"),
}


def graph_palette(mode):
    token = PALETTES["dark" if mode == "dark" else "light"]
    return {"theme": mode, "background": token["surface"], "label": token["ink"]}


def stylesheet(mode):
    p = PALETTES[mode]
    return f"""
QWidget {{ background: {p['bg']}; color: {p['ink']}; font-family: 'DreamHanSansCN-W15', 'Segoe UI', 'Microsoft YaHei'; font-size: 14px; widget-animation-duration: {DURATIONS['hover']}; }}
QMainWindow, QDialog {{ background: {p['bg']}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QFrame#sidebar {{ background: {p['sidebar']}; border-right: 1px solid {p['line']}; }}
QFrame#surface, QFrame#emptyCard, QGroupBox {{ background: {p['surface']}; border: 1px solid {p['line']}; border-radius: 16px; }}
QFrame#emptyCard {{ border: 1px dashed {p['strong']}; }}
QGroupBox {{ margin-top: 14px; padding: 16px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 16px; color: {p['muted']}; }}
QLineEdit, QTextEdit, QTextBrowser, QPlainTextEdit, QComboBox {{
 background: {p['surface']}; color: {p['ink']}; border: 1px solid {p['strong']};
 border-radius: 10px; padding: 8px 10px; selection-background-color: {p['selection']};
 selection-color: {p['ink']}; placeholder-text-color: {p['faint']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 2px solid {p['accent']}; padding: 7px 9px; }}
QComboBox::drop-down {{ width: 24px; border: none; }}
QComboBox QAbstractItemView {{ background: {p['raised']}; color: {p['ink']}; selection-background-color: {p['selection']}; }}
QPushButton, QToolButton {{ min-height: 34px; padding: 0 12px; border-radius: 10px;
 border: 1px solid {p['strong']}; background: {p['surface']}; color: {p['ink']}; }}
QPushButton:hover, QToolButton:hover {{ background: {p['inset']}; border-color: {p['accent']}; }}
QPushButton:focus, QToolButton:focus {{ border: 2px solid {p['accent']}; }}
QPushButton:pressed, QToolButton:pressed {{ padding-top: 1px; background: {p['selection']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {p['faint']}; background: {p['bg']}; border-color: {p['line']}; }}
QPushButton#primary {{ background: #0156FC; color: #FFFFFF; border-color: #0156FC; font-weight: 600; }}
QPushButton#primary:hover {{ background: #0148D2; }}
QPushButton#primary:disabled {{ background: {p['strong']}; color: {p['faint']}; }}
QPushButton#danger {{ color: {p['error']}; border-color: {p['error']}; background: {p['error_soft']}; }}
QPushButton#stat {{ color: {p['accent']}; border-color: {p['line']}; border-radius: 12px; font-weight: 600; padding: 6px 12px; }}
QLabel#badge {{ color: {p['accent']}; background: {p['inset']}; border: 1px solid {p['selection']}; border-radius: 10px; padding: 3px 10px; font-size: 12px; }}
QLabel#error, QLabel#inboxWarning {{ color: {p['error']}; background: {p['error_soft']}; border-radius: 10px; padding: 8px; }}
QListWidget {{ background: transparent; border: none; outline: none; padding: 4px; }}
QListWidget::item {{ padding: 10px; border-radius: 10px; margin: 3px 0; }}
QListWidget::item:hover {{ background: {p['surface']}; }}
QListWidget::item:selected {{ background: {p['selection']}; color: {p['ink']}; }}
/* v1.6.0：导航栏加大加粗 + 图标对齐 + W20 字重 */
QListWidget#nav::item {{ padding: 12px 14px; font-family: 'DreamHanSansCN-W20', 'Segoe UI', 'Microsoft YaHei'; font-size: 15px; font-weight: 600; }}
QListWidget#nav::item:selected {{ background: {p['accent']}; color: #FFFFFF; }}
QListWidget#memoryList::item {{ background: {p['surface']}; border: 1px solid {p['line']}; border-radius: 10px; padding: 6px 10px; margin: 2px 0; }}
QListWidget#memoryList::item:selected {{ background: {p['inset']}; border-color: {p['accent']}; }}
/* v1.6.0：侧栏后台任务面板 */
QFrame#jobPanel {{ background: transparent; border-top: 1px solid {p['line']}; }}
QFrame#jobPanel QLabel#eyebrow {{ color: {p['muted']}; font-size: 11px; font-weight: 700; }}
QTableView {{ background: {p['surface']}; alternate-background-color: {p['inset']}; gridline-color: {p['line']}; border: 1px solid {p['line']}; border-radius: 10px; selection-background-color: {p['selection']}; selection-color: {p['ink']}; }}
/* v1.6.0：技能库/安全中心加行高（原来压得太紧难以操作） */
QTableView::item {{ padding: 12px 10px; }}
QHeaderView::section {{ background: {p['raised']}; color: {p['muted']}; padding: 10px; border: none; border-bottom: 1px solid {p['line']}; }}
QLabel#eyebrow {{ color: {p['accent']}; font-size: 11px; font-weight: 700; }}
QLabel#muted, QLabel#status {{ color: {p['muted']}; }}
QLabel#faint {{ color: {p['faint']}; }}
QLabel#title {{ color: #0156FC; font-family: 'DreamHanSansCN-W27', 'Noto Serif SC', 'Source Han Serif SC', 'SimSun'; font-size: 28px; font-weight: 700; }}
QTabWidget::pane {{ border: 1px solid {p['line']}; border-radius: 16px; padding: 16px; background: {p['surface']}; }}
QTabBar::tab {{ padding: 10px 18px; border-radius: 10px; color: {p['muted']}; background: {p['sidebar']}; }}
QTabBar::tab:selected {{ color: {p['accent']}; background: {p['surface']}; }}
QDockWidget {{ border: 1px solid {p['line']}; }}
QDockWidget::title {{ background: {p['glass']}; padding: 8px 12px; color: {p['muted']}; }}
QToolTip {{ background: {p['raised']}; color: {p['ink']}; border: 1px solid {p['line']}; padding: 8px 10px; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 0; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 0; }}
QScrollBar::handle {{ background: {p['strong']}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {p['faint']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p['strong']}; border-radius: 4px; background: {p['surface']}; }}
QCheckBox::indicator:checked {{ background: #0156FC; border: 2px solid {p['accent']}; }}
QSplitter::handle {{ background: {p['line']}; }}
"""


LIGHT_QSS = stylesheet("light")
DARK_QSS = stylesheet("dark")


class ThemeController(QObject):
    changed = Signal(str)

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = settings or QSettings("123mshub", "123mshub")
        self.mode = str(self.settings.value("theme", "system"))
        app = QApplication.instance()
        if app and hasattr(app.styleHints(), "colorSchemeChanged"):
            app.styleHints().colorSchemeChanged.connect(self._system_changed)

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
        return "dark" if QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128 else "light"

    @property
    def effective_mode(self):
        return self.system_mode() if self.mode == "system" else self.mode

    def apply(self, mode=None):
        if mode in {"light", "dark", "system"}:
            self.mode = mode
            self.settings.setValue("theme", mode)
        effective = self.effective_mode
        app = QApplication.instance()
        if app:
            app.setStyleSheet(DARK_QSS if effective == "dark" else LIGHT_QSS)
        self.changed.emit(effective)
        return effective
