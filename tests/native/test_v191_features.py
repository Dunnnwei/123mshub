"""v1.9.1 回归测试：Codex 审查修复（P0-1/P0-2/P1-1/P1-3/P1-5 + SHA256SUMS 校验）
与三项新功能（启动自动检查更新配置、锚点失效、安全中心按钮行、任务面板分隔条）。"""
import hashlib
import zipfile
from pathlib import Path

import pytest

from mshub.config import AppConfig
from mshub.errors import FetchError, ValidationError
from mshub.native import upgrader

GOOD_ZIP_URL = "https://github.com/Dunnnwei/123mshub/releases/download/v1.9.1/123mshub-native-v1.9.1-win64.zip"
SUMS_URL = "https://github.com/Dunnnwei/123mshub/releases/download/v1.9.1/SHA256SUMS-v1.9.1.txt"


def _release(*assets: dict) -> dict:
    return {"assets": list(assets)}


# ---- P0-1：资产名白名单 + 下载域白名单 -------------------------------------


def test_pick_asset_accepts_canonical_name_and_host():
    asset = {"name": "123mshub-native-v1.9.1-win64.zip", "url": GOOD_ZIP_URL, "size": 1}
    assert upgrader.pick_asset(_release(asset)) is asset


def test_pick_asset_neutralizes_path_in_name():
    # 带路径的资产名先取 basename 再对白名单——逃逸段被剥离，无法写出目标目录
    asset = {"name": "../../evil/123mshub-native-v1.9.1-win64.zip", "url": GOOD_ZIP_URL, "size": 1}
    picked = upgrader.pick_asset(_release(asset))
    assert upgrader._asset_basename(picked["name"]) == "123mshub-native-v1.9.1-win64.zip"
    with pytest.raises(FetchError):  # 剥完 basename 仍不匹配发布惯例 → 拒绝
        upgrader._asset_basename("../evil.zip")


def test_pick_asset_rejects_foreign_host():
    with pytest.raises(FetchError):
        upgrader.pick_asset(_release({"name": "123mshub-native-v1.9.1-win64.zip", "url": "https://evil.example.com/x.zip", "size": 1}))


def test_pick_asset_rejects_plain_http():
    with pytest.raises(FetchError):
        upgrader.pick_asset(_release({"name": "123mshub-native-v1.9.1-win64.zip", "url": "http://github.com/x.zip", "size": 1}))


def test_validate_asset_url_rejects_relative():
    with pytest.raises(FetchError):
        upgrader._validate_asset_url("/relative/path.zip")


# ---- SHA256SUMS 校验 -------------------------------------------------------


def test_pick_sums_asset_finds_manifest():
    release = _release({"name": "SHA256SUMS-v1.9.1.txt", "url": SUMS_URL, "size": 200},
                       {"name": "123mshub-native-v1.9.1-win64.zip", "url": GOOD_ZIP_URL, "size": 170})
    assert upgrader.pick_sums_asset(release)["url"] == SUMS_URL
    assert upgrader.pick_sums_asset(_release({"name": "x.zip", "url": GOOD_ZIP_URL, "size": 1})) is None


def test_parse_sums_matches_zip_line():
    digest = "a" * 64
    # build-native.ps1 生成的两空格格式；zip 行前面还有 exe 行
    text = f"{'b' * 64}  123mshub\\123mshub.exe\n{digest}  123mshub-native-v1.9.1-win64.zip\n"
    assert upgrader.parse_sums(text, "123mshub-native-v1.9.1-win64.zip") == digest


def test_parse_sums_rejects_missing_and_malformed():
    text = f"{'a' * 64}  123mshub-native-v1.9.1-win64.zip\n"
    with pytest.raises(FetchError):
        upgrader.parse_sums(text, "missing.zip")
    with pytest.raises(FetchError):  # 非 64 位十六进制
        upgrader.parse_sums("zzz  123mshub-native-v1.9.1-win64.zip", "123mshub-native-v1.9.1-win64.zip")


def test_file_sha256_streams_known_bytes(tmp_path: Path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"123mshub")
    assert upgrader.file_sha256(target) == hashlib.sha256(b"123mshub").hexdigest()


# ---- P1-1：镜像请求不携带凭据 ----------------------------------------------


def test_request_plan_mirror_gets_no_token():
    plan = upgrader._request_plan(GOOD_ZIP_URL, ["https://mirror.example/gh/"], "tok123")
    assert len(plan) == 2
    mirror_url, mirror_headers = plan[0]
    assert mirror_url.startswith("https://mirror.example/gh/")
    assert "Authorization" not in mirror_headers
    direct_url, direct_headers = plan[1]
    assert direct_url == GOOD_ZIP_URL
    assert direct_headers["Authorization"] == "Bearer tok123"


def test_request_plan_direct_only_mode_keeps_token():
    plan = upgrader._request_plan(GOOD_ZIP_URL, ["https://mirror.example/gh/"], "tok", allow_mirrors=False)
    assert len(plan) == 1
    assert plan[0][0] == GOOD_ZIP_URL
    assert plan[0][1]["Authorization"] == "Bearer tok"


# ---- P1-5：解压限额 --------------------------------------------------------


def test_extract_zip_rejects_total_blowup(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(upgrader, "MAX_EXTRACT_BYTES", 64)
    archive = tmp_path / "pkg.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("123mshub/big.bin", b"x" * 200)
    with pytest.raises(FetchError):
        upgrader._extract_zip_safely(archive, tmp_path / "out")
    assert not (tmp_path / "out" / "123mshub" / "big.bin").exists()


def test_extract_zip_member_count_cap(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(upgrader, "MAX_ARCHIVE_MEMBERS", 3)
    archive = tmp_path / "pkg.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for index in range(5):
            bundle.writestr(f"123mshub/f{index}.txt", "x")
    with pytest.raises(FetchError):
        upgrader._extract_zip_safely(archive, tmp_path / "out")


def test_extract_zip_within_limits_still_works(tmp_path: Path):
    archive = tmp_path / "pkg.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("123mshub/ok.txt", "hello")
    out = tmp_path / "out"
    upgrader._extract_zip_safely(archive, out)
    assert (out / "123mshub" / "ok.txt").read_text(encoding="utf-8") == "hello"


# ---- P0-2：删除仓库边界 ----------------------------------------------------


class _FakeDB:
    def __init__(self, item: dict):
        self._item = item
        self.deleted: list[str] = []

    def get_skill(self, name, library=None):
        return self._item

    def delete_skill(self, name, library=None):
        self.deleted.append(name)


def _repo_with(monkeypatch, tmp_path: Path, local_dir: str):
    from mshub import repository as repo_module
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "keep.txt").write_text("valuable", encoding="utf-8")
    repo = object.__new__(repo_module.SkillRepository)
    db = _FakeDB({"name": "victim", "library": "", "local_dir": local_dir, "author": "a", "repo": "r"})
    monkeypatch.setattr(repo, "_storage", lambda: (root, db))
    monkeypatch.setattr(repo_module, "rebuild_index", lambda *args, **kwargs: None)
    return repo, root, outside, db


def test_skill_delete_rejects_absolute_local_dir(monkeypatch, tmp_path: Path):
    repo, root, outside, db = _repo_with(monkeypatch, tmp_path, "")
    db._item["local_dir"] = str(outside)  # 绝对路径：Path 拼接会丢弃仓库根
    with pytest.raises(ValidationError):
        repo.delete("victim", hard=True)
    assert (outside / "keep.txt").exists()  # 仓库外文件原样保留
    assert db.deleted == []  # 数据库记录未动


def test_skill_delete_rejects_dotdot_escape(monkeypatch, tmp_path: Path):
    repo, root, outside, db = _repo_with(monkeypatch, tmp_path, "../outside")
    with pytest.raises(ValidationError):
        repo.delete("victim", hard=False)  # 软删除（move）同样被边界拦截
    assert (outside / "keep.txt").exists()


def test_skill_delete_rejects_repo_root_itself(monkeypatch, tmp_path: Path):
    repo, root, outside, db = _repo_with(monkeypatch, tmp_path, ".")
    with pytest.raises(ValidationError):
        repo.delete("victim", hard=True)
    assert root.exists()


def test_skill_delete_allows_in_repo_target(monkeypatch, tmp_path: Path):
    repo, root, outside, db = _repo_with(monkeypatch, tmp_path, "skills/victim")
    target = root / "skills" / "victim"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("x", encoding="utf-8")
    result = repo.delete("victim", hard=True)
    assert result["hard"] is True
    assert not target.exists()
    assert db.deleted == ["victim"]


# ---- P1-3：Shift 锚点失效 --------------------------------------------------


def test_invalidate_shift_anchor_resets():
    from mshub.native.ui import ShiftRangeCheckMixin

    class Host(ShiftRangeCheckMixin):
        pass

    host = Host()
    host._shift_anchor = 3
    host.invalidate_shift_anchor()
    assert host._shift_anchor == -1


# ---- 需求 A：自动检查更新配置 ----------------------------------------------


def test_auto_check_updates_default_and_roundtrip(tmp_path: Path):
    from mshub.config import ConfigStore

    assert AppConfig().auto_check_updates is True  # 默认开启
    store = ConfigStore(tmp_path / "cfg")
    store.save({"auto_check_updates": False})
    assert store.load().auto_check_updates is False


def test_settings_page_has_auto_check_toggle(qapp, tmp_path: Path):
    from mshub.config import ConfigStore
    from mshub.native.main_window import MainWindow
    from mshub.native.memory_facade import MemoryFacade

    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    window = MainWindow(MemoryFacade(store))
    try:
        page = window.settings_page
        assert page.auto_check.text() == "启动时自动检查更新"
        assert page.auto_check.isChecked() is True  # 默认开启
        page.auto_check.setChecked(False)
        assert page.facade.config().auto_check_updates is False  # 即时保存生效
    finally:
        window.close()


# ---- 需求 B/C：布局构件存在 -------------------------------------------------


def test_main_window_has_vertical_job_splitter_and_auto_check(qapp, tmp_path: Path):
    from PySide6.QtCore import QSettings, Qt, QTimer
    from PySide6.QtWidgets import QSplitter

    from mshub.config import ConfigStore
    from mshub.native.main_window import MainWindow
    from mshub.native.memory_facade import MemoryFacade

    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    window = MainWindow(MemoryFacade(store))
    try:
        # 需求 C：导航与任务面板组成垂直分隔条，两端都不可折叠
        splitter = window.job_splitter
        assert isinstance(splitter, QSplitter)
        assert splitter.orientation() == Qt.Orientation.Vertical
        assert not splitter.childrenCollapsible()
        assert splitter.count() == 2
        assert splitter.widget(0) is window.nav
        assert splitter.widget(1) is window.job_panel
        # 需求 B：安全中心按钮行横排——路线/批量/信任/刷新同一 QHBoxLayout
        security = window.security_page
        assert security.route.parentWidget() is not None
        # 需求 A：启动自动检查入口存在且遵循开关（源码运行短路返回，不实际联网）
        assert hasattr(window, "_startup_update_check")
        assert window.update_scope is not None
        window._startup_update_check()  # 源码模式：应直接返回、无网络请求
    finally:
        window.close()
