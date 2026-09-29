from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .errors import ValidationError

SERVICE_NAME = "mshub"


def default_config_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / SERVICE_NAME
    return Path.home() / ".config" / SERVICE_NAME


@dataclass(slots=True)
class AppConfig:
    repo_root: str = ""
    mirrors: list[str] = field(default_factory=list)
    proxy: str = ""
    fetcher: str = "archive"
    github_token_configured: bool = False
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4.1-mini"
    ai_key_configured: bool = False
    memory_root_override: str = ""
    language: str = "system"
    # v1.8.0（审查 M-2）：密钥实际后端——keyring 不可用时降级为进程内存，
    # 重启即丢。暴露给设置页提示用户，不再静默。
    secrets_backend: str = "keyring"
    # v1.9.1：启动 8 秒后后台检查新版本（失败静默，发现新版仅轻提示，不自动下载）
    auto_check_updates: bool = True

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConfigStore:
    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or default_config_dir()
        self.path = self.config_dir / "config.json"
        self._memory_secrets: dict[str, str] = {}
        self._secrets_backend: str | None = None

    def detect_secrets_backend(self) -> str:
        """v1.8.0（审查 M-2）：探测钥匙串可用性并缓存；降级必须留痕。"""
        if self._secrets_backend is None:
            try:
                import keyring  # type: ignore

                keyring.get_keyring()
                self._secrets_backend = "keyring"
            except Exception as exc:
                self._secrets_backend = "memory"
                logging.getLogger(__name__).warning(
                    "系统钥匙串不可用，密钥仅保存到进程内存（重启后丢失）：%s", exc
                )
        return self._secrets_backend

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"配置文件无法读取：{exc}") from exc
        allowed = AppConfig.__dataclass_fields__.keys()
        config = AppConfig(**{key: value for key, value in data.items() if key in allowed})
        config.secrets_backend = self.detect_secrets_backend()
        return config

    def save(self, updates: dict[str, Any]) -> AppConfig:
        current = self.load()
        for key, value in updates.items():
            if key in {"github_token", "ai_key"}:
                if value:
                    self.set_secret(key, str(value))
                    setattr(current, f"{key}_configured", True)
                elif value == "":
                    self.delete_secret(key)
                    setattr(current, f"{key}_configured", False)
                continue
            if hasattr(current, key):
                setattr(current, key, value)

        if current.repo_root:
            current.repo_root = str(Path(current.repo_root).expanduser().resolve())
        if current.memory_root_override:
            current.memory_root_override = str(
                Path(current.memory_root_override).expanduser().resolve()
            )
        current.mirrors = [m.strip() for m in current.mirrors if m and m.strip()]
        current.secrets_backend = self.detect_secrets_backend()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(current.public_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, self.path)
        return current

    def get_secret(self, name: str) -> str:
        try:
            import keyring  # type: ignore

            return keyring.get_password(SERVICE_NAME, name) or self._memory_secrets.get(name, "")
        except Exception:
            return self._memory_secrets.get(name, "")

    def set_secret(self, name: str, value: str) -> None:
        try:
            import keyring  # type: ignore

            keyring.set_password(SERVICE_NAME, name, value)
        except Exception as exc:
            # v1.8.0（审查 M-2）：降级必须留痕——否则用户"显示已配置"但重启即丢
            logging.getLogger(__name__).warning(
                "密钥 %s 写入系统钥匙串失败，退回进程内存（重启后丢失）：%s", name, exc
            )
            self._memory_secrets[name] = value

    def delete_secret(self, name: str) -> None:
        try:
            import keyring  # type: ignore

            keyring.delete_password(SERVICE_NAME, name)
        except Exception as exc:
            # v1.8.0（审查 L-3）：删失败不阻断流程，但必须留排障线索
            logging.getLogger(__name__).debug("删除钥匙串条目 %s 失败：%s", name, exc)
        self._memory_secrets.pop(name, None)

    def require_repo_root(self) -> Path:
        config = self.load()
        if not config.repo_root:
            raise ValidationError("尚未设置技能仓库根目录，请先在设置中选择目录。")
        root = Path(config.repo_root)
        root.mkdir(parents=True, exist_ok=True)
        return root
