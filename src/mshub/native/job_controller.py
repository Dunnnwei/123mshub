"""Qt presentation of the existing serialized JobManager, no HTTP layer."""
from PySide6.QtCore import QObject, QTimer, Signal
from ..jobs import JobManager


class JobController(QObject):
    changed = Signal()
    completed = Signal(object)
    repositoryChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = JobManager()
        self._observed = set()
        self._callbacks = {}
        self._retry_callbacks = {}
        self._mutations = set()
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    # These operations are safe to repeat from the task panel because their
    # callable is captured at submission time.  Destructive delete jobs are
    # deliberately excluded; retrying those would turn a harmless click into
    # a second destructive request.
    _AUTO_RETRY_KINDS = frozenset({
        "install", "update", "translate", "metadata", "scan", "trust",
        "import", "reconcile", "ai", "tidy", "upgrade",
    })

    def submit(self, kind, label, fn, *, progress=False, changed=True, callback=None, retry=None,
               _register_auto_retry=True):
        def run(report):
            report(None, label)
            return fn(report) if progress else fn()
        job = self.manager.submit(kind, label, run)
        if callback:
            self._callbacks[job.id] = callback
        if retry is not None:
            self._retry_callbacks[job.id] = retry
        elif _register_auto_retry and kind in self._AUTO_RETRY_KINDS:
            # Capture all arguments in a zero-argument callback.  The retry
            # gets a new job id and therefore a fresh progress row, while the
            # original failure remains available for its details dialog.
            def resubmit(kind=kind, label=label, fn=fn, progress=progress,
                         changed=changed, callback=callback):
                return self.submit(
                    kind, label, fn, progress=progress, changed=changed,
                    callback=callback,
                )
            self._retry_callbacks[job.id] = resubmit
        if changed:
            self._mutations.add(job.id)
        self.changed.emit()
        return job

    def poll(self):
        for job in self.manager.list_jobs():
            if job["status"] != "running" and job["id"] not in self._observed:
                identifier = job["id"]
                self._observed.add(identifier)
                callback = self._callbacks.pop(identifier, None)
                if callback:
                    callback(job)
                self.completed.emit(job)
                if identifier in self._mutations:
                    self._mutations.discard(identifier)
                    self.repositoryChanged.emit()
        self.changed.emit()

    def list(self):
        return sorted(self.manager.list_jobs(), key=lambda j: j["created_at"], reverse=True)

    def dismiss(self, identifier):
        removed = self.manager.dismiss(identifier)
        self._observed.discard(identifier)
        self._retry_callbacks.pop(identifier, None)
        self.changed.emit()
        return removed

    def retry(self, identifier):
        """Re-submit a failed/unfinished task when its owner supplied a retry action."""
        job = next((row for row in self.manager.list_jobs() if row["id"] == identifier), None)
        callback = self._retry_callbacks.get(identifier)
        if not job or not callback or job["status"] != "error":
            return None
        return callback()

    def can_retry(self, identifier) -> bool:
        job = next((row for row in self.manager.list_jobs() if row["id"] == identifier), None)
        # A completed task has useful details but should not be re-run by an
        # accidental click.  Running tasks are still in flight; only an
        # observed failure is an actionable retry state.
        return bool(job and job["status"] == "error" and identifier in self._retry_callbacks)

    def clear_finished(self) -> int:
        """v1.7.3：一键清除全部已结束任务（运行中保留），供侧栏任务面板使用。

        ocr 审查修复（2026-09-29）：任务可能在工作线程刚完成、还没被 200ms 轮询
        观察到时就被清理——其 callback（如翻译 done）与 repositoryChanged 会被
        静默吞掉。先按 poll 的逻辑派发一遍未观察的已结束任务，再清理。
        """
        for job in self.manager.list_jobs():
            if job["status"] == "running" or job["id"] in self._observed:
                continue
            identifier = job["id"]
            self._observed.add(identifier)
            callback = self._callbacks.pop(identifier, None)
            if callback:
                callback(job)
            self.completed.emit(job)
            if identifier in self._mutations:
                self._mutations.discard(identifier)
                self.repositoryChanged.emit()
        removed = self.manager.clear_finished()
        for identifier in list(self._retry_callbacks):
            if not any(row["id"] == identifier for row in self.manager.list_jobs()):
                self._retry_callbacks.pop(identifier, None)
        self.changed.emit()
        return removed

    def shutdown(self):
        self.timer.stop()
        self.manager._executor.shutdown(wait=True)
