from __future__ import annotations

import asyncio

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.chat import ChatTurnRequest
from AEGIS.server.domain.extraction.models import ExtractedIntentPatch
from AEGIS.server.services.agent.chat_response_service import ChatResponseService
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.agent.orchestrator import AgentOrchestrator
from AEGIS.server.services.agent.parser_service import ParserService


class _VectorRetrieverStub:
    def __init__(self) -> None:
        self.last_query = None

    def retrieve_candidates(self, query, *, top_k=8):  # noqa: ANN001
        self.last_query = query
        return {"basemaps": [], "overlays": [], "providers": []}


class _SearchOrchestratorStub:
    nominatim_service = object()
    catalog_service = object()

    async def execute(self, payload):  # noqa: ANN001
        return {
            "payload": {"ok": True},
            "map_session": {
                "center": {"latitude": 41.9, "longitude": 12.5},
                "bounds": [12.4, 41.8, 12.6, 42.0],
            },
        }


def _allow_provider_checks(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(AgentOrchestrator, "_check_ollama_availability", lambda self, settings: (True, None))


def test_chat_orchestrator_executes_when_location_available(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    retriever = _VectorRetrieverStub()
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=retriever,
    )

    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: ExtractedIntentPatch(
            location={"address": "Rome, Italy"},
            coordinates={"latitude": 41.9, "longitude": 12.5},
            user_goal="traffic and weather",
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: AgentDecision(
            decision="search_and_complete",
            execution_mode="search",
            tool_target="map_search",
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
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: "ok",
    )

    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Find me Rome weather layers")))
    assert result.follow_up_required is False
    assert result.map_session is not None
    assert result.extracted_state is not None
    assert retriever.last_query == "Find me Rome weather layers"


def test_chat_orchestrator_follow_up_for_missing_location(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
    )

    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: ExtractedIntentPatch(),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: AgentDecision(
            decision="clarify",
            execution_mode="clarify",
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
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: "Which location?",
    )

    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Show traffic")))
    assert result.follow_up_required is True
    assert result.fallback_mode == "needs_clarification"


def test_chat_orchestrator_passes_prior_messages_in_context(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
    )
    contexts: list[str] = []

    def _capture_parser(self, conversation_context, latest_state, user_message):  # noqa: ANN001
        contexts.append(conversation_context)
        return ExtractedIntentPatch(location={"city": "Rome", "country": "Italy"})

    monkeypatch.setattr(ParserService, "extract_patch", _capture_parser)
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: AgentDecision(
            decision="clarify",
            execution_mode="clarify",
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
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: "Which location?",
    )

    first = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Find Rome")))
    asyncio.run(
        orchestrator.run_turn(
            ChatTurnRequest(session_id=first.session_id, message="same place, show fires")
        )
    )
    assert any("Find Rome" in context for context in contexts)
    assert any("same place, show fires" in context for context in contexts)


def test_chat_orchestrator_returns_coordinate_lookup_without_map_session(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    class _AgentToolsStub:
        def describe_tools(self):  # noqa: ANN201
            return [{"name": "location_to_coordinates", "description": "geocode"}]

        async def geocode_location(self, *, address, city, country_name, country_code=None):  # noqa: ANN001
            assert city == "Rome"
            return {"lat": 41.9, "lon": 12.5, "bbox": [12.4, 41.8, 12.6, 42.0]}

    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
        agent_tools=_AgentToolsStub(),
    )

    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: ExtractedIntentPatch(
            location={"city": "Rome", "country": "Italy"},
            user_goal="find coordinates",
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: AgentDecision(
            decision="search_and_complete",
            execution_mode="geocode",
            tool_target="location_to_coordinates",
            should_trigger_search=False,
            location_status="valid",
            requires_geocoding=True,
            reasoning_summary="test",
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: "Coordinates: 41.9, 12.5.",
    )

    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Give me the coordinates of Rome")))
    assert result.follow_up_required is False
    assert result.map_session is None
    assert result.tool_payload is not None
    assert result.tool_payload["execution"] == "location_to_coordinates"


def test_chat_orchestrator_integration_blocker_returns_follow_up(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
    )
    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: ExtractedIntentPatch(
            location={"city": "Rome", "country": "Italy"},
            user_goal="traffic",
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: AgentDecision(
            decision="clarify",
            execution_mode="clarify",
            should_trigger_search=False,
            location_status="valid",
            requires_geocoding=False,
            clarification_question="TomTom API key is not configured. Use another traffic layer?",
            reasoning_summary="Missing required integration",
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: "TomTom API key is not configured. Use another traffic layer?",
    )
    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="show TomTom traffic in Rome")))
    assert result.follow_up_required is True


def test_chat_orchestrator_geocode_uses_direct_coordinates_when_present(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    class _AgentToolsStub:
        def describe_tools(self):  # noqa: ANN201
            return [{"name": "location_to_coordinates", "description": "geocode"}]

        async def geocode_location(self, *, address, city, country_name, country_code=None):  # noqa: ANN001
            raise AssertionError("geocode service should not be called for direct coordinates")

    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
        agent_tools=_AgentToolsStub(),
    )
    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: ExtractedIntentPatch(
            coordinates={"latitude": 41.9, "longitude": 12.5},
            user_goal="coordinates lookup",
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: AgentDecision(
            decision="search_and_complete",
            execution_mode="geocode",
            tool_target="location_to_coordinates",
            should_trigger_search=False,
            location_status="valid",
            requires_geocoding=False,
            reasoning_summary="test",
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: "The coordinates are latitude 41.9 and longitude 12.5.",
    )

    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="coordinates 41.9, 12.5")))
    assert result.map_session is None
    assert result.tool_payload is not None
    assert result.tool_payload["execution"] == "location_to_coordinates"
    assert result.tool_payload["result"]["lat"] == 41.9
    assert result.tool_payload["result"]["lon"] == 12.5


def test_chat_orchestrator_executes_direct_weather_tool(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)

    class _AgentToolsStub:
        def describe_tools(self):  # noqa: ANN201
            return [{"name": "get_weather_forecast", "description": "weather"}]

        async def geocode_location(self, *, address, city, country_name, country_code=None):  # noqa: ANN001
            return {"lat": 41.9, "lon": 12.5}

        async def get_weather_forecast(self, *, latitude: float, longitude: float):  # noqa: ANN001
            return {"kind": "weather_forecast", "latitude": latitude, "longitude": longitude}

    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
        agent_tools=_AgentToolsStub(),
    )
    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: ExtractedIntentPatch(
            location={"city": "Rome", "country": "Italy"},
            user_goal="weather forecast",
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: AgentDecision(
            decision="search_and_complete",
            execution_mode="search",
            tool_target="get_weather_forecast",
            should_trigger_search=False,
            location_status="valid",
            requires_geocoding=True,
            reasoning_summary="direct weather",
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: "Forecast ready.",
    )

    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="weather forecast in Rome")))
    assert result.map_session is None
    assert result.tool_payload is not None
    assert result.tool_payload["execution"] == "get_weather_forecast"
