from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from mshub.config import ConfigStore


@pytest.fixture(autouse=True)
def _isolated_keyring():
    """隔离系统钥匙串：测试里的凭据读写一律走内存副本。

    ConfigStore.get/set_secret 会直接读写 OS 钥匙串（Windows 凭据管理器），
    不隔离的话测试会读到本机真实凭据（断言随机器漂移），
    更严重的是 set_secret 会把真实保存的 GitHub 令牌 / AI key 覆盖掉。
    keyring 是惰性导入的可选依赖，sys.modules 里可能没有该键，
    因此不走 monkeypatch.setitem（要求键已存在），直接换装并在结束后恢复。
    """
    secrets: dict[tuple[str, str], str] = {}

    class _FakeKeyring:
        @staticmethod
        def get_password(service: str, name: str) -> str | None:
            return secrets.get((service, name))

        @staticmethod
        def set_password(service: str, name: str, value: str) -> None:
            secrets[(service, name)] = value

        @staticmethod
        def delete_password(service: str, name: str) -> None:
            secrets.pop((service, name), None)

    saved = sys.modules.get("keyring")
    sys.modules["keyring"] = _FakeKeyring
    yield _FakeKeyring
    if saved is None:
        sys.modules.pop("keyring", None)
    else:
        sys.modules["keyring"] = saved


@pytest.fixture()
def config_store(tmp_path: Path) -> ConfigStore:
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "skills-repo")})
    return store


class FakeFetcher:
    name = "archive"

    def __init__(self) -> None:
        self.revision = 1

    def fetch(self, source, *, mirrors, proxy, token, progress=None):
        from mshub.models import FetchResult

        temp_root = Path(tempfile.mkdtemp(prefix="mshub-test-"))
        root = temp_root / "repo"
        (root / "scripts").mkdir(parents=True)
        (root / "assets").mkdir()
        (root / "SKILL.md").write_text(
            "---\n"
            "name: demo-skill\n"
            f"version: 1.{self.revision}.0\n"
            "description: 用于测试中文技能解析与仓库生命周期。\n"
            "---\n\n"
            "运行 `scripts/run.py` 完成任务。\n",
            encoding="utf-8",
        )
        (root / "scripts" / "run.py").write_text(
            f"print('revision-{self.revision}')\n", encoding="utf-8"
        )
        (root / "assets" / "large.txt").write_text("full-only", encoding="utf-8")
        (root / "README.md").write_text("# Demo\n\nFallback description.\n", encoding="utf-8")
        (root / "LICENSE").write_text("MIT", encoding="utf-8")
        return FetchResult(
            root=root,
            commit_hash=f"{self.revision:040x}",
            commit_date=f"2026-07-{20 + self.revision:02d}T00:00:00Z",
            ref=source.ref,
            fetcher=self.name,
            temp_root=temp_root,
        )


@pytest.fixture()
def fake_fetcher() -> FakeFetcher:
    return FakeFetcher()

