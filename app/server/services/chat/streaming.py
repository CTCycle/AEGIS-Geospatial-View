from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any, Literal, cast

from server.contracts.chat import ChatStreamEvent, ChatTurnRequest, ChatTurnResponse
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.llm.errors import LLMConfigurationError

###############################################################################
class ChatStreamingService:

    # -------------------------------------------------------------------------
    def __init__(self, agent_orchestrator: AgentOrchestrator) -> None:
        self.agent_orchestrator = agent_orchestrator

    # -------------------------------------------------------------------------
    @staticmethod
    def _emit_progress_event(
        queue: asyncio.Queue[ChatStreamEvent],
        event: str,
        data: dict[str, Any],
    ) -> None:
        queue.put_nowait(ChatStreamEvent(event=cast(Literal["status", "parsed", "policy", "tool_call_started", "tool_call_completed", "map_session_created", "final", "error"], event), data=data))

    # -------------------------------------------------------------------------
    async def stream_turn(self, payload: ChatTurnRequest) -> AsyncIterator[ChatStreamEvent]:
        request_id = payload.request_id or ""
        yield ChatStreamEvent(
            event="status",
            data={"message": "received", "request_id": request_id},
        )
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
                    "message": str(exc) or "Unexpected server error while streaming response.",
                    "status": int(HTTPStatus.INTERNAL_SERVER_ERROR),
                    "request_id": request_id,
                },
            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _serialize_chat_turn_response(response: ChatTurnResponse) -> dict[str, Any]:
        return {
            "conversation_id": response.conversation_id,
            "request_id": response.request_id,
            "assistant_message": response.assistant_message,
            "turn_contract": response.turn_contract.model_dump(mode="json"),
            "decision": response.decision.model_dump(mode="json"),
            "operation": response.operation.model_dump(mode="json")
            if response.operation is not None
            else None,
            "map_session": response.map_session.model_dump(mode="json")
            if response.map_session is not None
            else None,
            "tool_payload": response.tool_payload,
            "memory_snapshot": response.memory_snapshot,
            "context_usage": response.context_usage.model_dump(mode="json")
            if response.context_usage is not None
            else None,
        }
