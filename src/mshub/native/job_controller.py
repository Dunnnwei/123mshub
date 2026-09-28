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
        self._mutations = set()
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def submit(self, kind, label, fn, *, progress=False, changed=True, callback=None):
        def run(report):
            report(None, label)
            return fn(report) if progress else fn()
        job = self.manager.submit(kind, label, run)
        if callback:
            self._callbacks[job.id] = callback
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
        self.changed.emit()
        return removed

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
        self.changed.emit()
        return removed

    def shutdown(self):
        self.timer.stop()
        self.manager._executor.shutdown(wait=True)
