"""123mshub Native design tokens shared by Qt and the local graph island."""
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

DURATIONS = {"hover": 120, "fade": 180, "panel": 220}

_TOKENS_PATH = Path(__file__).with_name("design_tokens.json")

# ocr 审查修复：design_tokens.json 缺失/损坏时（打包或环境包部署异常）曾静默
# 返回空 dict，下游 stylesheet()/graph_palette() 直接 KeyError 且远离根因。
# 嵌一份与 json 同源的完整默认令牌作兜底：文件丢了 UI 也能起来（颜色不漂移）。
_FALLBACK_TOKENS = {
    "light": {"bg": "#F2F4F8", "sidebar": "#F7F8FA", "surface": "#FFFFFF", "raised": "#FFFFFF", "inset": "#F3F5F8",
              "ink": "#171B23", "muted": "#4E5766", "faint": "#606A7A", "line": "#E2E6EE", "strong": "#828DA0",
              "action": "#0156FC", "on_action": "#FFFFFF", "accent": "#0148D2", "selection": "#E7F0FF",
              "error": "#AF2424", "error_soft": "#FBEAEA", "ok": "#116B3A", "ok_soft": "#E5F4EB",
              "warning": "#88420A", "warning_soft": "#FBF0DD", "user": "#7144B8", "project": "#0148D2",
              "reference": "#006F72", "feedback": "#97500A", "glass": "#F7F8FA", "action_hover": "#0148D2",
              "action_pressed": "#003CAF"},
    "dark": {"bg": "#0B0E14", "sidebar": "#0F1219", "surface": "#141926", "raised": "#1B2232", "inset": "#1B2232",
             "ink": "#E9ECF4", "muted": "#A7B0C2", "faint": "#9AA6BC", "line": "#303A4D", "strong": "#73839E",
             "action": "#0156FC", "on_action": "#FFFFFF", "accent": "#8DB5FF", "selection": "#172E57",
             "error": "#FFAAA3", "error_soft": "#3D242A", "ok": "#58DFAC", "ok_soft": "#17392F",
             "warning": "#F5C46A", "warning_soft": "#40341F", "user": "#B8A0FC", "project": "#8DB5FF",
             "reference": "#6ED7D0", "feedback": "#F5BD74", "glass": "#1B2232", "action_hover": "#0148D2",
             "action_pressed": "#003CAF"},
}


def _load_tokens() -> dict:
    try:
        loaded = json.loads(_TOKENS_PATH.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or not loaded.get("light") or not loaded.get("dark"):
            raise ValueError("design tokens 不完整")
        return loaded
    except (OSError, ValueError) as exc:
        import logging

        logging.getLogger(__name__).error("设计令牌文件加载失败，使用内置默认令牌：%s", exc)
        return json.loads(json.dumps(_FALLBACK_TOKENS))

_DREAM_FONT_FAMILY = "Dream Han Sans CN"
_dream_fonts_loaded = False


def ensure_brand_fonts() -> str:
    """Load the four installed Dream Han Sans weights and return their family.

    The files are separate faces in Windows Fonts but share one real Qt family
    name.  Loading them through QFontDatabase makes the W1/W15/W20/W27 style
    names available to Qt instead of silently falling back to Segoe UI.
    """

    global _dream_fonts_loaded
    if _dream_fonts_loaded:
        return _DREAM_FONT_FAMILY
    # ocr 审查修复：字体未装时原来每次调用都重扫字体目录+枚举系统字体，
    # 而 resizeEvent 会高频调用（拖窗口卡顿）——记住"已尝试"，失败直接回退。
    if getattr(ensure_brand_fonts, "_checked", False):
        return "Segoe UI"
    ensure_brand_fonts._checked = True
    candidates = (
        # v1.8.0（审查 L-1）：非标准安装盘时 SystemRoot 环境变量兜底
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts",
        Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
    )
    for weight in ("W1", "W15", "W20", "W27"):
        filename = f"DreamHanSansCN-{weight}.ttf"
        path = next((root / filename for root in candidates if (root / filename).is_file()), None)
        if path is not None:
            QFontDatabase.addApplicationFont(str(path))
    _dream_fonts_loaded = _DREAM_FONT_FAMILY in QFontDatabase.families()
    return _DREAM_FONT_FAMILY if _dream_fonts_loaded else "Segoe UI"
PALETTES = _load_tokens()
PALETTES.setdefault("light", {})
PALETTES.setdefault("dark", {})


# v1.8.0（审查 UI 项）：视图层行内 setStyleSheet 引用的语义色单一来源
ROW_TEXT_ON_SELECTION = "#FFFFFF"
MUTED_TEXT_ON_SELECTION = "#E9ECF4"

def current_palette() -> dict:
    """v1.8.0（审查 UI 项）：视图层行内样式的取色入口——亮暗跟随应用样式表。"""
    app = QApplication.instance()
    stylesheet = app.styleSheet() if app else ""
    mode = "dark" if "#0B0E14" in stylesheet else "light"
    return PALETTES.get(mode, {})

def graph_palette(mode):
    token = PALETTES["dark" if mode == "dark" else "light"]
    return {
        "theme": mode,
        "background": token["surface"],
        "canvas": token["bg"],
        "label": token["ink"],
        "muted": token["muted"],
        "line": token["line"],
        "accent": token["accent"],
        "selection": token["selection"],
        "types": {key: token[key] for key in ("user", "project", "reference", "feedback")},
    }


def stylesheet(mode):
    # Build the stylesheet at import time without touching QFontDatabase; the
    # application font registry is only safe to query after QApplication exists.
    family = _DREAM_FONT_FAMILY
    p = PALETTES[mode]
    if mode == "dark":
        ghost_ink, ghost_line, ghost_hover = "#FFFFFF", "rgba(255,255,255,0.75)", "rgba(255,255,255,0.10)"
    else:
        ghost_ink, ghost_line, ghost_hover = p["ink"], "rgba(23,27,35,0.45)", p["selection"]
    return f"""
QWidget {{ background: {p['bg']}; color: {p['ink']}; font-family: '{family}', 'Segoe UI', 'Microsoft YaHei'; font-size: 14px; font-weight: 500; widget-animation-duration: {DURATIONS['hover']}; }}
QMainWindow, QDialog {{ background: {p['bg']}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
/* v1.7.4：侧边栏改浮动面板——四边 16px 外边距由主窗口布局负责，这里画
   圆角 20 的面板底色与描边；柔和投影用 QGraphicsDropShadowEffect（QSS 不支持阴影） */
QFrame#sidebar {{ background: {p['sidebar']}; border: 1px solid {p['line']}; border-radius: 20px; }}
QFrame#surface, QFrame#emptyCard, QGroupBox {{ background: {p['surface']}; border: 1px solid {p['line']}; border-radius: 12px; }}
QWidget#memoryRow {{ background: transparent; }}
QFrame#emptyCard {{ border: 1px dashed {p['strong']}; }}
QGroupBox {{ margin-top: 14px; padding: 16px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 16px; color: {p['ink']}; font-size: 13px; font-weight: 700; }}
QLineEdit, QTextEdit, QTextBrowser, QPlainTextEdit, QComboBox {{
 background: {p['surface']}; color: {p['ink']}; border: 1px solid {p['strong']};
 border-radius: 8px; padding: 8px 10px; selection-background-color: {p['selection']};
 selection-color: {p['ink']}; placeholder-text-color: {p['faint']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 2px solid {p['accent']}; padding: 7px 9px; }}
QComboBox::drop-down {{ width: 24px; border: none; }}
QComboBox QAbstractItemView {{ background: {p['raised']}; color: {p['ink']}; selection-background-color: {p['selection']}; }}
QPushButton, QToolButton {{ min-height: 36px; padding: 0 12px; border-radius: 8px;
 border: 1px solid {p['strong']}; background: {p['surface']}; color: {p['ink']}; font-size: 13px; font-weight: 550; }}
QPushButton:hover, QToolButton:hover {{ background: {p['inset']}; border-color: {p['accent']}; }}
QPushButton:focus, QToolButton:focus {{ border: 2px solid {p['accent']}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {p['selection']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {p['faint']}; background: {p['bg']}; border-color: {p['line']}; }}
QPushButton#primary {{ background: {p['action']}; color: {p['on_action']}; border-color: {p['action']}; font-weight: 700; }}
QPushButton#primary:hover {{ background: {p['action_hover']}; border-color: {p['action_hover']}; }}
QPushButton#primary:focus {{ border: 2px solid {p['ink']}; }}
QPushButton#primary:pressed {{ background: {p['action_pressed']}; }}
QPushButton#primary:disabled {{ background: {p['strong']}; color: {p['faint']}; }}
/* v1.7.5：幽灵按钮（描边空心）——与右上角皇家蓝「Agent连接提示词」并排的次级动作。
   暗色按用户模板白字白边；亮色主题下纯白会没入浅底，同构换成墨色字+半透明描边。 */
QPushButton#ghost {{ color: {ghost_ink}; border: 1px solid {ghost_line}; background: transparent; font-weight: 600; }}
QPushButton#ghost:hover {{ background: {ghost_hover}; border-color: {p['accent']}; color: {p['accent']}; }}
QPushButton#ghost:pressed {{ background: {p['selection']}; }}
QPushButton#ghost:disabled {{ color: {p['faint']}; border-color: {p['line']}; }}
QPushButton#danger {{ color: {p['error']}; border-color: {p['error']}; background: {p['error_soft']}; font-weight: 650; }}
QPushButton#stat {{ color: {p['accent']}; border-color: {p['line']}; border-radius: 10px; font-size: 13px; font-weight: 650; min-height: 40px; padding: 8px 14px; background: {p['inset']}; }}
QLabel#badge {{ color: {p['accent']}; background: {p['inset']}; border: 1px solid {p['selection']}; border-radius: 10px; padding: 3px 10px; font-size: 12px; }}
QLabel#error, QLabel#inboxWarning {{ color: {p['error']}; background: {p['error_soft']}; border-radius: 10px; padding: 8px; }}
QListWidget {{ background: transparent; border: none; outline: none; padding: 4px; }}
QListWidget::item {{ padding: 10px; border-radius: 10px; margin: 3px 0; }}
QListWidget::item:hover {{ background: {p['surface']}; }}
QListWidget::item:selected {{ background: {p['selection']}; color: {p['ink']}; }}QLabel#brandName {{ background: transparent; font-family: '{family}', 'Segoe UI', 'Microsoft YaHei'; font-size: 20px; font-weight: 760; }}
/* Navigation uses the actual Dream Han Sans family with its W20 face. */
QListWidget#nav::item {{ padding: 12px 14px; font-family: '{family}', 'Segoe UI', 'Microsoft YaHei'; font-size: 14px; font-weight: 650; }}
QListWidget#nav::item:selected {{ background: {p['action']}; color: {p['on_action']}; }}
QListWidget#memoryList::item {{ background: {p['surface']}; border: 1px solid {p['line']}; border-radius: 10px; padding: 0px 10px; margin: 2px 0; }}
/* v1.7.4：记忆列表选中从"高亮边框"改为整行皇家蓝底（行内文字色由 MemoryPage 联动切换） */
QListWidget#memoryList::item:selected {{ background: {p['action']}; border: 1px solid {p['action']}; }}
/* v1.6.0：侧栏后台任务面板；v1.7.2 标题 15px 明确大于"收起/展开"按钮的 13px（原来 eyebrow 11px 反而更小） */
QFrame#jobPanel {{ background: transparent; border-top: 1px solid {p['line']}; }}
QFrame#jobPanel QLabel#jobTitle {{ color: {p['ink']}; font-size: 15px; font-weight: 800; }}
/* v1.7.3：任务面板"清除已完成"入口——弱化的文字按钮，不与表格抢视觉 */
QPushButton#jobClear {{ background: transparent; border: none; color: {p['muted']}; font-size: 12px; font-weight: 550; min-height: 24px; padding: 0 2px; text-align: left; }}
QPushButton#jobClear:hover {{ color: {p['accent']}; }}
QPushButton#jobClear:pressed {{ color: {p['action']}; }}
/* v1.7.2：后台任务表头压紧（状态/进度列只占文字宽度，任务列吃满剩余空间）；
   v1.7.4：内边距再收紧一档，给两字动词+技能名腾出显示宽度 */
QTableWidget#jobTable QHeaderView::section {{ padding: 4px 6px; }}
QTableView {{ background: {p['surface']}; alternate-background-color: {p['inset']}; gridline-color: {p['line']}; border: 1px solid {p['line']}; border-radius: 10px; selection-background-color: {p['selection']}; selection-color: {p['ink']}; }}
/* v1.6.0：技能库/安全中心加行高（原来压得太紧难以操作） */
QTableView::item {{ padding: 12px 10px; }}
QHeaderView::section {{ background: {p['raised']}; color: {p['muted']}; padding: 10px; border: none; border-bottom: 1px solid {p['line']}; font-size: 12px; font-weight: 700; }}
QLabel#eyebrow {{ color: {p['accent']}; font-size: 12px; font-weight: 800; }}
QLabel#muted, QLabel#status {{ color: {p['muted']}; font-size: 13px; font-weight: 450; }}
/* v1.9.0（需求 1）：设置保存成功反馈——皇家蓝加粗强调，与主按钮同色系 */
QLabel#statusSaved {{ color: {p['action']}; font-size: 13px; font-weight: 700; }}
QLabel#faint {{ color: {p['faint']}; font-size: 12px; font-weight: 450; }}
QLabel#title {{ color: {p['ink']}; font-family: '{family}', 'Segoe UI', 'Microsoft YaHei'; font-size: 30px; font-weight: 760; }}
QTabWidget::pane {{ border: 1px solid {p['line']}; border-radius: 16px; padding: 16px; background: {p['surface']}; }}
QTabBar::tab {{ padding: 10px 18px; border-radius: 10px; color: {p['muted']}; background: {p['sidebar']}; font-size: 13px; }}
QTabBar::tab:selected {{ color: {p['accent']}; background: {p['surface']}; font-weight: 650; }}
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
/* v1.7.4：勾选态 = 实心皇家蓝方框；白描边保证在蓝色选中行上仍清晰可辨 */
QCheckBox::indicator:checked {{ background: {p['action']}; border: 2px solid #FFFFFF; }}
QCheckBox:focus {{ outline: 2px solid {p['accent']}; }}
/* v1.7.4：浮动侧栏与内容区之间的分隔条透明（拖拽区仍在）；悬停淡色提示可拖。
   编辑器里需要可见把手的分隔条用 #descSplitter 单独上色。 */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {p['selection']}; }}
QSplitter#descSplitter::handle {{ background: {p['line']}; }}
QTableWidget, QTableView {{ alternate-background-color: {p['inset']}; selection-background-color: {p['selection']}; selection-color: {p['ink']}; outline: none; }}
/* v1.7.4：表格选中行从"左侧 2px 竖条"改为整行皇家蓝底 + 白字（技能仓库/安全中心统一） */
QTableWidget::item:selected, QTableView::item:selected {{ background: {p['action']}; color: {p['on_action']}; border: none; }}
QTableWidget:focus, QTableView:focus, QListWidget#memoryList:focus, QTabWidget:focus {{ border: 2px solid {p['accent']}; }}
QListWidget#nav:focus::item:selected {{ border: 2px solid {p['accent']}; }}
QPlainTextEdit, QTextBrowser {{ font-family: 'Cascadia Mono', 'Microsoft YaHei'; }}
QGroupBox {{ color: {p['ink']}; }}
QProgressBar {{ min-height: 7px; max-height: 7px; border: 0; border-radius: 4px; background: {p['line']}; text-align: center; }}
QProgressBar::chunk {{ border-radius: 4px; background: {p['action']}; }}
QStatusBar {{ background: {p['sidebar']}; color: {p['muted']}; border-top: 1px solid {p['line']}; }}
QToolButton#iconButton {{ min-width: 32px; max-width: 32px; padding: 0; }}
QLabel#sectionTitle {{ color: {p['ink']}; font-size: 18px; font-weight: 700; }}
QLabel#helper {{ color: {p['faint']}; font-size: 12px; font-weight: 450; }}
QLabel#statusOk {{ color: {p['ok']}; background: {p['ok_soft']}; border-radius: 8px; padding: 6px 10px; }}
QLabel#statusWarning {{ color: {p['warning']}; background: {p['warning_soft']}; border-radius: 8px; padding: 6px 10px; }}
QLabel#statusError {{ color: {p['error']}; background: {p['error_soft']}; border-radius: 8px; padding: 6px 10px; }}
QToolButton, QPushButton, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QListWidget, QTableWidget {{
  selection-background-color: {p['selection']}; selection-color: {p['ink']};
}}
QAbstractScrollArea {{ background: {p['surface']}; }}
QDialog {{ border: 1px solid {p['line']}; }}
"""


LIGHT_QSS = stylesheet("light")
DARK_QSS = stylesheet("dark")


class ThemeController(QObject):
    changed = Signal(str)

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        ensure_brand_fonts()
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
