"""Memory workspace: filters, multi-select, explicit editing and inbox review."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QPlainTextEdit, QSplitter, QStackedWidget, QTextBrowser, QVBoxLayout,
    QWidget, QCheckBox, QScrollArea, QToolButton, QApplication, QSizePolicy,
)

from ...memory import TYPE_LABELS
from ..memory_facade import MemoryFacade
from ..state import ui_settings
from ..task_runner import TaskRunner, RequestScope
from ..widgets import MarkdownView
from ..i18n import tr
from ..ui import (SHIFT_RANGE_HINT, AdaptivePage, ElideLabel, FlowLayout, GuardedDialog,
                  HeaderBand, RichHoverToolTip, ShiftRangeCheckMixin, copy_agent_prompt, flow_bar, label_controls,
                  make_agent_prompt_button, prepare_dialog)
from ..theme import PALETTES, current_palette as _current_palette, system_font_family

TYPE_OPTIONS = [("用户", "user"), ("项目", "project"), ("参考", "reference"), ("反馈", "feedback")]
# v1.10.0C 修复：分类标签映射统一用核心层 mshub.memory.TYPE_LABELS（token键→中文），
# 原本地 TYPE_LABELS = dict(TYPE_OPTIONS) 方向写反（中文→token），胶囊文字恒为"参考"。


def _memory_source_label(source: object) -> str:
    """Stable source vocabulary for the Chinese/English native UI."""
    key = str(source or "").casefold()
    if key == "imported":
        return tr("导入")
    if key == "manual":
        return tr("存储")
    if key == "agent":
        return tr("Agent投递")
    return str(source or "—")

# v1.7.2：软删除的真实语义（用户问"删除之后保存备份原件备查吗"）——移入回收目录、原件保留
SOFT_DELETE_MEMORY_TIP = (
    "软删除：只把这条记忆的文件移入仓库回收目录 memory-trash（按删除时间归档），\n"
    "列表与关系图会立即隐藏该条目；原始文件完整保留在磁盘上，并没有被销毁。\n"
    "需要找回时，到「仓库根目录\\memory-trash」里按时间戳目录取回对应文件即可。"
)


def _type_colors_cached() -> dict:
    """ocr 审查修复：单次刷新内亮暗模式不变——一次算好四类颜色，行循环只查表，
    不再每行扫描整份应用级联样式表（搜索/筛选热路径）。
    v1.10.0C 修复：TYPE_OPTIONS 是 (标签, token键) 对，原来按标签取色全部
    落空到 accent——分类胶囊失去四色区分。"""
    # Reuse the token-aware theme resolver; the canvas colors are intentionally
    # neutral in v1.10.5 and must not be detected through a retired literal.
    palette = _current_palette()
    return {value: palette.get(value, palette.get("accent", "#4F46E5")) for _label, value in TYPE_OPTIONS}


def _type_pill_style(color: str) -> str:
    """Return a flat Mono Clean category label without translucent pill chrome."""
    palette = _current_palette()
    return (
        f"color:{color};border:1px solid {color};"
        f"background:{palette.get('inset', '#F9F9F9')};border-radius:0;"
        "font-size:10px;font-weight:650;padding:1px 0;"
    )


def _error(payload: object) -> str:
    return str(payload.get("error") if isinstance(payload, dict) else payload)


class MemoryPage(ShiftRangeCheckMixin, AdaptivePage):
    totalChanged = Signal(int)
    openGraphRequested = Signal()
    statusMessage = Signal(str)
    promptCopied = Signal()

    def __init__(self, facade: MemoryFacade, runner: TaskRunner, jobs=None, parent=None):
        super().__init__(parent)
        self.facade, self.runner, self.jobs = facade, runner, jobs
        self.scope = RequestScope(runner, self)
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(300); self._timer.timeout.connect(self._refresh_now)
        self._name_timer = QTimer(self); self._name_timer.setSingleShot(True); self._name_timer.setInterval(250); self._name_timer.timeout.connect(self._check_name)
        self._request_id = 0; self._current_name = ""; self._creating = False; self._loading = False; self._dirty = False; self._refreshing_listing = False; self._items: list[dict[str, Any]] = []
        # 每行的文字控件引用：刷新/重译后统一复位行内样式（见 _paint_selected_rows）
        self._row_meta: list[dict[str, Any]] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(20, 14, 20, 12); root.setSpacing(12)
        # v1.10.0B（Stitch 结构）：页头 = 横向信息带（眉标胶囊+大标题+分隔线+副题，动作组右侧）
        band = HeaderBand("共享记忆", "记忆仓库", "条目文件是事实源；搜索、整理与收编都可回看。")
        self.new_window_button = QPushButton("新建记忆"); self.new_window_button.setObjectName("primary"); self.new_window_button.clicked.connect(self.open_new_editor); band.actions.addWidget(self.new_window_button)
        self.edit_window_button = QPushButton("编辑选中"); self.edit_window_button.clicked.connect(self.edit_selected); band.actions.addWidget(self.edit_window_button)
        self.agent_button = make_agent_prompt_button(self, self.copy_prompt); band.actions.addWidget(self.agent_button); root.addWidget(band)
        stats_widget = QWidget(); self.stats_row = FlowLayout(stats_widget, spacing=8); self.stat_buttons: dict[str, QPushButton] = {}
        for key, label in (("total", "总数"), ("user", "用户"), ("project", "项目"), ("reference", "参考"), ("feedback", "反馈"), ("this_week", "本周新增"), ("inbox_pending", "待收编")):
            # v1.10.0D：Stitch 统计胶囊使用共享 token；沿用独立 metric
            # 对象名，避免改变既有 v1.9.0 的 #stat 兼容契约。
            button = QPushButton(f"{label} 0"); button.setObjectName("metric"); button.setMinimumHeight(30); button.setProperty("i18n_stat", label); button.setProperty("i18n_count", "0")
            button.clicked.connect(lambda _checked=False, key=key: self._stat_filter(key)); self.stat_buttons[key] = button; self.stats_row.addWidget(button)
        # Keep the chips readable in their own compact line. The batch bar is
        # folded until a row is checked, so this still removes one full row.
        root.addWidget(stats_widget)
        toolbar = QHBoxLayout(); toolbar.setSpacing(10); self.search = QLineEdit(); self.search.setPlaceholderText("搜索标题、描述、标签或正文全文"); self.search.setAccessibleName("搜索记忆"); self.search.setAccessibleDescription("搜索标题、描述、标签或正文全文"); self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self.refresh); toolbar.addWidget(self.search, 1)
        self.type_filter = QComboBox(); self.type_filter.addItem("全部类型", ""); [self.type_filter.addItem(label, value) for label, value in TYPE_OPTIONS]; self.type_filter.currentIndexChanged.connect(self.refresh); toolbar.addWidget(self.type_filter)
        self.sort = QComboBox(); self.sort.addItem("最近更新", "updated"); self.sort.addItem("创建时间", "created"); self.sort.addItem("名称", "name"); self.sort.currentIndexChanged.connect(self.refresh); toolbar.addWidget(self.sort)
        self.inbox_button = QPushButton("投递箱"); self.inbox_button.clicked.connect(self.open_inbox); toolbar.addWidget(self.inbox_button); root.addLayout(toolbar)
        self.batch_bar = QWidget(); batch = FlowLayout(self.batch_bar, spacing=8); self.batch_hint = QLabel("勾选列表中的条目进行批量操作"); self.batch_hint.setObjectName("muted"); batch.addWidget(self.batch_hint); self.batch_type = QComboBox(); self.batch_type.addItem("批量改分类…", ""); [self.batch_type.addItem(label, value) for label, value in TYPE_OPTIONS]; batch.addWidget(self.batch_type); self.batch_type.activated.connect(self.batch_update_type); self.batch_tags = QLineEdit(); self.batch_tags.setPlaceholderText("批量标签（逗号）"); self.batch_tags.setMaximumWidth(180); batch.addWidget(self.batch_tags); bt = QPushButton("应用标签"); bt.clicked.connect(self.batch_update_tags); batch.addWidget(bt); ai = QPushButton("AI 补全主题"); ai.clicked.connect(self.batch_ai); batch.addWidget(ai); bd = QPushButton("批量删除"); bd.setObjectName("danger"); bd.setToolTip(SOFT_DELETE_MEMORY_TIP + "\n（批量操作对勾选的每一条执行同样的软删除；列表聚焦时也可按 Delete 键触发。）"); bd.clicked.connect(self.batch_delete); batch.addWidget(bd); root.addWidget(self.batch_bar); self.batch_bar.hide()
        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setChildrenCollapsible(False)
        # v1.10.0B（Stitch 结构）：列表 = 表格卡——列头条 + 数据行（圆角卡容器见
        # theme.py #listCard；列宽与行内列宽一一对应保证纵向对齐）
        list_card = QFrame(); list_card.setObjectName("listCard")
        card_layout = QVBoxLayout(list_card); card_layout.setContentsMargins(0, 0, 0, 0); card_layout.setSpacing(0)
        header_row = QWidget(); header_row.setObjectName("listHeader")
        hlay = QHBoxLayout(header_row); hlay.setContentsMargins(14, 7, 14, 7); hlay.setSpacing(10)
        self.master_check = QCheckBox(); self.master_check.setAccessibleName("全选条目")
        self.master_check.setToolTip("勾选/取消当前列表全部条目")
        self.master_check.toggled.connect(self._toggle_all_rows)
        hlay.addWidget(self.master_check)
        hlay.addWidget(QLabel("记忆条目 / 语义摘要"))
        hlay.addStretch(1)
        # 列宽常量与数据行严格一致（行内同名列用 setFixedWidth 对齐）
        self._col_tags, self._col_type, self._col_source, self._col_time = 116, 62, 104, 86
        for text, width in (("关联标签", self._col_tags), ("分类", self._col_type), ("来源渠道", self._col_source), ("同步时间", self._col_time)):
            col = QLabel(text); col.setFixedWidth(width); col.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter); hlay.addWidget(col)
        card_layout.addWidget(header_row)
        self.entry_list = QListWidget(); self.entry_list.setObjectName("memoryList"); self.entry_list.setAccessibleName("记忆条目列表"); self.entry_list.setAccessibleDescription("使用方向键选择，Enter 或双击编辑"); self.entry_list.setMinimumWidth(340); self.entry_list.currentItemChanged.connect(self._selection_changed); self.entry_list.itemDoubleClicked.connect(lambda _item: self.edit_selected())
        self._rich_tooltip = RichHoverToolTip(self.entry_list, self._memory_tooltip_text)
        # 行选中/刷新后统一复位行内文字样式（v1.10.0C 起选中为主题色浅染，不再反白）
        self.entry_list.itemSelectionChanged.connect(self._paint_selected_rows)
        card_layout.addWidget(self.entry_list, 1)
        splitter.addWidget(list_card)
        self.empty_card = QFrame(objectName="emptyCard"); empty_layout = QVBoxLayout(self.empty_card); empty_layout.setContentsMargins(36, 36, 36, 36); empty_layout.setSpacing(10); empty_title = QLabel("还没有记忆条目"); empty_title.setObjectName("title"); empty_layout.addWidget(empty_title, alignment=Qt.AlignmentFlag.AlignHCenter); empty_layout.addWidget(QLabel("先建立一条可复用的共享记忆，或者用右上角「Agent连接提示词」连接你的 Agent。", objectName="muted"), alignment=Qt.AlignmentFlag.AlignHCenter); empty_actions = QHBoxLayout(); empty_new = QPushButton("新建一条记忆"); empty_new.setObjectName("primary"); empty_new.clicked.connect(self.open_new_editor); empty_prompt = QPushButton("Agent连接提示词"); empty_prompt.clicked.connect(self.copy_prompt); empty_actions.addWidget(empty_new); empty_actions.addWidget(empty_prompt); empty_layout.addLayout(empty_actions); root.addWidget(self.empty_card); self.empty_card.hide()
        detail = QFrame(); detail.setObjectName("surface"); dl = QVBoxLayout(detail); dl.setContentsMargins(20, 18, 20, 18); dl.setSpacing(12)
        dh = QHBoxLayout(); self.detail_title = QLabel("选择一条记忆"); self.detail_title.setObjectName("sectionTitle"); dh.addWidget(self.detail_title); dh.addStretch(); self.new_button = QPushButton("新建"); self.new_button.setObjectName("primary"); self.new_button.clicked.connect(self.new_entry); dh.addWidget(self.new_button); dl.addLayout(dh)
        form = QFormLayout(); self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText("kebab-case，改名会重命名文件"); self.name_preview = QLabel(""); self.name_preview.setObjectName("muted"); self.collision_label = QLabel(""); self.collision_label.setStyleSheet(f"color:{_current_palette().get('error', '#B42318')}"); self.open_collision_button = QPushButton("打开它"); self.open_collision_button.setVisible(False); self.open_collision_button.clicked.connect(self._open_collision); collision_row = QHBoxLayout(); collision_row.setContentsMargins(0, 0, 0, 0); collision_row.addWidget(self.collision_label, 1); collision_row.addWidget(self.open_collision_button); nrow = QVBoxLayout(); nrow.addWidget(self.name_edit); nrow.addWidget(self.name_preview); nrow.addLayout(collision_row); form.addRow("条目名", nrow); self.title_edit = QLineEdit(); form.addRow("标题", self.title_edit)
        # v1.6.0：AI 生成描述按钮移到"一句话描述"右边
        desc_row = QHBoxLayout(); desc_row.setContentsMargins(0, 0, 0, 0); self.description_edit = QLineEdit(); desc_row.addWidget(self.description_edit, 1); ai_desc_small = QPushButton("AI 生成"); ai_desc_small.setMaximumWidth(80); ai_desc_small.clicked.connect(self.ai_description); desc_row.addWidget(ai_desc_small); form.addRow("一句话描述", desc_row)
        self.type_edit = QComboBox(); [self.type_edit.addItem(label, value) for label, value in TYPE_OPTIONS]; form.addRow("类型", self.type_edit); self.tags_edit = QLineEdit(); self.tags_edit.setPlaceholderText("Enter 或中英文逗号确认，最多 12 个"); form.addRow("标签", self.tags_edit); dl.addLayout(form)
        self.created_label = QLabel(""); self.created_label.setObjectName("muted"); self.updated_label = QLabel(""); self.updated_label.setObjectName("muted"); dl.addWidget(self.created_label); dl.addWidget(self.updated_label)
        mode = QHBoxLayout(); self.edit_mode = QPushButton("编辑"); self.preview_mode = QPushButton("预览"); self.edit_mode.clicked.connect(lambda: self.body_stack.setCurrentIndex(0)); self.preview_mode.clicked.connect(self._show_preview); mode.addWidget(QLabel("正文")); mode.addStretch(); mode.addWidget(self.edit_mode); mode.addWidget(self.preview_mode); dl.addLayout(mode)
        self.body_stack = QStackedWidget(); self.body_edit = QPlainTextEdit(); self.body_edit.setFont(QFont(system_font_family(), 10)); self.body_edit.setPlaceholderText("正文支持 [[双链]]；显式保存，不自动保存。"); self.preview = MarkdownView(); self.body_stack.addWidget(self.body_edit); self.body_stack.addWidget(self.preview); dl.addWidget(self.body_stack, 1)
        links_row = QHBoxLayout(); links_row.addWidget(QLabel("双链")); self.links_box = links_row; links_row.addStretch(); dl.addLayout(links_row)
        actions = QHBoxLayout(); self.status = QLabel(""); self.status.setObjectName("status"); actions.addWidget(self.status, 1); self.delete_button = QPushButton("软删除"); self.delete_button.setObjectName("danger"); self.delete_button.setToolTip(SOFT_DELETE_MEMORY_TIP); self.delete_button.clicked.connect(self.delete_current); actions.addWidget(self.delete_button); self.hard_delete_button = QPushButton("删除"); self.hard_delete_button.setObjectName("danger"); self.hard_delete_button.setToolTip("彻底删除：直接删除条目文件，不进入 memory-trash 回收目录，删除后无法恢复。"); self.hard_delete_button.clicked.connect(self.hard_delete_current); actions.addWidget(self.hard_delete_button); self.save_button = QPushButton("保存"); self.save_button.setObjectName("primary"); self.save_button.clicked.connect(self.save_current); actions.addWidget(self.save_button); dl.addLayout(actions)
        self.editor_dialog = GuardedDialog(self, self.can_close_editor); self.editor_dialog.setWindowTitle("记忆编辑"); self.editor_dialog.setModal(False); self.editor_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False); editor_layout = QVBoxLayout(self.editor_dialog); editor_layout.setContentsMargins(0, 0, 0, 0); editor_layout.addWidget(detail); prepare_dialog(self.editor_dialog); self._restore_editor_geometry(); self.editor_dialog.finished.connect(lambda _code: self._save_editor_geometry()); self.editor_dialog.hide(); self.editor_save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self.editor_dialog); self.editor_save_shortcut.activated.connect(self.save_current); self.edit_window_button.setEnabled(False); self.content_splitter = splitter; splitter.setSizes([1100, 0]); root.addWidget(splitter, 1)
        tidy_widget, tidy = flow_bar(self); tidy_button = QPushButton("归纳整理"); tidy_button.clicked.connect(self.tidy); reports = QPushButton("整理日报"); reports.clicked.connect(self.show_reports); duty = QPushButton("复制值守提示词"); duty.clicked.connect(self.copy_duty); index = QPushButton("查看索引源文件"); index.clicked.connect(self.show_index); tidy.addWidget(tidy_button); tidy.addWidget(reports); tidy.addWidget(duty); tidy.addWidget(index); root.addWidget(tidy_widget)
        # v1.9.0（需求 6）：底部 Shift 连选提示小字（右对齐贴列表右边线）
        hint_row = QHBoxLayout(); hint_row.addStretch(); self.shift_hint = QLabel(tr(SHIFT_RANGE_HINT)); self.shift_hint.setObjectName("helper"); hint_row.addWidget(self.shift_hint); root.addLayout(hint_row)
        # v1.9.0（需求 2）：列表聚焦时按 Delete 键 = 批量删除勾选项
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self.entry_list)
        self._delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._delete_shortcut.activated.connect(self.batch_delete)
        for widget in (self.name_edit, self.title_edit, self.description_edit, self.tags_edit, self.body_edit): widget.textChanged.connect(self._mark_dirty)
        self.name_edit.textChanged.connect(lambda _text: (self.name_preview.setText(self._name_preview(self.name_edit.text())), self._name_timer.start()))
        self.type_edit.currentIndexChanged.connect(self._mark_dirty)
        self._set_editor_enabled(False)
        label_controls(self)
        QTimer.singleShot(0, self._equalize_header_actions)

    def _equalize_header_actions(self) -> None:
        """Keep the three header actions on one shared hit-target grid."""
        buttons = (self.new_window_button, self.edit_window_button, self.agent_button)
        width = max(128, max(button.sizeHint().width() for button in buttons))
        width = min(width, 190)
        for button in buttons:
            button.setFixedSize(width, 34)

    def _mark_dirty(self, *_):
        if self._loading:
            return
        focus = QApplication.focusWidget()
        if focus is not None and self.editor_dialog.isAncestorOf(focus):
            self._dirty = True

    def _set_editor_enabled(self, enabled):
        for widget in (self.name_edit, self.title_edit, self.description_edit, self.type_edit, self.tags_edit, self.body_edit, self.save_button, self.delete_button, self.hard_delete_button): widget.setEnabled(enabled)

    def _set_status(self, text): self.status.setText(text); self.statusMessage.emit(text)

    def can_close_editor(self) -> bool:
        """Guard the modeless editor without losing an uncommitted draft."""
        if not self.editor_dialog.isVisible() or not self._dirty:
            return True
        allowed = self._confirm_discard_edit()
        if allowed:
            self._dirty = False
        return allowed

    def refresh(self, *_): self._request_id += 1; self._timer.start()

    def _refresh_now(self):
        rid = self._request_id; query = self.search.text().strip(); type_filter = str(self.type_filter.currentData() or ""); sort = str(self.sort.currentData() or "updated")
        self.scope.call("list", self.facade.list_entries, lambda result: self._apply_listing(result) if rid == self._request_id else None, lambda msg: self._set_status(f"读取失败：{msg}"), query=query, type_filter=type_filter, sort=sort)

    def refresh_sync(self):
        self._timer.stop(); result = self.facade.list_entries(query=self.search.text().strip(), type_filter=str(self.type_filter.currentData() or ""), sort=str(self.sort.currentData() or "updated")); self._apply_listing(result); return result

    def _apply_listing(self, result):
        self.invalidate_shift_anchor()  # v1.9.1：行号即将重建，旧 Shift 锚点作废（审查 P1-3）
        self._last_result = result
        self._items = list(result.get("items") or [])
        selected = self._current_name
        had_current = bool(selected)
        auto_load_name = ""
        self._refreshing_listing = True
        self._row_meta = []
        self._row_checks: list[QCheckBox] = []  # v1.9.0：Shift 连选的行号→复选框映射
        type_colors = _type_colors_cached()  # ocr 审查修复：循环外算一次，行内查表
        was_blocked = self.entry_list.blockSignals(True)
        try:
            self.entry_list.clear()
            for item in self._items:
                row = QListWidgetItem()
                row.setData(Qt.ItemDataRole.UserRole, item.get("name", ""))
                row.setData(Qt.ItemDataRole.AccessibleTextRole, str(item.get("title") or item.get("name") or "记忆条目"))
                row.setToolTip(str(item.get("title") or item.get("name") or "记忆条目"))
                box = QWidget()
                box.setObjectName("memoryRow")
                box.setAccessibleName(str(item.get("title") or item.get("name") or "记忆条目"))
                box.setAccessibleDescription("双击编辑；使用复选框加入批量操作")
                box.setFixedHeight(52)
                self._rich_tooltip.attach(box)
                lay = QHBoxLayout(box)
                lay.setContentsMargins(14, 4, 14, 4)
                lay.setSpacing(10)
                check = QCheckBox()
                check.setAccessibleName(f"选择 {item.get('title') or item.get('name') or '记忆条目'}")
                check.setProperty("memory_name", item.get("name", ""))
                check.stateChanged.connect(lambda _state: self._update_batch_bar())
                lay.addWidget(check)
                self._hook_shift_checkbox(check, len(self._row_checks))  # v1.9.0：Shift 连选
                self._row_checks.append(check)
                text = QVBoxLayout()
                text.setContentsMargins(0, 0, 0, 0)
                text.setSpacing(1)
                title = ElideLabel(str(item.get("title") or item.get("name") or ""))
                title.setObjectName("rowTitle")
                desc = ElideLabel(str(item.get("description") or ""))
                desc.setObjectName("rowDesc")
                desc.setToolTip(desc.text())
                text.addWidget(title, 1)
                text.addWidget(desc, 1)
                lay.addLayout(text, 1)
                # v1.10.0B（Stitch 结构）：右侧四列——标签 / 分类胶囊 / 来源 / 等宽时间，
                # 列宽与 #listHeader 列头一一对应；类型胶囊色随 taxonomy token 走
                type_key = str(item.get("type") or "reference")
                tags = ElideLabel(" · ".join((item.get("tags") or [])[:3]))
                tags.setObjectName("rowCol")
                # v1.10.0C：ElideLabel 默认 Ignored 策略会让 setFixedWidth 失效
                # （固定列不被布局计入、右侧列重叠越界），固定列必须改回 Fixed
                tags.setFixedWidth(self._col_tags)
                tags.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
                tags.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                tags.setToolTip("、".join(item.get("tags") or []))
                lay.addWidget(tags)
                type_color = type_colors.get(type_key, type_colors.get("reference", "#4F46E5"))
                pill = QLabel(tr(TYPE_LABELS.get(type_key, "参考")))
                pill.setObjectName("typePill")
                pill.setProperty("pillType", type_key)
                pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
                pill.setFixedWidth(self._col_type - 12)
                pill.setFixedHeight(22)
                pill.setStyleSheet(_type_pill_style(type_color))
                lay.addWidget(pill, alignment=Qt.AlignmentFlag.AlignCenter)
                source_label = _memory_source_label(item.get("source"))
                source = ElideLabel(source_label)
                source.setObjectName("rowCol")
                source.setFixedWidth(self._col_source)
                source.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
                source.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                lay.addWidget(source)
                updated = ElideLabel(str(item.get("updated", ""))[:10])
                updated.setObjectName("rowTime")
                updated.setFixedWidth(self._col_time)
                updated.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
                updated.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                lay.addWidget(updated)
                for child in (title, desc, tags, pill, source, updated):
                    self._rich_tooltip.attach(child)
                row.setSizeHint(QSize(0, 52))
                self.entry_list.addItem(row)
                self.entry_list.setItemWidget(row, box)
                # 登记行内文字控件，刷新/重译后复位样式用
                self._row_meta.append({"title": title, "desc": desc, "tags": tags, "pill": pill, "source": source, "time": updated, "color": type_color})
            # Restore the previous row while signals are blocked. A refresh
            # must never turn a dirty editor into a selection confirmation.
            target = -1
            if selected:
                for i in range(self.entry_list.count()):
                    if self.entry_list.item(i).data(Qt.ItemDataRole.UserRole) == selected:
                        target = i
                        break
            if target < 0 and self.entry_list.count():
                target = 0
            if target >= 0:
                auto_load_name = str(self.entry_list.item(target).data(Qt.ItemDataRole.UserRole)) if not had_current else ""
                self.entry_list.setCurrentRow(target)
        finally:
            self.entry_list.blockSignals(was_blocked)
            self._refreshing_listing = False
        # 刷新/保存后滚回原选中行（不再跳回列表开头），并复位行内文字样式
        if target >= 0:
            current_item = self.entry_list.item(target)
            if current_item is not None:
                self.entry_list.scrollToItem(current_item, QAbstractItemView.ScrollHint.PositionAtCenter)
        self._paint_selected_rows()
        if auto_load_name:
            self._load_detail(auto_load_name)
        self._apply_stats(result); self.empty_card.setVisible(not self._items); self.content_splitter.setVisible(bool(self._items)); self.edit_window_button.setEnabled(bool(self._items)); self.batch_bar.setVisible(False); self._set_status(f"已刷新 {len(self._items)} 条")

    def _apply_stats(self, result):
        stats = result.get("stats") or {"total": len(self._items), "inbox_pending": result.get("inbox_pending", 0), "types": {}}
        self.totalChanged.emit(int(stats.get("total", len(self._items))))
        types = stats.get("types") or {}
        for key in ("total", "user", "project", "reference", "feedback", "this_week", "inbox_pending"):
            label = self.stat_buttons[key].property("i18n_stat")
            count = str(stats.get(key, types.get(key, 0)))
            self.stat_buttons[key].setProperty("i18n_count", count)
            self.stat_buttons[key].setText(f"{tr(label)} {count}")
        pending = int(stats.get("inbox_pending") or result.get("inbox_pending") or 0)
        inbox_label = tr("投递箱")
        self.inbox_button.setText(f"{inbox_label} · {pending}" if pending else inbox_label)

    def retranslate(self):
        self._equalize_header_actions()
        self.shift_hint.setText(tr(SHIFT_RANGE_HINT))
        if hasattr(self, "_last_result"):
            self._apply_listing(self._last_result)
        result = getattr(self, "_last_result", {}) or {}
        stats = result.get("stats") or {}
        pending = int(stats.get("inbox_pending") or result.get("inbox_pending") or 0)
        inbox_label = tr("投递箱")
        self.inbox_button.setText(f"{inbox_label} · {pending}" if pending else inbox_label)

    def _stat_filter(self, key):
        if key in {"user", "project", "reference", "feedback"}: self.type_filter.setCurrentIndex(max(0, self.type_filter.findData(key)))
        elif key == "inbox_pending": self.open_inbox()
        else: self.type_filter.setCurrentIndex(0); self.search.clear()

    def _selected_names(self):
        names = []
        for index in range(self.entry_list.count()):
            widget = self.entry_list.itemWidget(self.entry_list.item(index)); check = widget.findChild(QCheckBox) if widget else None
            if check and check.isChecked(): names.append(str(check.property("memory_name")))
        return names

    def _checkbox_at_row(self, row: int):
        """v1.9.0：ShiftRangeCheckMixin 宿主接口——第 row 行的多选框。"""
        return self._row_checks[row] if 0 <= row < len(self._row_checks) else None

    def _shift_range_applied(self, low: int, high: int) -> None:
        self._set_status(f"已连选第 {low + 1}–{high + 1} 条（共 {high - low + 1} 条）")
        self._update_batch_bar()

    def _update_batch_bar(self):
        if hasattr(self, "batch_bar"):
            self.batch_bar.setVisible(bool(self._selected_names()))

    def _toggle_all_rows(self, checked: bool) -> None:
        """v1.10.0B：列头主复选框——勾选/取消当前列表全部行（与 Shift 连选等效）。"""
        for check in self._row_checks:
            check.setChecked(checked)
        self._update_batch_bar()

    def _paint_selected_rows(self):
        """刷新后统一复位行内文字样式。

        v1.10.0C：选中行改为主题色浅染（theme.py #memoryList::item:selected），
        文字保持墨色不再反白，这里只需清空历史内联样式并把分类胶囊重置回类型色。
        """
        for index in range(self.entry_list.count()):
            item = self.entry_list.item(index)
            meta = self._row_meta[index] if index < len(self._row_meta) else None
            if item is None or meta is None:
                continue
            meta["title"].setStyleSheet("")
            meta["desc"].setStyleSheet("")
            meta["tags"].setStyleSheet("")
            meta["source"].setStyleSheet("")
            meta["time"].setStyleSheet("")
            meta["pill"].setStyleSheet(_type_pill_style(meta["color"]))

    def _memory_tooltip_text(self, pos) -> str:
        row = self.entry_list.itemAt(pos)
        if row is None:
            return ""
        name = str(row.data(Qt.ItemDataRole.UserRole) or "")
        item = next((candidate for candidate in self._items if str(candidate.get("name") or "") == name), None)
        if not item:
            return ""
        title = str(item.get("title") or item.get("name") or "记忆条目")
        description = str(item.get("description") or "（无语义摘要）")
        tags = "、".join(str(tag) for tag in (item.get("tags") or [])) or "（无标签）"
        type_label = tr(TYPE_LABELS.get(str(item.get("type") or "reference"), "参考"))
        source = _memory_source_label(item.get("source"))
        updated = str(item.get("updated") or "—")
        return f"{title}\n摘要：{description}\n标签：{tags}\n分类：{type_label}\n来源：{source}\n同步时间：{updated}"

    def _selection_changed(self, current, _previous):
        if not current: return
        if self._refreshing_listing:
            return
        if self._dirty and self._current_name and not self._confirm_discard_edit():
            if _previous is not None:
                self.entry_list.blockSignals(True); self.entry_list.setCurrentItem(_previous); self.entry_list.blockSignals(False)
            return
        self._load_detail(str(current.data(Qt.ItemDataRole.UserRole)))

    def _confirm_discard_edit(self) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("未保存修改")
        box.setText("放弃当前编辑并打开另一条？")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText("放弃")
        box.button(QMessageBox.StandardButton.No).setText("继续编辑")
        return box.exec() == QMessageBox.StandardButton.Yes

    def _load_detail(self, name, show=False):
        if show:
            # Open the non-modal shell immediately. The previous entry must
            # not remain visible while disk work is in flight.
            self._loading = True
            self._set_editor_enabled(False)
            self.detail_title.setText("正在加载…")
            self.body_edit.clear()
            self.preview.clear()
            self._set_status("正在加载记忆详情…")
            self._show_editor()
        def done(entry):
            self._apply_detail(entry)
        def failed(msg):
            self._loading = False
            # ocr 审查修复：加载失败时编辑器停在"全字段禁用"状态无法输入——
            # 恢复可用让用户可以改投别的条目或直接重试
            self._set_editor_enabled(True)
            self._set_status(f"详情读取失败：{msg}")
            self.detail_title.setText("读取失败")
        self.scope.call("detail", self.facade.get_entry, done, failed, name)

    def load_detail_sync(self, name): result = self.facade.get_entry(name); self._apply_detail(result); return result

    def _apply_detail(self, entry):
        self._loading = True; self._creating = False; self._dirty = False; self._collision_name = ""; self.collision_label.clear(); self.open_collision_button.setVisible(False); self._current_name = str(entry.get("name") or ""); self.detail_title.setText(str(entry.get("title") or self._current_name)); self.name_edit.setText(self._current_name); self.title_edit.setText(str(entry.get("title") or "")); self.description_edit.setText(str(entry.get("description") or "")); self.type_edit.setCurrentIndex(max(0, self.type_edit.findData(entry.get("type", "reference")))); self.tags_edit.setText(", ".join(entry.get("tags") or [])); self.body_edit.setPlainText(str(entry.get("body") or "")); self.preview.setMarkdown(str(entry.get("body") or "")); self.created_label.setText(f"创建：{entry.get('created') or '未知'}"); self.updated_label.setText(f"更新：{entry.get('updated') or '未知'}"); self._set_links(entry.get("links") or []); self.name_preview.setText(self._name_preview(self._current_name)); self._loading = False; self._set_editor_enabled(True); self._set_status("已加载")

    def _set_links(self, links):
        while self.links_box.count() > 2:
            item = self.links_box.takeAt(1)
            if item.widget(): item.widget().deleteLater()
        for link in links:
            target = str(link.get("name") or "")
            button = QPushButton(f"[[{target}]]")
            button.setEnabled(bool(link.get("exists")))
            button.setToolTip("打开条目" if link.get("exists") else "未创建")
            if link.get("exists"):
                button.clicked.connect(lambda _checked=False, target=target: self.load_detail_sync(target))
            self.links_box.insertWidget(self.links_box.count() - 1, button)

    @staticmethod
    def _name_preview(value):
        import re
        clean = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", value.strip()).strip("-").lower()
        return f"文件名预览：{clean or '保存时自动生成'}.md"

    def _check_name(self):
        candidate = self.name_edit.text().strip()
        if not candidate or candidate == self._current_name:
            self._collision_name = ""
            self.collision_label.clear(); self.open_collision_button.setVisible(False)
            return
        self.scope.call("collision", self.facade.get_entry,
                        lambda _entry: self._show_collision(candidate),
                        lambda _message: (self.collision_label.clear(), self.open_collision_button.setVisible(False)), candidate)

    def _show_collision(self, name):
        self._collision_name = str(name)
        self.collision_label.setText("已有同名条目")
        self.open_collision_button.setVisible(True)

    def _open_collision(self):
        name = getattr(self, "_collision_name", "")
        if not name:
            return
        self._load_detail(name, show=True)

    def _restore_editor_geometry(self):
        settings = ui_settings(self.facade.config_store.config_dir)
        geometry = settings.value("memory-editor/geometry")
        if geometry:
            self.editor_dialog.restoreGeometry(geometry)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.editor_dialog.resize(min(1100, int(screen.width() * .85)), int(screen.height() * .75))

    def _save_editor_geometry(self):
        settings = ui_settings(self.facade.config_store.config_dir)
        settings.setValue("memory-editor/geometry", self.editor_dialog.saveGeometry())

    def _show_editor(self):
        self.editor_dialog.show(); self.editor_dialog.raise_(); self.editor_dialog.activateWindow()

    def edit_selected(self):
        item = self.entry_list.currentItem()
        name = str(item.data(Qt.ItemDataRole.UserRole)) if item else self._current_name
        if name:
            self._load_detail(name, show=True)

    def open_entry(self, name: str) -> None:
        """Open a graph/list entry with the same immediate loading shell."""
        self._load_detail(str(name), show=True)

    def open_new_editor(self):
        self.new_entry(); self._show_editor()

    def new_entry(self):
        self._creating = True; self._current_name = ""; self._collision_name = ""; self.collision_label.clear(); self.open_collision_button.setVisible(False); self._dirty = False; self.detail_title.setText("新建记忆"); self._loading = True
        for field in (self.name_edit, self.title_edit, self.description_edit, self.tags_edit): field.clear()
        self.body_edit.clear(); self._set_links([]); self.created_label.clear(); self.updated_label.clear(); self._loading = False; self._set_editor_enabled(True); self.title_edit.setFocus(); self._set_status("填写后保存")

    def _payload(self): return {"name": self.name_edit.text().strip(), "title": self.title_edit.text().strip(), "description": self.description_edit.text().strip(), "type": self.type_edit.currentData() or "reference", "tags": [x.strip() for x in self.tags_edit.text().replace("，", ",").split(",") if x.strip()], "body": self.body_edit.toPlainText()}

    def save_current(self):
        if not self.title_edit.text().strip(): self._set_status("请先填写标题"); return
        payload = self._payload(); old = self._current_name; fn = self.facade.create_entry if self._creating else self.facade.update_entry; args = (payload,) if self._creating else (old, payload); self._set_status("保存中…")
        self.scope.call("save", fn, lambda result: (self._apply_detail(result), self.refresh(), self._set_status("已保存")), lambda msg: self._set_status(f"保存失败：{msg}"), *args)

    def save_current_sync(self):
        result = self.facade.create_entry(self._payload()) if self._creating else self.facade.update_entry(self._current_name, self._payload()); self._apply_detail(result); self.refresh_sync(); return result

    def delete_current(self):
        if not self._current_name: return
        if QMessageBox.question(self, "确认软删除", f"将「{self.detail_title.text()}」移入 memory-trash？") != QMessageBox.StandardButton.Yes: return
        self.scope.call("delete", self.facade.delete_entry, lambda _result: (self._set_editor_enabled(False), self.refresh(), self._set_status("已移入 memory-trash")), lambda msg: self._set_status(f"删除失败：{msg}"), self._current_name)

    def hard_delete_current(self):
        """v1.9.0（需求 3）：彻底删除——直接删除条目文件，不进回收目录、不可恢复。"""
        if not self._current_name: return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("彻底删除记忆")
        box.setText(f"将「{self.detail_title.text()}」彻底删除？\n\n文件将直接从磁盘移除，不进入 memory-trash 回收目录，删除后无法恢复。")
        confirm = box.addButton("彻底删除", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not confirm: return
        name = self._current_name

        def done(_result):
            self._set_editor_enabled(False); self.refresh(); self._set_status(f"已彻底删除「{name}」（不可恢复）")

        def failed(msg):
            self._set_status(f"彻底删除失败：{msg}")

        self.scope.call("delete", lambda: self.facade.delete_entry(name, hard=True), done, failed)

    def delete_current_sync(self, name=None):
        result = self.facade.delete_entry(name or self._current_name); self._current_name = ""; self._set_editor_enabled(False); self.refresh_sync(); return result

    def _toggle_max(self):
        window = self.window(); window.showMaximized() if not window.isMaximized() else window.showNormal()

    def _show_preview(self): self.preview.setMarkdown(self.body_edit.toPlainText()); self.body_stack.setCurrentIndex(1)

    def ai_description(self):
        body = self.body_edit.toPlainText(); before_title = self.title_edit.text().strip(); before_desc = self.description_edit.text().strip(); self._set_status("AI 草稿生成中…")
        def done(result):
            if not before_title and not self.title_edit.text().strip(): self.title_edit.setText(str(result.get("title") or ""))
            if not before_desc and not self.description_edit.text().strip(): self.description_edit.setText(str(result.get("description") or ""))
            # ocr 审查修复：程序化回填不触发 _mark_dirty 的焦点判定——不显式
            # 标脏的话，焦点在编辑器外时关闭窗口不会弹"放弃修改"确认，AI 内容静默丢失
            self._dirty = True
            self._set_status("AI 草稿已填入空位，请确认后保存")
        self.scope.call("ai", self.facade.ai_draft, done, lambda msg: self._set_status(f"AI 草稿失败：{msg}"), body)

    def copy_prompt(self):
        # v1.7.5：统一走右上角「Agent连接提示词」——复制成功在按钮下方弹「已复制」小框
        copy_agent_prompt(self.facade, self.agent_button, self.runner)

    def batch_update_type(self, _index):
        names = self._selected_names(); value = self.batch_type.currentData();
        if names and value: self._batch(self.facade.bulk_update, names, type_name=value)
        self.batch_type.setCurrentIndex(0)

    def batch_update_tags(self):
        names = self._selected_names(); tags = [x.strip() for x in self.batch_tags.text().replace("，", ",").split(",") if x.strip()]
        if names: self._batch(self.facade.bulk_update, names, tags=tags)

    def batch_delete(self):
        names = self._selected_names();
        if names and QMessageBox.question(self, "批量删除", f"确认删除 {len(names)} 条？（软删除：移入 memory-trash，可找回）") == QMessageBox.StandardButton.Yes: self._batch(self.facade.bulk_delete, names)

    def batch_ai(self):
        """v1.8.0（审查 P0-2）：AI 补全改后台任务——每条最长 60s 的网络调用
        原来在 GUI 线程串行执行会冻结界面；现在有进度汇报，完成经
        repositoryChanged 自动刷新列表。"""
        names = self._selected_names()
        if not names:
            return

        def work(report):
            for index, name in enumerate(names, start=1):
                entry = self.facade.get_entry(name)
                if not entry.get("title") or not entry.get("description"):
                    draft = self.facade.ai_draft(entry.get("body", ""))
                    self.facade.update_entry(name, {key: value for key, value in draft.items() if not entry.get(key)})
                report(int(index * 100 / len(names)), f"AI 补全 {index}/{len(names)}")
            return {"updated": len(names)}

        self.jobs.submit("ai", f"AI 补全（{len(names)} 条）", work, progress=True)
        self._set_status(f"已提交 {len(names)} 条 AI 补全任务")

    def _batch(self, fn, *args, **kwargs):
        """v1.8.0（审查 P0-2）：批量写操作（改分类/打标签/软删除）改后台线程，
        完成后回调里异步刷新列表，不再同步做全量对账。"""
        def done(result):
            updated = result.get("updated", result.get("deleted", []))
            failed = result.get("failed", result.get("errors", []))
            self._set_status(f"已 {len(updated) if isinstance(updated, list) else updated} 条，失败 {len(failed)} 条")
            self.refresh()
        self.scope.call("batch", fn, done, lambda msg: self._set_status(f"批量操作失败：{msg}"), *args, **kwargs)
        self._set_status("批量操作执行中…")

    def _panel_dialog_active(self, attr: str) -> bool:
        """v1.7.3：浏览类窗口（投递箱/日报/索引）非模态后，重复点按钮置前已有窗口而不是再开一个。"""
        existing = getattr(self, attr, None)
        if existing is None:
            return False
        try:
            if existing.isVisible():
                existing.raise_()
                existing.activateWindow()
                return True
        except RuntimeError:
            # C++ 对象已随 WA_DeleteOnClose 销毁，清理悬挂引用
            setattr(self, attr, None)
        return False

    def _register_panel_dialog(self, attr: str, dialog) -> None:
        """v1.7.3：非模态浏览窗口登记到页面属性，关闭（含 reject）后自毁并清引用。"""
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.finished.connect(dialog.deleteLater)
        dialog.destroyed.connect(lambda *_: setattr(self, attr, None))
        setattr(self, attr, dialog)
        dialog.show()

    def open_inbox(self):
        """v1.8.0（审查 H-2/H-3）：投递列表改后台读取（扫目录不再冻结界面）；
        窗口构造按「构造/填充/绑定」拆三个方法，替代原 500+ 字符单行长语句。"""
        if self._panel_dialog_active("_inbox_dialog"):
            return
        self._set_status("正在读取投递箱…")

        def done(result):
            dialog, parts = self._build_inbox_dialog()
            self._fill_inbox_items(dialog, parts, list(result.get("items") or []))
            self._bind_inbox_actions(dialog, parts)
            if parts["left"].count():
                parts["left"].setCurrentRow(0)
            self._register_panel_dialog("_inbox_dialog", dialog)

        self.scope.call("inbox", self.facade.list_inbox, done, lambda msg: self._set_status(f"投递箱读取失败：{msg}"))

    def _build_inbox_dialog(self):
        dialog = QDialog(self)
        dialog.resize(1060, 650)
        root = QVBoxLayout(dialog)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QListWidget()
        right = QFrame(); rl = QVBoxLayout(right)
        raw = QPlainTextEdit(); raw.setReadOnly(True); raw.setFont(QFont(system_font_family(), 9))
        warning = QLabel(""); warning.setObjectName("error"); warning.setWordWrap(True)
        rl.addWidget(warning); rl.addWidget(QLabel("投递原文（只读）")); rl.addWidget(raw, 1)
        form = QFormLayout()
        title = QLineEdit(); name = QLineEdit(); typ = QComboBox(); [typ.addItem(label, value) for label, value in TYPE_OPTIONS]
        tags = QLineEdit(); desc = QLineEdit()
        form.addRow("标题", title); form.addRow("条目名", name); form.addRow("类型", typ); form.addRow("标签", tags); form.addRow("描述", desc)
        rl.addLayout(form)
        ai = QPushButton("AI 补全标题与描述"); rl.addWidget(ai)
        splitter.addWidget(left); splitter.addWidget(right); splitter.setSizes([350, 700])
        root.addWidget(splitter, 1)
        buttons = QDialogButtonBox()
        admit = buttons.addButton("收编入库", QDialogButtonBox.ButtonRole.AcceptRole)
        discard = buttons.addButton("丢弃选中", QDialogButtonBox.ButtonRole.DestructiveRole)
        all_discard = buttons.addButton("全部丢弃", QDialogButtonBox.ButtonRole.DestructiveRole)
        close = buttons.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole)
        root.addWidget(buttons)
        parts = {"left": left, "raw": raw, "warning": warning, "title": title, "name": name, "typ": typ,
                 "tags": tags, "desc": desc, "ai": ai, "admit": admit, "discard": discard, "all_discard": all_discard, "close": close}
        return dialog, parts

    def _fill_inbox_items(self, dialog, parts, items):
        left = parts["left"]
        for item in items:
            row = QListWidgetItem(f"{item.get('title') or item.get('suggested_name') or item.get('file')}\n{item.get('file')}")
            row.setData(Qt.ItemDataRole.UserRole, item)
            left.addItem(row)
        dialog.setWindowTitle(f"投递箱（{len(items)}）")

    def _bind_inbox_actions(self, dialog, parts):
        left, raw, warning = parts["left"], parts["raw"], parts["warning"]

        def selected():
            value = left.currentItem().data(Qt.ItemDataRole.UserRole) if left.currentItem() else None
            return value if isinstance(value, dict) else None

        def fill(item):
            value = item.data(Qt.ItemDataRole.UserRole) if item else {}
            raw.setPlainText(str(value.get("raw_text") or value.get("body") or ""))
            warning.setText("检测到疑似提示词注入内容，请仔细审阅" if value.get("injection_hits") else "")
            parts["title"].setText(str(value.get("title") or value.get("suggested_name") or ""))
            parts["name"].setText(str(value.get("suggested_name") or ""))
            parts["desc"].setText(str(value.get("description") or ""))
            parts["typ"].setCurrentIndex(max(0, parts["typ"].findData(value.get("type", "reference"))))
            parts["tags"].setText(", ".join(value.get("tags") or []))

        left.currentItemChanged.connect(fill)

        def admit_one():
            value = selected()
            if not value: return
            try:
                self.facade.admit_inbox(str(value.get("file")), {"title": parts["title"].text().strip(), "name": parts["name"].text().strip(), "type": parts["typ"].currentData(), "tags": [x.strip() for x in parts["tags"].text().split(",") if x.strip()], "description": parts["desc"].text().strip()})
                left.takeItem(left.currentRow()); self.refresh(); self._set_status("已收编")
            except Exception as exc: self._set_status(f"收编失败：{exc}")

        def discard_one():
            value = selected()
            if not value: return
            try:
                self.facade.discard_inbox(str(value.get("file"))); left.takeItem(left.currentRow()); self.refresh(); self._set_status("已丢弃")
            except Exception as exc: self._set_status(f"丢弃失败：{exc}")

        def discard_all():
            if QMessageBox.question(dialog, "全部丢弃", "将全部投递移入回收区？") == QMessageBox.StandardButton.Yes:
                self.facade.discard_all_inbox(); left.clear(); self.refresh()

        def ai_fill():
            # v1.8.0（审查 P0-2）：AI 补全改后台——60s 网络调用不再冻结投递箱窗口
            def done(draft):
                parts["title"].setText(parts["title"].text() or draft.get("title", ""))
                parts["desc"].setText(parts["desc"].text() or draft.get("description", ""))
                parts["ai"].setEnabled(True)

            def failed(msg):
                warning.setText(f"AI 补全失败：{msg}"); parts["ai"].setEnabled(True)

            parts["ai"].setEnabled(False)
            self.scope.call("ai", self.facade.ai_draft, done, failed, raw.toPlainText())

        parts["admit"].clicked.connect(admit_one)
        parts["discard"].clicked.connect(discard_one)
        parts["all_discard"].clicked.connect(discard_all)
        parts["ai"].clicked.connect(ai_fill)
        parts["close"].clicked.connect(dialog.reject)

    def tidy(self):
        if self.jobs: self.jobs.submit("tidy", "归纳整理", lambda: self.facade.tidy_run(use_ai=True))
        else: self._set_status(str(self.facade.tidy_run(use_ai=True)))

    def show_reports(self):
        if self._panel_dialog_active("_reports_dialog"):
            return
        try: data = self.facade.tidy_reports(); reports = data.get("items") or []
        except Exception as exc: self._set_status(str(exc)); return
        dialog = QDialog(self); dialog.setWindowTitle("整理日报"); dialog.resize(900, 600); layout = QHBoxLayout(dialog); files = QListWidget(); content = QTextBrowser(); layout.addWidget(files); layout.addWidget(content, 1)
        for report in reports: row = QListWidgetItem(str(report.get("file") or report)); row.setData(Qt.ItemDataRole.UserRole, report.get("file") if isinstance(report, dict) else str(report)); files.addItem(row)
        def show(item):
            if item:
                try: content.setMarkdown(str(self.facade.tidy_report(item.data(Qt.ItemDataRole.UserRole)).get("content", "")))
                except Exception as exc: content.setPlainText(str(exc))
        files.currentItemChanged.connect(show)
        if files.count(): files.setCurrentRow(0)
        self._register_panel_dialog("_reports_dialog", dialog)

    def copy_duty(self):
        """v1.8.0（审查 P0-2）：值守提示词生成要读全库统计——改后台线程，
        回 GUI 线程再写剪贴板。"""
        from PySide6.QtWidgets import QApplication

        def done(text):
            QApplication.clipboard().setText(str(text)); self._set_status("值守提示词已复制")

        self._set_status("正在生成值守提示词…")
        self.scope.call("duty", self.facade.duty_prompt, done, lambda msg: self._set_status(f"复制失败：{msg}"))

    def show_index(self):
        if self._panel_dialog_active("_index_dialog"):
            return
        self._set_status("正在读取索引…")

        def done(data):
            dialog = QDialog(self); dialog.setWindowTitle("MEMORY.md（只读索引源文件）"); dialog.resize(900, 650); layout = QVBoxLayout(dialog); note = QLabel(str(data.get("note") or "索引由程序维护，手动修改会被覆盖。")); note.setObjectName("muted"); layout.addWidget(note); view = QPlainTextEdit(); view.setReadOnly(True); view.setFont(QFont(system_font_family(), 9)); view.setPlainText(str(data.get("content") or "")); layout.addWidget(view)
            self._register_panel_dialog("_index_dialog", dialog)

        self.scope.call("index", self.facade.index_file, done, lambda msg: self._set_status(f"索引读取失败：{msg}"))
