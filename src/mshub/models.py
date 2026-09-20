from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class InstallMode(StrEnum):
    STANDARD = "standard"
    FULL = "full"


class SecurityStatus(StrEnum):
    UNCHECKED = "unchecked"
    SAFE = "safe"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class SourceSpec:
    provider: str
    owner: str
    repo: str
    source_url: str
    ref: str = "HEAD"
    subdir: str = ""

    @property
    def name(self) -> str:
        # monorepo 子目录技能（如 anthropics/skills 的 skills/docx）必须以
        # 完整路径为唯一名，否则同仓库多个子技能会互相覆盖。
        base = f"{self.owner}/{self.repo}"
        return f"{base}/{self.subdir}" if self.subdir else base


@dataclass(slots=True)
class FetchResult:
    root: Path
    commit_hash: str
    commit_date: str
    ref: str
    fetcher: str
    temp_root: Path


@dataclass(slots=True)
class ParsedSkill:
    description: str
    version: str
    has_scripts: bool
    license_name: str
    skill_file: str
    referenced_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScanFinding:
    severity: str
    category: str
    file: str
    line: int
    rule: str
    excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScanReport:
    status: SecurityStatus
    route: str
    scanned_files: int
    findings: list[ScanFinding]
    summary: str
    scanned_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

