from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from tests.conftest import run_async_in_thread

from server.contracts.chat import (
    ChatOperationResult,
    ChatStreamEvent,
    ChatTurnRequest,
    ChatTurnResponse,
)
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentGoal,
    CapabilityRoute,
    CompletionContract,
)
from server.domain.agent.conversation import ConversationState
from server.services.chat.streaming import ChatStreamingService
from server.services.llm.errors import LLMConfigurationError


###############################################################################
async def collect_stream_events(
    stream: AsyncIterator[ChatStreamEvent],
) -> list[ChatStreamEvent]:
    return [event async for event in stream]


###############################################################################
def native_response(payload: ChatTurnRequest) -> ChatTurnResponse:
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="answer",
        presentation="text",
        requires_location=False,
    )
    return ChatTurnResponse(
        request_id=payload.request_id or "chat-req",
        conversation_id=payload.conversation_id,
        assistant_message="hello world",
        operation=ChatOperationResult(
            kind="direct_answer",
            status="success",
            message="hello world",
        ),
        context_revision=0,
        route=route,
        goal=AgentGoal(
            goal=payload.message,
            task_mode="answer",
            presentation="text",
            operation="answer",
            requires_location=False,
        ),
        completion_contract=CompletionContract(operation="answer"),
        conversation_state=ConversationState.empty(payload.conversation_id),
    )


###############################################################################
class ToolStatusAgentOrchestrator:

    # -------------------------------------------------------------------------
    async def run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback: Callable[[str, dict[str, Any]], None],
    ) -> ChatTurnResponse:
        progress_callback("stage", {"stage": "route_request"})
        progress_callback(
            "tool_call_started", {"name": "execute_geospatial_capability"}
        )
        progress_callback(
            "tool_call_completed",
            {"name": "execute_geospatial_capability", "status": "success"},
        )
        progress_callback(
            "map_session_created",
            {"map_session": {"session_id": "map-1"}},
        )
        return native_response(payload)


###############################################################################
class ContextUsageAgentOrchestrator:

    # -------------------------------------------------------------------------
    async def run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback: Callable[[str, dict[str, Any]], None],
    ) -> ChatTurnResponse:
        progress_callback(
            "context_usage",
            {
                "phase": "native_loop",
                "context_usage": {
                    "estimated_input_tokens": 700,
                    "selected_context_window": 4096,
                    "model_context_limit": 4096,
                    "usage_percent": 17.1,
                    "provider": "test",
                    "model": "runtime-model",
                    "usage_source": "estimated",
                },
            },
        )
        return native_response(payload)


###############################################################################
class ConfigurationErrorAgentOrchestrator:

    # -------------------------------------------------------------------------
    async def run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback: Callable[[str, dict[str, Any]], None],
    ) -> ChatTurnResponse:
        del payload, progress_callback
        raise LLMConfigurationError("provider unavailable")


###############################################################################
class UnexpectedErrorAgentOrchestrator:

    # -------------------------------------------------------------------------
    async def run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback: Callable[[str, dict[str, Any]], None],
    ) -> ChatTurnResponse:
        del payload, progress_callback
        raise RuntimeError("boom")


###############################################################################
class CancellableAgentOrchestrator:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    # -------------------------------------------------------------------------
    async def run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback: Callable[[str, dict[str, Any]], None],
    ) -> ChatTurnResponse:
        del payload, progress_callback
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


###############################################################################
def stream_events(agent_orchestrator: object) -> list[ChatStreamEvent]:
    service = ChatStreamingService(agent_orchestrator)  # type: ignore[arg-type]
    payload = ChatTurnRequest(
        conversation_id="test-conversation", message="hi", request_id="chat-123"
    )
    return run_async_in_thread(collect_stream_events(service.stream_turn(payload)))


###############################################################################
async def cancel_stream_and_check_orchestrator() -> bool:
    orchestrator = CancellableAgentOrchestrator()
    service = ChatStreamingService(orchestrator)  # type: ignore[arg-type]
    payload = ChatTurnRequest(
        conversation_id="test-conversation", message="hi", request_id="chat-123"
    )
    consumer = asyncio.create_task(consume_stream(service, payload))
    await orchestrator.started.wait()
    consumer.cancel()
    await asyncio.gather(consumer, return_exceptions=True)
    return orchestrator.cancelled


###############################################################################
async def consume_stream(
    service: ChatStreamingService,
    payload: ChatTurnRequest,
) -> None:
    async for _event in service.stream_turn(payload):
        pass


###############################################################################
def test_stream_turn_emits_native_lifecycle_and_map_events() -> None:
    events = stream_events(ToolStatusAgentOrchestrator())

    assert [event.event for event in events] == [
        "status",
        "stage",
        "tool_call_started",
        "tool_call_completed",
        "map_session_created",
        "final",
    ]
    assert events[2].data["name"] == "execute_geospatial_capability"
    assert events[3].data["status"] == "success"
    assert events[-1].data["route"]["primary_domain"] == "data_retrieval"
    assert "turn_contract" not in events[-1].data
    assert "decision" not in events[-1].data


###############################################################################
def test_stream_turn_emits_context_usage_before_final_event() -> None:
    events = stream_events(ContextUsageAgentOrchestrator())

    assert [event.event for event in events] == ["status", "context_usage", "final"]
    assert events[1].data["phase"] == "native_loop"
    assert events[1].data["context_usage"]["usage_percent"] == 17.1


###############################################################################
def test_stream_turn_configuration_error_maps_to_service_unavailable() -> None:
    events = stream_events(ConfigurationErrorAgentOrchestrator())

    assert events[-1].event == "error"
    assert events[-1].data["status"] == 503


###############################################################################
def test_stream_turn_unexpected_exception_maps_to_internal_error() -> None:
    events = stream_events(UnexpectedErrorAgentOrchestrator())

    assert events[-1].event == "error"
    assert events[-1].data["status"] == 500


###############################################################################
def test_stream_turn_cancels_backend_work_when_consumer_disconnects() -> None:
    assert run_async_in_thread(cancel_stream_and_check_orchestrator()) is True
