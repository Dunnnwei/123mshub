"""Qt translator for native chrome. User content is never a translation key."""
from PySide6.QtCore import QCoreApplication, QEvent, QLocale, QObject, QTranslator, Signal
from PySide6.QtWidgets import (QApplication, QAbstractButton, QComboBox, QDockWidget,
    QGroupBox, QLabel, QLineEdit, QListWidget, QPlainTextEdit, QTabWidget, QTableWidget, QWidget)

EN = {
    "记忆库": "Memory", "记忆图示": "Memory graph", "技能库": "Skills",
    "安全中心": "Safety", "设置": "Settings", "本地共享记忆与技能": "Shared memory & skills",
    "复制注入提示词": "Copy connection prompt", "准备就绪": "Ready", "后台任务": "Background tasks",
    "选择一条记忆": "Select a memory", "新建": "New", "新建记忆": "New memory",
    "标题": "Title", "条目名": "Entry name", "一句话描述": "Description", "描述": "Description",
    "类型": "Type", "标签": "Tags", "正文": "Body", "编辑": "Edit", "预览": "Preview",
    "保存": "Save", "软删除": "Move to trash", "放大编辑": "Expand editor", "还原编辑": "Restore editor",
    "AI 生成描述": "AI description", "全部类型": "All types", "最近更新": "Updated",
    "创建时间": "Created", "名称": "Name", "用户": "User", "项目": "Project", "参考": "Reference",
    "反馈": "Feedback", "投递箱": "Inbox", "应用标签": "Apply tags", "AI 补全主题": "AI complete",
    "批量软删除": "Trash selected", "批量改分类…": "Change type…", "归纳整理": "Tidy memories",
    "整理日报": "Tidy reports", "复制值守提示词": "Copy duty prompt", "查看索引源文件": "View index source",
    "搜索标题、描述、标签或正文全文": "Search title, description, tags or full text",
    "条目文件是事实源；搜索、整理与收编都可回看。 ": "Search, review and organize your shared memories.",
    "勾选列表中的条目进行批量操作": "Select entries for batch actions", "新建一条记忆": "Create a memory",
    "暂无记忆条目": "No memories yet", "投递原文（只读）": "Original submission (read-only)",
    "收编表单（可编辑）": "Admission form", "收编入库": "Admit to library", "丢弃选中": "Discard selected",
    "全部丢弃": "Discard all", "关闭": "Close", "AI 补全标题与描述": "AI title & description",
    "已有同名条目": "An entry with this name exists", "打开它": "Open existing entry", "规范化": "Normalize",
    "添加技能 / 程序": "Add skill / program", "全部来源": "All sources", "GitHub 源": "GitHub source",
    "本地自研": "Local author", "全部资产": "All assets", "技能": "Skill", "程序": "Program", "刷新": "Refresh",
    "搜索名称、中文备注、来源地址或标签": "Search name, description, source or tags",
    "来源": "Source", "中文备注": "Chinese description", "安全": "Safety", "更新时间": "Updated",
    "导入来源": "Imported from", "技能详情": "Skill details", "选择一项": "Select an item", "选": "Select",
    "离线检查": "Offline check", "AI 检查": "AI check", "信任放行": "Trust", "更新": "Update",
    "复制指定技能提示词": "Copy skill prompt", "复制安装提示词": "Copy install prompt", "编辑信息": "Edit metadata",
    "查版本": "Check version", "备份": "Back up", "检查报告": "Safety report", "中文翻译": "Translate to Chinese",
    "批量检查": "Check selected", "批量更新": "Update selected", "批量信任": "Trust selected",
    "批量翻译": "Translate selected", "全部标签": "All tags", "展开标签": "Expand tags", "收起标签": "Collapse tags",
    "安装模式": "Install mode", "标准（按说明文件）": "Standard (referenced files)", "全仓（完整 Git）": "Full repository",
    "抓取方式": "Fetcher", "扫描预览": "Scan preview", "后台入库": "Install in background",
    "选择本地目录…": "Choose local directory…", "所属库": "Library", "共享技能库": "Shared skills",
    "程序库": "Programs", "分支": "Branch", "子目录": "Subdirectory", "版本": "Version", "目录名": "Directory name",
    "条目身份（改名不改目录）": "Identity (renaming keeps directory)", "源地址": "Source URL",
    "需要确认": "Needs review", "路线 A · 离线": "Route A · Offline", "路线 B · AI": "Route B · AI",
    "批量检查待确认": "Check pending entries", "状态": "Status", "最近检查": "Last check", "摘要": "Summary",
    "配置目录固定为 %APPDATA%\\mshub；修改草稿不会立即生效。": "Configuration: %APPDATA%\\mshub. Save to apply changes.",
    "仓库根目录": "Repository root", "选择…": "Browse…", "记忆库位置覆盖": "Memory root override",
    "语言": "Language", "主题": "Theme", "跟随系统": "System", "跟随系统 / System": "System",
    "亮色": "Light", "暗色": "Dark", "代理": "Proxy", "只读检测": "Detect", "检测结果": "Detection result",
    "镜像列表": "Mirror list", "常用镜像": "Mirror shortcuts", "每行一个镜像地址": "One mirror URL per line",
    "仓库与语言": "Repository & language", "供应商预设": "Provider", "自定义": "Custom",
    "AI 接口地址": "AI base URL", "AI 模型": "AI model", "拉取 /models": "Fetch /models",
    "AI 密钥": "AI key", "测试连通": "Test connection", "清除已存密钥": "Clear saved key",
    "已存状态": "Saved state", "清除已存 Token": "Clear saved token", "AI 与凭据": "AI & credentials",
    "说明": "Note", "匿名访问可用，但更容易触发 GitHub 速率限制。": "Anonymous access works with lower GitHub rate limits.",
    "重新识别已同步条目": "Reconcile synced entries", "导入记忆技能库…": "Import memories & skills…",
    "打开仓库目录": "Open repository", "维护与导入": "Maintenance & import", "保存设置": "Save settings",
    "任务": "Task", "时间": "Time", "进度": "Progress", "操作": "Actions", "移除": "Dismiss", "报告": "Report",
    "清除已完成": "Clear finished", "选择导入目录": "Choose import directory", "导入记忆": "Import memories",
    "导入技能": "Import skills", "确认导入": "Confirm import", "导入记忆技能库": "Import memories & skills",
    "关闭窗口后任务继续，可在后台任务查看进度和报告。": "Tasks continue after closing this window. Open Background tasks for progress and reports.",
}


class NativeTranslator(QTranslator):
    def isEmpty(self):
        return False

    def translate(self, context, sourceText, disambiguation=None, n=-1):
        return EN.get(sourceText, "") if context == "Native" else ""


def tr(text):
    return QCoreApplication.translate("Native", text)


def localize(root):
    for widget in [root, *root.findChildren(QWidget)]:
        if widget.property("userContent"):
            continue
        for getter, setter, key in (("text", "setText", "text"), ("placeholderText", "setPlaceholderText", "placeholder"),
                                    ("title", "setTitle", "title"), ("windowTitle", "setWindowTitle", "windowTitle")):
            if getter == "text" and not isinstance(widget, (QLabel, QAbstractButton)):
                continue
            if hasattr(widget, getter) and hasattr(widget, setter):
                source = widget.property("i18n_" + key) or getattr(widget, getter)()
                if source in EN:
                    widget.setProperty("i18n_" + key, source)
                    getattr(widget, setter)(tr(source))
        if isinstance(widget, QComboBox) and not widget.isEditable():
            blocked = widget.blockSignals(True)
            for i in range(widget.count()):
                source = widget.itemData(i, 900) or widget.itemText(i)
                if source in EN:
                    widget.setItemData(i, source, 900)
                    widget.setItemText(i, tr(source))
            widget.blockSignals(blocked)
        if isinstance(widget, QTabWidget):
            for i in range(widget.count()):
                key = f"i18n_tab{i}"
                source = widget.property(key) or widget.tabText(i)
                if source in EN:
                    widget.setProperty(key, source)
                    widget.setTabText(i, tr(source))
        if isinstance(widget, QTableWidget):
            for i in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(i)
                if item:
                    source = item.data(900) or item.text()
                    if source in EN:
                        item.setData(900, source)
                        item.setText(tr(source))
        if isinstance(widget, QListWidget) and widget.objectName() == "nav":
            for i in range(widget.count()):
                item = widget.item(i)
                source = item.data(900) or item.text()
                if source in EN:
                    item.setData(900, source)
                    item.setText(tr(source))


class LanguageController(QObject):
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.translator = NativeTranslator(self)
        self.mode = "system"

    def apply(self, mode):
        self.mode = mode or "system"
        app = QApplication.instance()
        app.removeTranslator(self.translator)
        english = self.mode == "en" or (self.mode == "system" and QLocale.system().language() != QLocale.Language.Chinese)
        if english:
            app.installTranslator(self.translator)
        for window in app.topLevelWidgets():
            localize(window)
        self.changed.emit(self.mode)
        return self.mode
