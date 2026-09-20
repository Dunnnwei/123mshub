from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .ai_presets import AI_PROVIDER_PRESETS
from .config import ConfigStore
from .errors import ConflictError, NotFoundError, SkillRepoError, ValidationError
from .jobs import JobManager
from .importer import ImportService
from .repository import SkillRepository
from .tidy import TidyService

class PreviewRequest(BaseModel):
    source: str
    item_type: Literal["skill", "project"] = "skill"
    mode: Literal["standard", "full"] = "standard"
    fetcher: Literal["archive", "git"] | None = None
    ref: str | None = None
    subdir: str | None = None


class InstallRequest(PreviewRequest):
    overwrite: bool = False
    selected_files: list[str] | None = None
    tags: list[str] | None = Field(default=None, max_length=12)
    library: Literal["", "github", "skills"] = ""


class NamedRequest(BaseModel):
    name: str
    library: str = ""


class TagUpdate(NamedRequest):
    tags: list[str] = Field(default_factory=list, max_length=12)


class MetadataUpdate(NamedRequest):
    new_name: str | None = None
    target_library: str | None = None
    description: str | None = None
    description_zh: str | None = None
    provider: Literal["local", "github"] | None = None
    source_url: str | None = None
    version: str | None = None
    license_name: str | None = None
    dir_name: str | None = None


class TranslateBatchRequest(BaseModel):
    names: list[str] | None = None


class JobDismissRequest(BaseModel):
    job_id: str


class ModeRequest(NamedRequest):
    mode: Literal["standard", "full"]


class ScanRequest(NamedRequest):
    route: Literal["offline", "ai"] = "offline"
    ai_base_url: str = ""
    ai_key: str = ""
    ai_model: str = ""


class AiModelsRequest(BaseModel):
    ai_base_url: str
    ai_key: str = ""


class ConfigUpdate(BaseModel):
    repo_root: str | None = None
    mirrors: list[str] | None = None
    proxy: str | None = None
    fetcher: Literal["archive", "git"] | None = None
    github_token: str | None = None
    ai_base_url: str | None = None
    ai_key: str | None = None
    ai_model: str | None = None
    memory_root_override: str | None = None


class MemoryEntryCreate(BaseModel):
    title: str
    name: str = ""
    description: str = ""
    type: Literal["user", "project", "reference", "feedback"] = "reference"
    tags: list[str] = Field(default_factory=list, max_length=12)
    body: str = ""


class MemoryEntryUpdate(BaseModel):
    title: str | None = None
    name: str | None = None
    description: str | None = None
    type: Literal["user", "project", "reference", "feedback"] | None = None
    tags: list[str] | None = Field(default=None, max_length=12)
    body: str | None = None


class MemoryAdmit(BaseModel):
    title: str = ""
    name: str = ""
    description: str = ""
    type: Literal["user", "project", "reference", "feedback"] | None = None
    tags: list[str] | None = None
    body: str | None = None


class AiDraftRequest(BaseModel):
    body: str


class TidyRequest(BaseModel):
    use_ai: bool = True


class MigrationScanRequest(BaseModel):
    path: str


class MigrationRunRequest(BaseModel):
    path: str
    include_memory: bool = True
    include_skills: bool = True


def create_app(config_store: ConfigStore | None = None) -> FastAPI:
    store = config_store or ConfigStore()
    repository = SkillRepository(store)
    jobs = JobManager()
    importer = ImportService(store)
    app = FastAPI(
        title="123mshub API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.config_store = store
    app.state.repository = repository
    app.state.jobs = jobs
    tidy = TidyService(store)

    @app.exception_handler(SkillRepoError)
    async def mshub_error_handler(_, exc: SkillRepoError):
        status = 409 if isinstance(exc, ConflictError) else 404 if isinstance(exc, NotFoundError) else 400
        return _json_error(status, str(exc))

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, **repository.status()}

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return _config_with_masked_secrets(store)

    @app.get("/api/config/ai-presets")
    def get_ai_presets() -> dict[str, Any]:
        return {"items": AI_PROVIDER_PRESETS}

    @app.put("/api/config")
    def update_config(request: ConfigUpdate) -> dict[str, Any]:
        updates = request.model_dump(exclude_none=True)
        config = store.save(updates)
        recovery = {"recovered_count": 0, "total_count": 0}
        if config.repo_root:
            recovery = repository.reconcile()
        return {**_config_with_masked_secrets(store), "recovery": recovery}

    @app.post("/api/system/select-directory")
    def select_directory() -> dict[str, str]:
        return _choose_directory("选择技能仓库根目录")

    @app.post("/api/system/select-import-directory")
    def select_import_directory() -> dict[str, str]:
        """导入专用：标题点明场景，避免与仓库根选择混淆。"""
        return _choose_directory("选择要导入的 Agent 工作目录")
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title="选择技能仓库根目录")
            root.destroy()
            return {"path": selected or ""}
        except Exception as exc:
            raise ValidationError(f"无法打开目录选择器：{exc}") from exc

    @app.post("/api/system/open-directory")
    def open_directory(request: NamedRequest) -> dict[str, bool]:
        path = Path(request.name)
        if not path.exists():
            raise NotFoundError(f"目录不存在：{path}")
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            raise ValidationError("当前系统暂不支持从界面打开目录。")
        return {"opened": True}

    @app.get("/api/skills")
    def list_skills() -> dict[str, Any]:
        return {"items": repository.list()}

    @app.get("/api/skills/detail")
    def skill_detail(name: str, library: str = "") -> dict[str, Any]:
        return repository.get(name, library)

    @app.get("/api/tags")
    def list_tags() -> dict[str, Any]:
        return repository.list_tags()

    @app.put("/api/skills/tags")
    def update_tags(request: TagUpdate) -> dict[str, Any]:
        return repository.set_tags(request.name, request.tags, request.library)

    @app.put("/api/skills/metadata")
    def update_metadata(request: MetadataUpdate) -> dict[str, Any]:
        updates = request.model_dump(exclude={"name", "library"}, exclude_none=True)
        updates["name"] = request.new_name
        return repository.update_metadata(request.name, updates, request.library)

    @app.post("/api/skills/translate")
    def translate_skill(request: NamedRequest) -> dict[str, Any]:
        return repository.translate_one(request.name, request.library)

    @app.post("/api/jobs/translate")
    def start_translate_job(request: TranslateBatchRequest) -> dict[str, Any]:
        names = request.names
        if names is None:
            label = "批量翻译缺失的中文备注"
        else:
            if not names:
                raise ValidationError("请至少选择一个要翻译的条目。")
            label = f"翻译备注（{len(names)} 项）"
        job = jobs.submit(
            "translate",
            label,
            lambda report: repository.translate_descriptions(names, progress=report),
        )
        return {"job_id": job.id, "job": job.to_dict()}

    @app.post("/api/skills/preview")
    def preview_skill(request: PreviewRequest) -> dict[str, Any]:
        return repository.preview(
            request.source,
            item_type=request.item_type,
            mode=request.mode,
            fetcher_name=request.fetcher,
            ref=request.ref,
            subdir=request.subdir,
        )

    @app.post("/api/skills")
    def install_skill(request: InstallRequest) -> dict[str, Any]:
        return repository.install(
            request.source,
            item_type=request.item_type,
            mode=request.mode,
            fetcher_name=request.fetcher,
            ref=request.ref,
            subdir=request.subdir,
            overwrite=request.overwrite,
            selected_files=request.selected_files,
            tags=request.tags,
            library=request.library or None,
        )

    @app.post("/api/skills/check-version")
    def check_version(request: NamedRequest) -> dict[str, Any]:
        return repository.check_version(request.name, request.library)

    @app.post("/api/skills/update")
    def update_skill(request: NamedRequest) -> dict[str, Any]:
        return repository.update(request.name, request.library)

    @app.post("/api/skills/change-mode")
    def change_mode(request: ModeRequest) -> dict[str, Any]:
        return repository.change_mode(request.name, request.mode, request.library)

    @app.post("/api/skills/scan")
    def scan_skill(request: ScanRequest) -> dict[str, Any]:
        return repository.scan(
            request.name,
            request.library,
            route=request.route,
            ai_base_url=request.ai_base_url,
            ai_key=request.ai_key,
            ai_model=request.ai_model,
        )

    @app.post("/api/jobs/install")
    def start_install_job(request: InstallRequest) -> dict[str, Any]:
        item_label = "应用项目" if request.item_type == "project" else "技能"
        job = jobs.submit(
            "install",
            f"入库 {request.source}",
            lambda report: repository.install(
                request.source,
                item_type=request.item_type,
                mode=request.mode,
                fetcher_name=request.fetcher,
                ref=request.ref,
                subdir=request.subdir,
                overwrite=request.overwrite,
                selected_files=request.selected_files,
                tags=request.tags,
                library=request.library or None,
                progress=report,
            ),
        )
        return {"job_id": job.id, "job": job.to_dict(), "item_label": item_label}

    @app.post("/api/jobs/scan")
    def start_scan_job(request: ScanRequest) -> dict[str, Any]:
        job = jobs.submit(
            "scan",
            f"安全检查 {request.name}",
            lambda report: {
                "name": request.name,
                "library": request.library,
                **repository.scan(
                    request.name,
                    request.library,
                    route=request.route,
                    ai_base_url=request.ai_base_url,
                    ai_key=request.ai_key,
                    ai_model=request.ai_model,
                    progress=report,
                ),
            },
        )
        return {"job_id": job.id, "job": job.to_dict()}

    @app.post("/api/jobs/update")
    def start_update_job(request: NamedRequest) -> dict[str, Any]:
        job = jobs.submit(
            "update",
            f"更新 {request.name}",
            lambda report: repository.update(request.name, request.library, progress=report),
        )
        return {"job_id": job.id, "job": job.to_dict()}

    @app.post("/api/ai/models")
    def list_ai_models(request: AiModelsRequest) -> dict[str, Any]:
        """从 OpenAI 兼容网关（如 New API）拉取可用模型清单。"""
        if not request.ai_base_url:
            raise ValidationError("请先填写网关 API 地址。")
        endpoint = f"{request.ai_base_url.rstrip('/')}/models"
        headers = {"Accept": "application/json"}
        key = request.ai_key or store.get_secret("ai_key")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            response = httpx.get(endpoint, headers=headers, timeout=15, follow_redirects=True)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise ValidationError(f"网关模型列表获取失败：{exc}") from exc
        except ValueError as exc:
            raise ValidationError("网关返回的内容不是有效 JSON。") from exc
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            items = data if isinstance(data, list) else []
        models = sorted({
            str(entry.get("id"))
            for entry in items
            if isinstance(entry, dict) and entry.get("id")
        })
        return {"items": models}

    @app.get("/api/jobs")
    def list_jobs() -> dict[str, Any]:
        return {"items": jobs.list_jobs()}

    @app.post("/api/jobs/dismiss")
    def dismiss_job(request: JobDismissRequest) -> dict[str, Any]:
        if not jobs.dismiss(request.job_id):
            raise NotFoundError(f"任务不存在或仍在运行：{request.job_id}")
        return {"dismissed": True}

    @app.post("/api/jobs/clear-finished")
    def clear_finished_jobs() -> dict[str, Any]:
        return {"cleared": jobs.clear_finished()}

    @app.post("/api/skills/delete")
    def delete_skill(request: NamedRequest) -> dict[str, Any]:
        return repository.delete(request.name, request.library)

    @app.post("/api/skills/trust")
    def trust_skill(request: NamedRequest) -> dict[str, Any]:
        return repository.trust(request.name, request.library)

    @app.get("/api/skills/install-prompt")
    def install_prompt(name: str, library: str = "") -> dict[str, str]:
        return {"prompt": repository.install_prompt(name, library)}

    @app.get("/api/repository/library-prompt")
    def library_prompt() -> dict[str, str]:
        """MSHub 全局注入提示词：记忆读取 + 技能使用 + 记忆投递（含连通暗号）。"""
        return {"prompt": repository.library_prompt()}

    # ------------------------------------------------------------ 记忆库

    @app.get("/api/memory/entries")
    def memory_entries(
        type: str = "",
        q: str = "",
        sort: str = "updated",
    ) -> dict[str, Any]:
        return repository.memory.list_entries(type_filter=type, query=q, sort=sort)

    @app.get("/api/memory/entries/{name}")
    def memory_entry_detail(name: str) -> dict[str, Any]:
        return repository.memory.get_entry(name)

    @app.post("/api/memory/entries", status_code=201)
    def memory_entry_create(request: MemoryEntryCreate) -> dict[str, Any]:
        return repository.memory.create_entry(request.model_dump())

    @app.put("/api/memory/entries/{name}")
    def memory_entry_update(name: str, request: MemoryEntryUpdate) -> dict[str, Any]:
        updates = request.model_dump(exclude_none=True)
        return repository.memory.update_entry(name, updates)

    @app.delete("/api/memory/entries/{name}")
    def memory_entry_delete(name: str) -> dict[str, Any]:
        return repository.memory.delete_entry(name)

    @app.get("/api/memory/inbox")
    def memory_inbox() -> dict[str, Any]:
        return repository.memory.list_inbox()

    @app.post("/api/memory/inbox/{file_name}/admit")
    def memory_inbox_admit(file_name: str, request: MemoryAdmit) -> dict[str, Any]:
        return repository.memory.admit_inbox(file_name, request.model_dump(exclude_none=True))

    @app.post("/api/memory/inbox/{file_name}/discard")
    def memory_inbox_discard(file_name: str) -> dict[str, Any]:
        return repository.memory.discard_inbox(file_name)

    @app.post("/api/memory/inbox/discard-all")
    def memory_inbox_discard_all() -> dict[str, Any]:
        return repository.memory.discard_all_inbox()

    @app.post("/api/memory/ai-draft")
    def memory_ai_draft(request: AiDraftRequest) -> dict[str, str]:
        """对给定正文调统一 AI 接口，一次返回候选 title + description。"""
        return repository.memory.ai_draft(request.body)

    @app.get("/api/memory/stats")
    def memory_stats() -> dict[str, Any]:
        return repository.memory.stats()

    @app.get("/api/memory/index-file")
    def memory_index_file() -> dict[str, Any]:
        return repository.memory.index_file_content()

    @app.post("/api/memory/rebuild")
    def memory_rebuild() -> dict[str, Any]:
        """手动重建记忆索引并对账（并入「重新识别」同一套自愈逻辑）。"""
        return repository.memory.rebuild_all()

    @app.post("/api/memory/tidy")
    def memory_tidy(request: TidyRequest) -> dict[str, Any]:
        """手动归纳整理：本地盘点 +（配置了 AI 接口时）LLM 分析，合成日报落盘。"""
        return tidy.run_tidy(use_ai=request.use_ai)

    @app.get("/api/memory/reports")
    def memory_reports() -> dict[str, Any]:
        return tidy.list_reports()

    @app.get("/api/memory/reports/{file_name}")
    def memory_report_detail(file_name: str) -> dict[str, Any]:
        return tidy.read_report(file_name)

    @app.get("/api/memory/duty-prompt")
    def memory_duty_prompt() -> dict[str, str]:
        """值守整理提示词：交给外部 agent（如 NAS 总机）部署值守与日报。"""
        return {"prompt": tidy.duty_prompt()}

    # ------------------------------------------------------ 导入记忆技能库

    @app.post("/api/migration/scan")
    def migration_scan(request: MigrationScanRequest) -> dict[str, Any]:
        """只读预览：识别路径下可导入的记忆与技能（后台任务，大目录不卡界面）。"""
        store.require_repo_root()
        job = jobs.submit(
            "import-scan",
            f"扫描 {request.path}",
            lambda report: importer.scan(request.path, progress=report),
        )
        return {"job_id": job.id, "job": job.to_dict()}

    @app.post("/api/migration/run")
    def migration_run(request: MigrationRunRequest) -> dict[str, Any]:
        """执行导入：写入记忆 + 复制技能 + 入册去重 + 生成整理日报（后台任务）。"""
        store.require_repo_root()
        job = jobs.submit(
            "import-run",
            f"导入 {request.path}",
            lambda report: importer.run(
                request.path,
                include_memory=request.include_memory,
                include_skills=request.include_skills,
                progress=report,
            ),
        )
        return {"job_id": job.id, "job": job.to_dict()}

    @app.post("/api/index/rebuild")
    def rebuild() -> dict[str, Any]:
        return repository.rebuild()

    @app.post("/api/repository/reconcile")
    def reconcile_repository() -> dict[str, Any]:
        return repository.reconcile()

    @app.post("/api/repository/migrate-manifests")
    def migrate_manifests() -> dict[str, Any]:
        """一次性迁移：旧名 .manifest.json 改名为 _manifest.json（内容不变）。"""
        return repository.migrate_manifests()

    @app.get("/api/help", response_class=PlainTextResponse, include_in_schema=False)
    def help_document() -> str:
        readme = bundled_root() / "README.md"
        if not readme.exists():
            readme = Path(__file__).resolve().parents[2] / "README.md"
        if not readme.exists():
            return "123mshub 使用说明请参阅项目 README.md。"
        return readme.read_text(encoding="utf-8", errors="replace")

    static_root = bundled_static_root()
    project_static = Path(__file__).resolve().parents[2] / "web" / "dist"
    if not getattr(sys, "frozen", False) and project_static.exists():
        static_root = project_static
    if static_root.exists():
        assets = static_root / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            requested = (static_root / path).resolve()
            try:
                requested.relative_to(static_root.resolve())
            except ValueError:
                raise HTTPException(status_code=404)
            if path and requested.is_file():
                return FileResponse(requested)
            return FileResponse(static_root / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_frontend() -> dict[str, str]:
            return {"message": "前端尚未构建，请在 web 目录运行 npm run build。"}

    return app


def bundled_root() -> Path:
    """Return the PyInstaller extraction root or the source project root."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def bundled_static_root() -> Path:
    """Locate UI assets in both source/wheel and PyInstaller onefile builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return bundled_root() / "mshub" / "web"
    return Path(__file__).resolve().parent / "web"


def _choose_directory(title: str) -> dict[str, str]:
    """原生目录选择框（标题按场景定制）。"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title=title)
        root.destroy()
        return {"path": selected or ""}
    except Exception as exc:
        raise ValidationError(f"无法打开目录选择器：{exc}") from exc


def _config_with_masked_secrets(store: ConfigStore) -> dict[str, Any]:
    data = store.load().public_dict()
    data["github_token_masked"] = _mask_secret(store.get_secret("github_token"))
    data["ai_key_masked"] = _mask_secret(store.get_secret("ai_key"))
    return data


def _mask_secret(value: str) -> str:
    """凭据只隐藏中间部分：保留头尾各 4 位，中间用圆点替代。"""
    if not value:
        return ""
    if len(value) <= 8:
        return value[:2] + "••••"
    return f"{value[:4]}••••••{value[-4:]}"


def _json_error(status_code: int, message: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"detail": message})


app = create_app()
