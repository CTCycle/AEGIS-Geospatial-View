from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision
from server.domain.chat import (
    ChatOperationResult,
    ChatStreamEvent,
    ChatTurnRequest,
    ChatTurnResponse,
)
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TurnParseResult,
)
from server.domain.geographics import MapSession
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
        task_class="map_search",
        location_signals=[
            LocationSignal(
                signal_type="city",
                raw_value="Rome",
                normalized_value="Rome",
                latitude=41.9028,
                longitude=12.4964,
                confidence=0.9,
            )
        ],
        normalized_action=NormalizedAction(
            action_id="weather",
            action_label="Weather",
            requires_location=True,
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
    map_session: MapSession | None = None,
    operation: ChatOperationResult | None = None,
) -> ChatTurnResponse:
    return ChatTurnResponse(
        request_id=payload.request_id or "chat-req",
        session_id=7,
        assistant_message="hello world",
        turn_contract=turn_contract(),
        decision=policy_decision(),
        operation=operation,
        tool_payload=tool_payload,
        map_session=map_session,
        memory_snapshot={"k": "v"},
    )


class ToolStatusAgentOrchestrator:
    async def run_turn(self, payload: ChatTurnRequest) -> ChatTurnResponse:
        return chat_response(
            payload,
            tool_payload={
                "tool_calls": [
                    {"id": "tool-1", "name": "execute_geospatial_capability", "arguments": {"capability_id": "weather_overlay"}},
                ],
                "tool_results": [
                    {
                        "tool_call_id": "tool-1",
                        "name": "execute_geospatial_capability",
                        "content": {
                            "ok": True,
                            "data": {"map_session": {"overlay_ids": ["weather_overlay"]}},
                            "error": None,
                            "metadata": {},
                        },
                        "is_error": False,
                        "error": None,
                    }
                ],
            },
            map_session=MapSession(
                session_id="map-1",
                resolved_location={
                    "label": "Rome",
                    "latitude": 41.9028,
                    "longitude": 12.4964,
                    "source": "resolver",
                    "confidence": 0.9,
                },
                basemap_id="osm_default",
                overlay_ids=["weather_overlay"],
                viewport={
                    "center_latitude": 41.9028,
                    "center_longitude": 12.4964,
                    "radius_m": 2500.0,
                },
                basemap={"id": "osm_default", "label": "OpenStreetMap"},
                overlays=[{"id": "weather_overlay", "label": "Weather Overlay"}],
                center={"latitude": 41.9028, "longitude": 12.4964},
                bounds=[12.0, 41.0, 13.0, 42.0],
            ),
            operation=ChatOperationResult(
                kind="map_session",
                status="success",
                message="hello world",
            ),
        )


class FinalMessageAgentOrchestrator:
    async def run_turn(self, payload: ChatTurnRequest) -> ChatTurnResponse:
        return chat_response(
            payload,
            operation=ChatOperationResult(
                kind="direct_answer",
                status="success",
                message="hello world",
            ),
        )


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


def test_stream_turn_emits_lifecycle_and_map_events() -> None:
    events = stream_events(ToolStatusAgentOrchestrator())

    assert [event.event for event in events] == [
        "status",
        "parsed",
        "policy",
        "tool_call_started",
        "tool_call_completed",
        "map_session_created",
        "final",
    ]
    assert events[3].data["name"] == "execute_geospatial_capability"
    assert events[4].data["ok"] is True
    assert events[5].data["map_session"]["resolved_location"]["label"] == "Rome"


def test_stream_turn_final_assistant_event_emits_final_payload() -> None:
    events = stream_events(FinalMessageAgentOrchestrator())

    assert [event.event for event in events] == [
        "status",
        "parsed",
        "policy",
        "final",
    ]
    assert events[-1].data["session_id"] == 7
    assert (
        events[-1].data["turn_contract"]["normalized_action"]["action_id"] == "weather"
    )
    assert events[-1].data["decision"]["plan"]["state"] == "direct_response"
    assert events[-1].data["operation"]["kind"] == "direct_answer"
    assert not any(event.event == "assistant_delta" for event in events)


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
