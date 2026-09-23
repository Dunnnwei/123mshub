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

    def shutdown(self):
        self.timer.stop()
        self.manager._executor.shutdown(wait=True)
