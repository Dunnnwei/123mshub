"""Native skill and safety pages wired to the existing repository services."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget, QCheckBox, QHeaderView, QTextBrowser, QGroupBox, QFileDialog,
)

from ..memory_facade import MemoryFacade
from ..task_runner import TaskRunner, RequestScope
from ..job_controller import JobController


def _error(payload: object) -> str:
    return str(payload.get("error") if isinstance(payload, dict) else payload)


class _SkillTable(QTableWidget):
    def selected_names(self) -> list[tuple[str, str]]:
        out = []
        for row in range(self.rowCount()):
            check = self.cellWidget(row, 0)
            if isinstance(check, QCheckBox) and check.isChecked():
                out.append((str(self.item(row, 1).data(Qt.ItemDataRole.UserRole)), str(self.item(row, 1).data(Qt.ItemDataRole.UserRole + 1) or "")))
        return out


class SkillsPage(QWidget):
    def __init__(self, facade: MemoryFacade, runner: TaskRunner, jobs: JobController, parent=None):
        super().__init__(parent)
        self.facade, self.runner, self.jobs = facade, runner, jobs
        self.scope = RequestScope(runner, self)
        self.items: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(30, 26, 30, 24); root.setSpacing(12)
        head = QHBoxLayout(); labels = QVBoxLayout()
        eyebrow = QLabel("SKILL LIBRARY"); eyebrow.setObjectName("eyebrow")
        title = QLabel("技能库"); title.setObjectName("title")
        sub = QLabel("复用已有仓库能力；业务安装、更新、安全与对账沿用现有服务层。"); sub.setObjectName("muted")
        labels.addWidget(eyebrow); labels.addWidget(title); labels.addWidget(sub); head.addLayout(labels); head.addStretch()
        inject = QPushButton("复制注入提示词"); inject.setObjectName("primary"); inject.clicked.connect(self.copy_prompt); head.addWidget(inject)
        add = QPushButton("添加技能 / 程序"); add.clicked.connect(self.open_add); head.addWidget(add)
        root.addLayout(head)
        filters = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("搜索名称、中文备注、来源地址或标签"); self.search.textChanged.connect(self._debounced)
        filters.addWidget(self.search, 1)
        self.provider = QComboBox(); self.provider.addItem("全部来源", ""); self.provider.addItem("GitHub 源", "github"); self.provider.addItem("本地自研", "local"); self.provider.currentIndexChanged.connect(self.refresh); filters.addWidget(self.provider)
        self.category = QComboBox(); self.category.addItem("全部资产", ""); self.category.addItem("技能", "skill"); self.category.addItem("程序", "project"); self.category.currentIndexChanged.connect(self.refresh); filters.addWidget(self.category)
        refresh = QPushButton("刷新"); refresh.clicked.connect(self.refresh); filters.addWidget(refresh)
        root.addLayout(filters)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = _SkillTable(0, 7); self.table.setHorizontalHeaderLabels(["选", "名称", "来源", "中文备注", "安全", "标签", "更新时间"]); self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.itemSelectionChanged.connect(self._selection_changed); splitter.addWidget(self.table)
        detail = QGroupBox("技能详情"); detail_layout = QVBoxLayout(detail)
        self.detail_title = QLabel("选择一项"); self.detail_title.setStyleSheet("font-size:18px;font-weight:650")
        self.detail_text = QTextBrowser(); self.detail_text.setOpenExternalLinks(False); self.detail_text.setFont(QFont("Cascadia Mono", 9))
        detail_layout.addWidget(self.detail_title); detail_layout.addWidget(self.detail_text, 1)
        action = QHBoxLayout()
        self.check_button = QPushButton("离线检查"); self.check_button.clicked.connect(lambda: self.scan("offline")); action.addWidget(self.check_button)
        self.ai_check_button = QPushButton("AI 检查"); self.ai_check_button.clicked.connect(lambda: self.scan("ai")); action.addWidget(self.ai_check_button)
        self.trust_button = QPushButton("信任放行"); self.trust_button.clicked.connect(self.trust); action.addWidget(self.trust_button)
        self.update_button = QPushButton("更新"); self.update_button.clicked.connect(self.update); action.addWidget(self.update_button)
        self.delete_button = QPushButton("软删除"); self.delete_button.setObjectName("danger"); self.delete_button.clicked.connect(self.delete); action.addWidget(self.delete_button)
        self.edit_button = QPushButton("编辑信息"); self.edit_button.clicked.connect(self.edit_metadata); action.addWidget(self.edit_button)
        detail_layout.addLayout(action)
        prompt = QHBoxLayout(); self.prompt_button = QPushButton("复制指定技能提示词"); self.prompt_button.clicked.connect(self.copy_skill_prompt); prompt.addWidget(self.prompt_button); self.install_prompt_button = QPushButton("复制安装提示词"); self.install_prompt_button.clicked.connect(self.copy_install_prompt); prompt.addWidget(self.install_prompt_button); detail_layout.addLayout(prompt)
        splitter.addWidget(detail); splitter.setSizes([720, 420]); root.addWidget(splitter, 1)
        batch = QHBoxLayout(); batch.addWidget(QLabel("已勾选条目：")); self.batch_check = QPushButton("批量离线检查"); self.batch_check.clicked.connect(lambda: self.batch_scan("offline")); batch.addWidget(self.batch_check); self.batch_ai_check = QPushButton("批量 AI 检查"); self.batch_ai_check.clicked.connect(lambda: self.batch_scan("ai")); batch.addWidget(self.batch_ai_check); self.batch_update = QPushButton("批量更新 GitHub"); self.batch_update.clicked.connect(self.batch_update_github); batch.addWidget(self.batch_update); self.batch_trust = QPushButton("批量信任"); self.batch_trust.clicked.connect(self.batch_trust_items); batch.addWidget(self.batch_trust); self.batch_translate = QPushButton("批量中文翻译"); self.batch_translate.clicked.connect(self.batch_translate_items); batch.addWidget(self.batch_translate); batch.addStretch(); root.addLayout(batch)
        self.status = QLabel(""); self.status.setObjectName("status"); root.addWidget(self.status)
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(300); self._timer.timeout.connect(self._refresh_now)

    def _debounced(self): self._timer.start()

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    def _set_status(self, text): self.status.setText(text)

    def refresh(self, *_): self._timer.start()

    def _refresh_now(self):
        query = self.search.text().strip().casefold(); provider = self.provider.currentData() or ""; category = self.category.currentData() or ""
        def done(data):
            rows = list(data.get("items") or {}) if isinstance(data, dict) else []
            self.items = [row for row in rows if (not provider or row.get("provider") == provider) and (not category or row.get("item_type") == category) and (not query or query in str(row).casefold())]
            self._apply_rows()
        self.scope.call("list", self.facade.skills, done, lambda msg: self._set_status(f"技能列表读取失败：{msg}"))

    def _apply_rows(self):
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            check = QCheckBox(); self.table.setCellWidget(row, 0, check)
            name = QTableWidgetItem(str(item.get("name") or "")); name.setData(Qt.ItemDataRole.UserRole, item.get("name", "")); name.setData(Qt.ItemDataRole.UserRole + 1, item.get("library", "")); self.table.setItem(row, 1, name)
            provider = item.get("provider") or "github"; source = "GitHub 源" if provider == "github" else "本地自研"
            source_item = QTableWidgetItem(source); source_item.setToolTip("本地自研技能无在线源头，版本请在编辑信息中手动维护。" if provider == "local" else "可检查版本、更新")
            self.table.setItem(row, 2, source_item)
            self.table.setItem(row, 3, QTableWidgetItem(str(item.get("description_zh") or item.get("description") or "")))
            self.table.setItem(row, 4, QTableWidgetItem(str(item.get("security_status") or "unchecked")))
            self.table.setItem(row, 5, QTableWidgetItem(", ".join(item.get("tags") or [])))
            self.table.setItem(row, 6, QTableWidgetItem(str(item.get("updated_at") or "")[:19].replace("T", " ")))
        self._set_status(f"已加载 {len(self.items)} 项")
        if self.items: self.table.selectRow(0)

    def _selection_changed(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows: self.current = None; return
        item = self.items[rows[0].row()]; self.current = item; self.detail_title.setText(str(item.get("name") or ""))
        self.detail_text.setPlainText(self._format_detail(item))
        local = item.get("provider") == "local"
        self.update_button.setEnabled(not local); self.trust_button.setEnabled(True); self.check_button.setEnabled(True); self.ai_check_button.setEnabled(True)

    @staticmethod
    def _format_detail(item):
        lines = [f"来源: {item.get('source_url') or '本地自研'}", f"目录: {item.get('local_dir') or ''}", f"库: {item.get('library') or ''}", f"版本: {item.get('version') or '未知'}", f"安全: {item.get('security_status') or 'unchecked'}", "", str(item.get('description_zh') or item.get('description') or "")]
        return "\n".join(lines)

    def _selected(self):
        return self.current or {}

    def scan(self, route):
        item = self._selected();
        if not item: return
        self._set_status("安全检查任务已提交…")
        self.jobs.submit("scan", f"安全检查 {item.get('name')}", lambda report: self.facade.skill_scan(item["name"], item.get("library", ""), route=route, progress=report), progress=True)

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

    def edit_metadata(self):
        item = self._selected()
        if item:
            MetadataDialog(self, item).exec()

    def _checked(self):
        return self.table.selected_names()

    def batch_scan(self, route):
        selected = self._checked()
        for name, library in selected:
            self.jobs.submit("scan", f"安全检查 {name}", lambda report, name=name, library=library: self.facade.skill_scan(name, library, route=route, progress=report), progress=True)
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
        if names: self.jobs.submit("translate", f"中文翻译（{len(names)} 项）", lambda report: self.facade.skill_translate_batch(names, progress=report), progress=True)

    def copy_prompt(self):
        from PySide6.QtWidgets import QApplication
        try: QApplication.clipboard().setText(self.facade.library_prompt()); self._set_status("注入提示词已复制")
        except Exception as exc: self._set_status(str(exc))

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
        super().__init__(page); self.page, self.item = page, item; self.setWindowTitle("编辑技能信息"); self.resize(700, 500)
        root = QVBoxLayout(self); form = QFormLayout()
        self.name = QLineEdit(str(item.get("name") or "")); form.addRow("条目身份", self.name)
        self.directory = QLineEdit(Path(str(item.get("local_dir") or "")).name); self.directory.textChanged.connect(self._directory_hint); form.addRow("目录名", self.directory)
        self.provider = QComboBox(); self.provider.addItem("GitHub", "github"); self.provider.addItem("本地自研", "local"); self.provider.setCurrentIndex(max(0, self.provider.findData(item.get("provider", "github")))); form.addRow("来源", self.provider)
        self.source = QLineEdit(str(item.get("source_url") or "")); self.source.textChanged.connect(self._source_hint); form.addRow("来源地址", self.source)
        self.source_hint = QLabel(""); self.source_hint.setObjectName("muted"); form.addRow("解析预览", self.source_hint)
        self.library = QComboBox(); self.library.addItem("共享技能库", "skills"); self.library.addItem("程序库", "github"); self.library.setCurrentIndex(max(0, self.library.findData(item.get("library", "skills")))); form.addRow("所属库", self.library)
        self.version = QLineEdit(str(item.get("version") or "")); form.addRow("版本", self.version); self.description = QLineEdit(str(item.get("description") or "")); form.addRow("说明", self.description); self.description_zh = QLineEdit(str(item.get("description_zh") or "")); form.addRow("中文备注", self.description_zh); root.addLayout(form); note = QLabel("改名只改变身份；目录字段才决定仓库归属。目录不能包含 /、\\ 或以点开头。"); note.setObjectName("muted"); root.addWidget(note); buttons = QDialogButtonBox(); save = buttons.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole); close = buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole); root.addWidget(buttons); save.clicked.connect(self.save); close.clicked.connect(self.reject); self._directory_hint(); self._source_hint()

    def _directory_hint(self):
        value = self.directory.text().strip(); self.directory.setStyleSheet("color:#B42318" if "/" in value or "\\" in value or value.startswith(".") else "")

    def _source_hint(self):
        value = self.source.text().strip()
        if not value: self.source_hint.setText("本地自研不需要远程来源"); return
        try:
            from ...urltool import parse_source
            parsed = parse_source(value); self.source_hint.setText(f"作者 {parsed.owner} · 仓库 {parsed.repo} · 分支 {parsed.ref or 'HEAD'} · 子目录 {parsed.subdir or '根目录'}")
        except Exception as exc: self.source_hint.setText(f"地址待修正：{exc}")

    def save(self):
        updates = {"name": self.name.text().strip(), "dir_name": self.directory.text().strip(), "provider": self.provider.currentData(), "source_url": self.source.text().strip(), "target_library": self.library.currentData(), "version": self.version.text().strip(), "description": self.description.text().strip(), "description_zh": self.description_zh.text().strip()}
        self.page.jobs.submit("metadata", f"保存技能信息 {self.item['name']}", lambda: self.page.facade.skill_update_metadata(self.item["name"], updates, self.item.get("library", "")))
        self.accept()


class AddSkillDialog(QDialog):
    def __init__(self, page: SkillsPage):
        super().__init__(page); self.page = page; self.setWindowTitle("添加技能 / 程序"); self.resize(780, 560)
        root = QVBoxLayout(self); form = QFormLayout()
        self.source = QLineEdit(); self.source.setPlaceholderText("GitHub URL、owner/repo 或本地目录"); source_row = QHBoxLayout(); source_row.addWidget(self.source, 1); browse = QPushButton("选择本地目录…"); browse.clicked.connect(self.browse_local); source_row.addWidget(browse); form.addRow("来源", source_row)
        self.item_type = QComboBox(); self.item_type.addItem("技能", "skill"); self.item_type.addItem("程序", "project"); form.addRow("类型", self.item_type)
        self.mode = QComboBox(); self.mode.addItem("标准（按说明文件）", "standard"); self.mode.addItem("全仓（完整 Git）", "full"); form.addRow("安装模式", self.mode)
        self.fetcher = QComboBox(); self.fetcher.addItem("archive", "archive"); self.fetcher.addItem("git", "git"); form.addRow("抓取方式", self.fetcher)
        root.addLayout(form); self.preview = QTextBrowser(); root.addWidget(self.preview, 1)
        actions = QDialogButtonBox(); preview = actions.addButton("扫描预览", QDialogButtonBox.ButtonRole.ActionRole); install = actions.addButton("后台入库", QDialogButtonBox.ButtonRole.AcceptRole); close = actions.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole); root.addWidget(actions)
        preview.clicked.connect(self.do_preview); install.clicked.connect(self.do_install); close.clicked.connect(self.reject)

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


class SecurityPage(QWidget):
    def __init__(self, facade, runner, jobs, parent=None):
        super().__init__(parent); self.facade, self.runner, self.jobs = facade, runner, jobs; self.scope = RequestScope(runner, self); self.items = []; self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(30, 26, 30, 24); root.setSpacing(14)
        eyebrow = QLabel("SAFETY CENTER"); eyebrow.setObjectName("eyebrow"); title = QLabel("安全中心"); title.setObjectName("title"); note = QLabel("待确认条目可路线 A 离线检查、路线 B AI 检查，人工信任会保留记录。"); note.setObjectName("muted"); root.addWidget(eyebrow); root.addWidget(title); root.addWidget(note)
        bar = QHBoxLayout(); self.route = QComboBox(); self.route.addItem("路线 A · 离线", "offline"); self.route.addItem("路线 B · AI", "ai"); bar.addWidget(self.route); self.batch = QPushButton("批量检查待确认"); self.batch.clicked.connect(self.batch_scan); bar.addWidget(self.batch); refresh = QPushButton("刷新"); refresh.clicked.connect(self.refresh); bar.addWidget(refresh); bar.addStretch(); root.addLayout(bar)
        self.table = QTableWidget(0, 5); self.table.setHorizontalHeaderLabels(["名称", "来源", "状态", "最近检查", "摘要"]); self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch); self.table.itemSelectionChanged.connect(self._show_report); root.addWidget(self.table, 1); self.report = QPlainTextEdit(); self.report.setReadOnly(True); self.report.setPlaceholderText("选择条目查看检查报告"); root.addWidget(self.report, 1); self.status = QLabel(""); self.status.setObjectName("status"); root.addWidget(self.status)
        self.refresh()

    def refresh(self):
        self.scope.call("list", self.facade.skills, self._apply, lambda msg: self.status.setText(f"读取失败：{msg}"))

    def _apply(self, data):
        self.items = list(data.get("items") or {}); self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            for col, value in enumerate((item.get("name", ""), item.get("provider", ""), item.get("security_status", "unchecked"), str(item.get("updated_at", ""))[:19], str(item.get("security_findings", "")))): self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.status.setText(f"共 {len(self.items)} 项；需要确认的条目可直接信任或检查")

    def _show_report(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            self.report.clear(); return
        findings = self.items[selected[0].row()].get("security_findings") or []
        import json
        self.report.setPlainText(json.dumps(findings, ensure_ascii=False, indent=2, default=str) if findings else "暂无命中项；状态由最近一次路线检查或人工放行记录提供。")

    def batch_scan(self):
        route = self.route.currentData(); pending = [i for i in self.items if i.get("security_status") in {"unchecked", "warning", "error"}]
        for item in pending:
            self.jobs.submit("scan", f"安全检查 {item['name']}", lambda report, item=item: self.facade.skill_scan(item["name"], item.get("library", ""), route=route, progress=report), progress=True)

    def showEvent(self, event): self.refresh(); super().showEvent(event)
