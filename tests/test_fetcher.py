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

