from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision
from server.domain.chat import ChatStreamEvent, ChatTurnRequest, ChatTurnResponse
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedAction,
    TurnParseResult,
)
from server.services.chat.streaming import ChatStreamingService
from server.services.llm.errors import LLMConfigurationError


async def collect_stream_events(
    stream: AsyncIterator[ChatStreamEvent],
) -> list[ChatStreamEvent]:
    return [event async for event in stream]


def turn_contract() -> TurnParseResult:
    return TurnParseResult(
        user_text="show weather",
        conversation_context=ConversationContextSnapshot(),
        task_class="direct_query",
        normalized_action=NormalizedAction(
            action_id="weather",
            action_label="Weather",
        ),
    )


def policy_decision() -> PolicyDecision:
    return PolicyDecision(
        plan=ExecutionPlan(
            state="direct_response",
            mode="direct_text",
            action_id="weather",
        ),
        trace=DecisionTrace(steps=["test"]),
    )


def chat_response(
    payload: ChatTurnRequest,
    *,
    tool_payload: dict[str, object] | None = None,
) -> ChatTurnResponse:
    return ChatTurnResponse(
        request_id=payload.request_id or "chat-req",
        session_id=7,
        assistant_message="hello world",
        turn_contract=turn_contract(),
        decision=policy_decision(),
        tool_payload=tool_payload,
        memory_snapshot={"k": "v"},
    )


class ToolStatusAgentOrchestrator:
    async def run_turn(self, payload: ChatTurnRequest) -> ChatTurnResponse:
        return chat_response(
            payload,
            tool_payload={
                "execution": "ok",
                "map_session": {"overlays": [{"id": "a"}, {"id": "b"}]},
                "satellite_imagery": {"enabled": True},
            },
        )


class FinalMessageAgentOrchestrator:
    async def run_turn(self, payload: ChatTurnRequest) -> ChatTurnResponse:
        return chat_response(payload)


class ConfigurationErrorAgentOrchestrator:
    async def run_turn(self, payload: ChatTurnRequest) -> ChatTurnResponse:
        raise LLMConfigurationError("provider unavailable")


class UnexpectedErrorAgentOrchestrator:
    async def run_turn(self, payload: ChatTurnRequest) -> ChatTurnResponse:
        raise RuntimeError("boom")


def stream_events(agent_orchestrator: object) -> list[ChatStreamEvent]:
    service = ChatStreamingService(agent_orchestrator)  # type: ignore[arg-type]
    payload = ChatTurnRequest(message="hi", request_id="chat-123")
    return asyncio.run(collect_stream_events(service.stream_turn(payload)))


def test_stream_turn_emits_tool_status_event() -> None:
    events = stream_events(ToolStatusAgentOrchestrator())

    assert "tool_status" in [event.event for event in events]
    tool_status = next(event for event in events if event.event == "tool_status")
    assert tool_status.data["available"] is True
    assert tool_status.data["overlay_count"] == 2


def test_stream_turn_final_assistant_event_emits_final_payload() -> None:
    events = stream_events(FinalMessageAgentOrchestrator())

    assert [event.event for event in events] == [
        "status",
        "assistant_delta",
        "assistant_delta",
        "final",
    ]
    assert events[-1].data["session_id"] == 7
    assert (
        events[-1].data["turn_contract"]["normalized_action"]["action_id"] == "weather"
    )
    assert events[-1].data["decision"]["plan"]["state"] == "direct_response"


def test_stream_turn_llm_configuration_error_maps_to_error_event() -> None:
    events = stream_events(ConfigurationErrorAgentOrchestrator())

    assert events[-1].event == "error"
    assert events[-1].data["status"] == 503


def test_stream_turn_unexpected_exception_maps_to_500_error_event() -> None:
    events = stream_events(UnexpectedErrorAgentOrchestrator())

    assert events[-1].event == "error"
    assert events[-1].data["status"] == 500


def test_streaming_service_test_file_contains_no_nested_functions() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
    nested_functions: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                nested_functions.append(child.name)

    assert nested_functions == []
