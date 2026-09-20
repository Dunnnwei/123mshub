from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

import yaml

from .models import ParsedSkill

SCRIPT_SUFFIXES = {
    ".py", ".ps1", ".sh", ".bat", ".cmd", ".js", ".mjs", ".cjs", ".ts",
    ".tsx", ".jsx", ".rb", ".php", ".pl", ".lua", ".exe", ".dll",
}
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".yaml", ".yml", ".json", ".toml"}
REFERENCE_DIRS = {"scripts", "references", "assets", "templates", "examples"}
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
INLINE_PATH_RE = re.compile(
    r"`((?:\./|\.\./)?(?:scripts|references|assets|templates|examples)/[^`\s]+)`",
    re.IGNORECASE,
)
PLAIN_DIR_RE = re.compile(
    r"(?<![\w.-])((?:scripts|references|assets|templates|examples)/)(?![\w.-])",
    re.IGNORECASE,
)
VERSION_RE = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.-]+)?\b")


# 程序库判定标志：出现这些工程文件且没有 SKILL.md，按应用程序收录
PROGRAM_MARKERS = (
    "package.json", "pyproject.toml", "setup.py", "requirements.txt", "Pipfile",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "CMakeLists.txt",
    "Makefile", "docker-compose.yml", "composer.json", "Gemfile", "*.sln",
)


def classify_repository(root: Path) -> dict[str, object]:
    """判定仓库是 Agent 技能还是应用程序，供入库时自动选库（技能库/程序库）。

    判定规则：根目录有 SKILL.md = 技能；没有但检测到工程标志 = 程序；
    根目录没有、子目录里有的（monorepo，如 anthropics/skills）默认按程序收录，
    同时列出技能子目录供用户指定后按技能安装。
    """
    if _find_case_insensitive(root, "SKILL.md"):
        return {
            "suggested_item_type": "skill",
            "suggestion_reason": "仓库根目录发现 SKILL.md",
            "skill_subdirs": [],
        }

    skill_subdirs: list[str] = []
    for path in root.rglob("*"):
        if len(skill_subdirs) >= 20:
            break
        if not path.is_file() or path.name.lower() != "skill.md":
            continue
        relative = path.relative_to(root)
        if ".git" in relative.parts or len(relative.parts) > 3:
            continue
        skill_subdirs.append(relative.parent.as_posix())

    markers = []
    root_files = [p for p in root.iterdir() if p.is_file()] if root.exists() else []
    for marker in PROGRAM_MARKERS:
        if marker.startswith("*"):
            if any(p.name.endswith(marker[1:]) for p in root_files):
                markers.append(marker)
        elif _find_case_insensitive(root, marker):
            markers.append(marker)
    if skill_subdirs:
        return {
            "suggested_item_type": "project",
            "suggestion_reason": (
                f"根目录无 SKILL.md，发现 {len(skill_subdirs)} 个技能子目录"
                "（可指定子目录改按技能安装）"
            ),
            "skill_subdirs": skill_subdirs,
            "program_markers": markers,
        }
    if markers:
        return {
            "suggested_item_type": "project",
            "suggestion_reason": f"未发现 SKILL.md，检测到工程标志 {markers[0]}",
            "skill_subdirs": [],
            "program_markers": markers,
        }
    return {
        "suggested_item_type": "project",
        "suggestion_reason": "未发现 SKILL.md 与工程标志，按程序收录（可手动改为技能）",
        "skill_subdirs": [],
        "program_markers": [],
    }


def parse_skill(root: Path, commit_hash: str = "", commit_date: str = "") -> ParsedSkill:
    skill_file = _find_case_insensitive(root, "SKILL.md")
    readme_file = _find_readme(root)
    source = skill_file or readme_file
    text = source.read_text(encoding="utf-8", errors="replace") if source else ""
    frontmatter, body = _split_frontmatter(text)

    description = _description(frontmatter, body)
    if not description and readme_file and readme_file != source:
        _, readme_body = _split_frontmatter(
            readme_file.read_text(encoding="utf-8", errors="replace")
        )
        description = _description({}, readme_body)
    description = description or "暂无说明"

    raw_version = str(frontmatter.get("version", "")).strip()
    if raw_version and VERSION_RE.search(raw_version):
        version = VERSION_RE.search(raw_version).group(0).lstrip("v")
    elif commit_hash:
        version = commit_hash[:12]
    else:
        version = commit_date or "unknown"

    all_files = [path for path in root.rglob("*") if path.is_file()]
    has_scripts = any(path.suffix.lower() in SCRIPT_SUFFIXES for path in all_files)
    license_name = _license_name(root)
    referenced, warnings = referenced_files(root, source)

    return ParsedSkill(
        description=description,
        version=version,
        has_scripts=has_scripts,
        license_name=license_name,
        skill_file=source.relative_to(root).as_posix() if source else "",
        referenced_files=referenced,
        warnings=warnings,
    )


def referenced_files(root: Path, source: Path | None) -> tuple[list[str], list[str]]:
    files: set[Path] = set()
    warnings: list[str] = []
    if source:
        files.add(source)
    readme = _find_readme(root)
    if readme:
        files.add(readme)
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        found = _find_case_insensitive(root, name)
        if found:
            files.add(found)

    if not source:
        warnings.append("未找到 SKILL.md 或 README，标准安装将保守包含整个目录。")
        return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()), warnings

    text = source.read_text(encoding="utf-8", errors="replace")
    candidates = [match.group(1) for match in MARKDOWN_LINK_RE.finditer(text)]
    candidates.extend(match.group(1) for match in INLINE_PATH_RE.finditer(text))
    candidates.extend(match.group(1) for match in PLAIN_DIR_RE.finditer(text))

    for candidate in candidates:
        clean = candidate.split("#", 1)[0].split("?", 1)[0].strip().strip("<>")
        if not clean or clean.startswith(("http://", "https://", "mailto:", "#")):
            continue
        clean = clean.replace("\\", "/")
        relative = PurePosixPath(clean)
        if relative.is_absolute() or ".." in relative.parts:
            warnings.append(f"忽略了仓库外引用：{candidate}")
            continue
        target = source.parent / Path(*relative.parts)
        if target.is_dir():
            files.update(path for path in target.rglob("*") if path.is_file())
        elif target.is_file():
            files.add(target)
            _expand_script_dependencies(root, target, files)
        else:
            warnings.append(f"引用未找到：{candidate}")

    for directory in REFERENCE_DIRS:
        if re.search(rf"\b{re.escape(directory)}(?:/|\s+目录)", text, re.IGNORECASE):
            candidate_dir = root / directory
            if candidate_dir.is_dir():
                files.update(path for path in candidate_dir.rglob("*") if path.is_file())

    return sorted(_relative_posix(path, root) for path in files), sorted(set(warnings))


def _expand_script_dependencies(root: Path, script: Path, files: set[Path]) -> None:
    if script.suffix.lower() not in {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
        return
    text = script.read_text(encoding="utf-8", errors="replace")
    patterns = [
        re.compile(r"""(?:from|require\()\s*['"](\.{1,2}/[^'"]+)['"]"""),
        re.compile(r"""import\s+[^'"]*['"](\.{1,2}/[^'"]+)['"]"""),
    ]
    for pattern in patterns:
        for match in pattern.finditer(text):
            base = Path(os.path.abspath(script.parent / match.group(1)))
            options = [base, *(base.with_suffix(suffix) for suffix in [".py", ".js", ".ts", ".json"])]
            options.extend([base / f"index{suffix}" for suffix in [".js", ".ts"]])
            for candidate in options:
                if not _is_within(candidate, root):
                    continue
                if candidate.is_file():
                    files.add(candidate)
                    break


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    return (data if isinstance(data, dict) else {}), match.group(2)


def _description(frontmatter: dict, body: str) -> str:
    for key in ("description", "summary", "about"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return _one_line(value)
    paragraphs: list[str] = []
    current: list[str] = []
    in_code = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or stripped.startswith(("#", "!", "<", "|", "---")):
            continue
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))
    return _one_line(paragraphs[0]) if paragraphs else ""


def _one_line(value: str) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    return clean[:237] + "…" if len(clean) > 240 else clean


def _find_case_insensitive(root: Path, name: str) -> Path | None:
    lowered = name.lower()
    for path in root.iterdir() if root.exists() else []:
        if path.is_file() and path.name.lower() == lowered:
            return path
    return None


def _find_readme(root: Path) -> Path | None:
    for candidate in ("README.md", "README.markdown", "README.txt", "README"):
        found = _find_case_insensitive(root, candidate)
        if found:
            return found
    return None


def _license_name(root: Path) -> str:
    for path in root.iterdir() if root.exists() else []:
        if path.is_file() and path.name.lower().startswith(("license", "copying")):
            return path.name
    return ""


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.normcase(os.path.commonpath([os.path.abspath(path), os.path.abspath(root)])) == (
            os.path.normcase(os.path.abspath(root))
        )
    except ValueError:
        return False


def _relative_posix(path: Path, root: Path) -> str:
    return os.path.relpath(path, root).replace("\\", "/")
