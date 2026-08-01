from __future__ import annotations

from server.common.typing import json_object

import asyncio
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from server.common.constants import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
)
from server.domain.chat import ChatTurnRequest
from server.domain.jobs import (
    BackgroundJob, BackgroundJobEventType, BackgroundJobStatus, BackgroundJobType,
    BackgroundJobCreateResponse,
    BackgroundJobEvent,
    BackgroundJobEventsResponse,
    BackgroundJobStatusResponse,
    JobCancelResponse,
)
from server.services.chat.streaming import ChatStreamingService

LOGGER = logging.getLogger(__name__)

###############################################################################
def _utc_now() -> datetime:
    return datetime.now(UTC)

###############################################################################
class BackgroundJobService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        chat_streaming_service: ChatStreamingService,
        polling_interval: float = 1.0,
    ) -> None:
        self._chat_streaming_service = chat_streaming_service
        self._polling_interval = polling_interval
        self._jobs: dict[str, BackgroundJob] = {}
        self._job_ids_by_request_id: dict[str, str] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -------------------------------------------------------------------------
    @property
    def poll_interval(self) -> float:
        return self._polling_interval

    # -------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="background-job-worker", daemon=True)
        self._thread.start()

    # -------------------------------------------------------------------------
    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    # -------------------------------------------------------------------------
    def create_chat_job(self, payload: ChatTurnRequest) -> BackgroundJobCreateResponse:
        request_id = payload.request_id or f"chat-{uuid4().hex[:12]}"
        job = self._create_job(
            job_type="chat_turn",
            request_id=request_id,
            input_json=payload.model_copy(update={"request_id": request_id}).model_dump(mode="json"),
        )
        return self._to_create_response(job, "Chat job queued")

    # -------------------------------------------------------------------------
    def _create_job(
        self,
        *,
        job_type: str,
        request_id: str,
        input_json: dict[str, Any],
        parent_job_id: str | None = None,
        max_attempts: int = 1,
    ) -> BackgroundJob:
        with self._lock:
            existing_id = self._job_ids_by_request_id.get(request_id)
            if existing_id is not None:
                return self._jobs[existing_id]
            job = BackgroundJob(
                job_id=f"job_{uuid4().hex[:16]}",
                job_type=job_type,
                request_id=request_id,
                input_json=input_json,
                parent_job_id=parent_job_id,
                max_attempts=max_attempts,
            )
            self._jobs[job.job_id] = job
            self._job_ids_by_request_id[request_id] = job.job_id
            self._append_event_locked(job, "queued", {"request_id": request_id, "job_type": job_type})
            return job

    # -------------------------------------------------------------------------
    def get_job(self, job_id: str) -> BackgroundJobStatusResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._to_status_response(job) if job is not None else None

    # -------------------------------------------------------------------------
    def list_events(self, job_id: str) -> BackgroundJobEventsResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return BackgroundJobEventsResponse(job_id=job_id, events=list(job.events))

    # -------------------------------------------------------------------------
    def cancel_job(self, job_id: str) -> JobCancelResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in {JOB_STATUS_SUCCEEDED, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED}:
                return JobCancelResponse(job_id=job_id, success=False, message="Job cannot be cancelled")
            now = _utc_now()
            job.cancel_requested_at = now
            if job.status == JOB_STATUS_QUEUED:
                job.status = JOB_STATUS_CANCELLED
                job.completed_at = now
                job.status_message = "Cancelled"
            for child in self._jobs.values():
                if child.parent_job_id == job_id:
                    child.cancel_requested_at = now
            self._append_event_locked(job, "cancelled", {"message": "Cancellation requested"})
            return JobCancelResponse(job_id=job_id, success=True, message="Cancellation requested")

    # -------------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            claimed = self._claim_next_job()
            if claimed is None:
                time.sleep(0.1)
                continue
            try:
                asyncio.run(self._execute_job(claimed))
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected background job failure")
                self._fail_job(claimed.job_id, {"message": "Unexpected job failure"})

    # -------------------------------------------------------------------------
    def _claim_next_job(self) -> BackgroundJob | None:
        with self._lock:
            queued = sorted(
                (
                    job
                    for job in self._jobs.values()
                    if job.status == JOB_STATUS_QUEUED
                ),
                key=lambda item: (-item.priority, item.created_at),
            )
            if not queued:
                return None
            job = queued[0]
            now = _utc_now()
            if job.cancel_requested_at is not None:
                job.status = JOB_STATUS_CANCELLED
                job.completed_at = now
                job.status_message = "Cancelled"
                self._append_event_locked(job, "cancelled", {"message": "Cancelled before start"})
                return None
            job.status = JOB_STATUS_RUNNING
            job.started_at = job.started_at or now
            job.last_heartbeat_at = now
            job.attempt_count += 1
            job.progress_percent = max(job.progress_percent or 0, 1)
            job.status_message = "Running"
            self._append_event_locked(job, "started", {"message": "Job started"})
            return job

    # -------------------------------------------------------------------------
    async def _execute_job(self, job: BackgroundJob) -> None:
        if job.job_type == "chat_turn":
            await self._execute_chat_job(job)
            return
        self._fail_job(job.job_id, {"message": f"Unsupported job type: {job.job_type}"})

    # -------------------------------------------------------------------------
    async def _execute_chat_job(self, job: BackgroundJob) -> None:
        payload = ChatTurnRequest.model_validate(job.input_json)
        final_response: dict[str, Any] | None = None
        async for event in self._chat_streaming_service.stream_turn(payload):
            if self._is_cancel_requested(job.job_id):
                self._cancel_running_job(job.job_id)
                return
            self._record_stream_event(job.job_id, event.event, dict(event.data or {}))
            if event.event == "parsed":
                self._heartbeat(job.job_id, 20, "Parsed request")
            elif event.event == "policy":
                self._heartbeat(job.job_id, 35, "Planned execution")
            elif event.event == "tool_call_started":
                self._heartbeat(job.job_id, 55, "Running tools")
            elif event.event == "map_session_created":
                self._heartbeat(job.job_id, 85, "Map session created")
            elif event.event == "final":
                final_response = dict(event.data or {})
        if final_response is None:
            self._fail_job(job.job_id, {"message": "Chat job finished without final response"})
            return
        operation = json_object(final_response.get("operation"))
        if self._operation_failed(operation):
            self._fail_job(
                job.job_id,
                {
                    "message": str(operation.get("message") or "Chat job failed."),
                    "chat_turn_response": final_response,
                    "operation": operation,
                    "map_session": final_response.get("map_session"),
                },
            )
            return
        self._complete_job(
            job.job_id,
            {
                "chat_turn_response": final_response,
                "operation": operation,
                "map_session": final_response.get("map_session"),
            },
        )

    # -------------------------------------------------------------------------
    def _heartbeat(self, job_id: str, progress_percent: int, status_message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.last_heartbeat_at = _utc_now()
            job.progress_percent = progress_percent
            job.status_message = status_message
            self._append_event_locked(
                job,
                "status",
                {"progress_percent": progress_percent, "status_message": status_message},
            )

    # -------------------------------------------------------------------------
    def _record_stream_event(self, job_id: str, event_name: str, payload_json: dict[str, Any]) -> None:
        mapped_name = {
            "tool_call_started": "tool_call",
            "tool_call_completed": "tool_result",
            "final": "completed",
            "map_session_created": "map_session",
        }.get(event_name, event_name)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            self._append_event_locked(job, mapped_name, payload_json)

    # -------------------------------------------------------------------------
    def _complete_job(self, job_id: str, result_json: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job.cancel_requested_at is not None:
                self._cancel_running_job(job_id)
                return
            job.status = JOB_STATUS_SUCCEEDED
            job.result_json = result_json
            job.progress_percent = 100
            job.status_message = "Succeeded"
            job.completed_at = _utc_now()
            self._append_event_locked(job, "completed", {"result_json": result_json})

    # -------------------------------------------------------------------------
    def _fail_job(self, job_id: str, error_json: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job.cancel_requested_at is not None:
                self._cancel_running_job(job_id)
                return
            job.status = JOB_STATUS_FAILED
            job.error_json = error_json
            job.completed_at = _utc_now()
            job.status_message = str(error_json.get("message") or "Failed")
            self._append_event_locked(job, "failed", error_json)

    # -------------------------------------------------------------------------
    def _cancel_running_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JOB_STATUS_CANCELLED
            job.completed_at = _utc_now()
            job.status_message = "Cancelled"
            self._append_event_locked(job, "cancelled", {"message": "Cancelled"})

    # -------------------------------------------------------------------------
    def _is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return bool(job and job.cancel_requested_at is not None)

    # -------------------------------------------------------------------------
    @staticmethod
    def _operation_failed(operation: dict[str, Any]) -> bool:
        return (
            str(operation.get("status") or "").strip().lower() == "failed"
            or str(operation.get("kind") or "").strip().lower() == "error"
        )

    # -------------------------------------------------------------------------
    def _to_create_response(self, job: BackgroundJob, message: str) -> BackgroundJobCreateResponse:
        return BackgroundJobCreateResponse(
            job_id=job.job_id,
            job_type=cast(BackgroundJobType, job.job_type),
            status=cast(BackgroundJobStatus, job.status),
            request_id=job.request_id,
            message=message,
            poll_interval=self._polling_interval,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_status_response(job: BackgroundJob) -> BackgroundJobStatusResponse:
        return BackgroundJobStatusResponse(
            job_id=job.job_id,
            job_type=cast(BackgroundJobType, job.job_type),
            status=cast(BackgroundJobStatus, job.status),
            request_id=job.request_id,
            parent_job_id=job.parent_job_id,
            priority=job.priority,
            progress_percent=job.progress_percent,
            status_message=job.status_message,
            result_json=job.result_json,
            error_json=job.error_json,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            cancel_requested_at=job.cancel_requested_at,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            last_heartbeat_at=job.last_heartbeat_at,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _append_event_locked(job: BackgroundJob, event_type: str, payload_json: dict[str, Any]) -> None:
        job.events.append(
            BackgroundJobEvent(
                job_id=job.job_id,
                event_type=cast(BackgroundJobEventType, event_type),
                sequence=len(job.events) + 1,
                created_at=_utc_now(),
                payload_json=payload_json,
            )
        )
