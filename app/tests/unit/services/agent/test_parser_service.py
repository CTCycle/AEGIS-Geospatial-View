from __future__ import annotations

import json

import pytest

from server.domain.agent.extraction_schemas import LLMParserExtraction
from server.services.agent.parser_service import ParserService
from server.services.llm.prompts import PARSER_SYSTEM_PROMPT
from server.services.llm.errors import (
    LLMConfigurationError,
    LLMProviderRequestError,
    LLMResponseParsingError,
)

###############################################################################
class _ProviderStub:

    # -------------------------------------------------------------------------
    def structured_output(self, request, schema):  # noqa: ANN001
        payload = json.loads(request.messages[-1]["content"])
        user_message = payload.get("user_message", "")
        if "Colosseum" in user_message:
            return {
                "task_class": "direct_query",
                "action_id": "geospatial_data_retrieval",
                "action_label": "Location lookup",
                "task_tags": ["direct_query"],
                "action_tags": ["coordinates"],
                "requires_location": True,
                "location_signals": [
                    {
                        "signal_type": "city",
                        "raw_value": "Rome",
                        "normalized_value": "Rome",
                        "confidence": 0.9,
                    }
                ],
                "temporal_signal": {"mode": "none"},
                "ambiguities": [],
                "disallowed_patterns": [],
                "parser_confidence": 0.9,
            }
        if "القاهرة" in user_message:
            return {
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
                        "raw_value": "الخرطوم",
                        "normalized_value": "Khartoum",
                        "confidence": 0.85,
                    },
                ],
                "temporal_signal": {"mode": "none"},
                "ambiguities": ["'الخرطية' likely intended as 'الخرطوم' (Khartoum)"],
                "disallowed_patterns": [],
                "parser_confidence": 0.9,
            }
        if "No model location" in user_message:
            return {
                "task_class": "map_search",
                "action_id": "map_search",
                "action_label": "General map request",
                "task_tags": ["map"],
                "action_tags": ["map"],
                "requires_location": True,
                "location_signals": [],
                "temporal_signal": {"mode": "none"},
                "ambiguities": [],
                "disallowed_patterns": [],
                "parser_confidence": 0.7,
            }
        return {
            "task_class": "general_question",
            "action_id": "map_search",
            "action_label": "General map request",
            "task_tags": ["map"],
            "action_tags": ["map"],
            "requires_location": False,
            "location_signals": [],
            "temporal_signal": {"mode": "none"},
            "ambiguities": [],
            "disallowed_patterns": [],
            "parser_confidence": 0.5,
        }

###############################################################################
class _FactoryStub:

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str):  # noqa: ARG002
        return _ProviderStub()

###############################################################################
class _ConfigErrorFactoryStub:

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str):  # noqa: ARG002
        raise LLMConfigurationError("OpenAI credentials are saved but cannot be decrypted.")

###############################################################################
class _RetryProviderStub(_ProviderStub):

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
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
    parser = ParserService(llm_factory=_FactoryStub(), settings_repo=object(), provider="openai", model="gpt-4.1-mini")
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
    parser = ParserService(llm_factory=_FactoryStub(), settings_repo=object(), provider="openai", model="gpt-4.1-mini")
    result = parser.parse_turn(
        user_message="اعرض جودة الهواء في القاهرة على الخريطة.",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert [item.raw_value for item in result.location_signals] == ["القاهرة"]
    assert result.ambiguities == []

###############################################################################
def test_parser_service_does_not_create_heuristic_location_fallbacks() -> None:
    parser = ParserService(llm_factory=_FactoryStub(), settings_repo=object(), provider="openai", model="gpt-4.1-mini")
    result = parser.parse_turn(
        user_message="No model location around Rome",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert result.location_signals == []
    assert result.ambiguities == ["missing_location"]

###############################################################################
def test_parser_domain_rules_infer_local_viewport_intent_for_around_street_requests() -> None:
    extracted = ParserService._apply_domain_rules(
        "Show me satellite view around Via Pisa",
        LLMParserExtraction(),
        {},
    )

    assert extracted.viewport_intent is not None
    assert extracted.viewport_intent.scope == "street"
    assert extracted.requested_basemap == "esri_world_imagery"

###############################################################################
def test_parser_domain_rules_keep_satellite_view_as_basemap_only() -> None:
    extracted = ParserService._apply_domain_rules(
        "Show current satellite context for Rome, Italy.",
        LLMParserExtraction(requested_layers=["satellite"]),
        {},
    )

    assert extracted.requested_basemap == "esri_world_imagery"
    assert extracted.requested_layers == []

###############################################################################
def test_parser_domain_rules_tighten_viewport_for_closer_follow_up() -> None:
    extracted = ParserService._apply_domain_rules(
        "this is too high as point of view, i want to see much more closely",
        LLMParserExtraction(),
        {"active_visualization": {"viewport": {"radius_m": 2500.0}}},
    )

    assert extracted.viewport_intent is not None
    assert extracted.viewport_intent.scope == "street"
    assert extracted.viewport_intent.tighten_relative_to_active is True

###############################################################################
def test_parser_domain_rules_preserve_view_for_street_map_basemap_only_follow_up() -> None:
    extracted = ParserService._apply_domain_rules(
        "i want to switch to street maps view",
        LLMParserExtraction(),
        {"active_visualization": {"viewport": {"radius_m": 2500.0}}},
    )

    assert extracted.requested_basemap == "osm_default"
    assert extracted.viewport_intent is not None
    assert extracted.viewport_intent.scope == "preserve_current"

###############################################################################
def test_parser_domain_rules_preserve_active_location_for_satellite_follow_up() -> None:
    extracted = ParserService._apply_domain_rules(
        "Switch to satellite imagery",
        LLMParserExtraction(
            location_signals=[
                {
                    "signal_type": "city",
                    "raw_value": "Switch",
                    "normalized_value": "Switch, Pennsylvania",
                }
            ]
        ),
        {
            "active_visualization": {
                "resolved_location": {"label": "Lugano"},
            }
        },
    )

    assert extracted.location_signals == []
    assert extracted.map_target is None
    assert extracted.relationship == "follow_up"
    assert extracted.requested_basemap == "esri_world_imagery"
    assert extracted.viewport_intent is not None
    assert extracted.viewport_intent.scope == "preserve_current"

###############################################################################
def test_parser_domain_rules_select_openfreemap_styles() -> None:
    liberty = ParserService._apply_domain_rules(
        "Show a street map using OpenFreeMap Liberty",
        LLMParserExtraction(),
        {},
    )
    positron = ParserService._apply_domain_rules(
        "Use the clean OpenFreeMap Positron style",
        LLMParserExtraction(),
        {},
    )

    assert liberty.requested_basemap == "openfreemap_liberty"
    assert positron.requested_basemap == "openfreemap_positron"

###############################################################################
def test_parser_domain_rules_route_weather_addition_to_map_layer() -> None:
    extracted = ParserService._apply_domain_rules(
        "Add weather to the same map.",
        LLMParserExtraction(
            task_class="general_question",
            requires_location=True,
            requested_visualizations=["weather"],
            ambiguities=["missing_location"],
        ),
        {"active_visualization": {"basemap_id": "osm_default"}},
    )

    assert extracted.task_class == "map_search"
    assert extracted.requested_layers == ["openmeteo_weather_forecast"]
    assert extracted.tools_needed is True
    assert extracted.relationship == "follow_up"
    assert "missing_location" not in extracted.ambiguities
    assert extracted.viewport_intent is not None
    assert extracted.viewport_intent.scope == "preserve_current"


def test_parser_domain_rules_separate_global_overlay_remove_from_location_scope() -> None:
    global_remove = ParserService._apply_domain_rules(
        "Remove the weather overlay.",
        LLMParserExtraction(),
        {"active_visualization": {"basemap_id": "osm_default"}},
    )
    scoped_remove = ParserService._apply_domain_rules(
        "Remove the overlay over Switzerland.",
        LLMParserExtraction(),
        {"active_visualization": {"basemap_id": "osm_default"}},
    )

    assert global_remove.overlay_commands[0].action == "remove"
    assert global_remove.overlay_commands[0].selector.concepts == ["weather"]
    assert global_remove.overlay_commands[0].scope.kind == "global"
    assert global_remove.requires_location is False
    assert scoped_remove.overlay_commands[0].scope.kind == "location"
    assert scoped_remove.overlay_commands[0].scope.location is not None
    assert scoped_remove.overlay_commands[0].scope.location["label"] == "Switzerland"


def test_parser_domain_rules_use_current_view_for_local_overlay_commands() -> None:
    extracted = ParserService._apply_domain_rules(
        "Hide only the satellite layer in this area.",
        LLMParserExtraction(),
        {"active_visualization": {"basemap_id": "osm_default"}},
    )

    command = extracted.overlay_commands[0]
    assert command.action == "hide"
    assert command.selector.concepts == ["satellite"]
    assert command.scope.kind == "current_view"
    assert extracted.requested_basemap is None
    assert extracted.requires_location is False


def test_parser_domain_rules_preserve_explicit_basemap_in_compound_request() -> None:
    extracted = ParserService._apply_domain_rules(
        "Switch to satellite imagery and hide weather in this area.",
        LLMParserExtraction(
            requested_basemap="esri_world_imagery",
            overlay_commands=[
                {
                    "action": "hide",
                    "selector": {"concepts": ["weather"]},
                    "scope": {"kind": "current_view"},
                }
            ],
        ),
        {"active_visualization": {"basemap_id": "osm_default"}},
    )

    assert extracted.requested_basemap == "esri_world_imagery"
    assert extracted.overlay_commands[0].selector.concepts == ["weather"]


def test_parser_domain_rules_keep_only_and_location_scoped_show_are_independent() -> None:
    keep_only = ParserService._apply_domain_rules(
        "Keep only weather and remove the others.",
        LLMParserExtraction(),
        {"active_visualization": {"basemap_id": "osm_default"}},
    )
    show_local = ParserService._apply_domain_rules(
        "Show weather over Zurich.",
        LLMParserExtraction(),
        {},
    )

    assert keep_only.overlay_commands[0].action == "keep_only"
    assert keep_only.overlay_commands[0].selector.concepts == ["weather"]
    assert show_local.overlay_commands[0].action == "show"
    assert show_local.overlay_commands[0].scope.kind == "location"
    assert show_local.requires_location is True


def test_parser_domain_rules_capture_named_overlay_and_location_clause() -> None:
    extracted = ParserService._apply_domain_rules(
        "Remove X only from location Y.",
        LLMParserExtraction(),
        {},
    )

    command = extracted.overlay_commands[0]
    assert command.action == "remove"
    assert command.selector.concepts == ["X"]
    assert command.scope.kind == "location"
    assert command.scope.location is not None
    assert command.scope.location["label"] == "Y"

###############################################################################
def test_parser_domain_rules_infer_city_scale_viewport_intent() -> None:
    extracted = ParserService._apply_domain_rules(
        "show the entire city",
        LLMParserExtraction(),
        {},
    )

    assert extracted.viewport_intent is not None
    assert extracted.viewport_intent.scope == "city"
