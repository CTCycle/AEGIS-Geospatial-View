from __future__ import annotations

from server.common.constants import JOB_STATUS_PENDING
from server.services.jobs import JobManager


def test_start_job_returns_job_id_and_initial_status() -> None:
    manager = JobManager()

    job_id = manager.start_job("map_search", lambda: {})
    status = manager.get_job_status(job_id)

    assert isinstance(job_id, str)
    assert job_id
    assert status is not None
    assert status["job_id"] == job_id
    assert status["job_type"] == "map_search"
    assert status["status"] in {JOB_STATUS_PENDING, "running", "completed"}


def test_get_job_status_returns_snapshot() -> None:
    manager = JobManager()
    job_id = manager.start_job("map_search", lambda: {"items": 1})

    status = manager.get_job_status(job_id)

    assert status is not None
    assert status["job_id"] == job_id
    assert status["job_type"] == "map_search"
    assert "created_at" in status


def test_cancel_job_returns_false_for_missing_id() -> None:
    manager = JobManager()

    assert manager.cancel_job("missing") is False


def test_runner_accepts_job_id_detects_named_parameter() -> None:
    manager = JobManager()

    def runner(*, job_id: str) -> dict[str, object]:
        return {"job_id": job_id}

    assert manager.runner_accepts_job_id(runner) is True


def test_runner_accepts_job_id_detects_kwargs() -> None:
    manager = JobManager()

    def runner(**kwargs: object) -> dict[str, object]:
        return {"kwargs": kwargs}

    assert manager.runner_accepts_job_id(runner) is True


def test_runner_accepts_job_id_rejects_runner_without_job_id_support() -> None:
    manager = JobManager()

    def runner() -> dict[str, object]:
        return {}

    assert manager.runner_accepts_job_id(runner) is False
