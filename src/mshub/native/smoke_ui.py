"""Opt-in Windows release QA using an empty, explicitly isolated repository.

Runs the same shell and services as the product. No provider credentials or
network services are needed. Only the hidden --smoke-ui entry point calls this.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
import sys
import time
import traceback

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, Qt
from PySide6.QtGui import QFontInfo, QFontMetrics
from PySide6.QtWidgets import QLabel, QMessageBox, QTabWidget

from .. import __version__
from .branding import create_about_dialog
from .main_window import MainWindow
from .theme import current_palette
from .views.import_view import ImportDialog
from .views.skill_view import AddSkillDialog, MetadataDialog


def run_ui_smoke(app, facade, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    report = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
              "platform": app.platformName(), "scale": os.environ.get("QT_SCALE_FACTOR", "1"),
              "checks": {}, "screenshots": [], "errors": []}
    old_hook = sys.excepthook
    sys.excepthook = lambda kind, value, tb: report["errors"].append(
        "".join(traceback.format_exception(kind, value, tb)))
    window = None

    def pump(seconds=.15):
        loop = QEventLoop()
        QTimer.singleShot(max(1, int(seconds * 1000)), loop, loop.quit)
        loop.exec()

    def wait(check, label, seconds=15):
        end = time.monotonic() + seconds
        while not check():
            if time.monotonic() >= end:
                raise AssertionError(f"Timed out: {label}")
            pump(.03)
        report["checks"][label] = True

    def shot(name, widget=None):
        pump(.22)
        path = destination / f"{name}.png"
        pixmap = (widget or window).grab()
        assert pixmap.save(str(path)), name
        report["screenshots"].append({"file": path.name, "width": pixmap.width(),
                                      "height": pixmap.height(), "dpr": pixmap.devicePixelRatio()})

    def js(script):
        response = []
        window.graph_page.web_view.page().runJavaScript(script, lambda value: response.append(value))
        wait(lambda: bool(response), "webengine-callback", 20)
        return response[0]

    try:
        assert app.platformName() == "windows", "UI release QA requires the real Windows platform"
        facade.config_store.save({"auto_check_updates": False, "auto_sync_on_startup": False})
        records = [
            ("shared-memory", "共享记忆协议", "reference", "约定条目命名、双链和 Agent 读写边界。", "[[release-checks]] [[project-context]]"),
            ("project-context", "项目上下文与决策", "project", "让不同 Agent 共享经过整理的项目背景。", "[[shared-memory]] [[design-system]]"),
            ("design-system", "统一界面设计规范", "reference", "HAUI 调色板、字体和控件的使用规范。", "[[project-context]]"),
            ("release-checks", "发布验收清单", "project", "记录测试、文件校验和最终发布证据。", "[[design-system]] [[quality-feedback]]"),
            ("writing-preferences", "协作与写作偏好", "user", "先说明结论，保留可验证的操作记录。", "[[shared-memory]]"),
            ("quality-feedback", "交付质量反馈", "feedback", "中文字体清晰、列表稳定、操作状态可见。", "[[release-checks]]"),
        ]
        for name, title, kind, description, body in records:
            facade.create_entry({"name": name, "title": title, "type": kind,
                                 "description": description, "body": body, "tags": ["协作", "HAUI"]})
        source = facade.config_store.config_dir / "fixture-skill"
        source.mkdir()
        (source / "SKILL.md").write_text("---\ndescription: 离线整理项目笔记并输出检查清单。\n---\n# 交付检查\n只读取指定的本地资料。\n", encoding="utf-8")
        facade.repository.install(str(source), item_name="release-review", local_dir_name="release-review", tags=["验收", "本地"])
        # Simulate another PC syncing only a skill directory into a repository
        # whose local database already contains one installed skill.
        installed = facade.skills()["items"][0]
        original = facade.repo_root() / installed["local_dir"]
        synced = original.with_name("synced-at-startup")
        shutil.copytree(original, synced)
        manifest_file = synced / "_manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest["name"] = "synced-at-startup"
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        assert len(facade.skills()["items"]) == 1
        window = MainWindow(facade)
        window._ui_settings().setValue("setupHint/suppressed", True)
        geometry = app.primaryScreen().availableGeometry()
        window.resize(min(1440, geometry.width() - 32), min(900, geometry.height() - 56))
        window.theme.apply("light", palette="nous", accent="default")
        window.show_after_graph_prewarm()
        wait(lambda: window.isVisible() and window.memory_page.entry_list.count() == 6, "startup-and-memory-list")
        label = window.findChild(QLabel, "title")
        report["body_font"] = QFontInfo(window.nav.font()).family()
        report["title_font"] = QFontInfo(label.font()).family()
        report["brand_font"] = QFontInfo(window.brand_label.font()).family()
        report["version_font"] = QFontInfo(window.brand_version.font()).family()
        assert report["brand_font"].startswith("Space Grotesk"), report["brand_font"]
        assert report["version_font"] == "JetBrains Mono", report["version_font"]
        report["cjk_glyphs"] = QFontMetrics(window.nav.font()).inFontUcs4(ord("记"))
        assert report["cjk_glyphs"], "Chinese font unavailable"
        shot("memory-light")

        # Exercise the actual asynchronous edit/save/search flow.
        page = window.memory_page
        page.open_new_editor()
        page.name_edit.setText("ui-created")
        page.title_edit.setText("从界面创建的记忆")
        page.description_edit.setText("验证新建、保存、搜索与双链预览。")
        page.tags_edit.setText("验收, HAUI")
        page.body_edit.setPlainText("# 功能保留验证\n\n这条记忆由新版编辑窗口保存。\n\n关联 [[shared-memory]]。")
        page.save_button.click()
        wait(lambda: page.status.text() == "已保存" and not page._dirty, "async-editor-save")
        shot("memory-editor", page.editor_dialog)
        page.preview_mode.click()
        shot("memory-preview", page.editor_dialog)
        page.editor_dialog.close()
        page.search.setText("从界面创建")
        wait(lambda: page.entry_list.count() == 1, "memory-search")
        page.search.clear()
        wait(lambda: page.entry_list.count() == 7, "memory-search-reset")
        page.master_check.setChecked(True)
        shot("memory-selection")
        page.master_check.setChecked(False)
        window.theme.apply("dark")
        shot("memory-dark")

        window.nav.setCurrentRow(1)
        graph = window.graph_page
        report["graph_messages"] = []
        graph.statusMessage.connect(report["graph_messages"].append)
        wait(lambda: graph.web_view is not None and graph._page_loaded, "local-webengine-loaded")
        wait(lambda: bool(js("Boolean(window.mshubGraphReady && window.mshubGraphNodeCount >= 7)")), "graph-data-ready")
        state = json.loads(js("JSON.stringify({system:document.documentElement.dataset.designSystem, ready:window.mshubGraphReady,nodes:window.mshubGraphNodeCount,edges:window.mshubGraphEdgeCount,bg:getComputedStyle(document.body).backgroundColor,overflow:document.body.scrollWidth>innerWidth,fonts:document.fonts.check('13px \"Space Grotesk\"')})"))
        assert state["system"] == "HAUI" and not state["overflow"], state
        report["graph"] = state
        shot("graph-dark")
        js("document.getElementById('settings-toggle').click()")
        shot("graph-settings")
        wait(lambda: bool(js("document.fonts.check('13px \"Space Grotesk\"') && document.fonts.check('13px \"JetBrains Mono\"')")), "graph-local-fonts")
        report["graph"]["fonts"] = True
        js("document.getElementById('save-settings').click()")
        window.theme.apply("light")
        shot("graph-light")
        report["graph"]["light_bg"] = js("getComputedStyle(document.body).backgroundColor")
        assert report["graph"]["light_bg"] != state["bg"]
        def frame_digest():
            image = graph.web_view.grab().toImage()
            return hashlib.sha256(bytes(image.bits())).hexdigest()
        pump(2)
        first = frame_digest()
        pump(2)
        second = frame_digest()
        report["graph"]["frames_differ"] = first != second
        assert first != second, "Graph idle motion did not change rendered pixels"

        window.nav.setCurrentRow(2)
        wait(lambda: {item["name"] for item in window.skills_page.items} == {"release-review", "synced-at-startup"}, "startup-recovers-synced-skill")
        shot("skills-light")
        for name, dialog in (("skill-add", AddSkillDialog(window.skills_page)),
                             ("skill-metadata", MetadataDialog(window.skills_page, window.skills_page.items[0]))):
            dialog.show()
            shot(name, dialog)
            dialog.close()
        window.nav.setCurrentRow(3)
        wait(lambda: len(window.security_page.items) == 2, "security-list")
        shot("security-light")
        window.theme.apply("dark")
        shot("security-dark")

        window.nav.setCurrentRow(4)
        window.settings_page.load_config()
        tabs = window.settings_page.findChild(QTabWidget)
        for i in range(tabs.count()):
            tabs.setCurrentIndex(i)
            shot(f"settings-{i}-dark")
        tabs.setCurrentIndex(0)
        def save_appearance(mode, palette, accent):
            settings = window.settings_page
            for combo, value in ((settings.theme_combo, mode), (settings.palette_combo, palette),
                                 (settings.accent_combo, accent)):
                combo.setCurrentIndex(combo.findData(value))
            settings.save_button.click()
            wait(lambda: (window.theme.mode, window.theme.palette, window.theme.accent) ==
                 (mode, palette, accent), "appearance-settings-save")
            assert settings.palette_combo.currentData() == palette
        save_appearance("light", "everforest", "teal")
        shot("settings-everforest")
        save_appearance("light", "nous", "default")
        dialog = create_about_dialog(window)
        dialog.show()
        shot("about", dialog)
        dialog.close()
        dialog = ImportDialog(facade, window.runner, window.jobs, str(source), window)
        dialog.show()
        pump(.6)
        shot("import-preview", dialog)
        dialog.close()
        prompt = QMessageBox(QMessageBox.Icon.Question, "确认操作", "是否将选中的测试条目移入回收目录？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, window)
        prompt.show()
        shot("confirmation", prompt)
        prompt.reject()

        window.jobs.submit("ui-smoke", "本地验收完成", lambda: {"summary": "记忆、技能、图谱与设置均已完成界面检查。"})
        wait(lambda: any(job["status"] == "done" for job in window.jobs.list()), "background-task-complete")
        window.nav.setCurrentRow(0)
        shot("task-panel")
        window.language.apply("en")
        shot("memory-english")
        window.language.apply("zh-CN")
        window.resize(960, 640)
        shot("memory-minimum-size")

        # Exercise long-list scrolling through the real frozen widgets; these
        # synthetic rows are presentation fixtures, never written to user data.
        window.resize(1280, 820)
        pump(.4)
        page = window.memory_page
        base = page._items[0]
        page._apply_listing({"items": [{**base, "name": f"sort-{i:02}", "title": f"排序验收 {i:02}",
                              "tags": [f"tag-{39-i:02}"], "source": ("manual", "imported")[i % 2],
                              "updated": f"2026-10-{i % 28 + 1:02}"} for i in range(40)]})
        page._row_checks[7].setChecked(True)
        checked = set(page._selected_names())
        for key, button in page.sort_headers.items():
            for _ in range(2):
                page.entry_list.scrollToBottom()
                assert page.entry_list.verticalScrollBar().value() > 0
                button.click()
                assert page.entry_list.verticalScrollBar().value() == 0, key
                assert set(page._selected_names()) == checked
        report["checks"]["memory-all-header-sorts-at-top"] = True
        shot("memory-sort-top")
        window.nav.setCurrentRow(2)
        pump(.6)
        page = window.skills_page
        base = page.items[0]
        page.items = [{**base, "name": f"sort-{i:02}", "tags": [f"tag-{39-i:02}"],
                       "updated_at": f"2026-10-{i % 28 + 1:02}",
                       "provider": ("github", "local")[i % 2],
                       "security_status": ("unchecked", "safe", "warning")[i % 3]} for i in range(40)]
        page._apply_rows()
        page.table.selectRow(20)
        page.table.cellWidget(7, 0).setChecked(True)
        for column in (1, 2, 4, 5, 6):
            for _ in range(2):
                page.table.scrollToBottom()
                assert page.table.verticalScrollBar().value() > 0
                page.table_card.header.sectionClicked.emit(column)
                assert page.table.verticalScrollBar().value() == 0, column
                assert page._checked() == [("sort-07", base["library"])]
        report["checks"]["skills-all-header-sorts-at-top"] = True
        shot("skills-sort-top")
        assert not report["errors"], report["errors"]
        report["passed"] = True
    except Exception:
        report["passed"] = False
        report["errors"].append(traceback.format_exc())
    finally:
        if window is not None:
            window.memory_page._dirty = False
            window.jobs.shutdown()
            window.runner.pool.waitForDone(5000)
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        if report["errors"]:
            report["passed"] = False
        sys.excepthook = old_hook
        (destination / "ui-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 5
