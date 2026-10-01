"""123mshub Native design tokens shared by Qt and the local graph island.

v1.10.0（Stitch 视觉移植）：配色与组件样式按 Stitch 两套设计系统重制——
暗色走 Fluent Mica Utility（深海军蓝层阶 + 白 8% 描边），亮色走 Silk
（冷灰粘土底 + 浅卡 + 顶部高光边）。
v1.10.1（系统字体与视觉层级收口）：品牌主色从皇家蓝 #0156FC 换成 Stitch 的
靛蓝 #6366F1 / 紫罗兰 #7C3AED 体系（亮色 Silk 令牌 + 暗色 Mica 令牌），
图谱四分类色统一为 用户=靛蓝 / 项目=紫罗兰 / 参考=亮绿 / 反馈=亮红（列表胶囊
与图谱节点/图例同一映射）；选中态从实底反白改为主题色浅染。token 键位不变。
"""
import json
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

DURATIONS = {"hover": 120, "fade": 180, "panel": 220}

# Stitch typography is deliberately compact. Keeping the scale here prevents
# each native page from drifting toward a different dashboard size.
TYPOGRAPHY = {
    "display": 20,  # page title / template text-xl
    "brand": 14,    # sidebar brand / template text-sm
    "body": 12,     # controls, navigation and normal copy / text-xs
    "row": 12,      # table and memory row titles
    "meta": 11,     # descriptions, column heads and timestamps
    "micro": 10,    # eyebrow, version and count labels
    "nav": 13,      # primary sidebar navigation (one step above body)
    "count": 10,    # right-aligned sidebar totals
    "section": 14,  # in-page section title
}

_TOKENS_PATH = Path(__file__).with_name("design_tokens.json")

# ocr 审查修复：design_tokens.json 缺失/损坏时（打包或环境包部署异常）曾静默
# 返回空 dict，下游 stylesheet()/graph_palette() 直接 KeyError 且远离根因。
# 嵌一份与 json 同源的完整默认令牌作兜底：文件丢了 UI 也能起来（颜色不漂移）。
_FALLBACK_TOKENS = {
    "light": {"bg": "#E8EAF0", "sidebar": "#E5E7ED", "surface": "#F0F2F8", "raised": "#FFFFFF", "inset": "#E9ECF3",
              "ink": "#2E3040", "muted": "#585A68", "faint": "#8A8C9A", "line": "#D0D2DC", "strong": "#B8BACA",
              "action": "#6366F1", "on_action": "#FFFFFF", "accent": "#4F46E5", "selection": "#E0E2FF",
              "error": "#DC2626", "error_soft": "#FEE2E2", "ok": "#047857", "ok_soft": "#D1FAE5",
              "warning": "#B45309", "warning_soft": "#FEF3C7", "user": "#6366F1", "project": "#7C3AED",
              "reference": "#22C55E", "feedback": "#F43F5E", "glass": "#EEF0F7", "action_hover": "#4F46E5",
              "action_pressed": "#4338CA", "star_dot": "#6366F1", "star_bright": "#7C3AED", "sheet_alpha": 216},
    "dark": {"bg": "#0B0E14", "sidebar": "#0E172A", "surface": "#131B2E", "raised": "#1A243D", "inset": "#0F1830",
             "ink": "#DAE2FD", "muted": "#94A3B8", "faint": "#64748B", "line": "#232D45", "graph_line": "#465574", "strong": "#33415E",
             "action": "#6366F1", "on_action": "#FFFFFF", "accent": "#A5B4FC", "selection": "#2A2B63",
             "error": "#F87171", "error_soft": "#3D242A", "ok": "#34D399", "ok_soft": "#17392F",
             "warning": "#FBBF24", "warning_soft": "#40341F", "user": "#6366F1", "project": "#7C3AED",
             "reference": "#34D399", "feedback": "#FB7185", "glass": "#1A243D", "action_hover": "#818CF8",
             "action_pressed": "#4F46E5", "star_dot": "#6366F1", "star_bright": "#A5B4FC", "sheet_alpha": 218},
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

_SYSTEM_FONT_FALLBACK = "Segoe UI"


def system_font_family() -> str:
    """Return the Qt application font family without registering project fonts.

    Qt resolves the platform default after ``QApplication`` is created.  The
    static QSS constants are built during module import, so the Windows
    default remains the safe fallback for that early phase; live theme changes
    call :func:`stylesheet` again and pick up a user-selected system font.
    """

    app = QApplication.instance()
    if app is not None:
        family = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family().strip()
        if family:
            return family
    return _SYSTEM_FONT_FALLBACK


def ensure_brand_fonts() -> str:
    """Backward-compatible name for callers that used the old font loader.

    v1.10.1 deliberately does not register Dream Han Sans or any bundled face;
    the UI always follows the system font selected by Qt.
    """

    return system_font_family()
PALETTES = _load_tokens()
PALETTES.setdefault("light", {})
PALETTES.setdefault("dark", {})


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
        "line": token.get("graph_line", token["line"]),
        "accent": token["accent"],
        "selection": token["selection"],
        "types": {key: token[key] for key in ("user", "project", "reference", "feedback")},
    }


def _rgba(hex_color: str, alpha: int) -> str:
    color = hex_color.lstrip("#")
    r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha/255:.3f})"


def starfield_colors(mode: str) -> tuple[str, str, str, bool]:
    """兼容旧工作区接口；v1.10.0D 的原生画布使用静态 Silk/Mica 底色。"""
    token = PALETTES["dark" if mode == "dark" else "light"]
    bright_default = "#A5B4FC" if mode == "dark" else "#7C3AED"
    return token["bg"], token.get("star_dot", "#6366F1"), token.get("star_bright", bright_default), mode == "dark"


def stylesheet(mode):
    # Use the platform font selected by Qt.  The explicit fallbacks keep the
    # graph WebEngine and early-import QSS deterministic on Windows.
    family = system_font_family()
    font_stack = f"'{family}', 'Segoe UI', 'Microsoft YaHei', sans-serif"
    p = PALETTES[mode]
    dark = mode == "dark"
    # 内容区悬浮页板：点阵背景透出的一层半透明卡（Stitch 的 Mica 质感近似——
    # Qt 无 backdrop-blur，用高不透明度近似磨砂）
    sheet = _rgba(p["surface"], int(p.get("sheet_alpha", 216)))
    sidebar_fill = _rgba(p["sidebar"], 235)
    job_card = _rgba(p["raised"], dark and 200 or 178)
    agent_grad = "qlineargradient(x1:0 y1:0, x2:1 y2:1, stop:0 #6366F1, stop:0.55 #6156EA, stop:1 #7C3AED)"
    eyebrow_bg = _rgba(p["action"], 36)
    eyebrow_line = _rgba(p["action"], 92)
    stat_bg = _rgba(p["action"], 20)
    danger_line = _rgba(p["error"], 120)
    ghost_ink = "#FFFFFF" if dark else p["ink"]
    ghost_line = "rgba(255,255,255,0.75)" if dark else "rgba(46,48,64,0.45)"
    ghost_hover = "rgba(255,255,255,0.10)" if dark else p["selection"]
    # Silk 亮色的"挤压凸起"暗示：顶边白高光 + 其余细线（暗色用顶边微光）
    card_top = "#FFFFFF" if not dark else "rgba(255,255,255,0.06)"
    # v1.10.0C：选中态 = 主题色浅染（Stitch 选中行是 primary-fixed 淡底，不再实底反白）
    selected_tint = _rgba(p["action"], 30 if not dark else 46)
    nav_selected = (
        f"background: {p['raised']}; color: {p['ink']}; border: 1px solid {p['strong']};"
        if dark else
        f"background: {p['raised']}; color: {p['accent']}; border: 1px solid {eyebrow_line};"
    )
    return f"""
QWidget {{ background: {p['bg']}; color: {p['ink']}; font-family: {font_stack}; font-size: {TYPOGRAPHY['body']}px; font-weight: 400; widget-animation-duration: {DURATIONS['hover']}; }}
QMainWindow, QDialog {{ background: {p['bg']}; }}
/* v1.10.0D：中央底板由静态 Silk/Mica 画布绘制，QSS 侧放行 */
QWidget#workspace {{ background: transparent; border: none; }}
QWidget#pageArea {{ background: transparent; }}
/* 页面根透明——透出 #pageSheet 的半透明层（各页内部卡片自带上色不受影响） */
QStackedWidget#pages > QWidget {{ background: transparent; }}
/* v1.10.0B（Stitch 结构）：页头横向信息带——独立底色+描边，与内容区分层 */
QFrame#headerBand {{ background: {p['surface']}; border: 1px solid {p['line']}; border-top: 1px solid {card_top}; border-radius: 16px; }}
QFrame#headerBand QLabel#title {{ font-size: {TYPOGRAPHY['display']}px; line-height: 24px; font-weight: 700; letter-spacing: -0.2px; }}
QFrame#headerDivider {{ background: {p['line']}; border: none; }}
/* v1.10.0B：品牌版本胶囊（Stitch 名字旁 mono 小胶囊） */
QLabel#versionPill {{ color: {p['accent']}; background: {eyebrow_bg}; border: 1px solid {eyebrow_line}; border-radius: 10px; min-height: 20px; padding: 1px 6px; font-size: {TYPOGRAPHY['micro']}px; font-weight: 600; }}
/* v1.10.0B（Stitch 结构）：记忆列表表格卡 */
QFrame#listCard {{ background: {p['surface']}; border: 1px solid {p['line']}; border-top: 1px solid {card_top}; border-radius: 16px; }}
QWidget#listHeader {{ background: {p['inset']}; border: none; border-bottom: 1px solid {p['line']}; border-top-left-radius: 15px; border-top-right-radius: 15px; }}
QWidget#listHeader QLabel {{ color: {p['muted']}; font-size: {TYPOGRAPHY['meta']}px; font-weight: 600; background: transparent; }}
QListWidget#memoryList {{ background: transparent; border: none; padding: 0; }}
QListWidget#memoryList::item {{ background: transparent; border: none; border-bottom: 1px solid {_rgba(p['line'], 120)}; border-radius: 0; padding: 0; margin: 0; }}
QListWidget#memoryList::item:hover {{ background: {_rgba(p['action'], 14)}; }}
/* v1.10.0C：选中行 = 主题色浅染（Stitch primary-fixed 淡底），行内文字不再反白 */
QListWidget#memoryList::item:selected {{ background: {selected_tint}; border-bottom: 1px solid {_rgba(p['line'], 120)}; }}
QLabel#rowTitle {{ font-size: {TYPOGRAPHY['row']}px; font-weight: 700; background: transparent; }}
QLabel#rowDesc {{ color: {p['muted']}; font-size: {TYPOGRAPHY['meta']}px; background: transparent; }}
QLabel#rowCol {{ color: {p['muted']}; font-size: {TYPOGRAPHY['meta']}px; background: transparent; }}
QLabel#rowTime {{ color: {p['faint']}; font-size: {TYPOGRAPHY['meta']}px; background: transparent; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
/* v1.7.4：侧边栏浮动面板；v1.10.0 换 Stitch Mica 半透明层阶 */
QFrame#sidebar {{ background: {sidebar_fill}; border: 1px solid {p['line']}; border-radius: 16px; }}
QFrame#pageSheet {{ background: {sheet}; border: 1px solid {p['line']}; border-radius: 16px; }}
QFrame#surface, QFrame#emptyCard, QGroupBox {{ background: {p['surface']}; border: 1px solid {p['line']}; border-top: 1px solid {card_top}; border-radius: 12px; }}
QWidget#memoryRow {{ background: transparent; }}
QFrame#emptyCard {{ border: 1px dashed {p['strong']}; }}
QGroupBox {{ margin-top: 14px; padding: 16px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 16px; color: {p['ink']}; font-size: 12px; font-weight: 700; }}
QLineEdit, QTextEdit, QTextBrowser, QPlainTextEdit, QComboBox {{
 background: {p['inset']}; color: {p['ink']}; border: 1px solid {p['line']};
 border-radius: 12px; padding: 6px 10px; font-size: 12px; selection-background-color: {p['selection']};
 selection-color: {p['ink']}; placeholder-text-color: {p['faint']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 2px solid {p['accent']}; padding: 6px 9px; }}
QComboBox::drop-down {{ width: 24px; border: none; }}
QComboBox QAbstractItemView {{ background: {p['raised']}; color: {p['ink']}; selection-background-color: {p['selection']}; }}
QPushButton, QToolButton {{ min-height: 30px; padding: 0 12px; border-radius: 12px;
 border: 1px solid {p['line']}; background: {p['surface']}; color: {p['ink']}; font-size: {TYPOGRAPHY['body']}px; font-weight: 500; }}
QPushButton:hover, QToolButton:hover {{ background: {p['raised']}; border-color: {p['strong']}; }}
QPushButton:focus, QToolButton:focus {{ border: 2px solid {p['accent']}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {p['selection']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {p['faint']}; background: {p['bg']}; border-color: {p['line']}; }}
QPushButton#primary {{ background: {p['action']}; color: {p['on_action']}; border-color: {p['action']}; font-weight: 700; font-size: {TYPOGRAPHY['body']}px; }}
QPushButton#primary:hover {{ background: {p['action_hover']}; border-color: {p['action_hover']}; }}
QPushButton#primary:focus {{ border: 2px solid {p['ink']}; }}
QPushButton#primary:pressed {{ background: {p['action_pressed']}; }}
QPushButton#primary:disabled {{ background: {p['strong']}; color: {p['faint']}; }}
/* v1.10.0C（Stitch Silk）：Agent 连接提示词——靛蓝→紫罗兰动能渐变，智能体专属签名色 */
QPushButton#agentButton {{ background: {agent_grad}; color: #FFFFFF; border: 1px solid rgba(255,255,255,0.22); font-weight: 700; }}
QPushButton#agentButton:hover {{ border: 1px solid rgba(255,255,255,0.42); }}
QPushButton#agentButton:pressed {{ background: {p['action_pressed']}; }}
QPushButton#agentButton:disabled {{ background: {p['strong']}; color: {p['faint']}; border-color: {p['line']}; }}
/* v1.7.5：幽灵按钮（描边空心）；暗色白字白边、亮色同构换墨色 */
QPushButton#ghost {{ color: {ghost_ink}; border: 1px solid {ghost_line}; background: transparent; font-weight: 600; }}
QPushButton#ghost:hover {{ background: {ghost_hover}; border-color: {p['accent']}; color: {p['accent']}; }}
QPushButton#ghost:pressed {{ background: {p['selection']}; }}
QPushButton#ghost:disabled {{ color: {p['faint']}; border-color: {p['line']}; }}
QPushButton#danger {{ color: {p['error']}; border-color: {danger_line}; background: {p['error_soft']}; font-weight: 600; }}
QPushButton#metric {{ color: {p['accent']}; border: 1px solid {eyebrow_line}; border-radius: 15px; font-size: {TYPOGRAPHY['body']}px; font-weight: 600; min-height: 30px; padding: 3px 12px; background: {stat_bg}; }}
QPushButton#metric:hover {{ background: {eyebrow_bg}; }}
QLabel#badge {{ color: {p['accent']}; background: {eyebrow_bg}; border: 1px solid {eyebrow_line}; border-radius: 10px; padding: 2px 11px; font-size: 11px; font-weight: 600; }}
QLabel#error, QLabel#inboxWarning {{ color: {p['error']}; background: {p['error_soft']}; border-radius: 10px; padding: 8px; }}
QListWidget {{ background: transparent; border: none; outline: none; padding: 4px; }}
QListWidget::item {{ padding: 10px; border-radius: 12px; margin: 3px 0; }}
QListWidget::item:hover {{ background: {p['surface']}; }}
QListWidget::item:selected {{ background: {p['selection']}; color: {p['ink']}; }}QLabel#brandName {{ background: transparent; font-family: {font_stack}; font-size: {TYPOGRAPHY['brand']}px; font-weight: 700; }}
/* Primary navigation follows the system font and gets one additional size step. */
QListWidget#nav {{ background: transparent; border: none; outline: none; padding: 0; }}
QListWidget#nav:focus {{ border: none; outline: none; }}
QListWidget#nav::item {{ padding: 5px 8px; border-radius: 12px; border: 1px solid transparent; font-family: {font_stack}; font-size: {TYPOGRAPHY['nav']}px; font-weight: 700; }}
/* v1.10.0C（Stitch）：导航选中 = 浅色浮起胶囊（亮白/暗 slate）+ 主题色描边，不再实底反白 */
QListWidget#nav::item:selected {{ {nav_selected} }}
/* v1.10.0B：行样式已上移至 #listCard 表格卡区（旧独立行卡样式退役） */

/* v1.10.0（Stitch 需求 4）：后台任务 = 悬浮圆角卡——去掉旧版 border-top 分隔与
   卡下衬底，直接浮在侧栏底色上（卡片自带半透明填充+描边+独立投影） */
QFrame#jobPanel {{ background: {job_card}; border: 1px solid {p['line']}; border-top: 1px solid {card_top}; border-radius: 14px; }}
QFrame#jobPanel QLabel#jobTitle {{ color: {p['ink']}; font-size: {TYPOGRAPHY['body']}px; font-weight: 700; }}
QTableWidget#jobTable {{ background: transparent; border: none; }}
QTableWidget#jobTable QHeaderView::section {{ background: transparent; border: none; border-bottom: 1px solid {p['line']}; }}
/* v1.7.3：任务面板"清除已完成"入口——弱化的文字按钮 */
QPushButton#jobClear {{ background: transparent; border: none; color: {p['muted']}; font-size: 11px; font-weight: 500; min-height: 22px; padding: 0 2px; text-align: left; }}
QPushButton#jobClear:hover {{ color: {p['accent']}; }}
QPushButton#jobClear:pressed {{ color: {p['action']}; }}
QTableWidget#jobTable QHeaderView::section {{ padding: 4px 6px; }}
QTableView {{ background: {p['surface']}; alternate-background-color: {p['inset']}; gridline-color: {p['line']}; border: 1px solid {p['line']}; border-radius: 12px; selection-background-color: {p['selection']}; selection-color: {p['ink']}; }}
/* v1.6.0：技能库/安全中心加行高（原来压得太紧难以操作） */
QTableView::item {{ padding: 8px 10px; font-size: {TYPOGRAPHY['body']}px; }}
QHeaderView::section {{ background: {p['raised']}; color: {p['muted']}; padding: 7px 10px; border: none; border-bottom: 1px solid {p['line']}; font-size: {TYPOGRAPHY['meta']}px; font-weight: 600; }}
/* v1.10.0（Stitch）：页头 eyebrow 从纯文字改为发光胶囊（含色点由文本自带） */
QLabel#eyebrow {{ color: {p['accent']}; background: {eyebrow_bg}; border: 1px solid {eyebrow_line}; border-radius: 9px; padding: 2px 10px; font-size: {TYPOGRAPHY['micro']}px; font-weight: 700; }}
QLabel#muted, QLabel#status {{ color: {p['muted']}; font-size: {TYPOGRAPHY['meta']}px; font-weight: 400; }}
/* v1.9.0（需求 1）：设置保存成功反馈——皇家蓝加粗强调 */
QLabel#statusSaved {{ color: {p['action']}; font-size: {TYPOGRAPHY['body']}px; font-weight: 700; }}
QLabel#faint {{ color: {p['faint']}; font-size: {TYPOGRAPHY['meta']}px; font-weight: 400; }}
QLabel#title {{ color: {p['ink']}; font-family: {font_stack}; font-size: {TYPOGRAPHY['display']}px; font-weight: 700; }}
QTabWidget::pane {{ border: 1px solid {p['line']}; border-radius: 14px; padding: 16px; background: {p['surface']}; }}
QTabBar::tab {{ padding: 8px 16px; margin: 0 4px 6px 0; border: 1px solid {p['line']}; border-radius: 12px; color: {p['muted']}; background: {p['inset']}; font-size: 12px; font-weight: 500; }}
QTabBar::tab:selected {{ color: {p['accent']}; background: {p['selection']}; border-color: {eyebrow_line}; font-weight: 600; }}
QDockWidget {{ border: 1px solid {p['line']}; }}
QDockWidget::title {{ background: {p['glass']}; padding: 8px 12px; color: {p['muted']}; }}
QToolTip {{ background: {p['raised']}; color: {p['ink']}; border: 1px solid {p['line']}; padding: 8px 10px; }}
QScrollBar:vertical {{ width: 8px; background: transparent; margin: 0; }}
QScrollBar:horizontal {{ height: 8px; background: transparent; margin: 0; }}
QScrollBar::handle {{ background: {p['strong']}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {p['faint']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p['strong']}; border-radius: 4px; background: {p['inset']}; }}
/* 勾选态 = 实心主题色方框；白描边保证在浅染选中行上仍清晰可辨 */
QCheckBox::indicator:checked {{ background: {p['action']}; border: 2px solid #FFFFFF; }}
QCheckBox:focus {{ outline: 2px solid {p['accent']}; }}
/* v1.7.4：浮动侧栏与内容区分隔条透明（拖拽区仍在）；悬停淡色提示可拖。 */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {p['selection']}; }}
QSplitter#descSplitter::handle {{ background: {p['line']}; }}
/* v1.9.1：侧栏内导航/任务面板垂直分隔条；v1.10.0 悬浮卡化后透明（卡缘即界线） */
QSplitter#jobSplitter::handle {{ background: transparent; }}
QTableWidget, QTableView {{ alternate-background-color: {p['inset']}; selection-background-color: {p['selection']}; selection-color: {p['ink']}; outline: none; }}
/* v1.10.0C：表格选中行整行主题色浅染（技能仓库/安全中心统一），文字保持墨色 */
QTableWidget::item:selected, QTableView::item:selected {{ background: {selected_tint}; color: {p['ink']}; border: none; }}
QTableWidget:focus, QTableView:focus, QListWidget#memoryList:focus, QTabWidget:focus {{ border: 2px solid {p['accent']}; }}
QListWidget#nav:focus::item:selected {{ border: 2px solid {p['accent']}; }}
QPlainTextEdit, QTextBrowser {{ font-family: {font_stack}; }}
QGroupBox {{ color: {p['ink']}; }}
QProgressBar {{ min-height: 6px; max-height: 6px; border: 0; border-radius: 3px; background: {p['line']}; text-align: center; }}
QProgressBar::chunk {{ border-radius: 3px; background: {p['action']}; }}
QStatusBar {{ background: transparent; color: {p['muted']}; border: none; font-size: 11px; }}
QToolButton#iconButton {{ min-width: 32px; max-width: 32px; padding: 0; }}
QToolButton#jobToggle {{ min-width: 30px; max-width: 30px; min-height: 28px; max-height: 28px; padding: 0; border-radius: 8px; qproperty-toolButtonStyle: ToolButtonIconOnly; }}
QLabel#jobActivityIcon {{ background: transparent; }}
QLabel#sectionTitle {{ color: {p['ink']}; font-size: {TYPOGRAPHY['section']}px; font-weight: 700; }}
QLabel#helper {{ color: {p['faint']}; font-size: {TYPOGRAPHY['meta']}px; font-weight: 400; }}
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
        # v1.10.0：默认主题从「跟随系统」改为「暗色」——Stitch 主视觉即暗色 Mica；
        # 用户在设置页选过亮色/暗色的不受影响（仅无记忆时生效）
        self.mode = str(self.settings.value("theme", "dark"))
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
            # Rebuild after QApplication exists so a user-selected system font
            # is reflected immediately; constants remain available to tests and
            # consumers that import the module before the app starts.
            app.setStyleSheet(stylesheet(effective))
        self.changed.emit(effective)
        return effective
