from __future__ import annotations

import asyncio
import time
from threading import Event, Thread
from collections.abc import AsyncIterator

from server.common.constants import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_SUCCEEDED,
)
from server.contracts.chat import ChatStreamEvent, ChatTurnRequest
from server.services.jobs import BackgroundJobService

###############################################################################
class _ChatStreamingStub:

    # -------------------------------------------------------------------------
    async def stream_turn(self, payload: ChatTurnRequest):
        yield ChatStreamEvent(event="status", data={"request_id": payload.request_id})
        yield ChatStreamEvent(
            event="final",
            data={
                "request_id": payload.request_id,
                "conversation_id": payload.conversation_id,
                "assistant_message": "done",
                "operation": {
                    "kind": "direct_answer",
                    "status": "success",
                    "message": "done",
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

###############################################################################
class _MapSessionStub:
    compliance_warnings: list[str] = []
    overlay_ids: list[str] = []

    # -------------------------------------------------------------------------
    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return {"conversation_id": "conversation-test"}

###############################################################################
async def _map_runner(payload):  # noqa: ANN001
    _ = payload
    return _MapSessionStub()

###############################################################################
class _ChatStreamingFailureStub:

    # -------------------------------------------------------------------------
    async def stream_turn(self, payload: ChatTurnRequest):
        yield ChatStreamEvent(
            event="final",
            data={
                "request_id": payload.request_id,
                "conversation_id": payload.conversation_id,
                "assistant_message": "failed",
                "operation": {
                    "kind": "error",
                    "status": "failed",
                    "message": "parser unavailable",
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

###############################################################################
class _UnexpectedFailureStub:

    # -------------------------------------------------------------------------
    async def stream_turn(self, payload: ChatTurnRequest):
        _ = payload
        raise RuntimeError(
            "api-key=sk-test https://provider.invalid/v1 C:\\private\\settings.env"
        )
        yield  # pragma: no cover

###############################################################################
class _BlockingChatStreamingStub:

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    # -------------------------------------------------------------------------
    async def stream_turn(
        self, payload: ChatTurnRequest
    ) -> AsyncIterator[ChatStreamEvent]:
        self.started.set()
        yield ChatStreamEvent(event="status", data={"request_id": payload.request_id})
        await asyncio.to_thread(self.release.wait)
        yield ChatStreamEvent(
            event="final",
            data={
                "request_id": payload.request_id,
                "conversation_id": payload.conversation_id,
                "assistant_message": "done",
                "operation": {
                    "kind": "direct_answer",
                    "status": "success",
                    "message": "done",
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

###############################################################################
def _build_service() -> BackgroundJobService:
    return BackgroundJobService(
        chat_streaming_service=_ChatStreamingStub(),
        polling_interval=1.0,
    )

###############################################################################
def test_create_chat_job_is_idempotent() -> None:
    service = _build_service()
    request = ChatTurnRequest(
        conversation_id="test-conversation", message="hello", request_id="req-1"
    )
    first = service.create_chat_job(request)
    second = service.create_chat_job(request)
    assert first.job_id == second.job_id
    assert first.status == JOB_STATUS_QUEUED

###############################################################################
def test_cancel_queued_job_marks_it_cancelled() -> None:
    service = _build_service()
    created = service.create_chat_job(
        ChatTurnRequest(
            conversation_id="test-conversation", message="hello", request_id="req-2"
        )
    )
    cancelled = service.cancel_job(created.job_id)
    status = service.get_job(created.job_id)
    assert cancelled is not None and cancelled.success is True
    assert status is not None and status.status == JOB_STATUS_CANCELLED

###############################################################################
def test_worker_completes_chat_job() -> None:
    service = _build_service()
    service.start()
    created = service.create_chat_job(
        ChatTurnRequest(
            conversation_id="test-conversation", message="hello", request_id="req-3"
        )
    )
    deadline = time.time() + 2
    status = service.get_job(created.job_id)
    while (
        status is not None
        and status.status not in {JOB_STATUS_SUCCEEDED, JOB_STATUS_CANCELLED}
        and time.time() < deadline
    ):
        time.sleep(0.05)
        status = service.get_job(created.job_id)
    service.stop()
    assert status is not None
    assert status.status == JOB_STATUS_SUCCEEDED

###############################################################################
def test_worker_fails_chat_job_when_final_operation_failed() -> None:
    service = BackgroundJobService(
        chat_streaming_service=_ChatStreamingFailureStub(),
        polling_interval=1.0,
    )
    service.start()
    created = service.create_chat_job(
        ChatTurnRequest(
            conversation_id="test-conversation", message="hello", request_id="req-4"
        )
    )
    deadline = time.time() + 2
    status = service.get_job(created.job_id)
    while (
        status is not None
        and status.status not in {JOB_STATUS_FAILED, JOB_STATUS_CANCELLED}
        and time.time() < deadline
    ):
        time.sleep(0.05)
        status = service.get_job(created.job_id)
    service.stop()
    assert status is not None
    assert status.status == JOB_STATUS_FAILED
    assert status.error_json is not None
    assert status.error_json["operation"]["status"] == "failed"

###############################################################################
def test_worker_sanitizes_unexpected_exception_details() -> None:
    service = BackgroundJobService(
        chat_streaming_service=_UnexpectedFailureStub(),
        polling_interval=1.0,
    )
    service.start()
    created = service.create_chat_job(
        ChatTurnRequest(
            conversation_id="test-conversation", message="hello", request_id="req-5"
        )
    )
    deadline = time.time() + 2
    status = service.get_job(created.job_id)
    while (
        status is not None
        and status.status not in {JOB_STATUS_FAILED, JOB_STATUS_CANCELLED}
        and time.time() < deadline
    ):
        time.sleep(0.05)
        status = service.get_job(created.job_id)
    service.stop()

    assert status is not None
    assert status.status == JOB_STATUS_FAILED
    assert status.error_json == {"message": "Unexpected job failure"}

###############################################################################
def test_stop_waits_for_active_job_and_joins_worker() -> None:
    streaming_stub = _BlockingChatStreamingStub()
    service = BackgroundJobService(
        chat_streaming_service=streaming_stub,
        polling_interval=1.0,
    )
    service.start()
    created = service.create_chat_job(
        ChatTurnRequest(
            conversation_id="test-conversation",
            message="hello",
            request_id="req-shutdown",
        )
    )
    stop_returned = Event()
    stopper = Thread(target=lambda: (service.stop(), stop_returned.set()))

    try:
        assert streaming_stub.started.wait(timeout=2)
        stopper.start()
        assert not stop_returned.wait(timeout=2.2)
    finally:
        streaming_stub.release.set()
        if stopper.ident is not None:
            stopper.join(timeout=3)

    assert not stopper.is_alive()
    assert stop_returned.is_set()
    worker = service._thread
    assert worker is not None and not worker.is_alive()
    status = service.get_job(created.job_id)
    assert status is not None and status.status == JOB_STATUS_SUCCEEDED
