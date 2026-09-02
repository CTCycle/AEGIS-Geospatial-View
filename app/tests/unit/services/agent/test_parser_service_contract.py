from __future__ import annotations

import pytest
from time import monotonic

from server.domain.agent.extraction_schemas import LLMParserExtraction
from server.prompts.parser import PARSER_SCHEMA_CORRECTION, build_parser_prompt
from server.services.agent.parser_service import ParserService
from server.services.llm.errors import LLMProviderRequestError, LLMResponseParsingError


###############################################################################
def _failure():  # noqa: ANN202
    return ParserService.build_parser_failure_turn_result(
        user_message="Show weather near Rome",
        memory_snapshot={},
        conversation_messages=[],
        provider_error={
            "code": "provider_request_failed",
            "category": "provider_api",
            "provider": "opencode-go",
            "model": "deepseek-v4-flash",
            "stage": "structured_output",
        },
    )


###############################################################################
def test_parser_failure_contract_is_non_executable_and_diagnostic() -> None:
    result = _failure()

    assert result.task_class == "unclear"
    assert result.normalized_action.action_id == "unknown"
    assert result.location_signals == []
    assert result.requested_layers == []
    assert result.requested_basemap is None
    assert result.overlay_commands == []
    assert result.expected_frontend_update == "failure_diagnostic"
    assert result.failure_category == "provider_api"


###############################################################################
def test_structural_coordinate_extraction_is_independent_of_execution_planning() -> (
    None
):
    extracted = ParserService._extract_coordinate_signal("Show a map of 41.9, 12.5")

    assert extracted is not None
    assert extracted.signal_type == "coordinates"
    assert extracted.latitude == 41.9
    assert extracted.longitude == 12.5


###############################################################################
class _PromptProvider:
    # -------------------------------------------------------------------------
    def __init__(self, *, invalid_first: bool = False) -> None:
        self.invalid_first = invalid_first
        self.requests = []

    # -------------------------------------------------------------------------
    def structured_output(self, request, schema):  # noqa: ANN001
        _ = schema
        self.requests.append(request)
        if self.invalid_first and len(self.requests) == 1:
            raise LLMResponseParsingError(
                provider="test",
                model="test-model",
                stage="structured_output",
                detail="The structured payload did not match the extraction schema.",
            )
        return LLMParserExtraction(
            task_class="general_question",
            action_id="chat_response",
            requires_location=False,
        ).model_dump(mode="json")


###############################################################################
class _PromptFactory:
    # -------------------------------------------------------------------------
    def __init__(self, provider: _PromptProvider) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> _PromptProvider:
        _ = provider
        return self.provider


###############################################################################
def test_parser_uses_canonical_prompt_for_normal_and_schema_correction_calls() -> None:
    provider = _PromptProvider(invalid_first=True)
    parser = ParserService(
        llm_factory=_PromptFactory(provider),  # type: ignore[arg-type]
        settings_repo=object(),
        provider="test",
        model="test-model",
    )

    parser.parse_turn(
        user_message="What is currently on the map?",
        memory_snapshot={},
        conversation_messages=[],
    )

    assert len(provider.requests) == 2
    assert provider.requests[0].messages[0]["content"] == build_parser_prompt()
    corrected_prompt = provider.requests[1].messages[0]["content"]
    assert corrected_prompt == build_parser_prompt(schema_correction=True)
    assert corrected_prompt.count(PARSER_SCHEMA_CORRECTION) == 1


###############################################################################
def test_parser_normalizes_explicit_null_overlay_patch() -> None:
    class _Provider:
        def structured_output(self, request, schema):  # noqa: ANN001
            _ = request, schema
            return {
                "task_class": "map_search",
                "action_id": "overlay_control",
                "requires_location": False,
                "overlay_commands": [
                    {
                        "action": "hide",
                        "selector": {"concepts": ["weather"]},
                        "patch": None,
                    }
                ],
                "parser_confidence": 0.9,
            }

    class _Factory:
        def get_provider(self, provider: str):  # noqa: ANN001
            _ = provider
            return _Provider()

    result = ParserService(
        llm_factory=_Factory(),  # type: ignore[arg-type]
        settings_repo=object(),
        provider="test",
        model="test-model",
    ).parse_turn(
        user_message="Hide the weather overlay",
        memory_snapshot={},
        conversation_messages=[],
    )

    assert len(result.overlay_commands) == 1
    assert result.overlay_commands[0].patch.model_dump(mode="json") == {
        "opacity": None,
        "time": None,
        "style": None,
        "format": None,
    }


###############################################################################
def test_parser_maps_unknown_model_action_to_generic_data_action_with_semantics() -> None:
    class _Provider:
        def structured_output(self, request, schema):  # noqa: ANN001
            _ = request, schema
            return {
                "task_class": "direct_query",
                "action_id": "weather_query",
                "action_tags": ["weather"],
                "requested_concepts": ["weather"],
                "requires_location": True,
                "location_signals": [
                    {"signal_type": "city", "raw_value": "Rome", "confidence": 0.9}
                ],
                "parser_confidence": 0.9,
            }

    class _Factory:
        def get_provider(self, provider: str):  # noqa: ANN001
            _ = provider
            return _Provider()

    result = ParserService(
        llm_factory=_Factory(),  # type: ignore[arg-type]
        settings_repo=object(),
        provider="test",
        model="test-model",
    ).parse_turn(
        user_message="Show the weather in Rome",
        memory_snapshot={},
        conversation_messages=[],
    )

    assert result.normalized_action.action_id == "geospatial_data_retrieval"
    assert result.requested_concepts == ["weather"]


###############################################################################
def test_parser_prioritizes_actionable_data_over_context_query_label() -> None:
    class _Provider:
        def structured_output(self, request, schema):  # noqa: ANN001
            _ = request, schema
            return {
                "task_class": "direct_query",
                "action_id": "weather_query",
                "action_tags": ["weather"],
                "requested_concepts": ["temperature"],
                "context_query": {"kind": "active_location"},
                "relationship": "follow_up",
                "tools_needed": True,
                "requires_location": True,
                "location_signals": [
                    {
                        "signal_type": "deictic",
                        "raw_value": "there",
                        "normalized_value": "there",
                        "confidence": 0.9,
                    }
                ],
                "parser_confidence": 0.9,
            }

    class _Factory:
        def get_provider(self, provider: str):  # noqa: ANN001
            _ = provider
            return _Provider()

    result = ParserService(
        llm_factory=_Factory(),  # type: ignore[arg-type]
        settings_repo=object(),
        provider="test",
        model="test-model",
    ).parse_turn(
        user_message="What is the current temperature there?",
        memory_snapshot={"active_location": {"label": "Rome"}},
        conversation_messages=[],
    )

    assert result.context_query.kind == "none"
    assert result.relationship == "follow_up"
    assert result.requested_concepts == ["temperature"]


def test_parser_recovers_omitted_deictic_reference_for_memory_resolution() -> None:
    class _Provider:
        def structured_output(self, request, schema):  # noqa: ANN001
            _ = request, schema
            return {
                "task_class": "direct_query",
                "action_id": "get_weather_forecast",
                "requested_concepts": ["temperature"],
                "relationship": "follow_up",
                "tools_needed": True,
                "requires_location": True,
                "location_signals": [],
                "parser_confidence": 0.9,
            }

    class _Factory:
        def get_provider(self, provider: str):  # noqa: ANN001
            _ = provider
            return _Provider()

    result = ParserService(
        llm_factory=_Factory(),  # type: ignore[arg-type]
        settings_repo=object(),
        provider="test",
        model="test-model",
    ).parse_turn(
        user_message="What is the current temperature there?",
        memory_snapshot={
            "active_location": {
                "label": "Rome",
                "latitude": 41.9,
                "longitude": 12.5,
            }
        },
        conversation_messages=[],
    )

    assert result.location_signals[0].signal_type == "deictic"
    assert result.location_signals[0].source == "text"
    assert result.ambiguities == []


@pytest.mark.parametrize(
    ("task_class", "action_id", "typed_fields", "requires_location"),
    [
        (
            "map_search",
            "chat_response",
            {"location_signals": [{"signal_type": "city", "raw_value": "Quito"}]},
            True,
        ),
        (
            "direct_query",
            "chat_response",
            {"requested_concepts": ["weather"]},
            False,
        ),
        (
            "map_search",
            "unknown",
            {},
            True,
        ),
    ],
)
def test_typed_execution_invariants_override_inconsistent_model_flags(
    task_class: str,
    action_id: str,
    typed_fields: dict[str, object],
    requires_location: bool,
) -> None:
    extracted = LLMParserExtraction(
        task_class=task_class,  # type: ignore[arg-type]
        action_id=action_id,
        requires_location=False,
        tools_needed=False,
        direct_response_sufficient=True,
        parser_confidence=0.9,
        **typed_fields,
    )

    normalized = ParserService._apply_domain_rules(
        "generic request",
        extracted,
        {},
    )

    assert normalized.tools_needed is True
    assert normalized.direct_response_sufficient is False
    assert normalized.requires_location is requires_location


###############################################################################
def test_parser_retry_does_not_start_after_deadline(monkeypatch) -> None:
    parser = ParserService(
        llm_factory=object(),  # type: ignore[arg-type]
        settings_repo=object(),
        provider="test",
        model="test-model",
    )
    calls = 0

    def expired_extract(**kwargs):  # noqa: ANN003, ANN202
        nonlocal calls
        calls += 1
        raise LLMResponseParsingError(
            provider="test",
            model="test-model",
            stage="structured_intent_extraction",
            detail="invalid structured payload",
        )

    monkeypatch.setattr(parser, "_extract_turn", expired_extract)

    with pytest.raises(LLMResponseParsingError):
        parser._extract_turn_with_retry(
            user_message="show a map",
            memory_snapshot={},
            recent_messages=[],
            deadline_monotonic=monotonic() - 1.0,
        )

    assert calls == 1


###############################################################################
def test_unexpected_parser_exception_has_categorized_provider_diagnostic() -> None:
    class _BrokenProvider:
        # -------------------------------------------------------------------------
        def structured_output(self, request, schema):  # noqa: ANN001
            _ = request, schema
            raise RuntimeError("provider returned an unusable response")

    class _Factory:
        # -------------------------------------------------------------------------
        def get_provider(self, provider: str):  # noqa: ANN001
            _ = provider
            return _BrokenProvider()

    result = ParserService(
        llm_factory=_Factory(),  # type: ignore[arg-type]
        settings_repo=object(),
        provider="test",
        model="test-model",
    ).parse_turn(
        user_message="show a map of an unknown place",
        memory_snapshot={},
        conversation_messages=[],
    )

    assert result.failure_category == "provider_api"
    assert result.provider_error is not None
    assert result.provider_error["code"] == "parser_unavailable"
    assert result.provider_error["category"] == "provider_api"


###############################################################################
def test_parser_failure_preserves_provider_context_usage() -> None:
    context_usage = {
        "estimated_input_tokens": 321,
        "selected_context_window": None,
        "model_context_limit": None,
        "usage_percent": None,
        "provider": "opencode-go",
        "model": "deepseek-v4-flash",
    }

    class _TimeoutProvider:
        calls = 0

        def structured_output(self, request, schema):  # noqa: ANN001
            _ = request, schema
            self.calls += 1
            raise LLMProviderRequestError(
                provider="opencode-go",
                model="deepseek-v4-flash",
                stage="structured_output",
                code="provider_timeout",
                retryable=False,
                context_usage=context_usage,
            )

    provider = _TimeoutProvider()

    class _Factory:
        def get_provider(self, provider_name: str) -> _TimeoutProvider:
            _ = provider_name
            return provider

    result = ParserService(
        llm_factory=_Factory(),  # type: ignore[arg-type]
        settings_repo=object(),
        provider="opencode-go",
        model="deepseek-v4-flash",
    ).parse_turn_with_usage(
        user_message="tell me what you can do",
        memory_snapshot={},
        conversation_messages=[],
    )

    assert result.context_usage == context_usage
    assert provider.calls == 1
    assert result.turn_contract.provider_error is not None
    assert result.turn_contract.provider_error["code"] == "provider_timeout"
    assert result.turn_contract.provider_error["detail"]
