from __future__ import annotations

from pathlib import Path
import os

import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent

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


@pytest.fixture(autouse=True)
def _release_native_windows(qapp):
    """Closed Qt windows are hidden, not destroyed: don't retain them across tests.

    An application-wide stylesheet change otherwise repolishes every prior test
    window, turning the full suite into quadratic GUI work and retaining timers.
    """
    yield
    from mshub.native.job_controller import JobController
    from mshub.native.task_runner import TaskRunner
    for window in qapp.topLevelWidgets():
        if window.parent() is not None:
            continue
        for jobs in window.findChildren(JobController):
            jobs.shutdown()
        for runner in window.findChildren(TaskRunner):
            runner.pool.waitForDone(5000)
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
