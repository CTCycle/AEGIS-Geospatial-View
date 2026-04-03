from __future__ import annotations

import asyncio

from AEGIS.server.domain.chat import ChatTurnRequest
from AEGIS.server.services.agent.orchestrator import AgentOrchestrator


class _SearchOrchestratorStub:
    async def execute(self, payload):  # noqa: ANN001
        return {
            "payload": {"ok": True},
            "map_session": {
                "center": {"latitude": 41.9, "longitude": 12.5},
                "bounds": [12.4, 41.8, 12.6, 42.0],
            },
        }


def test_chat_orchestrator_executes_when_intent_complete(monkeypatch) -> None:
    orchestrator = AgentOrchestrator(search_orchestrator=_SearchOrchestratorStub())

    def fake_intent(text: str, explicit_datetime: str | None = None):  # noqa: ANN001
        return {
            "request_text": text,
            "location": {"text": "Rome, Italy", "coordinates": {"latitude": 41.9, "longitude": 12.5}},
            "display_area": {"mode": "point", "radius_m": 2500.0},
            "view": {"view_mode": "interactive_map", "map_type": "auto"},
            "overlays": {"requested": []},
            "planning": {
                "user_intent": "map_search",
                "datetime_inference": explicit_datetime or "2026-01-01T00:00:00Z",
                "missing_information": [],
                "confidence": 0.8,
                "should_execute_search": True,
                "follow_up_question": None,
            },
        }

    monkeypatch.setattr(orchestrator, "_extract_intent", fake_intent)
    result = asyncio.run(
        orchestrator.run_turn(ChatTurnRequest(message="Find me Rome weather layers"))
    )
    assert result.follow_up_required is False
    assert result.map_session is not None


def test_chat_orchestrator_follow_up_for_ambiguous_location(monkeypatch) -> None:
    orchestrator = AgentOrchestrator(search_orchestrator=_SearchOrchestratorStub())

    def ambiguous_intent(text: str, explicit_datetime: str | None = None):  # noqa: ANN001
        return {
            "request_text": text,
            "location": {"text": "Springfield", "ambiguity_reason": "multiple_matches"},
            "display_area": {"mode": "inferred"},
            "view": {"view_mode": "interactive_map", "map_type": "auto"},
            "overlays": {"requested": []},
            "planning": {
                "datetime_inference": explicit_datetime or "2026-01-01T00:00:00Z",
                "missing_information": ["location"],
                "confidence": 0.2,
                "should_execute_search": False,
                "follow_up_question": "Which Springfield did you mean?",
            },
        }

    monkeypatch.setattr(orchestrator, "_extract_intent", ambiguous_intent)
    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Show traffic in Springfield")))
    assert result.follow_up_required is True
