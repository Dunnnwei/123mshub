from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from mshub.errors import FetchError
from mshub.fetcher import GitFetcher, _extract_tar_safely, cleanup_fetch
from mshub.models import SourceSpec


def test_tar_extraction_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    payload = b"escape"
    with tarfile.open(archive, "w:gz") as handle:
        member = tarfile.TarInfo("../outside.txt")
        member.size = len(payload)
        handle.addfile(member, io.BytesIO(payload))
    with pytest.raises(FetchError):
        _extract_tar_safely(archive, tmp_path / "out")


def test_tar_extraction_skips_symlinks_and_writes_files(tmp_path: Path) -> None:
    archive = tmp_path / "safe.tar.gz"
    payload = b"hello"
    with tarfile.open(archive, "w:gz") as handle:
        member = tarfile.TarInfo("repo/SKILL.md")
        member.size = len(payload)
        handle.addfile(member, io.BytesIO(payload))
        link = tarfile.TarInfo("repo/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../outside"
        handle.addfile(link)
    destination = tmp_path / "out"
    destination.mkdir()
    _extract_tar_safely(archive, destination)
    assert (destination / "repo" / "SKILL.md").read_bytes() == payload
    assert not (destination / "repo" / "link").exists()


def test_git_fetcher_uses_mirror_then_direct(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, *, env=None, timeout=180):
        calls.append(command)
        if "clone" in command:
            url = command[-2]
            checkout = Path(command[-1])
            if url.startswith("https://mirror/"):
                raise FetchError("mirror unavailable")
            checkout.mkdir(parents=True)
            (checkout / "SKILL.md").write_text("# ok", encoding="utf-8")
            return ""
        if "rev-parse" in command:
            return "a" * 40
        if "--format=%cI" in command:
            return "2026-07-25T00:00:00Z"
        return ""

    monkeypatch.setattr("mshub.fetcher.shutil.which", lambda _: "git")
    monkeypatch.setattr("mshub.fetcher._run", fake_run)
    source = SourceSpec(
        provider="github",
        owner="owner",
        repo="demo",
        source_url="https://github.com/owner/demo",
    )
    result = GitFetcher().fetch(
        source,
        mirrors=["https://mirror/"],
        proxy="",
        token="",
    )
    try:
        clone_urls = [command[-2] for command in calls if "clone" in command]
        assert clone_urls == [
            "https://mirror/https://github.com/owner/demo",
            "https://github.com/owner/demo",
        ]
        assert result.commit_hash == "a" * 40
    finally:
        cleanup_fetch(result)



def test_git_auth_header_builds_correct_basic_credentials() -> None:
    """v1.8.0（K3 审查跟进）：git 通道 Basic 认证头必须有单测盯住。

    git HTTP 只认 Basic（用户名:令牌），用户名惯例 x-access-token。这条路径
    曾在审查报告中被误报为 f-string 缺陷（实为报告脱敏伪影），但"该路径无
    测试"属实——补上后，任何人真改坏这一行都会立刻红灯。
    """
    import base64

    from mshub.fetcher import _git_auth_header

    token = "ghp_UnitTestProbe0001"
    header = _git_auth_header(token)
    expected = "AUTHORIZATION: basic " + base64.b64encode(
        f"x-access-token:{token}".encode("utf-8")
    ).decode("ascii")
    assert header == expected
    # 解码回读：凭据原文必须是 "用户名:完整令牌"，无省略/截断/多余字面量
    decoded = base64.b64decode(header.split("basic ", 1)[1]).decode("utf-8")
    assert decoded == f"x-access-token:{token}"
