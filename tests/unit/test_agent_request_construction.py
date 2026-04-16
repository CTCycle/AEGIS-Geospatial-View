from __future__ import annotations

import json
from typing import Any

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.agent.chat_response_service import ChatResponseService
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.agent.parser_service import ParserService
from AEGIS.server.services.llm.types import ChatCompletionResult


###############################################################################
class _ParserProviderStub:
    def __init__(self) -> None:
        self.last_request = None
        self.last_schema = None

    def structured_output(self, request, schema):  # noqa: ANN001
        self.last_request = request
        self.last_schema = schema
        return {}


###############################################################################
class _ChatProviderStub:
    def __init__(self, *, content: str) -> None:
        self.content = content
        self.last_request = None

    def chat(self, request):  # noqa: ANN001
        self.last_request = request
        return ChatCompletionResult(content=self.content, raw={})


###############################################################################
class _FactoryStub:
    def __init__(self, *, parser: Any = None, agent: Any = None, chat: Any = None) -> None:
        self._parser = parser
        self._agent = agent
        self._chat = chat

    def get_parser_provider(self, provider: str):  # noqa: ANN001
        return self._parser

    def get_agent_provider(self, provider: str):  # noqa: ANN001
        return self._agent

    def get_chat_provider(self, provider: str):  # noqa: ANN001
        return self._chat


###############################################################################
def test_parser_service_includes_context_then_machine_readable_inputs() -> None:
    parser_provider = _ParserProviderStub()
    service = ParserService(
        llm_factory=_FactoryStub(parser=parser_provider),  # type: ignore[arg-type]
        provider="ollama",
        model="llama3.2",
    )
    state = ExtractedIntent.model_validate({"location": {"city": "Rome", "country": "Italy"}})
    context = "user: Find Rome\n\n# current extracted state\n{}"

    service.extract_patch(conversation_context=context, latest_state=state, user_message="same place")

    request = parser_provider.last_request
    assert request is not None
    assert request.messages[0]["role"] == "system"
    assert request.messages[1]["role"] == "user"
    assert request.messages[1]["content"] == context
    assert "latest_state=" in request.messages[2]["content"]
    assert "latest_user_message=same place" in request.messages[2]["content"]


###############################################################################
def test_decision_service_includes_context_and_retrieval_payload() -> None:
    agent_payload = {
        "decision": "search_and_complete",
        "should_trigger_search": True,
        "location_status": "valid",
        "requires_geocoding": False,
        "selected_basemap_id": "osm_default",
        "selected_overlay_ids": ["fires"],
        "clarification_question": None,
        "chat_instructions": {
            "tone": "clear_and_direct",
            "must_explain_limitations": True,
            "must_offer_refinements": True,
            "must_confirm_search_start": False,
        },
        "reasoning_summary": "ok",
        "feasibility": {"is_supported": True, "blocking_reason": None},
    }
    agent_provider = _ChatProviderStub(content=json.dumps(agent_payload))
    service = DecisionService(
        llm_factory=_FactoryStub(agent=agent_provider),  # type: ignore[arg-type]
        provider="ollama",
        model="llama3.2",
    )
    context = "user: Find Rome\n\n# current extracted state\n{}"
    retrieval = {"basemaps": [{"id": "osm_default"}], "overlays": [{"id": "fires"}], "providers": []}
    state = ExtractedIntent.model_validate({"location": {"city": "Rome"}})

    service.decide(
        conversation_context=context,
        user_message="compare air quality and weather in Rome",
        extracted_state=state,
        retrieval=retrieval,
        available_tools=[{"name": "map_search", "description": "Map search tool"}],
    )

    request = agent_provider.last_request
    assert request is not None
    assert request.messages[1]["content"] == context
    payload = json.loads(request.messages[2]["content"])
    assert payload["user_message"] == "compare air quality and weather in Rome"
    assert payload["retrieval"] == retrieval
    assert payload["available_tools"] == [{"name": "map_search", "description": "Map search tool"}]


###############################################################################
def test_chat_response_service_includes_context_and_decision_payload() -> None:
    chat_provider = _ChatProviderStub(content="Done")
    service = ChatResponseService(
        llm_factory=_FactoryStub(chat=chat_provider),  # type: ignore[arg-type]
        provider="ollama",
        model="llama3.2",
    )
    context = "user: Find Rome\n\n# current extracted state\n{}"
    decision = AgentDecision(
        decision="search_and_complete",
        should_trigger_search=True,
        location_status="valid",
        requires_geocoding=False,
        selected_basemap_id="osm_default",
        selected_overlay_ids=[],
        reasoning_summary="ok",
    )
    state = ExtractedIntent.model_validate({"location": {"city": "Rome"}})
    retrieval = {
        "basemaps": [{"id": "osm_default", "label": "OpenStreetMap", "provider": "fallback", "is_available": True}],
        "overlays": [{"id": "fires", "label": "Fires", "provider": "gibs", "is_available": True}],
        "providers": [],
    }
    search_result = {"map_session": {"center": {"latitude": 41.9, "longitude": 12.5}, "overlays": ["fires"]}}

    service.generate(
        conversation_context=context,
        user_message="show fires",
        extracted_state=state,
        decision=decision,
        retrieval=retrieval,
        search_result=search_result,
    )

    request = chat_provider.last_request
    assert request is not None
    assert request.messages[1]["content"] == context
    payload = json.loads(request.messages[2]["content"])
    assert payload["decision"]["decision"] == "search_and_complete"
    assert payload["retrieval"]["basemaps"][0]["label"] == "OpenStreetMap"
    assert "id" not in payload["retrieval"]["basemaps"][0]
    assert payload["search_result"]["map_session"]["overlay_count"] == 1
