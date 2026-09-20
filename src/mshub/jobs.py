"""后台任务管理：入库 / 更新 / 安全检查等长耗时操作异步执行并上报进度。

GUI 提交任务后立即返回 job_id，前端轮询 /api/jobs 展示进度条；
CLI 与旧的同步 REST 接口保持不变。所有任务经单线程执行器串行，
避免并发写 SQLite 与仓库目录。
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .errors import SkillRepoError

JOB_RETENTION_SECONDS = 30 * 60
MAX_FINISHED_JOBS = 30

# 进度回调：percent 为 None 表示进度未知（前端展示为流动条），
# phase 是阶段文案，detail 是补充说明（如已下载字节数）。
ProgressCallback = Callable[..., None]


class Job:
    def __init__(self, job_id: str, kind: str, label: str) -> None:
        self.id = job_id
        self.kind = kind
        self.label = label
        self.status = "running"
        self.progress: int | None = 0
        self.phase = "正在排队"
        self.detail = ""
        self.error = ""
        self.result: Any = None
        self.created_at = _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "progress": self.progress,
            "phase": self.phase,
            "detail": self.detail,
            "error": self.error,
            "result": self.result,
            "created_at": self.created_at,
        }


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mshub-job")

    def submit(self, kind: str, label: str, runner: Callable[[ProgressCallback], Any]) -> Job:
        self._purge()
        job = Job(uuid.uuid4().hex, kind, label)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)

        def report(percent: int | None = None, phase: str = "", detail: str = "") -> None:
            with self._lock:
                if job.status != "running":
                    return
                if percent is not None:
                    job.progress = max(job.progress or 0, min(int(percent), 99))
                if phase:
                    job.phase = phase
                if detail:
                    job.detail = detail

        def run() -> None:
            try:
                job.result = runner(report)
            except SkillRepoError as exc:
                job.error = str(exc)
                job.status = "error"
            except Exception as exc:  # 后台线程必须吞掉一切异常，转为任务失败
                job.error = f"任务执行出错：{exc}"
                job.status = "error"
            else:
                job.status = "done"
                job.progress = 100
            finally:
                job.phase = "已完成" if job.status == "done" else "失败"

        self._executor.submit(run)
        return job

    def list_jobs(self) -> list[dict[str, Any]]:
        self._purge()
        with self._lock:
            jobs = [self._jobs[job_id] for job_id in self._order if job_id in self._jobs]
        running = [job for job in jobs if job.status == "running"]
        # 已完成任务按创建时间倒序：面板最上面永远是最新记录
        finished = sorted(
            (job for job in jobs if job.status != "running"),
            key=lambda job: job.created_at,
            reverse=True,
        )
        return [job.to_dict() for job in running + finished]

    def dismiss(self, job_id: str) -> bool:
        """用户手动关闭一条已结束任务：服务端删除，重开面板不再出现。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status == "running":
                return False
            self._jobs.pop(job_id, None)
            try:
                self._order.remove(job_id)
            except ValueError:
                pass
            return True

    def clear_finished(self) -> int:
        with self._lock:
            finished = [job_id for job_id in self._order if self._jobs[job_id].status != "running"]
            for job_id in finished:
                self._jobs.pop(job_id, None)
                self._order.remove(job_id)
            return len(finished)

    def _purge(self) -> None:
        with self._lock:
            finished = [job_id for job_id in self._order if self._jobs[job_id].status != "running"]
            overflow = max(len(finished) - MAX_FINISHED_JOBS, 0)
            for job_id in finished[:overflow]:
                self._jobs.pop(job_id, None)
                self._order.remove(job_id)


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
