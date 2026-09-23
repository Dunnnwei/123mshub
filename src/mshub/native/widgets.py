"""Small shared native controls; no repository policy lives here."""
from __future__ import annotations

import json
import re
from datetime import datetime

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QTextBrowser, QVBoxLayout)

from ..tags import normalize_tags


class MarkdownView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)

    def loadResource(self, _kind, _url):
        # Notes may be untrusted; never load remote images or local files.
        return None


class TagsEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("标签用中英文逗号分隔，Enter 确认；最多 12 个")
        self.returnPressed.connect(self.confirm_tags)

    def values(self):
        return normalize_tags(re.split(r"[,，\n]", self.text()))

    def confirm_tags(self):
        try:
            self.setText(", ".join(self.values()))
            self.setToolTip("")
        except ValueError as exc:
            self.setToolTip(str(exc))
        except Exception as exc:
            self.setToolTip(str(exc))


class CheckList(QListWidget):
    """Qt supplies keyboard selection and rubber-band extended selection."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setSelectionRectVisible(True)
        self.setUniformItemSizes(True)
        self.setWordWrap(False)

    def checked(self):
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())
                if self.item(i).checkState() == Qt.CheckState.Checked or self.item(i).isSelected()]


def button(text, callback, *, primary=False, danger=False):
    result = QPushButton(text)
    if primary:
        result.setObjectName("primary")
    if danger:
        result.setObjectName("danger")
    result.clicked.connect(callback)
    return result


def report_text(result):
    if isinstance(result, dict) and result.get("content"):
        return str(result["content"])
    if isinstance(result, str):
        return result
    return "```json\n" + json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n```"


def show_report(parent, title, result):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(960, 680)
    root = QVBoxLayout(dialog)
    view = MarkdownView()
    view.setMarkdown(report_text(result))
    root.addWidget(view)
    actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    actions.rejected.connect(dialog.reject)
    root.addWidget(actions)
    from .i18n import localize
    localize(dialog)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.open()
    return dialog


def confirm(parent, title, text):
    return QMessageBox.question(parent, title, text) == QMessageBox.StandardButton.Yes


def local_time(value):
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(value or "")[:19]


def copy_text(text):
    QApplication.clipboard().setText(text)
