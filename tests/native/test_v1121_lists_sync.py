"""Sorting viewport/state and real cross-machine startup recovery regressions."""
import shutil
import time

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from mshub.config import ConfigStore
from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade


def wait_for(qapp, predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        QTest.qWait(10)
    assert predicate()


def skill_rows():
    return [{"name": f"skill-{i:02}", "library": "skills", "tags": [f"tag-{(i * 7) % 40:02}"],
             "provider": "github" if i % 2 else "local", "updated_at": f"2026-10-{i % 28 + 1:02}",
             "security_status": ("safe", "unchecked", "warning", "critical")[i % 4]}
            for i in range(40)]


def memory_rows():
    return [{"name": f"note-{i:02}", "title": f"note-{i:02}", "tags": [f"tag-{(i * 7) % 40:02}"],
             "type": ("reference", "user", "project", "feedback")[i % 4],
             "source": ("manual", "imported", "agent")[i % 3],
             "updated": f"2026-10-{i % 28 + 1:02}", "created": f"2026-09-{i % 28 + 1:02}"}
            for i in range(40)]


@pytest.mark.parametrize("column", [1, 2, 4, 5, 6])
def test_skill_sort_click_jumps_to_top_and_preserves_checked_identity(qapp, native_facade, monkeypatch, column):
    window = MainWindow(native_facade)
    page = window.skills_page
    monkeypatch.setattr(page, "refresh", lambda *_: None)
    window.pages.setCurrentWidget(page)
    window.show()
    page._timer.stop()
    page.items = skill_rows()
    page._apply_rows()
    page.table.selectRow(20)
    page.table.cellWidget(7, 0).setChecked(True)
    qapp.processEvents()
    header = page.table_card.header
    for _ in range(2):
        page.table.scrollToBottom()
        assert page.table.verticalScrollBar().value() > 0
        x = header.sectionViewportPosition(column) + header.sectionSize(column) // 2
        QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x, header.height() // 2))
        assert page.table.verticalScrollBar().value() == 0
        qapp.processEvents()
        assert page.table.verticalScrollBar().value() == 0
        assert page.table.visualItemRect(page.table.item(0, 1)).intersects(page.table.viewport().rect())
        assert page._checked() == [("skill-07", "skills")]
        assert page.table.item(page.table.currentRow(), 1).text() == "skill-20"
    window.close()


def test_skill_pending_refresh_keeps_sorted_top_but_edit_save_can_focus(qapp, native_facade, monkeypatch):
    window = MainWindow(native_facade)
    page = window.skills_page
    window.pages.setCurrentWidget(page)
    window.show()
    page._timer.stop()
    page.items = skill_rows()
    page._apply_rows()
    page.table.selectRow(20)
    qapp.processEvents()
    callbacks = []
    monkeypatch.setattr(page.scope, "call", lambda channel, fn, done, fail: callbacks.append(done))
    page._refresh_now()
    page._header_clicked(1)
    callbacks[0]({"items": skill_rows()})
    assert page.table.verticalScrollBar().value() == 0
    page._pending_focus = ("skill-30", "skills")
    page._apply_rows()
    assert page.table.item(page.table.currentRow(), 1).text() == "skill-30"
    assert page.table.verticalScrollBar().value() > 0
    window.close()


def prepare_memory(window, qapp):
    page = window.memory_page
    page._current_name = "note-20"
    page._apply_listing({"items": memory_rows()})
    window.show()
    qapp.processEvents()
    page._row_checks[7].setChecked(True)
    checked = set(page._selected_names())
    page.body_edit.setPlainText("unsaved draft")
    page._dirty = True
    return page, checked


@pytest.mark.parametrize("key", ["name", "tags", "type", "source", "updated"])
def test_memory_header_sort_is_immediate_and_keeps_draft_and_checks(qapp, native_facade, key):
    window = MainWindow(native_facade)
    page, checked = prepare_memory(window, qapp)
    try:
        for _ in range(2):
            page.entry_list.scrollToBottom()
            assert page.entry_list.verticalScrollBar().value() > 0
            QTest.mouseClick(page.sort_headers[key], Qt.MouseButton.LeftButton)
            assert page.entry_list.verticalScrollBar().value() == 0
            qapp.processEvents()
            assert page.entry_list.verticalScrollBar().value() == 0
            values = [(", ".join(item[key]) if isinstance(item[key], list) else item[key]).casefold()
                      for item in page._items]
            assert values == sorted(values, reverse=page._sort_descending)
            assert page.entry_list.visualItemRect(page.entry_list.item(0)).intersects(page.entry_list.viewport().rect())
            assert set(page._selected_names()) == checked
            assert page._current_name == "note-20" and page._dirty
            assert page.body_edit.toPlainText() == "unsaved draft"
            assert page._shift_anchor == -1
    finally:
        page._dirty = False
        window.close()


@pytest.mark.parametrize("key", ["name", "created", "updated"])
def test_memory_original_sort_combo_jumps_to_top(qapp, native_facade, key):
    window = MainWindow(native_facade)
    page, checked = prepare_memory(window, qapp)
    try:
        page.sort.setCurrentIndex(page.sort.findData("tags"))
        page.entry_list.scrollToBottom()
        page.sort.setCurrentIndex(page.sort.findData(key))
        assert page.entry_list.verticalScrollBar().value() == 0
        assert page._sort_key == key
        assert set(page._selected_names()) == checked
    finally:
        page._dirty = False
        window.close()


def test_memory_pending_read_cannot_undo_sort_and_empty_list_is_safe(qapp, native_facade, monkeypatch):
    window = MainWindow(native_facade)
    page, checked = prepare_memory(window, qapp)
    callbacks = []
    monkeypatch.setattr(page.scope, "call", lambda channel, fn, done, fail, **kw: callbacks.append(done))
    try:
        page.refresh()  # Pending filter/debounce when the user clicks a header.
        page.sort_headers["tags"].click()
        callbacks[-1]({"items": list(reversed(memory_rows()))})
        assert page.entry_list.verticalScrollBar().value() == 0
        assert set(page._selected_names()) == checked
        assert page._items[0]["tags"] == ["tag-00"]
        window.language.apply("en")
        assert page.sort_headers["tags"].text().endswith(" ↑")
        page._apply_listing({"items": []})
        page.sort_headers["name"].click()
        assert page.entry_list.count() == 0 and not page.master_check.isChecked()
        assert page._dirty and page.body_edit.toPlainText() == "unsaved draft"
    finally:
        page._dirty = False
        window.close()


def install_local(facade, tmp_path, name):
    source = tmp_path / ("source-" + name)
    source.mkdir()
    (source / "SKILL.md").write_text(f"---\ndescription: {name}\n---\n# {name}\n", encoding="utf-8")
    facade.repository.install(str(source), item_name=name, local_dir_name=name)
    return next(item for item in facade.skills()["items"] if item["name"] == name)


def quiet_startup(window, monkeypatch):
    for method in ("_prewarm_graph_page", "_maybe_show_setup_hint", "_startup_auto_sync"):
        monkeypatch.setattr(window, method, lambda: None)


def test_startup_recovers_new_skill_with_populated_database_and_late_arrival(qapp, native_facade, tmp_path, monkeypatch):
    install_local(native_facade, tmp_path, "existing")
    donor_store = ConfigStore(tmp_path / "donor-config")
    donor_store.save({"repo_root": str(tmp_path / "donor-repo")})
    donor = MemoryFacade(donor_store)

    def sync_directory(name):
        record = install_local(donor, tmp_path, name)
        shutil.copytree(donor.repo_root() / record["local_dir"], native_facade.repo_root() / record["local_dir"])

    sync_directory("synced-before-start")
    native_facade.heal()  # v1.12.0's startup path only heals memory.
    assert {item["name"] for item in native_facade.skills()["items"]} == {"existing"}
    window = MainWindow(native_facade)
    quiet_startup(window, monkeypatch)
    window.startup()
    window.startup()
    wait_for(qapp, lambda: len(window.skills_page.items) == 2 and len(window.security_page.items) == 2)
    assert len(window.jobs.list()) == 1 and window.jobs.list()[0]["status"] == "done"
    sync_directory("synced-after-start")
    assert len(native_facade.skills()["items"]) == 2  # No new filesystem watcher.
    window.jobs.submit("reconcile", "重新识别已同步条目", native_facade.rebuild)
    wait_for(qapp, lambda: len(window.skills_page.items) == 3)
    assert {item["name"] for item in window.skills_page.items} == {"existing", "synced-before-start", "synced-after-start"}
    window.close()


def test_failed_startup_reconcile_is_retryable_and_still_loads_memory(qapp, native_facade, monkeypatch):
    native_facade.create_entry({"name": "available", "type": "reference", "body": "memory remains usable"})
    def unavailable():
        raise OSError("temporary sync drive failure")
    monkeypatch.setattr(native_facade, "rebuild", unavailable)
    window = MainWindow(native_facade)
    quiet_startup(window, monkeypatch)
    window.startup()
    wait_for(qapp, lambda: window.memory_page.entry_list.count() == 1)
    job = window.jobs.list()[0]
    assert job["status"] == "error" and "temporary sync drive failure" in job["error"]
    assert window.jobs.can_retry(job["id"])
    window.close()
