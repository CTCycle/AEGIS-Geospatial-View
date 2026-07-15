from __future__ import annotations

import json

import pytest

from server.domain.agent.extraction_schemas import LLMParserExtraction
from server.services.agent.parser_service import ParserService
from server.services.llm.prompts import PARSER_SYSTEM_PROMPT
from server.services.llm.errors import LLMConfigurationError

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
def test_parser_service_classifies_direct_query() -> None:
    parser = ParserService(llm_factory=_FactoryStub(), provider="openai", model="gpt-4.1-mini")
    result = parser.parse_turn(
        user_message="What are the coordinates of the Colosseum in Rome?",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert result.task_class == "direct_query"
    assert result.normalized_action.action_id == "geospatial_data_retrieval"

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
    parser = ParserService(llm_factory=_FactoryStub(), provider="openai", model="gpt-4.1-mini")
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
    parser = ParserService(llm_factory=_FactoryStub(), provider="openai", model="gpt-4.1-mini")
    result = parser.parse_turn(
        user_message="اعرض جودة الهواء في القاهرة على الخريطة.",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert [item.raw_value for item in result.location_signals] == ["القاهرة"]
    assert result.ambiguities == []

###############################################################################
def test_parser_service_does_not_create_heuristic_location_fallbacks() -> None:
    parser = ParserService(llm_factory=_FactoryStub(), provider="openai", model="gpt-4.1-mini")
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
def test_parser_domain_rules_infer_city_scale_viewport_intent() -> None:
    extracted = ParserService._apply_domain_rules(
        "show the entire city",
        LLMParserExtraction(),
        {},
    )

    assert extracted.viewport_intent is not None
    assert extracted.viewport_intent.scope == "city"
