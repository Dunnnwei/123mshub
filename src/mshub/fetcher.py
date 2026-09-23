from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Callable

import httpx

from .errors import FetchError, ValidationError
from .models import FetchResult, SourceSpec
from .process import hidden_windows_kwargs
from .urltool import mirror_url

MAX_ARCHIVE_BYTES = 750 * 1024 * 1024

_PROXY_ENV_VARS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


def _git_env(proxy: str) -> dict[str, str]:
    """应用代理设置是唯一权威：清掉进程继承来的所有代理环境变量（含失效的本机代理），
    再按配置注入。避免用户 shell / 其他机器上残留的 127.0.0.1 之类死代理劫持 git。"""
    env = os.environ.copy()
    for var in _PROXY_ENV_VARS:
        env.pop(var, None)
    if proxy:
        env["HTTPS_PROXY"] = proxy
        env["HTTP_PROXY"] = proxy
    return env


def _git_proxy_args(proxy: str) -> list[str]:
    """git -c 级代理钉死：空值显式禁用（覆盖任何 gitconfig 里的代理）。"""
    return ["-c", f"http.proxy={proxy}", "-c", f"https.proxy={proxy}"]


def _git_auth_header(token: str) -> str:
    """GitHub 的 git HTTP 通道只认 Basic 格式（用户名:令牌）。

    Bearer 会被 git 端点拒绝（invalid credentials）——2026-09-10 公司分机实测确证：
    同一枚令牌 Bearer 失败、Basic 立即 200。用户名用惯例 x-access-token。
    注意：api.github.com 的 REST 端点两者皆可，ArchiveFetcher 的 Bearer 不用改。
    """
    raw = f"x-access-token:{token}".encode("utf-8")
    return "AUTHORIZATION: basic " + base64.b64encode(raw).decode("ascii")


class Fetcher(ABC):
    name: str

    @abstractmethod
    def fetch(
        self,
        source: SourceSpec,
        *,
        mirrors: list[str],
        proxy: str,
        token: str,
        progress: Callable[[int, int], None] | None = None,
    ) -> FetchResult:
        raise NotImplementedError


class ArchiveFetcher(Fetcher):
    name = "archive"

    def fetch(
        self,
        source: SourceSpec,
        *,
        mirrors: list[str],
        proxy: str,
        token: str,
        progress: Callable[[int, int], None] | None = None,
    ) -> FetchResult:
        temp_root = Path(tempfile.mkdtemp(prefix="mshub-archive-"))
        archive_path = temp_root / "repo.tar.gz"
        extracted = temp_root / "extracted"
        extracted.mkdir()
        ref = source.ref or "HEAD"
        if ref == "HEAD":
            # codeload does not accept the symbolic HEAD ref. GitHub's tarball
            # endpoint resolves the repository's current default branch and
            # redirects to the corresponding codeload archive.
            direct = f"https://api.github.com/repos/{source.owner}/{source.repo}/tarball"
        else:
            direct = f"https://codeload.github.com/{source.owner}/{source.repo}/tar.gz/{ref}"
        urls = [mirror_url(direct, prefix) for prefix in mirrors] + [direct]
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "mshub/0.1"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        errors: list[str] = []
        client_args = {"follow_redirects": True, "timeout": httpx.Timeout(30, read=180)}
        if proxy:
            client_args["proxy"] = proxy
        response_headers: dict[str, str] = {}
        try:
            with httpx.Client(**client_args) as client:
                downloaded = False
                for url in urls:
                    for attempt in range(1, 4):
                        try:
                            with client.stream("GET", url, headers=headers) as response:
                                response.raise_for_status()
                                response_headers = dict(response.headers)
                                total = 0
                                expected = int(response.headers.get("content-length") or 0)
                                with archive_path.open("wb") as handle:
                                    for chunk in response.iter_bytes():
                                        total += len(chunk)
                                        if total > MAX_ARCHIVE_BYTES:
                                            raise FetchError(
                                                "仓库压缩包超过 750MB 安全上限，请改用 Git 拉取。"
                                            )
                                        handle.write(chunk)
                                        if progress:
                                            progress(total, expected)
                            downloaded = True
                            break
                        except (httpx.HTTPError, OSError, FetchError) as exc:
                            errors.append(f"{url}（第 {attempt} 次）: {exc}")
                            if archive_path.exists():
                                archive_path.unlink()
                            if attempt < 3:
                                time.sleep(0.25 * attempt)
                    if downloaded:
                        break
                if not downloaded:
                    raise FetchError("所有镜像与直连地址均下载失败：" + "；".join(errors[-3:]))

            _extract_tar_safely(archive_path, extracted)
            children = [item for item in extracted.iterdir() if item.is_dir()]
            repository_root = children[0] if len(children) == 1 else extracted
            selected = repository_root
            if source.subdir:
                selected = repository_root / Path(*PurePosixPath(source.subdir).parts)
                if not selected.is_dir():
                    raise FetchError(f"仓库中不存在子目录：{source.subdir}")

            try:
                commit_hash, commit_date = remote_version(
                    source, proxy=proxy, token=token, allow_api=True
                )
            except FetchError:
                # A mirror may allow archive downloads while git/API endpoints remain blocked.
                # Installation must still succeed with a date fallback.
                commit_hash = ""
                commit_date = response_headers.get("last-modified") or datetime.now(UTC).isoformat()
            return FetchResult(
                root=selected,
                commit_hash=commit_hash,
                commit_date=commit_date,
                ref=ref,
                fetcher=self.name,
                temp_root=temp_root,
            )
        except Exception:
            shutil.rmtree(temp_root, ignore_errors=True)
            raise


class GitFetcher(Fetcher):
    name = "git"

    def fetch(
        self,
        source: SourceSpec,
        *,
        mirrors: list[str],
        proxy: str,
        token: str,
        progress: Callable[[int, int], None] | None = None,
    ) -> FetchResult:
        if not shutil.which("git"):
            raise FetchError("未找到 Git，请改用默认的 Archive 下载方式。")
        temp_root = Path(tempfile.mkdtemp(prefix="mshub-git-"))
        checkout = temp_root / "checkout"
        ref_args = [] if source.ref in {"", "HEAD"} else ["--branch", source.ref]
        command_prefix = [
            "git", "-c", "core.quotepath=false", *_git_proxy_args(proxy),
            "clone", "--depth", "1",
            "--filter=blob:none", *ref_args,
        ]
        if source.subdir:
            command_prefix.append("--sparse")
        env = _git_env(proxy)
        if token:
            env["GIT_CONFIG_COUNT"] = "1"
            env["GIT_CONFIG_KEY_0"] = "http.extraheader"
            env["GIT_CONFIG_VALUE_0"] = _git_auth_header(token)
        try:
            clone_urls = [mirror_url(source.source_url, prefix) for prefix in mirrors]
            clone_urls.append(source.source_url)
            if progress:
                progress(0, 0)
            clone_errors: list[str] = []
            for clone_url in clone_urls:
                if checkout.exists():
                    shutil.rmtree(checkout, ignore_errors=True)
                try:
                    _run([*command_prefix, clone_url, str(checkout)], env=env)
                    break
                except FetchError as exc:
                    clone_errors.append(f"{clone_url}: {exc}")
            else:
                raise FetchError("所有镜像与直连 Git 地址均拉取失败：" + "；".join(clone_errors[-3:]))
            if source.subdir:
                _run(
                    ["git", "-C", str(checkout), "sparse-checkout", "set", "--", source.subdir],
                    env=env,
                )
            commit_hash = _run(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"], env=env
            ).strip()
            commit_date = _run(
                ["git", "-C", str(checkout), "show", "-s", "--format=%cI", "HEAD"], env=env
            ).strip()
            selected = checkout / Path(*PurePosixPath(source.subdir).parts) if source.subdir else checkout
            if not selected.is_dir():
                raise FetchError(f"仓库中不存在子目录：{source.subdir}")
            return FetchResult(
                root=selected,
                commit_hash=commit_hash,
                commit_date=commit_date,
                ref=source.ref or "HEAD",
                fetcher=self.name,
                temp_root=temp_root,
            )
        except Exception:
            shutil.rmtree(temp_root, ignore_errors=True)
            raise


def get_fetcher(name: str) -> Fetcher:
    if name == "git":
        return GitFetcher()
    if name == "archive":
        return ArchiveFetcher()
    raise ValidationError(f"不支持的下载方式：{name}")


def remote_version(
    source: SourceSpec,
    *,
    proxy: str = "",
    token: str = "",
    allow_api: bool = True,
) -> tuple[str, str]:
    """Return commit hash and ISO commit date without downloading repository content."""
    if shutil.which("git"):
        env = _git_env(proxy)
        if token:
            env["GIT_CONFIG_COUNT"] = "1"
            env["GIT_CONFIG_KEY_0"] = "http.extraheader"
            env["GIT_CONFIG_VALUE_0"] = _git_auth_header(token)
        ref = "HEAD" if source.ref in {"", "HEAD"} else f"refs/heads/{source.ref}"
        try:
            output = _run(
                ["git", *_git_proxy_args(proxy), "ls-remote", source.source_url, ref],
                env=env,
                timeout=45,
            )
            line = next((item for item in output.splitlines() if item.strip()), "")
            if line:
                return line.split()[0], ""
        except FetchError:
            if not allow_api:
                raise

    if not allow_api:
        raise FetchError("无法查询远端版本。")
    endpoint = f"https://api.github.com/repos/{source.owner}/{source.repo}/commits/{source.ref or 'HEAD'}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "mshub/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    kwargs = {"headers": headers, "timeout": 30, "follow_redirects": True}
    if proxy:
        kwargs["proxy"] = proxy
    try:
        response = httpx.get(endpoint, **kwargs)
        response.raise_for_status()
        data = response.json()
        date = data.get("commit", {}).get("committer", {}).get("date", "")
        return data.get("sha", ""), date
    except (httpx.HTTPError, ValueError) as exc:
        raise FetchError(f"版本查询失败：{exc}") from exc


def _extract_tar_safely(archive: Path, destination: Path) -> None:
    try:
        with tarfile.open(archive, "r:gz") as handle:
            for member in handle:
                if member.issym() or member.islnk():
                    continue
                parts = PurePosixPath(member.name).parts
                if not parts or member.name.startswith("/") or ".." in parts:
                    raise FetchError("压缩包包含不安全路径，已停止解压。")
                target = destination.joinpath(*parts)
                resolved = target.resolve()
                try:
                    resolved.relative_to(destination.resolve())
                except ValueError as exc:
                    raise FetchError("压缩包路径试图跳出目标目录。") from exc
                if member.isdir():
                    resolved.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    continue
                resolved.parent.mkdir(parents=True, exist_ok=True)
                source = handle.extractfile(member)
                if source:
                    with source, resolved.open("wb") as output:
                        shutil.copyfileobj(source, output)
    except (tarfile.TarError, OSError) as exc:
        raise FetchError(f"压缩包解压失败：{exc}") from exc


def _run(command: list[str], *, env: dict | None = None, timeout: int = 180) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            check=False,
            **hidden_windows_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FetchError(f"命令执行失败：{exc}") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise FetchError(message or f"命令退出码 {result.returncode}")
    return result.stdout


def cleanup_fetch(result: FetchResult | None) -> None:
    if result:
        shutil.rmtree(result.temp_root, ignore_errors=True)
