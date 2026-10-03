"""Export the actual v1.10.5 Qt memory page into an editable SVG review kit.

Only this export process uses fixture data and temporary config. Product code,
user config, repositories, and release binaries are not changed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["QT_QPA_PLATFORM"] = "windows"
os.environ["QT_SCALE_FACTOR"] = "1"

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPainter, QRegion, QFontDatabase
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QApplication, QWidget
from mshub.config import ConfigStore
from mshub.native.memory_facade import MemoryFacade
from mshub.native.main_window import MainWindow

ROWS = [
    ("ui-design", "123 MSHub 界面设计规范", "统一亮暗主题、字号、间距与选中反馈。", "project", ["UI设计", "主题规范"], "manual"),
    ("writing", "中文文案与沟通偏好", "使用简洁清晰的中文，先给结论，再说明依据。", "user", ["写作", "偏好"], "agent"),
    ("release", "Windows 完整包发布流程", "记录版本冻结、构建、校验与交付文件清单。", "project", ["发布", "Windows"], "manual"),
    ("review", "代码审查与验收原则", "逐条核对需求、影响范围及自动化验证结果。", "reference", ["审查", "验收"], "imported"),
    ("feedback", "后台任务交互反馈", "任务出现时展开，允许用户主动收起与重试。", "feedback", ["交互", "任务"], "agent"),
    ("paths", "本地记忆仓库目录约定", "条目文件是事实源，索引辅助搜索与关联。", "reference", ["仓库", "目录"], "imported"),
    ("agent", "Agent 协作上下文", "持续维护项目约束、已确认决定和待办事项。", "project", ["Agent", "协作"], "agent"),
    ("readability", "列表可读性检查记录", "比较标题、摘要和元数据在两种主题中的层级。", "feedback", ["排版", "列表"], "manual"),
    ("privacy", "个人数据与配置偏好", "配置与仓库独立保存，便于升级和迁移。", "user", ["配置", "本地"], "manual"),
    ("links", "双链与知识关联示例", "通过关联标签和双向链接连接可复用知识。", "reference", ["双链", "知识"], "imported"),
]
ITEMS = [dict(name=n, title=t, description=d, type=k, tags=tags, source=s,
              created="2026-10-01", updated="2026-10-03") for n,t,d,k,tags,s in ROWS]
FIXTURE = dict(items=ITEMS, stats=dict(total=len(ITEMS), types=dict(user=2, project=3, reference=3, feedback=2), this_week=10, inbox_pending=0))
JOBS = [
    dict(id="preview-1", label="归纳整理记忆", status="running", progress=65, phase="正在处理", error="", result=None),
    dict(id="preview-2", label="技能离线检查", status="error", progress=40, phase="检查中断", error="示例失败状态", result=None),
    dict(id="preview-3", label="导入记忆条目", status="done", progress=100, phase="已完成", error="", result=None),
    dict(id="preview-4", label="更新技能索引", status="done", progress=100, phase="已完成", error="", result=None),
]

def settle(app, seconds=0.15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)

def main():
    HERE.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    with tempfile.TemporaryDirectory(prefix="mshub-svg-review-") as temp:
        store = ConfigStore(Path(temp) / "config")
        store.save(dict(repo_root=str(Path(temp) / "repo"), language="zh-CN", auto_check_updates=False))
        facade = MemoryFacade(store)
        facade.list_entries = lambda **kwargs: FIXTURE
        window = MainWindow(facade)
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.resize(1440, 900)
        window.memory_page._load_detail = lambda *args: None
        window.memory_page._current_name = ITEMS[0]["name"]
        window.show()
        settle(app, 0.6)
        window.jobs.timer.stop()
        window.jobs.list = lambda: JOBS
        window.jobs.can_retry = lambda job_id: job_id == "preview-2"
        window._refresh_jobs()
        window.memory_page.refresh_sync()
        window._set_nav_count("skills", 24)
        window._set_nav_count("security", 3)
        window.job_table.selectRow(1)
        window.memory_page.entry_list.setFocus()
        info = {}
        for mode in ("light", "dark"):
            window.theme.apply(mode)
            settle(app, 0.2)
            window.memory_page._timer.stop()
            window.memory_page.refresh_sync()
            window.job_activity_icon.timer.stop()
            window.job_activity_icon.angle = 0
            settle(app)
            window.grab().save(str(HERE / f"native-{mode}.png"))
            for widget in [window, *window.findChildren(QWidget)]:
                effect = widget.graphicsEffect()
                if effect:
                    effect.setEnabled(False)
            generator = QSvgGenerator()
            generator.setFileName(str(HERE / f"probe-{mode}.svg"))
            generator.setSize(window.size())
            generator.setViewBox(QRect(0, 0, window.width(), window.height()))
            generator.setResolution(96)
            generator.setTitle(f"123 MSHub v1.10.5 - Memory - {mode}")
            painter = QPainter(generator)
            window.render(painter, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawWindowBackground | QWidget.RenderFlag.DrawChildren)
            painter.end()
            svg = ET.parse(HERE / f"probe-{mode}.svg")
            counts = {}
            for element in svg.iter():
                tag = element.tag.rsplit("}", 1)[-1]
                counts[tag] = counts.get(tag, 0) + 1
            info[mode] = counts
        print(json.dumps(dict(font=QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family(), counts=info), ensure_ascii=False))
        window.close()
        settle(app)

if __name__ == "__main__":
    main()
