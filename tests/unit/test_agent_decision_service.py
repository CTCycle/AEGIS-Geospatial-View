from __future__ import annotations

from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.llm.factory import LLMFactory


def test_decision_service_requires_location() -> None:
    service = DecisionService(llm_factory=LLMFactory(), provider="ollama", model="llama3.2")
    decision = service.decide(
        conversation_context="# message 1\nshow traffic\n\n# extracted info\n{}",
        user_message="show traffic",
        extracted_state=ExtractedIntent(),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
    )
    assert decision.decision == "clarify"
    assert decision.should_trigger_search is False


def test_decision_service_routes_coordinate_lookup_requests() -> None:
    service = DecisionService(llm_factory=LLMFactory(), provider="ollama", model="llama3.2")
    decision = service.decide(
        conversation_context="# message 1\ncoordinates for Rome\n\n# extracted info\n{}",
        user_message="What are the coordinates for Rome, Italy?",
        extracted_state=ExtractedIntent(location={"city": "Rome", "country": "Italy"}),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
    )
    assert decision.execution_mode == "geocode"
    assert decision.tool_target == "location_to_coordinates"
    assert decision.should_trigger_search is False


def test_decision_service_rejects_non_geospatial_requests() -> None:
    service = DecisionService(llm_factory=LLMFactory(), provider="ollama", model="llama3.2")
    decision = service.decide(
        conversation_context="# message 1\nwrite a poem\n\n# extracted info\n{}",
        user_message="Write a poem about spring.",
        extracted_state=ExtractedIntent(),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
    )
    assert decision.feasibility.is_supported is False
    assert decision.should_trigger_search is False
