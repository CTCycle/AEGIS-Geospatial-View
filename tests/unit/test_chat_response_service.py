from __future__ import annotations

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.agent.chat_response_service import ChatResponseService


###############################################################################
class _ChatProviderStub:
    def __init__(self, content: str) -> None:
        self.content = content

    def chat(self, request):  # noqa: ANN001
        class _Result:
            def __init__(self, payload: str) -> None:
                self.content = payload

        return _Result(self.content)


###############################################################################
class _FactoryStub:
    def __init__(self, content: str) -> None:
        self._provider = _ChatProviderStub(content)

    def get_chat_provider(self, provider: str):  # noqa: ANN001
        return self._provider


###############################################################################
def _decision(**kwargs):  # noqa: ANN003, ANN202
    payload = {
        "decision": "search_and_complete",
        "execution_mode": "search",
        "should_trigger_search": True,
        "location_status": "valid",
        "requires_geocoding": False,
        "reasoning_summary": "ok",
    }
    payload.update(kwargs)
    return AgentDecision(**payload)


###############################################################################
def test_chat_response_service_normalizes_plain_text_output() -> None:
    service = ChatResponseService(
        llm_factory=_FactoryStub("```json\n{\"foo\": \"bar\"}\n```\n**Map ready**"),  # type: ignore[arg-type]
        provider="ollama",
        model="llama3.2",
    )
    response = service.generate(
        conversation_context="# message",
        user_message="show map",
        extracted_state=ExtractedIntent(),
        decision=_decision(),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        search_result={"map_session": {"center": {"latitude": 1, "longitude": 1}, "overlays": []}},
    )
    assert response == "Map ready"


###############################################################################
def test_chat_response_service_fallback_for_geocode_success_is_plain_text() -> None:
    class _FailingFactory:
        def get_chat_provider(self, provider: str):  # noqa: ANN001
            raise RuntimeError("chat unavailable")

    service = ChatResponseService(llm_factory=_FailingFactory(), provider="ollama", model="llama3.2")  # type: ignore[arg-type]
    response = service.generate(
        conversation_context="# message",
        user_message="coordinates of Rome",
        extracted_state=ExtractedIntent(),
        decision=_decision(execution_mode="geocode", should_trigger_search=False, tool_target="location_to_coordinates"),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        search_result={"geocode_result": {"lat": 41.9, "lon": 12.5}},
    )
    assert "latitude 41.9" in response
    assert "longitude 12.5" in response


###############################################################################
def test_chat_response_service_fallback_for_missing_integration_is_plain_text() -> None:
    class _FailingFactory:
        def get_chat_provider(self, provider: str):  # noqa: ANN001
            raise RuntimeError("chat unavailable")

    service = ChatResponseService(llm_factory=_FailingFactory(), provider="ollama", model="llama3.2")  # type: ignore[arg-type]
    response = service.generate(
        conversation_context="# message",
        user_message="tomtom traffic",
        extracted_state=ExtractedIntent(),
        decision=_decision(
            decision="clarify",
            execution_mode="clarify",
            should_trigger_search=False,
            reasoning_summary="Missing required integration",
            clarification_question="TomTom key needed.",
        ),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        search_result=None,
    )
    assert response == "TomTom key needed."


###############################################################################
def test_chat_response_service_reports_overlay_unmet_filters() -> None:
    class _FailingFactory:
        def get_chat_provider(self, provider: str):  # noqa: ANN001
            raise RuntimeError("chat unavailable")

    service = ChatResponseService(llm_factory=_FailingFactory(), provider="ollama", model="llama3.2")  # type: ignore[arg-type]
    response = service.generate(
        conversation_context="# message",
        user_message="show pm2.5 overlay",
        extracted_state=ExtractedIntent(),
        decision=_decision(selected_overlay_ids=["openmeteo_air_quality_forecast"]),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        search_result={
            "map_session": {"center": {"latitude": 1, "longitude": 1}, "overlays": []},
            "payload": {"unmet_filters": ["pm2.5"]},
        },
    )
    assert "Unmet filters" in response


###############################################################################
def test_chat_response_service_missing_location_is_single_human_question() -> None:
    class _FailingFactory:
        def get_chat_provider(self, provider: str):  # noqa: ANN001
            raise RuntimeError("chat unavailable")

    service = ChatResponseService(llm_factory=_FailingFactory(), provider="ollama", model="llama3.2")  # type: ignore[arg-type]
    response = service.generate(
        conversation_context="# context",
        user_message="show traffic",
        extracted_state=ExtractedIntent(),
        decision=_decision(
            decision="clarify",
            execution_mode="clarify",
            should_trigger_search=False,
            location_status="missing",
            tool_target="map_search",
            missing_fields=["location"],
            clarification_kind="missing_location",
            clarification_question="Which location should I search?",
        ),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
        search_result=None,
    )
    assert response.endswith("?")
    assert response.count("?") == 1
    assert "location" in response.lower()
