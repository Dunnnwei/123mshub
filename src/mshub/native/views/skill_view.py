"""Native skill and safety pages wired to the existing repository services."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget, QCheckBox, QHeaderView, QTextBrowser, QGroupBox, QFileDialog, QFrame,
)

from ..memory_facade import MemoryFacade
from ..state import ui_settings
from ..theme import current_palette as _current_palette, system_font_family
from ..task_runner import TaskRunner, RequestScope
from ..job_controller import JobController
from ..column_resize import ResizableColumnsTable
from ..i18n import tr
from ..ui import (SHIFT_RANGE_HINT, AdaptivePage, CheckableTableMixin, DataTable, FlowLayout,
                  HeaderBand, ShiftRangeCheckMixin, copy_agent_prompt, make_agent_prompt_button,
                  open_singleton_dialog, prepare_dialog, label_controls)


def _error(payload: object) -> str:
    return str(payload.get("error") if isinstance(payload, dict) else payload)


# v1.7.2：软删除语义说明（与记忆库一致：移入回收目录、原件保留可查）
SOFT_DELETE_SKILL_TIP = (
    "软删除：只把这个技能的目录移入仓库回收目录 .meta\\trash（按删除时间归档），\n"
    "列表会立即隐藏该条目；原始文件完整保留在磁盘上，并没有被销毁。\n"
    "需要找回时，到「仓库根目录\\.meta\\trash」里按时间戳目录取回对应技能目录即可。"
)


def _interface_language_is_english() -> bool:
    """v1.8.0（审查 M-3）：改读 LanguageController 维护的权威状态，
    不再用 `tr("中文") != "中文"` 探针（依赖翻译表巧合，表一改就反转）。"""
    from ..i18n import ui_is_english

    return ui_is_english()


# v1.7.3：安全状态中文映射从 SecurityPage 提为模块函数，技能列表"安全"列复用
# （原来技能列表显示英文原始枚举，与安全中心页不一致）
_SECURITY_LABELS = {"unchecked": "未检查", "safe": "已通过", "warning": "需复核", "error": "存在风险", "critical": "存在风险"}

# v1.7.4：安全列排序用——按风险从低到高（未检查 → 已通过 → 需复核 → 存在风险）
_SECURITY_RANK = {"unchecked": 0, "safe": 1, "warning": 2, "error": 3, "critical": 3}


def _security_rank(status) -> int:
    return _SECURITY_RANK.get(str(status or "unchecked").casefold(), 0)


def _security_label(status) -> str:
    return _SECURITY_LABELS.get(str(status).casefold(), str(status or "未检查"))


class _SkillTable(ResizableColumnsTable):
    def selected_names(self) -> list[tuple[str, str]]:
        out = []
        for row in range(self.rowCount()):
            check = self.cellWidget(row, 0)
            if isinstance(check, QCheckBox) and check.isChecked():
                out.append((str(self.item(row, 1).data(Qt.ItemDataRole.UserRole)), str(self.item(row, 1).data(Qt.ItemDataRole.UserRole + 1) or "")))
        return out

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "user_column_widths") or self.user_column_widths:
            return
        # Initial layout fills a wide viewport. Every column stays interactive;
        # narrow windows scroll instead of hiding fields or shrinking headers.
        widths = [56, max(190, min(300, int(self.width() * .22))), 96, 200, 94, 120, 168]
        widths[3] = max(200, self.viewport().width() - sum(widths) + widths[3])
        for col, width in enumerate(widths):
            self.setColumnWidth(col, width)
        self.sync_column_handles()


class SkillsPage(ShiftRangeCheckMixin, CheckableTableMixin, AdaptivePage):
    totalChanged = Signal(int)

    def __init__(self, facade: MemoryFacade, runner: TaskRunner, jobs: JobController, parent=None):
        super().__init__(parent)
        self.facade, self.runner, self.jobs = facade, runner, jobs
        self.scope = RequestScope(runner, self)
        self.items: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        # v1.7.4：表头排序状态（None = 保持服务层返回顺序）与编辑保存后的回跳目标
        self._sort_col: int | None = None
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._pending_focus: tuple[str, str] | None = None
        self._detail_dialog: QDialog | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(20, 14, 20, 12); root.setSpacing(12)
        # v1.10.0B（Stitch 结构）：页头 = 横向信息带（眉标胶囊+标题+分隔线+副题，动作组右侧）
        band = HeaderBand("技能资产", "技能仓库", "复用已有仓库能力；业务安装、更新、安全与对账沿用现有服务层。")
        add = QPushButton("添加技能 / 程序"); add.setObjectName("ghost"); add.clicked.connect(self.open_add); band.actions.addWidget(add)
        self.agent_button = make_agent_prompt_button(self, self.copy_prompt); band.actions.addWidget(self.agent_button)
        root.addWidget(band)
        filters = FlowLayout(spacing=8)
        self.search = QLineEdit(); self.search.setPlaceholderText("搜索名称、说明、来源地址或标签"); self.search.setAccessibleName("搜索技能或程序"); self.search.setAccessibleDescription("搜索名称、说明、来源地址或标签"); self.search.textChanged.connect(self._debounced)
        self.search.setMinimumWidth(220); filters.addWidget(self.search)
        self.provider = QComboBox(); self.provider.addItem("全部来源", ""); self.provider.addItem("GitHub 源", "github"); self.provider.addItem("本地自研", "local"); self.provider.currentIndexChanged.connect(self.refresh); filters.addWidget(self.provider)
        self.category = QComboBox(); self.category.addItem("全部资产", ""); self.category.addItem("技能", "skill"); self.category.addItem("程序", "project"); self.category.currentIndexChanged.connect(self.refresh); filters.addWidget(self.category)
        refresh = QPushButton("刷新"); refresh.clicked.connect(self.refresh); filters.addWidget(refresh)
        # v1.7.5：显式编辑入口——双击路径失效时（v1.7.4 曾发生）也能进编辑窗口
        edit_selected = QPushButton("编辑选中"); edit_selected.setToolTip("打开当前选中行的「编辑技能信息」窗口；双击行亦可进入详情后编辑。"); edit_selected.clicked.connect(self.edit_metadata); filters.addWidget(edit_selected)
        root.addLayout(filters)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        # v1.7.4：表头"选"改"多选"；各列表头点击排序（正/反序切换），
        # "多选"表头点击 = 全选 / 全取消（见 _header_clicked）
        self.table = _SkillTable(0, 7); self.table.setAccessibleName("技能与程序列表"); self.table.setAccessibleDescription("使用方向键选择，Enter 或双击查看详情；点击表头排序；拖动任意竖向分隔线调整列宽"); self.table.setHorizontalHeaderLabels(["多选", "名称", "来源", "说明", "安全", "标签", "更新时间"]); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.verticalHeader().setDefaultSectionSize(44); self.table.verticalHeader().setMinimumSectionSize(44); self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed); self.table.setWordWrap(False); self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded); self.table.itemSelectionChanged.connect(self._selection_changed); self.table.itemActivated.connect(lambda _item: self.show_detail_dialog()); self.table.itemDoubleClicked.connect(lambda _item: self.show_detail_dialog())
        # v1.7.5 修复（推翻 v1.7.4 的判断）：v1.7.4 只留 itemActivated（以为 Windows
        # 双击必触发它），实测打包版双击无反应 → 详情打不开、编辑无入口。现恢复
        # itemDoubleClicked 为主路径 + itemActivated（Enter 键）备用；show_detail_dialog
        # 内 0.35s 防重入，双信号同时到达也不会叠开两个窗口。
        # v1.7.5 修复（根因）：_SkillTable 漏设 NoEditTriggers——QTableWidget 默认
        # editTriggers 含 DoubleClicked，双击被"进入编辑"路径吞掉，clicked/
        # doubleClicked/activated 全都不发射（安全中心的 DataTable 设过所以双信号
        # 都发、v1.6.0 才会弹双窗；技能表没设，v1.7.4 删掉 doubleClicked 后彻底无反应）。
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().sectionClicked.connect(self._header_clicked)
        # v1.7.4：隐藏行号列（与安全中心 DataTable 一致；原来技能表一直显示 1/2/3…）
        self.table.verticalHeader().hide()
        splitter.addWidget(self.table)
        # v1.6.0：详情面板默认不显示（改为弹窗），保留 splitter 结构便于回退
        detail = QGroupBox("技能详情"); detail_layout = QVBoxLayout(detail)
        self.detail_title = QLabel("选择一项"); self.detail_title.setObjectName("sectionTitle")
        self.detail_text = QTextBrowser(); self.detail_text.setOpenExternalLinks(False); self.detail_text.setFont(QFont(system_font_family(), 9))
        detail_layout.addWidget(self.detail_title); detail_layout.addWidget(self.detail_text, 1)
        action = QHBoxLayout()
        self.check_button = QPushButton("离线检查"); self.check_button.setObjectName("primary"); self.check_button.clicked.connect(lambda: self.scan("offline")); action.addWidget(self.check_button)
        self.ai_check_button = QPushButton("AI 检查"); self.ai_check_button.clicked.connect(lambda: self.scan("ai")); action.addWidget(self.ai_check_button)
        self.trust_button = QPushButton("信任放行"); self.trust_button.clicked.connect(self.trust); action.addWidget(self.trust_button)
        self.update_button = QPushButton("更新"); self.update_button.clicked.connect(self.update); action.addWidget(self.update_button)
        self.delete_button = QPushButton("软删除"); self.delete_button.setObjectName("danger"); self.delete_button.setToolTip(SOFT_DELETE_SKILL_TIP); self.delete_button.clicked.connect(self.delete); action.addWidget(self.delete_button)
        self.edit_button = QPushButton("编辑信息"); self.edit_button.clicked.connect(self.edit_metadata); action.addWidget(self.edit_button)
        detail_layout.addLayout(action)
        prompt = QHBoxLayout(); self.prompt_button = QPushButton("复制指定技能提示词"); self.prompt_button.clicked.connect(self.copy_skill_prompt); prompt.addWidget(self.prompt_button); self.install_prompt_button = QPushButton("复制安装提示词"); self.install_prompt_button.clicked.connect(self.copy_install_prompt); prompt.addWidget(self.install_prompt_button); detail_layout.addLayout(prompt)
        splitter.addWidget(detail); detail.setVisible(False); splitter.setHandleWidth(0); splitter.setChildrenCollapsible(True); splitter.setSizes([720, 0]); self.content_splitter = splitter  # Detail opens in a dialog; no draggable splitter handle.
        empty = QFrame(objectName="emptyCard"); empty_layout = QVBoxLayout(empty); empty_layout.addWidget(QLabel("还没有技能或程序", objectName="title"), alignment=Qt.AlignmentFlag.AlignHCenter); empty_layout.addWidget(QLabel("从 GitHub URL、owner/repo 或本地目录添加第一项资产。", objectName="muted"), alignment=Qt.AlignmentFlag.AlignHCenter); empty_add = QPushButton("添加技能 / 程序"); empty_add.setObjectName("primary"); empty_add.clicked.connect(self.open_add); empty_layout.addWidget(empty_add, alignment=Qt.AlignmentFlag.AlignHCenter); self.empty_card = empty; root.addWidget(empty); root.addWidget(splitter, 1); empty.hide()
        batch = FlowLayout(spacing=8); batch.addWidget(QLabel("已勾选条目：")); self.batch_check = QPushButton("批量离线检查"); self.batch_check.clicked.connect(lambda: self.batch_scan("offline")); batch.addWidget(self.batch_check); self.batch_ai_check = QPushButton("批量 AI 检查"); self.batch_ai_check.clicked.connect(lambda: self.batch_scan("ai")); batch.addWidget(self.batch_ai_check); self.batch_update = QPushButton("批量更新 GitHub"); self.batch_update.clicked.connect(self.batch_update_github); batch.addWidget(self.batch_update); self.batch_trust = QPushButton("批量信任"); self.batch_trust.clicked.connect(self.batch_trust_items); batch.addWidget(self.batch_trust); self.batch_translate = QPushButton("批量中文翻译"); self.batch_translate.clicked.connect(self.batch_translate_items); batch.addWidget(self.batch_translate); self.batch_delete = QPushButton("批量删除"); self.batch_delete.setObjectName("danger"); self.batch_delete.setToolTip("删除勾选的技能/程序（软删除：移入仓库回收目录 .meta\\trash，可找回；\n也可在列表聚焦时按 Delete 键触发）。"); self.batch_delete.clicked.connect(self.batch_delete_items); batch.addWidget(self.batch_delete); root.addLayout(batch)
        # v1.9.0：底部状态行 + Shift 连选提示（右对齐贴表格右边线）
        bottom = QHBoxLayout(); self.status = QLabel(""); self.status.setObjectName("status"); bottom.addWidget(self.status, 1); self.shift_hint = QLabel(SHIFT_RANGE_HINT); self.shift_hint.setObjectName("helper"); bottom.addWidget(self.shift_hint); root.addLayout(bottom)
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(300); self._timer.timeout.connect(self._refresh_now); self.metadata_dialog = None
        label_controls(self)
        # v1.9.0：列表聚焦时按 Delete 键 = 删除勾选项（WidgetShortcut 不抢输入框的 Delete）
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self.table)
        self._delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._delete_shortcut.activated.connect(self.batch_delete_items)

    def _debounced(self): self._timer.start()

    def showEvent(self, event):
        self.refresh()
        label_controls(self)
        super().showEvent(event)

    def _set_status(self, text): self.status.setText(text)

    def refresh(self, *_): self._timer.start()

    def _refresh_now(self):
        query = self.search.text().strip().casefold(); provider = self.provider.currentData() or ""; category = self.category.currentData() or ""
        def done(data):
            rows = list(data.get("items") or {}) if isinstance(data, dict) else []
            self.totalChanged.emit(len(rows))
            self.items = [row for row in rows if (not provider or row.get("provider") == provider) and (not category or row.get("item_type") == category) and (not query or query in str(row).casefold())]
            self._apply_rows()
        self.scope.call("list", self.facade.skills, done, lambda msg: self._set_status(f"技能列表读取失败：{msg}"))

    def _apply_rows(self):
        self.invalidate_shift_anchor()  # v1.9.1：行号即将重建，旧 Shift 锚点作废（审查 P1-3）
        # v1.7.4：重建行前记住勾选与选中项，排序/刷新后不丢多选，并跳回原选中行
        checked = {(name, library) for name, library in self.table.selected_names()}
        previous = self.current
        focus = self._pending_focus
        self._pending_focus = None
        self._sort_rows()
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            check = QCheckBox(); check.setAccessibleName(f"选择 {item.get('name') or '技能条目'}")
            if (str(item.get("name") or ""), str(item.get("library") or "")) in checked:
                check.setChecked(True)
            self.table.setCellWidget(row, 0, check)
            self._hook_shift_checkbox(check, row)  # v1.9.0：Shift 连选
            name = QTableWidgetItem(str(item.get("name") or "")); name.setData(Qt.ItemDataRole.UserRole, item.get("name", "")); name.setData(Qt.ItemDataRole.UserRole + 1, item.get("library", "")); self.table.setItem(row, 1, name)
            name.setToolTip(str(item.get("name") or ""))
            provider = item.get("provider") or "github"; source = tr("GitHub 源") if provider == "github" else tr("本地自研")
            source_item = QTableWidgetItem(source); source_item.setToolTip("本地自研技能无在线源头，版本请在编辑信息中手动维护。" if provider == "local" else "可检查版本、更新")
            self.table.setItem(row, 2, source_item)
            self.table.setItem(row, 3, QTableWidgetItem(self._display_description(item)))
            security = _security_label(item.get("security_status", "unchecked"))
            security_item = QTableWidgetItem(security)
            security_item.setToolTip(f"{security}（原始状态：{str(item.get('security_status') or 'unchecked')}）")
            self.table.setItem(row, 4, security_item)
            self.table.setItem(row, 5, QTableWidgetItem(", ".join(item.get("tags") or [])))
            self.table.setItem(row, 6, QTableWidgetItem(str(item.get("updated_at") or "")[:19].replace("T", " ")))
            for col in range(self.table.columnCount()):
                cell = self.table.item(row, col)
                if cell is not None:
                    cell.setToolTip(cell.toolTip() or cell.text())
            self.table.setRowHeight(row, 44)
        self.empty_card.setVisible(not self.items); self.content_splitter.setVisible(bool(self.items)); self._set_status(f"已加载 {len(self.items)} 项")
        self._restore_selection(focus, previous)

    def _restore_selection(self, focus, previous):
        """v1.7.4：刷新/排序后选中原选中行（或编辑保存的目标行）并滚动到可视区。"""
        target = -1
        for candidate in (focus, (str(previous.get("name") or ""), str(previous.get("library") or "")) if previous else None):
            if not candidate or not candidate[0]:
                continue
            for row, item in enumerate(self.items):
                if str(item.get("name") or "") == candidate[0] and str(item.get("library") or "") == candidate[1]:
                    target = row
                    break
            if target >= 0:
                break
        if target < 0 and self.items:
            target = 0
        if target >= 0:
            self.table.selectRow(target)
            anchor = self.table.item(target, 1)
            if anchor is not None:
                self.table.scrollToItem(anchor, QTableWidget.ScrollHint.PositionAtCenter)

    def _sort_rows(self):
        """按表头排序状态原地排序；未点过表头时保持服务层顺序（纯排序，不重建行）。"""
        if self._sort_col is None:
            return
        col = self._sort_col
        def key(item):
            if col == 1: return str(item.get("name") or "").casefold()
            if col == 2: return str(item.get("provider") or "")
            if col == 3: return self._display_description(item).casefold()
            if col == 4: return _security_rank(item.get("security_status"))
            if col == 5: return ", ".join(item.get("tags") or []).casefold()
            if col == 6: return str(item.get("updated_at") or "")
            return ""
        self.items.sort(key=key, reverse=self._sort_order == Qt.SortOrder.DescendingOrder)

    def _apply_sort(self, col: int, order: Qt.SortOrder):
        """v1.8.0（审查 P2-4）：表头点击分派进 CheckableTableMixin——排序并重建行。"""
        self._sort_col, self._sort_order = col, order
        self._sort_rows()
        self._apply_rows()

    def _after_select_all(self, target: bool, count: int):
        self._set_status(f"已{'全选' if target else '全部取消选择'} {count} 项")

    def _checkbox_at_row(self, row: int):
        """v1.9.0：ShiftRangeCheckMixin 宿主接口——第 row 行的多选框。"""
        return self.table.cellWidget(row, 0)

    def _shift_range_applied(self, low: int, high: int) -> None:
        self._set_status(f"已连选第 {low + 1}–{high + 1} 行（共 {high - low + 1} 项）")

    def _toggle_select_all(self):
        rows = range(self.table.rowCount())
        checks = [self.table.cellWidget(row, 0) for row in rows]
        checks = [check for check in checks if isinstance(check, QCheckBox)]
        if not checks:
            return
        target = not all(check.isChecked() for check in checks)
        for check in checks:
            check.setChecked(target)
        self._set_status(f"已{'全选' if target else '全部取消选择'} {len(checks)} 项")

    def retranslate(self):
        if self.items:
            self._apply_rows()

    def _selection_changed(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows: self.current = None; return
        item = self.items[rows[0].row()]; self.current = item; self.detail_title.setText(str(item.get("name") or ""))
        self.detail_text.setPlainText(self._format_detail(item))
        local = item.get("provider") == "local"
        self.update_button.setEnabled(not local); self.trust_button.setEnabled(True); self.check_button.setEnabled(True); self.ai_check_button.setEnabled(True)

    @staticmethod
    def _display_description(item) -> str:
        """v1.7.2：说明列跟随界面语言——中文界面优先中文说明，英文界面优先英文说明；缺失回退另一语言。"""
        zh = str(item.get("description_zh") or "")
        en = str(item.get("description") or "")
        return (en or zh) if _interface_language_is_english() else (zh or en)

    @staticmethod
    def _format_detail(item):
        lines = [f"来源: {item.get('source_url') or '本地自研'}", f"目录: {item.get('local_dir') or ''}", f"库: {item.get('library') or ''}", f"版本: {item.get('version') or '未知'}", f"安全: {item.get('security_status') or 'unchecked'}", "", f"中文说明: {item.get('description_zh') or '（未填写，可在编辑信息中补全或自动翻译）'}", f"英文说明: {item.get('description') or '（未填写，可在编辑信息中补全或自动翻译）'}"]
        return "\n".join(lines)

    def _selected(self):
        return self.current or {}

    def show_detail_dialog(self):
        """v1.6.0：双击行弹出详情窗口（和记忆库的双击编辑逻辑一致）；
        v1.7.4：单实例——已有窗口时关旧开新，不再叠出多个要关多次的窗口；
        v1.7.5：0.35s 防重入（itemActivated 与 itemDoubleClicked 双绑定时同一双击
        可能两个信号都到，防重入保证只开一个窗）。"""
        item = self._selected()
        if not item:
            return

        # v1.8.0（审查 P2-4）：单实例/防重入/销毁身份判断统一进 open_singleton_dialog
        def build():
            dialog = QDialog(self)
            dialog.setWindowTitle(f"技能详情 - {item.get('name')}")
            dialog.setModal(False)
            dialog.resize(640, 480)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(20, 18, 20, 18)
            title = QLabel(str(item.get("name") or ""))
            # Detail dialogs follow the shared section tier instead of adding
            # a one-off 18px size that breaks the Stitch type scale.
            title.setObjectName("sectionTitle")
            layout.addWidget(title)
            text = QTextBrowser()
            text.setOpenExternalLinks(False)
            text.setFont(QFont(system_font_family(), 9))
            text.setPlainText(self._format_detail(item))
            layout.addWidget(text, 1)
            # 操作按钮（复用现有逻辑）
            actions = QHBoxLayout()
            check_btn = QPushButton("离线检查"); check_btn.clicked.connect(lambda: (self.scan("offline"), dialog.close())); actions.addWidget(check_btn)
            ai_check_btn = QPushButton("AI 检查"); ai_check_btn.clicked.connect(lambda: (self.scan("ai"), dialog.close())); actions.addWidget(ai_check_btn)
            trust_btn = QPushButton("信任放行"); trust_btn.clicked.connect(lambda: (self.trust(), dialog.close())); actions.addWidget(trust_btn)
            update_btn = QPushButton("更新"); update_btn.clicked.connect(lambda: (self.update(), dialog.close())); update_btn.setEnabled(item.get("provider") != "local"); actions.addWidget(update_btn)
            delete_btn = QPushButton("软删除"); delete_btn.setObjectName("danger"); delete_btn.setToolTip(SOFT_DELETE_SKILL_TIP); delete_btn.clicked.connect(lambda: (self.delete(), dialog.close())); actions.addWidget(delete_btn)
            # v1.9.0：软删除旁的「删除」= 彻底删除（不可恢复）
            hard_btn = QPushButton("删除"); hard_btn.setObjectName("danger"); hard_btn.setToolTip("彻底删除：直接移除磁盘上的技能目录，不进回收目录 .meta\\trash，删除后无法恢复。"); hard_btn.clicked.connect(lambda: (self.hard_delete(), dialog.close())); actions.addWidget(hard_btn)
            edit_btn = QPushButton("编辑信息"); edit_btn.clicked.connect(lambda: (self.edit_metadata(), dialog.close())); actions.addWidget(edit_btn)
            layout.addLayout(actions)
            close_btn = QPushButton("关闭"); close_btn.clicked.connect(dialog.close); layout.addWidget(close_btn)
            prepare_dialog(dialog)
            return dialog

        open_singleton_dialog(self, "_detail_dialog", build)

    def scan(self, route):
        item = self._selected();
        if not item: return
        self._set_status("安全检查任务已提交…")
        self.jobs.submit("scan", f"检查 {item.get('name')}", lambda report: self.facade.skill_scan(item["name"], item.get("library", ""), route=route, progress=report), progress=True)

    def trust(self):
        item = self._selected();
        if not item: return
        if QMessageBox.question(self, "确认信任", "确认保留人工放行标记并信任此技能？") != QMessageBox.StandardButton.Yes: return
        self.jobs.submit("trust", f"信任 {item['name']}", lambda: self.facade.skill_trust(item["name"], item.get("library", "")))

    def update(self):
        item = self._selected();
        if not item or item.get("provider") == "local": return
        self.jobs.submit("update", f"更新 {item['name']}", lambda report: self.facade.skill_update(item["name"], item.get("library", ""), progress=report), progress=True)

    def delete(self):
        item = self._selected();
        if not item: return
        if QMessageBox.question(self, "软删除技能", f"将「{item['name']}」移入回收区？") != QMessageBox.StandardButton.Yes: return
        self.jobs.submit("delete", f"删除 {item['name']}", lambda: self.facade.skill_delete(item["name"], item.get("library", "")))

    def hard_delete(self):
        """v1.9.0：彻底删除——直接从磁盘移除技能目录，不进回收区、不可恢复。"""
        item = self._selected()
        if not item: return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("彻底删除技能")
        box.setText(f"将「{item['name']}」从磁盘彻底删除？\n\n不进入回收目录 .meta\\trash，删除后无法恢复。")
        confirm = box.addButton("彻底删除", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not confirm: return
        self.jobs.submit("delete", f"删除 {item['name']}", lambda: self.facade.skill_delete(item["name"], item.get("library", ""), hard=True))

    def edit_metadata(self):
        item = self._selected()
        if item:
            if not hasattr(self, "metadata_dialog") or self.metadata_dialog is None:
                self.metadata_dialog = MetadataDialog(self, item)
            else:
                self.metadata_dialog.load_item(item)
            self.metadata_dialog.show(); self.metadata_dialog.raise_(); self.metadata_dialog.activateWindow()

    def _checked(self):
        return self.table.selected_names()

    def batch_scan(self, route):
        selected = self._checked()
        for name, library in selected:
            self.jobs.submit("scan", f"检查 {name}", lambda report, name=name, library=library: self.facade.skill_scan(name, library, route=route, progress=report), progress=True)
        if selected: self._set_status(f"已提交 {len(selected)} 条安全检查任务")

    def batch_update_github(self):
        selected = [(name, library) for name, library in self._checked() if next((x for x in self.items if x.get("name") == name and x.get("library", "") == library), {}).get("provider") != "local"]
        for name, library in selected:
            self.jobs.submit("update", f"更新 {name}", lambda report, name=name, library=library: self.facade.skill_update(name, library, progress=report), progress=True)
        if selected: self._set_status(f"已提交 {len(selected)} 条更新任务；本地自研已跳过")

    def batch_trust_items(self):
        selected = self._checked()
        if selected and QMessageBox.question(self, "批量信任", f"确认人工放行 {len(selected)} 项？") == QMessageBox.StandardButton.Yes:
            for name, library in selected: self.jobs.submit("trust", f"信任 {name}", lambda name=name, library=library: self.facade.skill_trust(name, library))

    def batch_translate_items(self):
        names = [name for name, _library in self._checked()]
        if names: self.jobs.submit("translate", f"翻译（{len(names)} 项）", lambda report: self.facade.skill_translate_batch(names, progress=report), progress=True)

    def batch_delete_items(self):
        """v1.9.0：批量删除勾选项（软删除入 .meta\\trash，可找回）。"""
        selected = self._checked()
        if not selected:
            self._set_status("先勾选要删除的技能/程序（支持 Shift 连选）")
            return
        if QMessageBox.question(self, "批量删除", f"确认删除勾选的 {len(selected)} 项？（移入回收目录 .meta\\trash，可找回）") != QMessageBox.StandardButton.Yes:
            return
        for name, library in selected:
            self.jobs.submit("delete", f"删除 {name}", lambda name=name, library=library: self.facade.skill_delete(name, library))
        self._set_status(f"已提交 {len(selected)} 条删除任务（软删除，回收目录 .meta\\trash 可找回）")

    def copy_prompt(self):
        # v1.7.5：与全站统一——右上角「Agent连接提示词」复制注入提示词并弹「已复制」
        copy_agent_prompt(self.facade, self.agent_button, self.runner)

    def copy_skill_prompt(self):
        item = self._selected();
        if not item: return
        from PySide6.QtWidgets import QApplication
        try: QApplication.clipboard().setText(self.facade.skill_install_prompt(item["name"], item.get("library", ""))); self._set_status("指定技能提示词已复制")
        except Exception as exc: self._set_status(f"复制失败：{exc}")

    def copy_install_prompt(self): self.copy_skill_prompt()

    def open_add(self): AddSkillDialog(self).exec()


class MetadataDialog(QDialog):
    def __init__(self, page, item):
        super().__init__(page); self.page, self.item = page, item; self.setWindowTitle("编辑技能信息"); self.resize(700, 500); self.setModal(False); self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        root = QVBoxLayout(self); form = QFormLayout()
        self.name = QLineEdit(); form.addRow("条目身份", self.name)
        self.directory = QLineEdit(); self.directory.textChanged.connect(self._directory_hint); form.addRow("目录名", self.directory)
        self.provider = QComboBox(); self.provider.addItem("GitHub", "github"); self.provider.addItem("本地自研", "local"); form.addRow("来源", self.provider)
        self.source = QLineEdit(); self.source.textChanged.connect(self._source_hint); form.addRow("来源地址", self.source)
        self.source_hint = QLabel(""); self.source_hint.setObjectName("muted"); form.addRow("解析预览", self.source_hint)
        self.library = QComboBox(); self.library.addItem("共享技能库", "skills"); self.library.addItem("程序库", "github"); form.addRow("所属库", self.library)
        self.version = QLineEdit(); form.addRow("版本", self.version)
        root.addLayout(form)
        # v1.7.2：中英说明从单行输入改为多行双栏，平分编辑窗口的剩余空间（原来各 1 行难以预读/编辑）
        # v1.7.4：objectName 让这条可拖把手在"分隔条透明化"全局样式下保持可见
        descriptions = QSplitter(Qt.Orientation.Horizontal); descriptions.setObjectName("descSplitter"); descriptions.setChildrenCollapsible(False); descriptions.setHandleWidth(4)
        zh_box = QGroupBox("中文说明"); zh_layout = QVBoxLayout(zh_box)
        self.description_zh = QPlainTextEdit(); self.description_zh.setAccessibleName("中文说明"); self.description_zh.setPlaceholderText("技能的中文说明。可手工填写，或留空后点下方「自动翻译」由英文说明生成。")
        zh_layout.addWidget(self.description_zh)
        en_box = QGroupBox("英文说明"); en_layout = QVBoxLayout(en_box)
        self.description = QPlainTextEdit(); self.description.setAccessibleName("英文说明"); self.description.setPlaceholderText("English description of the skill. Leave empty and click Auto-translate to generate the Chinese side.")
        en_layout.addWidget(self.description)
        descriptions.addWidget(zh_box); descriptions.addWidget(en_box); descriptions.setSizes([1, 1])
        root.addWidget(descriptions, 1)
        # v1.7.2：补回自动翻译按钮；v1.7.4 明确目标态：点完后固定「左栏中文 / 右栏英文」
        translate_row = QHBoxLayout()
        self.translate_button = QPushButton("自动翻译"); self.translate_button.setObjectName("primary")
        self.translate_button.setToolTip(
            "调用设置中已配置的 AI 接口，保证「左栏中文说明 / 右栏英文说明」：\n"
            "说明原文是中文时，先把它移到左栏，再翻译出英文填入右栏；\n"
            "左栏若是英文说明，先移到右栏，再翻译出中文填入左栏；\n"
            "两侧语言装反时直接交换。已是中文/英文各一侧时不重复翻译。"
        )
        self.translate_button.clicked.connect(self.auto_translate)
        self.translate_status = QLabel(""); self.translate_status.setObjectName("muted"); self.translate_status.setWordWrap(True)
        translate_row.addWidget(self.translate_button); translate_row.addWidget(self.translate_status, 1)
        root.addLayout(translate_row)
        note = QLabel("改名只改变身份；目录字段才决定仓库归属。目录不能包含 /、\\ 或以点开头。"); note.setObjectName("muted"); root.addWidget(note); buttons = QDialogButtonBox(); save = buttons.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole); close = buttons.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole); root.addWidget(buttons); save.clicked.connect(self.save); close.clicked.connect(self._hide); prepare_dialog(self); label_controls(self); self._restore_geometry(); self.load_item(item)

    def _restore_geometry(self):
        settings = ui_settings(self.page.facade.config_store.config_dir)
        geometry = settings.value("skill-editor/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.resize(min(1100, int(screen.width() * .85)), int(screen.height() * .75))

    def _save_geometry(self):
        settings = ui_settings(self.page.facade.config_store.config_dir)
        settings.setValue("skill-editor/geometry", self.saveGeometry())

    def _hide(self):
        self._save_geometry()
        self.hide()

    def closeEvent(self, event):
        self._save_geometry(); event.accept()

    def load_item(self, item):
        self.item = item
        # ocr 审查修复：切换条目时复位按钮（上一条的翻译任务可能还在跑/已过期）
        self.translate_button.setEnabled(True)
        self.name.setText(str(item.get("name") or "")); self.directory.setText(Path(str(item.get("local_dir") or "")).name); self.provider.setCurrentIndex(max(0, self.provider.findData(item.get("provider", "github")))); self.source.setText(str(item.get("source_url") or "")); self.library.setCurrentIndex(max(0, self.library.findData(item.get("library", "skills")))); self.version.setText(str(item.get("version") or "")); self.description.setPlainText(str(item.get("description") or "")); self.description_zh.setPlainText(str(item.get("description_zh") or "")); self.translate_status.clear(); self._directory_hint(); self._source_hint(); self.setWindowTitle(f"编辑技能信息 · {item.get('name', '')}")

    def _directory_hint(self):
        value = self.directory.text().strip(); self.directory.setStyleSheet(f"color:{_current_palette().get('error', '#B42318')}" if "/" in value or "\\" in value or value.startswith(".") else "")

    def _source_hint(self):
        value = self.source.text().strip()
        if not value: self.source_hint.setText("本地自研不需要远程来源"); return
        try:
            from ...urltool import parse_source
            parsed = parse_source(value); self.source_hint.setText(f"作者 {parsed.owner} · 仓库 {parsed.repo} · 分支 {parsed.ref or 'HEAD'} · 子目录 {parsed.subdir or '根目录'}")
        except Exception as exc: self.source_hint.setText(f"地址待修正：{exc}")

    @staticmethod
    def _looks_chinese(text: str) -> bool:
        """v1.7.4：含 CJK 字符即按中文处理（本产品中文优先，说明里混排英文词不算英文说明）。"""
        return any("\u4e00" <= ch <= "\u9fff" for ch in text)

    def auto_translate(self):
        """v1.7.4：点「自动翻译」后固定达到「左栏中文说明 / 右栏英文说明」。

        旧行为只补空侧：原文说明是中文时把中文又译到左栏，两边都是中文。
        现在先做不调接口的语言归位（中文进左栏、英文进右栏、装反则交换），
        再把仍空（或语言不对）的一侧用 AI 翻译补齐。
        """
        zh = self.description_zh.toPlainText().strip()
        en = self.description.toPlainText().strip()
        if not zh and not en:
            self.translate_status.setText("请先在任意一侧填写说明，再点「自动翻译」。"); return
        moved = ""
        if not zh and self._looks_chinese(en):
            # 说明原文是中文：先整体移到左栏，稍后翻译英文填右栏
            self.description_zh.setPlainText(en); self.description.clear()
            moved = "检测到说明原文是中文，已移到左栏；"
        elif zh and not en and not self._looks_chinese(zh):
            # 左栏实际是英文：先移到右栏，稍后翻译中文填左栏
            self.description.setPlainText(zh); self.description_zh.clear()
            moved = "检测到左栏是英文说明，已移到右栏；"
        elif zh and en and not self._looks_chinese(zh) and self._looks_chinese(en):
            self.description_zh.setPlainText(en); self.description.setPlainText(zh)
            self.translate_status.setText("两侧说明语言装反，已交换为「左中文 / 右英文」。"); return
        zh = self.description_zh.toPlainText().strip()
        en = self.description.toPlainText().strip()
        zh_cn = self._looks_chinese(zh)
        en_cn = self._looks_chinese(en)
        if zh and en and zh_cn and not en_cn:
            self.translate_status.setText("两侧说明已分别是中文/英文，无需翻译；如需重译请先清空对应一侧。"); return
        # 翻译方向：左栏是中文 → 译英文；否则用右栏（英文）译中文。
        if zh and zh_cn:
            text, target = zh, "en"
        elif en:
            text, target = en, "zh"
        else:
            self.translate_status.setText("请先在任意一侧填写说明，再点「自动翻译」。"); return
        name = str(self.item.get("name") or "")
        self.translate_button.setEnabled(False)
        self.translate_status.setText(f"{moved}正在调用 AI 翻译…")

        def done(job):
            # ocr 审查修复：编辑窗是复用单例——翻译期间用户切换到另一条技能时，
            # 过期译文不能写进当前条目（A 的译文污染 B 的说明）
            if str(self.item.get("name") or "") != name:
                return
            self.translate_button.setEnabled(True)
            if job.get("status") == "error":
                self.translate_status.setText(f"翻译失败：{job.get('error') or '未知错误'}"); return
            translated = str(job.get("result") or "").strip()
            if not translated:
                self.translate_status.setText("翻译失败：接口没有返回译文。"); return
            # 只在目标侧为空或语言不对时回填；用户在翻译期间手填的正确内容优先
            if target == "zh":
                current = self.description_zh.toPlainText().strip()
                if not current or not self._looks_chinese(current):
                    self.description_zh.setPlainText(translated)
            else:
                current = self.description.toPlainText().strip()
                if not current or self._looks_chinese(current):
                    self.description.setPlainText(translated)
            self.translate_status.setText("翻译完成：左栏中文说明 / 右栏英文说明；确认内容后点「保存」。")

        self.page.jobs.submit("translate", f"翻译 {name}", lambda: self.page.facade.skill_translate_text(text, target), changed=False, callback=done)

    def save(self):
        updates = {"name": self.name.text().strip(), "dir_name": self.directory.text().strip(), "provider": self.provider.currentData(), "source_url": self.source.text().strip(), "target_library": self.library.currentData(), "version": self.version.text().strip(), "description": self.description.toPlainText().strip(), "description_zh": self.description_zh.toPlainText().strip()}
        # v1.7.4：登记保存后的回跳目标（含改名后的新条目名），列表刷新时滚回该行
        self.page._pending_focus = (updates["name"] or str(self.item.get("name") or ""), updates["target_library"] or self.item.get("library", ""))
        self.page.jobs.submit("metadata", f"保存 {self.item['name']}", lambda: self.page.facade.skill_update_metadata(self.item["name"], updates, self.item.get("library", "")))
        self.page._set_status("技能信息已提交后台保存")


class AddSkillDialog(QDialog):
    def __init__(self, page: SkillsPage):
        super().__init__(page); self.page = page; self.setWindowTitle("添加技能 / 程序"); self.resize(780, 560)
        root = QVBoxLayout(self); form = QFormLayout()
        self.source = QLineEdit(); self.source.setPlaceholderText("GitHub URL、owner/repo 或本地目录"); source_row = QHBoxLayout(); source_row.addWidget(self.source, 1); browse = QPushButton("选择本地目录…"); browse.clicked.connect(self.browse_local); source_row.addWidget(browse); form.addRow("来源", source_row)
        self.item_type = QComboBox(); self.item_type.addItem("技能", "skill"); self.item_type.addItem("程序", "project"); form.addRow("类型", self.item_type)
        self.mode = QComboBox(); self.mode.addItem("标准（按说明文件）", "standard"); self.mode.addItem("全仓（完整 Git）", "full"); form.addRow("安装模式", self.mode)
        # v1.7.2：与设置页一致——中文可读选项 + 悬停注解（数据值仍为 archive/git）
        self.fetcher = QComboBox(); self.fetcher.addItem("ZIP 压缩包（免装 Git）", "archive"); self.fetcher.addItem("Git 克隆（保留完整历史）", "git")
        # v1.7.3：默认值继承设置页当前配置（原来两处各自为政，用户改了设置这里仍是 archive）
        self.fetcher.setCurrentIndex(max(0, self.fetcher.findData(getattr(self.page.facade.config(), "fetcher", "archive"))))
        fetcher_tip = ("从 GitHub 获取技能/程序文件的方式：\nZIP 压缩包——下载仓库打包快照，速度快、无需安装 Git，但没有提交历史；\nGit 克隆——完整克隆仓库，保留提交历史、可增量更新，需要本机已安装 Git。")
        self.fetcher.setToolTip(fetcher_tip); fetcher_label = QLabel("技能下载方式"); fetcher_label.setToolTip(fetcher_tip); form.addRow(fetcher_label, self.fetcher)
        root.addLayout(form); self.preview = QTextBrowser(); self.preview.setAccessibleName("技能扫描预览"); root.addWidget(self.preview, 1)
        actions = QDialogButtonBox(); preview = actions.addButton("扫描预览", QDialogButtonBox.ButtonRole.ActionRole); install = actions.addButton("后台入库", QDialogButtonBox.ButtonRole.AcceptRole); close = actions.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole); root.addWidget(actions)
        preview.clicked.connect(self.do_preview); install.clicked.connect(self.do_install); close.clicked.connect(self.reject); prepare_dialog(self); label_controls(self)

    def options(self): return {"item_type": self.item_type.currentData(), "mode": self.mode.currentData(), "fetcher_name": self.fetcher.currentData()}

    def browse_local(self):
        selected = QFileDialog.getExistingDirectory(self, "选择本地技能或程序目录")
        if selected: self.source.setText(selected)

    def do_preview(self):
        try:
            result = self.page.facade.skill_preview(self.source.text().strip(), **self.options()); self.preview.setPlainText(str(result)); self.page._set_status("预览完成：已识别来源与目标库")
        except Exception as exc: self.preview.setPlainText(f"预览失败：{exc}")

    def do_install(self):
        source = self.source.text().strip()
        if not source: return
        self.page.jobs.submit("install", f"入库 {source}", lambda report: self.page.facade.skill_install(source, **self.options(), progress=report), progress=True)
        self.accept()


class SecurityPage(ShiftRangeCheckMixin, CheckableTableMixin, AdaptivePage):
    totalChanged = Signal(int)

    def __init__(self, facade, runner, jobs, parent=None):
        super().__init__(parent); self.facade, self.runner, self.jobs = facade, runner, jobs; self.scope = RequestScope(runner, self); self.items = []
        # v1.7.4：表头排序 +「检查通过后不显示」开关 + 多选列
        self._sort_col: int | None = None
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._report_dialog: QDialog | None = None
        settings = ui_settings(facade.config_store.config_dir)
        hidden = settings.value("security/hidePassed", False)
        self._hide_passed = hidden in (True, "true", 1, "1")
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(20, 14, 20, 12); root.setSpacing(12)
        # v1.10.0B（Stitch 结构）：页头 = 横向信息带
        band = HeaderBand("安全审核", "安全中心", "需要确认的条目可路线 A 离线检查、路线 B AI 检查，人工信任会保留记录。")
        self.agent_button = make_agent_prompt_button(self, self.copy_prompt); band.actions.addWidget(self.agent_button)
        root.addWidget(band)
        route_hint = QLabel("推荐先用路线 A · 离线；路线 B · AI 会把摘要发送到已配置接口。"); route_hint.setObjectName("helper"); route_hint.setWordWrap(True); root.addWidget(route_hint)
        # v1.9.1（需求 B）：按钮行从 FlowLayout 改回 QHBoxLayout 横排靠左——
        # FlowLayout 挂进 QHBoxLayout 后布局协商异常，实际渲染成竖排。
        # 「检查通过后不显示」是勾选框、与按钮视觉不一致——保持在行尾靠右独立摆放。
        bar_row = QHBoxLayout(); bar_row.setSpacing(10)
        self.route = QComboBox(); self.route.setAccessibleName("安全检查路线"); self.route.addItem("路线 A · 离线", "offline"); self.route.addItem("路线 B · AI", "ai"); bar_row.addWidget(self.route)
        self.batch = QPushButton("批量检查需要确认"); self.batch.setObjectName("primary"); self.batch.setToolTip("勾选了条目时优先检查勾选项；未勾选时检查全部需要确认的条目。"); self.batch.clicked.connect(self.batch_scan); bar_row.addWidget(self.batch)
        self.trust_checked = QPushButton("信任选中"); self.trust_checked.setToolTip("对勾选的条目做人工信任放行（勾选一条即单独信任，多条即批量信任）；\n信任后状态转为「已通过」并保留放行记录。"); self.trust_checked.clicked.connect(self.batch_trust_checked); bar_row.addWidget(self.trust_checked)
        refresh = QPushButton("刷新"); refresh.clicked.connect(self.refresh); bar_row.addWidget(refresh)
        bar_row.addStretch()
        # v1.7.4：打开后列表不再显示已通过检查的条目（配置存在 native-ui.ini，重启保留）
        self.hide_passed = QCheckBox("检查通过后不显示"); self.hide_passed.setChecked(self._hide_passed); self.hide_passed.toggled.connect(self._toggle_hide_passed)
        bar_row.addWidget(self.hide_passed)
        root.addLayout(bar_row)
        # v1.7.4：补"多选"列（与技能仓库一致），表头点击排序
        self.table = DataTable(["多选", "名称", "来源", "状态", "最近检查", "摘要"], "security"); self.table.setAccessibleDescription("使用方向键选择，Enter 或双击查看完整检查报告；点击表头按该列排序"); self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch); self.table.setWordWrap(False)
        self.table.horizontalHeader().sectionClicked.connect(self._header_clicked)
        # v1.7.5 修复：与技能仓库同因——v1.7.4 只留 itemActivated，实测双击不触发。
        # 恢复双绑 + show_report_dialog 内防重入，双击/Enter 都能开且只开一个窗。
        self.table.itemActivated.connect(lambda _item: self.show_report_dialog())
        self.table.itemDoubleClicked.connect(lambda _item: self.show_report_dialog())
        root.addWidget(self.table, 1)
        # v1.6.0：报告面板默认隐藏（改为双击弹窗），保留 widget 便于回退
        self.report = QPlainTextEdit(); self.report.setReadOnly(True); self.report.setPlaceholderText("选择条目查看检查报告"); self.report.setVisible(False); root.addWidget(self.report, 0)
        # v1.9.0（需求 2）：列表下方批量删除入口（软删除入 .meta\trash 可找回）
        bottom_bar = FlowLayout(spacing=8)
        self.batch_delete = QPushButton("批量删除"); self.batch_delete.setObjectName("danger")
        self.batch_delete.setToolTip("删除勾选的条目（软删除：移入仓库回收目录 .meta\\trash，可找回；\n也可在列表聚焦时按 Delete 键触发）。")
        self.batch_delete.clicked.connect(self.batch_delete_items); bottom_bar.addWidget(self.batch_delete)
        root.addLayout(bottom_bar)
        bottom = QHBoxLayout(); self.status = QLabel(""); self.status.setObjectName("status"); bottom.addWidget(self.status, 1)
        self.shift_hint = QLabel(SHIFT_RANGE_HINT); self.shift_hint.setObjectName("helper"); bottom.addWidget(self.shift_hint)
        root.addLayout(bottom)
        self.refresh()
        label_controls(self)
        # v1.9.0：列表聚焦时按 Delete 键 = 删除勾选项
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self.table)
        self._delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._delete_shortcut.activated.connect(self.batch_delete_items)

    def _toggle_hide_passed(self, checked: bool):
        self._hide_passed = bool(checked)
        settings = ui_settings(self.facade.config_store.config_dir)
        settings.setValue("security/hidePassed", self._hide_passed)
        self._apply({"items": self.items})

    def refresh(self):
        self.scope.call("list", self.facade.skills, self._apply, lambda msg: self.status.setText(f"读取失败：{msg}"))

    def _visible_items(self):
        items = self.items
        if self._hide_passed:
            items = [item for item in items if str(item.get("security_status") or "unchecked").casefold() != "safe"]
        return items

    def _sort_visible(self, items):
        if self._sort_col is None:
            return items
        col = self._sort_col
        def key(item):
            if col == 1: return str(item.get("name") or "").casefold()
            if col == 2: return str(item.get("provider") or "")
            if col == 3: return _security_rank(item.get("security_status"))
            if col == 4: return str(item.get("updated_at") or "")
            if col == 5: return self._security_summary(item)
            return ""
        return sorted(items, key=key, reverse=self._sort_order == Qt.SortOrder.DescendingOrder)

    def _apply_sort(self, col: int, order: Qt.SortOrder):
        """v1.8.0（审查 P2-4）：表头点击分派进 CheckableTableMixin——安全中心按列重排并重建。"""
        self._sort_col, self._sort_order = col, order
        self._apply({"items": self.items})

    def _after_select_all(self, target: bool, count: int):
        self.status.setText(f"已{'全选' if target else '全部取消选择'} {count} 项")

    def _checkbox_at_row(self, row: int):
        """v1.9.0：ShiftRangeCheckMixin 宿主接口——第 row 行的多选框。"""
        return self.table.cellWidget(row, 0)

    def _shift_range_applied(self, low: int, high: int) -> None:
        self.status.setText(f"已连选第 {low + 1}–{high + 1} 行（共 {high - low + 1} 项）")

    def _checked_items(self):
        out = []
        for row in range(self.table.rowCount()):
            check = self.table.cellWidget(row, 0)
            if isinstance(check, QCheckBox) and check.isChecked() and row < len(self._visible):
                out.append(self._visible[row])
        return out

    def _apply(self, data):
        self.invalidate_shift_anchor()  # v1.9.1：行号即将重建，旧 Shift 锚点作废（审查 P1-3）
        self.items = list(data.get("items") or {})
        self.totalChanged.emit(len(self.items))
        # 先用"旧表 + 旧可见列表"记录勾选与选中项，再重算可见列表（避免索引错位）
        checked = set()
        previous = ""
        if hasattr(self, "_visible"):
            checked = {str(item.get("name") or "") for item in self._checked_items()}
            selected = self.table.selectionModel().selectedRows()
            if selected and selected[0].row() < len(self._visible):
                previous = str(self._visible[selected[0].row()].get("name") or "")
        visible = self._sort_visible(self._visible_items())
        self._visible = visible
        self.table.setRowCount(len(visible))
        for row, item in enumerate(visible):
            check = QCheckBox(); check.setAccessibleName(f"选择 {item.get('name') or '条目'}")
            if str(item.get("name") or "") in checked:
                check.setChecked(True)
            self.table.setCellWidget(row, 0, check)
            self._hook_shift_checkbox(check, row)  # v1.9.0：Shift 连选
            provider = tr("GitHub 源") if item.get("provider") == "github" else tr("本地自研")
            values = (item.get("name", ""), provider, _security_label(item.get("security_status", "unchecked")), str(item.get("updated_at", ""))[:19], self._security_summary(item))
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col == 4:
                    # ocr 审查修复：values 是 5 元组（0-4），原判断 col == 5 永假
                    cell.setToolTip("双击查看完整检查报告")
                self.table.setItem(row, col + 1, cell)
            for col in range(self.table.columnCount()):
                cell = self.table.item(row, col)
                if cell is not None:
                    cell.setToolTip(cell.toolTip() or cell.text())
            self.table.setRowHeight(row, 44)
        hidden_count = len(self.items) - len(visible)
        summary = f"共 {len(self.items)} 项；需要确认的条目可直接信任或检查"
        if self._hide_passed:
            summary = f"共 {len(self.items)} 项，已通过 {hidden_count} 项已隐藏；需要确认的条目可直接信任或检查"
        self.status.setText(summary)
        target = -1
        if previous:
            for row, item in enumerate(visible):
                if str(item.get("name") or "") == previous:
                    target = row
                    break
        if target < 0 and visible:
            target = 0
        if target >= 0:
            self.table.selectRow(target)
            anchor = self.table.item(target, 1)
            if anchor is not None:
                self.table.scrollToItem(anchor, QTableWidget.ScrollHint.PositionAtCenter)

    @staticmethod
    def _security_label(status):
        return _security_label(status)

    @staticmethod
    def _security_summary(item):
        findings = item.get("security_findings") or []
        if not isinstance(findings, list):
            findings = [findings]
        if not findings:
            return "0 项命中"
        rank = {"critical": 5, "error": 5, "high": 4, "warning": 3, "medium": 3, "low": 2, "info": 1}
        labels = {"critical": "critical", "error": "error", "high": "high", "warning": "warning", "medium": "medium", "low": "low", "info": "info"}
        levels = []
        for finding in findings:
            if isinstance(finding, dict):
                levels.append(str(finding.get("severity") or finding.get("level") or "info").casefold())
            else:
                levels.append("info")
        highest = max(levels, key=lambda level: rank.get(level, 0))
        return f"{len(findings)} 项命中 · 最高 {labels.get(highest, highest)}"

    def _show_report(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            self.report.clear(); return
        findings = self.items[selected[0].row()].get("security_findings") or []
        import json
        self.report.setPlainText(json.dumps(findings, ensure_ascii=False, indent=2, default=str) if findings else "暂无命中项；状态由最近一次路线检查或人工放行记录提供。")

    def show_report_dialog(self):
        """v1.6.0：双击行弹出检查报告窗口；v1.8.0（审查 P2-4）：单实例/防重入/
        销毁身份判断统一进 ui.open_singleton_dialog（原为三段手写副本）。"""
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        rows = [row.row() for row in selected]
        if rows[0] >= len(self._visible):
            return
        item = self._visible[rows[0]]

        def build():
            dialog = QDialog(self)
            dialog.setWindowTitle(f"检查报告 - {item.get('name')}")
            dialog.setModal(False)
            dialog.resize(680, 520)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(20, 18, 20, 18)
            title = QLabel(str(item.get("name") or ""))
            title.setObjectName("sectionTitle")
            layout.addWidget(title)
            meta = QLabel(f"来源：{item.get('provider', 'unknown')} · 状态：{_security_label(item.get('security_status', 'unchecked'))} · 最近检查：{str(item.get('updated_at', ''))[:19]}")
            meta.setObjectName("muted")
            layout.addWidget(meta)
            report_text = QPlainTextEdit()
            report_text.setReadOnly(True)
            findings = item.get("security_findings") or []
            import json
            report_text.setPlainText(json.dumps(findings, ensure_ascii=False, indent=2, default=str) if findings else "暂无命中项；状态由最近一次路线检查或人工放行记录提供。")
            layout.addWidget(report_text, 1)
            close_btn = QPushButton("关闭"); close_btn.clicked.connect(dialog.close); layout.addWidget(close_btn)
            prepare_dialog(dialog)
            return dialog

        open_singleton_dialog(self, "_report_dialog", build)

    def batch_scan(self):
        route = self.route.currentData()
        # v1.7.4：勾选了条目优先检查勾选项；未勾选时保持旧行为（全部待确认）
        checked = self._checked_items()
        pending = checked or [i for i in self.items if i.get("security_status") in {"unchecked", "warning", "error"}]
        for item in pending:
            self.jobs.submit("scan", f"检查 {item['name']}", lambda report, item=item: self.facade.skill_scan(item["name"], item.get("library", ""), route=route, progress=report), progress=True)

    def batch_trust_checked(self):
        """v1.9.0（需求 4）：信任勾选条目——一条即单独信任，多条即批量信任。"""
        checked = self._checked_items()
        if not checked:
            self.status.setText("先勾选要信任的条目（支持 Shift 连选）")
            return
        if QMessageBox.question(self, "信任选中", f"确认人工放行勾选的 {len(checked)} 项？") != QMessageBox.StandardButton.Yes:
            return
        for item in checked:
            self.jobs.submit("trust", f"信任 {item['name']}", lambda item=item: self.facade.skill_trust(item["name"], item.get("library", "")))
        self.status.setText(f"已提交 {len(checked)} 条信任任务")

    def batch_delete_items(self):
        """v1.9.0（需求 2）：批量删除勾选项（软删除入 .meta\\trash，可找回）。"""
        checked = self._checked_items()
        if not checked:
            self.status.setText("先勾选要删除的条目（支持 Shift 连选）")
            return
        if QMessageBox.question(self, "批量删除", f"确认删除勾选的 {len(checked)} 项？（移入回收目录 .meta\\trash，可找回）") != QMessageBox.StandardButton.Yes:
            return
        for item in checked:
            self.jobs.submit("delete", f"删除 {item['name']}", lambda item=item: self.facade.skill_delete(item["name"], item.get("library", "")))
        self.status.setText(f"已提交 {len(checked)} 条删除任务（软删除，回收目录 .meta\\trash 可找回）")

    def copy_prompt(self):
        """v1.7.5：安全中心右上角「Agent连接提示词」。"""
        copy_agent_prompt(self.facade, self.agent_button, self.runner)

    def showEvent(self, event): self.refresh(); super().showEvent(event)

    def retranslate(self):
        if self.items:
            self._apply({"items": self.items})
