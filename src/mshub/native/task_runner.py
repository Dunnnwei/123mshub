"""Blocking reads with explicit UI-thread delivery and stale-result protection."""
from __future__ import annotations

from dataclasses import dataclass
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot, QTimer


class WorkerSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, object)


@dataclass
class TaskHandle:
    request_id: int
    signals: WorkerSignals


class _Runnable(QRunnable):
    def __init__(self, owner, identifier, fn, args, kwargs):
        super().__init__()
        self.owner, self.identifier = owner, identifier
        self.fn, self.args, self.kwargs = fn, args, kwargs

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            self.owner.completed.emit(self.identifier, {"error": exc, "traceback": traceback.format_exc()}, False)
        else:
            self.owner.completed.emit(self.identifier, result, True)


class TaskRunner(QObject):
    completed = Signal(int, object, bool)

    def __init__(self, parent=None, pool=None):
        super().__init__(parent)
        self.pool = pool or QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._next_id = 0
        self._handles: dict[int, TaskHandle] = {}
        self._active: set[int] = set()
        self.completed.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    @property
    def active_ids(self):
        return frozenset(self._active)

    def submit(self, fn: Callable[..., Any], *args, **kwargs) -> TaskHandle:
        self._next_id += 1
        identifier = self._next_id
        handle = TaskHandle(identifier, WorkerSignals(self))
        self._handles[identifier] = handle
        self._active.add(identifier)
        runnable = _Runnable(self, identifier, fn, args, kwargs)
        # Queue start so callers can connect before instant work completes.
        QTimer.singleShot(0, self, lambda: self.pool.start(runnable))
        return handle

    @Slot(int, object, bool)
    def _deliver(self, identifier, result, ok):
        handle = self._handles.pop(identifier, None)
        active = identifier in self._active
        self._active.discard(identifier)
        if handle:
            if active:
                (handle.signals.finished if ok else handle.signals.failed).emit(identifier, result)
            handle.signals.deleteLater()

    def invalidate(self, identifier):
        self._active.discard(identifier)


class RequestScope(QObject):
    """Lifetime + generation gate shared by forms and detail/search views."""
    def __init__(self, runner: TaskRunner, parent: QObject):
        super().__init__(parent)
        self.runner = runner
        self.pending: dict[str, int] = {}
        parent.destroyed.connect(self.cancel_all)

    def invalidate(self, channel):
        identifier = self.pending.pop(channel, None)
        if identifier is not None:
            self.runner.invalidate(identifier)

    def cancel_all(self, *_):
        for identifier in self.pending.values():
            self.runner.invalidate(identifier)
        self.pending.clear()

    def call(self, channel, fn, success, failure, *args, **kwargs):
        self.invalidate(channel)
        handle = self.runner.submit(fn, *args, **kwargs)
        self.pending[channel] = handle.request_id

        def finish(identifier, payload, ok):
            if self.pending.get(channel) != identifier:
                return
            self.pending.pop(channel, None)
            (success if ok else failure)(payload if ok else str(payload["error"]))

        handle.signals.finished.connect(lambda i, p: finish(i, p, True))
        handle.signals.failed.connect(lambda i, p: finish(i, p, False))
        return handle
