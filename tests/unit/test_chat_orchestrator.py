from __future__ import annotations

import asyncio

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.chat import ChatTurnRequest
from AEGIS.server.domain.extraction.models import (
    ExtractedIntentPatch,
    StageAParserIntent,
    StageBSearchExtraction,
)
from AEGIS.server.services.agent.chat_response_service import ChatResponseService
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.agent.orchestrator import AgentOrchestrator
from AEGIS.server.services.agent.parser_service import ParserService


###############################################################################
class _VectorRetrieverStub:
    def __init__(self) -> None:
        self.last_query = None

    def retrieve_candidates(self, query, *, top_k=8):  # noqa: ANN001
        self.last_query = query
        return {"basemaps": [], "overlays": [], "providers": []}


###############################################################################
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


###############################################################################
def _allow_provider_checks(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        AgentOrchestrator,
        "_check_ollama_availability",
        lambda self, settings: (True, None),
    )


###############################################################################
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
        lambda self, conversation_context, latest_state, user_message: (
            ExtractedIntentPatch(
                location={"address": "Rome, Italy"},
                coordinates={"latitude": 41.9, "longitude": 12.5},
                user_goal="traffic and weather",
            )
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="search_and_complete",
                execution_mode="search",
                tool_target="map_search",
                should_trigger_search=True,
                location_status="valid",
                requires_geocoding=False,
                selected_basemap_id="osm_default",
                selected_overlay_ids=[],
                reasoning_summary="test",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "ok"
        ),
    )

    result = asyncio.run(
        orchestrator.run_turn(ChatTurnRequest(message="Find me Rome weather layers"))
    )
    assert result.follow_up_required is False
    assert result.map_session is not None
    assert result.extracted_state is not None
    assert retriever.last_query == "Find me Rome weather layers"


###############################################################################
def test_chat_orchestrator_follow_up_for_missing_location(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
    )

    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: (
            ExtractedIntentPatch()
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="clarify",
                execution_mode="clarify",
                should_trigger_search=False,
                location_status="missing",
                requires_geocoding=False,
                clarification_question="Which location?",
                reasoning_summary="missing",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "Which location?"
        ),
    )

    result = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Show traffic")))
    assert result.follow_up_required is True
    assert result.fallback_mode == "needs_clarification"


###############################################################################
def test_chat_orchestrator_passes_prior_messages_in_context(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
    )
    contexts: list[str] = []

    def _capture_stage_a(
        self,
        conversation_context,
        user_message,
        available_tools,
        certainty_threshold,
        max_retries,
    ):  # noqa: ANN001
        contexts.append(conversation_context)
        return StageAParserIntent(
            has_location=True,
            location_type="city",
            has_time_reference=False,
            requires_search=True,
            requires_data=True,
            required_tools=[],
            certainty=0.95,
        )

    monkeypatch.setattr(ParserService, "parse_stage_a_intent", _capture_stage_a)
    monkeypatch.setattr(
        ParserService,
        "parse_stage_b_enrichment",
        lambda self, conversation_context, user_message, retrieval, fallback_datetime: (
            StageBSearchExtraction(
                location={"city": "Rome", "country": "Italy"},
                time_reference=fallback_datetime,
            )
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="clarify",
                execution_mode="clarify",
                should_trigger_search=False,
                location_status="missing",
                requires_geocoding=False,
                clarification_question="Which location?",
                reasoning_summary="missing",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "Which location?"
        ),
    )

    first = asyncio.run(orchestrator.run_turn(ChatTurnRequest(message="Find Rome")))
    asyncio.run(
        orchestrator.run_turn(
            ChatTurnRequest(
                session_id=first.session_id, message="same place, show fires"
            )
        )
    )
    assert any("Find Rome" in context for context in contexts)
    assert any("same place, show fires" in context for context in contexts)


###############################################################################
def test_chat_orchestrator_returns_coordinate_lookup_without_map_session(
    monkeypatch,
) -> None:
    _allow_provider_checks(monkeypatch)

    class _AgentToolsStub:
        def describe_tools(self):  # noqa: ANN201
            return [{"name": "location_to_coordinates", "description": "geocode"}]

        async def geocode_location(
            self,
            *,
            address,
            city,
            country_name,
            country_code=None,
            expected_location_type=None,
        ):  # noqa: ANN001
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
        lambda self, conversation_context, latest_state, user_message: (
            ExtractedIntentPatch(
                location={"city": "Rome", "country": "Italy"},
                user_goal="find coordinates",
            )
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="search_and_complete",
                execution_mode="geocode",
                tool_target="location_to_coordinates",
                should_trigger_search=False,
                location_status="valid",
                requires_geocoding=True,
                reasoning_summary="test",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "Coordinates: 41.9, 12.5."
        ),
    )

    result = asyncio.run(
        orchestrator.run_turn(
            ChatTurnRequest(message="Give me the coordinates of Rome")
        )
    )
    assert result.follow_up_required is False
    assert result.map_session is None
    assert result.tool_payload is not None
    assert result.tool_payload["execution"] == "location_to_coordinates"


###############################################################################
def test_chat_orchestrator_integration_blocker_returns_follow_up(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
    )
    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: (
            ExtractedIntentPatch(
                location={"city": "Rome", "country": "Italy"},
                user_goal="traffic",
            )
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="clarify",
                execution_mode="clarify",
                should_trigger_search=False,
                location_status="valid",
                requires_geocoding=False,
                clarification_question="TomTom API key is not configured. Use another traffic layer?",
                reasoning_summary="Missing required integration",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "TomTom API key is not configured. Use another traffic layer?"
        ),
    )
    result = asyncio.run(
        orchestrator.run_turn(ChatTurnRequest(message="show TomTom traffic in Rome"))
    )
    assert result.follow_up_required is True


###############################################################################
def test_chat_orchestrator_geocode_uses_direct_coordinates_when_present(
    monkeypatch,
) -> None:
    _allow_provider_checks(monkeypatch)

    class _AgentToolsStub:
        def describe_tools(self):  # noqa: ANN201
            return [{"name": "location_to_coordinates", "description": "geocode"}]

        async def geocode_location(
            self,
            *,
            address,
            city,
            country_name,
            country_code=None,
            expected_location_type=None,
        ):  # noqa: ANN001
            raise AssertionError(
                "geocode service should not be called for direct coordinates"
            )

    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
        agent_tools=_AgentToolsStub(),
    )
    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: (
            ExtractedIntentPatch(
                coordinates={"latitude": 41.9, "longitude": 12.5},
                user_goal="coordinates lookup",
            )
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="search_and_complete",
                execution_mode="geocode",
                tool_target="location_to_coordinates",
                should_trigger_search=False,
                location_status="valid",
                requires_geocoding=False,
                reasoning_summary="test",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "The coordinates are latitude 41.9 and longitude 12.5."
        ),
    )

    result = asyncio.run(
        orchestrator.run_turn(ChatTurnRequest(message="coordinates 41.9, 12.5"))
    )
    assert result.map_session is None
    assert result.tool_payload is not None
    assert result.tool_payload["execution"] == "location_to_coordinates"
    assert result.tool_payload["result"]["lat"] == 41.9
    assert result.tool_payload["result"]["lon"] == 12.5


###############################################################################
def test_chat_orchestrator_geocode_retries_with_split_poi_and_city(
    monkeypatch,
) -> None:
    _allow_provider_checks(monkeypatch)
    calls: list[dict[str, str | None]] = []

    class _AgentToolsStub:
        def describe_tools(self):  # noqa: ANN201
            return [{"name": "location_to_coordinates", "description": "geocode"}]

        async def geocode_location(
            self,
            *,
            address,
            city,
            country_name,
            country_code=None,
            expected_location_type=None,
        ):  # noqa: ANN001
            _ = country_code, expected_location_type
            calls.append(
                {
                    "address": address,
                    "city": city,
                    "country_name": country_name,
                }
            )
            if address == "Colosseum" and city == "Rome":
                return {"lat": 41.8902, "lon": 12.4922}
            return None

    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
        agent_tools=_AgentToolsStub(),
    )
    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: (
            ExtractedIntentPatch(user_goal="coordinates lookup")
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="search_and_complete",
                execution_mode="geocode",
                tool_target="location_to_coordinates",
                should_trigger_search=False,
                location_status="valid",
                requires_geocoding=True,
                reasoning_summary="test",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "The coordinates are latitude 41.8902 and longitude 12.4922."
        ),
    )

    result = asyncio.run(
        orchestrator.run_turn(
            ChatTurnRequest(message="What are the coordinates of the Colosseum in Rome?")
        )
    )

    assert result.tool_payload is not None
    assert result.tool_payload["execution"] == "location_to_coordinates"
    assert result.tool_payload["result"]["lat"] == 41.8902
    assert result.tool_payload["result"]["lon"] == 12.4922
    assert calls[0]["address"] == "Colosseum in Rome"
    assert calls[1]["address"] == "Colosseum"
    assert calls[1]["city"] == "Rome"


###############################################################################
def test_chat_orchestrator_executes_direct_weather_tool(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)

    class _AgentToolsStub:
        def describe_tools(self):  # noqa: ANN201
            return [{"name": "get_weather_forecast", "description": "weather"}]

        async def geocode_location(
            self,
            *,
            address,
            city,
            country_name,
            country_code=None,
            expected_location_type=None,
        ):  # noqa: ANN001
            return {"lat": 41.9, "lon": 12.5}

        async def get_weather_forecast(self, *, latitude: float, longitude: float):  # noqa: ANN001
            return {
                "kind": "weather_forecast",
                "latitude": latitude,
                "longitude": longitude,
            }

    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
        agent_tools=_AgentToolsStub(),
    )
    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: (
            ExtractedIntentPatch(
                location={"city": "Rome", "country": "Italy"},
                user_goal="weather forecast",
            )
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="search_and_complete",
                execution_mode="search",
                tool_target="get_weather_forecast",
                should_trigger_search=False,
                location_status="valid",
                requires_geocoding=True,
                reasoning_summary="direct weather",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "Forecast ready."
        ),
    )

    result = asyncio.run(
        orchestrator.run_turn(ChatTurnRequest(message="weather forecast in Rome"))
    )
    assert result.map_session is None
    assert result.tool_payload is not None
    assert result.tool_payload["execution"] == "get_weather_forecast"


###############################################################################
def test_chat_orchestrator_clears_stale_coordinates_for_new_text_location(
    monkeypatch,
) -> None:
    _allow_provider_checks(monkeypatch)

    class _AgentToolsStub:
        def describe_tools(self):  # noqa: ANN201
            return [{"name": "location_to_coordinates", "description": "geocode"}]

        async def geocode_location(
            self,
            *,
            address,
            city,
            country_name,
            country_code=None,
            expected_location_type=None,
        ):  # noqa: ANN001
            if address and "Amphitheatre" in address:
                return {"lat": 37.422, "lon": -122.084}
            return None

    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
        agent_tools=_AgentToolsStub(),
    )

    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: (
            ExtractedIntentPatch(
                location={"address": "1600 Amphitheatre Parkway, Mountain View"}
            )
            if "Mountain View" in user_message
            else ExtractedIntentPatch(
                coordinates={"latitude": 40.7580, "longitude": -73.9855}
            )
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="search_and_complete",
                execution_mode="geocode",
                tool_target="location_to_coordinates",
                should_trigger_search=False,
                location_status="valid",
                requires_geocoding=True,
                reasoning_summary="test",
            )
        ),
    )

    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "coords"
        ),
    )

    first = asyncio.run(
        orchestrator.run_turn(
            ChatTurnRequest(message="Find restaurants near 40.7580, -73.9855")
        )
    )
    second = asyncio.run(
        orchestrator.run_turn(
            ChatTurnRequest(
                session_id=first.session_id,
                message="Locate 1600 Amphitheatre Parkway, Mountain View",
            )
        )
    )
    assert second.tool_payload is not None
    assert second.tool_payload["execution"] == "location_to_coordinates"
    if second.tool_payload.get("result") is not None:
        assert second.tool_payload["result"].get("lat") != 40.7580


###############################################################################
def test_chat_orchestrator_infers_overlay_ids_from_retrieval(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)

    class _RetrieverStub:
        def retrieve_candidates(self, query, *, top_k=8):  # noqa: ANN001
            return {
                "basemaps": [],
                "overlays": [
                    {
                        "id": "tomtom_traffic_flow",
                        "label": "TomTom Traffic Flow",
                        "provider": "tomtom",
                        "is_available": True,
                        "score": 0.9,
                        "distance": 0.1,
                    }
                ],
                "providers": [],
            }

    class _SearchStub(_SearchOrchestratorStub):
        async def execute(self, payload):  # noqa: ANN001
            return {
                "payload": {
                    "selected_overlay_ids": payload.overlay_ids,
                    "applied_filters": payload.semantic_filters,
                    "unmet_filters": [],
                },
                "map_session": {
                    "center": {"latitude": 41.9, "longitude": 12.5},
                    "bounds": [12.4, 41.8, 12.6, 42.0],
                    "overlays": [],
                },
            }

    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchStub(),
        vector_retriever=_RetrieverStub(),
    )

    monkeypatch.setattr(
        ParserService,
        "extract_patch",
        lambda self, conversation_context, latest_state, user_message: (
            ExtractedIntentPatch(
                location={"city": "Rome", "country": "Italy"},
                filters=["traffic"],
                user_goal="show traffic",
            )
        ),
    )
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="search_and_complete",
                execution_mode="search",
                tool_target="map_search",
                should_trigger_search=True,
                location_status="valid",
                requires_geocoding=False,
                selected_basemap_id="osm_default",
                selected_overlay_ids=[],
                reasoning_summary="test",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result: (
            "ok"
        ),
    )

    result = asyncio.run(
        orchestrator.run_turn(ChatTurnRequest(message="Show traffic in Rome"))
    )
    assert result.tool_payload is not None
    assert result.tool_payload["execution"] == "map_search"
    assert "tomtom_traffic_flow" in (
        result.tool_payload.get("selected_overlay_ids") or []
    )


###############################################################################
def test_chat_orchestrator_same_place_reuses_location(monkeypatch) -> None:
    _allow_provider_checks(monkeypatch)
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
    )

    def _stage_a(
        self,
        conversation_context,
        user_message,
        available_tools,
        certainty_threshold,
        max_retries,
    ):  # noqa: ANN001
        _ = conversation_context, available_tools, certainty_threshold, max_retries
        return StageAParserIntent(
            has_location="same place" not in user_message.lower(),
            location_type="city",
            has_time_reference=False,
            requires_search=True,
            requires_data=True,
            required_tools=[],
            certainty=0.92,
        )

    def _stage_b(
        self, conversation_context, user_message, retrieval, fallback_datetime
    ):  # noqa: ANN001
        _ = conversation_context, retrieval
        if "same place" in user_message.lower():
            return StageBSearchExtraction(time_reference=fallback_datetime)
        return StageBSearchExtraction(
            location={"city": "Rome", "country": "Italy", "location_type": "city"},
            time_reference=fallback_datetime,
        )

    monkeypatch.setattr(ParserService, "parse_stage_a_intent", _stage_a)
    monkeypatch.setattr(ParserService, "parse_stage_b_enrichment", _stage_b)
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="search_and_complete",
                execution_mode="search",
                tool_target="map_search",
                should_trigger_search=True,
                location_status="valid",
                requires_geocoding=False,
                reasoning_summary="ok",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result, execution_feedback=None: (
            "ok"
        ),
    )
    first = asyncio.run(
        orchestrator.run_turn(ChatTurnRequest(message="The Coliseum in Rome, Italy"))
    )
    second = asyncio.run(
        orchestrator.run_turn(
            ChatTurnRequest(
                session_id=first.session_id, message="same place, show traffic"
            )
        )
    )
    assert second.extracted_state["location"]["city"] == "Rome"


###############################################################################
def test_chat_orchestrator_new_task_clears_stale_filters_and_coordinates(
    monkeypatch,
) -> None:
    _allow_provider_checks(monkeypatch)
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
    )

    def _stage_a(
        self,
        conversation_context,
        user_message,
        available_tools,
        certainty_threshold,
        max_retries,
    ):  # noqa: ANN001
        _ = conversation_context, available_tools, certainty_threshold, max_retries
        return StageAParserIntent(
            has_location=True,
            location_type="address"
            if "Via San Bernardo" in user_message
            else "coordinates",
            has_time_reference=False,
            requires_search=True,
            requires_data=True,
            required_tools=[],
            certainty=0.94,
        )

    def _stage_b(
        self, conversation_context, user_message, retrieval, fallback_datetime
    ):  # noqa: ANN001
        _ = conversation_context, retrieval
        if "Via San Bernardo" in user_message:
            return StageBSearchExtraction(
                location={
                    "address": "Via San Bernardo 17 Canobbio",
                    "city": "Canobbio",
                    "country": "Switzerland",
                    "location_type": "address",
                },
                required_overlays=[],
                time_reference=fallback_datetime,
            )
        return StageBSearchExtraction(
            coordinates={"latitude": 41.9, "longitude": 12.5},
            location={"location_type": "coordinates"},
            required_overlays=["traffic"],
            time_reference=fallback_datetime,
        )

    monkeypatch.setattr(ParserService, "parse_stage_a_intent", _stage_a)
    monkeypatch.setattr(ParserService, "parse_stage_b_enrichment", _stage_b)
    monkeypatch.setattr(
        DecisionService,
        "decide",
        lambda self, conversation_context, user_message, extracted_state, retrieval, available_tools=None: (
            AgentDecision(
                decision="search_and_complete",
                execution_mode="search",
                tool_target="map_search",
                should_trigger_search=True,
                location_status="valid",
                requires_geocoding=False,
                reasoning_summary="ok",
            )
        ),
    )
    monkeypatch.setattr(
        ChatResponseService,
        "generate",
        lambda self, conversation_context, user_message, extracted_state, decision, retrieval, search_result, execution_feedback=None: (
            "ok"
        ),
    )
    first = asyncio.run(
        orchestrator.run_turn(
            ChatTurnRequest(message="Find restaurants near 41.9, 12.5 with traffic")
        )
    )
    second = asyncio.run(
        orchestrator.run_turn(
            ChatTurnRequest(
                session_id=first.session_id, message="Via San Bernardo 17 Canobbio"
            )
        )
    )
    assert second.extracted_state["coordinates"]["latitude"] is None
    assert second.extracted_state["coordinates"]["longitude"] is None
    assert second.extracted_state["filters"] == []


###############################################################################
def test_chat_orchestrator_derives_location_query_from_coordinate_question() -> None:
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        vector_retriever=_VectorRetrieverStub(),
    )

    query = orchestrator._derive_location_query_from_message(
        "What are the coordinates of the Colosseum in Rome?"
    )

    assert query == "Colosseum in Rome"
