"""HAUI source provenance, theme isolation, stale sync and release path regression."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt

from mshub.errors import FetchError
from mshub.native.haui import ROOT, catalog, resolve
from mshub.native.theme import ThemeController, current_palette, graph_palette
from mshub.native.main_window import MainWindow
from mshub.native.job_controller import JobController
from mshub.native import upgrader


def contrast(a, b):
    def lum(color):
        values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
        return sum(a * b for a, b in zip(values, (.2126, .7152, .0722)))
    x, y = sorted((lum(a), lum(b)))
    return (y + .05) / (x + .05)


def test_deferred_layout_callbacks_cancel_with_destroyed_window(qapp, native_facade, monkeypatch):
    import sys
    from PySide6.QtCore import QCoreApplication, QEvent
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: errors.append(args))
    window = MainWindow(native_facade)
    window.show()
    window.jobs.shutdown()
    window.runner.pool.waitForDone(5000)
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert errors == []


def test_haui_redistributed_resources_match_manifest():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    for file, digest in manifest["outputs"].items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest, file
    assert len(catalog()["themes"]) == 12
    assert (ROOT / "licenses/Tabler-MIT.txt").is_file()
    assert (ROOT / "fonts/SpaceGrotesk-OFL.txt").is_file()


def test_existing_category_labels_follow_new_appearance(qapp, native_facade):
    native_facade.create_entry({"name": "theme-label", "title": "主题切换", "type": "reference"})
    window = MainWindow(native_facade)
    window.theme.apply("light")
    window.memory_page.refresh_sync()
    pill = window.memory_page._row_meta[0]["pill"]
    old_style = pill.styleSheet()
    window.theme.apply("dark")
    assert pill.styleSheet() != old_style
    assert current_palette()["reference"] in pill.styleSheet()


def test_webengine_console_enum_reports_error_without_type_error():
    from types import SimpleNamespace
    from mshub.native.views.graph_view import _GraphPage, QWebEnginePage
    messages = []
    page = SimpleNamespace(consoleError=SimpleNamespace(emit=messages.append))
    levels = QWebEnginePage.JavaScriptConsoleMessageLevel
    _GraphPage.javaScriptConsoleMessage(page, levels.WarningMessageLevel, "warning", 1, "file")
    _GraphPage.javaScriptConsoleMessage(page, levels.ErrorMessageLevel, "script error", 2, "file")
    assert messages == ["script error（file:2）"]


def test_all_exported_variants_have_readable_body_and_filled_actions():
    for name, preset in catalog()["themes"].items():
        for accent, appearances in preset["variants"].items():
            for mode, value in appearances.items():
                p = value["qt"]
                assert len(value["seeds"]) == 26, (name, accent, mode)
                assert contrast(p["ink"], p["bg"]) >= 4.5
                assert contrast(p["faint"], p["bg"]) >= 4.5
                assert contrast(p["on_action"], p["action"]) >= 4.5


def test_palette_mode_and_accent_persist_independently(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    settings.setValue("theme", "dark")  # v1.11.4 migration
    theme = ThemeController(settings)
    theme.apply(palette="everforest", accent="rose")
    assert theme.mode == "dark"
    snapshot = dict(current_palette())
    restored = ThemeController(settings)
    restored.apply()
    assert (restored.palette, restored.accent, restored.mode) == ("everforest", "rose", "dark")
    assert current_palette() == snapshot
    # Stylesheet literals no longer select a different appearance.
    qapp.setStyleSheet(qapp.styleSheet() + "/* #ffffff #000000 */")
    assert current_palette() == snapshot
    assert graph_palette("dark")["controls"] == snapshot
    theme.apply("light", palette="nous", accent="default")


def test_invalid_saved_preferences_recover(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "bad.ini"), QSettings.Format.IniFormat)
    for key in ("theme", "haui/palette", "haui/accent"):
        settings.setValue(key, "invalid")
    theme = ThemeController(settings)
    assert (theme.mode, theme.palette, theme.accent) == ("system", "nous", "default")
    theme.apply()


def test_navigation_remains_keyboard_reachable(qapp, native_facade):
    window = MainWindow(native_facade)
    try:
        assert window.nav.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert window.settings_page.palette_combo.count() == 12
        assert window.settings_page.accent_combo.count() == 9
    finally:
        window.close()


def test_stale_sync_preview_cannot_import_into_new_repository(qapp, native_facade, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    native_facade.save_config({"auto_sync_source": str(source), "auto_sync_on_startup": True})
    window = MainWindow(native_facade)
    submitted = []
    monkeypatch.setattr(window.jobs, "submit", lambda *a, **kw: submitted.append(a))
    try:
        snapshot = window._sync_identity(native_facade.config())
        native_facade.save_config({"repo_root": str(tmp_path / "another-repo")})
        window._auto_sync_apply({"changed": True, "imported": ["one"]}, str(source), source, snapshot)
        assert submitted == []
    finally:
        window.close()


def test_disabling_sync_invalidates_preview(qapp, native_facade, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    native_facade.save_config({"auto_sync_source": str(source), "auto_sync_on_startup": True})
    window = MainWindow(native_facade)
    submitted = []
    monkeypatch.setattr(window.jobs, "submit", lambda *a, **kw: submitted.append(a))
    try:
        snapshot = window._sync_identity(native_facade.config())
        native_facade.save_config({"auto_sync_on_startup": False})
        window._auto_sync_apply({"changed": True}, str(source), source, snapshot)
        assert not submitted
    finally:
        window.close()


def test_idle_job_poll_does_not_rebuild_ui(qapp):
    jobs = JobController()
    changes = []
    jobs.changed.connect(lambda: changes.append(True))
    try:
        for _ in range(8):
            jobs.poll()
        assert len(changes) == 1
    finally:
        jobs.shutdown()


@pytest.mark.parametrize("name", ["../escape.txt", "../payload-neighbor/file", "x/../../escape", "x\\..\\escape", "app/x:stream", "app/NUL.txt", "app/file.", "app/file "])
def test_upgrade_rejects_windows_aliases_and_escape(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, "must not be extracted")
    target = tmp_path / "payload"
    target.mkdir()
    with pytest.raises(FetchError):
        upgrader._extract_zip_safely(archive, target)
    assert list(target.rglob("*")) == []


def test_upgrade_rejects_symlink_and_duplicate_case(tmp_path):
    for kind in ("symlink", "duplicate"):
        archive = tmp_path / f"{kind}.zip"
        with zipfile.ZipFile(archive, "w") as z:
            if kind == "symlink":
                info = zipfile.ZipInfo("app/link")
                info.create_system = 3
                info.external_attr = 0o120777 << 16
                z.writestr(info, "../outside")
            else:
                z.writestr("app/a.txt", "one")
                z.writestr("app/A.txt", "two")
        target = tmp_path / kind
        target.mkdir()
        with pytest.raises(FetchError):
            upgrader._extract_zip_safely(archive, target)


def test_upgrade_comparison_streams_and_detects_late_difference(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"a" * (2 * 1024 * 1024) + b"end")
    b.write_bytes(b"a" * (2 * 1024 * 1024) + b"end")
    monkeypatch.setattr(Path, "read_bytes", lambda _path: pytest.fail("must stream"))
    assert upgrader._same_contents(a, b)
    with b.open("r+b") as f:
        f.seek(-1, 2)
        f.write(b"x")
    assert not upgrader._same_contents(a, b)
