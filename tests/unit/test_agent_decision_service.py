from __future__ import annotations

from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.llm.factory import LLMFactory


###############################################################################
def test_decision_service_requires_location() -> None:
    service = DecisionService(
        llm_factory=LLMFactory(), provider="ollama", model="llama3.2"
    )
    decision = service.decide(
        conversation_context="# message 1\nshow traffic\n\n# extracted info\n{}",
        user_message="show traffic",
        extracted_state=ExtractedIntent(),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        available_tools=[],
    )
    assert decision.decision == "clarify"
    assert decision.should_trigger_search is False


###############################################################################
def test_decision_service_routes_coordinate_lookup_requests() -> None:
    service = DecisionService(
        llm_factory=LLMFactory(), provider="ollama", model="llama3.2"
    )
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


###############################################################################
def test_decision_service_rejects_non_geospatial_requests() -> None:
    service = DecisionService(
        llm_factory=LLMFactory(), provider="ollama", model="llama3.2"
    )
    decision = service.decide(
        conversation_context="# message 1\nwrite a poem\n\n# extracted info\n{}",
        user_message="Write a poem about spring.",
        extracted_state=ExtractedIntent(),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        available_tools=[],
    )
    assert decision.feasibility.is_supported is False
    assert decision.should_trigger_search is False


###############################################################################
def test_decision_service_routes_direct_weather_tool_with_location() -> None:
    service = DecisionService(
        llm_factory=LLMFactory(), provider="ollama", model="llama3.2"
    )
    decision = service.decide(
        conversation_context="# message 1\nweather forecast in Rome\n\n# extracted info\n{}",
        user_message="Give me the weather forecast for Rome",
        extracted_state=ExtractedIntent(location={"city": "Rome", "country": "Italy"}),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        available_tools=[
            {"name": "get_weather_forecast", "description": "Forecast weather"}
        ],
    )
    assert decision.execution_mode == "search"
    assert decision.tool_target == "get_weather_forecast"
    assert decision.should_trigger_search is False


###############################################################################
def test_decision_service_requests_integration_when_explicit_and_unavailable() -> None:
    service = DecisionService(
        llm_factory=LLMFactory(), provider="ollama", model="llama3.2"
    )
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


###############################################################################
def test_decision_service_treats_place_lookup_as_geospatial() -> None:
    service = DecisionService(
        llm_factory=LLMFactory(), provider="ollama", model="llama3.2"
    )
    decision = service.decide(
        conversation_context="# message 1\nfind area near Tour Eiffel\n\n# extracted info\n{}",
        user_message="I need to find the area nearby the Tour Eiffel",
        extracted_state=ExtractedIntent(certainty=0.2),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        available_tools=[],
    )
    assert decision.execution_mode in {"geocode", "search", "clarify"}
    assert decision.feasibility.is_supported is True
    assert decision.decision != "clarify" or decision.clarification_question is not None


###############################################################################
def test_decision_service_treats_street_address_as_geocodable() -> None:
    service = DecisionService(
        llm_factory=LLMFactory(), provider="ollama", model="llama3.2"
    )
    decision = service.decide(
        conversation_context="# message 1\ncheck via tesserete\n\n# extracted info\n{}",
        user_message="I need to check Via Tesserete 16 in Ticino, Switzerland",
        extracted_state=ExtractedIntent(certainty=0.1),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        available_tools=[],
    )
    assert decision.feasibility.is_supported is True
    assert decision.execution_mode in {"geocode", "search", "clarify"}


###############################################################################
def test_decision_service_forces_search_when_coordinates_exist() -> None:
    service = DecisionService(
        llm_factory=LLMFactory(), provider="ollama", model="llama3.2"
    )
    decision = service.decide(
        conversation_context="# message 1\nrestaurants near coords\n\n# extracted info\n{}",
        user_message="Find restaurants near 40.7580, -73.9855",
        extracted_state=ExtractedIntent(
            coordinates={"latitude": 40.7580, "longitude": -73.9855}
        ),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        available_tools=[],
    )
    assert decision.execution_mode == "search"
    assert decision.should_trigger_search is True


###############################################################################
def test_decision_service_routes_map_request_without_meta_question() -> None:
    service = DecisionService(
        llm_factory=LLMFactory(), provider="ollama", model="llama3.2"
    )
    decision = service.decide(
        conversation_context="user: I want to see the area nearby the Coliseum",
        user_message="I want to see the area nearby the Coliseum",
        extracted_state=ExtractedIntent(
            location={"address": "Coliseum, Rome"}, location_type="poi"
        ),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        available_tools=[{"name": "map_search", "description": "Run map search"}],
    )
    assert decision.execution_mode == "search"
    assert decision.tool_target == "map_search"
    assert decision.should_trigger_search is True
