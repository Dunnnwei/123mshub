"""整理与日报（tidy）服务：记忆 + 技能的归纳盘点，值守/手动两条路。

路线（需求补充 2026-09-20）：
- 手动「归纳整理」：程序本地确定性盘点（事实数字由程序计算，不会错），
  若设置里配置了「AI 接口」则再调用该 LLM 生成分析与建议，合成日报落盘；
- 值守 agent：复制「值守整理提示词」交给外部 agent（如 NAS 总机）部署，
  由 agent 周期整理并按同一模板写日报。

日报只报记忆与技能，不含其他内容。报告文件 = memory\\reports\\YYYY-MM-DD-HHMMSS.md，
文件名 ASCII、按时间自然排序。
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from .config import ConfigStore
from .database import Database
from .errors import NotFoundError, ValidationError
from .fsretry import robust_replace
from .memory import INDEX_NAME, extract_links
from .memory_service import MemoryService
from .prompts import build_duty_prompt

REPORTS_DIRNAME = "reports"
INDEX_WARN_LINES = 150
INDEX_WARN_BYTES = 20 * 1024


class TidyService:
    def __init__(self, config_store: ConfigStore | None = None) -> None:
        self.config_store = config_store or ConfigStore()
        self.memory = MemoryService(self.config_store)

    # -------------------------------------------------------------- 盘点

    def gather_state(self) -> dict[str, Any]:
        """收集记忆 + 技能的确定性盘点数据（全部由本地计算，不依赖 AI）。"""
        memory_stats = self.memory.stats()
        entries_detail = self.memory.list_entries(sort="updated")
        entries = entries_detail["items"]

        # 疑似重复：标题归一化后相同（保守规则，宁可漏报不误报洪水）
        seen_titles: dict[str, str] = {}
        duplicates: list[list[str]] = []
        for entry in entries:
            key = re.sub(r"[\s，。：:；;！!？?\-_/\\]+", "", str(entry["title"])).casefold()
            if not key:
                continue
            if key in seen_titles:
                duplicates.append([seen_titles[key], entry["name"]])
            else:
                seen_titles[key] = entry["name"]

        missing_description = [entry["name"] for entry in entries if not str(entry["description"] or "").strip()]

        # 失效双链与空正文都要读文件（列表项不含 body；notes 文件才是事实源）
        notes_dir = self.memory.memory_root() / "notes"
        known = {entry["name"] for entry in entries}
        broken_links: list[str] = []
        empty_body: list[str] = []
        for entry in entries:
            path = notes_dir / f"{entry['name']}.md"
            if not path.is_file():
                continue
            body = path.read_text(encoding="utf-8", errors="replace")
            if not body.strip():
                empty_body.append(entry["name"])
            for target in extract_links(body):
                if target not in known:
                    broken_links.append(f"{entry['name']} → [[{target}]]")

        # 技能侧：只读 SQLite 权威视图，不做联网检查
        skills: list[dict[str, Any]] = []
        repo_root = ""
        config = self.config_store.load()
        if config.repo_root:
            repo_root = config.repo_root
            from .database import Database

            skills = Database(Path(repo_root)).list_skills()

        skills_summary = {
            "total": len(skills),
            "github": sum(1 for item in skills if item.get("provider") == "github"),
            "local": sum(1 for item in skills if item.get("provider") == "local"),
            "projects": sum(1 for item in skills if item.get("item_type") == "project"),
            "unchecked": sum(1 for item in skills if item.get("security_status") == "unchecked"),
            "warning": sum(1 for item in skills if item.get("security_status") == "warning"),
            "safe": sum(1 for item in skills if item.get("security_status") == "safe"),
            "untagged": sum(1 for item in skills if not (item.get("tags") or [])),
        }

        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "memory_root": memory_stats["memory_root"],
            "repo_root": repo_root,
            "memory": {
                "total": memory_stats["total"],
                "types": memory_stats["types"],
                "this_week": memory_stats["this_week"],
                "inbox_pending": memory_stats["inbox_pending"],
                "index_lines": memory_stats["index_lines"],
                "index_bytes": memory_stats["index_bytes"],
                "index_warn": memory_stats["index_warn"],
                "duplicates": duplicates,
                "missing_description": missing_description,
                "empty_body": empty_body,
                "broken_links": broken_links,
            },
            "memory_entries_brief": [
                {
                    "name": entry["name"],
                    "title": entry["title"],
                    "type": entry["type"],
                    "tags": entry["tags"],
                    "description": str(entry["description"] or "")[:80],
                    "updated": entry["updated"],
                }
                for entry in entries
            ][:200],
            "skills": skills_summary,
            "skills_brief": [
                {
                    "name": item["name"],
                    "provider": item.get("provider", "github"),
                    "item_type": item.get("item_type", "skill"),
                    "security_status": item.get("security_status", "unchecked"),
                    "tags": item.get("tags") or [],
                }
                for item in skills
            ][:200],
        }

    def deterministic_suggestions(self, state: dict[str, Any]) -> list[str]:
        """从盘点数据推导的确定性建议（无 AI 也能给）。"""
        memory = state["memory"]
        skills = state["skills"]
        suggestions: list[str] = []
        if memory["inbox_pending"]:
            suggestions.append(f"有 {memory['inbox_pending']} 条投递待收编，先到收编视图审核。")
        if memory["duplicates"]:
            pairs = "；".join(" 与 ".join(pair) for pair in memory["duplicates"][:5])
            suggestions.append(f"疑似重复条目 {len(memory['duplicates'])} 组（{pairs}），建议合并保留更完整的一条。")
        if memory["missing_description"]:
            suggestions.append(
                f"{len(memory['missing_description'])} 条记忆缺一句话描述，影响索引可读性，可用「AI 生成描述」补齐。"
            )
        if memory["empty_body"]:
            suggestions.append(f"{len(memory['empty_body'])} 条记忆正文为空，考虑补内容或删除。")
        if memory["broken_links"]:
            suggestions.append(f"失效双链 {len(memory['broken_links'])} 处，指向的条目未创建，建议补建或修正引用。")
        if memory["index_warn"]:
            suggestions.append(
                f"索引规模 {memory['index_lines']} 行 / {memory['index_bytes'] // 1024} KB 已超健康线"
                f"（{INDEX_WARN_LINES} 行 / {INDEX_WARN_BYTES // 1024} KB），部分 agent 只加载前 200 行，建议精简。"
            )
        if skills["unchecked"]:
            suggestions.append(f"{skills['unchecked']} 个技能尚未做安全检查，建议批量跑离线检查。")
        if skills["warning"]:
            suggestions.append(f"{skills['warning']} 个技能处于「需要确认」状态，到安全中心复核。")
        if skills["untagged"]:
            suggestions.append(f"{skills['untagged']} 个技能没有标签，检索效率会打折。")
        if not suggestions:
            suggestions.append("记忆与技能状态良好，没有需要立即处理的事项。")
        return suggestions

    # ----------------------------------------------------------- AI 分析

    def ai_analysis(self, state: dict[str, Any]) -> str:
        """调用统一 AI 接口（设置里的「AI 接口」，与安全检查 B 线路共用）做分析。"""
        config = self.config_store.load()
        api_key = self.config_store.get_secret("ai_key")
        if not config.ai_base_url or not api_key:
            raise ValidationError("AI 分析需要先在设置中填写「AI 接口」的地址与 Key（未配置时整理仍可用，只是没有 AI 分析段）。")
        import json as _json

        brief = {
            "memory": state["memory"],
            "memory_entries": state["memory_entries_brief"],
            "skills": state["skills"],
            "skills_brief": state["skills_brief"],
        }
        prompt = (
            "你是 123 MSHub 的记忆与技能库整理员。下面是程序盘点出的库状态（JSON，数字是权威的，不要自行更改）。"
            "请写一段简短的「整理分析与建议」markdown（不超过 12 行），内容仅限记忆与技能：\n"
            "1. 一两句话总体评价；\n2. 指出最值得处理的 2-4 件事并说明理由（可引用盘点里的具体条目名）；\n"
            "3. 不要罗列全部数字（报告前半已有统计），不要建议清单之外的系统操作。\n"
            "只输出 markdown 正文，不要代码围栏。\n\n" + _json.dumps(brief, ensure_ascii=False)
        )
        endpoint = f"{config.ai_base_url.rstrip('/')}/chat/completions"
        request_body: dict[str, Any] = {
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
        if config.ai_model:
            request_body["model"] = config.ai_model
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            response = httpx.post(endpoint, headers=headers, json=request_body, timeout=90)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise ValidationError(f"AI 分析请求失败：{exc}") from exc
        except ValueError as exc:
            raise ValidationError("AI 网关返回的内容不是有效 JSON。") from exc
        try:
            content = str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("AI 没有返回可用的分析内容。") from exc
        content = re.sub(r"^```(?:markdown|md)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        if not content:
            raise ValidationError("AI 没有返回可用的分析内容。")
        return content

    # --------------------------------------------------------------- 日报

    def build_report(self, state: dict[str, Any], ai_section: str = "") -> str:
        memory = state["memory"]
        skills = state["skills"]
        types = memory["types"]
        lines = [
            f"# 整理日报 · {state['generated_at']}",
            "",
            "> 由 123 MSHub 生成；内容仅限记忆与技能的汇报信息。",
            "",
            "## 记忆",
            f"- 总条数 **{memory['total']}**"
            f"（user {types.get('user', 0)} / project {types.get('project', 0)}"
            f" / reference {types.get('reference', 0)} / feedback {types.get('feedback', 0)}）",
            f"- 本周新增 {memory['this_week']}；待收编投递 {memory['inbox_pending']}",
            f"- 疑似重复 {len(memory['duplicates'])} 组；缺描述 {len(memory['missing_description'])} 条；"
            f"空正文 {len(memory['empty_body'])} 条；失效双链 {len(memory['broken_links'])} 处",
            f"- 索引规模 {memory['index_lines']} 行 / {memory['index_bytes'] / 1024:.1f} KB"
            + ("（超出健康线，建议精简）" if memory["index_warn"] else "（健康）"),
            "",
            "## 技能",
            f"- 总数 **{skills['total']}**（GitHub 源 {skills['github']} / 本地自研 {skills['local']}；"
            f"其中程序库项目 {skills['projects']}）",
            f"- 安全状态：通过 {skills['safe']} / 需确认 {skills['warning']} / 未检查 {skills['unchecked']}",
            f"- 未打标签 {skills['untagged']} 个",
            "",
        ]
        if memory["duplicates"]:
            lines.append("### 疑似重复明细")
            for pair in memory["duplicates"][:10]:
                lines.append(f"- {' 与 '.join(pair)}")
            lines.append("")
        if memory["broken_links"]:
            lines.append("### 失效双链明细")
            for item in memory["broken_links"][:10]:
                lines.append(f"- {item}")
            lines.append("")
        if ai_section:
            lines.append("## 整理分析与建议（AI）")
            lines.append(ai_section)
            lines.append("")
        lines.append("## 建议（程序盘点）")
        for suggestion in self.deterministic_suggestions(state):
            lines.append(f"- {suggestion}")
        lines.append("")
        return "\n".join(lines)

    def run_tidy(self, *, use_ai: bool = True) -> dict[str, Any]:
        """手动归纳整理：盘点 →（可选）AI 分析 → 写日报 → 返回。"""
        state = self.gather_state()
        ai_section = ""
        ai_error = ""
        if use_ai:
            try:
                ai_section = self.ai_analysis(state)
            except ValidationError as exc:
                ai_error = str(exc)
        content = self.build_report(state, ai_section)
        report = self._write_report(content)
        return {**report, "has_ai": bool(ai_section), "ai_error": ai_error, "state_totals": {
            "memory": state["memory"]["total"],
            "skills": state["skills"]["total"],
        }}

    def _reports_dir(self) -> Path:
        directory = self.memory.memory_root() / REPORTS_DIRNAME
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _write_report(self, content: str) -> dict[str, Any]:
        directory = self._reports_dir()
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        target = directory / f"{stamp}.md"
        temp = directory / f".{target.name}.tmp"
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        robust_replace(temp, target)
        return {"file": target.name, "date": stamp, "content": content}

    def list_reports(self) -> dict[str, Any]:
        directory = self._reports_dir()
        items = []
        for child in sorted(directory.iterdir(), reverse=True):
            if not child.is_file() or child.suffix.lower() != ".md" or child.name.startswith("."):
                continue
            if "冲突副本" in child.name or "conflict" in child.name.lower():
                continue
            first_line = ""
            try:
                first_line = child.read_text(encoding="utf-8", errors="replace").splitlines()[0]
            except (OSError, IndexError):
                pass
            items.append({
                "file": child.name,
                "title": first_line.lstrip("# ").strip() or child.name,
                "size": child.stat().st_size,
            })
        return {"items": items}

    def read_report(self, file_name: str) -> dict[str, Any]:
        text = str(file_name or "").strip()
        if not text or text != Path(text).name or text.startswith(".") or "/" in text or "\\" in text:
            raise ValidationError(f"非法的日报文件名：{file_name}")
        path = self._reports_dir() / text
        if not path.is_file():
            raise NotFoundError(f"日报不存在：{text}")
        return {"file": text, "content": path.read_text(encoding="utf-8", errors="replace")}

    def duty_prompt(self) -> str:
        root = Path(self.config_store.load().repo_root or "")
        skill_count = len(Database(root).list_skills()) if str(root) else 0
        return build_duty_prompt(
            repo_root=root,
            memory_root=self.memory.memory_root(),
            memory_count=self.memory.stats()["total"],
            skill_count=skill_count,
        )
