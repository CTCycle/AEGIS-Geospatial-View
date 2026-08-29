from __future__ import annotations

import pytest

from server.domain.agent.extraction_schemas import LLMParserExtraction
from server.services.agent.parser_service import ParserService
from server.prompts.parser import PARSER_SYSTEM_PROMPT
from server.services.llm.errors import (
    LLMConfigurationError,
    LLMProviderRequestError,
    LLMResponseParsingError,
)

###############################################################################
class _ProviderStub:

    # -------------------------------------------------------------------------
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or {
            "task_class": "general_question",
            "action_id": "chat_response",
            "action_label": "General question",
            "task_tags": ["chat"],
            "action_tags": [],
            "requires_location": False,
            "location_signals": [],
            "temporal_signal": {"mode": "none"},
            "ambiguities": [],
            "disallowed_patterns": [],
            "parser_confidence": 0.9,
        }

    # -------------------------------------------------------------------------
    def structured_output(self, request, schema):  # noqa: ANN001
        _ = request, schema
        return dict(self.payload)


###############################################################################
class _FactoryStub:

    # -------------------------------------------------------------------------
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.provider = _ProviderStub(payload)

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str):  # noqa: ARG002
        return self.provider


###############################################################################
class _ConfigErrorFactoryStub:

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str):  # noqa: ARG002
        raise LLMConfigurationError("OpenAI credentials are saved but cannot be decrypted.")


###############################################################################
class _RetryProviderStub(_ProviderStub):

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    # -------------------------------------------------------------------------
    def structured_output(self, request, schema):  # noqa: ANN001
        self.calls += 1
        if self.calls == 1:
            raise LLMProviderRequestError(
                provider="opencode-go",
                model="mimo-v2.5",
                stage="structured_output",
                code="provider_request_failed",
                retryable=True,
            )
        return super().structured_output(request, schema)


###############################################################################
class _RetryFactoryStub:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.provider = _RetryProviderStub()

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str):  # noqa: ARG002
        return self.provider


###############################################################################
class _SchemaCorrectionProviderStub(_ProviderStub):

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    # -------------------------------------------------------------------------
    def structured_output(self, request, schema):  # noqa: ANN001
        self.calls += 1
        if self.calls == 1:
            raise LLMResponseParsingError(
                provider="opencode-go",
                model="deepseek-v4-flash",
                stage="structured_output",
                detail="The structured payload did not match the extraction schema.",
            )
        return super().structured_output(request, schema)


###############################################################################
class _SchemaCorrectionFactoryStub:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.provider = _SchemaCorrectionProviderStub()

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str):  # noqa: ARG002
        return self.provider

###############################################################################
def test_parser_service_classifies_direct_query() -> None:
    parser = ParserService(
        llm_factory=_FactoryStub(
            {
                "task_class": "direct_query",
                "action_id": "geospatial_data_retrieval",
                "action_label": "Location lookup",
                "task_tags": ["direct_query"],
                "action_tags": ["coordinates"],
                "requires_location": True,
                "location_signals": [
                    {
                        "signal_type": "poi",
                        "raw_value": "Colosseum in Rome",
                        "normalized_value": "Colosseum, Rome",
                        "confidence": 0.9,
                    }
                ],
                "temporal_signal": {"mode": "none"},
                "ambiguities": [],
                "disallowed_patterns": [],
                "parser_confidence": 0.9,
            }
        ),
        settings_repo=object(),
        provider="openai",
        model="gpt-4.1-mini",
    )
    result = parser.parse_turn(
        user_message="What are the coordinates of the Colosseum in Rome?",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert result.task_class == "direct_query"
    assert result.normalized_action.action_id == "geospatial_data_retrieval"

###############################################################################
def test_parser_service_retries_transient_provider_failure() -> None:
    factory = _RetryFactoryStub()
    parser = ParserService(
        llm_factory=factory,
        settings_repo=object(),
        provider="opencode-go",
        model="mimo-v2.5",
    )

    result = parser.parse_turn(
        user_message="What is the difference between a layer and a basemap?",
        memory_snapshot={},
        conversation_messages=[],
    )

    assert result.task_class == "general_question"
    assert factory.provider.calls == 2

###############################################################################
def test_parser_service_retries_schema_correction_on_the_same_model() -> None:
    factory = _SchemaCorrectionFactoryStub()
    parser = ParserService(
        llm_factory=factory,
        settings_repo=object(),
        provider="opencode-go",
        model="deepseek-v4-flash",
    )

    result = parser.parse_turn(
        user_message="Switch to satellite imagery",
        memory_snapshot={},
        conversation_messages=[],
    )

    assert result.failure_category is None
    assert factory.provider.calls == 2

###############################################################################
def test_parser_schema_accepts_poi_region_and_street_location_signals() -> None:
    extracted = LLMParserExtraction.model_validate(
        {
            "location_signals": [
                {
                    "signal_type": "poi",
                    "raw_value": "Colosseum",
                    "normalized_value": "Colosseum",
                    "confidence": 0.9,
                },
                {
                    "signal_type": "region",
                    "raw_value": "Lazio",
                    "normalized_value": "Lazio",
                    "confidence": 0.8,
                },
                {
                    "signal_type": "street",
                    "raw_value": "Via Pisa",
                    "normalized_value": "Via Pisa",
                    "confidence": 0.8,
                },
            ]
        }
    )

    assert [signal.signal_type for signal in extracted.location_signals] == [
        "poi",
        "region",
        "street",
    ]

###############################################################################
def test_parser_service_normalizes_recent_messages_to_strings() -> None:
    parser = ParserService(llm_factory=_FactoryStub(), settings_repo=object(), provider="openai", model="gpt-4.1-mini")
    result = parser.parse_turn(
        user_message="Where am I?",
        memory_snapshot={"active_location": None},
        conversation_messages=[
            {
                "id": 515,
                "conversation_id": "conversation-217",
                "turn_index": 0,
                "role": "assistant",
                "content": None,
                "created_at": None,
            }
        ],
    )
    recent = result.conversation_context.recent_messages
    assert len(recent) == 1
    assert recent[0]["id"] == "515"
    assert recent[0]["conversation_id"] == "conversation-217"
    assert recent[0]["turn_index"] == "0"
    assert recent[0]["content"] == ""

###############################################################################
def test_parser_service_does_not_hide_configuration_errors() -> None:
    parser = ParserService(
        llm_factory=_ConfigErrorFactoryStub(),
        settings_repo=object(),
        provider="openai",
        model="gpt-4.1-mini",
    )

    with pytest.raises(LLMConfigurationError):
        parser.parse_turn(
            user_message="Show Rome",
            memory_snapshot={},
            conversation_messages=[],
        )

###############################################################################
def test_parser_prompt_enforces_multilingual_and_verbatim_location_rules() -> None:
    assert "The user may write in any language" in PARSER_SYSTEM_PROMPT
    assert "raw_value must be a verbatim span" in PARSER_SYSTEM_PROMPT
    assert "requested_visualizations must use only canonical ids" in PARSER_SYSTEM_PROMPT
    assert "viewport_intent" in PARSER_SYSTEM_PROMPT

###############################################################################
def test_parser_service_drops_non_verbatim_location_hallucinations() -> None:
    parser = ParserService(
        llm_factory=_FactoryStub(
            {
                "task_class": "map_search",
                "action_id": "map_search",
                "action_label": "Air quality map",
                "task_tags": ["map"],
                "action_tags": ["air_quality"],
                "requested_visualizations": ["air_quality"],
                "requires_location": True,
                "location_signals": [
                    {
                        "signal_type": "city",
                        "raw_value": "القاهرة",
                        "normalized_value": "Cairo",
                        "confidence": 0.9,
                    },
                    {
                        "signal_type": "city",
                        "raw_value": "Khartoum",
                        "normalized_value": "Khartoum",
                        "confidence": 0.85,
                    },
                ],
                "temporal_signal": {"mode": "none"},
                "ambiguities": [],
                "disallowed_patterns": [],
                "parser_confidence": 0.9,
            }
        ),
        settings_repo=object(),
        provider="openai",
        model="gpt-4.1-mini",
    )
    result = parser.parse_turn(
        user_message="اعرض جودة الهواء في القاهرة على الخريطة.",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert [item.raw_value for item in result.location_signals] == ["القاهرة"]
    assert result.ambiguities == []

###############################################################################
def test_parser_service_does_not_create_heuristic_location_fallbacks() -> None:
    parser = ParserService(
        llm_factory=_FactoryStub(
            {
                "task_class": "map_search",
                "action_id": "map_search",
                "action_label": "Map request",
                "task_tags": ["map"],
                "action_tags": ["map"],
                "requires_location": True,
                "location_signals": [],
                "temporal_signal": {"mode": "none"},
                "ambiguities": [],
                "disallowed_patterns": [],
                "parser_confidence": 0.7,
            }
        ),
        settings_repo=object(),
        provider="openai",
        model="gpt-4.1-mini",
    )
    result = parser.parse_turn(
        user_message="No model location around Rome",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert result.location_signals == []
    assert result.ambiguities == ["missing_location"]

###############################################################################
def test_parser_domain_boundary_preserves_typed_fields_without_prose_inference() -> None:
    extracted = ParserService._apply_domain_rules(
        "Show an unrelated place with weather and satellite imagery.",
        LLMParserExtraction(
            task_class="map_search",
            requested_layers=["openmeteo_weather_forecast"],
            requested_basemap="esri_world_imagery",
            location_signals=[
                {
                    "signal_type": "city",
                    "raw_value": "unrelated place",
                    "normalized_value": "unrelated place",
                }
            ],
        ),
        {"active_visualization": {"basemap_id": "osm_default"}},
    )

    assert extracted.requested_layers == ["openmeteo_weather_forecast"]
    assert extracted.requested_basemap == "esri_world_imagery"
    assert [item.raw_value for item in extracted.location_signals] == ["unrelated place"]


###############################################################################
def test_parser_domain_boundary_does_not_invent_intent_from_prose() -> None:
    extracted = ParserService._apply_domain_rules(
        "Switch to satellite imagery over an unspecified place.",
        LLMParserExtraction(),
        {},
    )

    assert extracted.task_class == "unclear"
    assert extracted.location_signals == []
    assert extracted.requested_layers == []
    assert extracted.requested_basemap is None
    assert extracted.overlay_commands == []


