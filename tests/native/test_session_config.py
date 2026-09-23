from pathlib import Path
import time

from mshub.config import ConfigStore
from mshub.native.session_config import SessionConfigStore
from mshub.native.app import show_duplicate_message


def test_session_override_preserves_config_bytes_and_unrelated_save(tmp_path):
    disk = ConfigStore(tmp_path / "config")
    disk.save({"repo_root": str(tmp_path / "real"), "ai_model": "original"})
    before = disk.path.read_bytes()
    session = SessionConfigStore(disk.config_dir, repo=str(tmp_path / "temporary"))
    assert session.require_repo_root() == tmp_path / "temporary"
    assert disk.path.read_bytes() == before
    session.save({"ai_model": "changed"})
    assert disk.load().repo_root == str(tmp_path / "real")
    assert session.load().repo_root == str(tmp_path / "temporary")
    session.save({"repo_root": str(tmp_path / "explicit")})
    assert session.load().repo_root == disk.load().repo_root == str(tmp_path / "explicit")


def test_isolated_session_never_reads_or_writes_os_keyring(tmp_path, _isolated_keyring):
    _isolated_keyring.set_password("mshub", "ai_key", "real-test-secret")
    session = SessionConfigStore(tmp_path, isolated=True)
    assert session.get_secret("ai_key") == ""
    session.save({"ai_key": "temporary-test-key"})
    session.save({"ai_key": ""})
    assert _isolated_keyring.get_password("mshub", "ai_key") == "real-test-secret"


def test_duplicate_dialog_exits_on_timer(qapp):
    start = time.monotonic()
    show_duplicate_message(timeout_ms=80)
    assert .04 <= time.monotonic() - start < 1.5
