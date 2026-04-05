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
            "location": {"name": "Rome, Italy", "coordinates": {"latitude": 41.9, "longitude": 12.5}, "bbox": None, "granularity": "city", "is_partial": False, "ambiguity_reason": None},
            "map_preferences": {"map_type": "auto", "map_type_confidence": 0.8, "basemap_preference": None, "overlay_candidates": []},
            "task": {"user_intent": "map_search", "scope": "concrete_area", "requires_external_fact_finding": False, "is_geographically_actionable": True},
            "temporal_context": {"normalized_datetime": explicit_datetime or "2026-01-01T00:00:00Z"},
            "planning": {
                "missing_information": [],
                "confidence": 0.8,
                "should_execute_search": True,
                "follow_up_question": None,
                "fallback_mode": "none",
            },
        }

    monkeypatch.setattr(orchestrator, "extract_intent", fake_intent)
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
            "location": {"name": "Springfield", "coordinates": None, "bbox": None, "granularity": "city", "is_partial": True, "ambiguity_reason": "multiple_matches"},
            "map_preferences": {"map_type": "auto", "map_type_confidence": 0.2, "basemap_preference": None, "overlay_candidates": []},
            "task": {"user_intent": "map_search", "scope": "broad_but_usable_area", "requires_external_fact_finding": False, "is_geographically_actionable": True},
            "temporal_context": {"normalized_datetime": explicit_datetime or "2026-01-01T00:00:00Z"},
            "planning": {
                "missing_information": ["location"],
                "confidence": 0.2,
                "should_execute_search": False,
                "follow_up_question": "Which Springfield did you mean?",
                "fallback_mode": "partial_location",
            },
        }

    monkeypatch.setattr(orchestrator, "extract_intent", ambiguous_intent)
    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Show traffic in Springfield")))
    assert result.follow_up_required is True
    assert result.fallback_mode == "partial_location"
