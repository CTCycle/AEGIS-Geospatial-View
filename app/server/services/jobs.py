from __future__ import annotations

import inspect
import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from time import monotonic
from typing import Any

from server.common.constants import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
)
from server.common.logger import logger
from server.services.job_state import JobState


class JobBackend(ABC):
    @abstractmethod
    def start_job(
        self,
        job_type: str,
        runner: Callable[..., dict[str, Any]],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def cancel_job(self, job_id: str) -> bool:
        raise NotImplementedError


class InProcessJobBackend(JobBackend):
    def __init__(self) -> None:
        self.jobs: dict[str, JobState] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.lock = threading.Lock()

    def start_job(
        self,
        job_type: str,
        runner: Callable[..., dict[str, Any]],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())[:8]
        state = JobState(job_id=job_id, job_type=job_type, status=JOB_STATUS_PENDING)
        runner_kwargs = kwargs.copy() if kwargs else {}

        if self.runner_accepts_job_id(runner):
            runner_kwargs["job_id"] = job_id

        with self.lock:
            self.jobs[job_id] = state

        thread = threading.Thread(
            target=self.run_job,
            args=(job_id, runner, args, runner_kwargs),
            daemon=True,
        )

        with self.lock:
            self.threads[job_id] = thread

        state.update(status=JOB_STATUS_RUNNING)
        thread.start()

        logger.info("Started job %s (type=%s) with in-process backend", job_id, job_type)
        return job_id

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            state = self.jobs.get(job_id)
        if state is None:
            return None
        return state.snapshot()

    def cancel_job(self, job_id: str) -> bool:
        with self.lock:
            state = self.jobs.get(job_id)
        if state is None:
            return False
        if state.status not in (JOB_STATUS_PENDING, JOB_STATUS_RUNNING):
            return False
        state.update(
            stop_requested=True,
            status=JOB_STATUS_CANCELLED,
            completed_at=monotonic(),
        )
        logger.info("Cancelled in-process job %s", job_id)
        return True

    def run_job(
        self,
        job_id: str,
        runner: Callable[..., dict[str, Any]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        with self.lock:
            state = self.jobs.get(job_id)
        if state is None:
            return

        try:
            result = runner(*args, **kwargs)
            if state.stop_requested:
                state.update(status=JOB_STATUS_CANCELLED, completed_at=monotonic())
            else:
                result_payload = result or {}
                with state.lock:
                    merged = {**(state.result or {}), **result_payload}
                state.update(
                    status=JOB_STATUS_COMPLETED,
                    result=merged if merged else None,
                    progress=100.0,
                    completed_at=monotonic(),
                )
                logger.info("In-process job %s completed successfully", job_id)
        except Exception as exc:  # noqa: BLE001
            if state.stop_requested:
                state.update(status=JOB_STATUS_CANCELLED, completed_at=monotonic())
                logger.info("In-process job %s cancelled during execution", job_id)
                return
            error_msg = str(exc).split("\n")[0][:200]
            state.update(
                status=JOB_STATUS_FAILED,
                error=error_msg,
                completed_at=monotonic(),
            )
            logger.error("In-process job %s failed: %s", job_id, error_msg)
            logger.debug("In-process job %s error details", job_id, exc_info=True)

    @staticmethod
    def runner_accepts_job_id(runner: Callable[..., dict[str, Any]]) -> bool:
        try:
            signature = inspect.signature(runner)
        except (TypeError, ValueError):
            return False
        for param in signature.parameters.values():
            if param.kind == param.VAR_KEYWORD:
                return True
        return "job_id" in signature.parameters


class UnsupportedJobBackend(JobBackend):
    def __init__(self, backend_name: str) -> None:
        self.backend_name = backend_name

    def start_job(
        self,
        job_type: str,
        runner: Callable[..., dict[str, Any]],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> str:
        _ = job_type, runner, args, kwargs
        raise RuntimeError(
            f"Job backend '{self.backend_name}' is not implemented yet. "
            "Use 'in_process' or add a durable backend implementation."
        )

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        _ = job_id
        return None

    def cancel_job(self, job_id: str) -> bool:
        _ = job_id
        return False


def build_job_backend(backend_name: str) -> JobBackend:
    normalized = str(backend_name).strip().lower() or "in_process"
    if normalized == "in_process":
        return InProcessJobBackend()
    return UnsupportedJobBackend(normalized)


JobManager = InProcessJobBackend
