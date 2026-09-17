from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any, Literal, cast

from server.contracts.chat import ChatStreamEvent, ChatTurnRequest, ChatTurnResponse
from server.contracts.events import RunEvent, RunEventType
from server.contracts.runs import AgentRunCreateRequest
from server.services.agent.native_orchestrator import NativeAgentOrchestrator
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.exceptions import (
    RunAccessError,
    RunConflictError,
    RunNotFoundError,
)
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.llm.errors import LLMConfigurationError

###############################################################################
class ChatStreamingService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        agent_orchestrator: NativeAgentOrchestrator | None = None,
        *,
        lifecycle_service: RunLifecycleService | None = None,
        event_publisher: RunEventPublisher | None = None,
    ) -> None:
        self.agent_orchestrator = agent_orchestrator
        self.lifecycle_service = lifecycle_service
        self.event_publisher = event_publisher
        if lifecycle_service is not None and event_publisher is None:
            raise ValueError(
                "A run event publisher is required for persisted chat streaming."
            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _emit_progress_event(
        queue: asyncio.Queue[ChatStreamEvent],
        event: str,
        data: dict[str, Any],
    ) -> None:
        queue.put_nowait(
            ChatStreamEvent(
                event=cast(
                    Literal[
                        "status",
                        "context_usage",
                        "tool_call_started",
                        "tool_call_completed",
                        "tool_started",
                        "tool_completed",
                        "map_session_created",
                        "stage",
                        "final",
                        "error",
                    ],
                    event,
                ),
                data=data,
            )
        )

    # -------------------------------------------------------------------------
    async def stream_turn(
        self,
        payload: ChatTurnRequest,
        *,
        owner_user_id: str | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        request_id = payload.request_id or ""
        yield ChatStreamEvent(
            event="status",
            data={"message": "received", "request_id": request_id},
        )
        if self.lifecycle_service is not None:
            async for event in self._stream_persisted_turn(
                payload,
                owner_user_id=owner_user_id,
            ):
                yield event
            return

        if self.agent_orchestrator is None:
            yield ChatStreamEvent(
                event="error",
                data={
                    "message": "The persisted agent-run lifecycle is unavailable.",
                    "status": int(HTTPStatus.SERVICE_UNAVAILABLE),
                    "request_id": request_id,
                },
            )
            return

        task: asyncio.Task[ChatTurnResponse] | None = None
        try:
            queue: asyncio.Queue[ChatStreamEvent] = asyncio.Queue()

            task = asyncio.create_task(
                self.agent_orchestrator.run_turn(
                    payload,
                    progress_callback=lambda event, data: self._emit_progress_event(
                        queue,
                        event,
                        data,
                    ),
                )
            )
            while not task.done() or not queue.empty():
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=0.05)
                except TimeoutError:
                    continue
            result = await task
            yield ChatStreamEvent(
                event="final",
                data=self._serialize_chat_turn_response(result),
            )
        except LLMConfigurationError as exc:
            yield ChatStreamEvent(
                event="error",
                data={
                    "message": str(exc),
                    "status": int(HTTPStatus.SERVICE_UNAVAILABLE),
                    "request_id": request_id,
                },
            )
        except ValueError as exc:
            yield ChatStreamEvent(
                event="error",
                data={
                    "message": str(exc) or "Provider unavailable.",
                    "status": int(HTTPStatus.BAD_REQUEST),
                    "request_id": request_id,
                },
            )
        except Exception as exc:
            yield ChatStreamEvent(
                event="error",
                data={
                    "message": str(exc)
                    or "Unexpected server error while streaming response.",
                    "status": int(HTTPStatus.INTERNAL_SERVER_ERROR),
                    "request_id": request_id,
                },
            )
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    # -------------------------------------------------------------------------
    async def _stream_persisted_turn(
        self,
        payload: ChatTurnRequest,
        *,
        owner_user_id: str | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        """Create and observe a persisted run for the NDJSON transport."""

        lifecycle = self.lifecycle_service
        publisher = self.event_publisher
        if lifecycle is None or publisher is None:
            return
        request_id = payload.request_id or ""
        try:
            result, _created = await lifecycle.create_run_with_status(
                payload.conversation_id,
                AgentRunCreateRequest(
                    message=payload.message,
                    client_request_id=payload.request_id,
                    timezone=payload.timezone,
                ),
                schedule=False,
                owner_user_id=owner_user_id,
            )
            yield ChatStreamEvent(
                event="status",
                data={
                    "message": "accepted",
                    "request_id": request_id or result.run_id,
                    "run_id": result.run_id,
                    "run_version": result.run_version,
                },
            )
            response = await lifecycle.execute_run(result.run_id)
            emitted_final = False
            for run_event in publisher.replay(result.run_id):
                translated = self._translate_run_event(run_event)
                if translated is None:
                    continue
                if translated.event == "final":
                    emitted_final = True
                yield translated
            if response is not None and not emitted_final:
                yield ChatStreamEvent(
                    event="final",
                    data=self._serialize_chat_turn_response(response),
                )
            elif response is None:
                snapshot = lifecycle.run_repository.get_run(result.run_id)
                if snapshot is not None and snapshot.error_message:
                    yield ChatStreamEvent(
                        event="error",
                        data={
                            "message": snapshot.error_message,
                            "status": int(HTTPStatus.SERVICE_UNAVAILABLE),
                            "request_id": request_id or result.run_id,
                            "run_id": result.run_id,
                        },
                    )
        except RunNotFoundError as exc:
            yield self._error_event(
                request_id,
                str(exc) or "Conversation not found.",
                HTTPStatus.NOT_FOUND,
            )
        except RunAccessError as exc:
            yield self._error_event(
                request_id,
                str(exc) or "Conversation access denied.",
                HTTPStatus.FORBIDDEN,
            )
        except RunConflictError as exc:
            yield self._error_event(
                request_id,
                str(exc) or "Conversation already has an active run.",
                HTTPStatus.CONFLICT,
            )
        except ValueError as exc:
            yield self._error_event(
                request_id,
                str(exc) or "Provider unavailable.",
                HTTPStatus.BAD_REQUEST,
            )
        except Exception:
            yield self._error_event(
                request_id,
                "Unexpected server error while streaming response.",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _translate_run_event(event: RunEvent) -> ChatStreamEvent | None:
        payload = dict(event.payload or {})
        if event.type == RunEventType.PROGRESS:
            return ChatStreamEvent(event="stage", data=payload)
        if event.type == RunEventType.CONTEXT_USAGE:
            return ChatStreamEvent(event="context_usage", data=payload)
        if event.type == RunEventType.TOOL_STARTED:
            return ChatStreamEvent(event="tool_started", data=payload)
        if event.type == RunEventType.TOOL_COMPLETED:
            return ChatStreamEvent(event="tool_completed", data=payload)
        if event.type == RunEventType.MAP_PREPARED:
            return ChatStreamEvent(event="map_session_created", data=payload)
        if event.type in {RunEventType.COMPLETED, RunEventType.CLARIFICATION_NEEDED}:
            if "assistant_message" not in payload and "content" in payload:
                payload["assistant_message"] = payload.get("content")
            payload.pop("content", None)
            return ChatStreamEvent(event="final", data=payload)
        if event.type == RunEventType.ERROR:
            return ChatStreamEvent(event="error", data=payload)
        if event.type == RunEventType.CANCELLED:
            payload.setdefault("message", "The agent run was cancelled.")
            payload.setdefault("status", int(HTTPStatus.CONFLICT))
            return ChatStreamEvent(event="error", data=payload)
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _error_event(
        request_id: str,
        message: str,
        status: HTTPStatus,
    ) -> ChatStreamEvent:
        return ChatStreamEvent(
            event="error",
            data={
                "message": message,
                "status": int(status),
                "request_id": request_id,
            },
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _serialize_chat_turn_response(response: ChatTurnResponse) -> dict[str, Any]:
        return response.model_dump(mode="json", exclude_none=True)
