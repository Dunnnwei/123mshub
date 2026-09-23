"""Memory workspace: filters, multi-select, explicit editing and inbox review."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QPlainTextEdit, QSplitter, QStackedWidget, QTextBrowser, QVBoxLayout,
    QWidget, QCheckBox, QScrollArea, QToolButton,
)

from ..memory_facade import MemoryFacade
from ..task_runner import TaskRunner, RequestScope
from ..widgets import MarkdownView

TYPE_OPTIONS = [("用户", "user"), ("项目", "project"), ("参考", "reference"), ("反馈", "feedback")]
TYPE_COLORS = {"user": "#8B5CF6", "project": "#0156FC", "reference": "#0891B2", "feedback": "#D97706"}


def _error(payload: object) -> str:
    return str(payload.get("error") if isinstance(payload, dict) else payload)


class MemoryPage(QWidget):
    openGraphRequested = Signal()
    statusMessage = Signal(str)
    promptCopied = Signal()

    def __init__(self, facade: MemoryFacade, runner: TaskRunner, jobs=None, parent=None):
        super().__init__(parent)
        self.facade, self.runner, self.jobs = facade, runner, jobs
        self.scope = RequestScope(runner, self)
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(300); self._timer.timeout.connect(self._refresh_now)
        self._name_timer = QTimer(self); self._name_timer.setSingleShot(True); self._name_timer.setInterval(250); self._name_timer.timeout.connect(self._check_name)
        self._request_id = 0; self._current_name = ""; self._creating = False; self._loading = False; self._dirty = False; self._items: list[dict[str, Any]] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(30, 26, 30, 24); root.setSpacing(12)
        head = QHBoxLayout(); title_box = QVBoxLayout(); eyebrow = QLabel("SHARED MEMORY"); eyebrow.setObjectName("eyebrow"); title = QLabel("记忆库"); title.setObjectName("title"); sub = QLabel("条目文件是事实源；搜索、整理与收编都可回看。 "); sub.setObjectName("muted"); title_box.addWidget(eyebrow); title_box.addWidget(title); title_box.addWidget(sub); head.addLayout(title_box); head.addStretch()
        self.copy_button = QPushButton("复制注入提示词"); self.copy_button.setObjectName("primary"); self.copy_button.clicked.connect(self.copy_prompt); head.addWidget(self.copy_button); root.addLayout(head)
        self.stats_row = QHBoxLayout(); self.stat_buttons: dict[str, QPushButton] = {}
        for key, label in (("total", "总数"), ("user", "user"), ("project", "project"), ("reference", "reference"), ("feedback", "feedback"), ("this_week", "本周新增"), ("inbox_pending", "待收编")):
            button = QPushButton(f"{label} 0"); button.setFlat(True); button.clicked.connect(lambda _checked=False, key=key: self._stat_filter(key)); self.stat_buttons[key] = button; self.stats_row.addWidget(button)
        self.stats_row.addStretch(); root.addLayout(self.stats_row)
        toolbar = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText("搜索标题、描述、标签或正文全文"); self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self.refresh); toolbar.addWidget(self.search, 1)
        self.type_filter = QComboBox(); self.type_filter.addItem("全部类型", ""); [self.type_filter.addItem(label, value) for label, value in TYPE_OPTIONS]; self.type_filter.currentIndexChanged.connect(self.refresh); toolbar.addWidget(self.type_filter)
        self.sort = QComboBox(); self.sort.addItem("最近更新", "updated"); self.sort.addItem("创建时间", "created"); self.sort.addItem("名称", "name"); self.sort.currentIndexChanged.connect(self.refresh); toolbar.addWidget(self.sort)
        self.inbox_button = QPushButton("投递箱"); self.inbox_button.clicked.connect(self.open_inbox); toolbar.addWidget(self.inbox_button); root.addLayout(toolbar)
        batch = QHBoxLayout(); self.batch_hint = QLabel("勾选列表中的条目进行批量操作"); self.batch_hint.setObjectName("muted"); batch.addWidget(self.batch_hint); batch.addStretch(); self.batch_type = QComboBox(); self.batch_type.addItem("批量改分类…", ""); [self.batch_type.addItem(label, value) for label, value in TYPE_OPTIONS]; batch.addWidget(self.batch_type); self.batch_type.activated.connect(self.batch_update_type); self.batch_tags = QLineEdit(); self.batch_tags.setPlaceholderText("批量标签（逗号）"); self.batch_tags.setMaximumWidth(180); batch.addWidget(self.batch_tags); bt = QPushButton("应用标签"); bt.clicked.connect(self.batch_update_tags); batch.addWidget(bt); ai = QPushButton("AI 补全主题"); ai.clicked.connect(self.batch_ai); batch.addWidget(ai); bd = QPushButton("批量软删除"); bd.setObjectName("danger"); bd.clicked.connect(self.batch_delete); batch.addWidget(bd); root.addLayout(batch)
        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setChildrenCollapsible(False)
        self.entry_list = QListWidget(); self.entry_list.setMinimumWidth(340); self.entry_list.currentItemChanged.connect(self._selection_changed); splitter.addWidget(self.entry_list)
        detail = QFrame(); detail.setObjectName("surface"); dl = QVBoxLayout(detail); dl.setContentsMargins(20, 18, 20, 18); dl.setSpacing(9)
        dh = QHBoxLayout(); self.detail_title = QLabel("选择一条记忆"); self.detail_title.setStyleSheet("font-size:20px;font-weight:650"); dh.addWidget(self.detail_title); dh.addStretch(); self.new_button = QPushButton("新建"); self.new_button.clicked.connect(self.new_entry); dh.addWidget(self.new_button); self.max_button = QPushButton("放大编辑"); self.max_button.clicked.connect(self._toggle_max); dh.addWidget(self.max_button); dl.addLayout(dh)
        form = QFormLayout(); self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText("kebab-case，改名会重命名文件"); self.name_preview = QLabel(""); self.name_preview.setObjectName("muted"); self.collision_label = QLabel(""); self.collision_label.setStyleSheet("color:#B42318"); nrow = QVBoxLayout(); nrow.addWidget(self.name_edit); nrow.addWidget(self.name_preview); nrow.addWidget(self.collision_label); form.addRow("条目名", nrow); self.title_edit = QLineEdit(); form.addRow("标题", self.title_edit); self.description_edit = QLineEdit(); form.addRow("一句话描述", self.description_edit); self.type_edit = QComboBox(); [self.type_edit.addItem(label, value) for label, value in TYPE_OPTIONS]; form.addRow("类型", self.type_edit); self.tags_edit = QLineEdit(); self.tags_edit.setPlaceholderText("Enter 或中英文逗号确认，最多 12 个"); form.addRow("标签", self.tags_edit); dl.addLayout(form)
        self.created_label = QLabel(""); self.created_label.setObjectName("muted"); self.updated_label = QLabel(""); self.updated_label.setObjectName("muted"); dl.addWidget(self.created_label); dl.addWidget(self.updated_label)
        mode = QHBoxLayout(); self.edit_mode = QPushButton("编辑"); self.preview_mode = QPushButton("预览"); self.edit_mode.clicked.connect(lambda: self.body_stack.setCurrentIndex(0)); self.preview_mode.clicked.connect(self._show_preview); mode.addWidget(QLabel("正文")); mode.addStretch(); mode.addWidget(self.edit_mode); mode.addWidget(self.preview_mode); dl.addLayout(mode)
        self.body_stack = QStackedWidget(); self.body_edit = QPlainTextEdit(); self.body_edit.setFont(QFont("Cascadia Mono", 10)); self.body_edit.setPlaceholderText("正文支持 [[双链]]；显式保存，不自动保存。"); self.preview = MarkdownView(); self.body_stack.addWidget(self.body_edit); self.body_stack.addWidget(self.preview); dl.addWidget(self.body_stack, 1)
        links_row = QHBoxLayout(); links_row.addWidget(QLabel("双链")); self.links_box = links_row; links_row.addStretch(); dl.addLayout(links_row)
        actions = QHBoxLayout(); self.status = QLabel(""); self.status.setObjectName("status"); actions.addWidget(self.status, 1); ai_desc = QPushButton("AI 生成描述"); ai_desc.clicked.connect(self.ai_description); actions.addWidget(ai_desc); self.delete_button = QPushButton("软删除"); self.delete_button.setObjectName("danger"); self.delete_button.clicked.connect(self.delete_current); actions.addWidget(self.delete_button); self.save_button = QPushButton("保存"); self.save_button.setObjectName("primary"); self.save_button.clicked.connect(self.save_current); actions.addWidget(self.save_button); dl.addLayout(actions); splitter.addWidget(detail); splitter.setSizes([350, 760]); root.addWidget(splitter, 1)
        tidy = QHBoxLayout(); tidy_button = QPushButton("归纳整理"); tidy_button.clicked.connect(self.tidy); reports = QPushButton("整理日报"); reports.clicked.connect(self.show_reports); duty = QPushButton("复制值守提示词"); duty.clicked.connect(self.copy_duty); index = QPushButton("查看索引源文件"); index.clicked.connect(self.show_index); tidy.addWidget(tidy_button); tidy.addWidget(reports); tidy.addWidget(duty); tidy.addWidget(index); tidy.addStretch(); root.addLayout(tidy)
        for widget in (self.name_edit, self.title_edit, self.description_edit, self.tags_edit, self.body_edit): widget.textChanged.connect(self._mark_dirty)
        self.name_edit.textChanged.connect(lambda _text: (self.name_preview.setText(self._name_preview(self.name_edit.text())), self._name_timer.start()))
        self.type_edit.currentIndexChanged.connect(self._mark_dirty)
        self._set_editor_enabled(False)

    def _mark_dirty(self, *_):
        if not self._loading: self._dirty = True

    def _set_editor_enabled(self, enabled):
        for widget in (self.name_edit, self.title_edit, self.description_edit, self.type_edit, self.tags_edit, self.body_edit, self.save_button, self.delete_button): widget.setEnabled(enabled)

    def _set_status(self, text): self.status.setText(text); self.statusMessage.emit(text)

    def refresh(self, *_): self._request_id += 1; self._timer.start()

    def _refresh_now(self):
        rid = self._request_id; query = self.search.text().strip(); type_filter = str(self.type_filter.currentData() or ""); sort = str(self.sort.currentData() or "updated")
        self.scope.call("list", self.facade.list_entries, lambda result: self._apply_listing(result) if rid == self._request_id else None, lambda msg: self._set_status(f"读取失败：{msg}"), query=query, type_filter=type_filter, sort=sort)

    def refresh_sync(self):
        self._timer.stop(); result = self.facade.list_entries(query=self.search.text().strip(), type_filter=str(self.type_filter.currentData() or ""), sort=str(self.sort.currentData() or "updated")); self._apply_listing(result); return result

    def _apply_listing(self, result):
        self._items = list(result.get("items") or []); selected = self._current_name; self.entry_list.blockSignals(True); self.entry_list.clear()
        for item in self._items:
            row = QListWidgetItem(); row.setData(Qt.ItemDataRole.UserRole, item.get("name", "")); row.setSizeHint(self.entry_list.sizeHint())
            self.entry_list.addItem(row); box = QWidget(); lay = QHBoxLayout(box); lay.setContentsMargins(4, 6, 4, 6); check = QCheckBox(); check.setProperty("memory_name", item.get("name", "")); lay.addWidget(check); text = QVBoxLayout(); title = QLabel(str(item.get("title") or item.get("name") or "")); title.setStyleSheet("font-weight:600"); desc = QLabel(str(item.get("description") or "")); desc.setObjectName("muted"); badge = QLabel(f"{item.get('type','reference')} · {item.get('source','manual')} · {', '.join(item.get('tags') or [])} · {str(item.get('updated',''))[:10]}"); badge.setStyleSheet(f"color:{TYPE_COLORS.get(item.get('type'), '#0156FC')};font-size:11px"); text.addWidget(title); text.addWidget(desc); text.addWidget(badge); lay.addLayout(text, 1); self.entry_list.setItemWidget(row, box)
        self.entry_list.blockSignals(False); self._apply_stats(result); self._set_status(f"已刷新 {len(self._items)} 条")
        if selected:
            for i in range(self.entry_list.count()):
                if self.entry_list.item(i).data(Qt.ItemDataRole.UserRole) == selected: self.entry_list.setCurrentRow(i); break
        if self.entry_list.currentItem() is None and self.entry_list.count(): self.entry_list.setCurrentRow(0)

    def _apply_stats(self, result):
        stats = result.get("stats") or {"total": len(self._items), "inbox_pending": result.get("inbox_pending", 0), "types": {}}
        types = stats.get("types") or {}
        for key in ("total", "this_week", "inbox_pending"): self.stat_buttons[key].setText(f"{ {'total':'总数','this_week':'本周新增','inbox_pending':'待收编'}[key] } {stats.get(key, 0)}")
        for key in ("user", "project", "reference", "feedback"): self.stat_buttons[key].setText(f"{key} {types.get(key, 0)}")
        pending = int(stats.get("inbox_pending") or result.get("inbox_pending") or 0); self.inbox_button.setText(f"投递箱 · {pending}" if pending else "投递箱")

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

    def _selection_changed(self, current, _previous):
        if not current: return
        if self._dirty and self._current_name and QMessageBox.question(self, "未保存修改", "放弃当前编辑并打开另一条？") != QMessageBox.StandardButton.Yes:
            if _previous is not None:
                self.entry_list.blockSignals(True); self.entry_list.setCurrentItem(_previous); self.entry_list.blockSignals(False)
            return
        self._load_detail(str(current.data(Qt.ItemDataRole.UserRole)))

    def _load_detail(self, name):
        self.scope.call("detail", self.facade.get_entry, self._apply_detail, lambda msg: self._set_status(f"详情读取失败：{msg}"), name)

    def load_detail_sync(self, name): result = self.facade.get_entry(name); self._apply_detail(result); return result

    def _apply_detail(self, entry):
        self._loading = True; self._creating = False; self._dirty = False; self._current_name = str(entry.get("name") or ""); self.detail_title.setText(str(entry.get("title") or self._current_name)); self.name_edit.setText(self._current_name); self.title_edit.setText(str(entry.get("title") or "")); self.description_edit.setText(str(entry.get("description") or "")); self.type_edit.setCurrentIndex(max(0, self.type_edit.findData(entry.get("type", "reference")))); self.tags_edit.setText(", ".join(entry.get("tags") or [])); self.body_edit.setPlainText(str(entry.get("body") or "")); self.preview.setMarkdown(str(entry.get("body") or "")); self.created_label.setText(f"创建：{entry.get('created') or '未知'}"); self.updated_label.setText(f"更新：{entry.get('updated') or '未知'}"); self._set_links(entry.get("links") or []); self.name_preview.setText(self._name_preview(self._current_name)); self._loading = False; self._set_editor_enabled(True); self._set_status("已加载")

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
            self.collision_label.clear()
            return
        self.scope.call("collision", self.facade.get_entry,
                        lambda _entry: self.collision_label.setText("已有同名条目；请换一个名称，或打开已有条目。"),
                        lambda _message: self.collision_label.clear(), candidate)

    def new_entry(self):
        self._creating = True; self._current_name = ""; self._dirty = False; self.detail_title.setText("新建记忆"); self._loading = True
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
            self._set_status("AI 草稿已填入空位，请确认后保存")
        self.scope.call("ai", self.facade.ai_draft, done, lambda msg: self._set_status(f"AI 草稿失败：{msg}"), body)

    def copy_prompt(self):
        from PySide6.QtWidgets import QApplication
        try: QApplication.clipboard().setText(self.facade.injection_prompt()); self.promptCopied.emit(); self._set_status("注入提示词已复制")
        except Exception as exc: self._set_status(f"复制失败：{exc}")

    def batch_update_type(self, _index):
        names = self._selected_names(); value = self.batch_type.currentData();
        if names and value: self._batch(self.facade.bulk_update, names, type_name=value)
        self.batch_type.setCurrentIndex(0)

    def batch_update_tags(self):
        names = self._selected_names(); tags = [x.strip() for x in self.batch_tags.text().replace("，", ",").split(",") if x.strip()]
        if names: self._batch(self.facade.bulk_update, names, tags=tags)

    def batch_delete(self):
        names = self._selected_names();
        if names and QMessageBox.question(self, "批量软删除", f"确认删除 {len(names)} 条？") == QMessageBox.StandardButton.Yes: self._batch(self.facade.bulk_delete, names)

    def batch_ai(self):
        for name in self._selected_names():
            try:
                entry = self.facade.get_entry(name)
                if not entry.get("title") or not entry.get("description"):
                    draft = self.facade.ai_draft(entry.get("body", "")); self.facade.update_entry(name, {k: v for k, v in draft.items() if not entry.get(k)})
            except Exception as exc: self._set_status(f"批量 AI 首个失败：{exc}"); break
        self.refresh()

    def _batch(self, fn, *args, **kwargs):
        try:
            result = fn(*args, **kwargs); self.refresh_sync(); done = result.get("updated", result.get("deleted", [])); failed = result.get("failed", result.get("errors", [])); self._set_status(f"已 {len(done) if isinstance(done, list) else done} 条，失败 {len(failed)} 条")
        except Exception as exc: self._set_status(f"批量操作失败：{exc}")

    def open_inbox(self):
        try: result = self.facade.list_inbox()
        except Exception as exc: self._set_status(f"投递箱读取失败：{exc}"); return
        items = list(result.get("items") or []); dialog = QDialog(self); dialog.setWindowTitle(f"投递箱（{len(items)}）"); dialog.resize(1060, 650); root = QVBoxLayout(dialog); splitter = QSplitter(Qt.Orientation.Horizontal); left = QListWidget(); right = QFrame(); rl = QVBoxLayout(right); raw = QPlainTextEdit(); raw.setReadOnly(True); raw.setFont(QFont("Cascadia Mono", 9)); warning = QLabel(""); warning.setStyleSheet("color:#B42318;background:#FFF1F0;padding:8px"); rl.addWidget(warning); rl.addWidget(QLabel("投递原文（只读）")); rl.addWidget(raw, 1); form = QFormLayout(); title = QLineEdit(); name = QLineEdit(); typ = QComboBox(); [typ.addItem(label, value) for label, value in TYPE_OPTIONS]; tags = QLineEdit(); desc = QLineEdit(); form.addRow("标题", title); form.addRow("条目名", name); form.addRow("类型", typ); form.addRow("标签", tags); form.addRow("描述", desc); rl.addLayout(form); ai = QPushButton("AI 补全标题与描述"); rl.addWidget(ai); splitter.addWidget(left); splitter.addWidget(right); splitter.setSizes([350, 700]); root.addWidget(splitter, 1); buttons = QDialogButtonBox(); admit = buttons.addButton("收编入库", QDialogButtonBox.ButtonRole.AcceptRole); discard = buttons.addButton("丢弃选中", QDialogButtonBox.ButtonRole.DestructiveRole); all_discard = buttons.addButton("全部丢弃", QDialogButtonBox.ButtonRole.DestructiveRole); close = buttons.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole); root.addWidget(buttons)
        for item in items:
            row = QListWidgetItem(f"{item.get('title') or item.get('suggested_name') or item.get('file')}\n{item.get('file')}"); row.setData(Qt.ItemDataRole.UserRole, item); left.addItem(row)
        def selected():
            value = left.currentItem().data(Qt.ItemDataRole.UserRole) if left.currentItem() else None; return value if isinstance(value, dict) else None
        def fill(item):
            value = item.data(Qt.ItemDataRole.UserRole) if item else {}; raw.setPlainText(str(value.get("raw_text") or value.get("body") or "")); warning.setText("检测到疑似提示词注入内容，请仔细审阅" if value.get("injection_hits") else ""); title.setText(str(value.get("title") or value.get("suggested_name") or "")); name.setText(str(value.get("suggested_name") or "")); desc.setText(str(value.get("description") or "")); typ.setCurrentIndex(max(0, typ.findData(value.get("type", "reference")))); tags.setText(", ".join(value.get("tags") or []))
        left.currentItemChanged.connect(fill)
        def admit_one():
            value = selected();
            if not value: return
            try: self.facade.admit_inbox(str(value.get("file")), {"title": title.text().strip(), "name": name.text().strip(), "type": typ.currentData(), "tags": [x.strip() for x in tags.text().split(",") if x.strip()], "description": desc.text().strip()}); left.takeItem(left.currentRow()); self.refresh_sync(); self._set_status("已收编")
            except Exception as exc: self._set_status(f"收编失败：{exc}")
        def discard_one():
            value = selected();
            if not value: return
            try: self.facade.discard_inbox(str(value.get("file"))); left.takeItem(left.currentRow()); self.refresh_sync(); self._set_status("已丢弃")
            except Exception as exc: self._set_status(f"丢弃失败：{exc}")
        def discard_all():
            if QMessageBox.question(dialog, "全部丢弃", "将全部投递移入回收区？") == QMessageBox.StandardButton.Yes: self.facade.discard_all_inbox(); left.clear(); self.refresh_sync()
        def ai_fill():
            try: draft = self.facade.ai_draft(raw.toPlainText()); title.setText(title.text() or draft.get("title", "")); desc.setText(desc.text() or draft.get("description", ""))
            except Exception as exc: warning.setText(f"AI 补全失败：{exc}")
        admit.clicked.connect(admit_one); discard.clicked.connect(discard_one); all_discard.clicked.connect(discard_all); ai.clicked.connect(ai_fill); close.clicked.connect(dialog.reject)
        if items: left.setCurrentRow(0)
        dialog.exec()

    def tidy(self):
        if self.jobs: self.jobs.submit("tidy", "归纳整理", lambda: self.facade.tidy_run(use_ai=True))
        else: self._set_status(str(self.facade.tidy_run(use_ai=True)))

    def show_reports(self):
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
        dialog.exec()

    def copy_duty(self):
        from PySide6.QtWidgets import QApplication
        try: QApplication.clipboard().setText(self.facade.duty_prompt()); self._set_status("值守提示词已复制")
        except Exception as exc: self._set_status(str(exc))

    def show_index(self):
        try: data = self.facade.index_file(); dialog = QDialog(self); dialog.setWindowTitle("MEMORY.md（只读索引源文件）"); dialog.resize(900, 650); layout = QVBoxLayout(dialog); note = QLabel(str(data.get("note") or "索引由程序维护，手动修改会被覆盖。")); note.setObjectName("muted"); layout.addWidget(note); view = QPlainTextEdit(); view.setReadOnly(True); view.setFont(QFont("Cascadia Mono", 9)); view.setPlainText(str(data.get("content") or "")); layout.addWidget(view); dialog.exec()
        except Exception as exc: self._set_status(str(exc))
