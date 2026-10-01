"""v1.10.0（Stitch 视觉移植）：统一图标库 + 控件装饰助手。

设计来源：Stitch 稿大量使用 Material Symbols Outlined 小图标（15~17px）配小号
文字，专业感的主要来源之一。本模块把同一套 24×24 描边图标（stroke 1.8、圆角
端点，与侧栏导航 _NAV_SVGS 同一视觉语言）集中管理：

- :data:`ICONS`：图标名 → SVG 模板（``COLOR`` 占位符待染色）；
- :func:`tinted_icon`：按 (名称, 颜色, 尺寸) 渲染并缓存 QIcon；
- :func:`decorate_controls`：遍历控件树按**按钮文本**挂图标（零侵入——视图层
  一行不改，纯视觉增强，幂等可重复调用，主题切换后重染）。

按钮文本映射的好处：功能代码不动；代价是文案改动要同步 _ICON_TEXTS——
两处都在本文件内，review 可见。
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QLineEdit, QWidget

_S = 'stroke="COLOR" stroke-width="1.8" fill="none"'
_CAP = f'{_S} stroke-linecap="round"'

ICONS: dict[str, str] = {
    "note_new": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 4.5h14v15H5z" {_S} stroke-linejoin="round"/><path d="M12 9.5v5M9.5 12h5" {_CAP}/></svg>',
    "edit": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="m4.5 19.5.9-3.6L15.9 5.4l2.7 2.7L8.1 18.6l-3.6.9z" {_S} stroke-linejoin="round"/><path d="m14.3 7 2.7 2.7" {_CAP}/></svg>',
    "delete": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 7h14M9.5 7V4.8h5V7M7 7l.9 12.2h8.2L17 7" {_S} stroke-linejoin="round"/><path d="M10.3 10.5v5.5M13.7 10.5v5.5" {_CAP}/></svg>',
    "refresh": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M19 12a7 7 0 1 1-2.2-5.1" {_CAP}/><path d="M19.2 3.8v3.4h-3.4" {_S} stroke-linejoin="round"/></svg>',
    "trust": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3.8 19 6.5v5.2c0 4.1-2.8 7.3-7 8.5-4.2-1.2-7-4.4-7-8.5V6.5z" {_S} stroke-linejoin="round"/><path d="m8.6 12 2.3 2.3 4.6-4.8" {_CAP}/></svg>',
    "agent": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3v2.2" {_CAP}/><circle cx="12" cy="4" r="1.2" fill="COLOR" stroke="none"/><rect x="4.5" y="6.5" width="15" height="11" rx="3" {_S}/><circle cx="9" cy="12" r="1.3" fill="COLOR" stroke="none"/><circle cx="15" cy="12" r="1.3" fill="COLOR" stroke="none"/><path d="M9.5 15.6h5" {_CAP}/></svg>',
    "ai": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 8.5h14v10H5z" {_S} stroke-linejoin="round"/><path d="M8 5.5 9 8M16 5.5 15 8M8.8 12.4h.01M12.2 12.4h.01M15.4 12.4h.01M8.8 15h.01M12.2 15h.01M15.4 15h.01" {_CAP} stroke-width="2.4"/></svg>',
    "auto": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3.5 13.8 9 19.5 11 13.8 13 12 18.5 10.2 13 4.5 11 10.2 9z" {_S} stroke-linejoin="round"/><path d="M18.5 16.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" {_S} stroke-linejoin="round"/></svg>',
    "copy": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="8.5" y="8.5" width="11" height="11" rx="2" {_S}/><path d="M15.5 8.5v-2a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" {_S}/></svg>',
    "inbox": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4.5 13.5h4l1.2 2.2h4.6l1.2-2.2h4" {_S} stroke-linejoin="round"/><path d="M4.5 13.5 6.8 5.5h10.4l2.3 8v5a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2z" {_S} stroke-linejoin="round"/></svg>',
    "list": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M8 6.5h11.5M8 12h11.5M8 17.5h11.5" {_CAP}/><circle cx="4.6" cy="6.5" r="1.1" fill="COLOR" stroke="none"/><circle cx="4.6" cy="12" r="1.1" fill="COLOR" stroke="none"/><circle cx="4.6" cy="17.5" r="1.1" fill="COLOR" stroke="none"/></svg>',
    "add": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.2" {_S}/><path d="M12 8.4v7.2M8.4 12h7.2" {_CAP}/></svg>',
    "scan": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="5.8" {_S}/><path d="m15 15 4.5 4.5" {_CAP}/><path d="m8 10.7 1.8 1.8 3-3.4" {_CAP}/></svg>',
    "translate": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.2" {_S}/><path d="M3.8 12h16.4M12 3.8c-4.8 5-4.8 11.4 0 16.4 4.8-5 4.8-11.4 0-16.4z" {_S}/></svg>',
    "update": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 9a7.5 7.5 0 0 1 13-1.5" {_CAP}/><path d="M18.5 4v3.5H15" {_S} stroke-linejoin="round"/><path d="M12 8v7.5M8.8 12.5 12 15.7l3.2-3.2" {_CAP}/></svg>',
    "save": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 5h11l3 3v11H5z" {_S} stroke-linejoin="round"/><path d="M8.5 5v4.5h6V5M8.5 19v-5h7v5" {_S} stroke-linejoin="round"/></svg>',
    "folder": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 6.8h5.4l1.6 2H20v8.4H4z" {_S} stroke-linejoin="round"/></svg>',
    "import": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3.5v9M9 9.5l3 3 3-3" {_CAP}/><path d="M4.5 15v3.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V15" {_CAP}/></svg>',
    "clear": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.2" {_S}/><path d="m9.2 9.2 5.6 5.6M14.8 9.2l-5.6 5.6" {_CAP}/></svg>',
    "download": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 4v10M8.5 10.5 12 14l3.5-3.5" {_CAP}/><path d="M4.5 16v2.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V16" {_CAP}/></svg>',
    "network": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="2" fill="COLOR" stroke="none"/><path d="M7.8 7.8a6 6 0 0 0 0 8.4M16.2 16.2a6 6 0 0 0 0-8.4M5 5a10 10 0 0 0 0 14M19 19a10 10 0 0 0 0-14" {_CAP}/></svg>',
    "info": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.2" {_S}/><path d="M12 11v5.2" {_CAP}/><circle cx="12" cy="7.8" r="1.2" fill="COLOR" stroke="none"/></svg>',
    "close": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="m6.5 6.5 11 11M17.5 6.5l-11 11" {_CAP}/></svg>',
    "eye": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M3.5 12S6.8 6.2 12 6.2 20.5 12 20.5 12 17.2 17.8 12 17.8 3.5 12 3.5 12z" {_S} stroke-linejoin="round"/><circle cx="12" cy="12" r="2.6" {_S}/></svg>',
    "open": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M13.5 4.5H19V10" {_CAP}/><path d="M19 4.5 11 12.5" {_CAP}/><path d="M17 13.5v4a2 2 0 0 1-2 2H6.5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h4" {_CAP}/></svg>',
    "chevron_up": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="m6.5 14.5 5.5-5.5 5.5 5.5" {_S} stroke-linejoin="round"/></svg>',
    "chevron_down": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="m6.5 9.5 5.5 5.5 5.5-5.5" {_S} stroke-linejoin="round"/></svg>',
    "tag": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4.5 11V4.5H11l8.5 8.5-6.5 6.5z" {_S} stroke-linejoin="round"/><circle cx="8.2" cy="8.2" r="1.3" fill="COLOR" stroke="none"/></svg>',
    "search": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6" {_S}/><path d="m15 15 4.5 4.5" {_CAP}/></svg>',
    "shield": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3.8 19 6.5v5.2c0 4.1-2.8 7.3-7 8.5-4.2-1.2-7-4.4-7-8.5V6.5z" {_S} stroke-linejoin="round"/></svg>',
}

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

_ICON_CACHE: dict[tuple[str, str, int], QIcon] = {}


def tinted_icon(name: str, color: str, size: int = 24) -> QIcon:
    key = (name, color, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    source = ICONS.get(name)
    icon = QIcon()
    if source:
        renderer = QSvgRenderer(QByteArray(source.replace("COLOR", color).encode("utf-8")))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def _button_tint(button: QAbstractButton, palette: dict) -> str:
    """按按钮角色选图标色：主按钮/幽灵白字白图标，危险红，普通弱化灰。"""
    name = button.objectName() or ""
    if name in {"primary", "ghost", "agentButton"}:
        return "#FFFFFF" if name != "ghost" else str(palette.get("ink", "#FFFFFF"))
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
            continue
        size = 16 if (button.objectName() or "") in {"primary", "agentButton", "ghost"} else 15
        button.setIcon(tinted_icon(name, _button_tint(button, palette), size))
        button.setIconSize(QSize(size, size))
    for edit in root.findChildren(QLineEdit):
        hint = f'{edit.placeholderText() or ""} {edit.accessibleName() or ""}'
        if "搜索" in hint or "search" in hint.lower():
            if edit.property("mshubSearchIcon") is None:
                from PySide6.QtWidgets import QLineEdit as _QLE

                action = edit.addAction(
                    tinted_icon("search", str(palette.get("faint", "#94A3B8")), 16),
                    _QLE.ActionPosition.LeadingPosition,
                )
                action.setObjectName("searchLeading")
                edit.setProperty("mshubSearchIcon", True)
