from __future__ import annotations

import asyncio

from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision
from server.domain.chat import ChatTurnRequest, ChatTurnResponse
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedIntent,
    TurnParseResult,
)
from server.services.chat.streaming import ChatStreamingService
from server.services.llm.errors import LLMConfigurationError


class _FakeAgentOrchestrator:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    async def run_turn(self, payload: ChatTurnRequest) -> ChatTurnResponse:
        if self.mode == "llm_error":
            raise LLMConfigurationError("provider unavailable")
        if self.mode == "value_error":
            raise ValueError("bad request")

        return ChatTurnResponse(
            request_id=payload.request_id or "chat-req",
            session_id=7,
            assistant_message="hello world",
            turn_contract=TurnParseResult(
                user_text="show weather",
                conversation_context=ConversationContextSnapshot(),
                task_class="direct_query",
                normalized_intent=NormalizedIntent(
                    intent_id="weather",
                    intent_label="Weather",
                ),
            ),
            decision=PolicyDecision(
                plan=ExecutionPlan(
                    state="direct_response",
                    mode="direct_text",
                    intent_id="weather",
                ),
                trace=DecisionTrace(steps=["test"]),
            ),
            tool_payload=(
                {
                    "execution": "ok",
                    "map_session": {"overlays": [{"id": "a"}, {"id": "b"}]},
                    "satellite_imagery": {"enabled": True},
                }
                if self.mode == "tool"
                else None
            ),
            memory_snapshot={"k": "v"},
        )


async def _collect_events(mode: str):
    service = ChatStreamingService(_FakeAgentOrchestrator(mode))  # type: ignore[arg-type]
    payload = ChatTurnRequest(message="hi", request_id="chat-123")
    events = []
    async for event in service.stream_turn(payload):
        events.append(event)
    return events


def test_stream_turn_happy_path_sequence() -> None:
    events = asyncio.run(_collect_events("ok"))
    assert [event.event for event in events] == ["status", "assistant_delta", "assistant_delta", "final"]
    assert events[-1].data["request_id"] == "chat-123"


def test_stream_turn_emits_tool_status_when_payload_exists() -> None:
    events = asyncio.run(_collect_events("tool"))
    assert [event.event for event in events] == ["status", "assistant_delta", "assistant_delta", "tool_status", "final"]
    assert events[3].data["available"] is True
    assert events[3].data["overlay_count"] == 2


def test_stream_turn_llm_configuration_error() -> None:
    events = asyncio.run(_collect_events("llm_error"))
    assert events[-1].event == "error"
    assert events[-1].data["status"] == 503


def test_stream_turn_value_error() -> None:
    events = asyncio.run(_collect_events("value_error"))
    assert events[-1].event == "error"
    assert events[-1].data["status"] == 400


def test_stream_turn_final_payload_matches_contract_shape() -> None:
    events = asyncio.run(_collect_events("ok"))
    final = events[-1]
    assert final.event == "final"
    assert final.data["session_id"] == 7
    assert final.data["turn_contract"]["normalized_intent"]["intent_id"] == "weather"
    assert final.data["decision"]["plan"]["state"] == "direct_response"