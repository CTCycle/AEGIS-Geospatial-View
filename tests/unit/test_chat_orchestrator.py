from __future__ import annotations

import asyncio

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.chat import ChatTurnRequest
from AEGIS.server.domain.extraction.models import ExtractedIntent, ExtractedIntentPatch
from AEGIS.server.services.agent.chat_response_service import ChatResponseService
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.agent.orchestrator import AgentOrchestrator
from AEGIS.server.services.agent.parser_service import ParserService


class _SearchOrchestratorStub:
    async def execute(self, payload):  # noqa: ANN001
        return {
            "payload": {"ok": True},
            "map_session": {
                "center": {"latitude": 41.9, "longitude": 12.5},
                "bounds": [12.4, 41.8, 12.6, 42.0],
            },
        }


def test_chat_orchestrator_executes_when_location_available(monkeypatch) -> None:
    orchestrator = AgentOrchestrator(search_orchestrator=_SearchOrchestratorStub())

    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, latest_state, user_message: ExtractedIntentPatch(
            location={"address": "Rome, Italy"},
            coordinates={"latitude": 41.9, "longitude": 12.5},
            user_goal="traffic and weather",
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, user_message, extracted_state, retrieval: AgentDecision(
            decision="search_and_complete",
            should_trigger_search=True,
            location_status="valid",
            requires_geocoding=False,
            selected_basemap_id="osm_default",
            selected_overlay_ids=[],
            reasoning_summary="test",
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, user_message, extracted_state, decision, retrieval, search_result: "ok",
    )

    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Find me Rome weather layers")))
    assert result.follow_up_required is False
    assert result.map_session is not None
    assert result.extracted_state is not None


def test_chat_orchestrator_follow_up_for_missing_location(monkeypatch) -> None:
    orchestrator = AgentOrchestrator(search_orchestrator=_SearchOrchestratorStub())

    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, latest_state, user_message: ExtractedIntentPatch(),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, user_message, extracted_state, retrieval: AgentDecision(
            decision="clarify",
            should_trigger_search=False,
            location_status="missing",
            requires_geocoding=False,
            clarification_question="Which location?",
            reasoning_summary="missing",
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, user_message, extracted_state, decision, retrieval, search_result: "Which location?",
    )

    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Show traffic")))
    assert result.follow_up_required is True
    assert result.fallback_mode == "needs_clarification"
