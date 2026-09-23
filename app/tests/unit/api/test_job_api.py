from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from threading import Event
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.chat import get_job_service as get_chat_job_service
from server.api.chat import router as chat_router
from server.api.jobs import get_job_service as get_jobs_job_service
from server.api.jobs import router as jobs_router
from server.contracts.chat import ChatStreamEvent, ChatTurnRequest
from server.services.jobs import BackgroundJobService


class _ChatStreamingStub:
    async def stream_turn(self, payload: ChatTurnRequest) -> AsyncIterator[ChatStreamEvent]:
        yield ChatStreamEvent(event="status", data={"request_id": payload.request_id})
        yield ChatStreamEvent(
            event="context_usage",
            data={"request_id": payload.request_id, "usage_percent": 12},
        )
        yield ChatStreamEvent(
            event="stage",
            data={"stage": "context_assembly", "request_id": payload.request_id},
        )
        yield ChatStreamEvent(
            event="final",
            data={
                "request_id": payload.request_id,
                "conversation_id": payload.conversation_id,
                "assistant_message": "Background job completed.",
                "operation": {
                    "kind": "direct_answer",
                    "status": "success",
                    "message": "Background job completed.",
                },
                "map_session": None,
                "tool_payload": None,
                "memory_snapshot": {},
                "context_revision": 1,
                "presentation_status": "not_requested",
                "tool_results": [],
                "context_usage": None,
            },
        )


class _ErrorChatStreamingStub(_ChatStreamingStub):
    async def stream_turn(self, payload: ChatTurnRequest) -> AsyncIterator[ChatStreamEvent]:
        _ = payload
        yield ChatStreamEvent(
            event="error",
            data={
                "message": "api-key=sk-sensitive https://provider.invalid/private",
                "status": 503,
            },
        )


class _BlockingChatStreamingStub(_ChatStreamingStub):
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    async def stream_turn(self, payload: ChatTurnRequest) -> AsyncIterator[ChatStreamEvent]:
        self.started.set()
        yield ChatStreamEvent(event="status", data={"request_id": payload.request_id})
        await asyncio.to_thread(self.release.wait)
        yield ChatStreamEvent(
            event="final",
            data={
                "request_id": payload.request_id,
                "conversation_id": payload.conversation_id,
                "assistant_message": "Background job completed.",
                "operation": {
                    "kind": "direct_answer",
                    "status": "success",
                    "message": "Background job completed.",
                },
                "map_session": None,
                "tool_payload": None,
                "memory_snapshot": {},
                "context_revision": 1,
                "presentation_status": "not_requested",
                "tool_results": [],
                "context_usage": None,
            },
        )


def _create_app(service: BackgroundJobService) -> FastAPI:
    application = FastAPI()
    application.include_router(chat_router, prefix="/api")
    application.include_router(jobs_router, prefix="/api")
    application.dependency_overrides[get_chat_job_service] = lambda: service
    application.dependency_overrides[get_jobs_job_service] = lambda: service
    return application


@contextmanager
def _running_client(
    streaming_service: _ChatStreamingStub,
) -> Iterator[tuple[TestClient, BackgroundJobService]]:
    service = BackgroundJobService(
        chat_streaming_service=streaming_service,
        polling_interval=0.01,
    )
    service.start()
    try:
        with TestClient(_create_app(service)) as client:
            yield client, service
    finally:
        if isinstance(streaming_service, _BlockingChatStreamingStub):
            streaming_service.release.set()
        service.stop()


def _wait_for_terminal_job(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Job {job_id} did not reach a terminal state")


def _create_chat_job(client: TestClient, request_id: str) -> dict[str, Any]:
    response = client.post(
        "/api/chat/jobs",
        json={
            "conversation_id": "conversation-t1-07",
            "message": "Answer using the background job path.",
            "request_id": request_id,
        },
    )
    assert response.status_code == 202
    return response.json()


def test_mounted_job_api_completes_with_progress_and_ordered_events() -> None:
    with _running_client(_ChatStreamingStub()) as (client, _service):
        created = _create_chat_job(client, "t1-07-api-success")
        assert created["status"] == "queued"

        job = _wait_for_terminal_job(client, str(created["job_id"]))
        assert job["status"] == "succeeded"
        assert job["progress_percent"] == 100
        assert (
            job["result_json"]["chat_turn_response"]["assistant_message"]
            == "Background job completed."
        )

        events_response = client.get(f"/api/jobs/{created['job_id']}/events")
        assert events_response.status_code == 200
        events = events_response.json()["events"]
        event_types = [event["event_type"] for event in events]
        sequences = [event["sequence"] for event in events]
        assert event_types[0:2] == ["queued", "started"]
        assert "status" in event_types
        assert event_types[-1] == "completed"
        assert sequences == list(range(1, len(sequences) + 1))
        status_events = [event for event in events if event["event_type"] == "status"]
        assert any(
            event["payload_json"].get("source_event") == "context_usage"
            for event in status_events
        )
        assert any(
            event["payload_json"].get("source_event") == "stage"
            for event in status_events
        )
        assert (
            events[-1]["payload_json"]["result_json"]["operation"]["status"]
            == "success"
        )


def test_mounted_job_api_cancels_a_running_job_cooperatively() -> None:
    streaming_service = _BlockingChatStreamingStub()
    with _running_client(streaming_service) as (client, _service):
        created = _create_chat_job(client, "t1-07-api-cancel")
        assert streaming_service.started.wait(timeout=3)

        cancel_response = client.post(f"/api/jobs/{created['job_id']}/cancel")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["success"] is True

        streaming_service.release.set()
        job = _wait_for_terminal_job(client, str(created["job_id"]))
        assert job["status"] == "cancelled"
        events = client.get(f"/api/jobs/{created['job_id']}/events").json()["events"]
        assert events[-1]["event_type"] == "cancelled"


def test_mounted_job_api_returns_404_for_unknown_jobs() -> None:
    with _running_client(_ChatStreamingStub()) as (client, _service):
        assert client.get("/api/jobs/job-missing").status_code == 404
        assert client.get("/api/jobs/job-missing/events").status_code == 404
        assert client.post("/api/jobs/job-missing/cancel").status_code == 404


def test_mounted_job_api_sanitizes_stream_error_events() -> None:
    with _running_client(_ErrorChatStreamingStub()) as (client, _service):
        created = _create_chat_job(client, "t1-07-api-safe-error")
        job = _wait_for_terminal_job(client, str(created["job_id"]))

        assert job["status"] == "failed"
        assert job["error_json"] == {
            "message": "Background chat job failed. [RuntimeError]",
            "status": 503,
        }
        assert "sk-sensitive" not in str(job["error_json"])
        events = client.get(f"/api/jobs/{created['job_id']}/events").json()["events"]
        assert events[-1]["event_type"] == "failed"
        assert "provider.invalid" not in str(events)


def test_mounted_job_api_does_not_persist_jobs_across_service_restart() -> None:
    with _running_client(_ChatStreamingStub()) as (first_client, _first_service):
        created = _create_chat_job(first_client, "t1-07-api-restart")
        job = _wait_for_terminal_job(first_client, str(created["job_id"]))
        assert job["status"] == "succeeded"

    second_service = BackgroundJobService(
        chat_streaming_service=_ChatStreamingStub(),
        polling_interval=0.01,
    )
    with TestClient(_create_app(second_service)) as second_client:
        response = second_client.get(f"/api/jobs/{created['job_id']}")
        assert response.status_code == 404
