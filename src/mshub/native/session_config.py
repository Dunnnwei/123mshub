"""Session overrides; the durable ConfigStore and its format stay unchanged."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from ..config import ConfigStore


class SessionConfigStore(ConfigStore):
    def __init__(self, config_dir: Path | None = None, *, repo: str = "", isolated: bool = False):
        super().__init__(config_dir)
        self.disk = ConfigStore(self.config_dir)
        self.repo_override = str(Path(repo).expanduser().resolve()) if repo else ""
        self.isolated = isolated
        # Core save calls these through the durable store. Explicitly isolated
        # QA sessions must never reach the operating system credential vault.
        self.disk.get_secret = self.get_secret
        self.disk.set_secret = self.set_secret
        self.disk.delete_secret = self.delete_secret

    def load(self):
        config = self.disk.load()
        return replace(config, repo_root=self.repo_override) if self.repo_override else config

    def save(self, updates: dict[str, Any]):
        # Crucially, disk.save loads disk.load, never this session's load.
        self.disk.save(updates)
        if "repo_root" in updates:
            self.repo_override = ""
        return self.load()

    def get_secret(self, name: str) -> str:
        return self._memory_secrets.get(name, "") if self.isolated else super().get_secret(name)

    def set_secret(self, name: str, value: str) -> None:
        if self.isolated:
            self._memory_secrets[name] = value
        else:
            super().set_secret(name, value)

    def delete_secret(self, name: str) -> None:
        if self.isolated:
            self._memory_secrets.pop(name, None)
        else:
            super().delete_secret(name)
