"""v1.7.4 迭代的功能回归：翻译方向、表头排序/多选、双击弹窗、清除配置、环境包检测、图谱滚轮。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QMessageBox

from mshub.native.main_window import MainWindow
from mshub.native.memory_facade import MemoryFacade

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _skill(name: str, **kwargs):
    base = {"name": name, "library": "skills", "provider": "github", "security_status": "unchecked", "updated_at": "2026-01-01T00:00:00", "description": "", "description_zh": "", "tags": []}
    base.update(kwargs)
    return base


# ---- 2. 自动翻译：固定「左中文 / 右英文」 --------------------------------

def test_translation_probe_detects_chinese():
    from mshub.native.views.skill_view import MetadataDialog

    assert MetadataDialog._looks_chinese("这是一段中文说明")
    assert MetadataDialog._looks_chinese("mshub 管理本地技能")
    assert not MetadataDialog._looks_chinese("Manage local agent skills")


def test_auto_translate_moves_chinese_source_to_left(qapp, native_facade: MemoryFacade):
    """原文说明是中文（在右栏）时：先搬到左栏，再向右栏请求英文翻译。"""
    from mshub.native.views.skill_view import MetadataDialog

    window = MainWindow(native_facade)
    page = window.skills_page
    dialog = MetadataDialog(page, _skill("demo"))
    dialog.description_zh.setPlainText("")
    dialog.description.setPlainText("把本地技能统一管理的仓库工具")
    dialog.auto_translate()
    # 搬移是同步的：左栏拿到中文原文，右栏清空等待译文
    assert dialog.description_zh.toPlainText() == "把本地技能统一管理的仓库工具"
    assert dialog.description.toPlainText() == ""
    window.close()


def test_auto_translate_swaps_reversed_sides(qapp, native_facade: MemoryFacade):
    """两侧语言装反（左英右中）时：点击后直接交换，不调接口。"""
    from mshub.native.views.skill_view import MetadataDialog

    window = MainWindow(native_facade)
    dialog = MetadataDialog(window.skills_page, _skill("demo"))
    dialog.description_zh.setPlainText("English text on the wrong side")
    dialog.description.setPlainText("中文说明在右侧")
    dialog.auto_translate()
    assert dialog.description_zh.toPlainText() == "中文说明在右侧"
    assert dialog.description.toPlainText() == "English text on the wrong side"
    assert "装反" in dialog.translate_status.text()
    window.close()


# ---- 3/6. 技能列表：排序、全选、刷新跳回 ---------------------------------

def test_skills_header_renamed_and_sorts(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.skills_page
    assert page.table.horizontalHeaderItem(0).text() == "多选"
    page.items = [_skill("banana"), _skill("apple"), _skill("cherry")]
    page._apply_rows()
    page._header_clicked(1)  # 名称升序
    assert [page.table.item(row, 1).text() for row in range(3)] == ["apple", "banana", "cherry"]
    page._header_clicked(1)  # 再点降序
    assert [page.table.item(row, 1).text() for row in range(3)] == ["cherry", "banana", "apple"]
    window.close()


def test_skills_sorts_by_security_rank(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.skills_page
    page.items = [_skill("a", security_status="warning"), _skill("b", security_status="safe"), _skill("c", security_status="unchecked")]
    page._apply_rows()
    page._header_clicked(4)  # 安全列升序：未检查 → 已通过 → 需复核
    assert [page.table.item(row, 1).text() for row in range(3)] == ["c", "b", "a"]
    window.close()


def test_skills_select_all_header_toggle(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.skills_page
    page.items = [_skill("a"), _skill("b")]
    page._apply_rows()
    page._header_clicked(0)  # 全选
    assert len(page._checked()) == 2
    page._header_clicked(0)  # 全取消
    assert page._checked() == []
    window.close()


def test_skills_refresh_restores_selection_and_checks(qapp, native_facade: MemoryFacade):
    """刷新/排序后：选中行与勾选状态不丢，且不再强制跳回第 0 行。"""
    window = MainWindow(native_facade)
    page = window.skills_page
    page.items = [_skill(f"item-{i}") for i in range(5)]
    page._apply_rows()
    page.table.selectRow(3)
    page.table.cellWidget(2, 0).setChecked(True)
    page._apply_rows()  # 模拟数据刷新
    assert page.table.item(page.table.currentRow(), 1).text() == "item-3"
    assert len(page._checked()) == 1 and page._checked()[0][0] == "item-2"
    # 编辑保存登记回跳目标后，刷新滚到目标行（含改名场景）
    page._pending_focus = ("renamed", "skills")
    page.items = [_skill("renamed"), *_skill_list(4)]
    page._apply_rows()
    assert page.table.item(page.table.currentRow(), 1).text() == "renamed"
    window.close()


def _skill_list(count: int):
    return [_skill(f"item-{i}") for i in range(count)]


# ---- 5/6. 安全中心：多选列、排序、隐藏已通过 -----------------------------

def test_security_table_has_multi_column_and_sorts(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.security_page
    assert page.table.horizontalHeaderItem(0).text() == "多选"
    page.items = [
        _skill("a", security_status="safe", updated_at="2026-01-02T00:00:00"),
        _skill("b", security_status="warning", updated_at="2026-03-04T00:00:00"),
        _skill("c", security_status="unchecked", updated_at="2026-02-03T00:00:00"),
    ]
    page._apply({"items": page.items})
    assert page.table.rowCount() == 3
    assert isinstance(page.table.cellWidget(0, 0), QCheckBox)
    page._header_clicked(4)  # 最近检查升序
    assert [page.table.item(row, 1).text() for row in range(3)] == ["a", "c", "b"]
    page._header_clicked(3)  # 状态升序
    assert [page.table.item(row, 1).text() for row in range(3)] == ["c", "a", "b"]
    window.close()


def test_security_hide_passed_toggle(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.security_page
    page.items = [_skill("a", security_status="safe"), _skill("b", security_status="warning"), _skill("c", security_status="SAFE")]
    page._hide_passed = True
    page._apply({"items": page.items})
    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "b"
    assert "已通过 2 项已隐藏" in page.status.text()
    page._hide_passed = False
    page._apply({"items": page.items})
    assert page.table.rowCount() == 3
    window.close()


# ---- 7. 双击弹两个窗口的修复 ---------------------------------------------

def test_skill_detail_dialog_is_single_instance(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.skills_page
    page.items = [_skill("demo")]
    page._apply_rows()
    page.table.selectRow(0)
    page.show_detail_dialog()
    first = page._detail_dialog
    assert first is not None and first.isVisible()
    # v1.7.5 加了 0.35s 防重入（双信号只开一窗）——重置时间戳模拟用户稍后再开
    page._detail_dialog_last_open = 0.0
    page.show_detail_dialog()
    assert page._detail_dialog is not first, "第二次打开应换新窗口而不是叠加"
    window.close()


# ---- 8. 清除配置入口 ------------------------------------------------------

def test_clear_repo_data_detaches_but_keeps_config(qapp, native_facade: MemoryFacade, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window = MainWindow(native_facade)
    native_facade.save_config({"repo_root": str(native_facade.config_store.config_dir.parent / "repo"), "ai_model": "keep-me"})
    window.settings_page.load_config()
    window.settings_page.clear_repo_data()
    config = native_facade.config()
    assert config.repo_root == ""
    assert config.memory_root_override == ""
    assert config.ai_model == "keep-me", "API 等配置应保留"
    window.close()


def test_clear_all_settings_resets_everything(qapp, native_facade: MemoryFacade, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window = MainWindow(native_facade)
    native_facade.save_config({"repo_root": str(native_facade.config_store.config_dir.parent / "repo"), "ai_key": "secret", "language": "en"})
    window.settings_page.load_config()
    (native_facade.config_store.config_dir / "native-ui.ini").write_text("[General]\n", encoding="utf-8")
    window.settings_page.clear_all_settings()
    config = native_facade.config()
    assert config.repo_root == "" and config.language == "system"
    assert not config.ai_key_configured, "钥匙串里的 AI 密钥应被删除"
    assert not (native_facade.config_store.config_dir / "native-ui.ini").exists(), "界面偏好应一并清空"
    window.close()


# ---- 11. 环境包缺失检测 ---------------------------------------------------

def test_missing_environment_returns_none_when_not_frozen():
    from mshub.native.app import missing_environment_text

    assert missing_environment_text() is None


def test_missing_environment_detects_absent_pyside6(tmp_path, monkeypatch):
    from mshub.native import app as native_app

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "123mshub.exe"))
    text = native_app.missing_environment_text()
    assert text is not None and "环境包" in text and native_app.ENV_PACKAGE_URL in text
    (tmp_path / "_internal" / "PySide6").mkdir(parents=True)
    (tmp_path / "_internal" / "PySide6" / "Qt6Core.dll").write_bytes(b"x")
    assert native_app.missing_environment_text() is None


# ---- 1. 图谱：滚轮不再冻结呼吸（源码级防回归） ---------------------------

def test_graph_wheel_no_longer_pauses_breathing():
    source = (PROJECT_ROOT / "web" / "native-graph" / "graph.js").read_text(encoding="utf-8")
    assert "on('wheel', markInteraction)" not in source, "滚轮不应再挂 markInteraction（会冻结呼吸约 1s）"
    assert source.count("updateFloatScale()") >= 2, "floatTick 需每帧跟踪缩放比"


# ---- 10. 后台任务两字开头 -------------------------------------------------

def test_job_labels_use_two_char_prefix(qapp, native_facade: MemoryFacade):
    window = MainWindow(native_facade)
    page = window.skills_page
    page.items = [_skill("demo-skill")]
    page._apply_rows()
    page.table.selectRow(0)
    page.scan("offline")
    labels = [job["label"] for job in window.jobs.list()]
    assert labels and labels[0].startswith("检查 demo-skill")
    window.close()
