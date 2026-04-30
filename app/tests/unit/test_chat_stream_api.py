from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from fastapi import status

from server.api import chat
from server.domain.agent.decision import ExecutionPlan, PolicyDecision
from server.domain.chat import ChatTurnRequest, ChatTurnResponse
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedIntent,
    TemporalSignal,
    TurnParseResult,
)


def _collect_lines(stream) -> list[str]:  # noqa: ANN001
    async def _collect() -> list[str]:
        return [line async for line in stream]

    return asyncio.run(_collect())


def _turn_contract() -> TurnParseResult:
    return TurnParseResult(
        user_text="hello",
        conversation_context=ConversationContextSnapshot(),
        task_class="general_question",
        normalized_intent=NormalizedIntent(
            intent_id="general_question",
            intent_label="General question",
            requires_location=False,
        ),
        temporal_signal=TemporalSignal(),
        parser_confidence=1.0,
    )


def _decision() -> PolicyDecision:
    return PolicyDecision(
        plan=ExecutionPlan(state="direct_response", intent_id="general_question")
    )


def test_chat_stream_success_ndjson_event_sequence() -> None:
    async def _run_turn(_: ChatTurnRequest) -> ChatTurnResponse:
        return ChatTurnResponse(
            request_id="chat-test",
            session_id=1,
            assistant_message="hello world",
            turn_contract=_turn_contract(),
            decision=_decision(),
            tool_payload={"execution": "map_search", "map_session": {"overlays": []}},
        )

    runtime = SimpleNamespace(agent_orchestrator=SimpleNamespace(run_turn=_run_turn))
    stream = chat._chat_event_stream(ChatTurnRequest(message="hello"), runtime)
    lines = _collect_lines(stream)
    events = [json.loads(entry.strip())["event"] for entry in lines]
    assert events[0] == "status"
    assert "assistant_delta" in events
    assert events[-1] == "final"


def test_chat_stream_value_error_converted_to_503_error_event() -> None:
    async def _run_turn(_: ChatTurnRequest) -> ChatTurnResponse:
        raise ValueError("provider unavailable")

    runtime = SimpleNamespace(agent_orchestrator=SimpleNamespace(run_turn=_run_turn))
    stream = chat._chat_event_stream(ChatTurnRequest(message="hello"), runtime)
    lines = _collect_lines(stream)
    final = json.loads(lines[-1].strip())
    assert final["event"] == "error"
    assert final["data"]["status"] == status.HTTP_503_SERVICE_UNAVAILABLE


def test_chat_stream_unexpected_exception_converted_and_logged(monkeypatch) -> None:
    async def _run_turn(_: ChatTurnRequest) -> ChatTurnResponse:
        raise RuntimeError("boom")

    logged = {"called": False}

    def _log_exception(message: str) -> None:
        logged["called"] = True
        assert "Chat stream failed" in message

    runtime = SimpleNamespace(agent_orchestrator=SimpleNamespace(run_turn=_run_turn))
    monkeypatch.setattr(chat.logger, "exception", _log_exception)
    stream = chat._chat_event_stream(ChatTurnRequest(message="hello"), runtime)
    lines = _collect_lines(stream)
    final = json.loads(lines[-1].strip())
    assert final["event"] == "error"
    assert final["data"]["status"] == 500
    assert logged["called"] is True


def test_tool_payload_status_summary_structure() -> None:
    payload = chat._build_tool_status_payload(
        {
            "execution": "map_search",
            "satellite_imagery": {"ok": True},
            "map_session": {"overlays": [{"id": "a"}, {"id": "b"}]},
        }
    )
    assert payload["available"] is True
    assert payload["execution"] == "map_search"
    assert payload["has_satellite_imagery"] is True
    assert payload["has_map_session"] is True
    assert payload["overlay_count"] == 2
