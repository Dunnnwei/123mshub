"""HAUI Tabler icons and shared native control decoration.

SVG sources are exported from the local HAUI system, with its license retained.

- :data:`ICONS`：图标名 → SVG 模板（``COLOR`` 占位符待染色）；
- :func:`tinted_icon`：按 (名称, 颜色, 尺寸) 渲染并缓存 QIcon；
- :func:`decorate_controls`：遍历控件树按**按钮文本**挂图标（零侵入——视图层
  一行不改，纯视觉增强，幂等可重复调用，主题切换后重染）。

按钮文本映射的好处：功能代码不动；代价是文案改动要同步 _ICON_TEXTS——
两处都在本文件内，review 可见。
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QObject, QEvent, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QAbstractButton, QLineEdit, QToolButton, QWidget

from .haui import icons as haui_icons

ICONS = haui_icons()

# 按钮「精确文本 → 图标名」映射。文案变更时同步这里（注释一处、可见性好排查）。
_ICON_TEXTS: dict[str, str] = {
    "新建记忆": "note_new", "新建一条记忆": "note_new", "新建": "note_new",
    "编辑选中": "edit", "编辑": "edit", "编辑信息": "edit",
    "删除": "delete", "软删除": "delete", "批量删除": "delete",
    "刷新": "refresh",
    "信任选中": "trust", "信任放行": "trust", "批量信任": "trust",
    "AI 检查": "ai", "批量 AI 检查": "ai", "AI 生成": "ai",
    "AI 补全主题": "ai", "AI 补全标题与描述": "ai",
    "Agent连接提示词": "agent",
    "归纳整理": "auto", "整理日报": "auto",
    "复制值守提示词": "copy", "复制安装提示词": "copy", "复制指定技能提示词": "copy",
    "投递箱": "inbox", "查看索引源文件": "list",
    "添加技能 / 程序": "add",
    "离线检查": "scan", "批量离线检查": "scan", "批量检查需要确认": "scan",
    "只读检测": "scan", "扫描预览": "scan", "重新识别已同步条目": "scan",
    "自动翻译": "translate", "批量中文翻译": "translate",
    "更新": "update", "批量更新 GitHub": "update", "检查更新": "update",
    "保存": "save", "保存设置": "save",
    "打开仓库目录": "folder", "选择本地目录…": "folder", "选择…": "folder",
    "导入记忆技能库…": "import",
    "导入记忆技能库（可选择Agent记忆或技能文件夹导入）": "import",
    "清除已完成": "clear", "清除仓库数据保留配置": "clear", "清除所有配置": "clear",
    "清除已存 Token": "clear", "清除已存密钥": "clear",
    "拉取 /models": "download", "测试连通": "network",
    "关于 123 MSHub": "info", "关闭": "close",
    "预览": "eye", "打开它": "open",
    "收起": "chevron_up", "展开": "chevron_down",
    "应用标签": "tag",
}

_ICON_CACHE: dict[tuple[str, str, int, float], QIcon] = {}


class _SearchIconPositioner(QObject):
    """Keep a leading search icon optically centered in a QLineEdit."""

    def __init__(self, edit: QLineEdit, button: QToolButton) -> None:
        super().__init__(edit)
        self.edit = edit
        self.button = button
        self.reposition()

    def reposition(self) -> None:
        # A fixed 20px hit box removes style-dependent QToolButton padding from
        # the equation.  The 16px glyph is then centered in the actual edit
        # height, including Windows high-DPI styles and theme changes.
        size = QSize(20, 20)
        self.button.setFixedSize(size)
        self.button.move(6, max(0, (self.edit.height() - size.height()) // 2))
        self.button.raise_()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt virtual method name
        if obj is self.edit and event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.StyleChange, QEvent.Type.FontChange):
            self.reposition()
            QTimer.singleShot(0, self, self.reposition)
        return super().eventFilter(obj, event)


def tinted_icon(name: str, color: str, size: int = 24) -> QIcon:
    app = QApplication.instance()
    screen = app.primaryScreen() if app else None
    dpr = screen.devicePixelRatio() if screen else 1.0
    key = (name, color, size, dpr)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    source = ICONS.get(name)
    icon = QIcon()
    if source:
        renderer = QSvgRenderer(QByteArray(source.replace("COLOR", color).encode("utf-8")))
        pixmap = QPixmap(round(size * dpr), round(size * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        icon.addPixmap(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def _button_tint(button: QAbstractButton, palette: dict) -> str:
    """按按钮角色选图标色：主按钮/幽灵白字白图标，危险红，普通弱化灰。"""
    name = button.objectName() or ""
    if name in {"primary", "ghost", "agentButton"}:
        return str(palette.get("ink", "#FFFFFF")) if name == "ghost" else str(palette.get("on_action", "#FFFFFF"))
    if name == "danger":
        return str(palette.get("error", "#FFAAA3"))
    return str(palette.get("muted", "#94A3B8"))


def decorate_controls(root: QWidget, palette: dict) -> None:
    """按文本映射给按钮挂图标、给搜索框挂前缀放大镜；幂等，可随主题重染。"""
    for button in root.findChildren(QAbstractButton):
        if button.property("mshubNoIcon"):
            continue
        name = _ICON_TEXTS.get(button.text().strip())
        if not name:
            from .i18n import EN
            name = next((icon for label, icon in _ICON_TEXTS.items() if EN.get(label) == button.text().strip()), None)
        if not name:
            continue
        size = 16 if (button.objectName() or "") in {"primary", "agentButton", "ghost"} else 15
        button.setIcon(tinted_icon(name, _button_tint(button, palette), size))
        button.setIconSize(QSize(size, size))
    for edit in root.findChildren(QLineEdit):
        hint = f'{edit.placeholderText() or ""} {edit.accessibleName() or ""}'
        if "搜索" in hint or "search" in hint.lower():
            if edit.property("mshubSearchIcon") is None:
                # QAction placement varies by the active Windows style and was
                # one or two pixels low in the search fields.  A transparent
                # child hit target gives the icon an explicit vertical center
                # while leaving the line edit's clear action untouched.
                button = QToolButton(edit)
                button.setObjectName("searchLeading")
                button.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.setIcon(tinted_icon("search", str(palette.get("faint", "#94A3B8")), 16))
                button.setIconSize(QSize(16, 16))
                button.setStyleSheet("QToolButton#searchLeading { background: transparent; border: none; padding: 0; }")
                edit.setTextMargins(28, 0, 0, 0)
                positioner = _SearchIconPositioner(edit, button)
                edit.installEventFilter(positioner)
                edit._mshub_search_positioner = positioner
                edit._mshub_search_button = button
                edit.setProperty("mshubSearchIcon", True)
            else:
                button = getattr(edit, "_mshub_search_button", None)
                if button is not None:
                    button.setIcon(tinted_icon("search", str(palette.get("faint", "#808080")), 16))
                    getattr(edit, "_mshub_search_positioner", None) and edit._mshub_search_positioner.reposition()
