from __future__ import annotations

from pathlib import Path
import os

import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from mshub.config import ConfigStore
from mshub.native.memory_facade import MemoryFacade


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture()
def native_facade(tmp_path: Path) -> MemoryFacade:
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    return MemoryFacade(store)
