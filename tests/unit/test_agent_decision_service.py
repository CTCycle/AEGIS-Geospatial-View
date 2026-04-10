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
        available_tools=[],
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
        available_tools=[{"name": "location_to_coordinates", "description": "Geocode"}],
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
        available_tools=[],
    )
    assert decision.feasibility.is_supported is False
    assert decision.should_trigger_search is False


def test_decision_service_requests_integration_when_explicit_and_unavailable() -> None:
    service = DecisionService(llm_factory=LLMFactory(), provider="ollama", model="llama3.2")
    decision = service.decide(
        conversation_context="# message 1\ntomtom traffic in Rome\n\n# extracted info\n{}",
        user_message="Show TomTom traffic in Rome",
        extracted_state=ExtractedIntent(location={"city": "Rome", "country": "Italy"}),
        retrieval={
            "basemaps": [],
            "overlays": [
                {
                    "id": "tomtom_traffic_flow",
                    "label": "TomTom Traffic Flow",
                    "provider": "tomtom",
                    "is_available": False,
                    "availability_reason": "TomTom API key is not configured.",
                    "score": 0.9,
                    "distance": 0.1,
                }
            ],
            "providers": [],
        },
        available_tools=[],
    )
    assert decision.execution_mode == "clarify"
    assert decision.should_trigger_search is False
    assert decision.clarification_question is not None
    assert "API key" in decision.clarification_question
