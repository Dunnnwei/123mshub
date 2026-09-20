"""库布局：一个共享技能库 + 一个程序库（v0.7.0，用户裁决"平台不分仓库"）。

- skills = 共享技能库：所有 agent 平台的技能目录都 junction 指向这里，
  一个技能一份文件一条记录，更新一次全体平台立即生效；
- github = 程序库：GitHub 上的安装程序/应用程序仓（playwright、poppler 这类
  非 SKILL.md 的工具仓），不挂载给任何 agent，但技能可通过路径/提示词引用；
- zcode-skills / workbuddy-skills = 历史分区，仅用于识别与合并迁移，
  不再接受新入库（consolidate_libraries 会把它们并入 skills）。

加新平台（如 Hermes）= 每台机器一条 mklink 指向 skills，仓库零改动。
"""
from __future__ import annotations

from pathlib import Path

LIBRARY_GITHUB = "github"
LIBRARY_DSH = "skills"
LEGACY_ZCODE = "zcode-skills"
LEGACY_WORKBUDDY = "workbuddy-skills"

SKILL_LIBRARY = LIBRARY_DSH
PROGRAM_LIBRARY = LIBRARY_GITHUB

# 布局检测 / 恢复扫描认识的全部库名（含历史分区）
LIBRARIES = (LIBRARY_GITHUB, LIBRARY_DSH, LEGACY_ZCODE, LEGACY_WORKBUDDY)
# 新入库仅接受这两个
ACTIVE_LIBRARIES = (LIBRARY_GITHUB, LIBRARY_DSH)
LEGACY_LIBRARIES = (LEGACY_ZCODE, LEGACY_WORKBUDDY)

LIBRARY_LABELS = {
    LIBRARY_GITHUB: "程序库（本地程序仓，不挂载给 agent）",
    LIBRARY_DSH: "共享技能库（所有平台共用）",
    LEGACY_ZCODE: "ZCode 旧分区（待合并）",
    LEGACY_WORKBUDDY: "WorkBuddy 旧分区（待合并）",
}

# 兼容恢复逻辑的历史引用：这三个库按"技能库"规则收录（含 SKILL.md 目录可作本地技能）
AGENT_LIBRARIES = (LIBRARY_DSH, LEGACY_ZCODE, LEGACY_WORKBUDDY)

# 检测布局时忽略的根级目录名
ROOT_RESERVED = {".meta", "index.json"}

# 合并去重时的库优先级（同分时谁留下）：已在共享库的优先（免搬动）
LIBRARY_MERGE_PRIORITY = {LIBRARY_DSH: 0, LEGACY_ZCODE: 1, LEGACY_WORKBUDDY: 2}


def is_library_name(value: str) -> bool:
    return value in LIBRARIES


def repo_uses_libraries(root: Path) -> bool:
    """根下存在任一库目录即视为多库布局。"""
    return any((root / name).is_dir() for name in LIBRARIES)


def resolve_library(root: Path, library: str | None, *, item_type: str = "skill") -> str:
    """归一化入库库：技能默认进共享技能库，应用程序项目默认进程序库。"""
    if library in (None, ""):
        if repo_uses_libraries(root):
            return PROGRAM_LIBRARY if item_type == "project" else SKILL_LIBRARY
        return ""
    if library in LEGACY_LIBRARIES:
        raise ValueError(
            f"{library} 是已合并的历史分区，请选择共享技能库（skills）或程序库（github）。"
        )
    if not is_library_name(library):
        raise ValueError(f"未知的技能库：{library}")
    return library


def library_root(root: Path, library: str) -> Path:
    if library:
        return root / library
    return root


def candidate_skill_dirs(repo_root: Path) -> list[str]:
    """列出待恢复扫描的技能目录（相对根的 posix 路径）。

    多库布局：各库下的一级子目录；flat 布局：根下的一级子目录。
    """
    if not repo_root.exists():
        return []
    if repo_uses_libraries(repo_root):
        result: list[str] = []
        for name in LIBRARIES:
            base = repo_root / name
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    result.append(child.relative_to(repo_root).as_posix())
        return result
    return [
        path.relative_to(repo_root).as_posix()
        for path in sorted(repo_root.iterdir())
        if path.is_dir() and not path.name.startswith(".") and path.name not in ROOT_RESERVED
    ]
