"""Small Qt thread-pool adapter used by native views.

Workers never touch widgets.  Results are delivered through Qt signals on the
receiver's thread and every submitted operation gets a monotonically
increasing request id so stale search results cannot replace current state.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class WorkerSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, object)
    progress = Signal(int, int, str)


class _Runnable(QRunnable):
    def __init__(self, request_id: int, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], signals: WorkerSignals) -> None:
        super().__init__()
        self.request_id = request_id
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except BaseException as exc:  # deliver every failure; never silently swallow worker errors
            self.signals.failed.emit(self.request_id, {
                "error": exc,
                "traceback": traceback.format_exc(),
            })
            return
        self.signals.finished.emit(self.request_id, result)


@dataclass(slots=True)
class TaskHandle:
    request_id: int
    signals: WorkerSignals


class TaskRunner(QObject):
    """Submit blocking work without blocking the Qt event loop."""

    def __init__(self, parent: QObject | None = None, pool: QThreadPool | None = None) -> None:
        super().__init__(parent)
        self.pool = pool or QThreadPool.globalInstance()
        self._next_id = 0
        self._active: set[int] = set()

    @property
    def active_ids(self) -> frozenset[int]:
        return frozenset(self._active)

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> TaskHandle:
        self._next_id += 1
        request_id = self._next_id
        signals = WorkerSignals()
        self._active.add(request_id)

        def clear_finished(identifier: int, _payload: object) -> None:
            self._active.discard(identifier)

        signals.finished.connect(clear_finished)
        signals.failed.connect(clear_finished)
        self.pool.start(_Runnable(request_id, fn, args, kwargs, signals))
        return TaskHandle(request_id, signals)

    def invalidate(self, request_id: int) -> None:
        """Make a request stale from the caller's perspective.

        QRunnable cannot be safely killed after it entered a core operation;
        invalidation instead ensures the view ignores its eventual result.
        """

        self._active.discard(request_id)

