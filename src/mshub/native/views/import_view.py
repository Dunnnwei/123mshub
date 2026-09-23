"""Import preview and background admission flow."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QVBoxLayout)

from ..task_runner import RequestScope


class ImportDialog(QDialog):
    def __init__(self, facade, runner, jobs, source: str, parent=None):
        super().__init__(parent)
        self.facade, self.runner, self.jobs = facade, runner, jobs
        self.source = Path(source)
        self.scope = RequestScope(runner, self)
        self.setWindowTitle("导入记忆技能库")
        self.resize(920, 650)
        root = QVBoxLayout(self)
        intro = QLabel(f"来源目录：{self.source}\n扫描是只读的；确认后写入当前仓库，重复内容按既有幂等规则跳过。")
        intro.setWordWrap(True); intro.setObjectName("muted"); root.addWidget(intro)
        options = QHBoxLayout()
        self.memory = QCheckBox("导入记忆"); self.memory.setChecked(True); options.addWidget(self.memory)
        self.skills = QCheckBox("导入技能 / 程序"); self.skills.setChecked(True); options.addWidget(self.skills)
        options.addStretch(); self.scan_button = QPushButton("扫描预览"); options.addWidget(self.scan_button); root.addLayout(options)
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True); self.preview.setFont(QFont("Cascadia Mono", 9)); root.addWidget(self.preview, 1)
        self.status = QLabel("尚未扫描"); self.status.setObjectName("status"); root.addWidget(self.status)
        buttons = QDialogButtonBox(); self.import_button = buttons.addButton("确认导入", QDialogButtonBox.ButtonRole.AcceptRole); close = buttons.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole); self.import_button.setEnabled(False); root.addWidget(buttons)
        self.scan_button.clicked.connect(self.scan); self.import_button.clicked.connect(self.start_import); close.clicked.connect(self.reject)
        self.scan()

    def scan(self):
        self.scan_button.setEnabled(False); self.status.setText("正在扫描（只读）…")
        self.scope.call("scan", self.facade.scan_import, self._show_scan, self._scan_failed, self.source)

    def _show_scan(self, result):
        self.scan_button.setEnabled(True); self.import_button.setEnabled(True); self.preview.setPlainText(self._format(result)); self.status.setText("扫描完成；检查预览后确认导入")

    def _scan_failed(self, message):
        self.scan_button.setEnabled(True); self.import_button.setEnabled(False); self.status.setText(f"扫描失败：{message}")

    @staticmethod
    def _format(result):
        memory = result.get("memory_preview") or []
        skills = result.get("skill_preview") or []
        lines = [f"记忆候选：{result.get('memory_count', len(memory))} 条", f"技能 / 程序候选：{result.get('skill_count', len(skills))} 个", ""]
        for item in memory[:100]:
            lines.append(f"[记忆] {item.get('path', '')} · {item.get('title') or item.get('name') or item.get('title_hint', '')}")
        for item in skills[:100]:
            lines.append(f"[技能] {item.get('path', '')} · {item.get('kind', '')} · 库 {item.get('library', '')}")
        notes = result.get("notes") or []
        if notes:
            lines.extend(["", "扫描提示：", *[f"- {note}" for note in notes]])
        return "\n".join(lines)

    def start_import(self):
        self.import_button.setEnabled(False); self.scan_button.setEnabled(False); self.status.setText("已提交后台任务；关闭此窗口不影响导入。")
        self.jobs.submit("import", f"导入 {self.source.name or self.source}", lambda report: self.facade.run_import(self.source, include_memory=self.memory.isChecked(), include_skills=self.skills.isChecked(), progress=report), progress=True)
        self.accept()
