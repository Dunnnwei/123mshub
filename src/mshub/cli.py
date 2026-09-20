from __future__ import annotations

import json
import sys
from typing import Optional

import typer

from .api import create_app
from .config import ConfigStore
from .errors import SkillRepoError
from .repository import SkillRepository

app = typer.Typer(
    name="mshub",
    help="本地 agent 技能包管理器与分发中枢。",
    no_args_is_help=True,
)
config_app = typer.Typer(help="查看或修改全局配置。")
app.add_typer(config_app, name="config")


def _repo() -> SkillRepository:
    return SkillRepository(ConfigStore())


def _print(data) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@config_app.callback(invoke_without_command=True)
def config(
    repo_root: Optional[str] = typer.Option(None, "--repo-root", help="技能仓库根目录"),
    mirror: list[str] = typer.Option([], "--mirror", help="镜像前缀，可重复"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="HTTP/HTTPS 代理"),
    fetcher: Optional[str] = typer.Option(None, "--fetcher", help="archive 或 git"),
    github_token: Optional[str] = typer.Option(None, "--github-token", help="GitHub Token，不写入明文配置"),
    ai_base_url: Optional[str] = typer.Option(None, "--ai-base-url"),
    ai_key: Optional[str] = typer.Option(None, "--ai-key", help="AI API Key，不写入明文配置"),
    ai_model: Optional[str] = typer.Option(None, "--ai-model"),
) -> None:
    store = ConfigStore()
    updates = {
        key: value for key, value in {
            "repo_root": repo_root,
            "mirrors": mirror or None,
            "proxy": proxy,
            "fetcher": fetcher,
            "github_token": github_token,
            "ai_base_url": ai_base_url,
            "ai_key": ai_key,
            "ai_model": ai_model,
        }.items() if value is not None
    }
    _print(store.save(updates).public_dict() if updates else store.load().public_dict())


@app.command()
def add(
    source: str,
    mode: str = typer.Option("standard", "--mode"),
    fetcher: Optional[str] = typer.Option(None, "--fetcher"),
    ref: Optional[str] = typer.Option(None, "--ref"),
    subdir: Optional[str] = typer.Option(None, "--subdir"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过文件清单确认"),
    tag: list[str] = typer.Option([], "--tag", help="分类标签，可重复"),
    library: Optional[str] = typer.Option(
        None,
        "--library",
        help="目标技能库：github / skills / zcode-skills / workbuddy-skills（库即分发目标）",
    ),
) -> None:
    repository = _repo()
    if not yes:
        preview = repository.preview(source, mode=mode, fetcher_name=fetcher, ref=ref, subdir=subdir)
        typer.echo(
            f"{preview['name']} · {preview['selected_file_count']} 个文件 · "
            f"{preview['total_bytes'] / 1024:.1f} KB · {preview['mode']}"
        )
        if not typer.confirm("确认安装到本地仓库？"):
            raise typer.Abort()
    _print(repository.install(
        source, mode=mode, fetcher_name=fetcher, ref=ref,
        subdir=subdir, overwrite=overwrite, tags=tag or None, library=library,
    ))


@app.command("list")
def list_skills() -> None:
    _print(_repo().list())


@app.command()
def show(name: str) -> None:
    _print(_repo().get(name))


@app.command("tags")
def list_tags() -> None:
    """列出仓库标签及其技能数量。"""
    _print(_repo().list_tags())


@app.command("tag")
def set_tags(
    name: str,
    tag: list[str] = typer.Option([], "--tag", help="新的标签集合，可重复"),
    clear: bool = typer.Option(False, "--clear", help="清空该技能的全部标签"),
) -> None:
    """替换一个技能的标签集合。"""
    if not tag and not clear:
        raise typer.BadParameter("请至少提供一个 --tag，或使用 --clear。")
    _print(_repo().set_tags(name, [] if clear else tag))


@app.command()
def scan(name: str, route: str = typer.Option("offline", "--route")) -> None:
    _print(_repo().scan(name, route=route))


@app.command("check-updates")
def check_updates(name: Optional[str] = None) -> None:
    repository = _repo()
    names = [name] if name else [item["name"] for item in repository.list()]
    _print([repository.check_version(item) for item in names])


@app.command()
def update(name: str, force: bool = typer.Option(False, "--force")) -> None:
    _print(_repo().update(name, force=force))


@app.command()
def mode(name: str, target: str = typer.Argument(..., help="standard 或 full")) -> None:
    _print(_repo().change_mode(name, target))


@app.command()
def remove(name: str, yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    if not yes and not typer.confirm(f"完全删除 {name}？可从 .meta/trash 恢复。"):
        raise typer.Abort()
    _print(_repo().delete(name))


@app.command()
def prompt(name: str) -> None:
    typer.echo(_repo().install_prompt(name))


@app.command("migrate-manifests")
def migrate_manifests() -> None:
    """一次性迁移：库内旧名 .manifest.json 批量改名为 _manifest.json（内容不变）。

    点开头清单会被飞牛同步按隐藏文件排除，NAS 侧收不到；改名后即可随目录同步。
    """
    _print(_repo().migrate_manifests())


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8766, "--port"),
    gui: bool = typer.Option(False, "--gui", help="用桌面窗口打开"),
) -> None:
    if gui:
        from .gui import launch

        launch(host=host, port=port)
        return
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


def main() -> None:
    try:
        app()
    except SkillRepoError as exc:
        typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    main()
