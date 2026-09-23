"""Memory library page for the v1.4.0 native shell."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..memory_facade import MemoryFacade
from ..task_runner import TaskRunner


TYPE_OPTIONS = [("用户", "user"), ("项目", "project"), ("参考", "reference"), ("反馈", "feedback")]


class MemoryPage(QWidget):
    openGraphRequested = Signal()
    statusMessage = Signal(str)
    promptCopied = Signal()

    def __init__(self, facade: MemoryFacade, runner: TaskRunner, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.facade = facade
        self.runner = runner
        self._request_id = 0
        self._detail_request_id = 0
        self._current_name = ""
        self._creating = False
        self._items: list[dict[str, Any]] = []
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)
        self._refresh_timer.timeout.connect(self._refresh_now)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 24)
        root.setSpacing(16)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        eyebrow = QLabel("SHARED MEMORY")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("记忆库")
        title.setObjectName("title")
        subtitle = QLabel("把值得复用的事实留在本地仓库，条目文件是事实源。")
        subtitle.setObjectName("muted")
        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box)
        heading.addStretch(1)
        self.stats_label = QLabel("0 条记忆")
        self.stats_label.setObjectName("muted")
        heading.addWidget(self.stats_label, alignment=Qt.AlignmentFlag.AlignBottom)
        root.addLayout(heading)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索标题、描述、标签或正文")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search, 1)
        self.type_filter = QComboBox()
        self.type_filter.addItem("全部类型", "")
        for label, value in TYPE_OPTIONS:
            self.type_filter.addItem(label, value)
        self.type_filter.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self.type_filter)
        self.inbox_button = QPushButton("投递箱")
        self.inbox_button.clicked.connect(self.open_inbox)
        toolbar.addWidget(self.inbox_button)
        self.copy_button = QPushButton("复制注入提示词")
        self.copy_button.setObjectName("primary")
        self.copy_button.clicked.connect(self.copy_prompt)
        toolbar.addWidget(self.copy_button)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.entry_list = QListWidget()
        self.entry_list.setMinimumWidth(290)
        self.entry_list.currentItemChanged.connect(self._list_selection_changed)
        splitter.addWidget(self.entry_list)

        detail = QFrame()
        detail.setObjectName("surface")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(20, 18, 20, 18)
        detail_layout.setSpacing(12)
        detail_heading = QHBoxLayout()
        self.detail_title = QLabel("选择一条记忆")
        self.detail_title.setStyleSheet("font-size: 20px; font-weight: 650;")
        detail_heading.addWidget(self.detail_title)
        detail_heading.addStretch(1)
        self.new_button = QPushButton("新建")
        self.new_button.clicked.connect(self.new_entry)
        detail_heading.addWidget(self.new_button)
        detail_layout.addLayout(detail_heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("英文 kebab-case，可留空自动生成")
        self.title_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.type_edit = QComboBox()
        for label, value in TYPE_OPTIONS:
            self.type_edit.addItem(label, value)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("标签用逗号分隔")
        form.addRow("条目名", self.name_edit)
        form.addRow("标题", self.title_edit)
        form.addRow("描述", self.description_edit)
        form.addRow("类型", self.type_edit)
        form.addRow("标签", self.tags_edit)
        detail_layout.addLayout(form)

        body_label = QLabel("正文")
        body_label.setObjectName("muted")
        detail_layout.addWidget(body_label)
        self.body_edit = QPlainTextEdit()
        self.body_edit.setFont(QFont("Cascadia Mono", 10))
        self.body_edit.setPlaceholderText("正文支持 [[双链]]，保存后由核心服务维护 frontmatter 和索引。")
        detail_layout.addWidget(self.body_edit, 1)

        self.links_label = QLabel("")
        self.links_label.setObjectName("muted")
        self.links_label.setWordWrap(True)
        detail_layout.addWidget(self.links_label)
        actions = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("status")
        actions.addWidget(self.status, 1)
        self.delete_button = QPushButton("软删除")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self.delete_current)
        actions.addWidget(self.delete_button)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_current)
        actions.addWidget(self.save_button)
        detail_layout.addLayout(actions)
        splitter.addWidget(detail)
        splitter.setSizes([310, 720])
        root.addWidget(splitter, 1)
        self._set_editor_enabled(False)

    def _set_editor_enabled(self, enabled: bool) -> None:
        for widget in (self.name_edit, self.title_edit, self.description_edit, self.type_edit, self.tags_edit, self.body_edit, self.save_button, self.delete_button):
            widget.setEnabled(enabled)

    def _set_status(self, message: str) -> None:
        self.status.setText(message)
        self.statusMessage.emit(message)

    def refresh(self, *_args: object) -> None:
        self._refresh_timer.start()

    def _refresh_now(self) -> None:
        self._request_id += 1
        request_id = self._request_id
        query = self.search.text().strip()
        type_filter = str(self.type_filter.currentData() or "")
        handle = self.runner.submit(self.facade.list_entries, query=query, type_filter=type_filter)

        def done(identifier: int, payload: object) -> None:
            if identifier != handle.request_id or request_id != self._request_id:
                return
            self._apply_listing(payload if isinstance(payload, dict) else {})

        def failed(identifier: int, payload: object) -> None:
            if identifier != handle.request_id or request_id != self._request_id:
                return
            message = str(payload.get("error") if isinstance(payload, dict) else payload)
            self._set_status(f"读取失败：{message}")

        handle.signals.finished.connect(done)
        handle.signals.failed.connect(failed)

    def refresh_sync(self) -> dict[str, Any]:
        self._refresh_timer.stop()
        result = self.facade.list_entries(query=self.search.text().strip(), type_filter=str(self.type_filter.currentData() or ""))
        self._apply_listing(result)
        return result

    def _apply_listing(self, result: dict[str, Any]) -> None:
        self._items = list(result.get("items") or [])
        selected = self._current_name
        self.entry_list.blockSignals(True)
        self.entry_list.clear()
        for item in self._items:
            title = str(item.get("title") or item.get("name") or "")
            description = str(item.get("description") or "").strip()
            suffix = f"\n{description}" if description else ""
            row = QListWidgetItem(f"{title}\n{item.get('name', '')}{suffix}")
            row.setData(Qt.ItemDataRole.UserRole, item.get("name", ""))
            self.entry_list.addItem(row)
        self.entry_list.blockSignals(False)
        self.stats_label.setText(f"{len(self._items)} 条记忆")
        pending = int(result.get("inbox_pending") or 0)
        self.inbox_button.setText(f"投递箱 · {pending}" if pending else "投递箱")
        self._set_status("已刷新")
        if selected:
            for index in range(self.entry_list.count()):
                if self.entry_list.item(index).data(Qt.ItemDataRole.UserRole) == selected:
                    self.entry_list.setCurrentRow(index)
                    break
        if self.entry_list.currentItem() is None and self.entry_list.count():
            self.entry_list.setCurrentRow(0)

    def _list_selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        name = str(current.data(Qt.ItemDataRole.UserRole) or "")
        self._load_detail(name)

    def _load_detail(self, name: str) -> None:
        self._detail_request_id += 1
        request_id = self._detail_request_id
        handle = self.runner.submit(self.facade.get_entry, name)

        def done(identifier: int, payload: object) -> None:
            if identifier != handle.request_id or request_id != self._detail_request_id or not isinstance(payload, dict):
                return
            self._apply_detail(payload)

        def failed(identifier: int, payload: object) -> None:
            if identifier != handle.request_id or request_id != self._detail_request_id:
                return
            self._set_status(f"详情读取失败：{payload.get('error') if isinstance(payload, dict) else payload}")

        handle.signals.finished.connect(done)
        handle.signals.failed.connect(failed)

    def load_detail_sync(self, name: str) -> dict[str, Any]:
        result = self.facade.get_entry(name)
        self._apply_detail(result)
        return result

    def _apply_detail(self, entry: dict[str, Any]) -> None:
        self._creating = False
        self._current_name = str(entry.get("name") or "")
        self.detail_title.setText(str(entry.get("title") or self._current_name))
        self.name_edit.setText(self._current_name)
        self.title_edit.setText(str(entry.get("title") or ""))
        self.description_edit.setText(str(entry.get("description") or ""))
        index = max(0, self.type_edit.findData(entry.get("type", "reference")))
        self.type_edit.setCurrentIndex(index)
        self.tags_edit.setText(", ".join(str(tag) for tag in entry.get("tags") or []))
        self.body_edit.setPlainText(str(entry.get("body") or ""))
        links = [f"{link.get('name')} {'(存在)' if link.get('exists') else '(未找到)'}" for link in entry.get("links") or []]
        self.links_label.setText("双链：" + ("、".join(links) if links else "无"))
        self._set_editor_enabled(True)
        self._set_status("已加载")

    def new_entry(self) -> None:
        self._creating = True
        self._current_name = ""
        self.detail_title.setText("新建记忆")
        for field in (self.name_edit, self.title_edit, self.description_edit, self.tags_edit):
            field.clear()
        self.type_edit.setCurrentIndex(self.type_edit.findData("reference"))
        self.body_edit.clear()
        self.links_label.clear()
        self._set_editor_enabled(True)
        self.title_edit.setFocus()
        self._set_status("填写后保存")

    def _payload(self) -> dict[str, Any]:
        return {
            "name": self.name_edit.text().strip(),
            "title": self.title_edit.text().strip(),
            "description": self.description_edit.text().strip(),
            "type": self.type_edit.currentData() or "reference",
            "tags": [tag.strip() for tag in self.tags_edit.text().split(",") if tag.strip()],
            "body": self.body_edit.toPlainText(),
        }

    def save_current(self) -> None:
        if not self.title_edit.text().strip():
            self._set_status("请先填写标题")
            self.title_edit.setFocus()
            return
        payload = self._payload()
        old_name = self._current_name
        self._set_status("保存中…")
        fn = self.facade.create_entry if self._creating else self.facade.update_entry
        args = (payload,) if self._creating else (old_name, payload)
        handle = self.runner.submit(fn, *args)

        def done(_identifier: int, result: object) -> None:
            if not isinstance(result, dict):
                return
            self._apply_detail(result)
            self.refresh()
            self._set_status("已保存")

        def failed(_identifier: int, payload_obj: object) -> None:
            message = str(payload_obj.get("error") if isinstance(payload_obj, dict) else payload_obj)
            self._set_status(f"保存失败：{message}")

        handle.signals.finished.connect(done)
        handle.signals.failed.connect(failed)

    def save_current_sync(self) -> dict[str, Any]:
        payload = self._payload()
        result = self.facade.create_entry(payload) if self._creating else self.facade.update_entry(self._current_name, payload)
        self._apply_detail(result)
        self.refresh_sync()
        return result

    def delete_current(self) -> None:
        if not self._current_name:
            return
        answer = QMessageBox.question(self, "确认软删除", f"将「{self.detail_title.text()}」移入 memory-trash？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._delete_current_async()

    def _delete_current_async(self) -> None:
        name = self._current_name
        self._set_status("软删除中…")
        handle = self.runner.submit(self.facade.delete_entry, name)

        def done(_identifier: int, _result: object) -> None:
            self._current_name = ""
            self._creating = False
            self._set_editor_enabled(False)
            self.refresh()
            self._set_status("已移入 memory-trash")

        def failed(_identifier: int, payload: object) -> None:
            self._set_status(f"删除失败：{payload.get('error') if isinstance(payload, dict) else payload}")

        handle.signals.finished.connect(done)
        handle.signals.failed.connect(failed)

    def delete_current_sync(self, name: str | None = None) -> dict[str, Any]:
        target = name or self._current_name
        result = self.facade.delete_entry(target)
        self._current_name = ""
        self._set_editor_enabled(False)
        self.refresh_sync()
        return result

    def copy_prompt(self) -> None:
        try:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self.facade.injection_prompt())
            self.promptCopied.emit()
            self._set_status("注入提示词已复制")
        except Exception as exc:
            self._set_status(f"复制失败：{exc}")

    def open_inbox(self) -> None:
        try:
            result = self.facade.list_inbox()
        except Exception as exc:
            self._set_status(f"投递箱读取失败：{exc}")
            return
        items = list(result.get("items") or [])
        dialog = QDialog(self)
        dialog.setWindowTitle(f"投递箱（{len(items)}）")
        dialog.resize(820, 560)
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        for item in items:
            row = QListWidgetItem(f"{item.get('title') or item.get('suggested_name')}\n{item.get('file', '')}")
            row.setData(Qt.ItemDataRole.UserRole, item)
            list_widget.addItem(row)
        layout.addWidget(list_widget, 1)
        editor = QLineEdit()
        editor.setPlaceholderText("收编标题（选择条目后可修改）")
        layout.addWidget(editor)
        buttons = QDialogButtonBox()
        admit = buttons.addButton("收编选中", QDialogButtonBox.ButtonRole.AcceptRole)
        discard = buttons.addButton("丢弃选中", QDialogButtonBox.ButtonRole.DestructiveRole)
        close = buttons.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)
        def selected() -> dict[str, Any] | None:
            item = list_widget.currentItem()
            value = item.data(Qt.ItemDataRole.UserRole) if item else None
            return value if isinstance(value, dict) else None
        def fill(item: QListWidgetItem | None) -> None:
            if item:
                value = item.data(Qt.ItemDataRole.UserRole) or {}
                editor.setText(str(value.get("title") or value.get("suggested_name") or ""))
        list_widget.currentItemChanged.connect(fill)
        def admit_one() -> None:
            value = selected()
            if not value:
                return
            try:
                self.facade.admit_inbox(str(value.get("file")), {"title": editor.text().strip()})
                list_widget.takeItem(list_widget.currentRow())
                self.refresh_sync()
                self._set_status("已收编")
            except Exception as exc:
                self._set_status(f"收编失败：{exc}")
        def discard_one() -> None:
            value = selected()
            if not value:
                return
            try:
                self.facade.discard_inbox(str(value.get("file")))
                list_widget.takeItem(list_widget.currentRow())
                self.refresh_sync()
                self._set_status("已丢弃")
            except Exception as exc:
                self._set_status(f"丢弃失败：{exc}")
        admit.clicked.connect(admit_one)
        discard.clicked.connect(discard_one)
        close.clicked.connect(dialog.reject)
        dialog.exec()
