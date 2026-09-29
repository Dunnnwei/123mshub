"""v1.9.0：在线升级——从 GitHub Releases 拉取最新完整包并原地覆盖安装。

纯逻辑层（httpx + zipfile + shutil），不依赖 Qt；界面在 SettingsPage。
设计要点：

- 检查更新读 ``releases/latest``（GitHub 该端点自动排除 Pre-release 与草稿，
  正好符合"只推正式版"的发布惯例）；
- 下载走与技能抓取同一套镜像/代理/Token 配置（mirror_url 前缀拼接）；
- 覆盖安装：解压新包到临时目录，逐文件复制到安装目录。被锁文件
  （运行中的 exe、已加载的 DLL）先把旧文件改名为 ``*.mshub-old`` 再写入
  ——Windows 允许改名正在使用的可执行文件，这是无需外部 updater 的关键；
- ``.mshub-old`` 残留由下次启动的 :func:`cleanup_old` 清理；
- 配置在 ``%APPDATA%\\mshub``、仓库数据在用户自选目录，都不在安装目录内，
  升级天然保留，无需迁移逻辑。
"""
from __future__ import annotations

import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import httpx

from ..errors import FetchError

RELEASES_LATEST = "https://api.github.com/repos/Dunnnwei/123mshub/releases/latest"
DOWNLOAD_PAGE = "https://github.com/Dunnnwei/123mshub/releases"
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024  # 完整包上限 1GB（v1.9 约 170MB，留足余量）
OLD_SUFFIX = ".mshub-old"


def fetch_latest_release(proxy: str = "", token: str = "") -> dict[str, Any]:
    """读取最新正式版 Release；返回 tag/说明/资产列表（网络失败抛 FetchError）。"""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "mshub-updater"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    kwargs: dict[str, Any] = {"headers": headers, "timeout": 30, "follow_redirects": True}
    if proxy:
        kwargs["proxy"] = proxy
    try:
        response = httpx.get(RELEASES_LATEST, **kwargs)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FetchError(f"无法访问 GitHub Releases：{exc}") from exc
    assets = [
        {"name": str(asset.get("name") or ""), "url": str(asset.get("browser_download_url") or ""),
         "size": int(asset.get("size") or 0)}
        for asset in (data.get("assets") or [])
        if isinstance(asset, dict)
    ]
    return {
        "tag": str(data.get("tag_name") or ""),
        "name": str(data.get("name") or ""),
        "body": str(data.get("body") or ""),
        "url": str(data.get("html_url") or DOWNLOAD_PAGE),
        "assets": assets,
    }


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.9.0' / '1.10.1-rc1' → (1, 10, 1)；先截掉 -rc/-beta 后缀再取数字段。"""
    clean = str(text or "").strip().lstrip("vV")
    core = re.split(r"[-+]", clean, maxsplit=1)[0]
    digits = re.findall(r"\d+", core)
    return tuple(int(value) for value in digits[:4]) or (0,)


def is_newer(remote: str, local: str) -> bool:
    """远端版本号是否高于本地（右补零后逐位比较，(1,9) 与 (1,9,0) 视为相等）。"""
    left, right = parse_version(remote), parse_version(local)
    width = max(len(left), len(right))
    left = left + (0,) * (width - len(left))
    right = right + (0,) * (width - len(right))
    return left > right


def pick_asset(release: dict[str, Any]) -> dict[str, Any]:
    """从 Release 资产里挑完整包：优先 123mshub-native-*-win64.zip，其次最大 zip。"""
    assets = [asset for asset in release.get("assets") or [] if asset.get("url")]
    preferred = [asset for asset in assets
                 if "123mshub-native-" in asset.get("name", "") and asset.get("name", "").lower().endswith(".zip")]
    if preferred:
        return preferred[0]
    zips = [asset for asset in assets if asset.get("name", "").lower().endswith(".zip")]
    if zips:
        return max(zips, key=lambda asset: asset.get("size", 0))
    raise FetchError("最新 Release 里没有可用的 zip 资产。")


def download_asset(
    url: str,
    destination: Path,
    *,
    proxy: str = "",
    mirrors: list[str] | None = None,
    token: str = "",
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """流式下载升级包到 destination；镜像优先、直连兜底，各重试 2 次。"""
    from ..urltool import mirror_url

    candidates = [mirror_url(url, prefix) for prefix in (mirrors or [])] + [url]
    headers = {"User-Agent": "mshub-updater"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    client_args: dict[str, Any] = {"follow_redirects": True, "timeout": httpx.Timeout(30, read=300)}
    if proxy:
        client_args["proxy"] = proxy
    errors: list[str] = []
    with httpx.Client(**client_args) as client:
        for candidate in candidates:
            for attempt in range(1, 3):
                try:
                    with client.stream("GET", candidate, headers=headers) as response:
                        response.raise_for_status()
                        expected = int(response.headers.get("content-length") or 0)
                        if expected and expected > MAX_PACKAGE_BYTES:
                            raise FetchError("升级包超过 1GB 安全上限。")
                        done = 0
                        with destination.open("wb") as handle:
                            for chunk in response.iter_bytes(chunk_size=1024 * 256):
                                done += len(chunk)
                                if done > MAX_PACKAGE_BYTES:
                                    raise FetchError("升级包超过 1GB 安全上限。")
                                handle.write(chunk)
                                if progress:
                                    progress(done, expected)
                    return destination
                except (httpx.HTTPError, OSError, FetchError) as exc:
                    errors.append(f"{candidate}（第 {attempt} 次）: {exc}")
                    if destination.exists():
                        destination.unlink()
                    if attempt < 2:
                        time.sleep(0.5 * attempt)
    raise FetchError("所有镜像与直连地址均下载失败：" + "；".join(errors[-3:]))


def _extract_zip_safely(archive: Path, destination: Path) -> None:
    """逐成员解压并做路径安全检查（zip-slip / 绝对路径 / 盘符全拦）。"""
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if member.is_dir():
                continue
            parts = PurePosixPath(member.filename).parts
            if not parts or member.filename.startswith(("/", "\\")) or ".." in parts or ":" in parts[0]:
                raise FetchError("升级包包含不安全路径，已停止解压。")
            target = destination.joinpath(*parts)
            resolved = target.resolve()
            if not str(resolved).startswith(str(destination.resolve())):
                raise FetchError("升级包路径试图跳出目标目录。")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, resolved.open("wb") as output:
                shutil.copyfileobj(source, output)


def _copy_over(src: Path, dst: Path) -> bool:
    """覆盖单个文件；目标被锁（运行中 exe/已加载 DLL）时改名旧文件再写。

    返回是否走了"改名让位"路径（用于升级统计与提示）。
    """
    try:
        if dst.exists() and dst.stat().st_size == src.stat().st_size and dst.read_bytes() == src.read_bytes():
            return False
        shutil.copyfile(src, dst)
        return False
    except PermissionError:
        stale = dst.with_name(dst.name + OLD_SUFFIX)
        try:
            if stale.exists():
                stale.unlink()
            dst.rename(stale)
        except OSError as exc:
            raise FetchError(f"无法替换被占用的文件 {dst.name}：{exc}") from exc
        shutil.copyfile(src, dst)
        return True


def _payload_root(extracted: Path) -> Path:
    """定位包内程序目录：zip 顶层是 123mshub\\；单顶层目录时下钻一层。"""
    if (extracted / "123mshub.exe").is_file():
        return extracted
    children = [child for child in extracted.iterdir() if child.is_dir()]
    if len(children) == 1 and (children[0] / "123mshub.exe").is_file():
        return children[0]
    raise FetchError("升级包结构不符合预期（找不到 123mshub.exe）。")


def apply_upgrade(archive: Path, install_dir: Path, progress: Callable[[int, str], None] | None = None) -> dict[str, Any]:
    """解压完整包并覆盖安装目录；返回 {files, renamed} 统计。"""
    temp_root = Path(tempfile.mkdtemp(prefix="mshub-upgrade-apply-"))
    try:
        _extract_zip_safely(archive, temp_root)
        payload = _payload_root(temp_root)
        files = [path for path in payload.rglob("*") if path.is_file()]
        copied = renamed = 0
        for index, source in enumerate(files, start=1):
            relative = source.relative_to(payload)
            target = install_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if _copy_over(source, target):
                renamed += 1
            else:
                copied += 1
            if progress and (index % 10 == 0 or index == len(files)):
                progress(int(index * 100 / max(len(files), 1)), f"覆盖 {index}/{len(files)}")
        return {"files": len(files), "copied": copied, "renamed": renamed}
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def cleanup_old(install_dir: Path) -> int:
    """启动时清理上次升级留下的 ``*.mshub-old`` 残留；返回清理数量（失败忽略）。"""
    removed = 0
    try:
        for stale in install_dir.rglob(f"*{OLD_SUFFIX}"):
            try:
                stale.unlink()
                removed += 1
            except OSError:
                pass  # 仍被占用：下次启动再清
    except OSError:
        pass
    return removed
