from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlparse

from .errors import ValidationError
from .models import SourceSpec

_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def parse_source(value: str, *, ref: str | None = None, subdir: str | None = None) -> SourceSpec:
    raw = value.strip().rstrip("/")
    if not raw:
        raise ValidationError("请输入 GitHub 地址或“作者/仓库”。")

    if not raw.startswith(("http://", "https://")):
        parts = raw.split("/")
        if len(parts) != 2 or not all(_SLUG_RE.fullmatch(p) for p in parts):
            raise ValidationError("简写必须是“作者/仓库”，例如 anthropics/skills。")
        owner, repo = parts
        return SourceSpec(
            provider="github",
            owner=owner,
            repo=repo.removesuffix(".git"),
            source_url=f"https://github.com/{owner}/{repo.removesuffix('.git')}",
            ref=ref or "HEAD",
            subdir=_clean_subdir(subdir or ""),
        )

    parsed = urlparse(raw)
    host = parsed.hostname.lower() if parsed.hostname else ""
    if host not in {"github.com", "www.github.com"}:
        raise ValidationError("v0.1 目前支持 GitHub 地址；架构已为其他代码托管源预留扩展位。")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValidationError("GitHub 地址至少需要包含作者和仓库名。")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not _SLUG_RE.fullmatch(owner) or not _SLUG_RE.fullmatch(repo):
        raise ValidationError("GitHub 作者或仓库名包含不支持的字符。")

    url_ref = "HEAD"
    url_subdir = ""
    if len(parts) >= 4 and parts[2] == "tree":
        url_ref = parts[3]
        url_subdir = "/".join(parts[4:])

    return SourceSpec(
        provider="github",
        owner=owner,
        repo=repo,
        source_url=f"https://github.com/{owner}/{repo}",
        ref=ref or url_ref,
        subdir=_clean_subdir(subdir if subdir is not None else url_subdir),
    )


def _clean_subdir(value: str) -> str:
    if not value:
        return ""
    normalized = str(PurePosixPath(value.replace("\\", "/"))).strip("/")
    if normalized in {".", ""}:
        return ""
    if normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise ValidationError("子目录不能跳出仓库根目录。")
    return normalized


def safe_dir_name(owner: str, repo: str) -> str:
    """Create a stable Windows-safe directory name while keeping owner and repo visible."""
    raw = f"{owner}__{repo}"
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).rstrip(" .")
    if not cleaned:
        raise ValidationError("无法从仓库地址生成安全的目录名。")
    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def mirror_url(original: str, prefix: str) -> str:
    prefix = prefix.strip()
    if not prefix:
        return original
    if "{url}" in prefix:
        return prefix.replace("{url}", original)
    return f"{prefix.rstrip('/')}/{original}"

